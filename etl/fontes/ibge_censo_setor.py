"""Censo 2022, agregados por setor censitário (IBGE): demanda por setor, hexágono e bairro.

Uso:
    python -m etl.fontes.ibge_censo_setor [--arquivo a.zip --arquivo b.zip ...]

Sem --arquivo, usa os arquivos em dados/bruto/ibge_censo_setor/ ou baixa, do FTP do IBGE, um por tema de
TEMAS (Agregados_por_setores_<tema>_BR*.zip). Os arquivos são nacionais; ficam só os setores do município.
O tema sai do nome do arquivo. Toda coluna V#### (e AREA_KM2) vai para censo_setor_var; censo_variavel diz
quais viram indicador (conferir os códigos no dicionário de cada tema; a tabela é editável).

A população do setor é distribuída pelos endereços de domicílio do CNEFE (espécies 1 e 2), o que dá
moradores por hexágono (demanda_h3) e moradores num raio (moradores_raio, raio_x). Depois roda
sql/70_demanda.sql: setor_demografia, demanda_h3 e m2_espaco_livre. Relatório em relatorios/demanda.md.
"""

import argparse
import csv
import logging
import re
import tempfile
from collections import Counter
from pathlib import Path

import h3

from etl import baixar, config, db, leitura

log = logging.getLogger("ibge_censo_setor")
FONTE = "ibge_censo_setor"
TEMAS = ["basico", "demografia", "renda_responsavel"]
VARIAVEL = re.compile(r"^(V\d+|AREA_KM2)$")


def tema_de(nome: str) -> str:
    m = re.search(r"Agregados_por_setores_(.+?)_BR", nome, re.I)
    return (m.group(1) if m else Path(nome).stem).lower()


def obter_arquivos(arquivos: list[str] | None) -> list[Path]:
    if arquivos:
        return [Path(a) for a in arquivos]
    pasta = config.DADOS_BRUTO / FONTE
    locais = sorted(p for p in pasta.glob("*") if p.suffix.lower() in (".zip", ".csv")) if pasta.exists() else []
    if locais:
        return locais
    f = config.fonte(FONTE)
    saida = []
    for tema in TEMAS:
        url = baixar.resolver_no_diretorio(f["url_diretorio"], rf"^Agregados_por_setores_{tema}_BR.*\.zip$")
        saida.append(baixar.baixar(url, FONTE))
    return saida


def setor_digitos(t: str | None) -> str:
    return re.sub(r"\D", "", t or "")[:15]


def carregar(conn, caminho: Path) -> tuple[str, int]:
    tema = tema_de(caminho.name)
    n_setores = 0
    with (
        leitura.ler_csv(caminho, ["CD_SETOR"]) as leitor,
        tempfile.TemporaryFile("w+", encoding="utf-8", newline="") as tmp,
    ):
        variaveis = [c for c in leitor.fieldnames if c and VARIAVEL.match(c)]
        w = csv.writer(tmp)
        for r in leitor:
            cd = setor_digitos(r["CD_SETOR"])
            mun = (r.get("CD_MUN") or "").strip() or cd[:7]
            if mun != config.COD_IBGE or len(cd) != 15:
                continue
            n_setores += 1
            for v in variaveis:
                w.writerow([cd, v, (r.get(v) or "").strip()])
        tmp.seek(0)
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE censo_carga (cd_setor TEXT, variavel TEXT, valor TEXT) ON COMMIT DROP")
            cur.copy_expert("COPY censo_carga FROM STDIN WITH (FORMAT csv)", tmp)
            cur.execute("DELETE FROM censo_setor_var WHERE tema = %s", (tema,))
            cur.execute(
                """
                INSERT INTO censo_setor_var (cd_setor, tema, variavel, valor)
                SELECT DISTINCT ON (cd_setor, variavel) cd_setor, %s, variavel,
                       CASE WHEN valor ~ '^-?\\d+(,\\d+)?$' THEN replace(valor, ',', '.')::NUMERIC
                            WHEN valor ~ '^-?\\d+(\\.\\d+)?$' THEN valor::NUMERIC END
                FROM censo_carga
                """,
                (tema,),
            )
            cur.execute("DROP TABLE censo_carga")
    log.info("%s: %d setores, %d variáveis", tema, n_setores, len(variaveis))
    return tema, n_setores


