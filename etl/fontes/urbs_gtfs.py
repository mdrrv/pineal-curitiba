"""Transporte coletivo no formato GTFS: pontos de ônibus com linhas e partidas, e agregado por hexágono.

Uso:
    python -m etl.fontes.urbs_gtfs [--arquivo gtfs.zip]

O portal da prefeitura não publica arquivo do transporte coletivo, só o webservice da URBS (com chave).
Este ETL lê um GTFS padrão (zip com stops.txt, trips.txt e stop_times.txt): o informado em --arquivo, o
que estiver em dados/bruto/urbs_gtfs/ ou o da `url` do catálogo. Partidas = passagens de viagens pelo
ponto no feed; linhas = rotas distintas que param nele. Grava onibus_ponto e onibus_h3.
"""

import argparse
import csv
import io
import logging
import zipfile
from collections import defaultdict
from pathlib import Path

import h3
from psycopg2.extras import execute_values

from etl import baixar, config, db

log = logging.getLogger("urbs_gtfs")
FONTE = "urbs_gtfs"


def obter_arquivo(arquivo: str | None) -> Path:
    if arquivo:
        return Path(arquivo)
    local = baixar.arquivo_local(FONTE, r"\.zip$")
    if local:
        return local
    url = config.fonte(FONTE).get("url")
    if not url:
        raise SystemExit(f"sem GTFS: coloque o zip em {baixar.pasta(FONTE)} ou informe --arquivo / `url` no catálogo")
    return baixar.baixar(url, FONTE)


def _tabela(z: zipfile.ZipFile, nome: str):
    caminho = next((n for n in z.namelist() if n.rsplit("/", 1)[-1] == nome), None)
    if caminho is None:
        raise ValueError(f"{nome} ausente no GTFS")
    return csv.DictReader(io.TextIOWrapper(z.open(caminho), encoding="utf-8-sig"))


def ler_gtfs(caminho: Path) -> list[tuple]:
    with zipfile.ZipFile(caminho) as z:
        rota_da_viagem = {t["trip_id"]: t["route_id"] for t in _tabela(z, "trips.txt")}
        partidas, linhas = defaultdict(int), defaultdict(set)
        for st in _tabela(z, "stop_times.txt"):
            partidas[st["stop_id"]] += 1
            rota = rota_da_viagem.get(st["trip_id"])
            if rota:
                linhas[st["stop_id"]].add(rota)
        pontos = []
        for s in _tabela(z, "stops.txt"):
            if s.get("location_type") not in (None, "", "0"):
                continue  # estações e entradas: só os pontos de parada
            lat, lon = float(s["stop_lat"]), float(s["stop_lon"])
            pontos.append(
                (
                    s["stop_id"],
                    s.get("stop_name"),
                    len(linhas[s["stop_id"]]),
                    partidas[s["stop_id"]],
                    h3.latlng_to_cell(lat, lon, 9),
                    lon,
                    lat,
                )
            )
    return pontos


def gravar(conn, pontos: list[tuple]) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE onibus_ponto")
        execute_values(
            cur,
            "INSERT INTO onibus_ponto (stop_id, nome, linhas, partidas, h3_9, geom) VALUES %s",
            pontos,
            template="(%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
        )
        cur.execute("TRUNCATE onibus_h3")
        cur.execute("""
            INSERT INTO onibus_h3
            SELECT h3_9, count(*), max(linhas), sum(partidas) FROM onibus_ponto GROUP BY h3_9
        """)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", help="GTFS (zip)")
    args = ap.parse_args(argv)
    with db.etapa("transporte"):
        caminho = obter_arquivo(args.arquivo)
        pontos = ler_gtfs(caminho)
        with db.conectar() as conn:
            db.criar_schema(conn)
            gravar(conn, pontos)
            db.registrar(conn, FONTE, str(caminho), caminho.name, baixar.sha256(caminho), len(pontos))
    log.info("%d pontos de ônibus", len(pontos))


if __name__ == "__main__":
    main()
