"""Recorte dos estabelecimentos do município a partir de dados_rfb.cnpj_consolidado (ETL da MINDATA).

Uso:
    python -m etl.fontes.cnpj_recorte [--competencia AAAA-MM]

Lê do banco RFB (RFB_DSN ou RFB_DB_*; sem configuração, o mesmo banco do Pineal) e grava em empresa.
Traz todas as situações cadastrais: as baixadas e inaptas entram na dinâmica de fechamentos.

LGPD: quando o CNPJ é de pessoa física (MEI ou empresário individual, natureza 2135), a razão social
não é gravada; o CPF que a Receita põe nela fica só mascarado (***.456.789-**). Nome fantasia com
CPF dentro também não é gravado. Os dados passam por uma tabela temporária, nunca pela tabela final.

Cada rodada também grava uma foto do recorte em empresa_historico, na competência informada (padrão:
PINEAL_COMPETENCIA ou o mês corrente). Rodar de novo na mesma competência substitui a foto. Com uma foto
por mês, aberturas, fechamentos e mudanças de endereço saem da comparação entre competências.
"""

import argparse
import logging
import os
import tempfile
from datetime import date

from etl import config, db

log = logging.getLogger("cnpj_recorte")
FONTE = "rfb_cnpj"
NATUREZA_EMPRESARIO_INDIVIDUAL = "2135"

COLUNAS = [
    "cnpj",
    "cnpj_basico",
    "razao_social",
    "nome_fantasia",
    "situacao_cadastral",
    "data_situacao_cadastral",
    "data_inicio_atividade",
    "cnae_fiscal_principal",
    "natureza_juridica",
    "capital_social",
    "porte_empresa",
    "opcao_pelo_simples",
    "opcao_mei",
    "identificador_mf",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cep",
]

GRAVAR = f"""
    INSERT INTO empresa (cnpj, cnpj_basico, razao_social, nome_fantasia, pessoa_fisica, cpf_mascarado,
                         situacao_cadastral, data_situacao_cadastral, data_inicio_atividade, cnae_fiscal_principal,
                         natureza_juridica, capital_social, porte_empresa, opcao_pelo_simples, opcao_mei,
                         identificador_mf, logradouro, numero, complemento, bairro, cep)
    SELECT cnpj, coalesce(NULLIF(cnpj_basico, ''), left(cnpj, 8)),
           CASE WHEN pf THEN NULL ELSE razao_social END,
           CASE WHEN cpf_no_texto(nome_fantasia) IS NOT NULL THEN NULL ELSE NULLIF(btrim(nome_fantasia), '') END,
           pf,
           CASE WHEN pf THEN mascarar_cpf(coalesce(cpf_no_texto(razao_social), cpf_no_texto(nome_fantasia))) END,
           situacao_cadastral, data_rfb(data_situacao_cadastral), data_rfb(data_inicio_atividade),
           cnae_fiscal_principal, natureza_juridica, NULLIF(capital_social, '')::NUMERIC, porte_empresa,
           opcao_pelo_simples, opcao_mei, identificador_mf, logradouro, numero, complemento, bairro, cep
    FROM (
        SELECT c.*, (coalesce(opcao_mei, '') = 'S' OR natureza_juridica = '{NATUREZA_EMPRESARIO_INDIVIDUAL}') AS pf
        FROM empresa_carga c
    ) x
"""


def consulta(cur_rfb) -> str:
    filtro = "uf = %(uf)s AND (municipio = %(cod_rfb)s OR upper(nome_municipio) = %(nome)s)"
    return cur_rfb.mogrify(
        f"COPY (SELECT {', '.join(COLUNAS)} FROM dados_rfb.cnpj_consolidado WHERE {filtro}) TO STDOUT WITH (FORMAT csv)",
        {"uf": config.UF, "cod_rfb": config.COD_RFB, "nome": config.NOME_MUNICIPIO},
    ).decode()


def gravar(conn, arquivo_csv) -> tuple[int, int, int]:
    """Carrega o CSV exportado do banco RFB na tabela empresa. Devolve (total, ativas, pessoa_fisica)."""
    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE empresa_carga ({', '.join(c + ' TEXT' for c in COLUNAS)}) ON COMMIT DROP")
        cur.copy_expert(f"COPY empresa_carga ({', '.join(COLUNAS)}) FROM STDIN WITH (FORMAT csv)", arquivo_csv)
        cur.execute("TRUNCATE empresa CASCADE")
        cur.execute(GRAVAR)
        n = cur.rowcount
        cur.execute("TRUNCATE empresa_carga")
        cur.execute("ANALYZE empresa")
        cur.execute("""SELECT count(*) FILTER (WHERE situacao_cadastral = '02'), count(*) FILTER (WHERE pessoa_fisica)
                       FROM empresa""")
        ativas, pf = cur.fetchone()
    return n, ativas, pf


def competencia(texto: str | None) -> date:
    texto = texto or os.getenv("PINEAL_COMPETENCIA")
    if not texto:
        hoje = date.today()
        return date(hoje.year, hoje.month, 1)
    ano, mes = texto.split("-")[:2]
    return date(int(ano), int(mes), 1)


def foto_mensal(conn, comp: date) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM empresa_historico WHERE competencia = %s", (comp,))
        cur.execute(
            """
            INSERT INTO empresa_historico (competencia, cnpj, situacao_cadastral, data_situacao_cadastral,
                data_inicio_atividade, cnae_fiscal_principal, porte_empresa, capital_social, opcao_mei, endereco_chave)
            SELECT %s, cnpj, situacao_cadastral, data_situacao_cadastral, data_inicio_atividade, cnae_fiscal_principal,
                   porte_empresa, capital_social, opcao_mei,
                   concat_ws('|', norm_cep(cep), norm_logradouro(logradouro), norm_numero(numero))
            FROM empresa
            """,
            (comp,),
        )
        return cur.rowcount


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--competencia", help="AAAA-MM da foto mensal (padrão: PINEAL_COMPETENCIA ou mês corrente)")
    args = ap.parse_args(argv)
    comp = competencia(args.competencia)
    with db.etapa("cnpj"), tempfile.TemporaryFile("w+b") as tmp:
        with db.conectar(config.dsn_rfb(), schema=None) as rfb, rfb.cursor() as cur:
            log.info(
                "exportando recorte de dados_rfb.cnpj_consolidado (uf=%s, municipio=%s/%s)",
                config.UF,
                config.COD_RFB,
                config.NOME_MUNICIPIO,
            )
            cur.copy_expert(consulta(cur), tmp)
        tmp.seek(0)
        with db.conectar() as conn:
            db.criar_schema(conn)
            n, ativas, pf = gravar(conn, tmp)
            if n == 0:
                raise SystemExit("recorte vazio: confira PINEAL_COD_RFB/PINEAL_NOME_MUNICIPIO e o banco RFB")
            foto_mensal(conn, comp)
            db.registrar(
                conn,
                FONTE,
                "dados_rfb.cnpj_consolidado",
                linhas=n,
                ativas=ativas,
                pessoa_fisica=pf,
                uf=config.UF,
                cod_rfb=config.COD_RFB,
                competencia=comp,
            )
        log.info("%d estabelecimentos (%d ativos, %d de pessoa física) em empresa", n, ativas, pf)


if __name__ == "__main__":
    main()
