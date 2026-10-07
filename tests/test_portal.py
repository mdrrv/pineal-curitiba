"""Cliente do portal de dados abertos com HTML e JSON no formato real (outubro de 2026)."""

from datetime import datetime

from etl import portal

DETALHE = """<html><head><title>Detalhes do Conjunto de Dados - Base de Alvar&#xE1;s - Dados Abertos</title></head><body>
<strong>&#xDA;ltima atualiza&#xE7;&#xE3;o</strong> 01/10/2026 05:19:00 <br />
<strong>
    Secretaria
</strong>
SMF <br />
<strong>Frequ&#xEA;ncia de atualiza&#xE7;&#xE3;o</strong> Mensal <br />
<a class="nav-link" href="#aba_377f4e23-0e4f-4f11-954f-ae06ba689558" role="tab">.CSV</a>
<span>2026-10-01_Alvaras_-_Base_de_Dados.csv</span><span>01/10/2026 05:19:00 &nbsp; 543,61 MB</span>
<div><table class='table table-bordered'><thead><tr><th>NOME_EMPRESARIAL</th><th>CEP</th><th>CNAE_ATIVIDADE_PRINCIPAL</th></tr></thead></table></div>
<span>2026-10-01_Alvaras_-_Dicionario_de_Dados.csv</span><span>01/10/2026</span>
<div><table class='table table-bordered'><thead><tr><th>NOME CAMPO</th><th>TIPO</th></tr></thead></table></div>
<a type="button" href="http://dadosabertos.c3sl.ufpr.br/curitiba/BaseAlvaras/" target="_blank">BASE DE DADOS</a>
</body></html>"""

LISTA = (
    "<table><thead><tr><th>Nome</th></tr></thead><tbody>"
    "<tr><td class='align-left'><a href='https://mid-dadosabertos.curitiba.pr.gov.br/BaseAlvaras/2026-10-01_Alvaras_-_Base_de_Dados.csv'>x</a></td>"
    "<td><a href='https://mid-dadosabertos.curitiba.pr.gov.br/BaseAlvaras/2026-10-01_Alvaras_-_Dicionario_de_Dados.csv'>d</a></td>"
    "<td>01/10/2026 05:26</td><td>543,61 MB</td><td><input type='checkbox'></td></tr>"
    "<tr><td class='align-left'><a href='https://mid-dadosabertos.curitiba.pr.gov.br/BaseAlvaras/2026-09-01_Alvaras_-_Base_de_Dados.csv'>x</a></td>"
    "<td></td><td>01/09/2026 05:26</td><td>544,45 MB</td></tr></tbody></table>"
)


def test_ler_detalhe():
    c = portal.ler_detalhe(DETALHE, "be211e1f")
    assert c.titulo == "Base de Alvarás"
    assert c.metadados == {
        "Última atualização": "01/10/2026 05:19:00",
        "Secretaria": "SMF",
        "Frequência de atualização": "Mensal",
    }
    assert c.extensoes == {"csv": "377f4e23-0e4f-4f11-954f-ae06ba689558"}
    assert c.colunas["2026-10-01_Alvaras_-_Base_de_Dados.csv"] == [
        "NOME_EMPRESARIAL",
        "CEP",
        "CNAE_ATIVIDADE_PRINCIPAL",
    ]
    assert c.espelho == "http://dadosabertos.c3sl.ufpr.br/curitiba/BaseAlvaras/"


def test_ler_lista():
    a = portal.ler_lista(LISTA)
    assert [x.nome for x in a] == ["2026-10-01_Alvaras_-_Base_de_Dados.csv", "2026-09-01_Alvaras_-_Base_de_Dados.csv"]
    assert a[0].dicionario.endswith("2026-10-01_Alvaras_-_Dicionario_de_Dados.csv")
    assert a[1].dicionario is None
    assert a[0].atualizado == datetime(2026, 10, 1, 5, 26)
    assert a[0].tamanho == "543,61 MB"


def test_mais_recente(monkeypatch):
    class R:
        def __init__(self, texto=None, dados=None):
            self.text, self.dados = texto, dados

        def raise_for_status(self):
            pass

        def json(self):
            return self.dados

    def get(url, params=None, **k):
        if "detalhe" in url:
            return R(texto=DETALHE)
        return R(dados={"sucesso": True, "tabela": LISTA, "paginacao": {"pagina": 1, "totalPaginas": 1}})

    monkeypatch.setattr(portal.requests, "get", get)
    a = portal.mais_recente("be211e1f")
    assert a.nome == "2026-10-01_Alvaras_-_Base_de_Dados.csv"
    assert portal.mais_recente("be211e1f", padrao="09-01").nome == "2026-09-01_Alvaras_-_Base_de_Dados.csv"
