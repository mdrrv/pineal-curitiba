"""Malha de setores censitários 2022 (IBGE), recortada para o município.

Uso:
    python -m etl.fontes.ibge_setores [--arquivo caminho.zip]

Sem --arquivo, acha o zip da UF na listagem do FTP do IBGE (url_diretorio + padrao_arquivo no catalogo.yaml).
"""
import argparse
import logging
from pathlib import Path

from psycopg2.extras import execute_values

from etl import baixar, config, db, geo

log = logging.getLogger("ibge_setores")
FONTE = "ibge_setores"


def obter_arquivo(arquivo: str | None) -> tuple[Path, str]:
    if arquivo:
        return Path(arquivo), arquivo
    local = baixar.arquivo_local(FONTE, r"\.(zip|shp|gpkg)$")
    if local:
        return local, str(local)
    f = config.fonte(FONTE)
    url = baixar.resolver_no_diretorio(f["url_diretorio"], f["padrao_arquivo"])
    return baixar.baixar(url, FONTE), url


def carregar(conn, caminho: Path, origem: str) -> int:
    cols = geo.colunas(caminho)
    col_setor = geo.achar_coluna(cols, ["CD_SETOR", "CD_GEOCODI", "COD_SETOR"])
    col_mun = geo.achar_coluna(cols, ["CD_MUN", "CD_GEOCODM", "COD_MUN"])
    if not col_setor:
        raise ValueError(f"coluna do código do setor não encontrada. Colunas: {cols}")
    where = f"{col_mun} = '{config.COD_IBGE}'" if col_mun else None
    gdf = geo.ler(caminho, where=where)
    if not col_mun:
        gdf = gdf[gdf[col_setor].astype(str).str.startswith(config.COD_IBGE)]
    if gdf.empty:
        raise ValueError(f"nenhum setor do município {config.COD_IBGE} em {caminho.name}")

    attrs = gdf.drop(columns=gdf.geometry.name)
    linhas = [(str(a[col_setor]), geo._atributos(a), g.wkb) for a, g in zip(attrs.to_dict("records"), gdf.geometry)]
    with conn.cursor() as cur:
        cur.execute("TRUNCATE setor")
        execute_values(
            cur,
            "INSERT INTO setor (cd_setor, atributos, geom) VALUES %s ON CONFLICT (cd_setor) DO NOTHING",
            linhas,
            template="(%s, %s::jsonb, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromWKB(%s, 4326)), 3)))",
            page_size=500,
        )
    db.registrar(conn, FONTE, origem, caminho.name, baixar.sha256(caminho), len(linhas), colunas=cols)
    log.info("%d setores carregados", len(linhas))
    return len(linhas)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", help="zip/shp/gpkg já baixado")
    args = ap.parse_args(argv)
    with db.etapa("setores"):
        caminho, origem = obter_arquivo(args.arquivo)
        with db.conectar() as conn:
            db.criar_schema(conn)
            carregar(conn, caminho, origem)


if __name__ == "__main__":
    main()
