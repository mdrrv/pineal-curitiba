import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg2

from etl import config

log = logging.getLogger(__name__)


PADRAO = "__schema_do_pineal__"


@contextmanager
def conectar(dsn: str | None = None, schema: str | None = PADRAO):
    """Conexão com o schema do Pineal na frente do search_path.
    schema=None deixa o search_path padrão (use para o banco RFB, que não deve ganhar o schema do Pineal)."""
    conn = psycopg2.connect(dsn or config.dsn_pineal())
    if schema == PADRAO:
        schema = config.SCHEMA
    try:
        if schema:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
                cur.execute(f"SET search_path TO {schema}, public")
            conn.commit()  # SET dentro de transação desfeita voltaria atrás
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
    executar_sql(conn, "02_apoio.sql")
    executar_sql(conn, "05_m1_schema.sql")
    executar_sql(conn, "06_censo_schema.sql")


def _inserir(conn, **campos) -> None:
    if campos.get("detalhes") is not None:
        campos["detalhes"] = json.dumps(campos["detalhes"], ensure_ascii=False, default=str)
    cols = ", ".join(campos)
    with conn.cursor() as cur:
        cur.execute(f"INSERT INTO execucao ({cols}) VALUES ({', '.join(['%s'] * len(campos))})", list(campos.values()))


def registrar(
    conn,
    fonte: str,
    origem: str | None = None,
    arquivo: str | None = None,
    sha256: str | None = None,
    linhas: int | None = None,
    **detalhes,
) -> None:
    """Registra uma carga bem-sucedida (vai junto com a transação dos dados)."""
    _inserir(
        conn,
        run_id=config.RUN_ID,
        tipo="carga",
        fonte=fonte,
        origem=origem,
        arquivo=arquivo,
        sha256=sha256,
        linhas=linhas,
        detalhes=detalhes or None,
    )


@contextmanager
def etapa(nome: str):
    """Registra início, fim, duração e status (ok ou erro) de uma etapa, numa conexão própria:
    o registro de erro sobrevive ao rollback da etapa."""
    inicio = time.monotonic()
    try:
        yield
    except BaseException as e:
        _registrar_etapa(nome, "erro", time.monotonic() - inicio, f"{type(e).__name__}: {e}"[:4000])
        raise
    _registrar_etapa(nome, "ok", time.monotonic() - inicio, None)


def _registrar_etapa(nome: str, status: str, duracao: float, erro: str | None) -> None:
    try:
        with conectar() as conn:
            criar_schema(conn)
            _inserir(
                conn,
                run_id=config.RUN_ID,
                tipo="etapa",
                fonte=nome,
                status=status,
                duracao_s=round(duracao, 1),
                erro=erro,
            )
    except psycopg2.Error as e:
        log.error("não consegui registrar a etapa %s em execucao: %s", nome, e)
    log.info("etapa %s: %s em %.1f s", nome, status, duracao)


def contar(conn, sql: str, params=None) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]
