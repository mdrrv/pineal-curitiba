"""Recorte dos estabelecimentos do município a partir de dados_rfb.cnpj_consolidado (ETL da MINDATA).

Uso:
    python -m etl.fontes.cnpj_recorte

Lê do banco RFB (RFB_DSN ou RFB_DB_*; sem configuração, o mesmo banco do Pineal) e grava em cwb.empresa.
Traz todas as situações cadastrais: as baixadas e inaptas entram na dinâmica de fechamentos.
"""
import argparse
import logging
import tempfile

from etl import config, db

log = logging.getLogger("cnpj_recorte")
FONTE = "rfb_cnpj"

COLUNAS = [
    "cnpj", "razao_social", "nome_fantasia", "situacao_cadastral", "data_situacao_cadastral",
    "data_inicio_atividade", "cnae_fiscal_principal", "natureza_juridica", "capital_social", "porte_empresa",
    "opcao_pelo_simples", "opcao_mei", "identificador_mf", "logradouro", "numero", "complemento", "bairro", "cep",
]


def consulta(cur_rfb) -> str:
    filtro = "uf = %(uf)s AND (municipio = %(cod_rfb)s OR upper(nome_municipio) = %(nome)s)"
    return cur_rfb.mogrify(
        f"COPY (SELECT {', '.join(COLUNAS)} FROM dados_rfb.cnpj_consolidado WHERE {filtro}) TO STDOUT WITH (FORMAT csv)",
        {"uf": config.UF, "cod_rfb": config.COD_RFB, "nome": config.NOME_MUNICIPIO},
    ).decode()


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with tempfile.TemporaryFile("w+b") as tmp:
        with db.conectar(config.dsn_rfb()) as rfb, rfb.cursor() as cur:
            log.info("exportando recorte de dados_rfb.cnpj_consolidado (uf=%s, municipio=%s/%s)",
                     config.UF, config.COD_RFB, config.NOME_MUNICIPIO)
            cur.copy_expert(consulta(cur), tmp)
        tmp.seek(0)
        with db.conectar() as conn:
            db.criar_schema(conn)
            with conn.cursor() as cur:
                cur.execute("TRUNCATE cwb.empresa CASCADE")
                cur.copy_expert(f"COPY cwb.empresa ({', '.join(COLUNAS)}) FROM STDIN WITH (FORMAT csv)", tmp)
                n = cur.rowcount
                cur.execute("ANALYZE cwb.empresa")
                cur.execute("SELECT count(*) FILTER (WHERE situacao_cadastral = '02') FROM cwb.empresa")
                ativas = cur.fetchone()[0]
            db.registrar(conn, FONTE, "dados_rfb.cnpj_consolidado", linhas=n, ativas=ativas,
                         uf=config.UF, cod_rfb=config.COD_RFB)
    log.info("%d estabelecimentos (%d ativos) em cwb.empresa", n, ativas)
    if n == 0:
        raise SystemExit("recorte vazio: confira PINEAL_COD_RFB/PINEAL_NOME_MUNICIPIO e o banco RFB")


if __name__ == "__main__":
    main()
