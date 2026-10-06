import os

import psycopg2
import pytest

from etl import config, db

SCHEMA_TESTE = "teste_pineal"  # diferente do padrão (cwb) para provar que o schema é configurável


@pytest.fixture
def conn(monkeypatch):
    dsn = os.getenv("PINEAL_TEST_DSN")
    if not dsn:
        pytest.skip("PINEAL_TEST_DSN não definido (banco descartável com PostGIS)")
    monkeypatch.setattr(config, "SCHEMA", SCHEMA_TESTE)
    c = psycopg2.connect(dsn)
    with c.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_TESTE} CASCADE")
        cur.execute(f"CREATE SCHEMA {SCHEMA_TESTE}")
        cur.execute(f"SET search_path TO {SCHEMA_TESTE}, public")
    c.commit()
    db.criar_schema(c)
    c.commit()
    yield c
    c.rollback()
    c.close()
