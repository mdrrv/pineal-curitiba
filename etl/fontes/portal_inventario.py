"""Inventário das bases do Portal de Dados Abertos de Curitiba.

Uso:
    python -m etl.fontes.portal_inventario            # só lista os links de download de cada base
    python -m etl.fontes.portal_inventario --baixar   # baixa e descreve as colunas de cada CSV

Lê as fontes do catalogo.yaml que têm `portal_chave`. Gera relatorios/inventario_portal.md com, por base:
links encontrados, separador, codificação, colunas e preenchimento de cada coluna. Não grava valores das
linhas no relatório (algumas bases têm nome e CPF).
"""

import argparse
import csv
import io
import logging
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from etl import baixar, config

log = logging.getLogger("portal_inventario")

BASE = "https://dadosabertos.curitiba.pr.gov.br"
EXT_ARQUIVO = re.compile(r"\.(csv|zip|json|xlsx?|txt|geojson|gpkg|shp|7z|rar|pdf)(\?|$)", re.I)
INTERESSE = {
    "cnpj": re.compile(r"cnpj", re.I),
    "cpf": re.compile(r"cpf", re.I),
    "endereco": re.compile(r"endere|logradouro|rua|numero|n[uú]mero|cep|bairro", re.I),
    "coordenada": re.compile(r"lat|lon|coord|geom|x_|y_|utm", re.I),
    "data": re.compile(r"data|dt_|ano|mes", re.I),
}
AMOSTRA_LINHAS = 200_000


def links_de_arquivo(html: str) -> list[str]:
    return [u for u in baixar.links(html, BASE) if EXT_ARQUIVO.search(urlparse(u).path) or "mid" in urlparse(u).netloc]


def detalhe(chave: str) -> str:
    r = requests.get(f"{BASE}/conjuntodado/detalhe", params={"chave": chave}, headers=baixar.UA, timeout=120)
    r.raise_for_status()
    return r.text


def _texto(dados: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise AssertionError("latin-1 decodifica qualquer byte")


def descrever_csv(dados: bytes) -> dict:
    texto, enc = _texto(dados)
    primeira = texto.split("\n", 1)[0]
    sep = max([";", ",", "\t", "|"], key=primeira.count)
    leitor = csv.reader(io.StringIO(texto), delimiter=sep)
    cab = [c.strip() for c in next(leitor, [])]
    preenchidas = [0] * len(cab)
    n = 0
    for linha in leitor:
        n += 1
        for i, v in enumerate(linha[: len(cab)]):
            if v.strip():
                preenchidas[i] += 1
        if n >= AMOSTRA_LINHAS:
            break
    sinais = {k: [c for c in cab if rx.search(c)] for k, rx in INTERESSE.items()}
    return {
        "codificacao": enc,
        "separador": sep,
        "linhas_lidas": n,
        "colunas": [(c, round(100 * p / n, 1) if n else 0.0) for c, p in zip(cab, preenchidas, strict=True)],
        "sinais": {k: v for k, v in sinais.items() if v},
    }


def descrever_arquivo(caminho: Path) -> list[tuple[str, dict]]:
    suf = caminho.suffix.lower()
    if suf == ".csv" or suf == ".txt":
        with open(caminho, "rb") as f:
            return [(caminho.name, descrever_csv(f.read(64 << 20)))]
    if suf == ".zip":
        saida = []
        with zipfile.ZipFile(caminho) as z:
            for nome in z.namelist():
                if nome.lower().endswith((".csv", ".txt")):
                    with z.open(nome) as f:
                        saida.append((nome, descrever_csv(f.read(64 << 20))))
                else:
                    saida.append((nome, {}))
        return saida
    return [(caminho.name, {})]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baixar", action="store_true", help="baixa os arquivos e descreve as colunas")
    ap.add_argument("--fonte", action="append", help="id da fonte no catálogo (padrão: todas com portal_chave)")
    args = ap.parse_args(argv)

    fontes = [f for f in config.catalogo()["fontes"] if f.get("portal_chave")]
    if args.fonte:
        fontes = [f for f in fontes if f["id"] in args.fonte]

    md = ["# Inventário do Portal de Dados Abertos de Curitiba", ""]
    for f in fontes:
        md += [
            f"## {f['nome']} (`{f['id']}`)",
            "",
            f"Página: {BASE}/conjuntodado/detalhe?chave={f['portal_chave']}",
            "",
        ]
        try:
            achados = links_de_arquivo(detalhe(f["portal_chave"]))
        except requests.RequestException as e:
            log.error("%s: %s", f["id"], e)
            md += [f"Erro ao abrir a página: `{e}`", ""]
            continue
        log.info("%s: %d links", f["id"], len(achados))
        md += [f"- {u}" for u in achados] or [
            "Nenhum link de arquivo na página (pode ser webservice ou carregado por script)."
        ]
        md.append("")
        if not args.baixar:
            continue
        for url in achados:
            if not EXT_ARQUIVO.search(urlparse(url).path):
                continue
            try:
                caminho = baixar.baixar(url, f["id"], nome=unquote(Path(urlparse(url).path).name))
            except requests.RequestException as e:
                md += [f"Falha ao baixar {url}: `{e}`", ""]
                continue
            for nome, d in descrever_arquivo(caminho):
                md += [f"### {nome}", ""]
                if not d:
                    md += ["(não tabular, não descrito)", ""]
                    continue
                md += [
                    f"Codificação `{d['codificacao']}`, separador `{d['separador']}`, {d['linhas_lidas']} linhas lidas.",
                    "",
                ]
                if d["sinais"]:
                    md += ["Sinais: " + "; ".join(f"**{k}**: {', '.join(v)}" for k, v in d["sinais"].items()), ""]
                md += ["| coluna | preenchida (%) |", "|---|---|"] + [f"| {c} | {p} |" for c, p in d["colunas"]] + [""]

    config.RELATORIOS.mkdir(exist_ok=True)
    saida = config.RELATORIOS / "inventario_portal.md"
    saida.write_text("\n".join(md), encoding="utf-8")
    log.info("relatório em %s", saida)


if __name__ == "__main__":
    main()
