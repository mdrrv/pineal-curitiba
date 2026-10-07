"""Regressões da revisão de código antes da rodada real (cada teste cita o defeito que cobre)."""

import datetime
import os
import zipfile
from decimal import Decimal

import pytest

from etl import config, isocronas, leitura, verificar
from etl.fontes import inmet_clima, inpi_marcas, listas_cnpj


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    return tmp_path / "bruto"


def test_valor_br(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT valor_br('4,599'), valor_br('1.234'), valor_br('12.345.678'), valor_br('1.234,56'), "
            "valor_br('1234.5'), valor_br('R$ 10,00')"
        )
        assert cur.fetchone() == (Decimal("4.599"), 1234, 12345678, Decimal("1234.56"), Decimal("1234.5"), 10)


def test_utf8_cortado_na_amostra(tmp_path):
    # o 1º MiB termina no meio do "Á": antes, o arquivo inteiro virava cp1252 ("Ã\x81GUA VERDE")
    linha = "BAIRRO\n"
    corpo = "X" * ((1 << 20) - len(linha) - 1) + "\nÁGUA VERDE\n"
    arq = tmp_path / "a.csv"
    arq.write_bytes((linha + corpo).encode("utf-8"))
    with leitura.abrir_texto(arq) as t:
        assert "ÁGUA VERDE" in t.read()


def test_categorias_alarme_e_arma(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT categoria_natureza('Disparo de alarme'), categoria_natureza('Disparo de arma de fogo')")
        assert cur.fetchone() == ("outros", "violento")


def test_listas_pf_sem_atributos_e_datas_invalidas(conn, ambiente):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO empresa (cnpj, cnpj_basico, pessoa_fisica, situacao_cadastral) VALUES
                       ('11111111000191', '11111111', false, '02'), ('55555555000191', '55555555', true, '02')""")
    conn.commit()
    pasta = ambiente / "bndes_operacoes"
    pasta.mkdir(parents=True)
    (pasta / "op.csv").write_text(
        "CLIENTE;CPF/CNPJ;UF;OBS;PRODUTO;DATA DA CONTRATACAO;VALOR CONTRATADO R$\n"
        "EMPRESA X SA;11.111.111/0001-91;PR;dono 123.456.789-09;FINAME;202313;1.000,00\n"
        "JOAO DA SILVA;55.555.555/0001-91;PR;mei;CARTAO;2026-01-05;10,00\n",
        encoding="utf-8",
    )
    pasta = ambiente / "anatel_scm"
    pasta.mkdir()
    (pasta / "acessos.csv").write_text(
        "ANO_MES;CNPJ;TECNOLOGIA;ACESSOS\n2026-08;11111111000191;FIBRA;1.000\n2026-09;11111111000191;FIBRA;1.200\n",
        encoding="utf-8",
    )
    listas_cnpj.main(["--so", "bndes_operacoes", "--so", "anatel_scm"])  # mês 13 não aborta a lista
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cnpj_basico, data, atributos FROM lista_registro WHERE lista = 'bndes_operacoes' ORDER BY 1"
        )
        (_, d1, a1), (_, d2, a2) = cur.fetchall()
        assert d1 is None and d2 == datetime.date(2026, 1, 5)  # mês 13 vira NULL
        assert a1["OBS"] == "dono ***" and "CLIENTE" not in a1  # CPF no texto some; coluna de nome não entra
        assert a2 == {}  # pessoa física: nenhuma coluna extra
        cur.execute("SELECT valor FROM empresa_lista WHERE lista = 'anatel_scm'")
        assert cur.fetchone()[0] == 1200  # mês mais recente, não a soma dos meses


def test_inpi_titular_sem_forma_de_empresa_e_outra_cidade(conn, ambiente):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO empresa (cnpj, cnpj_basico, razao_social, identificador_mf) VALUES
                       ('11111111000191', '11111111', 'JOAO DA SILVA LTDA', '1'),
                       ('22222222000191', '22222222', 'COMERCIAL SOUZA LTDA', '1')""")
    conn.commit()
    pasta = ambiente / "inpi_marcas"
    pasta.mkdir(parents=True)
    proc = (
        '<processo numero="{}"><titulares><titular nome-razao-social="{}" uf="PR" cidade="{}"/></titulares></processo>'
    )
    (pasta / "RM1.xml").write_text(
        '<revista numero="1">'
        + proc.format(1, "JOAO DA SILVA", "Curitiba")
        + proc.format(2, "COMERCIAL SOUZA LTDA", "Londrina")
        + proc.format(3, "COMERCIAL SOUZA LTDA", "Curitiba")
        + "</revista>",
        encoding="utf-8",
    )
    inpi_marcas.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT processo, cnpj FROM inpi_marca")
        assert cur.fetchall() == [("3", "22222222000191")]


