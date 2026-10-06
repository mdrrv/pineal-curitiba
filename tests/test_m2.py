"""Enriquecimento, indicadores do M2, tabelas de apoio, cruzamentos, edificações e exportação."""

import datetime
import decimal
import os

import geopandas as gpd
import pytest
from shapely.geometry import box

from etl import db, enriquecer, exportar, indicadores, territorio
from etl.fontes import apoio, cnpj_recorte, mindata_cruzamentos, overture_edificacoes

LON0, LAT0 = -49.2700, -25.4300
HOJE = datetime.date.today()


def ponto(i):
    return LON0 + i * 0.0002, LAT0  # endereços a ~20 m um do outro


def endereco(cur, cep, numero, i, bairro):
    lon, lat = ponto(i)
    return dict(cep=cep, numero=numero, lon=lon, lat=lat, bairro=bairro)


def empresa(
    cur, cnpj, end, cnae, situacao="02", inicio="2020-01-01", fim=None, basico=None, mf="1", mei="N", zona=None
):
    cur.execute(
        """INSERT INTO empresa (cnpj, cnpj_basico, situacao_cadastral, data_inicio_atividade, data_situacao_cadastral,
                                cnae_fiscal_principal, identificador_mf, opcao_mei, logradouro, numero, cep)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'RUA DOUTOR FAIVRE', %s, %s)""",
        (cnpj, basico or cnpj[:8], situacao, inicio, fim, cnae, mf, mei, str(end["numero"]), end["cep"]),
    )
    cur.execute(
        """INSERT INTO empresa_geo (cnpj, cep, logr_chave, logr_completa, numero, geo_precisao, geom, bairro, zona)
           VALUES (%s, %s, 'FAIVRE', 'DOUTOR FAIVRE', %s, 'endereco', ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)""",
        (cnpj, end["cep"], end["numero"], end["lon"], end["lat"], end["bairro"], zona),
    )


def cnefe(cur, cod, end, especie):
    cur.execute(
        """INSERT INTO cnefe (cod_unico, cep, logr_chave, numero, especie, geom)
           VALUES (%s, %s, 'FAIVRE', %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))""",
        (cod, end["cep"], end["numero"], especie, end["lon"], end["lat"]),
    )


@pytest.fixture
def cenario(conn):
    with conn.cursor() as cur:
        a = endereco(cur, "80000001", 10, 0, "CENTRO")  # só estabelecimento no CNEFE
        b = endereco(cur, "80000002", 20, 1, "CENTRO")  # estabelecimento e domicílio
        c = endereco(cur, "80000003", 30, 2, "CENTRO")  # só domicílio
        d = endereco(cur, "80000004", 40, 3, "CENTRO")  # domiciliação: 20 CNPJs
        e = endereco(cur, "80000005", 50, 4, "BATEL")  # ponto vago
        f = endereco(cur, "80000006", 60, 5, "BATEL")
        cnefe(cur, "a", a, 6)
        cnefe(cur, "b1", b, 6)
        cnefe(cur, "b2", b, 1)
        cnefe(cur, "c", c, 1)
        empresa(cur, "11111111000101", a, "4711301", inicio="2015-01-01", mf="1")
        empresa(cur, "11111111000202", b, "4711301", basico="11111111", mf="2")
        empresa(cur, "22222222000101", c, "6201501", mei="S", zona="ZR1")
        for i in range(20):
            empresa(cur, f"3333333300{i:02d}01", d, "6920601", basico=f"3{i:07d}")
        empresa(
            cur,
            "44444444000101",
            e,
            "5611201",
            situacao="08",
            inicio="2015-01-01",
            fim=HOJE.replace(year=HOJE.year - 1),
        )
        empresa(cur, "44444444000202", e, "5611201", situacao="08", inicio="2016-01-01", fim="2016-06-01")
        empresa(cur, "55555555000101", f, "6201501")
        cur.execute(
            "INSERT INTO zona_regra VALUES ('ZR1', '62', true, 'geral'), ('ZR1', '6201', false, 'mais específica')"
        )
        cur.execute(f"""INSERT INTO bairro (codigo, nome, geom) VALUES
            ('1', 'CENTRO', ST_Multi(ST_MakeEnvelope({LON0 - 0.005}, {LAT0 - 0.005}, {LON0 + 0.0009}, {LAT0 + 0.005}, 4326))),
            ('2', 'BATEL', ST_Multi(ST_MakeEnvelope({LON0 + 0.0009}, {LAT0 - 0.005}, {LON0 + 0.006}, {LAT0 + 0.005}, 4326)))""")
    territorio.gravar_h3(conn)
    conn.commit()
    return conn


