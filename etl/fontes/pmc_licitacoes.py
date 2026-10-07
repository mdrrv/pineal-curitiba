"""Licitações e Contratações da prefeitura (e a base separada da COVID-19).

Uso:
    python -m etl.fontes.pmc_licitacoes [--arquivo base.csv] [--arquivo-covid covid.csv]

Itens de processo com órgão, modalidade, fornecedor, CNPJ/CPF, contrato, vigência e valores. Só o CNPJ é
gravado: fornecedor pessoa física (CPF) fica com cnpj nulo e sem nome. Grava contrato_pmc_item e o resumo
por CNPJ em empresa_contratos_pmc (contratos, valor, contratos vigentes, fim do último contrato).
"""

import argparse
import logging

import requests

from etl import config, db, leitura, portal

log = logging.getLogger("pmc_licitacoes")
BASES = {
    "pmc_licitacoes": r"Licitacoes_Contratacoes_Itens.*Base_de_Dados",
    "pmc_licitacoes_covid": r"Covid.*Base_de_Dados",
}
COLUNAS = {
    "Órgão": "orgao",
    "Número do Processo": "processo",
    "Modalidade": "modalidade",
    "Item": "item",
    "Quantidade": "quantidade",
    "Unidade de Medida": "unidade",
    "CNPJ/CPF": "doc",
    "Número do Contrato": "contrato",
    "Inicio da Vigência do Contrato": "inicio",
    "Fim da Vigência do Contrato": "fim",
    "Valor Unitário": "vu",
    "Valor Total/Global": "vt",
}

RESUMO = """
    DROP TABLE IF EXISTS empresa_contratos_pmc;
    CREATE TABLE empresa_contratos_pmc AS
    SELECT cnpj,
           count(DISTINCT coalesce(contrato, processo)) AS contratos,
           count(*) AS itens,
           sum(valor_total) AS valor_total,
           count(DISTINCT coalesce(contrato, processo)) FILTER (WHERE fim_vigencia >= current_date) AS contratos_vigentes,
           max(fim_vigencia) AS fim_ultimo_contrato,
           EXISTS (SELECT 1 FROM empresa e WHERE e.cnpj = c.cnpj) AS na_cidade
    FROM contrato_pmc_item c
    WHERE cnpj IS NOT NULL
    GROUP BY cnpj;
    ALTER TABLE empresa_contratos_pmc ADD PRIMARY KEY (cnpj);
"""


def carregar(conn, base: str, caminho) -> int:
    leitura.copiar_para_temp(conn, caminho, "lic_carga", COLUNAS, obrigatorias=["CNPJ/CPF", "Valor Total/Global"])
    with conn.cursor() as cur:
        cur.execute("DELETE FROM contrato_pmc_item WHERE base = %s", (base,))
        cur.execute(
            """
            INSERT INTO contrato_pmc_item (base, orgao, processo, modalidade, item, quantidade, unidade_medida, cnpj,
                                           pessoa_fisica, contrato, inicio_vigencia, fim_vigencia, valor_unitario, valor_total)
            SELECT %s, NULLIF(btrim(orgao), ''), NULLIF(btrim(processo), ''), NULLIF(btrim(modalidade), ''),
                   NULLIF(btrim(item), ''), valor_br(quantidade), NULLIF(btrim(unidade), ''),
                   CASE WHEN length(d) = 14 THEN d END, length(d) = 11, NULLIF(btrim(contrato), ''),
                   data_br(inicio), data_br(fim), valor_br(vu), valor_br(vt)
            FROM (SELECT *, regexp_replace(coalesce(doc, ''), '[^0-9]', '', 'g') AS d FROM lic_carga) x
        """,
            (base,),
        )
        n = cur.rowcount
        cur.execute("DROP TABLE lic_carga")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo")
    ap.add_argument("--arquivo-covid")
    args = ap.parse_args(argv)
    with db.etapa("licitacoes"), db.conectar() as conn:
        db.criar_schema(conn)
        totais = {}
        for base, padrao in BASES.items():
            arquivo = args.arquivo if base == "pmc_licitacoes" else args.arquivo_covid
            try:
                caminho, origem = portal.obter(base, padrao, arquivo)
            except (requests.RequestException, FileNotFoundError) as e:
                if base == "pmc_licitacoes":
                    raise
                log.warning("%s indisponível (%s): pulada", base, e)
                continue
            totais[base] = carregar(conn, base, caminho)
            db.registrar(conn, base, origem, caminho.name, linhas=totais[base])
        with conn.cursor() as cur:
            cur.execute(RESUMO)
            cur.execute("""SELECT count(*), count(*) FILTER (WHERE na_cidade), count(*) FILTER (WHERE contratos_vigentes > 0),
                                  sum(valor_total) FROM empresa_contratos_pmc""")
            fornecedores, na_cidade, vigentes, valor = cur.fetchone()
    md = "\n".join(
        [
            "# Licitações e contratações da prefeitura",
            "",
            *[f"- {b}: {n} itens" for b, n in totais.items()],
            f"- Fornecedores com CNPJ: {fornecedores} ({na_cidade} com estabelecimento em Curitiba)",
            f"- Com contrato vigente: {vigentes}",
            f"- Valor total dos itens: R$ {valor or 0:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        ]
    )
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "licitacoes.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
