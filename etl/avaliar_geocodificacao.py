"""Mede o erro em metros de cada nível da geocodificação.

Uso:
    python -m etl.avaliar_geocodificacao [--amostra 20000] [--semente pineal]

Sorteia endereços do CNEFE com número e CEP, esconde o ponto de cada um da base e geocodifica o
endereço com o mesmo núcleo usado para os CNPJs (sql/10_geocodificar.sql). A distância entre o ponto
achado e o ponto verdadeiro dá o erro por nível. Como o próprio ponto some da base, o erro sai um
pouco pior que o real dos CNPJs (cujo endereço costuma estar no CNEFE): é uma estimativa conservadora.
Grava relatorios/erro_geocodificacao.md.
"""

import argparse
import logging

from etl import config, db
from etl.geocodificar import ORDEM, geocodificar

log = logging.getLogger("avaliar_geocodificacao")


def avaliar(conn, amostra: int, semente: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE amostra ON COMMIT DROP AS
            SELECT cod_unico, cep, logradouro, numero, nome_chave, geom
            FROM cnefe
            WHERE cep IS NOT NULL AND numero IS NOT NULL AND logradouro IS NOT NULL
            ORDER BY md5(cod_unico || %s)
            LIMIT %s
        """,
            (semente, amostra),
        )
    geocodificar(
        conn,
        """SELECT cod_unico, cep, norm_logradouro(logradouro), norm_logradouro_completa(logradouro), numero,
                  nome_chave, NULL FROM amostra""",
        "SELECT c.* FROM cnefe c WHERE NOT EXISTS (SELECT 1 FROM amostra s WHERE s.cod_unico = c.cod_unico)",
    )
    with conn.cursor() as cur:
        cur.execute("""
            SELECT a.geo_precisao, count(*),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_Distance(a.geom::geography, s.geom::geography)),
                   percentile_cont(0.9) WITHIN GROUP (ORDER BY ST_Distance(a.geom::geography, s.geom::geography)),
                   avg((ST_Distance(a.geom::geography, s.geom::geography) <= 50)::int),
                   avg((ST_Distance(a.geom::geography, s.geom::geography) <= 250)::int)
            FROM alvo a JOIN amostra s ON s.cod_unico = a.id
            GROUP BY 1
        """)
        por = {r[0]: r[1:] for r in cur.fetchall()}
    return [(p, *por[p]) for p in ORDEM if p in por]


def relatorio(linhas: list[tuple], amostra: int) -> str:
    total = sum(r[1] for r in linhas) or 1
    md = [
        "# Erro da geocodificação em metros",
        "",
        f"Amostra: {amostra} endereços do CNEFE, cada um geocodificado sem o próprio ponto na base.",
        "",
        "| nível | endereços | % | erro mediano (m) | p90 (m) | até 50 m | até 250 m |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for p, n, med, p90, ate50, ate250 in linhas:
        if p == "nao_localizado":
            md.append(f"| {p} | {n} | {100 * n / total:.1f} | | | | |")
        else:
            md.append(
                f"| {p} | {n} | {100 * n / total:.1f} | {med:.0f} | {p90:.0f} | "
                f"{100 * ate50:.0f}% | {100 * ate250:.0f}% |"
            )
    md += [
        "",
        "Use o p90 para decidir a menor escala em que cada nível entra numa análise (quadra, raio, setor, bairro).",
    ]
    return "\n".join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--amostra", type=int, default=20_000)
    ap.add_argument("--semente", default="pineal")
    args = ap.parse_args(argv)
    with db.etapa("avaliar_geocodificacao"), db.conectar() as conn:
        db.criar_schema(conn)
        if not db.contar(conn, "SELECT count(*) FROM cnefe"):
            raise SystemExit("cnefe vazio: rode antes python -m etl.fontes.ibge_cnefe")
        linhas = avaliar(conn, args.amostra, args.semente)
        conn.rollback()  # descarta as tabelas temporárias; só o registro abaixo fica no banco
        db.registrar(
            conn,
            "avaliacao_geocodificacao",
            linhas=sum(r[1] for r in linhas),
            niveis={r[0]: {"n": r[1], "mediana_m": r[2], "p90_m": r[3]} for r in linhas},
        )
    md = relatorio(linhas, args.amostra)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "erro_geocodificacao.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
