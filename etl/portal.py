"""Cliente do Portal de Dados Abertos de Curitiba (dadosabertos.curitiba.pr.gov.br).

A página de detalhe de cada conjunto traz os metadados e as colunas de cada arquivo; a lista de arquivos
(um por mês, com o dicionário de dados ao lado) vem do endpoint /ConjuntoDado/DownloadArquivos/.
Os arquivos ficam em mid-dadosabertos.curitiba.pr.gov.br; os de mais de um ano, no espelho da UFPR
(dadosabertos.c3sl.ufpr.br).
"""

import html
import re
from dataclasses import dataclass, field
from datetime import datetime  # noqa: F401 (usado também por quem importa portal)

import requests

from etl import baixar

BASE = "https://dadosabertos.curitiba.pr.gov.br"


@dataclass
class Arquivo:
    nome: str
    url: str
    dicionario: str | None
    atualizado: datetime | None
    tamanho: str | None


@dataclass
class Conjunto:
    chave: str
    titulo: str | None = None
    metadados: dict = field(default_factory=dict)
    extensoes: dict[str, str] = field(default_factory=dict)  # extensão -> id da aba
    colunas: dict[str, list[str]] = field(default_factory=dict)  # nome do arquivo -> colunas
    espelho: str | None = None


def _get(url: str, **params) -> requests.Response:
    r = requests.get(url, params=params, headers=baixar.UA, timeout=120)
    r.raise_for_status()
    return r


def _texto(fragmento: str) -> str:
    return html.unescape(" ".join(re.sub(r"<[^>]+>", " ", fragmento).split()))


def ler_detalhe(pagina: str, chave: str) -> Conjunto:
    c = Conjunto(chave=chave)
    t = re.search(r"<title>(.*?)</title>", pagina, re.S)
    c.titulo = (
        _texto(t.group(1)).split(" - Dados Abertos")[0].replace("Detalhes do Conjunto de Dados - ", "") if t else None
    )
    for rotulo, valor in re.findall(r"<strong>\s*([^<]+?)\s*</strong>\s*([^<]*)", pagina):
        rotulo, valor = _texto(rotulo), _texto(valor)
        if valor and rotulo in (
            "Secretaria",
            "Responsável",
            "Frequência de atualização",
            "Espectro temporal",
            "Última atualização",
        ):
            c.metadados[rotulo] = valor
    c.extensoes = {
        _texto(ext).lstrip(".").lower(): aba
        for aba, ext in re.findall(r'href="#aba_([0-9a-f-]+)"[^>]*>([^<]*)</a>', pagina)
    }
    # cada arquivo é um item do acordeão: cabeçalho com o nome, corpo com a tabela de colunas
    for nome, corpo in re.findall(
        r"<span>([^<]+\.\w{2,7})</span>.*?(<table class='table table-bordered'>.*?</thead>)", pagina, re.S
    ):
        c.colunas[_texto(nome)] = [_texto(th) for th in re.findall(r"<th>(.*?)</th>", corpo, re.S)]
    m = re.search(r'href="(https?://dadosabertos\.c3sl\.ufpr\.br/[^"]+)"', pagina)
    c.espelho = m.group(1) if m else None
    return c


def detalhe(chave: str) -> Conjunto:
    return ler_detalhe(_get(f"{BASE}/conjuntodado/detalhe", chave=chave).text, chave)


def ler_lista(tabela_html: str) -> list[Arquivo]:
    arquivos = []
    for linha in re.findall(r"<tr>(.*?)</tr>", tabela_html, re.S):
        links = re.findall(r"href='(https?://[^']+)'", linha)
        if not links:
            continue
        celulas = [_texto(c) for c in re.findall(r"<td>(.*?)</td>", linha, re.S)]
        data = next((c for c in celulas if re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", c)), None)
        tamanho = next((c for c in celulas if re.search(r"\d\s*(B|KB|MB|GB)$", c)), None)
        arquivos.append(
            Arquivo(
                nome=links[0].rsplit("/", 1)[-1],
                url=links[0],
                dicionario=links[1] if len(links) > 1 else None,
                atualizado=datetime.strptime(data, "%d/%m/%Y %H:%M") if data else None,
                tamanho=tamanho,
            )
        )
    return arquivos


def paginas(chave: str, aba: str):
    """Páginas da lista de arquivos, na ordem do portal (do mais novo para o mais antigo)."""
    pagina, total = 1, 1
    while pagina <= total:
        d = _get(
            f"{BASE}/ConjuntoDado/DownloadArquivos/",
            conjuntoDadoChave=chave,
            conjuntoDadoExtensao=aba,
            pagina=pagina,
            tamanhoPagina=50,
        ).json()
        if not d.get("sucesso"):
            raise RuntimeError(f"portal recusou a lista de arquivos de {chave}: {d.get('erro')}")
        yield ler_lista(d["tabela"])
        total = (d.get("paginacao") or {}).get("totalPaginas") or 1
        pagina += 1


def arquivos(chave: str, aba: str) -> list[Arquivo]:
    return [a for p in paginas(chave, aba) for a in p]


def mais_recente(chave: str, extensao: str = "csv", padrao: str | None = None) -> Arquivo:
    """Arquivo mais recente do conjunto na extensão pedida; `padrao` (regex) filtra pelo nome."""
    c = detalhe(chave)
    if extensao not in c.extensoes:
        raise FileNotFoundError(f"conjunto {chave} não tem arquivos .{extensao} (tem: {list(c.extensoes)})")
    lista = []
    for p in paginas(chave, c.extensoes[extensao]):
        lista += [a for a in p if not padrao or re.search(padrao, a.nome, re.I)]
        if lista and padrao:
            break  # o portal lista do mais novo para o mais antigo: a primeira página com o arquivo basta
    if not lista:
        raise FileNotFoundError(
            f"nenhum arquivo .{extensao} em {chave}" + (f" casando com /{padrao}/" if padrao else "")
        )
    return max(lista, key=lambda a: (a.atualizado or datetime.min, a.nome))


def obter(fonte_id: str, padrao: str, arquivo: str | None = None, extensao: str = "csv"):
    """Arquivo de uma fonte do portal: o informado, o que estiver em dados/bruto/<fonte>/ casando com
    `padrao`, ou o mais recente do portal (baixado com cache). Devolve (caminho, origem)."""
    from pathlib import Path

    from etl import config

    if arquivo:
        return Path(arquivo), arquivo
    local = baixar.arquivo_local(fonte_id, padrao)
    if local:
        return local, str(local)
    a = mais_recente(config.fonte(fonte_id)["portal_chave"], extensao=extensao, padrao=padrao)
    return baixar.baixar(a.url, fonte_id), a.url
