"""Listas públicas com CNPJ (M1b): quem exporta, tem crédito do BNDES, licença ambiental, SIF, CADASTUR...

Uso:
    python -m etl.fontes.listas_cnpj                 # todas as listas com arquivo em dados/bruto/<lista>/
    python -m etl.fontes.listas_cnpj --so bndes_operacoes --so cnes

Cada lista é lida dos CSVs (soltos ou um por zip) que estiverem em dados/bruto/<lista>/. As páginas de
download estão no catalogo.yaml (campo url). Planilha .xlsx: salve como CSV antes.

O layout de cada órgão muda com o tempo, então a leitura é tolerante: a coluna do CNPJ, da data, do valor e
do rótulo é a primeira que existir numa lista de nomes possíveis (LISTAS). Só ficam as linhas cujo CNPJ
(dígito verificador conferido) é de uma empresa do recorte de Curitiba:
    estabelecimento  CNPJ igual (posto, hospital, hotel, frigorífico)
    empresa          mesma raiz (crédito, exportação, cadastro federal valem para todas as unidades)
Linha de pessoa física (CPF) não entra. Colunas de contato e de pessoa (CPF, e-mail, telefone,
responsável, sócio) não vão para `atributos`.

Grava lista_registro (linhas casadas) e empresa_lista (por CNPJ e lista: registros, valor, datas, rótulos).
Relatório em relatorios/listas_cnpj.md.
"""

import argparse
import csv
import json
import logging
import re
import tempfile
from pathlib import Path

from etl import baixar, config, db, leitura

log = logging.getLogger("listas_cnpj")

CNPJ_PADRAO = ["CNPJ", "NU_CNPJ", "CO_CNPJ", "NR_CNPJ", "CNPJ_CPF", "CPF_CNPJ", "NUM_CNPJ", "CNPJ_EMPRESA"]

# nivel: estabelecimento | empresa; agregar: soma | media (do valor)
LISTAS = {
    "mdic_exportadoras": dict(
        nivel="empresa",
        rotulo=["FAIXA_VALOR", "FAIXA", "FAIXA_FOB", "OPERACAO", "TIPO"],
        data=["ANO", "CO_ANO"],
    ),
    "bndes_operacoes": dict(
        nivel="empresa",
        cnpj=["CPF_CNPJ", "CNPJ", "CNPJ_DO_CLIENTE", "CNPJ_CLIENTE"],
        valor=["VALOR_CONTRATADO_R", "VALOR_CONTRATADO", "VALOR_DA_OPERACAO_EM_R", "VALOR_DESEMBOLSADO_R"],
        data=["DATA_DA_CONTRATACAO", "DATA_CONTRATACAO", "DATA_DA_OPERACAO"],
        rotulo=["PRODUTO", "INSTRUMENTO_FINANCEIRO", "SUBSETOR_CNAE_NOME", "SETOR_BNDES"],
    ),
    "ibama_ctf": dict(
        nivel="empresa",
        data=["DATA_INICIO_ATIVIDADE", "DATA_DE_INICIO_DA_ATIVIDADE", "DT_INICIO_ATIVIDADE", "DATA_CADASTRO"],
        rotulo=["CATEGORIA", "DESCRICAO_CATEGORIA", "ATIVIDADE", "DESCRICAO_ATIVIDADE"],
    ),
    "iat_licencas": dict(
        nivel="estabelecimento",
        data=["DATA_VALIDADE", "VALIDADE", "DT_VALIDADE", "DATA_DE_VALIDADE", "VENCIMENTO"],
        rotulo=["TIPO_LICENCA", "TIPO_DE_LICENCA", "MODALIDADE", "ATIVIDADE"],
    ),
    "cadastur": dict(
        nivel="estabelecimento",
        data=["VALIDADE_DO_CERTIFICADO", "DATA_VALIDADE", "VALIDADE", "DATA_DE_VALIDADE"],
        rotulo=["ATIVIDADE", "TIPO_DE_ATIVIDADE", "ATIVIDADE_TURISTICA", "TIPO"],
    ),
    "anatel_scm": dict(
        nivel="empresa",
        cnpj=["CNPJ", "CNPJ_DA_PRESTADORA", "NUM_CNPJ"],
        valor=["ACESSOS", "QUANTIDADE_DE_ACESSOS", "QT_ACESSOS"],
        agregar="soma",
        data=["DATA", "ANO_MES", "ANO"],
        rotulo=["TECNOLOGIA", "MEIO_DE_ACESSO", "SERVICO"],
    ),
    "mapa_sif": dict(
        nivel="estabelecimento",
        rotulo=["CLASSIFICACAO", "AREA", "CATEGORIA", "ATIVIDADE"],
    ),
    "emec": dict(
        nivel="empresa",
        cnpj=["CNPJ", "NU_CNPJ", "CNPJ_MANTENEDORA", "NU_CNPJ_MANTENEDORA"],
        rotulo=["ORGANIZACAO_ACADEMICA", "CATEGORIA_ADMINISTRATIVA", "TIPO"],
        data=["DATA_DE_INICIO_DO_FUNCIONAMENTO", "DT_INICIO_FUNCIONAMENTO"],
    ),
    "cnes": dict(
        nivel="estabelecimento",
        cnpj=["NU_CNPJ", "CO_CNPJ", "CNPJ"],
        rotulo=["DS_TIPO_UNIDADE", "TIPO_UNIDADE", "TP_UNIDADE", "NO_TIPO_UNIDADE"],
        data=["DT_ATUALIZACAO", "DATA_ATUALIZACAO", "CO_COMPETENCIA"],
    ),
    "anp_revendas": dict(
        nivel="estabelecimento",
        cnpj=["CNPJ_DA_REVENDA", "CNPJ"],
        valor=["VALOR_DE_VENDA", "PRECO_VENDA"],
        agregar="media",
        data=["DATA_DA_COLETA", "DATA_COLETA"],
        rotulo=["PRODUTO", "BANDEIRA"],
    ),
}

