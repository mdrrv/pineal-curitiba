"""Roda o módulo eleitoral (ME): cargas do TSE, ponte seção -> território e agregados por bairro.

Uso:
    python -m etl.me                    # todas as etapas
    python -m etl.me --so votacao       # uma etapa (repetível)
    python -m etl.me --pular perfil     # todas menos essa (repetível)

Etapas: locais, votacao, perfil. Depois de qualquer caminho roda sql/90_eleitoral.sql e grava o
relatório em relatorios/eleitoral.md. Pré-requisito: M0 com setores, bairros e CNEFE carregados
(sem eles os locais sem coordenada do TSE ficam sem geocodificação e sem chave territorial).
Escopo, fases e limites legais em docs/prd-eleitoral-2028.md.
"""

import argparse
import logging

from etl import config, db
from etl.fontes import tse_eleitorado, tse_locais, tse_votacao

log = logging.getLogger("me")

ETAPAS = {
    "locais": lambda: tse_locais.main([]),
    "votacao": lambda: tse_votacao.main([]),
    "perfil": lambda: tse_eleitorado.main([]),
}


def resumo(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("""SELECT count(DISTINCT ano), count(*), count(*) FILTER (WHERE geom IS NOT NULL)
                       FROM eleicao_local_votacao""")
        anos_locais, locais, com_geom = cur.fetchone()
        cur.execute("""SELECT count(*), count(*) FILTER (WHERE bairro IS NOT NULL),
                              round(100.0 * count(*) FILTER (WHERE bairro IS NOT NULL) / NULLIF(count(*), 0), 1)
                       FROM eleicao_secao_territorio""")
        secoes, com_terr, pct_terr = cur.fetchone()
        cur.execute("""
            SELECT ano, turno, sum(aptos), sum(comparecimento), sum(abstencoes),
                   round(100.0 * sum(abstencoes) / NULLIF(sum(aptos), 0), 1)
            FROM eleicao_bairro_participacao GROUP BY 1, 2 ORDER BY 1, 2
        """)
        participacao = cur.fetchall()
        cur.execute("""
            SELECT bairro, ano, turno, abstencao_pct FROM eleicao_bairro_participacao
            WHERE bairro <> '(sem território)' AND turno = 1
              AND ano = (SELECT max(ano) FROM eleicao_bairro_participacao)
            ORDER BY abstencao_pct DESC NULLS LAST LIMIT 10
        """)
        abstencao = cur.fetchall()
        cur.execute("""
            SELECT ano, turno, nr_votavel, min(nm_votavel), sum(votos) FROM eleicao_bairro_votacao
            WHERE cd_cargo = 11 AND nr_votavel < 90
            GROUP BY 1, 2, 3 ORDER BY 1 DESC, 2, 5 DESC
        """)
        prefeito = cur.fetchall()
    md = [
        "# Módulo eleitoral (ME): carga do TSE",
        "",
        f"- Locais de votação: {locais} seções em {anos_locais} anos; {com_geom} com geometria",
        f"- Ponte seção -> território: {secoes} seções, {com_terr} com bairro ({pct_terr or 0}%)",
        "",
        "## Participação por eleição",
        "",
        "| ano | turno | aptos | comparecimento | abstenções | abstenção % |",
        "|---|---|---:|---:|---:|---:|",
        *[f"| {a} | {t} | {ap or ''} | {c or ''} | {ab or ''} | {p or ''} |" for a, t, ap, c, ab, p in participacao],
        "",
        "## Maior abstenção por bairro (última eleição, 1º turno)",
        "",
        "| bairro | ano | turno | abstenção % |",
        "|---|---|---|---:|",
        *[f"| {b} | {a} | {t} | {p} |" for b, a, t, p in abstencao],
        "",
        "## Prefeito: votos no município por candidato (sem brancos/nulos)",
        "",
        "| ano | turno | número | candidato | votos |",
        "|---|---|---|---|---:|",
        *[f"| {a} | {t} | {nr} | {nm or ''} | {v} |" for a, t, nr, nm, v in prefeito],
    ]
    return "\n".join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--so", action="append", choices=list(ETAPAS))
    ap.add_argument("--pular", action="append", choices=list(ETAPAS), default=[])
    args = ap.parse_args(argv)
    for nome, etapa in ETAPAS.items():
        if (args.so and nome not in args.so) or nome in args.pular:
            continue
        log.info("=== %s ===", nome)
        etapa()
    with db.etapa("eleitoral"), db.conectar() as conn:
        db.criar_schema(conn)
        db.executar_sql(conn, "90_eleitoral.sql")
        md = resumo(conn)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "eleitoral.md").write_text(md, encoding="utf-8")
    print(md)
    log.info("ME concluído. Relatório em relatorios/eleitoral.md")


if __name__ == "__main__":
    main()
