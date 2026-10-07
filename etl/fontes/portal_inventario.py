"""Inventário das bases do Portal de Dados Abertos de Curitiba.

Uso:
    python -m etl.fontes.portal_inventario            # metadados, arquivos e colunas de cada base
    python -m etl.fontes.portal_inventario --baixar   # também baixa o arquivo mais recente e mede o preenchimento

Lê as fontes do catalogo.yaml que têm `portal_chave`. Para cada uma: secretaria, frequência, última
atualização, extensões, quantos arquivos há (um por mês), o mais recente com URL, tamanho e dicionário, as
colunas do arquivo e quais delas servem para cruzar (CNPJ, CPF, endereço, coordenada, data).

Gera relatorios/inventario_portal.md (para ler) e relatorios/inventario_portal.json (para scripts).
Com --baixar, mede o preenchimento de cada coluna sem gravar valores no relatório (algumas bases têm nome e CPF).
Os arquivos ficam em mid-dadosabertos.curitiba.pr.gov.br: sem acesso a esse host, use só o modo sem --baixar.
"""

import argparse
import csv
import io
import json
import logging
import re
import zipfile
from pathlib import Path

import requests

from etl import baixar, config, portal

log = logging.getLogger("portal_inventario")

INTERESSE = {
    "cnpj": re.compile(r"cnpj", re.I),
    "cpf": re.compile(r"cpf", re.I),
    "endereco": re.compile(r"endere|logradouro|^rua|numero|n[uú]mero|cep|bairro", re.I),
    "coordenada": re.compile(r"lat|lon|coord|geom|^x$|^y$|utm", re.I),
    "data": re.compile(r"data|^dt_|^ano|^mes|inicio|emissao|expiracao", re.I),
}
AMOSTRA_LINHAS = 200_000


def sinais(colunas: list[str]) -> dict[str, list[str]]:
    achados = {k: [c for c in colunas if rx.search(c)] for k, rx in INTERESSE.items()}
    return {k: v for k, v in achados.items() if v}


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
    return {
        "codificacao": enc,
        "separador": sep,
        "linhas_lidas": n,
        "colunas": [(c, round(100 * p / n, 1) if n else 0.0) for c, p in zip(cab, preenchidas, strict=True)],
        "sinais": sinais(cab),
    }


def descrever_arquivo(caminho: Path) -> list[tuple[str, dict]]:
    suf = caminho.suffix.lower()
    if suf in (".csv", ".txt"):
        with open(caminho, "rb") as f:
            return [(caminho.name, descrever_csv(f.read(64 << 20)))]
    if suf == ".zip":
        saida = []
        with zipfile.ZipFile(caminho) as z:
            for nome in z.namelist():
                if nome.lower().endswith((".csv", ".txt")):
                    with z.open(nome) as f:
                        saida.append((nome, descrever_csv(f.read(64 << 20))))
        return saida
    return [(caminho.name, {})]


def inventariar(fonte: dict, baixar_arquivo: bool) -> dict:
    c = portal.detalhe(fonte["portal_chave"])
    item = {"id": fonte["id"], "titulo": c.titulo, "metadados": c.metadados, "espelho": c.espelho, "extensoes": {}}
    for ext, aba in c.extensoes.items():
        lista = portal.arquivos(c.chave, aba)
        recente = max(lista, key=lambda a: (a.atualizado or portal.datetime.min, a.nome)) if lista else None
        cols = c.colunas.get(recente.nome, []) if recente else []
        reg = {
            "arquivos": len(lista),
            "mais_antigo": min((a.atualizado for a in lista if a.atualizado), default=None),
            "mais_recente": recente.__dict__ if recente else None,
            "colunas": cols,
            "sinais": sinais(cols),
        }
        if baixar_arquivo and recente and ext in ("csv", "zip", "txt"):
            try:
                caminho = baixar.baixar(recente.url, fonte["id"])
                reg["descricao"] = [{"arquivo": n, **d} for n, d in descrever_arquivo(caminho)]
            except requests.RequestException as e:
                reg["erro_download"] = str(e)
        item["extensoes"][ext] = reg
    return item


