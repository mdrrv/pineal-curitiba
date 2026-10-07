"""Leitura de CSV grande (solto ou dentro de zip) com detecção de codificação e separador."""

import csv
import io
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
    try:
        amostra.decode("utf-8")
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


def separador(primeira_linha: str) -> str:
    return max([";", ",", "\t", "|"], key=primeira_linha.count)


@contextmanager
def ler_csv(caminho: Path, obrigatorias: list[str] = ()):
    """DictReader com cabeçalho em maiúsculas e sem espaços nas pontas. Falha se faltar coluna obrigatória."""
    with abrir_texto(caminho) as txt:
        primeira = txt.readline()
        sep = separador(primeira)
        cab = [c.strip().upper() for c in next(csv.reader([primeira], delimiter=sep))]
        faltando = [c for c in obrigatorias if c.upper() not in cab]
        if faltando:
            raise ValueError(f"colunas ausentes em {Path(caminho).name}: {faltando}. Cabeçalho: {cab}")
        yield csv.DictReader(txt, fieldnames=cab, delimiter=sep)
