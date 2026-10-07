"""Verificação antes de rodar: o que vai funcionar nesta máquina e o que falta. Não baixa nem grava dados.

Uso:
    python -m etl.verificar              # tudo
    python -m etl.verificar --sem-rede   # pula os hosts das fontes

Confere o banco do Pineal (conexão, PostGIS, unaccent, pg_trgm, permissão de criar schema), o banco da MINDATA
(dados_rfb.cnpj_consolidado com o município e as tabelas dos cruzamentos), os hosts das fontes do catálogo,
os arquivos já baixados em dados/bruto/ e o espaço em disco. Grava relatorios/verificacao.md e sai com código 1
se faltar algo obrigatório (falha); aviso não impede a rodada, só desliga a parte que depende dele.
"""

import argparse
import shutil
from collections import defaultdict
from urllib.parse import urlparse

import psycopg2
import requests

from etl import baixar, config
from etl.fontes import mindata_cruzamentos

OK, AVISO, FALHA = "ok", "aviso", "falha"
EXTENSOES = ["postgis", "unaccent", "pg_trgm"]
# hosts que o catálogo não lista com url mas os scripts usam
HOSTS_FIXOS = {
    "dadosabertos.curitiba.pr.gov.br": ["portal da prefeitura (M1)"],
    "mid-dadosabertos.curitiba.pr.gov.br": ["arquivos do portal da prefeitura (M1)"],
    "dadosabertos.c3sl.ufpr.br": ["histórico do portal da prefeitura"],
}
DISCO_RECOMENDADO_GB = 30


def banco_pineal() -> list[tuple]:
    r = []
    try:
        conn = psycopg2.connect(config.dsn_pineal(), connect_timeout=10)
    except psycopg2.Error as e:
        return [("banco Pineal", "conexão", FALHA, str(e).strip().splitlines()[0])]
    with conn, conn.cursor() as cur:
        cur.execute("SELECT current_database(), split_part(version(), ' ', 2)")
        nome, versao = cur.fetchone()
        r.append(("banco Pineal", "conexão", OK, f"{nome} (PostgreSQL {versao})"))
        cur.execute(
            "SELECT name, installed_version, default_version FROM pg_available_extensions WHERE name = ANY(%s)",
            (EXTENSOES,),
        )
        disponiveis = {n: (inst, padrao) for n, inst, padrao in cur.fetchall()}
        for ext in EXTENSOES:
            if ext not in disponiveis:
                r.append(("banco Pineal", f"extensão {ext}", FALHA, "não instalada no servidor"))
            else:
                inst, padrao = disponiveis[ext]
                r.append(
                    ("banco Pineal", f"extensão {ext}", OK, f"{inst} ativa" if inst else f"{padrao} (será criada)")
                )
        cur.execute(
            "SELECT has_database_privilege(current_database(), 'CREATE'), "
            "(SELECT has_schema_privilege(%s, 'CREATE') FROM pg_namespace WHERE nspname = %s)",
            (config.SCHEMA, config.SCHEMA),
        )
        criar_banco, criar_schema = cur.fetchone()
        if criar_schema or (criar_schema is None and criar_banco):
            r.append(("banco Pineal", f"schema {config.SCHEMA}", OK, "existe" if criar_schema else "será criado"))
        else:
            r.append(("banco Pineal", f"schema {config.SCHEMA}", FALHA, "sem permissão de CREATE"))
    conn.close()
    return r


def banco_rfb() -> list[tuple]:
    r = []
    try:
        conn = psycopg2.connect(config.dsn_rfb(), connect_timeout=10)
    except psycopg2.Error as e:
        return [("banco MINDATA", "conexão", FALHA, str(e).strip().splitlines()[0])]
    with conn, conn.cursor() as cur:
        cur.execute("SET statement_timeout = '60s'")
        cur.execute("SELECT to_regclass('dados_rfb.cnpj_consolidado')")
        if cur.fetchone()[0] is None:
            r.append(("banco MINDATA", "dados_rfb.cnpj_consolidado", FALHA, "tabela não existe (configure RFB_DSN)"))
        else:
            cur.execute(
                """SELECT EXISTS (SELECT 1 FROM dados_rfb.cnpj_consolidado WHERE uf = %s AND municipio = %s),
                          EXISTS (SELECT 1 FROM dados_rfb.cnpj_consolidado WHERE uf = %s AND upper(nome_municipio) = %s)""",
                (config.UF, config.COD_RFB, config.UF, config.NOME_MUNICIPIO),
            )
            por_codigo, por_nome = cur.fetchone()
            if por_codigo:
                r.append(("banco MINDATA", "recorte do município", OK, f"município {config.COD_RFB} encontrado"))
            elif por_nome:
                r.append(
                    (
                        "banco MINDATA",
                        "recorte do município",
                        AVISO,
                        f"código {config.COD_RFB} não achado; o nome {config.NOME_MUNICIPIO} acha (confira PINEAL_COD_RFB)",
                    )
                )
            else:
                r.append(
                    (
                        "banco MINDATA",
                        "recorte do município",
                        FALHA,
                        f"nem o código {config.COD_RFB} nem o nome {config.NOME_MUNICIPIO} em {config.UF}",
                    )
                )
        for nome, (tabela, _, _) in mindata_cruzamentos.FONTES.items():
            cur.execute("SELECT to_regclass(%s)", (tabela,))
            existe = cur.fetchone()[0] is not None
            r.append(
                (
                    "banco MINDATA",
                    f"cruzamento {nome}",
                    OK if existe else AVISO,
                    tabela if existe else f"{tabela} ausente: o cruzamento é pulado",
                )
            )
    conn.close()
    return r


