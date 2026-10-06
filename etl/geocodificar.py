"""Geocodifica cwb.empresa pelo CNEFE e grava o relatório de acerto.

Uso:
    python -m etl.geocodificar
"""
import argparse
import logging

from etl import config, db

log = logging.getLogger("geocodificar")

ORDEM = ["endereco", "endereco_sem_cep", "numero_proximo", "logradouro", "logradouro_aproximado",
         "logradouro_sem_cep", "cep", "nao_localizado"]


def resumo(conn) -> list[tuple[str, int, int]]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT g.geo_precisao, count(*), count(*) FILTER (WHERE e.situacao_cadastral = '02')
            FROM cwb.empresa_geo g JOIN cwb.empresa e USING (cnpj)
            GROUP BY 1
        """)
        por = {p: (t, a) for p, t, a in cur.fetchall()}
    return [(p, *por.get(p, (0, 0))) for p in ORDEM]


def relatorio(linhas: list[tuple[str, int, int]]) -> str:
    total = sum(t for _, t, _ in linhas) or 1
    ativas = sum(a for _, _, a in linhas) or 1
    md = ["# Geocodificação dos CNPJs", "",
          "| nível | todas | % | acumulado | ativas | % | acumulado |", "|---|---:|---:|---:|---:|---:|---:|"]
    acum_t = acum_a = 0
    for p, t, a in linhas:
        if p != "nao_localizado":
            acum_t += t
            acum_a += a
        md.append(f"| {p} | {t} | {100 * t / total:.1f} | {100 * acum_t / total:.1f} | "
                  f"{a} | {100 * a / ativas:.1f} | {100 * acum_a / ativas:.1f} |")
    md += ["", "Acumulado = localizadas até aquele nível. `endereco` e `numero_proximo` servem para análise por quadra;",
           "`logradouro*` para bairro e setor; `cep` só para bairro ou regional."]
    return "\n".join(md)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with db.conectar() as conn:
        db.criar_schema(conn)
        if not db.contar(conn, "SELECT count(*) FROM cwb.cnefe"):
            raise SystemExit("cwb.cnefe vazio: rode antes python -m etl.fontes.ibge_cnefe")
        db.executar_sql(conn, "10_geocodificar.sql")
        linhas = resumo(conn)
        db.registrar(conn, "geocodificacao", linhas=sum(t for _, t, _ in linhas),
                     niveis={p: t for p, t, _ in linhas})
    md = relatorio(linhas)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "geocodificacao.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
