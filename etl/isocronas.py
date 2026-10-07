"""Isócronas a pé e de ônibus, e o raio-x da área alcançada.

Uso:
    python -m etl.isocronas --lat -25.4284 --lon -49.2733                     # a pé, 5, 10 e 15 min
    python -m etl.isocronas --lat ... --lon ... --modo onibus --minutos 15 30 --saida "2026-10-08 08:00"

Precisa da rede (python -m etl.fontes.osm_vias). O modo ônibus usa também o GTFS de
dados/bruto/urbs_gtfs/.

A pé: Dijkstra na rede a 4,8 km/h (80 m por minuto) a partir do nó mais perto do ponto.
Ônibus: caminha até os pontos, embarca nas viagens do dia que partem dentro da janela (Connection Scan:
cada viagem em ordem de partida, transferência a pé entre pontos a até 300 m) e, de cada ponto alcançado,
caminha com o tempo que sobra (um Dijkstra só, com todos os pontos como origem).
A área é a união das ruas alcançadas com 40 m de cada lado.

Cada isócrona vai para a tabela isocrona; o raio-x dela sai com
    SELECT * FROM raio_x_area((SELECT geom FROM isocrona WHERE id = <id>));
"""

import argparse
import datetime
import heapq
import logging
import math
from collections import defaultdict
from pathlib import Path

from etl import db
from etl.fontes import urbs_gtfs

log = logging.getLogger("isocronas")
VELOCIDADE = 80.0  # metros por minuto (4,8 km/h)
TRANSFERENCIA_M = 300
MARGEM_M = 40


def rede(conn) -> tuple[dict[int, list[tuple[int, float]]], list[tuple[int, int, int]]]:
    adj: dict[int, list[tuple[int, float]]] = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute("SELECT id, u, v, comprimento_m FROM via_aresta")
        arestas = cur.fetchall()
    for _, u, v, w in arestas:
        adj[u].append((v, w))
        adj[v].append((u, w))
    if not arestas:
        raise SystemExit("rede vazia: rode python -m etl.fontes.osm_vias")
    return adj, [(i, u, v) for i, u, v, _ in arestas]


def no_proximo(conn, pontos: list[tuple[str, float, float]]) -> dict[str, tuple[int, float]]:
    """Para cada (chave, lat, lon), o nó do componente principal mais perto e a distância em metros."""
    if not pontos:
        return {}
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE _p (chave TEXT, geom geometry(Point, 4326)) ON COMMIT DROP")
        cur.executemany(
            "INSERT INTO _p VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
            [(k, lon, lat) for k, lat, lon in pontos],
        )
        cur.execute("""
            SELECT p.chave, n.id, ST_Distance(n.geom::geography, p.geom::geography)
            FROM _p p CROSS JOIN LATERAL (
                SELECT id, geom FROM via_no WHERE principal ORDER BY geom <-> p.geom LIMIT 1) n
        """)
        r = {k: (n, d) for k, n, d in cur.fetchall()}
        cur.execute("DROP TABLE _p")
    return r


def dijkstra(adj, origens: dict[int, float], limite: float) -> dict[int, float]:
    dist = dict(origens)
    fila = [(d, n) for n, d in origens.items()]
    heapq.heapify(fila)
    while fila:
        d, n = heapq.heappop(fila)
        if d > dist.get(n, math.inf) or d > limite:
            continue
        for m, w in adj[n]:
            nd = d + w
            if nd <= limite and nd < dist.get(m, math.inf):
                dist[m] = nd
                heapq.heappush(fila, (nd, m))
    return {n: d for n, d in dist.items() if d <= limite}


