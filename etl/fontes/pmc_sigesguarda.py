"""SiGesGuarda (ocorrências da Guarda Municipal) e índice de risco por bairro.

Uso:
    python -m etl.fontes.pmc_sigesguarda [--arquivo base.csv]

O arquivo mais recente do portal traz de 2023 até a extração. Carrega o fato (código, data, hora, bairro,
regional, logradouro, naturezas 1 a 5, marca de defesa civil, equipamento urbano, flagrante); nada de
pessoa. Cada natureza vira uma categoria pela tabela natureza_categoria (editável).

Localização: a base tem rua e bairro, sem número. O ponto é o endereço do CNEFE mais perto do centro da rua
dentro do bairro (logradouro_no_bairro); sem rua no bairro, o ponto do bairro (bairro).

Grava seguranca_ocorrencia (fonte pmc_sigesguarda) e, de todas as fontes, seguranca_bairro_mes, seguranca_h3,
risco_bairro e risco_bairro_indice (sql/60_seguranca.sql). Relatório em relatorios/seguranca.md.
"""

import argparse
import logging

import h3

from etl import config, db, leitura, portal

log = logging.getLogger("pmc_sigesguarda")
FONTE = "pmc_sigesguarda"

COLUNAS = {
    "OCORRENCIA_CODIGO": "cod_origem",
    "OCORRENCIA_DATA": "data",
    "OCORRENCIA_HORA": "hora",
    "ATENDIMENTO_BAIRRO_NOME": "bairro",
    "REGIONAL_FATO_NOME": "regional",
    "LOGRADOURO_NOME": "logradouro",
    "EQUIPAMENTO_URBANO_NOME": "equipamento",
    "FLAG_FLAGRANTE": "flagrante",
    **{f"NATUREZA{i}_DESCRICAO": f"n{i}" for i in range(1, 6)},
    **{f"NATUREZA{i}_DEFESA_CIVIL": f"d{i}" for i in range(1, 6)},
}
OBRIGATORIAS = ["OCORRENCIA_DATA", "ATENDIMENTO_BAIRRO_NOME", "NATUREZA1_DESCRICAO"]

SIM = "upper(btrim({c})) IN ('S', 'SIM', '1', 'T', 'TRUE', 'Y')"
HORA = """CASE WHEN {c} ~ '\\d{{1,2}}:\\d{{2}}' THEN substring({c} from '(\\d{{1,2}}):\\d{{2}}')::INT
               WHEN btrim({c}) ~ '^\\d{{1,2}}$' THEN btrim({c})::INT END"""

INSERIR = f"""
    WITH linha AS (
        SELECT coalesce(NULLIF(btrim(cod_origem), ''), md5(s::TEXT)) AS codigo, s.*
        FROM sg s
    ), nat AS (
        SELECT l.codigo, array_agg(DISTINCT btrim(v.n) ORDER BY btrim(v.n)) AS naturezas,
               bool_or({SIM.format(c="v.d")}) AS defesa_civil
        FROM linha l
        CROSS JOIN LATERAL (VALUES (n1, d1), (n2, d2), (n3, d3), (n4, d4), (n5, d5)) v(n, d)
        WHERE NULLIF(btrim(v.n), '') IS NOT NULL
        GROUP BY 1
    ), fato AS (
        SELECT DISTINCT ON (codigo) * FROM linha ORDER BY codigo, data_br(data)
    )
    INSERT INTO seguranca_ocorrencia (fonte, codigo, data, hora, bairro, regional, logradouro, naturezas,
                                      categorias, defesa_civil, equipamento_urbano, flagrante)
    SELECT %s, f.codigo, data_br(f.data), x.hora,
           coalesce((SELECT b.nome FROM bairro b WHERE norm_txt(b.nome) = norm_txt(f.bairro) LIMIT 1),
                    NULLIF(upper(btrim(f.bairro)), '')),
           NULLIF(upper(btrim(f.regional)), ''), NULLIF(btrim(f.logradouro), ''), n.naturezas,
           ARRAY(SELECT DISTINCT c FROM (
                     SELECT categoria_natureza(u) AS c FROM unnest(n.naturezas) u
                     UNION ALL SELECT 'fisico' WHERE n.defesa_civil) t
                 WHERE c IS NOT NULL ORDER BY c),
           coalesce(n.defesa_civil, false), NULLIF(btrim(f.equipamento), ''), {SIM.format(c="f.flagrante")}
    FROM fato f
    LEFT JOIN nat n USING (codigo)
    CROSS JOIN LATERAL (SELECT {HORA.format(c="f.hora")} AS h) h0
    CROSS JOIN LATERAL (SELECT CASE WHEN h0.h BETWEEN 0 AND 23 THEN h0.h END AS hora) x
"""

