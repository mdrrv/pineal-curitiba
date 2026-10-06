import pytest


def um(conn, sql, *params):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


@pytest.mark.parametrize("a, b", [
    ("R DR FAIVRE", "RUA DOUTOR FAIVRE"),
    ("AV. SETE DE SETEMBRO", "Avenida Sete de Setembro"),
    ("R. MAL. FLORIANO PEIXOTO", "RUA MARECHAL FLORIANO PEIXOTO"),
    ("AL PRES TAUNAY", "ALAMEDA PRESIDENTE TAUNAY"),
    ("R XV DE NOVEMBRO", "RUA XV DE NOVEMBRO"),
    ("R. PE. ANCHIETA", "Rua Padre Anchieta"),
    ("PCA TIRADENTES", "PRAÇA TIRADENTES"),
])
def test_mesma_chave(conn, a, b):
    assert um(conn, "SELECT cwb.norm_logradouro(%s)", a) == um(conn, "SELECT cwb.norm_logradouro(%s)", b)


@pytest.mark.parametrize("entrada, esperado", [
    ("RUA DOUTOR FAIVRE", "FAIVRE"),
    ("Av. Sete de Setembro", "SETE SETEMBRO"),
    ("RUA", "RUA"),
    ("AVENIDA RUA", "RUA"),
    ("RUA DOS", "DOS"),
    ("", None),
    (None, None),
])
def test_norm_logradouro(conn, entrada, esperado):
    assert um(conn, "SELECT cwb.norm_logradouro(%s)", entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("1234", 1234), ("1234-A", 1234), ("S/N", None), ("SN", None), ("0", None), ("", None), (None, None),
    ("KM 12", 12), ("1234567890", 123456),
])
def test_norm_numero(conn, entrada, esperado):
    assert um(conn, "SELECT cwb.norm_numero(%s)", entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("80.010-000", "80010000"), ("80010000", "80010000"), ("00000000", None), ("8001", None), (None, None),
])
def test_norm_cep(conn, entrada, esperado):
    assert um(conn, "SELECT cwb.norm_cep(%s)", entrada) == esperado
