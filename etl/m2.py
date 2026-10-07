"""Roda o enriquecimento e os indicadores do M2, depois do M0.

Uso:
    python -m etl.m2                       # todas as etapas
    python -m etl.m2 --so indicadores      # uma etapa (repetível)
    python -m etl.m2 --pular edificacoes   # todas menos essa (repetível)

Etapas: apoio, cruzamentos, edificacoes, enriquecer, censo, indicadores, score, exportar
"""

import argparse
import logging

from etl import enriquecer, exportar, indicadores, score
from etl.fontes import apoio, ibge_censo_setor, mindata_cruzamentos, overture_edificacoes

log = logging.getLogger("m2")

ETAPAS = {
    "apoio": lambda: apoio.main([]),
    "cruzamentos": lambda: mindata_cruzamentos.main([]),
    "edificacoes": lambda: overture_edificacoes.main([]),
    "enriquecer": lambda: enriquecer.main([]),
    "censo": lambda: ibge_censo_setor.main([]),
    "indicadores": lambda: indicadores.main([]),
    "score": lambda: score.main([]),
    "exportar": lambda: exportar.main([]),
}


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
    log.info("M2 concluído. Relatórios em relatorios/, camadas em dados/exportar/")


if __name__ == "__main__":
    main()
