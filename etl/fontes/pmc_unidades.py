"""Unidades de Atendimento de Curitiba (ativas): equipamentos públicos e privados, geocodificados.

Uso:
    python -m etl.fontes.pmc_unidades [--arquivo base.csv]

A base traz rua, número e bairro, sem CEP nem coordenada: a geocodificação usa os níveis sem CEP do
núcleo (logradouro e número na cidade, logradouro único, bairro). Grava unidade_atendimento, com o
hexágono H3 res 9, para servir de polo de atração nas análises de ponto.
"""

import argparse
import logging

import h3

from etl import config, db, leitura, portal
from etl.geocodificar import geocodificar

log = logging.getLogger("pmc_unidades")
FONTE = "pmc_unidades"
COLUNAS = {
    "CD_EQUI": "codigo",
    "NM_EQUI": "nome",
    "DS_TEMA": "tema",
    "DS_TP_EQUIPAMENTO": "tipo",
    "DS_SUBTIPO_EQUIPAMENTO": "subtipo",
    "DS_DEP_ADMINISTRATIVA": "dependencia",
    "FUNCIONAMENTO_MANHA_EQUI": "manha",
    "FUNCIONAMENTO_TARDE_EQUI": "tarde",
    "FUNCIONAMENTO_NOITE_EQUI": "noite",
    "FUNCIONAMENTO_24HRS_EQUI": "h24",
    "NM_RUA": "rua",
    "NUMERO_EQUI": "numero",
    "NM_BAIRRO": "bairro",
    "NM_REGIONAL": "regional",
}


def carregar(conn, caminho) -> int:
    leitura.copiar_para_temp(conn, caminho, "un_carga", COLUNAS, obrigatorias=["CD_EQUI", "NM_RUA", "NM_BAIRRO"])
    with conn.cursor() as cur:
        cur.execute("TRUNCATE unidade_atendimento")
        cur.execute("""
            INSERT INTO unidade_atendimento (codigo, nome, tema, tipo, subtipo, dependencia, turnos, logradouro,
                                             numero, bairro, regional)
            SELECT DISTINCT ON (codigo) codigo, NULLIF(btrim(nome), ''), NULLIF(btrim(tema), ''), NULLIF(btrim(tipo), ''),
                   NULLIF(btrim(subtipo), ''), NULLIF(btrim(dependencia), ''),
                   NULLIF(concat_ws(',', CASE WHEN upper(manha) IN ('S', 'SIM', '1', 'TRUE') THEN 'manha' END,
                                         CASE WHEN upper(tarde) IN ('S', 'SIM', '1', 'TRUE') THEN 'tarde' END,
                                         CASE WHEN upper(noite) IN ('S', 'SIM', '1', 'TRUE') THEN 'noite' END,
                                         CASE WHEN upper(h24) IN ('S', 'SIM', '1', 'TRUE') THEN '24h' END), ''),
                   NULLIF(btrim(rua), ''), NULLIF(btrim(numero), ''), NULLIF(btrim(bairro), ''), NULLIF(btrim(regional), '')
            FROM un_carga WHERE NULLIF(btrim(codigo), '') IS NOT NULL
            ORDER BY codigo
        """)
        n = cur.rowcount
        cur.execute("DROP TABLE un_carga")
    return n


def geocodificar_unidades(conn) -> None:
    geocodificar(
        conn,
        """
        SELECT codigo, NULL, norm_logradouro(logradouro), norm_logradouro_completa(logradouro), norm_numero(numero),
               norm_nome(nome), norm_txt(bairro)
        FROM unidade_atendimento
    """,
    )
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE unidade_atendimento u SET geo_precisao = a.geo_precisao, geom = a.geom FROM alvo a WHERE a.id = u.codigo"
        )
        cur.execute("DROP TABLE alvo")
        cur.execute("SELECT codigo, ST_Y(geom), ST_X(geom) FROM unidade_atendimento WHERE geom IS NOT NULL")
        h3s = [(h3.latlng_to_cell(lat, lon, 9), c) for c, lat, lon in cur.fetchall()]
        cur.executemany("UPDATE unidade_atendimento SET h3_9 = %s WHERE codigo = %s", h3s)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo")
    args = ap.parse_args(argv)
    with db.etapa("unidades"), db.conectar() as conn:
        db.criar_schema(conn)
        caminho, origem = portal.obter(FONTE, r"Unidades.*Base_de_Dados", args.arquivo)
        n = carregar(conn, caminho)
        if db.contar(conn, "SELECT count(*) FROM cnefe"):
            geocodificar_unidades(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT geo_precisao, count(*) FROM unidade_atendimento GROUP BY 1 ORDER BY 2 DESC")
            niveis = cur.fetchall()
            cur.execute("SELECT tema, count(*) FROM unidade_atendimento GROUP BY 1 ORDER BY 2 DESC LIMIT 15")
            temas = cur.fetchall()
        db.registrar(conn, FONTE, origem, caminho.name, linhas=n, niveis=dict(niveis))
    md = ["# Unidades de atendimento", "", f"{n} unidades.", "", "| geocodificação | unidades |", "|---|---:|"]
    md += [f"| {p} | {q} |" for p, q in niveis]
    md += ["", "| tema | unidades |", "|---|---:|"] + [f"| {t} | {q} |" for t, q in temas]
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "unidades.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
