import os

import psycopg2
import pytest

from etl import db


@pytest.fixture
def conn():
    dsn = os.getenv("PINEAL_TEST_DSN")
    if not dsn:
        pytest.skip("PINEAL_TEST_DSN não definido (banco descartável com PostGIS)")
    c = psycopg2.connect(dsn)
    with c.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS cwb CASCADE")
    db.criar_schema(c)
    c.commit()
    yield c
    c.rollback()
    c.close()
