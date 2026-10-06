"""Tabelas de apoio: hierarquia de CNAE (seção, divisão, grupo, classe, subclasse) e natureza jurídica.

Uso:
    python -m etl.fontes.apoio

CNAE vem da API do IBGE (url no catalogo.yaml). Se a API não responder, usa dados_rfb.cnae do banco RFB:
nesse caso só a subclasse tem descrição, e os níveis acima saem só com o código.
Natureza jurídica vem de dados_rfb.natju. Porte e situação cadastral são fixas (sql/02_apoio.sql).
"""

import argparse
import logging

import requests
from psycopg2.extras import execute_values

from etl import baixar, config, db

log = logging.getLogger("apoio")
FONTE = "apoio"


def cnae_do_ibge(url: str) -> list[tuple]:
    r = requests.get(url, headers=baixar.UA, timeout=120)
    r.raise_for_status()
    linhas = []
    for s in r.json():
        classe = s.get("classe") or {}
        grupo = classe.get("grupo") or {}
        divisao = grupo.get("divisao") or {}
        secao = divisao.get("secao") or {}
        linhas.append(
            (
                str(s["id"]).replace("-", "").replace("/", "").replace(".", ""),
                s.get("descricao"),
                str(classe.get("id", "")).replace("-", "").replace(".", "") or None,
                classe.get("descricao"),
                str(grupo.get("id", "")).replace(".", "") or None,
                grupo.get("descricao"),
                divisao.get("id"),
                divisao.get("descricao"),
                secao.get("id"),
                secao.get("descricao"),
            )
        )
    return linhas


def tabela_rfb(sql: str) -> list[tuple]:
    try:
        with db.conectar(config.dsn_rfb(), schema=None) as rfb, rfb.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    except Exception as e:  # tabela ausente no banco RFB não impede o resto
        log.warning("não li do banco RFB (%s): %s", sql.split("FROM")[-1].strip(), e)
        return []


def cnae_da_rfb() -> list[tuple]:
    return [
        (cod, desc, cod[:5], None, cod[:3], None, cod[:2], None, None, None)
        for cod, desc in tabela_rfb("SELECT codigo, descricao FROM dados_rfb.cnae")
        if cod and len(cod) == 7
    ]


def gravar(conn, cnae: list[tuple], natureza: list[tuple]) -> None:
    with conn.cursor() as cur:
        if cnae:
            cur.execute("TRUNCATE cnae")
            execute_values(cur, "INSERT INTO cnae VALUES %s ON CONFLICT (subclasse) DO NOTHING", cnae)
        if natureza:
            cur.execute("TRUNCATE natureza_juridica")
            execute_values(cur, "INSERT INTO natureza_juridica VALUES %s ON CONFLICT (codigo) DO NOTHING", natureza)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with db.etapa("apoio"):
        url = config.fonte("ibge_cnae")["url"]
        try:
            cnae, origem = cnae_do_ibge(url), url
        except (requests.RequestException, ValueError) as e:
            log.warning("API de CNAE do IBGE indisponível (%s); usando dados_rfb.cnae", e)
            cnae, origem = cnae_da_rfb(), "dados_rfb.cnae"
        natureza = tabela_rfb("SELECT codigo, descricao FROM dados_rfb.natju")
        with db.conectar() as conn:
            db.criar_schema(conn)
            gravar(conn, cnae, natureza)
            db.registrar(conn, FONTE, origem, linhas=len(cnae), naturezas=len(natureza))
        log.info("%d subclasses CNAE (%s), %d naturezas jurídicas", len(cnae), origem, len(natureza))


if __name__ == "__main__":
    main()
