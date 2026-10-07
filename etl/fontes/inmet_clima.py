"""Clima diário de Curitiba (INMET, estações automáticas e convencionais): chuva e temperatura.

Uso:
    python -m etl.fontes.inmet_clima [--anos 2020-2025]

Lê os dados históricos do INMET que estiverem em dados/bruto/inmet_clima/ (zip anual com um CSV por estação,
ou os CSVs soltos) ou baixa os anos pedidos (url_modelo do catálogo). Só ficam as estações de Curitiba
(nome do arquivo com _PR_ e CURITIBA). O arquivo é horário, em UTC: o dia é o de Curitiba (UTC-3).
Valor -9999 ou vazio é falta de medição. Grava clima_dia (chuva somada, horas com chuva, temperatura média,
mínima e máxima, horas medidas).
"""

import argparse
import csv
import datetime
import io
import logging
import re
import zipfile
from collections import defaultdict
from pathlib import Path

from psycopg2.extras import execute_values

from etl import baixar, config, db, leitura

log = logging.getLogger("inmet_clima")
FONTE = "inmet_clima"
DE_CURITIBA = re.compile(r"_PR_.*CURITIBA", re.I)


def _num(v: str | None) -> float | None:
    v = (v or "").strip().replace(",", ".")
    if not v or v.startswith("-9999"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _momento(data: str, hora: str) -> datetime.datetime | None:
    d = re.sub(r"\D", "", data or "")
    h = re.sub(r"\D", "", hora or "")[:4].ljust(4, "0")
    if len(d) != 8:
        return None
    try:
        return datetime.datetime.strptime(d + h, "%Y%m%d%H%M")
    except ValueError:
        return None


def novo_dia() -> dict:
    return {"chuva": 0.0, "n_chuva": 0, "horas_chuva": 0, "temps": [], "max": None, "min": None}


def ler_estacao(texto: io.TextIOBase, dias: dict) -> str:
    """Acumula em dias[(estação, dia local)] as horas de um CSV do INMET; devolve o código da estação."""
    estacao = None
    for linha in texto:
        chave, _, valor = linha.partition(";")
        if leitura.norm_coluna(chave).startswith("CODIGO"):
            estacao = valor.strip().strip(";")
        if leitura.norm_coluna(chave).startswith("DATA") and ";" in valor:
            cab = [leitura.norm_coluna(c) for c in next(csv.reader([linha], delimiter=";"))]
            break
    else:
        raise ValueError("cabeçalho de dados não encontrado")
    estacao = estacao or "desconhecida"

    def col(prefixo):
        return next((i for i, c in enumerate(cab) if c.startswith(prefixo)), None)

    i_data, i_hora = col("DATA"), col("HORA")
    i_chuva, i_temp = col("PRECIPITACAO_TOTAL"), col("TEMPERATURA_DO_AR_BULBO_SECO")
    i_max, i_min = col("TEMPERATURA_MAXIMA"), col("TEMPERATURA_MINIMA")
    for r in csv.reader(texto, delimiter=";"):
        if len(r) <= max(i for i in (i_data, i_hora, i_chuva, i_temp) if i is not None):
            continue
        m = _momento(r[i_data], r[i_hora])
        if m is None:
            continue
        dia = (m - datetime.timedelta(hours=3)).date()
        a = dias[(estacao, dia)]
        chuva = _num(r[i_chuva]) if i_chuva is not None else None
        if chuva is not None:
            a["chuva"] += chuva
            a["n_chuva"] += 1
            a["horas_chuva"] += chuva > 0
        t = _num(r[i_temp]) if i_temp is not None else None
        if t is not None:
            a["temps"].append(t)
        for chave, i, f in (("max", i_max, max), ("min", i_min, min)):
            v = _num(r[i]) if i is not None and i < len(r) else None
            v = t if v is None else v
            if v is not None:
                a[chave] = v if a[chave] is None else f(a[chave], v)
    return estacao


def textos(caminho: Path):
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as z:
            for nome in z.namelist():
                if nome.lower().endswith(".csv") and DE_CURITIBA.search(nome.rsplit("/", 1)[-1]):
                    with z.open(nome) as f:
                        yield nome, io.TextIOWrapper(f, encoding="cp1252", errors="replace")
    elif DE_CURITIBA.search(caminho.name):
        with open(caminho, encoding="cp1252", errors="replace") as f:
            yield caminho.name, f


def obter_arquivos(anos: str | None) -> list[Path]:
    if anos:
        ini, _, fim = anos.partition("-")
        modelo = config.fonte(FONTE)["url_modelo"]
        for a in range(int(ini), int(fim or ini) + 1):
            baixar.baixar(modelo.format(ano=a), FONTE)
    pasta = config.DADOS_BRUTO / FONTE
    return sorted(p for p in pasta.glob("*") if p.suffix.lower() in (".zip", ".csv")) if pasta.exists() else []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anos", help="anos a baixar, ex.: 2020-2025")
    args = ap.parse_args(argv)
    with db.etapa("clima"):
        arquivos = obter_arquivos(args.anos)
        if not arquivos:
            raise SystemExit(f"sem dados em {config.DADOS_BRUTO / FONTE}: use --anos ou coloque os zips do INMET lá")
        dias = defaultdict(novo_dia)
        for a in arquivos:
            for nome, texto in textos(a):
                log.info("%s: estação %s", nome, ler_estacao(texto, dias))
        linhas = []
        for (estacao, dia), x in sorted(dias.items()):
            temps = x["temps"]
            linhas.append(
                (
                    estacao,
                    dia,
                    round(x["chuva"], 1) if x["n_chuva"] else None,
                    x["horas_chuva"] if x["n_chuva"] else None,
                    round(sum(temps) / len(temps), 1) if temps else None,
                    x["min"],
                    x["max"],
                    max(x["n_chuva"], len(temps)),
                )
            )
        with db.conectar() as conn:
            db.criar_schema(conn)
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO clima_dia (estacao, data, precipitacao_mm, horas_com_chuva, temp_media, temp_min,
                                              temp_max, horas_medidas) VALUES %s
                       ON CONFLICT (estacao, data) DO UPDATE SET
                           precipitacao_mm = EXCLUDED.precipitacao_mm, horas_com_chuva = EXCLUDED.horas_com_chuva,
                           temp_media = EXCLUDED.temp_media, temp_min = EXCLUDED.temp_min,
                           temp_max = EXCLUDED.temp_max, horas_medidas = EXCLUDED.horas_medidas""",
                    linhas,
                )
            for a in arquivos:
                db.registrar(conn, FONTE, str(a), a.name, baixar.sha256(a), linhas=len(linhas))
    print(f"{len(linhas)} dias-estação gravados em clima_dia")


if __name__ == "__main__":
    main()