def test_enriquecimento(cenario):
    conn = cenario
    db.executar_sql(conn, "30_enriquecimento.sql")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cnpj, tipo_ponto, domiciliacao, ativos_da_raiz_na_cidade, matriz_na_cidade, filial FROM empresa_perfil"
        )
        p = {r[0]: r[1:] for r in cur.fetchall()}
        cur.execute("SELECT endereco_chave, cnpjs_total, cnpjs_ativos, vago FROM ponto_comercial ORDER BY 1")
        pontos = {r[0]: r[1:] for r in cur.fetchall()}
        cur.execute("SELECT cnpj, regra_prefixo, permitido FROM uso_zoneamento WHERE permitido IS NOT NULL")
        zona = cur.fetchall()
    assert p["11111111000101"] == ("comercial", False, 2, True, False)
    assert p["11111111000202"] == ("misto", False, 2, True, True)
    assert p["22222222000101"][:2] == ("residencial", False)
    assert p["33333333000001"][:2] == ("desconhecido", True)
    assert pontos["80000004|FAIVRE|40"] == (20, 20, False)
    assert pontos["80000005|FAIVRE|50"] == (2, 0, True)
    assert zona == [("22222222000101", "6201", False)]  # vale a regra de prefixo mais longo
    assert "Em endereço de domiciliação" in enriquecer.resumo(conn)


def test_indicadores(cenario):
    conn = cenario
    db.executar_sql(conn, "30_enriquecimento.sql")
    db.executar_sql(conn, "40_m2.sql")
    with conn.cursor() as cur:
        cur.execute("SELECT bairro, divisao, ativos, ql FROM m2_saturacao_bairro ORDER BY 1, 2")
        sat = cur.fetchall()
        cur.execute(
            "SELECT coorte, abertas, sobrevivencia_1a, sobrevivencia_5a FROM m2_sobrevivencia WHERE divisao IS NULL ORDER BY coorte"
        )
        sob = {r[0]: r[1:] for r in cur.fetchall()}
        cur.execute("SELECT sum(ativos) FROM m2_densidade_h3 WHERE divisao IS NULL")
        total_h3 = cur.fetchone()[0]
        cur.execute("SELECT divisao, ativos_raio, indice IS NOT NULL FROM raio_x(%s, %s, 250) ORDER BY 1", (LAT0, LON0))
        raio = cur.fetchall()
    D = decimal.Decimal
    # domiciliação (contabilidades) fica de fora: CENTRO tem 47, 47, 62; BATEL tem 62
    assert sat == [("BATEL", "62", 1, D("2.000")), ("CENTRO", "47", 2, D("1.333")), ("CENTRO", "62", 1, D("0.667"))]
    assert sob[2015][0] == 2 and sob[2015][1] == D("100.0") and sob[2015][2] == D("100.0")
    assert sob[2016] == (1, D("0.0"), D("0.0"))
    assert total_h3 == 4
    assert raio == [("47", 2, True), ("62", 2, True)]
    assert "Sobrevivência" in indicadores.resumo(conn)


