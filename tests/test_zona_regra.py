"""Regras de zoneamento: carga validada do CSV, modelo para preencher e amostra para revisar."""

import csv
import os

import pytest

from etl import config, db
from etl.fontes import zona_regra

CAB = "zona;cnae_prefixo;permitido;fonte;observacao\n"


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    with conn.cursor() as cur:
        for cod, nome in [("ZR1", "Zona Residencial 1"), ("ZC", "Zona Central")]:
            cur.execute(
                "INSERT INTO zoneamento (codigo, nome, geom) VALUES (%s, %s, ST_Multi(ST_MakeEnvelope(0, 0, 1, 1, 4326)))",
                (cod, nome),
            )
        for cnpj, cnae, zona in [("1", "4711302", "ZR1"), ("2", "6201501", "ZR1"), ("3", "4711302", "ZC")]:
            cur.execute(
                "INSERT INTO empresa (cnpj, situacao_cadastral, cnae_fiscal_principal) VALUES (%s, '02', %s)",
                (cnpj, cnae),
            )
            cur.execute(
                "INSERT INTO empresa_geo (cnpj, zona, geom) VALUES (%s, %s, ST_SetSRID(ST_MakePoint(0.5, 0.5), 4326))",
                (cnpj, zona),
            )
    conn.commit()
    return tmp_path


def test_carga_e_amostra(conn, ambiente):
    arq = ambiente / "zona_regra.csv"
    arq.write_text(
        CAB + "ZR1;47;N;Anexo II, ZR-1;varejo de grande porte\nZR1;62;sim;Anexo II, ZR-1;\nZC;47;S;Anexo II, ZC;\n",
        encoding="utf-8",
    )
    zona_regra.main(["--arquivo", str(arq)])
    db.executar_sql(conn, "30_enriquecimento.sql")
    with conn.cursor() as cur:
        cur.execute("SELECT cnpj, regra_prefixo, permitido FROM uso_zoneamento ORDER BY 1")
        assert cur.fetchall() == [("1", "47", False), ("2", "62", True), ("3", "47", True)]
    conn.commit()
    zona_regra.main(["--amostra", "10"])
    with open(config.RELATORIOS / "uso_zoneamento_amostra.csv", encoding="utf-8") as f:
        linhas = list(csv.reader(f, delimiter=";"))
    assert len(linhas) == 2 and linhas[1][:2] == ["1", "ZR1"] and linhas[1][5] == "Anexo II, ZR-1"

    zona_regra.main(["--modelo"])
    with open(config.RELATORIOS / "zona_regra_modelo.csv", encoding="utf-8") as f:
        modelo = [r[:3] for r in csv.reader(f, delimiter=";")][1:]
    assert modelo == [["ZC", "47", "S"], ["ZR1", "47", "N"], ["ZR1", "62", "S"]]


def test_erros(conn, ambiente):
    arq = ambiente / "zona_regra.csv"
    arq.write_text(CAB + "ZX;47;N;lei;\nZR1;4;N;lei;\nZR1;47;talvez;lei;\nZC;47;S;;\nZC;47;S;lei;\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        zona_regra.main(["--arquivo", str(arq)])
    msg = str(e.value)
    for trecho in [
        "linha 2: zona 'ZX'",
        "linha 3: cnae_prefixo",
        "linha 4: permitido",
        "linha 5: sem fonte",
        "linha 6: regra repetida",
    ]:
        assert trecho in msg


def test_csv_versionado_vazio_e_valido(conn, ambiente):
    zona_regra.main([])
    assert db.contar(conn, "SELECT count(*) FROM zona_regra") == 0
