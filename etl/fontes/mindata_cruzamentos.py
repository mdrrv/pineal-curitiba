"""Sinais por CNPJ a partir das bases que o ETL da MINDATA já carrega no banco RFB.

Uso:
    python -m etl.fontes.mindata_cruzamentos

Lê, só para os CNPJs de empresa:
    dados_rfb.pncp_contratos      contratos públicos de todas as esferas (PNCP)
    dados_rfb.tce_pr_contratos    contratos municipais do Paraná (TCE-PR)
    dados_rfb.pgfn_divida_ativa   dívida ativa da União (PGFN)
    dados_rfb.sancoes_federais    CEIS, CNEP e afins
Tabela ausente no banco RFB é pulada com aviso; as colunas dela ficam nulas.
Grava empresa_sinais (uma linha por CNPJ com pelo menos um sinal).
"""

import argparse
import io
import logging

from psycopg2.extras import execute_values

from etl import config, db

log = logging.getLogger("mindata_cruzamentos")
FONTE = "mindata_cruzamentos"

FONTES = {
    "pncp": (
        "dados_rfb.pncp_contratos",
        """SELECT cnpj_14, count(*), sum(valor_global), max(ano_contrato)
           FROM dados_rfb.pncp_contratos JOIN alvo ON alvo.cnpj = cnpj_14 GROUP BY 1""",
        ["pncp_contratos", "pncp_valor", "pncp_ultimo_ano"],
    ),
    "tce_pr": (
        "dados_rfb.tce_pr_contratos",
        """SELECT cnpj_14, count(*), sum(vl_contrato), count(*) FILTER (WHERE dt_fim >= current_date)
           FROM dados_rfb.tce_pr_contratos JOIN alvo ON alvo.cnpj = cnpj_14 GROUP BY 1""",
        ["tce_pr_contratos", "tce_pr_valor", "tce_pr_vigentes"],
    ),
    "pgfn": (
        "dados_rfb.pgfn_divida_ativa",
        """SELECT cnpj_14, count(*), sum(valor_consolidado)
           FROM dados_rfb.pgfn_divida_ativa JOIN alvo ON alvo.cnpj = cnpj_14 GROUP BY 1""",
        ["pgfn_inscricoes", "pgfn_valor"],
    ),
    "sancoes": (
        "dados_rfb.sancoes_federais",
        """SELECT cnpj_14, count(*) FILTER (WHERE coalesce(ativo, true))
           FROM dados_rfb.sancoes_federais JOIN alvo ON alvo.cnpj = cnpj_14 GROUP BY 1""",
        ["sancoes_ativas"],
    ),
}
COLUNAS = [c for _, _, cols in FONTES.values() for c in cols]

DDL = f"""
    CREATE TABLE IF NOT EXISTS empresa_sinais (
        cnpj VARCHAR(14) PRIMARY KEY,
        pncp_contratos INT, pncp_valor NUMERIC(18,2), pncp_ultimo_ano SMALLINT,
        tce_pr_contratos INT, tce_pr_valor NUMERIC(18,2), tce_pr_vigentes INT,
        pgfn_inscricoes INT, pgfn_valor NUMERIC(18,2),
        sancoes_ativas INT
    );
    COMMENT ON TABLE empresa_sinais IS 'colunas: {", ".join(COLUNAS)}'
"""


def ler_sinais(cnpjs: list[str]) -> tuple[dict[str, dict], dict[str, int]]:
    sinais: dict[str, dict] = {}
    cobertura: dict[str, int] = {}
    with db.conectar(config.dsn_rfb(), schema=None) as rfb, rfb.cursor() as cur:
        cur.execute("CREATE TEMP TABLE alvo (cnpj VARCHAR(14) PRIMARY KEY) ON COMMIT DROP")
        cur.copy_expert("COPY alvo FROM STDIN", io.StringIO("".join(f"{c}\n" for c in cnpjs)))
        for nome, (tabela, sql, cols) in FONTES.items():
            cur.execute("SELECT to_regclass(%s)", (tabela,))
            if cur.fetchone()[0] is None:
                log.warning("%s não existe no banco RFB: %s pulado", tabela, nome)
                continue
            cur.execute(sql)
            linhas = cur.fetchall()
            cobertura[nome] = len(linhas)
            for cnpj, *valores in linhas:
                sinais.setdefault(cnpj, {}).update(dict(zip(cols, valores, strict=True)))
    return sinais, cobertura


def gravar(conn, sinais: dict[str, dict]) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("TRUNCATE empresa_sinais")
        execute_values(
            cur,
            f"INSERT INTO empresa_sinais (cnpj, {', '.join(COLUNAS)}) VALUES %s",
            [(cnpj, *(s.get(c) for c in COLUNAS)) for cnpj, s in sinais.items()],
        )


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with db.etapa("cruzamentos"):
        with db.conectar() as conn, conn.cursor() as cur:
            cur.execute("SELECT cnpj FROM empresa")
            cnpjs = [r[0] for r in cur.fetchall()]
        if not cnpjs:
            raise SystemExit("empresa vazio: rode antes python -m etl.fontes.cnpj_recorte")
        sinais, cobertura = ler_sinais(cnpjs)
        with db.conectar() as conn:
            db.criar_schema(conn)
            gravar(conn, sinais)
            db.registrar(conn, FONTE, "banco RFB", linhas=len(sinais), por_fonte=cobertura)
        log.info("%d CNPJs com algum sinal; por fonte: %s", len(sinais), cobertura)


if __name__ == "__main__":
    main()
