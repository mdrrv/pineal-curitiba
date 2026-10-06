import datetime

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
    ("R S JOSE", "RUA SAO JOSE"),
])
def test_mesma_chave_nas_duas_formas(conn, a, b):
    for f in ("norm_logradouro", "norm_logradouro_completa"):
        assert um(conn, f"SELECT {f}(%s)", a) == um(conn, f"SELECT {f}(%s)", b), f


@pytest.mark.parametrize("a, b", [
    ("R SAO JOSE", "R JOSE"),
    ("AV PRES KENNEDY", "AV KENNEDY"),
    ("R STA CATARINA", "R CATARINA"),
    ("R DR PEDRO", "R PEDRO"),
])
def test_colisao_so_na_chave_curta(conn, a, b):
    """Títulos somem da chave curta (o CEP desempata), mas separam ruas na chave completa."""
    assert um(conn, "SELECT norm_logradouro(%s)", a) == um(conn, "SELECT norm_logradouro(%s)", b)
    assert um(conn, "SELECT norm_logradouro_completa(%s)", a) != um(conn, "SELECT norm_logradouro_completa(%s)", b)


@pytest.mark.parametrize("entrada, curta, completa", [
    ("RUA DOUTOR FAIVRE", "FAIVRE", "DOUTOR FAIVRE"),
    ("Av. Sete de Setembro", "SETE SETEMBRO", "SETE SETEMBRO"),
    ("R NSRA DA LUZ", "LUZ", "NOSSA SENHORA LUZ"),
    ("RUA", "RUA", "RUA"),
    ("AVENIDA RUA", "RUA", "RUA"),
    ("RUA DOS", "DOS", "DOS"),
    ("", None, None),
    (None, None, None),
])
def test_chaves(conn, entrada, curta, completa):
    assert um(conn, "SELECT norm_logradouro(%s)", entrada) == curta
    assert um(conn, "SELECT norm_logradouro_completa(%s)", entrada) == completa


@pytest.mark.parametrize("entrada, esperado", [
    ("PADARIA PAO DOURADO LTDA - ME", "PADARIA PAO DOURADO"),
    ("Mercado São José S/A", "MERCADO SAO JOSE"),
    ("JOAO DA SILVA 12345678901", "JOAO SILVA"),
    ("LTDA", None),
    (None, None),
])
def test_norm_nome(conn, entrada, esperado):
    assert um(conn, "SELECT norm_nome(%s)", entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("1234", 1234), ("1234-A", 1234), ("S/N", None), ("SN", None), ("0", None), ("", None), (None, None),
    ("KM 12", 12), ("1234567890", 123456),
])
def test_norm_numero(conn, entrada, esperado):
    assert um(conn, "SELECT norm_numero(%s)", entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("80.010-000", "80010000"), ("80010000", "80010000"), ("00000000", None), ("8001", None), (None, None),
])
def test_norm_cep(conn, entrada, esperado):
    assert um(conn, "SELECT norm_cep(%s)", entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("20230115", datetime.date(2023, 1, 15)), ("20230231", None), ("00000000", None), ("", None),
    (None, None), ("2023011", None), ("abcdefgh", None),
])
def test_data_rfb(conn, entrada, esperado):
    assert um(conn, "SELECT data_rfb(%s)", entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("JOAO DA SILVA 12345678901", "***.456.789-**"),
    ("JOAO DA SILVA 123.456.789-01", "***.456.789-**"),
    ("MARIA 123456789012345", None),  # 15 dígitos não é CPF
    ("PADARIA LTDA", None),
    (None, None),
])
def test_cpf_mascarado(conn, entrada, esperado):
    assert um(conn, "SELECT mascarar_cpf(cpf_no_texto(%s))", entrada) == esperado


def test_funcoes_funcionam_fora_do_search_path(conn):
    """As funções guardam o search_path de quando foram criadas."""
    with conn.cursor() as cur:
        cur.execute("SET search_path TO public")
        cur.execute("SELECT current_setting('search_path')")
        cur.execute("SELECT teste_pineal.norm_logradouro('R DR FAIVRE')")
        assert cur.fetchone()[0] == "FAIVRE"
