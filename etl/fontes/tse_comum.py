"""Partes comuns dos leitores do TSE (módulo ME): arquivos por ano e filtro do município.

Os arquivos vêm do Portal de Dados Abertos do TSE (cdn.tse.jus.br), um zip por ano (locais nacionais;
votação e perfil por UF). Como nas listas M1b, arquivo colocado à mão em dados/bruto/<fonte>/ tem
prioridade sobre o download, e o layout real se confere na primeira carga.
"""

import os
import re
from pathlib import Path

from etl import baixar, config

# CD_MUNICIPIO do TSE (não é o código IBGE nem o da Receita). Reserva: nome + UF, como no recorte RFB.
COD_TSE = os.getenv("PINEAL_COD_TSE", "75353")

# WHERE de recorte do município numa tabela temporária com colunas cd_mun, nm_mun e uf (texto cru do CSV)
FILTRO_MUNICIPIO = """(btrim(cd_mun) = %(cod_tse)s
    OR (norm_txt(nm_mun) = norm_txt(%(nome_municipio)s) AND upper(btrim(uf)) = %(uf)s))"""


def parametros_municipio() -> dict:
    return {"cod_tse": COD_TSE, "nome_municipio": config.NOME_MUNICIPIO, "uf": config.UF}


def ano_do_nome(nome: str) -> int | None:
    m = re.search(r"(20\d{2})", Path(nome).name)
    return int(m.group(1)) if m else None


def obter_arquivos(fonte_id: str, arquivos: list[str] | None, anos: list[int] | None = None) -> list[Path]:
    """--arquivo repetível > arquivos locais em dados/bruto/<fonte>/ > download pela url_modelo do catálogo."""
    if arquivos:
        return [Path(a) for a in arquivos]
    pasta = config.DADOS_BRUTO / fonte_id
    locais = sorted(p for p in pasta.glob("*") if p.suffix.lower() in (".zip", ".csv")) if pasta.exists() else []
    if locais:
        return locais
    f = config.fonte(fonte_id)
    saida = []
    for ano in anos or f.get("anos", []):
        url = f["url_modelo"].format(ano=ano, uf=config.UF)
        saida.append(baixar.baixar(url, fonte_id))
    if not saida:
        raise SystemExit(f"nenhum arquivo em {pasta} e nenhum ano para baixar (catalogo.yaml: {fonte_id})")
    return saida