PESSOAL = re.compile(r"CPF|E_?MAIL|TELEFONE|FONE|CELULAR|FAX|RESPONSAVEL|REPRESENTANTE|SOCIO|CONTATO|NOME_DO_CLIENTE")
CAMPOS = ["lista", "arquivo", "cnpj", "cnpj_basico", "rotulo", "data", "valor", "atributos"]


def _dv(base: str) -> str:
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        r = sum(int(d) * p for d, p in zip(base, pesos, strict=True)) % 11
        base += "0" if r < 2 else str(11 - r)
    return base[-2:]


def cnpj_de(texto: str | None, so_cnpj: bool) -> str | None:
    """CNPJ de 14 dígitos com DV válido, ou a raiz (8 dígitos) quando a lista só traz a raiz.
    Em coluna só de CNPJ, zeros à esquerda perdidos (planilha) são repostos; em coluna CPF/CNPJ não."""
    d = re.sub(r"\D", "", texto or "")
    if len(d) == 8 and so_cnpj:
        return d
    if so_cnpj and 9 <= len(d) < 14:
        d = d.zfill(14)
    if len(d) != 14 or d == "0" * 14 or _dv(d[:12]) != d[12:]:
        return None
    return d


def primeira(cab: list[str], opcoes: list[str]) -> str | None:
    return next((c for c in (leitura.norm_coluna(o) for o in opcoes) if c in cab), None)


def coluna_cnpj(cab: list[str], opcoes: list[str]) -> str | None:
    return primeira(cab, opcoes) or next((c for c in cab if "CNPJ" in c and "MANTENEDORA" not in c), None)


def arquivos(lista: str) -> list[Path]:
    p = config.DADOS_BRUTO / lista
    return sorted(x for x in p.glob("*") if x.suffix.lower() in (".csv", ".zip", ".txt")) if p.exists() else []


