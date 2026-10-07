"""Pacote de publicação para a plataforma (M3): só coordenadas, malhas e agregados.

Uso:
    python -m etl.publicar [--pasta dados/publicar]

Gera dados/publicar/<AAAA-MM-DD>/ com uma camada por arquivo (FlatGeobuf para o mapa, Parquet para tabela)
e manifesto.json (camadas, linhas, colunas, sha256, data da base). Depois, para o mapa:
    scripts/pmtiles.sh dados/publicar/<AAAA-MM-DD>       # tippecanoe -> pineal.pmtiles (MapLibre)

Recorte publicado (CAMADAS):
    - empresas: ponto só de empresa ativa, pessoa jurídica, não MEI, com localização de quadra; colunas de
      atividade, porte, território, score e risco. MEI e CNPJ de pessoa física só entram nos agregados (o ponto
      pode ser a casa da pessoa).
    - hexágonos H3 r9 e bairros: contagens e índices.
Nada de nome, razão social, CPF, contato ou endereço por extenso: a checagem final recusa o pacote se aparecer
coluna proibida ou um CPF em qualquer valor de texto. Camada cujas tabelas não existem (passo não rodou) fica
de fora e o manifesto diz por quê.
"""

import argparse
import datetime
import hashlib
import json
import logging
import re
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from shapely import wkb
from shapely.geometry import Polygon

from etl import config, db

log = logging.getLogger("publicar")

PROIBIDAS = re.compile(
    r"razao|fantasia|nome_socio|socio|cpf|e_?mail|telefone|fone|logradouro|^numero$|complemento|endereco|titular",
    re.I,
)
CPF = re.compile(r"(?<![0-9])[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}(?![0-9])")
PRECISA = "('estabelecimento', 'endereco', 'endereco_sem_cep', 'numero_proximo')"
OPCIONAIS = {"empresa_lead": "cnpj VARCHAR(14), score INT", "empresa_risco": "cnpj VARCHAR(14), risco_12m NUMERIC"}

# nome: (tabelas exigidas, tipo de geometria, SQL). tipo: ponto/poligono (coluna geom em WKB), h3 (coluna h3_9),
# tabela (sem geometria)
CAMADAS = {
    "empresas": (
        ["empresa", "empresa_geo"],
        "ponto",
        f"""
        SELECT e.cnpj, left(e.cnae_fiscal_principal, 2) AS divisao, e.cnae_fiscal_principal AS cnae, e.porte_empresa,
               extract(YEAR FROM e.data_inicio_atividade)::INT AS ano_abertura, g.geo_precisao, g.bairro, g.h3_9,
               l.score, r.risco_12m, ST_AsBinary(g.geom) AS geom
        FROM empresa e
        JOIN empresa_geo g USING (cnpj)
        LEFT JOIN empresa_lead l USING (cnpj)
        LEFT JOIN empresa_risco r USING (cnpj)
        WHERE e.situacao_cadastral = '02' AND NOT e.pessoa_fisica AND coalesce(e.opcao_mei, 'N') <> 'S'
          AND g.geo_precisao IN {PRECISA} AND g.geom IS NOT NULL
        """,
    ),
    "densidade_h3": (
        ["m2_densidade_h3"],
        "h3",
        """
        SELECT h3_9, max(ativos) FILTER (WHERE divisao IS NULL) AS ativos,
               (jsonb_object_agg(divisao, ativos) FILTER (WHERE divisao IS NOT NULL))::TEXT AS por_divisao
        FROM m2_densidade_h3 GROUP BY 1
        """,
    ),
    "demanda_h3": (["demanda_h3"], "h3", "SELECT * FROM demanda_h3"),
    "seguranca_h3": (
        ["seguranca_h3"],
        "h3",
        """
        SELECT h3_9, sum(ocorrencias_12m)::INT AS ocorrencias_12m,
               (jsonb_object_agg(categoria, ocorrencias_12m))::TEXT AS por_categoria
        FROM seguranca_h3 GROUP BY 1
        """,
    ),
    "onibus_h3": (["onibus_h3"], "h3", "SELECT * FROM onibus_h3"),
    "bairros": (
        ["bairro"],
        "poligono",
        """
        SELECT b.nome AS bairro, b.codigo,
               (SELECT count(*) FROM empresa_geo g JOIN empresa e USING (cnpj)
                WHERE g.bairro = b.nome AND e.situacao_cadastral = '02') AS ativos,
               (SELECT sum(pessoas) FROM setor_demografia d WHERE d.bairro = b.nome) AS moradores,
               ri.patrimonial AS risco_patrimonial, ri.violento AS risco_violento, ri.fisico AS risco_fisico,
               ri.indice AS risco_indice, ST_AsBinary(b.geom) AS geom
        FROM (SELECT DISTINCT ON (nome) * FROM bairro ORDER BY nome, ST_Area(geom) DESC) b
        LEFT JOIN risco_bairro_indice ri ON ri.bairro = b.nome
        """,
    ),
    "saturacao_bairro": (["m2_saturacao_bairro"], "tabela", "SELECT * FROM m2_saturacao_bairro"),
    "espaco_livre": (["m2_espaco_livre"], "tabela", "SELECT * FROM m2_espaco_livre"),
}
# camadas que usam tabelas de passos opcionais; ausentes viram vazias (LEFT JOIN)
STUBS_SQL = {
    "bairros": {
        "risco_bairro_indice": "bairro TEXT, patrimonial NUMERIC, violento NUMERIC, fisico NUMERIC, indice NUMERIC",
        "setor_demografia": "bairro TEXT, pessoas NUMERIC",
    },
}


