"""Testes sem banco: leitura de CSV do CNEFE, links do portal e descrição de CSV."""

import csv
import io
import zipfile

from etl import baixar, geo
from etl.fontes import ibge_cnefe, portal_inventario

CAB = (
    "COD_UNICO_ENDERECO;COD_UF;COD_MUNICIPIO;COD_SETOR;CEP;NOM_TIPO_SEGLOGR;NOM_TITULO_SEGLOGR;"
    "NOM_SEGLOGR;NUM_ENDERECO;LATITUDE;LONGITUDE;NV_GEO_COORD;COD_ESPECIE;DSC_ESTABELECIMENTO"
)


def test_cnefe_filtra_municipio_e_decimal():
    txt = "\n".join(
        [
            CAB,
            "1;41;4106902;410690205000001P;80060140;RUA;DOUTOR;FAIVRE;150;-25,43;-49,27;1;1;",
            "2;41;4113700;411370005000001P;86000000;RUA;;OUTRA CIDADE;10;-23,3;-51,1;1;1;",
            "3;41;4106902;410690205000001P;80060140;RUA;;SEM COORDENADA;10;;;1;1;",
        ]
    )
    leitor = csv.DictReader(io.StringIO(txt), delimiter=";")
    linhas = list(ibge_cnefe.linhas_saida(leitor, "4106902"))
    assert len(linhas) == 1
    assert linhas[0][:3] == ["1", "410690205000001P", "80060140"]
    assert linhas[0][7:9] == ["-25.43", "-49.27"]


def test_cnefe_abre_zip_latin1(tmp_path):
    z = tmp_path / "4106902_CURITIBA.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(
            "4106902_CURITIBA.csv",
            (CAB + "\n1;41;4106902;1;80060140;RUA;;SÃO JOSÉ;1;-25.4;-49.2;1;1;\n").encode("latin-1"),
        )
    with ibge_cnefe.abrir_texto(z) as t:
        conteudo = t.read()
    assert "SÃO JOSÉ" in conteudo


def test_descrever_csv_sem_valores():
    dados = "CNPJ;NOME;ENDERECO;BAIRRO\n12345678000199;FULANO;RUA A 1;CENTRO\n;BELTRANO;;CENTRO\n".encode("cp1252")
    d = portal_inventario.descrever_csv(dados)
    assert d["separador"] == ";"
    assert d["linhas_lidas"] == 2
    assert ("CNPJ", 50.0) in d["colunas"]
    assert d["sinais"]["cnpj"] == ["CNPJ"]
    assert "FULANO" not in repr(d)


def test_resolver_diretorio(monkeypatch):
    class R:
        text = '<a href="PR_setores_CD2022.zip">x</a><a href="SC_setores_CD2022.zip">y</a>'

        def raise_for_status(self):
            pass

    monkeypatch.setattr(baixar.requests, "get", lambda *a, **k: R())
    url = baixar.resolver_no_diretorio("https://geoftp.ibge.gov.br/x/", r"^PR_.*\.zip$")
    assert url == "https://geoftp.ibge.gov.br/x/PR_setores_CD2022.zip"


def test_achar_coluna_e_txt():
    assert geo.achar_coluna(["cd_mun", "NM_MUN"], ["CD_MUN"]) == "cd_mun"
    assert geo.achar_coluna(["a"], ["b"]) is None
    assert geo._txt(12.0) == "12"
    assert geo._txt(float("nan")) is None
    assert geo._txt("  x ") == "x"
