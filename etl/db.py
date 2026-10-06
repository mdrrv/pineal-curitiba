import json
import logging
from contextlib import contextmanager
from pathlib import Path

import psycopg2

from etl import config

log = logging.getLogger(__name__)


@contextmanager
def conectar(dsn: str | None = None):
    conn = psycopg2.connect(dsn or config.dsn_pineal())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def executar_sql(conn, arquivo: str | Path) -> None:
    caminho = Path(arquivo)
    if not caminho.is_absolute():
        caminho = config.SQL / caminho
    log.info("sql %s", caminho.name)
    with conn.cursor() as cur:
        cur.execute(caminho.read_text(encoding="utf-8"))


def criar_schema(conn) -> None:
    executar_sql(conn, "00_schema.sql")
    executar_sql(conn, "01_normalizacao.sql")


def registrar(conn, fonte: str, origem: str | None = None, arquivo: str | None = None,
              sha256: str | None = None, linhas: int | None = None, **detalhes) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO cwb.execucao (fonte, origem, arquivo, sha256, linhas, detalhes) VALUES (%s,%s,%s,%s,%s,%s)",
            (fonte, origem, arquivo, sha256, linhas, json.dumps(detalhes, ensure_ascii=False, default=str) if detalhes else None),
        )


def contar(conn, sql: str, params=None) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]