def hosts_do_catalogo() -> dict[str, list[str]]:
    hosts = defaultdict(list)
    for h, usos in HOSTS_FIXOS.items():
        hosts[h] += usos
    for f in config.catalogo()["fontes"]:
        if f.get("status") in ("fora", "lai", "convenio"):
            continue
        for campo in ("url", "url_diretorio", "url_modelo"):
            if f.get(campo):
                hosts[urlparse(str(f[campo])).hostname].append(f["id"])
    return {h: sorted(set(u)) for h, u in hosts.items() if h}


def hosts(timeout: int = 10) -> list[tuple]:
    r = []
    for host, usos in sorted(hosts_do_catalogo().items()):
        try:
            resp = requests.head(f"https://{host}/", timeout=timeout, headers=baixar.UA, allow_redirects=True)
            r.append(("rede", host, OK, f"HTTP {resp.status_code}; usado por {', '.join(usos)}"))
        except requests.RequestException as e:
            motivo = type(e).__name__
            r.append(("rede", host, AVISO, f"inalcançável ({motivo}); afeta {', '.join(usos)}"))
    return r


def arquivos() -> list[tuple]:
    r = []
    if not config.DADOS_BRUTO.exists():
        return [("arquivos", str(config.DADOS_BRUTO), AVISO, "pasta ainda não existe: tudo será baixado")]
    for pasta in sorted(p for p in config.DADOS_BRUTO.iterdir() if p.is_dir()):
        itens = [p for p in pasta.iterdir() if p.is_file() and not p.name.endswith(".parcial")]
        parciais = [p for p in pasta.iterdir() if p.name.endswith(".parcial")]
        tamanho = sum(p.stat().st_size for p in itens) / 1e6
        detalhe = f"{len(itens)} arquivo(s), {tamanho:.1f} MB"
        if parciais:
            detalhe += f"; {len(parciais)} download(s) interrompido(s), apague e baixe de novo"
        r.append(("arquivos", pasta.name, AVISO if parciais else OK, detalhe))
    return r


def disco() -> list[tuple]:
    alvo = config.DADOS_BRUTO
    while not alvo.exists():
        alvo = alvo.parent
    livre = shutil.disk_usage(alvo).free / 1e9
    status = OK if livre >= DISCO_RECOMENDADO_GB else AVISO
    r = [("máquina", "espaço livre", status, f"{livre:.0f} GB em {alvo} (recomendado {DISCO_RECOMENDADO_GB} GB)")]
    r.append(
        (
            "máquina",
            "tippecanoe",
            OK if shutil.which("tippecanoe") else AVISO,
            "instalado" if shutil.which("tippecanoe") else "ausente: só o PMTiles do M3 depende dele",
        )
    )
    return r


def relatorio(linhas: list[tuple]) -> str:
    falhas = sum(1 for li in linhas if li[2] == FALHA)
    avisos = sum(1 for li in linhas if li[2] == AVISO)
    md = [
        "# Verificação antes da rodada",
        "",
        f"Schema `{config.SCHEMA}`, município {config.COD_IBGE} (IBGE) / {config.COD_RFB} (Receita). "
        f"{falhas} falha(s), {avisos} aviso(s).",
        "",
        "| grupo | item | situação | detalhe |",
        "|---|---|---|---|",
        *[f"| {g} | {i} | {s} | {d} |" for g, i, s, d in linhas],
    ]
    return "\n".join(md)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sem-rede", action="store_true")
    args = ap.parse_args(argv)
    linhas = banco_pineal() + banco_rfb() + ([] if args.sem_rede else hosts()) + arquivos() + disco()
    md = relatorio(linhas)
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "verificacao.md").write_text(md, encoding="utf-8")
    print(md)
    return 1 if any(li[2] == FALHA for li in linhas) else 0


if __name__ == "__main__":
    raise SystemExit(main())
