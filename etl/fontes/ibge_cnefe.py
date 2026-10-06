"""CNEFE 2022 (IBGE): endereços com coordenada, recortados para o município.

Uso:
    python -m etl.fontes.ibge_cnefe [--arquivo caminho.zip|.csv]

Sem --arquivo, acha o arquivo do município na listagem do FTP do IBGE (url_diretorio + padrao_arquivo).
Aceita o arquivo do município ou o da UF inteira (filtra por COD_MUNICIPIO).
"""
import argparse
import csv
import io
import logging
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

from etl import baixar, config, db

log = logging.getLogger("ibge_cnefe")
FONTE = "ibge_cnefe"

OBRIGATORIAS = ["COD_UNICO_ENDERECO", "COD_SETOR", "CEP", "NOM_SEGLOGR", "NUM_ENDERECO", "LATITUDE", "LONGITUDE"]
SAIDA = ["cod_unico", "cd_setor", "cep", "tipo", "titulo", "nome", "numero", "lat", "lon", "especie", "estabelecimento", "nv_geo"]


def obter_arquivo(arquivo: str | None) -> tuple[Path, str]:
    if arquivo:
        return Path(arquivo), arquivo
    local = baixar.arquivo_local(FONTE, r"\.(zip|csv)$")
    if local:
        return local, str(local)
    f = config.fonte(FONTE)
    url = baixar.resolver_no_diretorio(f["url_diretorio"], f["padrao_arquivo"])
    return baixar.baixar(url, FONTE), url


@contextmanager
def abrir_texto(caminho: Path):
    """Abre o CSV (solto ou dentro do zip) como texto, detectando UTF-8 ou Latin-1."""
    if caminho.suffix.lower() == ".zip":
        z = zipfile.ZipFile(caminho)
        nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not nomes:
            raise ValueError(f"nenhum .csv dentro de {caminho.name}")
        abrir_bin = lambda: z.open(nomes[0])  # noqa: E731
    else:
        z = None
        abrir_bin = lambda: open(caminho, "rb")  # noqa: E731
    with abrir_bin() as b:
        amostra = b.read(1 << 20)
    try:
        amostra.decode("utf-8")
        enc = "utf-8-sig"
    except UnicodeDecodeError:
        enc = "latin-1"
    b = abrir_bin()
    try:
        yield io.TextIOWrapper(b, encoding=enc, newline="")
    finally:
        b.close()
        if z:
            z.close()


def _num(v: str) -> str:
    return (v or "").strip().replace(",", ".")


def linhas_saida(leitor: csv.DictReader, cod_ibge: str):
    for r in leitor:
        mun = r.get("COD_MUNICIPIO")
        if mun and mun.strip() != cod_ibge:
            continue
        lat, lon = _num(r["LATITUDE"]), _num(r["LONGITUDE"])
        if not lat or not lon:
            continue
        yield [
            r["COD_UNICO_ENDERECO"].strip(),
            r["COD_SETOR"].strip(),
            r["CEP"],
            r.get("NOM_TIPO_SEGLOGR", ""),
            r.get("NOM_TITULO_SEGLOGR", ""),
            r["NOM_SEGLOGR"],
            r["NUM_ENDERECO"],
            lat,
            lon,
            (r.get("COD_ESPECIE") or "").strip(),
            r.get("DSC_ESTABELECIMENTO", ""),
            (r.get("NV_GEO_COORD") or "").strip(),
        ]


def carregar(conn, caminho: Path, origem: str) -> int:
    with abrir_texto(caminho) as txt:
        primeira = txt.readline()
        sep = ";" if primeira.count(";") >= primeira.count(",") else ","
        cab = [c.strip().upper() for c in next(csv.reader([primeira], delimiter=sep))]
        faltando = [c for c in OBRIGATORIAS if c not in cab]
        if faltando:
            raise ValueError(f"colunas obrigatórias ausentes no CNEFE: {faltando}. Cabeçalho: {cab}")
        leitor = csv.DictReader(txt, fieldnames=cab, delimiter=sep)

        with tempfile.TemporaryFile("w+", encoding="utf-8", newline="") as tmp:
            w = csv.writer(tmp)
            n = 0
            for linha in linhas_saida(leitor, config.COD_IBGE):
                w.writerow(linha)
                n += 1
            tmp.seek(0)
            log.info("%d endereços do município lidos; gravando", n)
            with conn.cursor() as cur:
                cur.execute(f"CREATE TEMP TABLE cnefe_carga ({', '.join(c + ' TEXT' for c in SAIDA)}) ON COMMIT DROP")
                cur.copy_expert(f"COPY cnefe_carga ({', '.join(SAIDA)}) FROM STDIN WITH (FORMAT csv)", tmp)
                cur.execute("TRUNCATE cnefe")
                cur.execute("""
                    INSERT INTO cnefe (cod_unico, cd_setor, cep, logradouro, logr_chave, logr_completa, numero,
                                       especie, estabelecimento, nome_chave, nv_geo, geom)
                    SELECT cod_unico, cd_setor, norm_cep(cep),
                           NULLIF(concat_ws(' ', NULLIF(btrim(tipo), ''), NULLIF(btrim(titulo), ''), NULLIF(btrim(nome), '')), ''),
                           norm_logradouro(concat_ws(' ', tipo, titulo, nome)),
                           norm_logradouro_completa(concat_ws(' ', tipo, titulo, nome)),
                           norm_numero(numero),
                           NULLIF(especie, '')::SMALLINT,
                           NULLIF(btrim(estabelecimento), ''),
                           norm_nome(estabelecimento),
                           NULLIF(nv_geo, '')::SMALLINT,
                           ST_SetSRID(ST_MakePoint(lon::float8, lat::float8), 4326)
                    FROM cnefe_carga
                    WHERE lat ~ '^-?[0-9.]+$' AND lon ~ '^-?[0-9.]+$'
                    ON CONFLICT (cod_unico) DO NOTHING
                """)
                gravadas = cur.rowcount
                cur.execute("ANALYZE cnefe")
    db.registrar(conn, FONTE, origem, caminho.name, baixar.sha256(caminho), gravadas, cabecalho=cab, separador=sep)
    log.info("%d endereços gravados em cnefe", gravadas)
    return gravadas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", help="zip ou csv já baixado")
    args = ap.parse_args(argv)
    with db.etapa("cnefe"):
        caminho, origem = obter_arquivo(args.arquivo)
        with db.conectar() as conn:
            db.criar_schema(conn)
            carregar(conn, caminho, origem)


if __name__ == "__main__":
    main()
