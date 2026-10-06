"""Exporta camadas em GeoParquet para conferir no mapa (QGIS, Kepler.gl, Lonboard num notebook).

Uso:
    python -m etl.exportar [--pasta dados/exportar]

Arquivos (sem nome, razão social ou CPF; só código de atividade, situação e território):
    empresas.parquet           pontos das empresas geocodificadas
    densidade_h3.parquet       hexágonos H3 res 9 com ativos por divisão (divisao vazia = total)
    saturacao_bairro.parquet   bairros com QL por divisão (formato longo: uma linha por bairro x divisão)
    pontos_comerciais.parquet  endereços com histórico de CNPJs, rotatividade e ponto vago
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from shapely import wkb
from shapely.geometry import Polygon

from etl import config, db

log = logging.getLogger("exportar")

CONSULTAS = {
    "empresas": """
        SELECT e.cnpj, e.cnae_fiscal_principal AS cnae, left(e.cnae_fiscal_principal, 2) AS divisao,
               e.situacao_cadastral, e.porte_empresa, e.opcao_mei, e.data_inicio_atividade,
               g.geo_precisao, g.bairro, g.regional, g.zona, g.cd_setor, g.h3_9,
               p.tipo_ponto, p.domiciliacao, ST_AsBinary(g.geom) AS geom
        FROM empresa e JOIN empresa_geo g USING (cnpj) LEFT JOIN empresa_perfil p USING (cnpj)
        WHERE g.geom IS NOT NULL
    """,
    "saturacao_bairro": """
        SELECT s.bairro, s.divisao, s.divisao_descricao, s.ativos, s.ql, ST_AsBinary(b.geom) AS geom
        FROM m2_saturacao_bairro s
        JOIN (SELECT DISTINCT ON (nome) nome, geom FROM bairro ORDER BY nome, ST_Area(geom) DESC) b ON b.nome = s.bairro
    """,
    "pontos_comerciais": """
        SELECT endereco_chave, tipo_ponto, cnpjs_total, cnpjs_ativos, cnpjs_encerrados, primeira_abertura,
               ultimo_encerramento, cnpjs_por_ano, vago, ST_AsBinary(geom) AS geom
        FROM ponto_comercial WHERE geom IS NOT NULL
    """,
}


def ler(conn, sql: str) -> gpd.GeoDataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    geoms = [wkb.loads(bytes(g)) if g is not None else None for g in df.pop("geom")] if len(df) else []
    return gpd.GeoDataFrame(df, geometry=gpd.GeoSeries(geoms, crs=4326), crs=4326)


def hexagonos(conn) -> gpd.GeoDataFrame:
    with conn.cursor() as cur:
        cur.execute("SELECT h3_9, divisao, ativos FROM m2_densidade_h3")
        df = pd.DataFrame(cur.fetchall(), columns=["h3_9", "divisao", "ativos"])
    geoms = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in df["h3_9"]]
    return gpd.GeoDataFrame(df, geometry=gpd.GeoSeries(geoms, crs=4326), crs=4326)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pasta", default=str(config.DADOS_BRUTO.parent / "exportar"))
    args = ap.parse_args(argv)
    pasta = Path(args.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    with db.etapa("exportar"), db.conectar() as conn:
        camadas = {nome: ler(conn, sql) for nome, sql in CONSULTAS.items()}
        camadas["densidade_h3"] = hexagonos(conn)
        for nome, gdf in camadas.items():
            destino = pasta / f"{nome}.parquet"
            gdf.to_parquet(destino)
            log.info("%s: %d linhas", destino, len(gdf))
        db.registrar(
            conn,
            "exportacao",
            str(pasta),
            linhas=sum(len(g) for g in camadas.values()),
            camadas={n: len(g) for n, g in camadas.items()},
        )


if __name__ == "__main__":
    main()
