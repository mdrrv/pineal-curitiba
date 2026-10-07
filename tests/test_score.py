"""Risco de fechamento (com validação em anos passados) e score de lead."""

import datetime
import os

import pytest

from etl import config, score


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    with conn.cursor() as cur:
        # comércio (47) fecha um a cada dois com pouco mais de 1 ano; software (62) não fecha
        for k in range(400):
            div = "4711302" if k % 2 == 0 else "6201501"
            inicio = datetime.date(2017 + (k // 4) % 8, 3, 1)
            fecha = div.startswith("47") and k % 4 == 0
            cur.execute(
                """INSERT INTO empresa (cnpj, cnpj_basico, situacao_cadastral, data_situacao_cadastral,
                                        data_inicio_atividade, cnae_fiscal_principal, porte_empresa, opcao_mei)
                   VALUES (%s, %s, %s, %s, %s, %s, '01', 'S')""",
                (
                    f"{k:08d}000100",
                    f"{k:08d}",
                    "08" if fecha else "02",
                    inicio + datetime.timedelta(days=400) if fecha else None,
                    inicio,
                    div,
                ),
            )
        cur.execute(
            """INSERT INTO empresa (cnpj, cnpj_basico, situacao_cadastral, data_inicio_atividade, cnae_fiscal_principal,
                                    porte_empresa, opcao_mei)
               VALUES ('99999999000100', '99999999', '02', '2015-01-01', '6201501', '05', 'N'),
                      ('88888888000100', '88888888', '02', '2026-06-01', '6201501', '01', 'S'),
                      ('77777777000100', '77777777', '02', '2025-09-01', '4711302', '01', 'S'),
                      ('66666666000100', '66666666', '02', '2025-09-01', '6201501', '01', 'S')"""
        )
        cur.execute(
            "INSERT INTO empresa_lista (cnpj, lista, via, registros) VALUES ('99999999000100', 'bndes_operacoes', 'cnpj', 1)"
        )
    conn.commit()
    return tmp_path


def test_auc():
    assert score.auc([(0.1, False), (0.9, True)]) == 1
    assert score.auc([(0.5, False), (0.5, True)]) == 0.5
    assert score.auc([(0.1, False)]) is None


def test_risco_e_lead(conn, ambiente):
    score.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT ano, eventos > 0, auc FROM modelo_validacao ORDER BY ano")
        validacao = cur.fetchall()
        assert [a for a, _, _ in validacao] == [2023, 2024, 2025]
        assert all(ev and auc > 0.8 for _, ev, auc in validacao), validacao
        cur.execute("SELECT count(*) FROM modelo_calibracao WHERE ano = 2025")
        assert cur.fetchone()[0] == 10
        # recém-aberta: no comércio, a faixa de idade que mais fecha; no software, quase nada
        cur.execute(
            "SELECT cnpj, faixa_idade, risco_12m FROM empresa_risco WHERE cnpj IN ('77777777000100', '66666666000100') ORDER BY 1"
        )
        (_, f62, r62), (_, f47, r47) = cur.fetchall()
        assert f47 == f62 == "0-1" and r47 > 5 * r62
        cur.execute("SELECT score, criterios FROM empresa_lead WHERE cnpj = '99999999000100'")
        assert cur.fetchone() == (40, ["porte_demais", "idade_2a", "lista_credito", "nao_mei"])
        cur.execute("SELECT count(*) FROM empresa_lead")
        assert cur.fetchone()[0] == 304  # só as ativas
        cur.execute("UPDATE lead_peso SET pontos = 20 WHERE criterio = 'lista_credito'")
    conn.commit()
    score.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT score FROM empresa_lead WHERE cnpj = '99999999000100'")
        assert cur.fetchone()[0] == 50
    assert "AUC" in (config.RELATORIOS / "score.md").read_text(encoding="utf-8")