def test_movimento_entre_competencias(cenario):
    conn = cenario
    cnpj_recorte.foto_mensal(conn, datetime.date(2026, 1, 1))
    with conn.cursor() as cur:
        cur.execute("UPDATE empresa SET situacao_cadastral = '08' WHERE cnpj = '11111111000101'")
        cur.execute("UPDATE empresa SET numero = '22' WHERE cnpj = '11111111000202'")
        cur.execute("UPDATE empresa SET situacao_cadastral = '02' WHERE cnpj = '44444444000202'")
        cur.execute("UPDATE empresa SET cnae_fiscal_principal = '6202300' WHERE cnpj = '55555555000101'")
        cur.execute("DELETE FROM empresa WHERE cnpj = '22222222000101'")
        cur.execute(
            "INSERT INTO empresa (cnpj, situacao_cadastral, cnae_fiscal_principal) VALUES ('66666666000101', '02', '4711301')"
        )
    cnpj_recorte.foto_mensal(conn, datetime.date(2026, 2, 1))
    db.executar_sql(conn, "30_enriquecimento.sql")
    db.executar_sql(conn, "40_m2.sql")
    with conn.cursor() as cur:
        cur.execute("SELECT cnpj, evento FROM m2_movimento ORDER BY cnpj, evento")
        assert cur.fetchall() == [
            ("11111111000101", "fechamento"),
            ("11111111000202", "mudanca_endereco"),
            ("22222222000101", "saiu_do_recorte"),
            ("44444444000202", "reativacao"),
            ("55555555000101", "mudanca_cnae"),
            ("66666666000101", "abertura"),
        ]
        cur.execute("SELECT DISTINCT competencia FROM m2_movimento")
        assert cur.fetchall() == [(datetime.date(2026, 2, 1),)]


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setenv("RFB_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr("etl.config.RELATORIOS", tmp_path / "relatorios")
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS dados_rfb CASCADE; CREATE SCHEMA dados_rfb")
    conn.commit()
    yield tmp_path
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS dados_rfb CASCADE")
    conn.commit()


class Resposta:
    def __init__(self, dados):
        self.dados = dados

    def raise_for_status(self):
        pass

    def json(self):
        return self.dados


def test_apoio_pela_api_do_ibge(conn, ambiente, monkeypatch):
    subclasse = {
        "id": "4711301",
        "descricao": "Comércio varejista ... hipermercados",
        "classe": {
            "id": "47113",
            "descricao": "Varejo com alimentos",
            "grupo": {
                "id": "471",
                "descricao": "Comércio varejista não especializado",
                "divisao": {
                    "id": "47",
                    "descricao": "Comércio varejista",
                    "secao": {"id": "G", "descricao": "Comércio"},
                },
            },
        },
    }
    monkeypatch.setattr(apoio.requests, "get", lambda *a, **k: Resposta([subclasse]))
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE dados_rfb.natju (codigo VARCHAR(4), descricao TEXT)")
        cur.execute("INSERT INTO dados_rfb.natju VALUES ('2062', 'Sociedade Empresária Limitada')")
    conn.commit()
    apoio.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT subclasse, classe, grupo, divisao, divisao_descricao, secao FROM cnae")
        assert cur.fetchall() == [("4711301", "47113", "471", "47", "Comércio varejista", "G")]
        cur.execute("SELECT * FROM natureza_juridica")
        assert cur.fetchall() == [("2062", "Sociedade Empresária Limitada")]
        cur.execute("SELECT descricao FROM porte WHERE codigo = '03'")
        assert cur.fetchone()[0] == "Empresa de pequeno porte"


def test_apoio_sem_api_usa_tabela_da_receita(conn, ambiente, monkeypatch):
    def falha(*a, **k):
        raise apoio.requests.ConnectionError("sem rede")

    monkeypatch.setattr(apoio.requests, "get", falha)
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE dados_rfb.cnae (codigo VARCHAR(7), descricao TEXT)")
        cur.execute("INSERT INTO dados_rfb.cnae VALUES ('6201501', 'Desenvolvimento de programas sob encomenda')")
    conn.commit()
    apoio.main([])  # dados_rfb.natju não existe: só avisa
    with conn.cursor() as cur:
        cur.execute("SELECT subclasse, descricao, divisao, divisao_descricao FROM cnae")
        assert cur.fetchall() == [("6201501", "Desenvolvimento de programas sob encomenda", "62", None)]


def test_cruzamentos(cenario, ambiente):
    conn = cenario
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE dados_rfb.pncp_contratos (cnpj_14 VARCHAR(14), valor_global NUMERIC, ano_contrato SMALLINT);
            INSERT INTO dados_rfb.pncp_contratos VALUES ('11111111000101', 100, 2024), ('11111111000101', 50, 2026),
                                                       ('99999999000101', 10, 2026);
            CREATE TABLE dados_rfb.pgfn_divida_ativa (cnpj_14 VARCHAR(14), valor_consolidado NUMERIC);
            INSERT INTO dados_rfb.pgfn_divida_ativa VALUES ('55555555000101', 1234.5);
            CREATE TABLE dados_rfb.sancoes_federais (cnpj_14 VARCHAR(14), ativo BOOLEAN);
            INSERT INTO dados_rfb.sancoes_federais VALUES ('55555555000101', true), ('55555555000101', false);
        """)
    conn.commit()
    mindata_cruzamentos.main([])  # sem tce_pr_contratos: pulado
    with conn.cursor() as cur:
        cur.execute("""SELECT cnpj, pncp_contratos, pncp_valor, pncp_ultimo_ano, tce_pr_contratos, pgfn_valor, sancoes_ativas
                       FROM empresa_sinais ORDER BY cnpj""")
        assert cur.fetchall() == [
            ("11111111000101", 2, decimal.Decimal("150.00"), 2026, None, None, None),
            ("55555555000101", None, None, None, None, decimal.Decimal("1234.50"), 1),
        ]


def test_edificacoes(conn, ambiente, monkeypatch):
    utm = gpd.GeoSeries([box(0, 0, 10, 10), box(20, 0, 30, 10), box(5000, 0, 5010, 10)], crs=31982)
    centro = gpd.GeoSeries.from_xy([LON0], [LAT0], crs=4326).to_crs(31982).iloc[0]
    utm = utm.translate(centro.x, centro.y)
    gdf = gpd.GeoDataFrame({"height": [None, 9.0, None], "num_floors": [2, None, None]}, geometry=utm).to_crs(4326)
    agregado = overture_edificacoes.agregar(gdf)
    assert sorted(agregado["edificacoes"]) == [1, 2]
    perto = agregado.sort_values("edificacoes").iloc[-1]
    assert round(perto["area_projecao_m2"]) == 200
    assert round(perto["area_construida_m2"]) == 500  # 100 m² x 2 andares + 100 m² x (9 m / 3)

    arquivo = ambiente / "edificacoes.parquet"
    gdf.to_parquet(arquivo)
    overture_edificacoes.main(["--arquivo", str(arquivo)])
    with conn.cursor() as cur:
        cur.execute("SELECT sum(edificacoes), count(*) FROM edificacao_h3")
        assert cur.fetchone() == (3, 2)


def test_release_do_overture(monkeypatch):
    class R:
        text = "<Prefix>release/2026-07-22.0/</Prefix><Prefix>release/2026-09-17.1/</Prefix>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(overture_edificacoes.requests, "get", lambda *a, **k: R())
    assert overture_edificacoes.release_mais_recente() == "2026-09-17.1"


def test_exportar_sem_dados_pessoais(cenario, ambiente):
    enriquecer.main([])
    indicadores.main([])
    pasta = ambiente / "exportar"
    exportar.main(["--pasta", str(pasta)])
    empresas = gpd.read_parquet(pasta / "empresas.parquet")
    assert len(empresas) == 26
    assert not {"razao_social", "nome_fantasia", "cpf_mascarado"} & set(empresas.columns)
    assert len(gpd.read_parquet(pasta / "densidade_h3.parquet")) > 0
    sat = gpd.read_parquet(pasta / "saturacao_bairro.parquet")
    assert set(sat["bairro"]) == {"CENTRO", "BATEL"} and sat.geometry.notna().all()
    assert gpd.read_parquet(pasta / "pontos_comerciais.parquet")["vago"].sum() == 1
    assert (ambiente / "relatorios" / "indicadores.md").exists()
