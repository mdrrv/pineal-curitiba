"""Marcas do INPI (casamento pela razão social) e clima diário do INMET."""

import datetime
import os
import zipfile
from decimal import Decimal

import pytest

from etl import config
from etl.fontes import inmet_clima, inpi_marcas


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    return tmp_path / "bruto"


def rpi(numero, processos):
    corpo = "".join(
        f"""<processo numero="{p}" data-deposito="10/03/2026">
              <despachos><despacho codigo="{cod}" nome="{nome}"/></despachos>
              <titulares><titular nome-razao-social="{tit}" pais="BR" uf="{uf}"/></titulares>
              <marca apresentacao="Mista" natureza="De Produto"><nome>PÃO DOURADO</nome></marca>
              <lista-classe-nice><classe-nice codigo="30"/><classe-nice codigo="43"/></lista-classe-nice>
            </processo>"""
        for p, cod, nome, tit, uf in processos
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><revista numero="{numero}" data="07/10/2026">{corpo}</revista>'


def test_inpi(conn, ambiente):
    with conn.cursor() as cur:
        for cnpj, razao, mf in [
            ("11111111000191", "PADARIA PAO DOURADO LTDA", "1"),
            ("11111111000272", "PADARIA PAO DOURADO LTDA", "2"),
            ("22222222000100", "MERCADO BOM LTDA", "1"),
            ("33333333000100", "MERCADO BOM EIRELI", "1"),  # mesmo nome normalizado, outra raiz: ambíguo
        ]:
            cur.execute(
                "INSERT INTO empresa (cnpj, cnpj_basico, razao_social, identificador_mf) VALUES (%s, %s, %s, %s)",
                (cnpj, cnpj[:8], razao, mf),
            )
    conn.commit()
    pasta = ambiente / "inpi_marcas"
    pasta.mkdir(parents=True)
    pub = ("IPAS009", "Publicação de pedido de registro para oposição")
    with zipfile.ZipFile(pasta / "RM2850.zip", "w") as z:
        z.writestr(
            "RM2850.xml",
            rpi(
                2850,
                [
                    ("900000001", *pub, "PADARIA PAO DOURADO LTDA", "PR"),
                    ("900000002", *pub, "PADARIA PAO DOURADO LTDA", "SP"),
                    ("900000003", *pub, "JOSE DA SILVA", "PR"),
                    ("900000004", *pub, "MERCADO BOM LTDA", "PR"),
                ],
            ),
        )
    (pasta / "RM2851.xml").write_text(
        rpi(2851, [("900000001", "IPAS158", "Concessão de registro", "PADARIA PAO DOURADO LTDA - ME", "PR")]),
        encoding="utf-8",
    )
    inpi_marcas.main([])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT processo, cnpj, marca, classes_nice, ultimo_despacho, revista, data_deposito FROM inpi_marca"
        )
        assert cur.fetchall() == [
            ("900000001", "11111111000191", "PÃO DOURADO", ["30", "43"], "IPAS158", 2851, datetime.date(2026, 3, 10))
        ]
        cur.execute("SELECT cnpj, marcas, concedidas, classes_nice FROM empresa_marca")
        assert cur.fetchall() == [("11111111000191", 1, 1, ["30", "43"])]
        cur.execute("SELECT count(*) FROM inpi_marca m WHERE m::text ILIKE '%%SILVA%%'")
        assert cur.fetchone()[0] == 0


CAB_INMET = (
    "REGIAO:;S\nUF:;PR\nESTACAO:;CURITIBA\nCODIGO (WMO):;A807\nLATITUDE:;-25,44\nLONGITUDE:;-49,23\n"
    "ALTITUDE:;923,5\nDATA DE FUNDACAO:;22/02/03\n"
    "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);"
    "TEMPERATURA MÁXIMA NA HORA ANT. (AUT) (°C);TEMPERATURA MÍNIMA NA HORA ANT. (AUT) (°C);\n"
)


def test_inmet(conn, ambiente):
    pasta = ambiente / "inmet_clima"
    pasta.mkdir(parents=True)
    with zipfile.ZipFile(pasta / "2025.zip", "w") as z:
        z.writestr(
            "2025/INMET_S_PR_A807_CURITIBA_01-01-2025_A_31-12-2025.CSV",
            (
                CAB_INMET
                + "2025/03/10;0200 UTC;1,2;18,0;18,5;17,5;\n"  # 23h do dia 9 em Curitiba
                + "2025/03/10;1500 UTC;0;25,0;26,0;24,0;\n"
                + "2025/03/10;1600 UTC;2,0;24,0;-9999;23,0;\n"
                + "2025/03/10;1700 UTC;-9999;;;;\n"
            ).encode("cp1252"),
        )
        z.writestr(
            "2025/INMET_S_PR_A834_LONDRINA_01-01-2025_A_31-12-2025.CSV",
            (CAB_INMET.replace("A807", "A834") + "2025/03/10;1500 UTC;9;9;9;9;\n").encode("cp1252"),
        )
    inmet_clima.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM clima_dia ORDER BY data")
        assert cur.fetchall() == [
            (
                "A807",
                datetime.date(2025, 3, 9),
                Decimal("1.2"),
                1,
                Decimal("18.0"),
                Decimal("17.5"),
                Decimal("18.5"),
                1,
            ),
            (
                "A807",
                datetime.date(2025, 3, 10),
                Decimal("2.0"),
                1,
                Decimal("24.5"),
                Decimal("23.0"),
                Decimal("26.0"),
                2,
            ),
        ]