def test_inmet_hora_repetida_em_dois_arquivos(conn, ambiente):
    pasta = ambiente / "inmet_clima"
    pasta.mkdir(parents=True)
    cab = (
        "REGIAO:;S\nUF:;PR\nESTACAO:;CURITIBA\nCODIGO (WMO):;A807\n"
        "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);"
        "TEMPERATURA MÁXIMA NA HORA ANT. (AUT) (°C);TEMPERATURA MÍNIMA NA HORA ANT. (AUT) (°C);\n"
    )
    csv_ = (cab + "2025/03/10;1500 UTC;2,0;25,0;26,0;24,0;\n").encode("cp1252")
    nome = "INMET_S_PR_A807_CURITIBA_01-01-2025_A_31-12-2025.CSV"
    with zipfile.ZipFile(pasta / "2025.zip", "w") as z:
        z.writestr(nome, csv_)
    (pasta / nome).write_bytes(csv_)
    inmet_clima.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT precipitacao_mm, horas_medidas FROM clima_dia")
        assert cur.fetchone() == (Decimal("2.0"), 1)


def test_gtfs_parada_sem_horario(tmp_path):
    gtfs = tmp_path / "g.zip"
    with zipfile.ZipFile(gtfs, "w") as z:
        z.writestr("stops.txt", "stop_id,stop_lat,stop_lon\nA,-25.43,-49.27\nB,-25.43,-49.26\nC,-25.43,-49.25\n")
        z.writestr("trips.txt", "route_id,service_id,trip_id\nR,U,T\n")
        z.writestr(
            "stop_times.txt",
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T,08:00:00,08:00:00,A,1\nT,,,B,2\nT,08:10:00,08:10:00,C,3\n",
        )
    conexoes, _ = isocronas.ler_conexoes(gtfs, datetime.date(2026, 10, 8), 7 * 3600, 9 * 3600)
    assert [(a, b) for _, _, a, b, _ in conexoes] == [("A", "C")]


def test_transferencia_leste_oeste_a_290_m():
    lat = -25.43
    dlon = 290 / (111_320 * __import__("math").cos(__import__("math").radians(lat)))
    viz = isocronas.transferencias({"A": (lat, -49.27), "B": (lat, -49.27 + dlon)})
    assert [t for t, _ in viz["A"]] == ["B"]


def test_verificar_consulta_que_falha_vira_linha(conn, ambiente, monkeypatch):
    monkeypatch.setenv("RFB_DSN", os.environ["PINEAL_TEST_DSN"])
    with conn.cursor() as cur:
        cur.execute(
            "DROP SCHEMA IF EXISTS dados_rfb CASCADE; CREATE SCHEMA dados_rfb; "
            "CREATE TABLE dados_rfb.cnpj_consolidado (cnpj TEXT)"
        )  # sem uf/municipio
    conn.commit()
    try:
        linhas = verificar.banco_rfb()
        assert ("banco MINDATA", "consulta", "falha") == linhas[-1][:3]
    finally:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA dados_rfb CASCADE")
        conn.commit()


def test_censo_sem_perfil_do_ponto(conn, ambiente):
    from etl.fontes import ibge_censo_setor

    pasta = ambiente / "ibge_censo_setor"
    pasta.mkdir(parents=True)
    (pasta / "Agregados_por_setores_basico_BR.csv").write_text("CD_SETOR;CD_MUN;v0001\n410690205000001;4106902;10\n")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('empresa_perfil')")
        assert cur.fetchone()[0] is None
    ibge_censo_setor.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT pessoas FROM setor_demografia")
        assert cur.fetchone()[0] == 10
