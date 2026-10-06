"""Indicadores do M2: saturação (QL), sobrevivência por coorte, densidade H3, movimentos e raio-x.

Uso:
    python -m etl.indicadores

Roda sql/40_m2.sql (depois do enriquecimento) e grava relatorios/indicadores.md.
O raio-x fica como função no banco:  SELECT * FROM raio_x(-25.4284, -49.2733, 250);
"""

import argparse
import logging

from etl import config, db

log = logging.getLogger("indicadores")


def resumo(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT bairro, divisao, coalesce(divisao_descricao, ''), ativos, ql FROM m2_saturacao_bairro
            WHERE ativos >= 10 ORDER BY ql DESC, bairro, divisao LIMIT 15
        """)
        polos = cur.fetchall()
        cur.execute("""
            SELECT coorte, abertas, sobrevivencia_1a, sobrevivencia_3a, sobrevivencia_5a FROM m2_sobrevivencia
            WHERE divisao IS NULL ORDER BY coorte DESC LIMIT 10
        """)
        coortes = cur.fetchall()
        cur.execute("SELECT count(*), max(ativos) FROM m2_densidade_h3 WHERE divisao IS NULL")
        hexes, pico = cur.fetchone()
        cur.execute("SELECT competencia, evento, count(*) FROM m2_movimento GROUP BY 1, 2 ORDER BY 1 DESC, 2 LIMIT 30")
        mov = cur.fetchall()
    md = [
        "# Indicadores do M2",
        "",
        "## Maiores concentrações (QL, bairro x divisão com 10+ ativas)",
        "",
        "| bairro | divisão | descrição | ativas | QL |",
        "|---|---|---|---:|---:|",
    ]
    md += [f"| {b} | {d} | {desc} | {n} | {ql} |" for b, d, desc, n, ql in polos]
    md += [
        "",
        "## Sobrevivência por coorte de abertura (todas as atividades)",
        "",
        "| coorte | abertas | 1 ano (%) | 3 anos (%) | 5 anos (%) |",
        "|---|---:|---:|---:|---:|",
    ]
    md += [f"| {c} | {n} | {s1 or ''} | {s3 or ''} | {s5 or ''} |" for c, n, s1, s3, s5 in coortes]
    md += [
        "",
        "## Densidade",
        "",
        f"{hexes} hexágonos H3 res 9 com empresas ativas; o mais denso tem {pico or 0}.",
        "",
    ]
    md += ["## Movimentos entre competências", ""]
    if mov:
        md += ["| competência | evento | CNPJs |", "|---|---|---:|"] + [f"| {c} | {e} | {n} |" for c, e, n in mov]
    else:
        md.append(
            "Ainda só uma competência em empresa_historico: os movimentos aparecem a partir da segunda foto mensal."
        )
    return "\n".join(md)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with db.etapa("indicadores"), db.conectar() as conn:
        db.criar_schema(conn)
        if not db.contar(
            conn, "SELECT count(*) FROM pg_tables WHERE tablename = 'empresa_perfil' AND schemaname = current_schema()"
        ):
            raise SystemExit("empresa_perfil não existe: rode antes python -m etl.enriquecer")
        db.executar_sql(conn, "40_m2.sql")
        md = resumo(conn)
        db.registrar(conn, "indicadores", linhas=db.contar(conn, "SELECT count(*) FROM m2_saturacao_bairro"))
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "indicadores.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
