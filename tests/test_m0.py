"""M0 de ponta a ponta com arquivos sintéticos nos formatos das fontes reais."""

import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import box

from etl import config, m0

LON0, LAT0 = -49.2700, -25.4300


@pytest.fixture
def ambiente(conn, tmp_path, monkeypatch):
    dsn = conn.dsn
    monkeypatch.setenv("PINEAL_DSN", dsn)
    monkeypatch.setenv("RFB_DSN", dsn)
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    bruto = tmp_path / "bruto"

    # setores: zip de shapefile da UF, com um setor de outro município
    pasta = tmp_path / "shp"
    pasta.mkdir()
    gpd.GeoDataFrame(
        {
            "CD_SETOR": ["410690205000001P", "411370005000001P"],
            "CD_MUN": ["4106902", "4113700"],
            "NM_MUN": ["Curitiba", "Londrina"],
        },
        geometry=[box(LON0 - 0.01, LAT0 - 0.01, LON0 + 0.01, LAT0 + 0.01), box(-51.2, -23.4, -51.1, -23.3)],
        crs=4674,
    ).to_file(pasta / "PR_setores_CD2022.shp")
    (bruto / "ibge_setores").mkdir(parents=True)
    with zipfile.ZipFile(bruto / "ibge_setores" / "PR_setores_CD2022.zip", "w") as z:
        for p in pasta.glob("PR_setores_CD2022.*"):
            z.write(p, p.name)

    # IPPUC: bairro em UTM sem .prj, regional em geojson, zoneamento em gpkg
    (bruto / "ippuc").mkdir()
    caixa = gpd.GeoSeries([box(LON0 - 0.01, LAT0 - 0.01, LON0 + 0.01, LAT0 + 0.01)], crs=4326)
    gpd.GeoDataFrame({"NOME": ["CENTRO"], "CODIGO": [1.0]}, geometry=caixa.to_crs(31982).values).to_file(
        bruto / "ippuc" / "DIVISA_DE_BAIRROS.shp"
    )
    (bruto / "ippuc" / "DIVISA_DE_BAIRROS.prj").unlink()
    gpd.GeoDataFrame({"NOME_REGIO": ["MATRIZ"]}, geometry=caixa.values, crs=4326).to_file(
        bruto / "ippuc" / "regionais.geojson", driver="GeoJSON"
    )
    gpd.GeoDataFrame({"SG_ZONA": ["ZC"], "NM_ZONA": ["ZONA CENTRAL"]}, geometry=caixa.values, crs=4326).to_file(
        bruto / "ippuc" / "zoneamento.gpkg", driver="GPKG"
    )

    # CNEFE: zip com csv ; e decimal com vírgula
    linhas = [
        "COD_UNICO_ENDERECO;COD_UF;COD_MUNICIPIO;COD_SETOR;CEP;NOM_TIPO_SEGLOGR;NOM_TITULO_SEGLOGR;"
        "NOM_SEGLOGR;NUM_ENDERECO;LATITUDE;LONGITUDE;NV_GEO_COORD;COD_ESPECIE;DSC_ESTABELECIMENTO"
    ]
    for n in range(100, 120):
        lon = str(LON0 + (n - 100) * 0.00005).replace(".", ",")
        linhas.append(
            f"{n};41;4106902;410690205000001P;80060140;RUA;DOUTOR;FAIVRE;{n};{str(LAT0).replace('.', ',')};{lon};1;8;"
        )
    (bruto / "ibge_cnefe").mkdir()
    with zipfile.ZipFile(bruto / "ibge_cnefe" / "4106902_CURITIBA.zip", "w") as z:
        z.writestr("4106902_CURITIBA.csv", "\n".join(linhas).encode("utf-8"))

    # banco RFB falso
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS cwb CASCADE")  # resto de rodadas antigas; o teste usa outro schema
        cur.execute("""
            DROP SCHEMA IF EXISTS dados_rfb CASCADE;
            CREATE SCHEMA dados_rfb;
            CREATE TABLE dados_rfb.cnpj_consolidado (
                cnpj VARCHAR(14), cnpj_basico VARCHAR(8), razao_social TEXT, nome_fantasia TEXT, situacao_cadastral VARCHAR(2),
                data_situacao_cadastral VARCHAR(8), data_inicio_atividade VARCHAR(8), cnae_fiscal_principal VARCHAR(7),
                natureza_juridica VARCHAR(4), capital_social NUMERIC(18,2), porte_empresa VARCHAR(2),
                opcao_pelo_simples VARCHAR(1), opcao_mei VARCHAR(1), identificador_mf VARCHAR(1), logradouro TEXT,
                numero TEXT, complemento TEXT, bairro TEXT, cep VARCHAR(8), uf VARCHAR(2), municipio VARCHAR(4),
                nome_municipio TEXT);
            INSERT INTO dados_rfb.cnpj_consolidado (cnpj, cnpj_basico, razao_social, situacao_cadastral,
                data_inicio_atividade, data_situacao_cadastral, natureza_juridica, opcao_mei, logradouro, numero,
                cep, uf, municipio, nome_municipio) VALUES
                ('11111111000101', '11111111', 'A, "LTDA"', '02', '20190110', '20190110', '2062', 'N', 'R DR FAIVRE', '105', '80060140', 'PR', '7535', 'CURITIBA'),
                ('11111111000102', '11111111', 'B', '08', '20150101', '20230231', '2062', 'N', 'RUA FAIVRE', 'SN', '80060140', 'PR', '7535', 'CURITIBA'),
                ('11111111000103', '11111111', 'C', '02', '00000000', '', '2062', 'N', 'R NADA', '1', '00000000', 'PR', '7535', 'CURITIBA'),
                ('33333333000101', '33333333', 'JOAO DA SILVA 12345678901', '02', '20200115', '20200115', '2135', 'S', 'R DR FAIVRE', '107', '80060140', 'PR', '7535', 'CURITIBA'),
                ('22222222000101', '22222222', 'D', '02', '20200101', '20200101', '2062', 'N', 'R DR FAIVRE', '105', '86000000', 'PR', '5269', 'LONDRINA');
        """)
    conn.commit()
    yield tmp_path
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS dados_rfb CASCADE")
    conn.commit()


