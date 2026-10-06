import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

DADOS_BRUTO = Path(os.getenv("PINEAL_DADOS", RAIZ / "dados")) / "bruto"
RELATORIOS = RAIZ / "relatorios"
SQL = RAIZ / "sql"

COD_IBGE = os.getenv("PINEAL_COD_IBGE", "4106902")
COD_RFB = os.getenv("PINEAL_COD_RFB", "7535")
NOME_MUNICIPIO = os.getenv("PINEAL_NOME_MUNICIPIO", "CURITIBA")
UF = os.getenv("PINEAL_UF", "PR")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")


def dsn_pineal() -> str:
    return os.getenv("PINEAL_DSN") or _dsn("PINEAL")


def dsn_rfb() -> str:
    """Banco onde está dados_rfb.cnpj_consolidado. Sem configuração, usa o mesmo do Pineal."""
    return os.getenv("RFB_DSN") or (_dsn("RFB") if os.getenv("RFB_DB_NAME") else dsn_pineal())


def _dsn(prefixo: str) -> str:
    partes = {
        "host": os.getenv(f"{prefixo}_DB_HOST", "localhost"),
        "port": os.getenv(f"{prefixo}_DB_PORT", "5432"),
        "dbname": os.getenv(f"{prefixo}_DB_NAME", "pineal"),
        "user": os.getenv(f"{prefixo}_DB_USER", "postgres"),
        "password": os.getenv(f"{prefixo}_DB_PASSWORD", ""),
    }
    return " ".join(f"{k}={v}" for k, v in partes.items() if v != "")


def catalogo() -> dict:
    with open(RAIZ / "catalogo.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fonte(fonte_id: str) -> dict:
    for f in catalogo()["fontes"]:
        if f["id"] == fonte_id:
            return f
    raise KeyError(f"fonte '{fonte_id}' não está no catalogo.yaml")
