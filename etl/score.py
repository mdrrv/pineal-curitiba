"""Risco de fechamento em 12 meses e score de lead por CNPJ ativo.

Uso:
    python -m etl.score

Risco (empresa_risco): taxa anual de fechamento observada nos 5 anos completos antes da data da base, por
divisão CNAE, faixa de idade e MEI, com encolhimento bayesiano para a faixa de idade (célula pequena puxa
para a média da faixa), vezes o fator do bairro (fechamentos observados / esperados, também encolhido para 1).
Exposta no ano: abriu antes de 1º de janeiro e estava ativa nesse dia; evento: baixa, inaptidão ou suspensão
dentro do ano.

Validação (modelo_validacao, modelo_calibracao): para cada um dos 3 anos antes da base, ajusta com os 5
anteriores e prevê o ano: AUC (0,5 = sorte, 1 = perfeito) e taxa prevista x observada por decil de risco.
Conferir antes de usar no produto.

Score (empresa_lead): soma dos pontos de lead_peso por critério (sql/80_score.sql), de 0 a 100.
Relatório em relatorios/score.md.
"""

import argparse
import logging

from etl import config, db

log = logging.getLogger("score")
K_CELULA = 50  # exposições "emprestadas" da faixa de idade para a célula
K_BAIRRO = 20  # fechamentos "emprestados" para o fator do bairro
OPCIONAIS = {
    "empresa_perfil": "cnpj VARCHAR(14)",
    "empresa_sinais": "cnpj VARCHAR(14)",
    "empresa_alvara": "cnpj VARCHAR(14)",
    "empresa_contratos_pmc": "cnpj VARCHAR(14)",
}

FAIXA = """CASE WHEN {i} < 1 THEN '0-1' WHEN {i} < 2 THEN '1-2' WHEN {i} < 3 THEN '2-3' WHEN {i} < 5 THEN '3-5'
                WHEN {i} < 10 THEN '5-10' ELSE '10+' END"""

EXPOSICAO = f"""
    DROP TABLE IF EXISTS _exp;
    CREATE TEMP TABLE _exp ON COMMIT DROP AS
    SELECT e.cnpj, y.ano, left(e.cnae_fiscal_principal, 2) AS divisao, coalesce(e.opcao_mei, 'N') = 'S' AS mei,
           g.bairro, {FAIXA.format(i="i.idade")} AS faixa,
           (e.situacao_cadastral <> '02' AND e.data_situacao_cadastral < make_date(y.ano + 1, 1, 1)) AS evento
    FROM empresa e
    LEFT JOIN empresa_geo g USING (cnpj)
    CROSS JOIN generate_series(%(ini)s, %(fim)s) y(ano)
    CROSS JOIN LATERAL (SELECT extract(YEAR FROM age(make_date(y.ano, 1, 1), e.data_inicio_atividade))::INT AS idade) i
    WHERE e.data_inicio_atividade < make_date(y.ano, 1, 1) AND e.cnae_fiscal_principal IS NOT NULL
      AND (e.situacao_cadastral = '02' OR e.data_situacao_cadastral >= make_date(y.ano, 1, 1));
"""

AJUSTE = f"""
    DROP TABLE IF EXISTS _hg, _h0, _h1, _mult;
    CREATE TEMP TABLE _hg ON COMMIT DROP AS
    SELECT coalesce(avg(evento::INT), 0)::NUMERIC AS h FROM _exp WHERE ano BETWEEN %(ini)s AND %(fim)s;
    CREATE TEMP TABLE _h0 ON COMMIT DROP AS
    SELECT faixa, mei, (sum(evento::INT) + {K_CELULA} * (SELECT h FROM _hg)) / (count(*) + {K_CELULA}) AS h
    FROM _exp WHERE ano BETWEEN %(ini)s AND %(fim)s GROUP BY 1, 2;
    CREATE TEMP TABLE _h1 ON COMMIT DROP AS
    SELECT x.divisao, x.faixa, x.mei, count(*) AS n,
           (sum(x.evento::INT) + {K_CELULA} * min(h0.h)) / (count(*) + {K_CELULA}) AS h
    FROM _exp x JOIN _h0 h0 USING (faixa, mei)
    WHERE x.ano BETWEEN %(ini)s AND %(fim)s GROUP BY 1, 2, 3;
    CREATE TEMP TABLE _mult ON COMMIT DROP AS
    SELECT x.bairro, (sum(x.evento::INT) + {K_BAIRRO}) / (sum(h1.h) + {K_BAIRRO}) AS m
    FROM _exp x JOIN _h1 h1 USING (divisao, faixa, mei)
    WHERE x.ano BETWEEN %(ini)s AND %(fim)s AND x.bairro IS NOT NULL GROUP BY 1;
"""

