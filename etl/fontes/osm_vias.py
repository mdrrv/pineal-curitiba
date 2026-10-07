"""Rede de caminhada para as isócronas: vias do OpenStreetMap (ou eixos de logradouro do IPPUC).

Uso:
    python -m etl.fontes.osm_vias [--arquivo sul-latest.osm.pbf | eixos.shp | eixos.gpkg]

Sem --arquivo, usa o que estiver em dados/bruto/osm_vias/ ou baixa o recorte do Sul do Geofabrik (url do
catálogo, ~350 MB). Do .osm.pbf lê a camada lines só no retângulo da cidade (bairros ou setores), sem vias
onde não se anda (autoestrada, canaleta exclusiva, obra, foot=no). Qualquer outro arquivo de linhas também
serve (eixos do IPPUC), sem esse filtro.

As linhas são nodadas no PostGIS (cruzamento vira nó; viaduto também, o que para caminhada é aceitável).
Grava via_no (com o componente principal marcado) e via_aresta.
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
from psycopg2.extras import execute_values

from etl import baixar, config, db, geo

log = logging.getLogger("osm_vias")
FONTE = "osm_vias"
EXCLUIR = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "construction",
    "proposed",
    "raceway",
    "busway",
    "bus_guideway",
    "abandoned",
    "platform",
}

NODAR = """
    CREATE TEMP TABLE _seg ON COMMIT DROP AS
    SELECT (ST_Dump(ST_Node(ST_Collect(geom)))).geom AS geom FROM _bruta;
    DELETE FROM _seg WHERE ST_Length(geom) = 0;
    ALTER TABLE _seg ADD COLUMN tipo TEXT;
    UPDATE _seg s SET tipo = (SELECT b.tipo FROM _bruta b WHERE ST_DWithin(b.geom, ST_LineInterpolatePoint(s.geom, 0.5), 1e-6)
                              ORDER BY b.tipo NULLS LAST LIMIT 1);

    CREATE TEMP TABLE _pt ON COMMIT DROP AS
    SELECT (row_number() OVER (ORDER BY chave))::INT AS id, chave, geom FROM (
        SELECT DISTINCT ON (chave) chave, geom FROM (
            SELECT round(ST_X(p)::NUMERIC, 7) || ' ' || round(ST_Y(p)::NUMERIC, 7) AS chave, p AS geom
            FROM (SELECT ST_StartPoint(geom) AS p FROM _seg UNION ALL SELECT ST_EndPoint(geom) FROM _seg) x
        ) y ORDER BY chave
    ) z;
    CREATE INDEX ON _pt (chave);

    TRUNCATE via_aresta, via_no;
    INSERT INTO via_no (id, geom) SELECT id, geom FROM _pt;

    INSERT INTO via_aresta (id, u, v, comprimento_m, tipo, geom)
    SELECT row_number() OVER (), a.id, b.id, ST_Length(s.geom::geography), s.tipo, s.geom
    FROM _seg s
    JOIN _pt a ON a.chave = round(ST_X(ST_StartPoint(s.geom))::NUMERIC, 7) || ' ' || round(ST_Y(ST_StartPoint(s.geom))::NUMERIC, 7)
    JOIN _pt b ON b.chave = round(ST_X(ST_EndPoint(s.geom))::NUMERIC, 7) || ' ' || round(ST_Y(ST_EndPoint(s.geom))::NUMERIC, 7)
    WHERE a.id <> b.id;
    DROP TABLE _seg, _pt, _bruta;
"""


def obter_arquivo(arquivo: str | None) -> Path:
    if arquivo:
        return Path(arquivo)
    local = baixar.arquivo_local(FONTE, r"\.(pbf|shp|gpkg|zip|geojson)$")
    if local:
        return local
    return baixar.baixar(config.fonte(FONTE)["url"], FONTE)


def retangulo(conn) -> tuple[float, float, float, float] | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ST_XMin(e) - 0.01, ST_YMin(e) - 0.01, ST_XMax(e) + 0.01, ST_YMax(e) + 0.01
            FROM (SELECT coalesce((SELECT ST_Extent(geom) FROM bairro), (SELECT ST_Extent(geom) FROM setor)) AS e) x
        """)
        r = cur.fetchone()
    return None if r[0] is None else tuple(r)


