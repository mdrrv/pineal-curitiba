"""Edificações do Overture Maps agregadas por hexágono H3 res 9 (proxy de densidade construída).

Uso:
    python -m etl.fontes.overture_edificacoes [--release AAAA-MM-DD.N] [--arquivo edificacoes.parquet]

Lê direto do bucket público do Overture (s3://overturemaps-us-west-2) com DuckDB, filtrando pela
caixa do município (extensão de setor ou bairro já carregados). Sem --release, descobre a mais recente
listando o bucket; se a listagem falhar, usa `release` do catalogo.yaml. --arquivo aceita um GeoParquet
já baixado (colunas geometry, height, num_floors), para rodar sem internet.

Grava edificacao_h3: edificações, área de projeção, área construída estimada e altura média por hexágono.
Área construída = projeção x andares; sem andares, usa altura / 3 m; sem nenhum dos dois, 1 andar.
Licença dos dados: ODbL (atribuição ao Overture Maps Foundation e OpenStreetMap).
"""

import argparse
import logging
import re
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
import requests
from psycopg2.extras import execute_values
from shapely import wkb

from etl import baixar, config, db

log = logging.getLogger("overture_edificacoes")
FONTE = "overture_edificacoes"
BUCKET = "https://overturemaps-us-west-2.s3.amazonaws.com"
CAIXA_PADRAO = (-49.39, -25.65, -49.18, -25.34)  # Curitiba, se setor e bairro ainda não foram carregados

DDL = """
    CREATE TABLE IF NOT EXISTS edificacao_h3 (
        h3_9 TEXT PRIMARY KEY,
        edificacoes INT,
        area_projecao_m2 NUMERIC(14, 1),
        area_construida_m2 NUMERIC(14, 1),
        altura_media_m NUMERIC(6, 1)
    )
"""


def release_mais_recente() -> str:
    r = requests.get(
        BUCKET, params={"list-type": "2", "prefix": "release/", "delimiter": "/"}, headers=baixar.UA, timeout=60
    )
    r.raise_for_status()
    releases = re.findall(r"<Prefix>release/([^/<]+)/</Prefix>", r.text)
    if not releases:
        raise ValueError("nenhuma release na listagem do bucket do Overture")
    return max(releases)


def caixa(conn) -> tuple[float, float, float, float]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)
            FROM (SELECT coalesce((SELECT ST_Extent(geom) FROM setor), (SELECT ST_Extent(geom) FROM bairro)) AS e) x
        """)
        c = cur.fetchone()
    return c if c and c[0] is not None else CAIXA_PADRAO


def baixar_overture(release: str, bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    import duckdb

    xmin, ymin, xmax, ymax = bbox
    con = duckdb.connect()
    for ext in ("spatial", "httpfs"):
        con.install_extension(ext)
        con.load_extension(ext)
    con.execute("SET s3_region = 'us-west-2'")
    caminho = f"s3://overturemaps-us-west-2/release/{release}/theme=buildings/type=building/*"
    log.info("lendo edificações do Overture %s na caixa %s", release, bbox)
    df = con.execute(
        f"""
        SELECT ST_AsWKB(geometry) AS geom, height, num_floors
        FROM read_parquet('{caminho}', hive_partitioning = 1)
        WHERE bbox.xmin >= ? AND bbox.xmax <= ? AND bbox.ymin >= ? AND bbox.ymax <= ?
        """,
        [xmin, xmax, ymin, ymax],
    ).fetchdf()
    geoms = [wkb.loads(bytes(g)) for g in df.pop("geom")]
    return gpd.GeoDataFrame(df, geometry=gpd.GeoSeries(geoms, crs=4326), crs=4326)


def agregar(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Uma linha por hexágono H3 res 9, a partir de polígonos de edificação com height e num_floors."""
    if gdf.empty:
        return pd.DataFrame(columns=["h3_9", "edificacoes", "area_projecao_m2", "area_construida_m2", "altura_media_m"])
    area = gdf.to_crs(31982).area  # SIRGAS 2000 / UTM 22S, em metros
    andares = gdf["num_floors"].where(gdf["num_floors"].notna() & (gdf["num_floors"] > 0))
    andares = andares.fillna((gdf["height"] / 3).clip(lower=1)).fillna(1)
    centro = gdf.geometry.representative_point()
    df = pd.DataFrame(
        {
            "h3_9": [h3.latlng_to_cell(p.y, p.x, 9) for p in centro],
            "area": area.values,
            "construida": (area * andares).values,
            "altura": gdf["height"].values,
        }
    )
    g = df.groupby("h3_9").agg(
        edificacoes=("area", "size"),
        area_projecao_m2=("area", "sum"),
        area_construida_m2=("construida", "sum"),
        altura_media_m=("altura", "mean"),
    )
    return g.round(1).reset_index()


def gravar(conn, agregado: pd.DataFrame) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("TRUNCATE edificacao_h3")
        linhas = [
            (
                r.h3_9,
                int(r.edificacoes),
                float(r.area_projecao_m2),
                float(r.area_construida_m2),
                None if pd.isna(r.altura_media_m) else float(r.altura_media_m),
            )
            for r in agregado.itertuples()
        ]
        execute_values(cur, "INSERT INTO edificacao_h3 VALUES %s", linhas)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release")
    ap.add_argument("--arquivo", help="GeoParquet já baixado")
    args = ap.parse_args(argv)
    with db.etapa("edificacoes"), db.conectar() as conn:
        db.criar_schema(conn)
        if args.arquivo:
            gdf, origem = gpd.read_parquet(args.arquivo), args.arquivo
        else:
            release = args.release
            if not release:
                try:
                    release = release_mais_recente()
                except (requests.RequestException, ValueError) as e:
                    release = config.fonte(FONTE).get("release")
                    if not release:
                        raise SystemExit(
                            f"não listei as releases do Overture ({e}): informe --release ou `release` no catálogo"
                        ) from e
                    log.warning("não listei as releases do Overture (%s); usando %s do catálogo", e, release)
            gdf, origem = baixar_overture(release, caixa(conn)), f"overture {release}"
            destino = baixar.pasta(FONTE) / f"edificacoes_{release}.parquet"
            gdf.to_parquet(destino)
            log.info("cópia local em %s", destino)
        agregado = agregar(gdf)
        gravar(conn, agregado)
        db.registrar(
            conn,
            FONTE,
            origem,
            Path(args.arquivo).name if args.arquivo else None,
            linhas=len(agregado),
            edificacoes=len(gdf),
        )
    log.info("%d edificações em %d hexágonos", len(gdf), len(agregado))


if __name__ == "__main__":
    main()
