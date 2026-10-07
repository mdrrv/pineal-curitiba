"""Roda as bases da prefeitura (M1), depois do M0.

Uso:
    python -m etl.m1                    # todas as etapas
    python -m etl.m1 --so alvaras       # uma etapa (repetível)
    python -m etl.m1 --pular alvaras    # todas menos essa (repetível)

Etapas: alvaras, licitacoes, zeladoria, unidades, transporte, seguranca, listas
"""

import argparse
import logging

from etl.fontes import listas_cnpj, pmc_alvaras, pmc_licitacoes, pmc_sigesguarda, pmc_unidades, pmc_zeladoria, urbs_gtfs

log = logging.getLogger("m1")

ETAPAS = {
    "alvaras": lambda: pmc_alvaras.main([]),
    "licitacoes": lambda: pmc_licitacoes.main([]),
    "zeladoria": lambda: pmc_zeladoria.main([]),
    "unidades": lambda: pmc_unidades.main([]),
    "transporte": lambda: urbs_gtfs.main([]),
    "seguranca": lambda: pmc_sigesguarda.main([]),
    "listas": lambda: listas_cnpj.main([]),
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
    log.info("M1 concluído. Relatórios em relatorios/")


if __name__ == "__main__":
    main()