def existe(conn, tabela: str) -> bool:
    return db.contar(conn, "SELECT count(*) FROM (SELECT to_regclass(%s) AS r) x WHERE r IS NOT NULL", (tabela,)) > 0


def ler(conn, sql: str, tipo: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    if tipo in ("ponto", "poligono"):
        geoms = [wkb.loads(bytes(g)) if g is not None else None for g in df.pop("geom")] if len(df) else []
        return gpd.GeoDataFrame(df, geometry=gpd.GeoSeries(geoms, crs=4326), crs=4326)
    if tipo == "h3":
        geoms = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in df["h3_9"]]
        return gpd.GeoDataFrame(df, geometry=gpd.GeoSeries(geoms, crs=4326), crs=4326)
    return df


def checar(nome: str, df: pd.DataFrame) -> None:
    ruins = [c for c in df.columns if c != "geometry" and PROIBIDAS.search(c)]
    if ruins:
        raise ValueError(f"camada {nome}: colunas proibidas na publicação: {ruins}")
    for c in df.columns:
        if (
            c != "geometry"
            and not c.startswith("h3_")
            and (df[c].dtype == object or pd.api.types.is_string_dtype(df[c]))
        ):  # índice H3 é hexadecimal
            achado = df[c].dropna().astype(str).map(lambda v: bool(CPF.search(v)))
            if achado.any():
                raise ValueError(f"camada {nome}: CPF na coluna {c} (linha {achado.idxmax()})")


def gravar(df: pd.DataFrame, destino: Path) -> None:
    for c in df.columns:  # Decimal e date viram tipos que o FlatGeobuf/Parquet aceitam
        if c != "geometry" and df[c].dtype == object:
            amostra = df[c].dropna().head(1).tolist()
            if amostra and type(amostra[0]).__name__ == "Decimal":
                df[c] = df[c].astype(float)
            elif amostra and isinstance(amostra[0], datetime.date):
                df[c] = df[c].astype(str)
    if isinstance(df, gpd.GeoDataFrame):
        df.to_file(destino, driver="FlatGeobuf", engine="pyogrio")
    else:
        df.to_parquet(destino, index=False)


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def publicar(conn, pasta: Path) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    with conn.cursor() as cur:
        for tabela, colunas in OPCIONAIS.items():
            if not existe(conn, tabela):
                cur.execute(f"CREATE TEMP TABLE {tabela} ({colunas}) ON COMMIT DROP")
        for stubs in STUBS_SQL.values():
            for tabela, colunas in stubs.items():
                if not existe(conn, tabela):
                    cur.execute(f"CREATE TEMP TABLE {tabela} ({colunas}) ON COMMIT DROP")
        cur.execute("SELECT greatest(max(data_inicio_atividade), max(data_situacao_cadastral)) FROM empresa")
        base = cur.fetchone()[0]
    manifesto = {
        "gerado_em": datetime.datetime.now().isoformat(timespec="seconds"),
        "base_rfb": str(base),
        "schema": config.SCHEMA,
        "camadas": {},
        "fora": {},
    }
    for nome, (tabelas, tipo, sql) in CAMADAS.items():
        faltando = [t for t in tabelas if not existe(conn, t)]
        if faltando:
            manifesto["fora"][nome] = f"tabelas ausentes: {', '.join(faltando)}"
            continue
        df = ler(conn, sql, tipo)
        if df.empty:
            manifesto["fora"][nome] = "vazia"
            continue
        checar(nome, df)
        destino = pasta / f"{nome}.{'parquet' if tipo == 'tabela' else 'fgb'}"
        gravar(df, destino)
        manifesto["camadas"][nome] = {
            "arquivo": destino.name,
            "tipo": tipo,
            "linhas": len(df),
            "colunas": [c for c in df.columns if c != "geometry"],
            "sha256": sha256(destino),
        }
        log.info("%s: %d linhas", destino.name, len(df))
    (pasta / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pasta", type=Path)
    args = ap.parse_args(argv)
    pasta = args.pasta or config.DADOS_BRUTO.parent / "publicar" / datetime.date.today().isoformat()
    with db.etapa("publicar"), db.conectar() as conn:
        m = publicar(conn, pasta)
        db.registrar(
            conn,
            "publicacao",
            str(pasta),
            linhas=sum(c["linhas"] for c in m["camadas"].values()),
            camadas={n: c["linhas"] for n, c in m["camadas"].items()},
        )
    for n, c in m["camadas"].items():
        print(f"{n}: {c['linhas']} linhas ({c['arquivo']})")
    for n, motivo in m["fora"].items():
        print(f"{n}: fora ({motivo})")
    print(f"pacote em {pasta}; mapa: scripts/pmtiles.sh {pasta}")
    return m


if __name__ == "__main__":
    main()
