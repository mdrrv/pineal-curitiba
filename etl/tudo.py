"""Roda o pipeline inteiro na ordem das dependências, com verificação antes e retomada depois de falha.

Uso:
    python -m etl.tudo                         # verificação + todas as etapas
    python -m etl.tudo --pular vias --pular edificacoes
    python -m etl.tudo --retomar <run_id>      # pula as etapas que já deram ok nessa rodada

Ordem: fundação (M0) -> apoio, Censo, cruzamentos, edificações e enriquecimento (o perfil do ponto é usado
pelos alvarás) -> bases da prefeitura e listas (M1) -> indicadores, score e exportação -> rede de caminhada
-> publicação. Etapa essencial que falha para a rodada; etapa de fonte externa (OPCIONAIS) que falha, por
host fora do ar ou arquivo ausente, fica registrada e a rodada segue sem ela.

O run_id sai no início e no fim; com ele, --retomar refaz só o que faltou. Resumo em relatorios/rodada.md.
"""

import argparse
import logging
import time

from etl import config, db, enriquecer, exportar, geocodificar, indicadores, publicar, score, territorio, verificar
from etl.fontes import (
    apoio,
    cnpj_recorte,
    ibge_censo_setor,
    ibge_cnefe,
    ibge_setores,
    ippuc,
    listas_cnpj,
    mindata_cruzamentos,
    osm_vias,
    overture_edificacoes,
    pmc_alvaras,
    pmc_licitacoes,
    pmc_sigesguarda,
    pmc_unidades,
    pmc_zeladoria,
    urbs_gtfs,
)

log = logging.getLogger("tudo")


def _schema():
    with db.etapa("schema"), db.conectar() as conn:
        db.criar_schema(conn)


ORDEM = [
    ("schema", _schema),
    ("setores", lambda: ibge_setores.main([])),
    ("ippuc", lambda: ippuc.main([])),
    ("cnefe", lambda: ibge_cnefe.main([])),
    ("cnpj", lambda: cnpj_recorte.main([])),
    ("geocodificar", lambda: geocodificar.main([])),
    ("territorio", lambda: territorio.main([])),
    ("apoio", lambda: apoio.main([])),
    ("censo", lambda: ibge_censo_setor.main([])),
    ("cruzamentos", lambda: mindata_cruzamentos.main([])),
    ("edificacoes", lambda: overture_edificacoes.main([])),
    ("enriquecer", lambda: enriquecer.main([])),
    ("alvaras", lambda: pmc_alvaras.main([])),
    ("licitacoes", lambda: pmc_licitacoes.main([])),
    ("zeladoria", lambda: pmc_zeladoria.main([])),
    ("unidades", lambda: pmc_unidades.main([])),
    ("transporte", lambda: urbs_gtfs.main([])),
    ("seguranca", lambda: pmc_sigesguarda.main([])),
    ("listas", lambda: listas_cnpj.main([])),
    ("indicadores", lambda: indicadores.main([])),
    ("score", lambda: score.main([])),
    ("exportar", lambda: exportar.main([])),
    ("vias", lambda: osm_vias.main([])),
    ("publicar", lambda: publicar.main([])),
]
OPCIONAIS = {
    "censo", "cruzamentos", "edificacoes", "alvaras", "licitacoes", "zeladoria", "unidades", "transporte",
    "seguranca", "listas", "vias",
}  # fmt: skip


def ja_feitas(run_id: str) -> set[str]:
    with db.conectar() as conn:
        db.criar_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT fonte FROM execucao WHERE run_id = %s AND tipo = 'etapa' AND status = 'ok'", (run_id,))
            return {f for (f,) in cur.fetchall()}


def resumo(linhas: list[tuple[str, str, float, str]]) -> str:
    md = [
        "# Rodada completa",
        "",
        f"run_id `{config.RUN_ID}` (para retomar: `python -m etl.tudo --retomar {config.RUN_ID}`)",
        "",
        "| etapa | situação | segundos | detalhe |",
        "|---|---|---:|---|",
        *[f"| {n} | {s} | {t:.1f} | {d} |" for n, s, t, d in linhas],
    ]
    return "\n".join(md)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    nomes = [n for n, _ in ORDEM]
    ap.add_argument("--pular", action="append", choices=nomes, default=[])
    ap.add_argument("--retomar", metavar="RUN_ID")
    ap.add_argument("--sem-verificar", action="store_true")
    ap.add_argument("--sem-rede", action="store_true", help="verificação sem testar os hosts")
    args = ap.parse_args(argv)
    if args.retomar:
        config.RUN_ID = args.retomar
    log.info("rodada %s", config.RUN_ID)
    if not args.sem_verificar and verificar.main(["--sem-rede"] if args.sem_rede else []) != 0:
        log.error("a verificação achou falha (relatorios/verificacao.md): corrija antes de rodar")
        return 1
    feitas = ja_feitas(config.RUN_ID) if args.retomar else set()
    linhas, codigo = [], 0
    for nome, rodar in ORDEM:
        if nome in args.pular:
            linhas.append((nome, "pulada", 0.0, "--pular"))
            continue
        if nome in feitas:
            linhas.append((nome, "já feita", 0.0, f"ok na rodada {config.RUN_ID}"))
            continue
        log.info("=== %s ===", nome)
        inicio = time.monotonic()
        try:
            rodar()
            linhas.append((nome, "ok", time.monotonic() - inicio, ""))
        except KeyboardInterrupt:
            raise
        except BaseException as e:  # SystemExit dos ETLs (arquivo ausente) também conta como falha da etapa
            detalhe = f"{type(e).__name__}: {e}".replace("|", "/").replace("\n", " ")[:300]
            if nome in OPCIONAIS:
                log.warning("%s falhou e é opcional; seguindo: %s", nome, detalhe)
                linhas.append((nome, "falhou (opcional)", time.monotonic() - inicio, detalhe))
                continue
            log.error("%s falhou; rodada interrompida: %s", nome, detalhe)
            linhas.append((nome, "falhou", time.monotonic() - inicio, detalhe))
            codigo = 1
            break
    md = resumo(linhas)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "rodada.md").write_text(md, encoding="utf-8")
    print(md)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
