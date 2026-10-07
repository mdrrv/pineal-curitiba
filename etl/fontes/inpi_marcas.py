"""Marcas do INPI (Revista da Propriedade Industrial, seção de marcas) por empresa de Curitiba.

Uso:
    python -m etl.fontes.inpi_marcas [--numeros 2850-2860]

Lê os zips/XMLs da RPI de marcas (RM<numero>.zip, semanal) que estiverem em dados/bruto/inpi_marcas/ ou baixa
os números pedidos (url_modelo do catálogo). A RPI não traz o CNPJ do titular: o casamento é pela razão social
normalizada (norm_nome) com o titular de UF PR, e só vale quando o nome aponta para uma única raiz de CNPJ do
recorte (vai para a matriz em Curitiba, ou o menor CNPJ). Titular pessoa física e nome ambíguo não entram.

Cada processo fica com o último despacho visto (maior número de revista). Grava inpi_marca e o resumo em
empresa_marca (marcas, pedidos nos últimos 12 meses, registros concedidos, classes Nice).
"""

import argparse
import csv
import logging
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from etl import baixar, config, db

log = logging.getLogger("inpi_marcas")
FONTE = "inpi_marcas"
CAMPOS = [
    "revista",
    "processo",
    "deposito",
    "titular",
    "uf",
    "marca",
    "apresentacao",
    "natureza",
    "classes",
    "despacho",
    "despacho_nome",
]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def processos(xml):
    """Gera um dict por <processo> do XML da RPI (leitura em fluxo; tolera variações de nome de atributo)."""
    revista = None
    for evento, el in ET.iterparse(xml, events=("start", "end")):
        nome = _local(el.tag)
        if evento == "start":
            if nome == "revista":
                revista = el.get("numero")
            continue
        if nome != "processo":
            continue
        titulares = [t for t in el.iter() if _local(t.tag) == "titular"]
        marca = next((m for m in el.iter() if _local(m.tag) == "marca"), None)
        nome_marca = None
        if marca is not None:
            nome_marca = next((n.text for n in marca.iter() if _local(n.tag) == "nome" and n.text), None)
        despachos = [d for d in el.iter() if _local(d.tag) == "despacho"]
        classes = sorted({c.get("codigo") for c in el.iter() if _local(c.tag) == "classe-nice" and c.get("codigo")})
        for t in titulares:
            yield {
                "revista": revista,
                "processo": el.get("numero"),
                "deposito": el.get("data-deposito") or el.get("data_deposito"),
                "titular": t.get("nome-razao-social") or t.get("nome"),
                "uf": t.get("uf"),
                "marca": nome_marca,
                "apresentacao": marca.get("apresentacao") if marca is not None else None,
                "natureza": marca.get("natureza") if marca is not None else None,
                "classes": "|".join(classes),
                "despacho": despachos[-1].get("codigo") if despachos else None,
                "despacho_nome": despachos[-1].get("nome") if despachos else None,
            }
        el.clear()


def ler_arquivo(caminho: Path, w) -> int:
    n = 0
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as z:
            for membro in (m for m in z.namelist() if m.lower().endswith(".xml")):
                with z.open(membro) as f:
                    for p in processos(f):
                        w.writerow([p[c] or "" for c in CAMPOS])
                        n += 1
    else:
        with open(caminho, "rb") as f:
            for p in processos(f):
                w.writerow([p[c] or "" for c in CAMPOS])
                n += 1
    return n


def obter_arquivos(numeros: str | None) -> list[Path]:
    pasta = config.DADOS_BRUTO / FONTE
    if numeros:
        ini, _, fim = numeros.partition("-")
        modelo = config.fonte(FONTE)["url_modelo"]
        for n in range(int(ini), int(fim or ini) + 1):
            baixar.baixar(modelo.format(numero=n), FONTE)
    return sorted(p for p in pasta.glob("*") if p.suffix.lower() in (".zip", ".xml")) if pasta.exists() else []