def poligono(conn, arestas, dist: dict[int, float], limite: float, nome, modo, minutos, lat, lon, saida) -> int:
    ids = [i for i, u, v in arestas if dist.get(u, math.inf) <= limite and dist.get(v, math.inf) <= limite]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO isocrona (nome, modo, minutos, lat, lon, saida, geom)
            SELECT %s, %s, %s, %s, %s, %s, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Union(g)), 3))
            FROM (
                SELECT ST_Buffer(geom::geography, %s)::geometry AS g FROM via_aresta WHERE id = ANY(%s)
                UNION ALL SELECT ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)::geometry
            ) x
            RETURNING id
            """,
            (nome, modo, minutos, lat, lon, saida, MARGEM_M, ids, lon, lat, MARGEM_M),
        )
        return cur.fetchone()[0]


# ------------------------------------------------------------------ GTFS


def _seg(hhmmss: str) -> int | None:
    try:
        h, m, s = (int(x) for x in hhmmss.strip().split(":"))
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


def servicos_do_dia(z, dia: datetime.date) -> set[str] | None:
    """service_id ativos no dia (calendar + calendar_dates). None = GTFS sem calendário: vale tudo."""
    nomes = {n.rsplit("/", 1)[-1] for n in z.namelist()}
    if "calendar.txt" not in nomes and "calendar_dates.txt" not in nomes:
        return None
    ativos = set()
    d = dia.strftime("%Y%m%d")
    semana = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][dia.weekday()]
    if "calendar.txt" in nomes:
        for c in urbs_gtfs._tabela(z, "calendar.txt"):
            if c.get(semana) == "1" and c["start_date"] <= d <= c["end_date"]:
                ativos.add(c["service_id"])
    if "calendar_dates.txt" in nomes:
        for c in urbs_gtfs._tabela(z, "calendar_dates.txt"):
            if c["date"] == d:
                (ativos.add if c["exception_type"] == "1" else ativos.discard)(c["service_id"])
    return ativos


def ler_conexoes(caminho: Path, dia: datetime.date, inicio: int, fim: int):
    """Conexões (partida, chegada, ponto de, ponto para, viagem) do dia com partida em [inicio, fim], e os pontos."""
    import zipfile

    with zipfile.ZipFile(caminho) as z:
        servicos = servicos_do_dia(z, dia)
        viagens = {
            t["trip_id"] for t in urbs_gtfs._tabela(z, "trips.txt") if servicos is None or t["service_id"] in servicos
        }
        paradas = defaultdict(list)
        for st in urbs_gtfs._tabela(z, "stop_times.txt"):
            if st["trip_id"] in viagens:
                paradas[st["trip_id"]].append(
                    (int(st["stop_sequence"]), _seg(st["arrival_time"]), _seg(st["departure_time"]), st["stop_id"])
                )
        pontos = {
            s["stop_id"]: (float(s["stop_lat"]), float(s["stop_lon"]))
            for s in urbs_gtfs._tabela(z, "stops.txt")
            if s.get("stop_lat") and s.get("stop_lon")
        }
    conexoes = []
    for trip, seq in paradas.items():
        # parada sem horário (permitido no GTFS para quem não é ponto de controle) fica de fora: o trecho liga a
        # última parada com horário à próxima com horário
        seq = sorted((o, chg if chg is not None else sai, sai if sai is not None else chg, s) for o, chg, sai, s in seq)
        seq = [x for x in seq if x[1] is not None]
        for (_, _, dep, a), (_, arr, _, b) in zip(seq, seq[1:], strict=False):
            if dep is not None and arr is not None and inicio <= dep <= fim:
                conexoes.append((dep, arr, a, b, trip))
    conexoes.sort()
    return conexoes, pontos


def metros(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def transferencias(pontos: dict[str, tuple[float, float]]) -> dict[str, list[tuple[str, float]]]:
    grade = defaultdict(list)
    if not pontos:
        return {}
    passo = TRANSFERENCIA_M / 111_320
    lat_media = sum(la for la, _ in pontos.values()) / len(pontos)
    passo_lon = passo / math.cos(math.radians(lat_media))  # grau de longitude é mais curto fora do equador
    for s, (la, lo) in pontos.items():
        grade[(int(la / passo), int(lo / passo_lon))].append(s)
    viz = defaultdict(list)
    for s, p in pontos.items():
        ci, cj = int(p[0] / passo), int(p[1] / passo_lon)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for t in grade[(ci + di, cj + dj)]:
                    if t != s and (d := metros(p, pontos[t]) * 1.3) <= TRANSFERENCIA_M * 1.3:
                        viz[s].append((t, d))
    return viz


def connection_scan(conexoes, chegada: dict[str, float], viz) -> dict[str, float]:
    chegada = dict(chegada)
    embarcado = set()
    for dep, arr, a, b, trip in conexoes:
        if trip in embarcado or chegada.get(a, math.inf) <= dep:
            embarcado.add(trip)
            if arr < chegada.get(b, math.inf):
                chegada[b] = arr
                for t, d in viz.get(b, ()):
                    ta = arr + d / VELOCIDADE * 60
                    if ta < chegada.get(t, math.inf):
                        chegada[t] = ta
    return chegada


# ------------------------------------------------------------------ CLI


def calcular(
    conn, lat, lon, minutos: list[int], modo: str, saida: datetime.datetime, nome=None, gtfs=None
) -> list[int]:
    adj, arestas = rede(conn)
    origem = no_proximo(conn, [("origem", lat, lon)]).get("origem")
    if origem is None:
        raise SystemExit("sem nó no componente principal da rede")
    no0, d0 = origem
    if d0 > 300:
        log.warning("o ponto está a %.0f m da rede mais próxima: confira lat/lon (fora da cidade?)", d0)
    limite_max = max(minutos) * VELOCIDADE
    origens = {no0: d0}
    rotulo_saida = None
    if modo == "onibus":
        t0 = saida.hour * 3600 + saida.minute * 60
        conexoes, pontos = ler_conexoes(gtfs or urbs_gtfs.obter_arquivo(None), saida.date(), t0, t0 + max(minutos) * 60)
        usados = {s for c in conexoes for s in (c[2], c[3])}
        nos = no_proximo(conn, [(s, *pontos[s]) for s in usados if s in pontos])
        a_pe = dijkstra(adj, {no0: d0}, limite_max)
        chegada = {
            s: t0 + (a_pe[n] + d) / VELOCIDADE * 60
            for s, (n, d) in nos.items()
            if a_pe.get(n, math.inf) + d <= limite_max
        }
        chegada = connection_scan(conexoes, chegada, transferencias({s: pontos[s] for s in nos}))
        for s, t in chegada.items():
            if s not in nos:  # parada sem coordenada em stops.txt
                continue
            n, d = nos[s]
            custo = (t - t0) / 60 * VELOCIDADE + d
            if custo < origens.get(n, math.inf):
                origens[n] = custo
        rotulo_saida = saida.strftime("%Y-%m-%d %H:%M")
        log.info("%d conexões na janela; %d pontos alcançados", len(conexoes), len(chegada))
    dist = dijkstra(adj, origens, limite_max)
    return [
        poligono(conn, arestas, dist, m * VELOCIDADE, nome, modo, m, lat, lon, rotulo_saida) for m in sorted(minutos)
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--minutos", type=int, nargs="+", default=[5, 10, 15])
    ap.add_argument("--modo", choices=["pe", "onibus"], default="pe")
    ap.add_argument("--saida", help='dia e hora de saída, "AAAA-MM-DD HH:MM" (ônibus; padrão: hoje às 08:00)')
    ap.add_argument("--nome")
    ap.add_argument("--gtfs", type=Path)
    args = ap.parse_args(argv)
    saida = (
        datetime.datetime.strptime(args.saida, "%Y-%m-%d %H:%M")
        if args.saida
        else datetime.datetime.combine(datetime.date.today(), datetime.time(8))
    )
    with db.etapa("isocronas"), db.conectar() as conn:
        db.criar_schema(conn)
        ids = calcular(conn, args.lat, args.lon, args.minutos, args.modo, saida, args.nome, args.gtfs)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT i.id, i.minutos, round((ST_Area(i.geom::geography) / 1e6)::NUMERIC, 2), m.moradores
                   FROM isocrona i LEFT JOIN LATERAL moradores_area(i.geom) m ON true
                   WHERE i.id = ANY(%s) ORDER BY i.minutos""",
                (ids,),
            )
            linhas = cur.fetchall()
    for i, m, km2, mor in linhas:
        print(f"isócrona {i}: {args.modo}, {m} min, {km2} km², {mor if mor is not None else 's/ Censo'} moradores")
    print("raio-x: SELECT * FROM raio_x_area((SELECT geom FROM isocrona WHERE id = <id>));")
    return ids


if __name__ == "__main__":
    main()
