"""Leitura de CSV grande (solto ou dentro de zip) com detecção de codificação e separador."""

import codecs
import csv
import io
import re
import tempfile
import unicodedata
import zipfile
from contextlib import contextmanager
from pathlib import Path

csv.field_size_limit(1 << 27)


@contextmanager
def abrir_texto(caminho: Path, padrao_interno: str = ".csv"):
    """Abre o CSV (solto ou o primeiro `padrao_interno` dentro do zip) como texto, em UTF-8 ou Latin-1."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".zip":
        z = zipfile.ZipFile(caminho)
        nomes = [n for n in z.namelist() if n.lower().endswith(padrao_interno)]
        if not nomes:
            raise ValueError(f"nenhum {padrao_interno} dentro de {caminho.name}")
        abrir_bin = lambda: z.open(nomes[0])  # noqa: E731
    else:
        z = None
        abrir_bin = lambda: open(caminho, "rb")  # noqa: E731
    with abrir_bin() as b:
        amostra = b.read(1 << 20)
    try:  # incremental: a amostra pode terminar no meio de um caractere de 2 ou 3 bytes
        codecs.getincrementaldecoder("utf-8")().decode(amostra, final=False)
        enc = "utf-8-sig"
    except UnicodeDecodeError:
        enc = "cp1252"
    b = abrir_bin()
    try:
        yield io.TextIOWrapper(b, encoding=enc, errors="replace" if enc == "cp1252" else "strict", newline="")
    finally:
        b.close()
        if z:
            z.close()


def norm_coluna(nome: str) -> str:
    """'Órgão' -> 'ORGAO', 'CNPJ/CPF' -> 'CNPJ_CPF', 'Valor Total/Global' -> 'VALOR_TOTAL_GLOBAL'."""
    s = unicodedata.normalize("NFKD", nome.strip()).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", s.upper()).strip("_")


def separador(primeira_linha: str) -> str:
    return max([";", ",", "\t", "|"], key=primeira_linha.count)


@contextmanager
def ler_csv(caminho: Path, obrigatorias: list[str] = ()):
    """DictReader com cabeçalho normalizado (norm_coluna). Falha se faltar coluna obrigatória."""
    with abrir_texto(caminho) as txt:
        primeira = txt.readline()
        sep = separador(primeira)
        cab = [norm_coluna(c) for c in next(csv.reader([primeira], delimiter=sep))]
        faltando = [c for c in obrigatorias if norm_coluna(c) not in cab]
        if faltando:
            raise ValueError(f"colunas ausentes em {Path(caminho).name}: {faltando}. Cabeçalho: {cab}")
        yield csv.DictReader(txt, fieldnames=cab, delimiter=sep)


def copiar_para_temp(conn, caminho: Path, tabela: str, colunas: dict[str, str], obrigatorias: list[str] = ()) -> int:
    """Copia as colunas escolhidas do CSV para uma tabela temporária (texto), sem passar o resto do arquivo.

    colunas: {coluna_no_csv (qualquer grafia): nome_na_tabela}. Coluna ausente no CSV vira NULL.
    """
    origem = {norm_coluna(k): v for k, v in colunas.items()}
    with ler_csv(caminho, obrigatorias) as leitor, tempfile.TemporaryFile("w+", encoding="utf-8", newline="") as tmp:
        w = csv.writer(tmp)
        n = 0
        for r in leitor:
            w.writerow([r.get(k) or "" for k in origem])
            n += 1
        tmp.seek(0)
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE TEMP TABLE {tabela} ({', '.join(v + ' TEXT' for v in origem.values())}) ON COMMIT DROP"
            )
            cur.copy_expert(f"COPY {tabela} ({', '.join(origem.values())}) FROM STDIN WITH (FORMAT csv)", tmp)
    return n
