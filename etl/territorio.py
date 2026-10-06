"""Atribui a chave territorial (setor, bairro, regional, zona, H3 res 8 e 9) às empresas geocodificadas.

Uso:
    python -m etl.territorio
"""
import argparse
import io
import logging

import h3

from etl import config, db

log = logging.getLogger("territorio")

LOTE = 50_000


def gravar_h3(conn) -> int:
    n = 0
    with conn.cursor(name="pontos") as leitura, conn.cursor() as escrita:
        escrita.execute("CREATE TEMP TABLE h3_carga (cnpj VARCHAR(14), h3_8 TEXT, h3_9 TEXT) ON COMMIT DROP")
        leitura.itersize = LOTE
        leitura.execute("SELECT cnpj, ST_Y(geom), ST_X(geom) FROM cwb.empresa_geo WHERE geom IS NOT NULL")
        while True:
            lote = leitura.fetchmany(LOTE)
            if not lote:
                break
            buf = io.StringIO()
            for cnpj, lat, lon in lote:
                buf.write(f"{cnpj}\t{h3.latlng_to_cell(lat, lon, 8)}\t{h3.latlng_to_cell(lat, lon, 9)}\n")
            buf.seek(0)
            escrita.copy_expert("COPY h3_carga FROM STDIN", buf)
            n += len(lote)
        escrita.execute("""
            UPDATE cwb.empresa_geo g SET h3_8 = c.h3_8, h3_9 = c.h3_9
            FROM h3_carga c WHERE g.cnpj = c.cnpj
        """)
    return n


def resumo(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FILTER (WHERE geom IS NOT NULL),
                   count(cd_setor), count(bairro), count(regional), count(zona), count(h3_9)
            FROM cwb.empresa_geo
        """)
        geo, setor, bairro, regional, zona, h3_9 = cur.fetchone()
    base = geo or 1
    linhas = [("setor", setor), ("bairro", bairro), ("regional", regional), ("zona", zona), ("h3", h3_9)]
    md = ["# Chave territorial", "", f"Empresas geocodificadas: {geo}", "",
          "| camada | com chave | % das geocodificadas |", "|---|---:|---:|"]
    md += [f"| {c} | {v} | {100 * v / base:.1f} |" for c, v in linhas]
    md += ["", "Camada com 0% normalmente é camada ainda não carregada (ver `python -m etl.fontes.ippuc --listar`)."]
    return "\n".join(md)


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    with db.conectar() as conn:
        db.criar_schema(conn)
        db.executar_sql(conn, "20_territorio.sql")
        n = gravar_h3(conn)
        log.info("h3 calculado para %d empresas", n)
        md = resumo(conn)
        db.registrar(conn, "territorio", linhas=n)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "territorio.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