LOCALIZAR = """
    CREATE TEMP TABLE _par ON COMMIT DROP AS
    SELECT DISTINCT coalesce(norm_logradouro_completa(logradouro), '') AS lc, coalesce(norm_txt(bairro), '') AS bc,
           NULL::TEXT AS nivel, NULL::geometry(Point, 4326) AS geom, NULL::TEXT AS h3_9
    FROM seguranca_ocorrencia WHERE fonte = %(fonte)s;

    CREATE TEMP TABLE _bp ON COMMIT DROP AS
    SELECT DISTINCT ON (norm_txt(nome)) norm_txt(nome) AS bc, geom FROM bairro ORDER BY norm_txt(nome), ST_Area(geom) DESC;

    UPDATE _par p SET geom = x.geom, nivel = 'logradouro_no_bairro'
    FROM (
        SELECT p2.lc, p2.bc, (
            SELECT c.geom FROM cnefe c
            WHERE c.logr_completa = p2.lc AND ST_Intersects(b.geom, c.geom)
            ORDER BY c.geom <-> (SELECT ST_Centroid(ST_Collect(c2.geom)) FROM cnefe c2
                                 WHERE c2.logr_completa = p2.lc AND ST_Intersects(b.geom, c2.geom))
            LIMIT 1) AS geom
        FROM _par p2 JOIN _bp b ON b.bc = p2.bc
        WHERE p2.lc <> ''
    ) x
    WHERE x.lc = p.lc AND x.bc = p.bc AND x.geom IS NOT NULL;

    UPDATE _par p SET geom = ST_PointOnSurface(b.geom), nivel = 'bairro'
    FROM _bp b WHERE p.nivel IS NULL AND b.bc = p.bc;

    UPDATE _par SET nivel = 'nao_localizado' WHERE nivel IS NULL;
"""


def carregar(conn, caminho) -> int:
    leitura.copiar_para_temp(conn, caminho, "sg", COLUNAS, OBRIGATORIAS)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM seguranca_ocorrencia WHERE fonte = %s", (FONTE,))
        cur.execute(INSERIR, (FONTE,))
        n = cur.rowcount
        cur.execute("DROP TABLE sg")
    return n


def localizar(conn, fonte: str) -> None:
    with conn.cursor() as cur:
        cur.execute(LOCALIZAR, {"fonte": fonte})
        cur.execute("SELECT lc, bc, ST_Y(geom), ST_X(geom) FROM _par WHERE geom IS NOT NULL")
        h3s = [(h3.latlng_to_cell(lat, lon, 9), lc, bc) for lc, bc, lat, lon in cur.fetchall()]
        cur.executemany("UPDATE _par SET h3_9 = %s WHERE lc = %s AND bc = %s", h3s)
        cur.execute(
            """
            UPDATE seguranca_ocorrencia o SET geo_precisao = p.nivel, geom = p.geom, h3_9 = p.h3_9
            FROM _par p
            WHERE o.fonte = %s AND p.lc = coalesce(norm_logradouro_completa(o.logradouro), '')
              AND p.bc = coalesce(norm_txt(o.bairro), '')
            """,
            (fonte,),
        )
        cur.execute("DROP TABLE _par, _bp")


def resumo(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("""SELECT min(data), max(data), count(*) FROM seguranca_ocorrencia WHERE fonte = %s""", (FONTE,))
        ini, fim, total = cur.fetchone()
        cur.execute(
            "SELECT geo_precisao, count(*) FROM seguranca_ocorrencia WHERE fonte = %s GROUP BY 1 ORDER BY 2 DESC",
            (FONTE,),
        )
        niveis = cur.fetchall()
        cur.execute(
            """
            SELECT c, count(*) FROM seguranca_ocorrencia, unnest(categorias) c
            WHERE fonte = %s GROUP BY 1 ORDER BY 2 DESC
        """,
            (FONTE,),
        )
        cats = cur.fetchall()
        cur.execute(
            """
            SELECT n, count(*) FROM seguranca_ocorrencia, unnest(naturezas) n
            WHERE fonte = %s AND categoria_natureza(n) = 'outros' GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 15
        """,
            (FONTE,),
        )
        outros = cur.fetchall()
        cur.execute("""
            SELECT bairro, patrimonial, violento, fisico, indice FROM risco_bairro_indice
            WHERE indice IS NOT NULL ORDER BY indice DESC, bairro LIMIT 15
        """)
        top = cur.fetchall()
        cur.execute("SELECT min(janela_inicio), max(janela_fim) FROM risco_bairro")
        j_ini, j_fim = cur.fetchone()
    md = [
        "# Segurança: SiGesGuarda e índice de risco por bairro",
        "",
        f"- Ocorrências: {total} ({ini} a {fim})",
        f"- Janela do índice: {j_ini} a {j_fim}",
        "",
        "| localização | ocorrências |",
        "|---|---:|",
        *[f"| {n} | {q} |" for n, q in niveis],
        "",
        "| categoria | ocorrências |",
        "|---|---:|",
        *[f"| {c} | {q} |" for c, q in cats],
        "",
        "## Naturezas sem categoria (ajustar natureza_categoria)",
        "",
        "| natureza | ocorrências |",
        "|---|---:|",
        *[f"| {n} | {q} |" for n, q in outros],
        "",
        "## Bairros com maior índice (percentis 0 a 100)",
        "",
        "| bairro | patrimonial | violento | físico | índice |",
        "|---|---:|---:|---:|---:|",
        *[f"| {b} | {p} | {v} | {f} | {i} |" for b, p, v, f, i in top],
    ]
    return "\n".join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo")
    args = ap.parse_args(argv)
    with db.etapa("seguranca"), db.conectar() as conn:
        db.criar_schema(conn)
        caminho, origem = portal.obter(FONTE, r"sigesguarda_-_Base_de_Dados", args.arquivo)
        n = carregar(conn, caminho)
        log.info("%d ocorrências carregadas; localizando", n)
        localizar(conn, FONTE)
        db.executar_sql(conn, "60_seguranca.sql")
        db.registrar(conn, FONTE, origem, caminho.name, linhas=n)
        md = resumo(conn)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "seguranca.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