def ler_linhas(caminho: Path, bbox) -> gpd.GeoDataFrame:
    if caminho.name.lower().endswith(".pbf"):
        gdf = gpd.read_file(caminho, layer="lines", bbox=bbox, engine="pyogrio")
    else:
        gdf = geo.ler(caminho, crs_padrao=31982)
        if bbox:
            gdf = gdf.cx[bbox[0] : bbox[2], bbox[1] : bbox[3]]
    if "highway" in gdf.columns:
        gdf = gdf[gdf["highway"].notna() & ~gdf["highway"].isin(EXCLUIR)]
        if "other_tags" in gdf.columns:
            gdf = gdf[~gdf["other_tags"].fillna("").str.contains('"foot"=>"no"', regex=False)]
    gdf = gdf.explode(index_parts=False)
    return gdf[gdf.geometry.geom_type == "LineString"]


def marcar_principal(conn) -> tuple[int, int]:
    """Componente conexo com mais nós: só ele serve de partida (evita começar num trecho solto)."""
    with conn.cursor() as cur:
        cur.execute("SELECT u, v FROM via_aresta")
        pai: dict[int, int] = {}

        def raiz(x):
            while pai.setdefault(x, x) != x:
                pai[x] = pai[pai[x]]
                x = pai[x]
            return x

        for u, v in cur.fetchall():
            ru, rv = raiz(u), raiz(v)
            if ru != rv:
                pai[ru] = rv
        tamanho: dict[int, int] = {}
        for n in list(pai):
            r = raiz(n)
            tamanho[r] = tamanho.get(r, 0) + 1
        if not tamanho:
            return 0, 0
        maior = max(tamanho, key=lambda r: (tamanho[r], -r))
        cur.execute("UPDATE via_no SET principal = false")
        execute_values(
            cur,
            "UPDATE via_no n SET principal = true FROM (VALUES %s) x(id) WHERE n.id = x.id",
            [(n,) for n in pai if raiz(n) == maior],
            page_size=5000,
        )
    return tamanho[maior], len(tamanho)


def carregar(conn, caminho: Path) -> tuple[int, int]:
    gdf = ler_linhas(caminho, retangulo(conn))
    tipos = gdf["highway"] if "highway" in gdf.columns else [None] * len(gdf)
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE _bruta (tipo TEXT, geom geometry(LineString, 4326)) ON COMMIT DROP")
        execute_values(
            cur,
            "INSERT INTO _bruta (tipo, geom) VALUES %s",
            [(t, g.wkb) for t, g in zip(tipos, gdf.geometry, strict=True)],
            template="(%s, ST_SetSRID(ST_Force2D(ST_GeomFromWKB(%s)), 4326))",
            page_size=2000,
        )
        log.info("%d linhas lidas; nodando", len(gdf))
        cur.execute(NODAR)
        cur.execute("ANALYZE via_no; ANALYZE via_aresta")
        cur.execute("SELECT (SELECT count(*) FROM via_no), (SELECT count(*) FROM via_aresta)")
        return cur.fetchone()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo")
    args = ap.parse_args(argv)
    with db.etapa("vias"):
        caminho = obter_arquivo(args.arquivo)
        with db.conectar() as conn:
            db.criar_schema(conn)
            nos, arestas = carregar(conn, caminho)
            principal, componentes = marcar_principal(conn)
            db.registrar(conn, FONTE, str(caminho), caminho.name, baixar.sha256(caminho), arestas, nos=nos)
    print(f"rede: {nos} nós, {arestas} arestas; componente principal com {principal} nós ({componentes} componentes)")


if __name__ == "__main__":
    main()
