"""Camadas do IPPUC: bairros, regionais e zoneamento.

Uso:
    python -m etl.fontes.ippuc [--camada bairro|regional|zoneamento] [--listar]

O IPPUC não publica link direto estável para todos os arquivos. Coloque o shp/zip/gpkg/geojson de cada
camada em dados/bruto/ippuc/ (o nome do arquivo precisa casar com `padrao_arquivo` no catalogo.yaml).
Se a camada tiver `url` no catálogo, o script baixa sozinho.

--listar mostra as colunas de cada arquivo encontrado, para ajustar campo_nome/campo_codigo no catálogo.
"""

import argparse
import logging

from etl import baixar, config, db, geo

log = logging.getLogger("ippuc")
FONTE = "ippuc"

CANDIDATOS_NOME = {
    "bairro": ["NOME", "NM_BAIRRO", "NOME_BAIRR", "NOME_BAIRRO", "BAIRRO"],
    "regional": ["NOME", "NM_REGIONA", "NOME_REGIO", "NOME_REGIONAL", "REGIONAL", "ADM_REGIONAL"],
    "zoneamento": ["NM_ZONA", "NOME_ZONA", "ZONA", "NOME", "DESCRICAO", "SG_ZONA", "SIGLA"],
}
CANDIDATOS_CODIGO = {
    "bairro": ["CODIGO", "CD_BAIRRO", "COD_BAIRRO", "CODIGO_BAI", "COD"],
    "regional": ["CODIGO", "CD_REGIONA", "COD_REGIONAL", "COD"],
    "zoneamento": ["SG_ZONA", "SIGLA", "CD_ZONA", "COD_ZONA", "CODIGO"],
}


def arquivo_da_camada(camada: str, cfg: dict):
    local = baixar.arquivo_local(FONTE, cfg["padrao_arquivo"])
    if local:
        return local
    if cfg.get("url"):
        return baixar.baixar(cfg["url"], FONTE)
    return None


def carregar_camada(conn, camada: str, cfg: dict) -> int:
    caminho = arquivo_da_camada(camada, cfg)
    if caminho is None:
        log.warning(
            "camada %s: nenhum arquivo em %s casando com /%s/. Pulando.",
            camada,
            baixar.pasta(FONTE),
            cfg["padrao_arquivo"],
        )
        return 0
    cols = geo.colunas(caminho)
    campo_nome = cfg.get("campo_nome") or geo.achar_coluna(cols, CANDIDATOS_NOME[camada])
    campo_codigo = cfg.get("campo_codigo") or geo.achar_coluna(cols, CANDIDATOS_CODIGO[camada])
    if campo_codigo == campo_nome:
        campo_codigo = None
    if not campo_nome:
        raise ValueError(f"camada {camada}: defina campo_nome no catalogo.yaml. Colunas de {caminho.name}: {cols}")
    log.info("camada %s: %s (nome=%s, codigo=%s)", camada, caminho.name, campo_nome, campo_codigo)
    gdf = geo.ler(caminho, crs_padrao=cfg.get("crs_padrao"))
    n = geo.gravar_poligonos(conn, camada, gdf, campo_nome, campo_codigo)
    db.registrar(
        conn,
        f"{FONTE}_{camada}",
        cfg.get("url") or str(caminho),
        caminho.name,
        baixar.sha256(caminho),
        n,
        colunas=cols,
        campo_nome=campo_nome,
        campo_codigo=campo_codigo,
    )
    log.info("camada %s: %d polígonos", camada, n)
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camada", choices=list(CANDIDATOS_NOME), action="append")
    ap.add_argument("--listar", action="store_true", help="só mostra arquivos e colunas encontrados")
    args = ap.parse_args(argv)
    camadas = config.fonte(FONTE)["camadas"]
    escolhidas = args.camada or list(camadas)

    if args.listar:
        for c in escolhidas:
            caminho = arquivo_da_camada(c, camadas[c])
            print(f"{c}: {caminho or '(não encontrado)'}")
            if caminho:
                print("   colunas:", geo.colunas(caminho))
        return

    with db.etapa("ippuc"), db.conectar() as conn:
        db.criar_schema(conn)
        for c in escolhidas:
            carregar_camada(conn, c, camadas[c])


if __name__ == "__main__":
    main()