def recorte(conn) -> tuple[set[str], set[str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT cnpj, cnpj_basico FROM empresa")
        linhas = cur.fetchall()
    return {c for c, _ in linhas}, {b or c[:8] for c, b in linhas}


def ler_arquivo(caminho: Path, lista: str, spec: dict, cnpjs: set[str], raizes: set[str], w) -> tuple[int, int]:
    lidas = casadas = 0
    with leitura.ler_csv(caminho) as leitor:
        cab = leitor.fieldnames
        col = coluna_cnpj(cab, spec.get("cnpj", CNPJ_PADRAO))
        if not col:
            raise ValueError(f"{lista}: nenhuma coluna de CNPJ em {caminho.name}. Cabeçalho: {cab}")
        so_cnpj = "CPF" not in col
        c_data, c_valor, c_rotulo = (primeira(cab, spec.get(k, [])) for k in ("data", "valor", "rotulo"))
        guardar = [c for c in cab if c and c != col and not PESSOAL.search(c)]
        log.info("%s/%s: CNPJ em %s, data %s, valor %s, rótulo %s", lista, caminho.name, col, c_data, c_valor, c_rotulo)
        for r in leitor:
            lidas += 1
            c = cnpj_de(r.get(col), so_cnpj)
            if not c:
                continue
            raiz = c[:8]
            if spec["nivel"] == "estabelecimento":
                if c not in cnpjs:
                    continue
            elif raiz not in raizes:
                continue
            casadas += 1
            atributos = {k: v.strip() for k in guardar if (v := r.get(k)) and v.strip()}
            w.writerow(
                [
                    lista,
                    caminho.name,
                    c if len(c) == 14 else "",
                    raiz,
                    (r.get(c_rotulo) or "").strip() if c_rotulo else "",
                    (r.get(c_data) or "").strip() if c_data else "",
                    (r.get(c_valor) or "").strip() if c_valor else "",
                    json.dumps(atributos, ensure_ascii=False),
                ]
            )
    return lidas, casadas


GRAVAR = """
    INSERT INTO lista_registro (lista, arquivo, cnpj, cnpj_basico, rotulo, data, valor, atributos)
    SELECT lista, arquivo, NULLIF(cnpj, ''), cnpj_basico, NULLIF(rotulo, ''),
           CASE WHEN data ~ '^\\d{4}$' THEN make_date(data::INT, 1, 1)
                WHEN data ~ '^\\d{6}$' THEN make_date(left(data, 4)::INT, right(data, 2)::INT, 1)
                WHEN data ~ '^\\d{4}-\\d{2}$' THEN make_date(left(data, 4)::INT, right(data, 2)::INT, 1)
                ELSE data_br(data) END,
           valor_br(valor), atributos::JSONB
    FROM lista_carga
"""

RESUMIR = """
    DELETE FROM empresa_lista WHERE lista = ANY(%(listas)s);
    INSERT INTO empresa_lista (cnpj, lista, via, registros, valor, data_min, data_max, rotulos)
    SELECT e.cnpj, r.lista,
           CASE WHEN bool_or(r.cnpj = e.cnpj) THEN 'cnpj' ELSE 'raiz' END,
           count(*),
           CASE WHEN min(r.agregar) = 'media' THEN round(avg(r.valor), 4) ELSE sum(r.valor) END,
           min(r.data), max(r.data),
           (array_agg(DISTINCT r.rotulo) FILTER (WHERE r.rotulo IS NOT NULL))[1:5]
    FROM (SELECT l.*, a.agregar, a.nivel FROM lista_registro l JOIN lista_spec a USING (lista)
          WHERE l.lista = ANY(%(listas)s)) r
    JOIN empresa e ON (r.nivel = 'estabelecimento' AND e.cnpj = r.cnpj)
                   OR (r.nivel = 'empresa' AND coalesce(e.cnpj_basico, left(e.cnpj, 8)) = r.cnpj_basico)
    GROUP BY 1, 2;
"""


def carregar(conn, lista: str, cnpjs: set[str], raizes: set[str]) -> tuple[int, int, list[str]] | None:
    fontes = arquivos(lista)
    if not fontes:
        return None
    spec = LISTAS[lista]
    lidas = casadas = 0
    with tempfile.TemporaryFile("w+", encoding="utf-8", newline="") as tmp:
        w = csv.writer(tmp)
        for f in fontes:
            li, ca = ler_arquivo(f, lista, spec, cnpjs, raizes, w)
            lidas += li
            casadas += ca
        tmp.seek(0)
        with conn.cursor() as cur:
            cur.execute(f"CREATE TEMP TABLE lista_carga ({', '.join(c + ' TEXT' for c in CAMPOS)}) ON COMMIT DROP")
            cur.copy_expert(f"COPY lista_carga ({', '.join(CAMPOS)}) FROM STDIN WITH (FORMAT csv)", tmp)
            cur.execute("DELETE FROM lista_registro WHERE lista = %s", (lista,))
            cur.execute(GRAVAR)
            cur.execute("DROP TABLE lista_carga")
    for f in fontes:
        db.registrar(conn, lista, str(f), f.name, baixar.sha256(f), lidas, casadas=casadas)
    return lidas, casadas, [f.name for f in fontes]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--so", action="append", choices=list(LISTAS))
    args = ap.parse_args(argv)
    escolhidas = args.so or list(LISTAS)
    linhas = []
    with db.etapa("listas"), db.conectar() as conn:
        db.criar_schema(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE lista_spec")
            cur.executemany(
                "INSERT INTO lista_spec (lista, nivel, agregar) VALUES (%s, %s, %s)",
                [(k, v["nivel"], v.get("agregar", "soma")) for k, v in LISTAS.items()],
            )
        cnpjs, raizes = recorte(conn)
        carregadas = {}
        for lista in escolhidas:
            r = carregar(conn, lista, cnpjs, raizes)
            if r is None:
                url = config.fonte(lista).get("url", "")
                log.warning("%s: sem arquivo em dados/bruto/%s/ (%s)", lista, lista, url)
                linhas.append(f"| {lista} | sem arquivo ({url}) | | | |")
            else:
                carregadas[lista] = r
        por = {}
        if carregadas:
            with conn.cursor() as cur:
                cur.execute(RESUMIR, {"listas": list(carregadas)})
                cur.execute("SELECT lista, count(*) FROM empresa_lista GROUP BY 1")
                por = dict(cur.fetchall())
    for lista, (lidas, casadas, nomes) in carregadas.items():
        linhas.append(f"| {lista} | {', '.join(nomes)} | {lidas} | {casadas} | {por.get(lista, 0)} |")
    md = [
        "# Listas com CNPJ (M1b)",
        "",
        "| lista | arquivos | linhas lidas | do recorte | empresas de Curitiba |",
        "|---|---|---:|---:|---:|",
        *linhas,
    ]
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "listas_cnpj.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