PREVER = """
    SELECT x.cnpj, x.divisao, x.faixa, h1.n,
           least(1, coalesce(h1.h, h0.h, (SELECT h FROM _hg)) * coalesce(mb.m, 1)) AS risco, mb.m, x.evento
    FROM {alvo} x
    LEFT JOIN _h1 h1 USING (divisao, faixa, mei)
    LEFT JOIN _h0 h0 USING (faixa, mei)
    LEFT JOIN _mult mb USING (bairro)
"""


def auc(pares: list[tuple[float, bool]]) -> float | None:
    """Área sob a curva ROC pelo teste de Mann-Whitney (empates com posto médio)."""
    pos = sum(1 for _, e in pares if e)
    neg = len(pares) - pos
    if not pos or not neg:
        return None
    ordenado = sorted(pares, key=lambda p: p[0])
    soma_postos, i = 0.0, 0
    while i < len(ordenado):
        j = i
        while j < len(ordenado) and ordenado[j][0] == ordenado[i][0]:
            j += 1
        posto = (i + 1 + j) / 2
        soma_postos += posto * sum(1 for k in range(i, j) if ordenado[k][1])
        i = j
    return round((soma_postos - pos * (pos + 1) / 2) / (pos * neg), 4)


def ano_base(conn) -> int:
    return db.contar(
        conn,
        "SELECT extract(YEAR FROM greatest(max(data_inicio_atividade), max(data_situacao_cadastral)))::INT FROM empresa",
    )


