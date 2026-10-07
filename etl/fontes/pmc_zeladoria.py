"""156 e SIGMU: pedidos do cidadão e de manutenção urbana agregados por bairro e mês.

Uso:
    python -m etl.fontes.pmc_zeladoria [--arquivo-156 base.csv] [--arquivo-sigmu-solicitado x.csv --arquivo-sigmu-servico y.csv]

156: tipo, assunto, situação, bairro, regional, datas de criação e resposta. SIGMU: SERVICO_SOLICITADO
(pedido, bairro, datas de solicitação e realização) com SERVICO_TAB (descrição do serviço). Nada de texto
livre nem dado do solicitante é carregado. Bairro casado pelo nome com o bairro do IPPUC quando houver.
Grava siac156_bairro_mes e sigmu_bairro_mes.
"""

import argparse
import logging

import requests

from etl import config, db, leitura, portal

log = logging.getLogger("pmc_zeladoria")

C156 = {
    "Tipo": "tipo",
    "DataCriacao": "criacao",
    "Assunto": "assunto",
    "Situacao": "situacao",
    "Bairro": "bairro",
    "Regional": "regional",
    "DataResposta": "resposta",
}
SOLICITADO = {
    "SSO_IDF": "id",
    "SSO_DATA_SOLICITACAO": "solicitacao",
    "SET_IDF": "servico_id",
    "SSO_NOME_BAIRRO": "bairro",
    "SSO_DATA_REALIZACAO": "realizacao",
}
SERVICO = {"SET_IDF": "servico_id", "SET_DESCRICAO": "descricao"}

BAIRRO = """coalesce((SELECT b.nome FROM bairro b WHERE norm_txt(b.nome) = norm_txt({c}) LIMIT 1),
                     NULLIF(upper(btrim({c})), ''))"""


def carregar_156(conn, caminho) -> int:
    leitura.copiar_para_temp(conn, caminho, "c156", C156, obrigatorias=["Bairro", "DataCriacao"])
    with conn.cursor() as cur:
        cur.execute("TRUNCATE siac156_bairro_mes")
        cur.execute(f"""
            INSERT INTO siac156_bairro_mes
            SELECT {BAIRRO.format(c="bairro")}, NULLIF(upper(btrim(regional)), ''), date_trunc('month', data_br(criacao))::DATE,
                   NULLIF(btrim(tipo), ''), NULLIF(btrim(assunto), ''), count(*), count(data_br(resposta)),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY data_br(resposta) - data_br(criacao))
            FROM c156 WHERE data_br(criacao) IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5
        """)
        cur.execute("SELECT coalesce(sum(solicitacoes), 0) FROM siac156_bairro_mes")
        return cur.fetchone()[0]


def carregar_sigmu(conn, solicitado, servico) -> int:
    leitura.copiar_para_temp(conn, solicitado, "sso", SOLICITADO, obrigatorias=["SSO_DATA_SOLICITACAO", "SET_IDF"])
    leitura.copiar_para_temp(conn, servico, "sset", SERVICO, obrigatorias=["SET_IDF", "SET_DESCRICAO"])
    with conn.cursor() as cur:
        cur.execute("TRUNCATE sigmu_bairro_mes")
        cur.execute(f"""
            INSERT INTO sigmu_bairro_mes
            SELECT {BAIRRO.format(c="s.bairro")}, date_trunc('month', data_br(s.solicitacao))::DATE,
                   coalesce(NULLIF(btrim(t.descricao), ''), 'serviço ' || s.servico_id),
                   count(*), count(data_br(s.realizacao)),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY data_br(s.realizacao) - data_br(s.solicitacao))
            FROM sso s LEFT JOIN (SELECT DISTINCT ON (servico_id) * FROM sset) t USING (servico_id)
            WHERE data_br(s.solicitacao) IS NOT NULL
            GROUP BY 1, 2, 3
        """)
        cur.execute("SELECT coalesce(sum(solicitacoes), 0) FROM sigmu_bairro_mes")
        return cur.fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo-156")
    ap.add_argument("--arquivo-sigmu-solicitado")
    ap.add_argument("--arquivo-sigmu-servico")
    args = ap.parse_args(argv)
    md = ["# Zeladoria: 156 e SIGMU", ""]
    with db.etapa("zeladoria"), db.conectar() as conn:
        db.criar_schema(conn)
        caminho, origem = portal.obter("pmc_siac156", r"156_-_Base_de_Dados", args.arquivo_156)
        n = carregar_156(conn, caminho)
        db.registrar(conn, "pmc_siac156", origem, caminho.name, linhas=n)
        md.append(f"- 156: {n} solicitações em siac156_bairro_mes")
        try:
            sol, _ = portal.obter(
                "pmc_sigmu", r"Sigmu_-_SERVICO_SOLICITADO_-_Base_de_Dados", args.arquivo_sigmu_solicitado
            )
            ser, _ = portal.obter("pmc_sigmu", r"Sigmu_-_SERVICO_TAB_-_Base_de_Dados", args.arquivo_sigmu_servico)
            n = carregar_sigmu(conn, sol, ser)
            db.registrar(conn, "pmc_sigmu", sol.name, linhas=n)
            md.append(f"- SIGMU: {n} solicitações em sigmu_bairro_mes")
        except (requests.RequestException, FileNotFoundError) as e:
            log.warning("SIGMU indisponível (%s): pulada", e)
            md.append(f"- SIGMU: indisponível ({e})")
        with conn.cursor() as cur:
            cur.execute("""SELECT bairro, sum(solicitacoes) FROM siac156_bairro_mes
                           WHERE mes >= date_trunc('month', current_date) - INTERVAL '12 months'
                           GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10""")
            top = cur.fetchall()
    md += ["", "## Bairros com mais pedidos ao 156 nos últimos 12 meses", "", "| bairro | solicitações |", "|---|---:|"]
    md += [f"| {b} | {n} |" for b, n in top]
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "zeladoria.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
