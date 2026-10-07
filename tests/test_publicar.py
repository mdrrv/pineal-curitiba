"""Pacote de publicação: recorte sem dado pessoal, camadas ausentes e manifesto."""

import json
import os

import geopandas as gpd
import pandas as pd
import pytest

from etl import config, publicar

LON0, LAT0 = -49.2700, -25.4300


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO bairro (codigo, nome, geom) VALUES ('1', 'Centro', ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326)))",
            (LON0 - 0.01, LAT0 - 0.01, LON0 + 0.01, LAT0 + 0.01),
        )
        for cnpj, pf, mei, precisao in [
            ("11111111000191", False, "N", "endereco"),
            ("22222222000191", False, "S", "endereco"),  # MEI: só no agregado
            ("33333333000191", True, "N", "endereco"),  # pessoa física: só no agregado
            ("44444444000191", False, "N", "bairro"),  # sem localização de quadra
        ]:
            cur.execute(
                """INSERT INTO empresa (cnpj, razao_social, pessoa_fisica, opcao_mei, situacao_cadastral,
                                        cnae_fiscal_principal, data_inicio_atividade)
                   VALUES (%s, 'NOME QUALQUER LTDA', %s, %s, '02', '4711302', '2020-01-01')""",
                (cnpj, pf, mei),
            )
            cur.execute(
                """INSERT INTO empresa_geo (cnpj, geo_precisao, bairro, h3_9, geom)
                   VALUES (%s, %s, 'Centro', '89a8100c00fffff', ST_SetSRID(ST_MakePoint(%s, %s), 4326))""",
                (cnpj, precisao, LON0, LAT0),
            )
        cur.execute("CREATE TABLE m2_densidade_h3 (h3_9 TEXT, divisao TEXT, ativos BIGINT)")
        cur.execute("INSERT INTO m2_densidade_h3 VALUES ('89a8100c00fffff', NULL, 4), ('89a8100c00fffff', '47', 4)")
    conn.commit()
    return tmp_path


def test_pacote(conn, ambiente):
    pasta = ambiente / "pub"
    m = publicar.main(["--pasta", str(pasta)])
    assert set(m["camadas"]) == {"empresas", "densidade_h3", "bairros"}
    assert m["fora"]["demanda_h3"] == "tabelas ausentes: demanda_h3"
    emp = gpd.read_file(pasta / "empresas.fgb")
    assert emp["cnpj"].tolist() == ["11111111000191"]
    assert not any(publicar.PROIBIDAS.search(c) for c in emp.columns if c != "geometry")
    dens = gpd.read_file(pasta / "densidade_h3.fgb")
    assert dens["ativos"].tolist() == [4] and json.loads(dens["por_divisao"][0]) == {"47": 4}
    bairros = gpd.read_file(pasta / "bairros.fgb")
    assert bairros["ativos"].tolist() == [4]
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    assert manifesto["camadas"]["empresas"]["sha256"] == publicar.sha256(pasta / "empresas.fgb")


def test_checagem():
    with pytest.raises(ValueError, match="colunas proibidas"):
        publicar.checar("x", pd.DataFrame({"razao_social": ["A"]}))
    with pytest.raises(ValueError, match="CPF na coluna obs"):
        publicar.checar("x", pd.DataFrame({"obs": ["ok", "dono 123.456.789-09"]}))
    publicar.checar("x", pd.DataFrame({"cnpj": ["11111111000191"], "h3_9": ["89a81234567890f"]}))
