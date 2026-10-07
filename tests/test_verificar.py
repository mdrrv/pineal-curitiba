"""Verificação antes da rodada: bancos, arquivos, hosts (sem rede de verdade) e código de saída."""

import os

import pytest
import requests

from etl import config, verificar


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.delenv("RFB_DSN", raising=False)
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS dados_rfb CASCADE")
    conn.commit()
    yield tmp_path
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS dados_rfb CASCADE")
    conn.commit()


def situacao(linhas, item):
    return next(s for _, i, s, _ in linhas if i == item)


def test_sem_base_da_receita_falha(conn, ambiente):
    assert verificar.main(["--sem-rede"]) == 1
    md = (ambiente / "relatorios" / "verificacao.md").read_text(encoding="utf-8")
    assert "| banco MINDATA | dados_rfb.cnpj_consolidado | falha |" in md
    assert "| banco Pineal | extensão postgis | ok |" in md


def test_com_base_e_arquivos(conn, ambiente, monkeypatch):
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA dados_rfb")
        cur.execute("CREATE TABLE dados_rfb.cnpj_consolidado (uf TEXT, municipio TEXT, nome_municipio TEXT)")
        cur.execute("INSERT INTO dados_rfb.cnpj_consolidado VALUES ('PR', '7535', 'CURITIBA')")
        cur.execute("CREATE TABLE dados_rfb.pncp_contratos (cnpj_14 TEXT)")
    conn.commit()
    (ambiente / "bruto" / "ibge_cnefe").mkdir(parents=True)
    (ambiente / "bruto" / "ibge_cnefe" / "4106902.zip").write_bytes(b"x" * 1000)
    (ambiente / "bruto" / "pmc_alvaras").mkdir()
    (ambiente / "bruto" / "pmc_alvaras" / "base.csv.parcial").write_bytes(b"x")
    assert verificar.main(["--sem-rede"]) == 0
    rfb = verificar.banco_rfb()
    assert situacao(rfb, "recorte do município") == "ok"
    assert situacao(rfb, "cruzamento pncp") == "ok" and situacao(rfb, "cruzamento pgfn") == "aviso"
    arq = verificar.arquivos()
    assert situacao(arq, "ibge_cnefe") == "ok" and situacao(arq, "pmc_alvaras") == "aviso"

    monkeypatch.setattr(config, "COD_RFB", "9999")
    assert situacao(verificar.banco_rfb(), "recorte do município") == "aviso"  # acha pelo nome


def test_hosts(monkeypatch):
    def head(url, **_):
        if "geofabrik" in url:
            raise requests.ConnectionError("bloqueado")
        return type("R", (), {"status_code": 200})()

    monkeypatch.setattr(requests, "head", head)
    linhas = verificar.hosts()
    assert situacao(linhas, "download.geofabrik.de") == "aviso"
    assert situacao(linhas, "dadosabertos.curitiba.pr.gov.br") == "ok"
    usos = verificar.hosts_do_catalogo()
    assert "osm_vias" in usos["download.geofabrik.de"]
