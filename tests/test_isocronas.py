"""Rede de caminhada nodada e isócronas a pé e de ônibus, com GTFS sintético."""

import datetime
import os
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from etl import config, db, isocronas
from etl.fontes import osm_vias

LON0, LAT0 = -49.2700, -25.4300
P = 0.001  # ~100 m


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    linhas, tipos = [], []
    for j in range(5):  # grade 5 x 5: linhas inteiras que só se cruzam (o ETL precisa nodar)
        linhas.append(LineString([(LON0, LAT0 + j * P), (LON0 + 4 * P, LAT0 + j * P)]))
        linhas.append(LineString([(LON0 + j * P, LAT0), (LON0 + j * P, LAT0 + 4 * P)]))
        tipos += ["residential", "residential"]
    linhas.append(LineString([(LON0 - P, LAT0 - P), (LON0 + 5 * P, LAT0 + 5 * P)]))  # autoestrada: fora
    tipos.append("motorway")
    linhas.append(LineString([(LON0 + 20 * P, LAT0), (LON0 + 21 * P, LAT0)]))  # trecho solto
    tipos.append("footway")
    arquivo = tmp_path / "vias.gpkg"
    gpd.GeoDataFrame({"highway": tipos}, geometry=linhas, crs=4326).to_file(arquivo, engine="pyogrio")

    gtfs = tmp_path / "gtfs.zip"
    with zipfile.ZipFile(gtfs, "w") as z:
        z.writestr(
            "stops.txt",
            f"stop_id,stop_name,stop_lat,stop_lon\nS1,a,{LAT0},{LON0}\nS2,b,{LAT0 + 4 * P},{LON0 + 4 * P}\n"
            f"S3,c,{LAT0},{LON0 + 4 * P}\n",
        )
        z.writestr("trips.txt", "route_id,service_id,trip_id\nR1,U,T1\nR2,DOM,T2\n")
        z.writestr(
            "stop_times.txt",
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T1,08:01:00,08:01:00,S1,1\nT1,08:03:00,08:03:00,S2,2\n"
            "T2,08:01:00,08:01:00,S1,1\nT2,08:02:00,08:02:00,S3,2\n",
        )
        z.writestr(
            "calendar.txt",
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "U,1,1,1,1,1,0,0,20260101,20261231\nDOM,0,0,0,0,0,0,1,20260101,20261231\n",
        )
    return arquivo, gtfs


def contem(conn, iso_id, lon, lat) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) FROM isocrona WHERE id = %s",
            (lon, lat, iso_id),
        )
        return cur.fetchone()[0]


def test_rede_e_isocronas(conn, ambiente):
    arquivo, gtfs = ambiente
    osm_vias.main(["--arquivo", str(arquivo)])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(*) FILTER (WHERE principal) FROM via_no")
        assert cur.fetchone() == (27, 25)
        cur.execute("SELECT count(*), round(sum(comprimento_m)) FROM via_aresta WHERE tipo = 'residential'")
        n, total = cur.fetchone()
        assert n == 40 and 4100 < total < 4300

    quinta = datetime.datetime(2026, 10, 8, 8, 0)
    a_pe = isocronas.calcular(conn, LAT0, LON0, [2, 5], "pe", quinta)
    onibus = isocronas.calcular(conn, LAT0, LON0, [5], "onibus", quinta, gtfs=gtfs)
    conn.commit()
    assert contem(conn, a_pe[0], LON0 + 0.5 * P, LAT0)
    assert not contem(conn, a_pe[0], LON0 + 2.5 * P, LAT0)
    assert not contem(conn, a_pe[1], LON0 + 4 * P, LAT0 + 3.5 * P)
    assert contem(conn, onibus[0], LON0 + 4 * P, LAT0 + 3.5 * P)  # desceu em S2 às 08:03 e andou 2 min
    assert not contem(conn, onibus[0], LON0 + 4 * P, LAT0)  # T2 só roda no domingo

    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS empresa_perfil (cnpj VARCHAR(14) PRIMARY KEY, tipo_ponto TEXT, domiciliacao BOOLEAN)"
        )
        cur.execute(
            "INSERT INTO empresa (cnpj, cnpj_basico, situacao_cadastral, cnae_fiscal_principal) VALUES ('1', '1', '02', '4771701')"
        )
        cur.execute(
            """INSERT INTO empresa_geo (cnpj, geo_precisao, geom)
               VALUES ('1', 'endereco', ST_SetSRID(ST_MakePoint(%s, %s), 4326))""",
            (LON0 + 0.5 * P, LAT0),
        )
    db.executar_sql(conn, "40_m2.sql")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT divisao, ativos_area FROM raio_x_area((SELECT geom FROM isocrona WHERE id = %s))", (a_pe[0],)
        )
        assert cur.fetchall() == [("47", 1)]


def test_isocronas_cli(conn, ambiente, capsys):
    arquivo, _ = ambiente
    osm_vias.main(["--arquivo", str(arquivo)])
    ids = isocronas.main(["--lat", str(LAT0), "--lon", str(LON0), "--minutos", "3"])
    assert len(ids) == 1 and "3 min" in capsys.readouterr().out
