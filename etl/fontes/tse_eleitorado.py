"""Perfil do eleitorado por seção do TSE (módulo ME): gênero x faixa etária x escolaridade.

Uso:
    python -m etl.fontes.tse_eleitorado [--arquivo perfil_eleitor_secao_2024_PR.zip ...]

Sem --arquivo, usa os arquivos em dados/bruto/tse_perfil_eleitorado/ ou baixa, do CDN do TSE, os anos
do catálogo (um zip por ano e UF). Ficam só as seções do município, agregadas em gênero, faixa etária
e escolaridade (o estado civil fica de fora da chave para a tabela não explodir). Só agregados: nenhum
dado nominal de eleitor (docs/prd-eleitoral-2028.md).
"""

import argparse
import logging

from etl import baixar, db, leitura
from etl.fontes import tse_comum

log = logging.getLogger("tse_eleitorado")
FONTE = "tse_perfil_eleitorado"

COLUNAS = {
    "ANO_ELEICAO": "ano",
    "SG_UF": "uf",
    "CD_MUNICIPIO": "cd_mun",
    "NM_MUNICIPIO": "nm_mun",
    "NR_ZONA": "zona",
    "NR_SECAO": "secao",
    "DS_GENERO": "genero",
    "DS_FAIXA_ETARIA": "faixa_etaria",
    "DS_GRAU_ESCOLARIDADE": "escolaridade",
    "QT_ELEITORES_PERFIL": "eleitores",
}
OBRIGATORIAS = ["ANO_ELEICAO", "NR_ZONA", "NR_SECAO", "QT_ELEITORES_PERFIL"]

INT = "CASE WHEN btrim({c}) ~ '^\\d+$' THEN btrim({c})::INT END"

INSERIR = f"""
    INSERT INTO eleicao_perfil_secao (ano, nr_zona, nr_secao, genero, faixa_etaria, escolaridade, eleitores)
    SELECT ano_n, zona_n, secao_n,
           coalesce(NULLIF(btrim(genero), ''), 'NÃO INFORMADO'),
           coalesce(NULLIF(btrim(faixa_etaria), ''), 'NÃO INFORMADO'),
           coalesce(NULLIF(btrim(escolaridade), ''), 'NÃO INFORMADO'),
           sum(eleitores_n)
    FROM (
        SELECT t.*, {INT.format(c="ano")} AS ano_n, {INT.format(c="zona")} AS zona_n,
               {INT.format(c="secao")} AS secao_n, {INT.format(c="eleitores")} AS eleitores_n
        FROM pe t
        WHERE {tse_comum.FILTRO_MUNICIPIO}
    ) t
    WHERE ano_n IS NOT NULL AND zona_n IS NOT NULL AND secao_n IS NOT NULL AND eleitores_n IS NOT NULL
    GROUP BY 1, 2, 3, 4, 5, 6
"""


def carregar(conn, caminho) -> tuple[int | None, int]:
    leitura.copiar_para_temp(conn, caminho, "pe", COLUNAS, OBRIGATORIAS)
    ano = tse_comum.ano_do_nome(caminho.name)
    with conn.cursor() as cur:
        if ano:
            cur.execute("DELETE FROM eleicao_perfil_secao WHERE ano = %s", (ano,))
        else:
            cur.execute(
                f"DELETE FROM eleicao_perfil_secao WHERE ano IN (SELECT DISTINCT {INT.format(c='ano')} FROM pe)"
            )
        cur.execute(INSERIR, tse_comum.parametros_municipio())
        n = cur.rowcount
        cur.execute("DROP TABLE pe")
    return ano, n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", action="append", help="zip ou csv de um ano (repetível)")
    args = ap.parse_args(argv)
    with db.etapa("tse_eleitorado"), db.conectar() as conn:
        db.criar_schema(conn)
        total = 0
        for caminho in tse_comum.obter_arquivos(FONTE, args.arquivo):
            ano, n = carregar(conn, caminho)
            total += n
            db.registrar(conn, FONTE, str(caminho), caminho.name, baixar.sha256(caminho), n, ano=ano)
            log.info("%s: %d linhas de perfil", caminho.name, n)
        db.executar_sql(conn, "90_eleitoral.sql")
    log.info("%d linhas de perfil carregadas", total)


if __name__ == "__main__":
    main()
