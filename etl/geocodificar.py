"""Geocodifica as empresas pelo CNEFE e grava o relatório de acerto.

Uso:
    python -m etl.geocodificar

A lógica dos níveis está em sql/10_geocodificar.sql e é a mesma usada por etl.avaliar_geocodificacao.
"""
import argparse
import logging

from etl import config, db

log = logging.getLogger("geocodificar")

ORDEM = ["estabelecimento", "endereco", "endereco_sem_cep", "numero_proximo", "logradouro",
         "logradouro_aproximado", "logradouro_sem_cep", "cep", "bairro", "nao_localizado"]

CRIAR_ALVO = """
    CREATE TEMP TABLE alvo (
        id TEXT PRIMARY KEY, cep VARCHAR(8), logr_chave TEXT, logr_completa TEXT, numero INTEGER,
        nome_chave TEXT, bairro_chave TEXT, geo_precisao TEXT, geom geometry(Point, 4326)
    ) ON COMMIT DROP
"""


def geocodificar(conn, sql_alvo: str, sql_base: str = "SELECT * FROM cnefe") -> None:
    """Roda o núcleo sobre os alvos de `sql_alvo` (colunas id, cep, logr_chave, logr_completa, numero,
    nome_chave, bairro_chave) usando como base os endereços de `sql_base`. Resultado fica na tabela temporária alvo."""
    with conn.cursor() as cur:
        cur.execute(CRIAR_ALVO)
        cur.execute(f"INSERT INTO alvo (id, cep, logr_chave, logr_completa, numero, nome_chave, bairro_chave) {sql_alvo}")
        cur.execute(f"CREATE TEMP VIEW cnefe_base AS {sql_base}")
    db.executar_sql(conn, "10_geocodificar.sql")
    with conn.cursor() as cur:
        cur.execute("DROP VIEW cnefe_base")


ALVO_EMPRESAS = """
    SELECT cnpj, norm_cep(cep), norm_logradouro(logradouro), norm_logradouro_completa(logradouro),
           norm_numero(numero), norm_nome(coalesce(nome_fantasia, razao_social)), norm_txt(bairro)
    FROM empresa
"""


def gravar_empresas(conn) -> None:
    geocodificar(conn, ALVO_EMPRESAS)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE empresa_geo")
        cur.execute("""
            INSERT INTO empresa_geo (cnpj, cep, logr_chave, logr_completa, numero, geo_precisao, geom)
            SELECT id, cep, logr_chave, logr_completa, numero, geo_precisao, geom FROM alvo
        """)
        cur.execute("ANALYZE empresa_geo")


def resumo(conn) -> list[tuple[str, int, int]]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT g.geo_precisao, count(*), count(*) FILTER (WHERE e.situacao_cadastral = '02')
            FROM empresa_geo g JOIN empresa e USING (cnpj)
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
    md += ["", "Acumulado = localizadas até aquele nível. `estabelecimento`, `endereco` e `numero_proximo` servem",
           "para análise por quadra; `logradouro*` para setor e bairro; `cep` e `bairro` só para bairro ou regional.",
           "O erro em metros de cada nível sai em `python -m etl.avaliar_geocodificacao`."]
    return "\n".join(md)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with db.etapa("geocodificar"), db.conectar() as conn:
        db.criar_schema(conn)
        if not db.contar(conn, "SELECT count(*) FROM cnefe"):
            raise SystemExit("cnefe vazio: rode antes python -m etl.fontes.ibge_cnefe")
        gravar_empresas(conn)
        linhas = resumo(conn)
        db.registrar(conn, "geocodificacao", linhas=sum(t for _, t, _ in linhas),
                     niveis={p: t for p, t, _ in linhas})
    md = relatorio(linhas)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "geocodificacao.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