def markdown(itens: list[dict]) -> str:
    md = [
        "# Inventário do Portal de Dados Abertos de Curitiba",
        "",
        "| base | frequência | última atualização | extensões | arquivos | CNPJ | endereço | coordenada |",
        "|---|---|---|---|---:|:-:|:-:|:-:|",
    ]
    for it in itens:
        if "erro" in it:
            md.append(f"| {it['id']} | erro: {it['erro']} | | | | | | |")
            continue
        ext = it["extensoes"]
        s = {k for e in ext.values() for k in e["sinais"]}
        md.append(
            f"| {it['titulo']} (`{it['id']}`) | {it['metadados'].get('Frequência de atualização', '')} | "
            f"{it['metadados'].get('Última atualização', '')} | {', '.join(ext)} | "
            f"{sum(e['arquivos'] for e in ext.values())} | {'✔' if 'cnpj' in s else ''} | "
            f"{'✔' if 'endereco' in s else ''} | {'✔' if 'coordenada' in s else ''} |"
        )
    for it in itens:
        if "erro" in it:
            continue
        md += ["", f"## {it['titulo']} (`{it['id']}`)", ""]
        md += [f"- {k}: {v}" for k, v in it["metadados"].items()]
        if it["espelho"]:
            md.append(f"- Histórico (mais de um ano): {it['espelho']}")
        for ext, e in it["extensoes"].items():
            r = e["mais_recente"] or {}
            md += [
                "",
                f"### .{ext}: {e['arquivos']} arquivos, mais recente `{r.get('nome', '')}` ({r.get('tamanho', '')})",
                "",
            ]
            if r.get("dicionario"):
                md.append(f"Dicionário: {r['dicionario']}")
                md.append("")
            if e["sinais"]:
                md.append(
                    "Colunas para cruzar: " + "; ".join(f"**{k}**: {', '.join(v)}" for k, v in e["sinais"].items())
                )
                md.append("")
            if e["colunas"]:
                md.append("Colunas: " + ", ".join(f"`{c}`" for c in e["colunas"]))
            for d in e.get("descricao", []):
                if d.get("colunas"):
                    md += [
                        "",
                        f"Preenchimento em `{d['arquivo']}` ({d['linhas_lidas']} linhas, `{d['codificacao']}`, "
                        f"separador `{d['separador']}`):",
                        "",
                        "| coluna | % |",
                        "|---|---:|",
                    ]
                    md += [f"| {c} | {p} |" for c, p in d["colunas"]]
            if e.get("erro_download"):
                md += ["", f"Download falhou: `{e['erro_download']}`"]
    return "\n".join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baixar", action="store_true", help="baixa o arquivo mais recente e mede o preenchimento")
    ap.add_argument("--fonte", action="append", help="id da fonte no catálogo (padrão: todas com portal_chave)")
    args = ap.parse_args(argv)

    fontes = [f for f in config.catalogo()["fontes"] if f.get("portal_chave")]
    if args.fonte:
        fontes = [f for f in fontes if f["id"] in args.fonte]
    itens = []
    for f in fontes:
        try:
            itens.append(inventariar(f, args.baixar))
            log.info("%s: ok", f["id"])
        except (requests.RequestException, RuntimeError) as e:
            log.error("%s: %s", f["id"], e)
            itens.append({"id": f["id"], "erro": str(e)})

    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "inventario_portal.md").write_text(markdown(itens), encoding="utf-8")
    (config.RELATORIOS / "inventario_portal.json").write_text(
        json.dumps(itens, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    log.info("relatório em %s", config.RELATORIOS / "inventario_portal.md")


if __name__ == "__main__":
    main()
