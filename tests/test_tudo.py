"""Orquestrador: ordem das dependências, falha opcional x essencial e retomada."""

import os

import pytest

from etl import config, db, tudo


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    monkeypatch.setattr(config, "RUN_ID", "rodada-teste")
    monkeypatch.setattr(tudo.verificar, "main", lambda argv=None: 0)
    return tmp_path


def etapa(nome, chamadas, falha=None):
    def rodar():
        chamadas.append(nome)
        with db.etapa(nome):
            if falha:
                raise falha

    return rodar


def test_ordem_das_dependencias():
    nomes = [n for n, _ in tudo.ORDEM]
    antes = lambda a, b: nomes.index(a) < nomes.index(b)  # noqa: E731
    assert antes("territorio", "enriquecer") and antes("enriquecer", "alvaras")
    assert antes("alvaras", "score") and antes("listas", "score") and antes("score", "publicar")
    assert set(tudo.OPCIONAIS) <= set(nomes)


def test_falhas_e_retomada(conn, ambiente, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        tudo,
        "ORDEM",
        [
            ("schema", etapa("schema", chamadas)),
            ("transporte", etapa("transporte", chamadas, SystemExit("sem GTFS"))),
            ("score", etapa("score", chamadas, RuntimeError("quebrou"))),
            ("publicar", etapa("publicar", chamadas)),
        ],
    )
    monkeypatch.setattr(tudo, "OPCIONAIS", {"transporte"})
    assert tudo.main([]) == 1
    assert chamadas == ["schema", "transporte", "score"]  # opcional segue, essencial para
    md = (ambiente / "relatorios" / "rodada.md").read_text(encoding="utf-8")
    assert "| transporte | falhou (opcional) |" in md and "| score | falhou |" in md

    chamadas.clear()
    monkeypatch.setattr(tudo, "ORDEM", [(n, etapa(n, chamadas)) for n in ["schema", "transporte", "score", "publicar"]])
    assert tudo.main(["--retomar", "rodada-teste"]) == 0
    assert chamadas == ["transporte", "score", "publicar"]  # schema já tinha dado ok
    assert "| schema | já feita |" in (ambiente / "relatorios" / "rodada.md").read_text(encoding="utf-8")


def test_verificacao_com_falha_nao_roda(conn, ambiente, monkeypatch):
    chamadas = []
    monkeypatch.setattr(tudo.verificar, "main", lambda argv=None: 1)
    monkeypatch.setattr(tudo, "ORDEM", [("schema", etapa("schema", chamadas))])
    assert tudo.main([]) == 1 and chamadas == []
