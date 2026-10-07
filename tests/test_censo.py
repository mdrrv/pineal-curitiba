"""Censo 2022 por setor: carga dos agregados, distribuição pelos domicílios do CNEFE, raio e espaço livre."""

import os
import zipfile
from decimal import Decimal

import pytest

from etl import config, db
from etl.fontes import ibge_censo_setor

LON0, LAT0 = -49.2700, -25.4300
SETOR_A, SETOR_B = "410690205000001", "410690205000002"


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    envelope = "ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
    with conn.cursor() as cur:
        for cd, x0 in [(SETOR_A, 0), (SETOR_B, 0.001)]:
            cur.execute(
                f"INSERT INTO setor (cd_setor, geom) VALUES (%s, {envelope})",
                (cd, LON0 + x0, LAT0, LON0 + x0 + 0.001, LAT0 + 0.001),
            )
        for nome, x0 in [("Centro", -0.001), ("Batel", 0.001)]:
            cur.execute(
                f"INSERT INTO bairro (codigo, nome, geom) VALUES (%s, %s, {envelope})",
                (nome[0], nome, LON0 + x0, LAT0 - 0.001, LON0 + x0 + 0.002, LAT0 + 0.002),
            )
        # setor A: 4 domicílios e 1 estabelecimento no CNEFE (código com o "P" do arquivo); setor B: nenhum
        for i in range(5):
            cur.execute(
                """INSERT INTO cnefe (cod_unico, cd_setor, especie, geom)
                   VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))""",
                (f"d{i}", SETOR_A + "P", 1 if i < 4 else 6, LON0 + 0.0002 * (i + 1), LAT0 + 0.0005),
            )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS empresa_perfil (cnpj VARCHAR(14) PRIMARY KEY, tipo_ponto TEXT, domiciliacao BOOLEAN)"
        )
        for cnpj, cnae, bairro, lon in [
            ("10000000000101", "4771701", "Centro", LON0 + 0.0005),
            ("10000000000202", "4771701", "Centro", LON0 + 0.0005),
            ("10000000000303", "9313100", "Batel", LON0 + 0.0015),
        ]:
            cur.execute(
                "INSERT INTO empresa (cnpj, cnpj_basico, situacao_cadastral, cnae_fiscal_principal) VALUES (%s, %s, '02', %s)",
                (cnpj, cnpj[:8], cnae),
            )
            cur.execute(
                """INSERT INTO empresa_geo (cnpj, geo_precisao, bairro, geom)
                   VALUES (%s, 'endereco', %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))""",
                (cnpj, bairro, lon, LAT0 + 0.0005),
            )
    conn.commit()
    pasta = tmp_path / "bruto" / "ibge_censo_setor"
    pasta.mkdir(parents=True)
    basico = (
        "CD_SETOR;SITUACAO;CD_MUN;NM_MUN;AREA_KM2;v0001;v0002;v0003;v0004;v0005;v0006;v0007\n"
        f"{SETOR_A}P;Urbana;4106902;Curitiba;0,0112;100;45;44;1;2,5;0;40\n"
        f"{SETOR_B}P;Urbana;4106902;Curitiba;0,0112;50;22;22;0;X;0;20\n"
        "411370005000001P;Urbana;4113700;Londrina;1;999;1;1;0;1;0;1\n"
    )
    with zipfile.ZipFile(pasta / "Agregados_por_setores_basico_BR_20250417.zip", "w") as z:
        z.writestr("Agregados_por_setores_basico_BR.csv", basico.encode("cp1252"))
    idades = ";".join(f"V0103{i}" for i in range(1, 10)) + ";V01040;V01041"
    (pasta / "Agregados_por_setores_demografia_BR.csv").write_text(
        f"CD_setor;V01007;V01008;{idades}\n{SETOR_A};48;52;10;10;10;5;5;10;10;10;10;10;10\n", encoding="utf-8"
    )
    (pasta / "Agregados_por_setores_renda_responsavel_BR.csv").write_text(
        f"CD_SETOR;V06001;V06004\n{SETOR_A};40;3000,50\n{SETOR_B};20;1000\n", encoding="utf-8"
    )
    return tmp_path


def test_censo(conn, ambiente):
    ibge_censo_setor.main([])
    with conn.cursor() as cur:
        cur.execute("""
            SELECT cd_setor, bairro, pessoas, domicilios_ocupados, moradores_por_domicilio, idade_0_14, idade_60_mais,
                   renda_media_responsavel, area_km2, densidade_km2, dependencia, envelhecimento, domicilios_cnefe
            FROM setor_demografia ORDER BY 1
        """)
        D = Decimal
        assert cur.fetchall() == [
            (
                SETOR_A,
                "Centro",
                D(100),
                D(40),
                D("2.5"),
                D(30),
                D(20),
                D("3000.50"),
                D("0.0112"),
                D("8928.6"),
                D("100.0"),
                D("66.7"),
                4,
            ),
            (SETOR_B, "Batel", D(50), D(20), None, None, None, D(1000), D("0.0112"), D("4464.3"), None, None, 0),
        ]
        cur.execute("SELECT count(*) FROM censo_setor_var WHERE cd_setor LIKE '4113700%%'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT sum(moradores), sum(domicilios) FROM demanda_h3")
        assert cur.fetchone() == (D(150), D(60))

        cur.execute("SELECT * FROM moradores_raio(%s, %s, 20)", (LAT0 + 0.0005, LON0 + 0.0005))
        assert cur.fetchone() == (D(50), D(20), D("3000.50"))
        cur.execute("SELECT * FROM moradores_raio(%s, %s, 1000)", (LAT0 + 0.0005, LON0 + 0.0005))
        assert cur.fetchone() == (D(150), D(60), D("2333.67"))

        cur.execute(
            "SELECT bairro, classe, ativos, moradores, esperado, lacuna, indice FROM m2_espaco_livre ORDER BY 2, 1"
        )
        assert cur.fetchall() == [
            ("Batel", "47717", 0, D(50), D("0.7"), D("0.7"), D(0)),
            ("Centro", "47717", 2, D(100), D("1.3"), D("-0.7"), D(150)),
            ("Batel", "93131", 1, D(50), D("0.3"), D("-0.7"), D(300)),
            ("Centro", "93131", 0, D(100), D("0.7"), D("0.7"), D(0)),
        ]

    db.executar_sql(conn, "40_m2.sql")
    with conn.cursor() as cur:
        cur.execute(
            """SELECT divisao, ativos_raio, moradores_raio, por_mil_moradores_raio, por_mil_moradores_cidade,
                      indice_moradores FROM raio_x(%s, %s, 20)""",
            (LAT0 + 0.0005, LON0 + 0.0005),
        )
        assert cur.fetchall() == [("47", 2, Decimal(50), Decimal("40.00"), Decimal("13.33"), Decimal(300))]
    md = (config.RELATORIOS / "demanda.md").read_text(encoding="utf-8")
    assert "basico (2 setores)" in md and "demografia (1 setores)" in md
