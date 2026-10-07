"""M1b: listas com CNPJ, com arquivos sintéticos em layouts diferentes."""

import datetime
import os
import zipfile
from decimal import Decimal

import pytest

from etl import config
from etl.fontes import listas_cnpj


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    with conn.cursor() as cur:
        for c in ["11111111000191", "55555555000191", "00123456000149"]:
            cur.execute("INSERT INTO empresa (cnpj, cnpj_basico, situacao_cadastral) VALUES (%s, %s, '02')", (c, c[:8]))
    conn.commit()
    return tmp_path / "bruto"


def escrever(caminho, linhas, enc="cp1252"):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes("\r\n".join(";".join(li) for li in linhas).encode(enc))


def test_cnpj_de():
    assert listas_cnpj.cnpj_de("11.111.111/0001-91", True) == "11111111000191"
    assert listas_cnpj.cnpj_de("11.111.111/0001-90", True) is None  # DV errado
    assert listas_cnpj.cnpj_de("123456000149", True) == "00123456000149"  # zeros perdidos
    assert listas_cnpj.cnpj_de("123456000149", False) is None  # coluna CPF/CNPJ: não completa
    assert listas_cnpj.cnpj_de("123.456.789-09", False) is None
    assert listas_cnpj.cnpj_de("11111111", True) == "11111111"


def test_listas(conn, ambiente):
    escrever(
        ambiente / "bndes_operacoes" / "operacoes.csv",
        [
            ["CLIENTE", "CPF/CNPJ", "UF", "PRODUTO", "DATA DA CONTRATACAO", "VALOR CONTRATADO R$"],
            ["EMPRESA X SA", "11.111.111/0002-72", "SP", "FINAME", "2025-03-10", "1.000.000,00"],
            ["EMPRESA X SA", "11.111.111/0001-91", "PR", "BNDES AUTOMATICO", "2026-01-05", "500.000,00"],
            ["JOSE DA SILVA", "123.456.789-09", "PR", "CARTAO", "2026-01-05", "10.000,00"],
            ["JOSE DA SILVA", "***.456.789-**", "PR", "CARTAO", "2026-01-05", "10.000,00"],
            ["OUTRA SA", "99.999.999/0001-91", "PR", "FINAME", "2026-01-05", "9,00"],
        ],
    )
    (ambiente / "anp_revendas").mkdir(parents=True)
    with zipfile.ZipFile(ambiente / "anp_revendas" / "precos.zip", "w") as z:
        z.writestr(
            "ca-2026-02.csv",
            "Regiao - Sigla;Municipio;CNPJ da Revenda;Produto;Data da Coleta;Valor de Venda\n"
            "S;CURITIBA;55.555.555/0001-91;GASOLINA;01/09/2026;5,79\n"
            "S;CURITIBA;55.555.555/0001-91;ETANOL;02/09/2026;3,99\n"
            "S;LONDRINA;55.555.555/0002-72;GASOLINA;01/09/2026;6,99\n",
        )
    escrever(
        ambiente / "cnes" / "cnes.csv",
        [
            ["CO_CNES", "NU_CNPJ", "DS_TIPO_UNIDADE", "NU_TELEFONE", "NO_EMAIL"],
            ["1234567", "123456000149", "CLINICA/CENTRO DE ESPECIALIDADE", "4133330000", "x@y.com"],
        ],
    )
    listas_cnpj.main([])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cnpj, lista, via, registros, valor, data_min, data_max, rotulos FROM empresa_lista ORDER BY 2"
        )
        assert cur.fetchall() == [
            (
                "55555555000191",
                "anp_revendas",
                "cnpj",
                2,
                None,
                datetime.date(2026, 9, 1),
                datetime.date(2026, 9, 2),
                ["ETANOL", "GASOLINA"],
            ),
            (
                "11111111000191",
                "bndes_operacoes",
                "cnpj",
                2,
                Decimal("1500000.00"),
                datetime.date(2025, 3, 10),
                datetime.date(2026, 1, 5),
                ["BNDES AUTOMATICO", "FINAME"],
            ),
            ("00123456000149", "cnes", "cnpj", 1, None, None, None, ["CLINICA/CENTRO DE ESPECIALIDADE"]),
        ]
        cur.execute("SELECT count(*) FROM lista_registro WHERE lista = 'bndes_operacoes' AND cnpj IS NULL")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT atributos FROM lista_registro WHERE lista = 'cnes'")
        assert cur.fetchone()[0] == {"CO_CNES": "1234567", "DS_TIPO_UNIDADE": "CLINICA/CENTRO DE ESPECIALIDADE"}
        cur.execute("SELECT count(*) FROM lista_registro r WHERE r::text ~ '123\\.?456\\.?789|JOSE|4133330000'")
        assert cur.fetchone()[0] == 0
    md = (config.RELATORIOS / "listas_cnpj.md").read_text(encoding="utf-8")
    assert "| bndes_operacoes | operacoes.csv | 5 | 2 | 1 |" in md
    assert "| mdic_exportadoras | sem arquivo (https://www.gov.br/mdic" in md


def test_lista_so_raiz(conn, ambiente):
    escrever(
        ambiente / "mdic_exportadoras" / "exportadoras_2025.csv",
        [["ANO", "CNPJ", "EMPRESA", "UF", "FAIXA_VALOR"], ["2025", "11111111", "EMPRESA X", "SP", "ATE US$ 1 MILHAO"]],
    )
    listas_cnpj.main(["--so", "mdic_exportadoras"])
    with conn.cursor() as cur:
        cur.execute("SELECT cnpj, via, data_min, rotulos FROM empresa_lista")
        assert cur.fetchall() == [("11111111000191", "raiz", datetime.date(2025, 1, 1), ["ATE US$ 1 MILHAO"])]
