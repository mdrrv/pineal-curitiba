"""Download com cache local. O arquivo fica em dados/bruto/<fonte>/ e não é baixado de novo."""

import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests

from etl import config

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (Pineal-Curitiba ETL)"}


def pasta(fonte_id: str) -> Path:
    p = config.DADOS_BRUTO / fonte_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(url: str, fonte_id: str, nome: str | None = None, forcar: bool = False) -> Path:
    destino = pasta(fonte_id) / (nome or unquote(Path(urlparse(url).path).name) or "arquivo")
    if destino.exists() and destino.stat().st_size > 0 and not forcar:
        log.info("cache %s", destino)
        return destino
    log.info("baixando %s", url)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    with requests.get(url, headers=UA, stream=True, timeout=(30, 600)) as r:
        r.raise_for_status()
        with open(parcial, "wb") as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
    parcial.replace(destino)
    log.info("ok %s (%.1f MB)", destino.name, destino.stat().st_size / 1e6)
    return destino


def links(html: str, base: str) -> list[str]:
    vistos, saida = set(), []
    for href in re.findall(r'href\s*=\s*["\']([^"\'#]+)["\']', html, flags=re.I):
        url = urljoin(base, href.strip())
        if url not in vistos:
            vistos.add(url)
            saida.append(url)
    return saida


def resolver_no_diretorio(url_diretorio: str, padrao: str) -> str:
    """Acha, numa listagem de diretório (FTP do IBGE via HTTPS), o arquivo cujo nome casa com o regex."""
    r = requests.get(url_diretorio, headers=UA, timeout=60)
    r.raise_for_status()
    rx = re.compile(padrao, re.I)
    candidatos = [u for u in links(r.text, url_diretorio) if rx.search(unquote(Path(urlparse(u).path).name))]
    if not candidatos:
        raise FileNotFoundError(f"nenhum arquivo casa com /{padrao}/ em {url_diretorio}")
    return sorted(candidatos)[-1]


def arquivo_local(fonte_id: str, padrao: str) -> Path | None:
    """Arquivo colocado à mão em dados/bruto/<fonte>/ (para fontes sem link direto)."""
    rx = re.compile(padrao, re.I)
    achados = sorted(
        p for p in pasta(fonte_id).iterdir() if p.is_file() and rx.search(p.name) and not p.name.endswith(".parcial")
    )
    return achados[-1] if achados else None