GRAVAR = """
    CREATE TEMP TABLE _nome ON COMMIT DROP AS
    SELECT nome, min(cnpj) FILTER (WHERE identificador_mf = '1') AS matriz, min(cnpj) AS menor
    FROM (SELECT norm_nome(razao_social) AS nome, cnpj, coalesce(cnpj_basico, left(cnpj, 8)) AS raiz, identificador_mf
          FROM empresa WHERE razao_social IS NOT NULL AND NOT pessoa_fisica) e
    WHERE nome IS NOT NULL
    GROUP BY nome HAVING count(DISTINCT raiz) = 1;

    INSERT INTO inpi_marca (processo, cnpj, data_deposito, marca, apresentacao, natureza, classes_nice,
                            ultimo_despacho, ultimo_despacho_nome, revista)
    SELECT DISTINCT ON (c.processo) c.processo, coalesce(n.matriz, n.menor), data_br(c.deposito),
           NULLIF(btrim(c.marca), ''), NULLIF(c.apresentacao, ''), NULLIF(c.natureza, ''),
           string_to_array(NULLIF(c.classes, ''), '|'), NULLIF(c.despacho, ''), NULLIF(c.despacho_nome, ''),
           NULLIF(c.revista, '')::INT
    FROM marca_carga c
    JOIN _nome n ON n.nome = norm_nome(c.titular)
    WHERE upper(btrim(c.uf)) = 'PR' AND c.processo <> ''
    ORDER BY c.processo, NULLIF(c.revista, '')::INT DESC NULLS LAST
    ON CONFLICT (processo) DO UPDATE SET
        ultimo_despacho = EXCLUDED.ultimo_despacho, ultimo_despacho_nome = EXCLUDED.ultimo_despacho_nome,
        revista = EXCLUDED.revista, classes_nice = coalesce(EXCLUDED.classes_nice, inpi_marca.classes_nice),
        marca = coalesce(EXCLUDED.marca, inpi_marca.marca),
        data_deposito = coalesce(EXCLUDED.data_deposito, inpi_marca.data_deposito)
    WHERE EXCLUDED.revista >= coalesce(inpi_marca.revista, 0);

    DROP TABLE IF EXISTS empresa_marca;
    CREATE TABLE empresa_marca AS
    SELECT m.cnpj, count(*) AS marcas,
           count(*) FILTER (WHERE m.data_deposito > current_date - INTERVAL '12 months') AS pedidos_12m,
           count(*) FILTER (WHERE m.ultimo_despacho_nome ILIKE '%concess%') AS concedidas,
           (SELECT array_agg(DISTINCT c ORDER BY c) FROM inpi_marca m2, unnest(m2.classes_nice) c
            WHERE m2.cnpj = m.cnpj) AS classes_nice,
           max(m.data_deposito) AS ultimo_deposito
    FROM inpi_marca m
    GROUP BY m.cnpj;
    ALTER TABLE empresa_marca ADD PRIMARY KEY (cnpj);
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--numeros", help="números da RPI a baixar, ex.: 2850-2860")
    args = ap.parse_args(argv)
    with db.etapa("inpi"):
        arquivos = obter_arquivos(args.numeros)
        if not arquivos:
            raise SystemExit(f"sem RPI em {config.DADOS_BRUTO / FONTE}: use --numeros ou coloque os RM*.zip lá")
        with db.conectar() as conn:
            db.criar_schema(conn)
            lidos = 0
            with tempfile.TemporaryFile("w+", encoding="utf-8", newline="") as tmp:
                w = csv.writer(tmp)
                for a in arquivos:
                    lidos += ler_arquivo(a, w)
                tmp.seek(0)
                with conn.cursor() as cur:
                    cur.execute(
                        f"CREATE TEMP TABLE marca_carga ({', '.join(c + ' TEXT' for c in CAMPOS)}) ON COMMIT DROP"
                    )
                    cur.copy_expert(f"COPY marca_carga ({', '.join(CAMPOS)}) FROM STDIN WITH (FORMAT csv)", tmp)
                    cur.execute(GRAVAR)
                    cur.execute("SELECT count(*), count(DISTINCT cnpj) FROM inpi_marca")
                    marcas, empresas = cur.fetchone()
            for a in arquivos:
                db.registrar(conn, FONTE, str(a), a.name, baixar.sha256(a), linhas=lidos)
    print(f"{lidos} titulares lidos em {len(arquivos)} revistas; {marcas} marcas de {empresas} empresas de Curitiba")


if __name__ == "__main__":
    main()
