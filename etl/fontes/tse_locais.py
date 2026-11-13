"""Locais de votação do TSE: o elo entre a seção eleitoral e a chave territorial (módulo ME).

Uso:
    python -m etl.fontes.tse_locais [--arquivo eleitorado_local_votacao_2024.zip ...]

Sem --arquivo, usa os arquivos em dados/bruto/tse_locais_votacao/ ou baixa, do CDN do TSE, os anos do
catálogo. O arquivo é nacional; ficam só as seções do município (PINEAL_COD_TSE, reserva por nome + UF).

Coordenada: o TSE publica NR_LATITUDE/NR_LONGITUDE nas extrações recentes (-1 = sem coordenada). Seção
sem coordenada é geocodificada pelo núcleo existente (endereço "RUA, 123" + nome do local + bairro do
TSE), se o CNEFE estiver carregado. Depois sql/90_eleitoral.sql atribui a chave territorial e refaz a
ponte seção -> território. Escopo e limites em docs/prd-eleitoral-2028.md.
"""

import argparse
import logging

import h3

from etl import baixar, db, leitura
from etl.fontes import tse_comum
from etl.geocodificar import geocodificar

log = logging.getLogger("tse_locais")
FONTE = "tse_locais_votacao"

COLUNAS = {
    "AA_ELEICAO": "ano_a",
    "ANO_ELEICAO": "ano_b",
    "SG_UF": "uf",
    "CD_MUNICIPIO": "cd_mun",
    "NM_MUNICIPIO": "nm_mun",
    "NR_ZONA": "zona",
    "NR_SECAO": "secao",
    "NR_LOCAL_VOTACAO": "nr_local",
    "NM_LOCAL_VOTACAO": "nome_local",
    "DS_ENDERECO": "endereco",
    "NM_BAIRRO": "bairro_tse",
    "NR_CEP": "cep",
    "QT_ELEITOR": "eleitores",
    "NR_SECAO_PRINCIPAL": "secao_principal",
    "NR_LATITUDE": "lat",
    "NR_LONGITUDE": "lon",
}
OBRIGATORIAS = ["SG_UF", "NR_ZONA", "NR_SECAO", "NM_LOCAL_VOTACAO"]

INT = "CASE WHEN btrim({c}) ~ '^\\d+$' THEN btrim({c})::INT END"
COORD = """CASE WHEN replace(btrim({c}), ',', '.') ~ '^-?\\d+(\\.\\d+)?$'
                 AND replace(btrim({c}), ',', '.')::NUMERIC BETWEEN {minimo} AND {maximo}
                 AND replace(btrim({c}), ',', '.')::NUMERIC <> -1
            THEN replace(btrim({c}), ',', '.')::NUMERIC END"""

INSERIR = f"""
    INSERT INTO eleicao_local_votacao (ano, nr_zona, nr_secao, nr_local, nome_local, endereco, bairro_tse,
                                       cep, eleitores, secao_principal, geo_origem, geom)
    SELECT DISTINCT ON (zona_n, secao_n)
           %(ano)s, zona_n, secao_n, {INT.format(c="nr_local")}, NULLIF(btrim(nome_local), ''),
           NULLIF(btrim(endereco), ''), NULLIF(btrim(bairro_tse), ''), norm_cep(cep),
           {INT.format(c="eleitores")}, NULLIF({INT.format(c="secao_principal")}, secao_n),
           CASE WHEN x.lat_n IS NOT NULL AND x.lon_n IS NOT NULL THEN 'tse' END,
           CASE WHEN x.lat_n IS NOT NULL AND x.lon_n IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(x.lon_n, x.lat_n), 4326) END
    FROM (
        SELECT t.*, {INT.format(c="zona")} AS zona_n, {INT.format(c="secao")} AS secao_n FROM lv t
        WHERE {tse_comum.FILTRO_MUNICIPIO}
          AND coalesce(NULLIF(btrim(ano_a), ''), NULLIF(btrim(ano_b), ''), %(ano)s::TEXT) = %(ano)s::TEXT
    ) t
    CROSS JOIN LATERAL (
        SELECT {COORD.format(c="lat", minimo=-90, maximo=90)} AS lat_n,
               {COORD.format(c="lon", minimo=-180, maximo=180)} AS lon_n
    ) x
    WHERE zona_n IS NOT NULL AND secao_n IS NOT NULL
    ORDER BY zona_n, secao_n, nr_local
"""