def validar(conn, base: int) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS modelo_validacao, modelo_calibracao")
        cur.execute("""CREATE TABLE modelo_validacao (ano INT PRIMARY KEY, expostos INT, eventos INT,
                       taxa_observada NUMERIC, taxa_prevista NUMERIC, auc NUMERIC)""")
        cur.execute("""CREATE TABLE modelo_calibracao (ano INT, decil INT, n INT, prevista NUMERIC, observada NUMERIC,
                       PRIMARY KEY (ano, decil))""")
        for alvo in range(base - 3, base):
            params = {"ini": alvo - 5, "fim": alvo - 1}
            cur.execute(EXPOSICAO, {"ini": alvo - 5, "fim": alvo})
            cur.execute(AJUSTE, params)
            cur.execute(PREVER.format(alvo=f"(SELECT * FROM _exp WHERE ano = {int(alvo)})"))
            linhas = cur.fetchall()
            if not linhas:
                continue
            pares = [(float(r[4]), r[6]) for r in linhas]
            eventos = sum(e for _, e in pares)
            cur.execute(
                "INSERT INTO modelo_validacao VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    alvo,
                    len(pares),
                    eventos,
                    round(eventos / len(pares), 4),
                    round(sum(p for p, _ in pares) / len(pares), 4),
                    auc(pares),
                ),
            )
            pares.sort(key=lambda p: p[0])
            for d in range(10):
                fatia = pares[d * len(pares) // 10 : (d + 1) * len(pares) // 10]
                if fatia:
                    cur.execute(
                        "INSERT INTO modelo_calibracao VALUES (%s, %s, %s, %s, %s)",
                        (
                            alvo,
                            d + 1,
                            len(fatia),
                            round(sum(p for p, _ in fatia) / len(fatia), 4),
                            round(sum(e for _, e in fatia) / len(fatia), 4),
                        ),
                    )
        cur.execute("SELECT * FROM modelo_validacao ORDER BY ano")
        return cur.fetchall()


def risco_atual(conn, base: int) -> int:
    with conn.cursor() as cur:
        cur.execute(EXPOSICAO, {"ini": base - 5, "fim": base - 1})
        cur.execute(AJUSTE, {"ini": base - 5, "fim": base - 1})
        cur.execute(f"""
            CREATE TEMP TABLE _ativa ON COMMIT DROP AS
            SELECT e.cnpj, left(e.cnae_fiscal_principal, 2) AS divisao, coalesce(e.opcao_mei, 'N') = 'S' AS mei, g.bairro,
                   {FAIXA.format(i="extract(YEAR FROM age(r.d, e.data_inicio_atividade))")} AS faixa, NULL::BOOLEAN AS evento
            FROM empresa e LEFT JOIN empresa_geo g USING (cnpj)
            CROSS JOIN (SELECT greatest(max(data_inicio_atividade), max(data_situacao_cadastral)) AS d FROM empresa) r
            WHERE e.situacao_cadastral = '02' AND e.data_inicio_atividade IS NOT NULL AND e.cnae_fiscal_principal IS NOT NULL
        """)
        cur.execute("DROP TABLE IF EXISTS empresa_risco")
        cur.execute(f"""
            CREATE TABLE empresa_risco AS
            SELECT cnpj, divisao, faixa AS faixa_idade, n AS celula_expostos, round(risco, 4) AS risco_12m,
                   round(m, 3) AS fator_bairro
            FROM ({PREVER.format(alvo="_ativa")}) p
        """)
        n = cur.rowcount
        cur.execute("ALTER TABLE empresa_risco ADD PRIMARY KEY (cnpj)")
        return n


def resumo(conn, validacao) -> str:
    with conn.cursor() as cur:
        cur.execute("""SELECT width_bucket(score, 0, 100, 5), count(*), round(avg(risco_12m), 4)
                       FROM empresa_lead GROUP BY 1 ORDER BY 1""")
        faixas = cur.fetchall()
        cur.execute("""SELECT c, count(*) FROM empresa_lead, unnest(criterios) c GROUP BY 1 ORDER BY 2 DESC""")
        criterios = cur.fetchall()
    md = [
        "# Risco de fechamento e score de lead",
        "",
        "## Validação do risco (ajuste nos 5 anos anteriores, previsão do ano)",
        "",
        "| ano | expostas | fecharam | taxa observada | taxa prevista | AUC |",
        "|---|---:|---:|---:|---:|---:|",
        *[f"| {a} | {n} | {e} | {o} | {p} | {u if u is not None else '-'} |" for a, n, e, o, p, u in validacao],
        "",
        "Calibração por decil de risco em `modelo_calibracao`.",
        "",
        "## Score de lead (empresas ativas)",
        "",
        "| faixa de score | empresas | risco médio 12 meses |",
        "|---|---:|---:|",
        *[f"| {(b - 1) * 20}-{min(b * 20, 100)} | {n} | {r} |" for b, n, r in faixas],
        "",
        "| critério | empresas |",
        "|---|---:|",
        *[f"| {c} | {n} |" for c, n in criterios],
    ]
    return "\n".join(md)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with db.etapa("score"), db.conectar() as conn:
        db.criar_schema(conn)
        with conn.cursor() as cur:
            for tabela, colunas in OPCIONAIS.items():
                cur.execute("SELECT to_regclass(%s)", (tabela,))
                if cur.fetchone()[0] is None:
                    cur.execute(f"CREATE TEMP TABLE {tabela} ({colunas}) ON COMMIT DROP")
        base = ano_base(conn)
        validacao = validar(conn, base)
        n = risco_atual(conn, base)
        log.info("risco calculado para %d empresas ativas (base %s)", n, base)
        db.executar_sql(conn, "80_score.sql")
        md = resumo(conn, validacao)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "score.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
