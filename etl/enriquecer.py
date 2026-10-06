"""Informação nova a partir do M0: tipo do ponto, domiciliação, rede, histórico do ponto e uso x zoneamento.

Uso:
    python -m etl.enriquecer

Roda sql/30_enriquecimento.sql e grava relatorios/enriquecimento.md.
"""

import argparse
import logging

from etl import config, db

log = logging.getLogger("enriquecer")


def resumo(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.tipo_ponto, count(*) FROM empresa_perfil p JOIN empresa e USING (cnpj)
            WHERE e.situacao_cadastral = '02' GROUP BY 1 ORDER BY 2 DESC
        """)
        tipos = cur.fetchall()
        cur.execute("""
            SELECT count(*) FILTER (WHERE p.domiciliacao), count(DISTINCT p.endereco_chave) FILTER (WHERE p.domiciliacao),
                   count(*) FILTER (WHERE p.filial), count(DISTINCT e.cnpj_basico) FILTER (WHERE p.ativos_da_raiz_na_cidade >= 5)
            FROM empresa_perfil p JOIN empresa e USING (cnpj) WHERE e.situacao_cadastral = '02'
        """)
        dom, dom_end, filiais, redes = cur.fetchone()
        cur.execute("""
            SELECT count(*), count(*) FILTER (WHERE vago), round(avg(cnpjs_por_ano), 2) FROM ponto_comercial
        """)
        pontos, vagos, rot = cur.fetchone()
        cur.execute(
            "SELECT count(*), count(*) FILTER (WHERE permitido IS FALSE) FROM uso_zoneamento WHERE permitido IS NOT NULL"
        )
        com_regra, fora = cur.fetchone()
    md = ["# Enriquecimento", "", "## Tipo do ponto (empresas ativas)", "", "| tipo | ativas |", "|---|---:|"]
    md += [f"| {t} | {n} |" for t, n in tipos]
    md += [
        "",
        "`comercial`: o endereço só tem estabelecimentos no CNEFE; `residencial`: só domicílios (empresa em casa);",
        "`misto`: os dois (prédio com loja e apartamentos); `desconhecido`: sem número ou fora do CNEFE.",
        "",
        "## Outros sinais (empresas ativas)",
        "",
        f"- Em endereço de domiciliação (20+ CNPJs ativos no mesmo endereço): {dom}, em {dom_end} endereços",
        f"- Filiais: {filiais}",
        f"- Redes com 5+ estabelecimentos ativos na cidade: {redes}",
        f"- Pontos comerciais (endereços com CNPJ): {pontos}; vagos nos últimos 3 anos: {vagos}; "
        f"média de {rot or 0} CNPJs por ano por ponto",
        f"- Uso x zoneamento: {com_regra} empresas com regra em zona_regra, {fora} fora do uso permitido",
    ]
    return "\n".join(md)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with db.etapa("enriquecer"), db.conectar() as conn:
        db.criar_schema(conn)
        if not db.contar(conn, "SELECT count(*) FROM empresa_geo"):
            raise SystemExit("empresa_geo vazio: rode antes o M0 (python -m etl.m0)")
        db.executar_sql(conn, "30_enriquecimento.sql")
        md = resumo(conn)
        db.registrar(conn, "enriquecimento", linhas=db.contar(conn, "SELECT count(*) FROM empresa_perfil"))
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "enriquecimento.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