def carregar(conn, caminho) -> tuple[int, int]:
    ano = tse_comum.ano_do_nome(caminho.name)
    if not ano:
        raise SystemExit(f"não achei o ano no nome do arquivo: {caminho.name} (renomeie com o ano, ex.: _2024)")
    leitura.copiar_para_temp(conn, caminho, "lv", COLUNAS, OBRIGATORIAS)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM eleicao_local_votacao WHERE ano = %s", (ano,))
        cur.execute(INSERIR, {"ano": ano, **tse_comum.parametros_municipio()})
        n = cur.rowcount
        cur.execute("DROP TABLE lv")
    return ano, n


def geocodificar_sem_coordenada(conn, ano: int) -> None:
    """Endereço do TSE vem livre ("RUA X, 123 - CENTRO"): logradouro antes da vírgula, primeiro número depois."""
    geocodificar(
        conn,
        f"""
        SELECT ano || '-' || nr_zona || '-' || nr_secao, norm_cep(cep),
               norm_logradouro(split_part(endereco, ',', 1)), norm_logradouro_completa(split_part(endereco, ',', 1)),
               norm_numero(substring(endereco FROM ',\\s*(\\d+)')), norm_nome(nome_local), norm_txt(bairro_tse)
        FROM eleicao_local_votacao WHERE geom IS NULL AND endereco IS NOT NULL AND ano = {int(ano)}
    """,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE eleicao_local_votacao g
            SET geom = a.geom, geo_precisao = a.geo_precisao,
                geo_origem = CASE WHEN a.geom IS NULL THEN 'nao_localizado' ELSE 'geocodificado' END
            FROM alvo a WHERE a.id = g.ano || '-' || g.nr_zona || '-' || g.nr_secao
            """
        )
        cur.execute("DROP TABLE alvo")


def gravar_h3(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ano, nr_zona, nr_secao, ST_Y(geom), ST_X(geom) FROM eleicao_local_votacao"
            " WHERE geom IS NOT NULL AND h3_9 IS NULL"
        )
        linhas = [
            (h3.latlng_to_cell(lat, lon, 8), h3.latlng_to_cell(lat, lon, 9), a, z, s)
            for a, z, s, lat, lon in cur.fetchall()
        ]
        cur.executemany(
            "UPDATE eleicao_local_votacao SET h3_8 = %s, h3_9 = %s WHERE ano = %s AND nr_zona = %s AND nr_secao = %s",
            linhas,
        )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", action="append", help="zip ou csv de um ano (repetível)")
    args = ap.parse_args(argv)
    with db.etapa("tse_locais"), db.conectar() as conn:
        db.criar_schema(conn)
        anos = {}
        for caminho in tse_comum.obter_arquivos(FONTE, args.arquivo):
            ano, n = carregar(conn, caminho)
            anos[ano] = n
            if db.contar(conn, "SELECT count(*) FROM cnefe"):
                geocodificar_sem_coordenada(conn, ano)
            db.registrar(conn, FONTE, str(caminho), caminho.name, baixar.sha256(caminho), n, ano=ano)
        gravar_h3(conn)
        db.executar_sql(conn, "90_eleitoral.sql")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT coalesce(geo_origem, 'nao_localizado'), count(*) FROM eleicao_local_votacao"
                " GROUP BY 1 ORDER BY 2 DESC"
            )
            origens = cur.fetchall()
    log.info("seções por ano: %s; localização: %s", anos, dict(origens))


if __name__ == "__main__":
    main()