def test_m0_completo(conn, ambiente):
    m0.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM setor")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT nome, codigo, round(ST_X(ST_Centroid(geom))::numeric, 3) FROM bairro")
        assert cur.fetchone() == ("CENTRO", "1", round(__import__("decimal").Decimal(LON0), 3))
        cur.execute("SELECT nome FROM regional UNION ALL SELECT codigo FROM zoneamento")
        assert [r[0] for r in cur.fetchall()] == ["MATRIZ", "ZC"]
        cur.execute("SELECT count(*), min(logr_chave) FROM cnefe")
        assert cur.fetchone() == (20, "FAIVRE")
        cur.execute(
            "SELECT cnpj, geo_precisao, cd_setor, bairro, regional, zona, h3_9 IS NOT NULL FROM empresa_geo ORDER BY cnpj"
        )
        assert cur.fetchall() == [
            ("11111111000101", "endereco", "410690205000001P", "CENTRO", "MATRIZ", "ZC", True),
            ("11111111000102", "logradouro", "410690205000001P", "CENTRO", "MATRIZ", "ZC", True),
            ("11111111000103", "nao_localizado", None, None, None, None, False),
            ("33333333000101", "endereco", "410690205000001P", "CENTRO", "MATRIZ", "ZC", True),
        ]
        cur.execute("""SELECT cnpj, razao_social, pessoa_fisica, cpf_mascarado, data_inicio_atividade,
                              data_situacao_cadastral FROM empresa ORDER BY cnpj""")
        d = __import__("datetime").date
        assert cur.fetchall() == [
            ("11111111000101", 'A, "LTDA"', False, None, d(2019, 1, 10), d(2019, 1, 10)),
            ("11111111000102", "B", False, None, d(2015, 1, 1), None),  # 31/02 inválida vira nula
            ("11111111000103", "C", False, None, None, None),
            ("33333333000101", None, True, "***.456.789-**", d(2020, 1, 15), d(2020, 1, 15)),
        ]
        cur.execute(
            "SELECT count(*) FROM empresa WHERE razao_social LIKE '%%12345678901%%' OR nome_fantasia LIKE '%%JOAO%%'"
        )
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT fonte FROM execucao WHERE tipo = 'carga' ORDER BY id")
        assert [r[0] for r in cur.fetchall()] == [
            "ibge_setores",
            "ippuc_bairro",
            "ippuc_regional",
            "ippuc_zoneamento",
            "ibge_cnefe",
            "rfb_cnpj",
            "geocodificacao",
            "territorio",
        ]
        cur.execute("SELECT fonte, status FROM execucao WHERE tipo = 'etapa' ORDER BY id")
        assert cur.fetchall() == [
            (e, "ok") for e in ["schema", "setores", "ippuc", "cnefe", "cnpj", "geocodificar", "territorio"]
        ]
        cur.execute("SELECT count(DISTINCT run_id), count(*) FILTER (WHERE run_id IS NULL) FROM execucao")
        assert cur.fetchone() == (1, 0)
        cur.execute("SELECT count(*) FROM pg_namespace WHERE nspname = 'cwb'")
        assert cur.fetchone()[0] == 0  # tudo foi para o schema configurado
    assert (ambiente / "relatorios" / "geocodificacao.md").exists()
    assert (ambiente / "relatorios" / "territorio.md").exists()

    # rodar de novo não duplica nada
    conn.commit()
    m0.main(["--pular", "setores"])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT count(*) FROM empresa), (SELECT count(*) FROM bairro), (SELECT count(*) FROM cnefe)"
        )
        assert cur.fetchone() == (4, 1, 20)


def test_etapa_com_erro_fica_registrada(conn, ambiente):
    (ambiente / "bruto" / "ibge_cnefe" / "4106902_CURITIBA.zip").write_bytes(b"isto nao e um zip")
    with pytest.raises(zipfile.BadZipFile):
        m0.main(["--so", "cnefe"])
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT fonte, status, erro IS NOT NULL FROM execucao WHERE tipo = 'etapa'")
        assert cur.fetchall() == [("cnefe", "erro", True)]
