"""Roda o M0 inteiro, na ordem.

Uso:
    python -m etl.m0                     # todas as etapas
    python -m etl.m0 --so geocodificar   # uma etapa (repetível)
    python -m etl.m0 --pular ippuc       # todas menos essa (repetível)

Etapas: schema, setores, ippuc, cnefe, cnpj, geocodificar, territorio
"""

import argparse
import logging

from etl import db, geocodificar, territorio
from etl.fontes import cnpj_recorte, ibge_cnefe, ibge_setores, ippuc

log = logging.getLogger("m0")


def _schema():
    with db.etapa("schema"), db.conectar() as conn:
        db.criar_schema(conn)


ETAPAS = {
    "schema": _schema,
    "setores": lambda: ibge_setores.main([]),
    "ippuc": lambda: ippuc.main([]),
    "cnefe": lambda: ibge_cnefe.main([]),
    "cnpj": lambda: cnpj_recorte.main([]),
    "geocodificar": lambda: geocodificar.main([]),
    "territorio": lambda: territorio.main([]),
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
    log.info("M0 concluído. Relatórios em relatorios/")


if __name__ == "__main__":
    main()
