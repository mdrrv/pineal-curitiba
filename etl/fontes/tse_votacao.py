"""Votação por seção eleitoral do TSE (módulo ME): votos por ano, turno, cargo e votável.

Uso:
    python -m etl.fontes.tse_votacao [--arquivo votacao_secao_2024_PR.zip ...]

Sem --arquivo, usa os arquivos em dados/bruto/tse_votacao_secao/ ou baixa, do CDN do TSE, os anos do
catálogo (um zip por ano e UF). Ficam só as seções do município. NR_VOTAVEL com 2 dígitos é voto de
legenda; 95/96/97 são brancos/nulos/anulados. Aptos, comparecimento e abstenções vêm repetidos por
votável: fica o máximo da seção. Depois sql/90_eleitoral.sql refaz a ponte e os agregados por bairro.
"""

import argparse
import logging

from etl import baixar, db, leitura
from etl.fontes import tse_comum

log = logging.getLogger("tse_votacao")
FONTE = "tse_votacao_secao"

COLUNAS = {
    "ANO_ELEICAO": "ano",
    "NR_TURNO": "turno",
    "SG_UF": "uf",
    "CD_MUNICIPIO": "cd_mun",
    "NM_MUNICIPIO": "nm_mun",
    "NR_ZONA": "zona",
    "NR_SECAO": "secao",
    "CD_CARGO": "cd_cargo",
    "DS_CARGO": "cargo",
    "NR_VOTAVEL": "votavel",
    "NM_VOTAVEL": "nm_votavel",
    "QT_VOTOS": "votos",
    "QT_APTOS": "aptos",
    "QT_COMPARECIMENTO": "comparecimento",
    "QT_ABSTENCOES": "abstencoes",
}
OBRIGATORIAS = ["ANO_ELEICAO", "NR_TURNO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "NR_VOTAVEL", "QT_VOTOS"]

INT = "CASE WHEN btrim({c}) ~ '^-?\\d+$' THEN btrim({c})::INT END"

INSERIR = f"""
    INSERT INTO eleicao_votacao_secao (ano, turno, nr_zona, nr_secao, cd_cargo, cargo, nr_votavel, nm_votavel,
                                       votos, aptos, comparecimento, abstencoes)
    SELECT ano_n, turno_n, zona_n, secao_n, cargo_n, min(NULLIF(btrim(cargo), '')), votavel_n,
           min(NULLIF(btrim(nm_votavel), '')), sum(votos_n),
           max({INT.format(c="aptos")}), max({INT.format(c="comparecimento")}), max({INT.format(c="abstencoes")})
    FROM (
        SELECT t.*, {INT.format(c="ano")} AS ano_n, {INT.format(c="turno")} AS turno_n,
               {INT.format(c="zona")} AS zona_n, {INT.format(c="secao")} AS secao_n,
               {INT.format(c="cd_cargo")} AS cargo_n, {INT.format(c="votavel")} AS votavel_n,
               {INT.format(c="votos")} AS votos_n
        FROM vs t
        WHERE {tse_comum.FILTRO_MUNICIPIO}
    ) t
    WHERE ano_n IS NOT NULL AND turno_n IS NOT NULL AND zona_n IS NOT NULL AND secao_n IS NOT NULL
      AND cargo_n IS NOT NULL AND votavel_n IS NOT NULL AND votos_n IS NOT NULL
    GROUP BY ano_n, turno_n, zona_n, secao_n, cargo_n, votavel_n
"""


def carregar(conn, caminho) -> tuple[int | None, int]:
    leitura.copiar_para_temp(conn, caminho, "vs", COLUNAS, OBRIGATORIAS)
    ano = tse_comum.ano_do_nome(caminho.name)
    with conn.cursor() as cur:
        if ano:
            cur.execute("DELETE FROM eleicao_votacao_secao WHERE ano = %s", (ano,))
        else:
            cur.execute(
                f"DELETE FROM eleicao_votacao_secao WHERE ano IN (SELECT DISTINCT {INT.format(c='ano')} FROM vs)"
            )
        cur.execute(INSERIR, tse_comum.parametros_municipio())
        n = cur.rowcount
        cur.execute("DROP TABLE vs")
    return ano, n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", action="append", help="zip ou csv de um ano (repetível)")
    args = ap.parse_args(argv)
    with db.etapa("tse_votacao"), db.conectar() as conn:
        db.criar_schema(conn)
        total = 0
        for caminho in tse_comum.obter_arquivos(FONTE, args.arquivo):
            ano, n = carregar(conn, caminho)
            total += n
            db.registrar(conn, FONTE, str(caminho), caminho.name, baixar.sha256(caminho), n, ano=ano)
            log.info("%s: %d linhas de votação", caminho.name, n)
        db.executar_sql(conn, "90_eleitoral.sql")
        anos = db.contar(conn, "SELECT count(DISTINCT ano) FROM eleicao_votacao_secao")
    log.info("%d linhas carregadas; %d eleições no banco", total, anos)


if __name__ == "__main__":
    main()
