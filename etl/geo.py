"""Leitura de camadas vetoriais (shp, zip, gpkg, geojson) e gravação de polígonos no PostGIS."""
import json
import logging
from pathlib import Path

import geopandas as gpd
import pyogrio
from psycopg2.extras import execute_values

log = logging.getLogger(__name__)


def caminho_ogr(arquivo: Path) -> str:
    return f"zip://{arquivo}" if arquivo.suffix.lower() == ".zip" else str(arquivo)


def colunas(arquivo: Path) -> list[str]:
    return list(pyogrio.read_info(caminho_ogr(arquivo))["fields"])


def achar_coluna(cols: list[str], candidatos: list[str]) -> str | None:
    por_maiuscula = {c.upper(): c for c in cols}
    for c in candidatos:
        if c.upper() in por_maiuscula:
            return por_maiuscula[c.upper()]
    return None


def ler(arquivo: Path, crs_padrao: int | None = None, where: str | None = None) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(caminho_ogr(arquivo), where=where, engine="pyogrio")
    if gdf.crs is None:
        if crs_padrao is None:
            raise ValueError(f"{arquivo.name} não tem CRS (.prj). Informe crs_padrao no catalogo.yaml")
        log.warning("%s sem CRS: assumindo EPSG:%s", arquivo.name, crs_padrao)
        gdf = gdf.set_crs(crs_padrao)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    return gdf.to_crs(4326)


def _atributos(linha: dict) -> str:
    return json.dumps({k: (None if v != v else v) for k, v in linha.items()}, ensure_ascii=False, default=str)


def gravar_poligonos(conn, tabela: str, gdf: gpd.GeoDataFrame, campo_nome: str, campo_codigo: str | None) -> int:
    """Substitui o conteúdo de <tabela> (bairro, regional, zoneamento)."""
    attrs = gdf.drop(columns=gdf.geometry.name)
    linhas = [
        (None if campo_codigo is None else _txt(a[campo_codigo]), _txt(a[campo_nome]), _atributos(a), g.wkb)
        for a, g in zip(attrs.to_dict("records"), gdf.geometry)
    ]
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {tabela}")
        execute_values(
            cur,
            f"INSERT INTO {tabela} (codigo, nome, atributos, geom) VALUES %s",
            linhas,
            template="(%s, %s, %s::jsonb, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromWKB(%s, 4326)), 3)))",
            page_size=500,
        )
    return len(linhas)


def _txt(v) -> str | None:
    if v is None or v != v:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip() or None