def domicilios_h3(conn) -> int:
    """Endereços de domicílio do CNEFE por setor e hexágono r9."""
    conta: Counter = Counter()
    with conn.cursor(name="cnefe_dom") as cur:
        cur.itersize = 50000
        cur.execute(
            "SELECT cd_setor, ST_Y(geom), ST_X(geom) FROM cnefe WHERE especie IN (1, 2) AND cd_setor IS NOT NULL"
        )
        for cd, lat, lon in cur:
            conta[(setor_digitos(cd), h3.latlng_to_cell(lat, lon, 9))] += 1
    com_domicilio = {s for s, _ in conta}
    with conn.cursor() as cur:
        # setor sem domicílio no CNEFE: a população vai inteira para o hexágono do ponto interno do setor
        cur.execute(r"""SELECT left(regexp_replace(cd_setor, '\D', '', 'g'), 15), ST_Y(p), ST_X(p)
                        FROM (SELECT cd_setor, ST_PointOnSurface(geom) AS p FROM setor) s""")
        for cd, lat, lon in cur.fetchall():
            if cd not in com_domicilio:
                conta[(cd, h3.latlng_to_cell(lat, lon, 9))] = 0
        cur.execute("TRUNCATE setor_h3_domicilio")
        cur.executemany(
            "INSERT INTO setor_h3_domicilio (cd_setor, h3_9, enderecos) VALUES (%s, %s, %s)",
            [(s, h, n) for (s, h), n in conta.items()],
        )
    return sum(conta.values())


def resumo(conn, temas: dict[str, int]) -> str:
    with conn.cursor() as cur:
        cur.execute("""SELECT count(*), sum(pessoas), sum(domicilios_ocupados), count(*) FILTER (WHERE bairro IS NULL),
                              count(*) FILTER (WHERE domicilios_cnefe = 0)
                       FROM setor_demografia""")
        setores, pessoas, domicilios, sem_bairro, sem_cnefe = cur.fetchone()
        cur.execute("""
            SELECT cv.tema, cv.variavel, cv.indicador FROM censo_variavel cv
            WHERE cv.tema IN (SELECT DISTINCT tema FROM censo_setor_var)
              AND NOT EXISTS (SELECT 1 FROM censo_setor_var x WHERE x.tema = cv.tema AND x.variavel = cv.variavel)
            ORDER BY 1, 2
        """)
        faltando = cur.fetchall()
        cur.execute("SELECT count(*), sum(moradores) FROM demanda_h3")
        hexes, mor_h3 = cur.fetchone()
        cur.execute("""
            SELECT bairro, classe, classe_descricao, ativos, esperado, lacuna FROM m2_espaco_livre
            WHERE esperado >= 3 ORDER BY lacuna DESC, bairro, classe LIMIT 20
        """)
        lacunas = cur.fetchall()
    md = [
        "# Demanda: Censo 2022 por setor",
        "",
        f"- Temas carregados: {', '.join(f'{t} ({n} setores)' for t, n in temas.items())}",
        f"- Setores com indicador: {setores}; moradores: {pessoas}; domicílios ocupados: {domicilios}",
        f"- Setores sem bairro (sem malha ou fora dos bairros): {sem_bairro}; sem domicílio no CNEFE: {sem_cnefe}",
        f"- Hexágonos com moradores: {hexes} ({mor_h3} moradores distribuídos)",
        "",
    ]
    if faltando:
        md += [
            "## Variáveis mapeadas que não vieram (conferir censo_variavel com o dicionário)",
            "",
            *[f"- {t}.{v} ({i})" for t, v, i in faltando],
            "",
        ]
    md += [
        "## Maiores lacunas de oferta por bairro (empresas esperadas pela média da cidade menos as ativas)",
        "",
        "| bairro | classe | atividade | ativas | esperadas | lacuna |",
        "|---|---|---|---:|---:|---:|",
        *[f"| {b} | {c} | {d or ''} | {a} | {e} | {la} |" for b, c, d, a, e, la in lacunas],
    ]
    return "\n".join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", action="append", help="zip ou csv de um tema (repetível)")
    args = ap.parse_args(argv)
    with db.etapa("censo"):
        arquivos = obter_arquivos(args.arquivo)
        with db.conectar() as conn:
            db.criar_schema(conn)
            temas = {}
            for a in arquivos:
                tema, n = carregar(conn, a)
                temas[tema] = n
                db.registrar(conn, FONTE, str(a), a.name, baixar.sha256(a), n, tema=tema)
            n = domicilios_h3(conn)
            log.info("%d endereços de domicílio do CNEFE distribuídos", n)
            with conn.cursor() as cur:  # rodado antes do enriquecimento: espaço livre sem filtro de domiciliação
                cur.execute("SELECT to_regclass('empresa_perfil')")
                if cur.fetchone()[0] is None:
                    cur.execute(
                        "CREATE TEMP TABLE empresa_perfil (cnpj VARCHAR(14), domiciliacao BOOLEAN) ON COMMIT DROP"
                    )
            db.executar_sql(conn, "70_demanda.sql")
            md = resumo(conn, temas)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "demanda.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
