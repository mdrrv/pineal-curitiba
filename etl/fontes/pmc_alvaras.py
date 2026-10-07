"""Base de Alvarás da prefeitura: carga, geocodificação e cruzamento com os CNPJs.

Uso:
    python -m etl.fontes.pmc_alvaras [--arquivo caminho.csv]

Sem --arquivo, usa o CSV que estiver em dados/bruto/pmc_alvaras/ ou baixa o mais recente do portal
(arquivo mensal de ~540 MB em mid-dadosabertos.curitiba.pr.gov.br).

A base não tem CNPJ. O cruzamento (sql/50_alvaras.sql) procura a empresa no mesmo endereço ou na mesma
rua e pontua por nome, CNAE e data de início. LGPD: o nome empresarial (no MEI, o nome da pessoa) fica só
numa tabela temporária durante o cruzamento; para refazer o cruzamento, rode este comando de novo (o
arquivo já baixado é reaproveitado).

Grava alvara, alvara_cnpj, empresa_alvara e a view alvara_sem_cnpj; relatório em relatorios/alvaras.md.
"""

import argparse
import csv
import logging
import tempfile
from pathlib import Path

from etl import baixar, config, db, leitura, portal
from etl.geocodificar import geocodificar

log = logging.getLogger("pmc_alvaras")
FONTE = "pmc_alvaras"

OBRIGATORIAS = [
    "NOME_EMPRESARIAL",
    "NUMERO_DO_ALVARA",
    "NOME_FANTASIA",
    "INICIO_ATIVIDADE",
    "DATA_EMISSAO",
    "DATA_EXPIRACAO",
    "ENDERECO",
    "NUMERO",
    "BAIRRO",
    "CEP",
    "CNAE_ATIVIDADE_PRINCIPAL",
]
CARGA = [
    "numero_alvara",
    "nome_empresarial",
    "nome_fantasia",
    "inicio",
    "emissao",
    "expiracao",
    "cep",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cnae",
    "atividade",
    "secundarios",
]


def obter_arquivo(arquivo: str | None) -> tuple[Path, str]:
    if arquivo:
        return Path(arquivo), arquivo
    local = baixar.arquivo_local(FONTE, r"Alvaras.*Base_de_Dados.*\.(csv|zip)$")
    if local:
        return local, str(local)
    a = portal.mais_recente(config.fonte(FONTE)["portal_chave"], padrao="Base_de_Dados")
    return baixar.baixar(a.url, FONTE), a.url


def linhas_carga(leitor):
    for r in leitor:
        numero = (r.get("NUMERO_DO_ALVARA") or "").strip()
        if not numero:
            continue
        complemento = " ".join(x for x in (r.get("UNIDADE"), r.get("ANDAR"), r.get("COMPLEMENTO")) if x and x.strip())
        secundarios = [r[k] for k in r if k and k.startswith("CNAE_ATIVIDADE_SECUNDARIA") and r[k] and r[k].strip()]
        yield [
            numero,
            r["NOME_EMPRESARIAL"],
            r["NOME_FANTASIA"],
            r["INICIO_ATIVIDADE"],
            r["DATA_EMISSAO"],
            r["DATA_EXPIRACAO"],
            r["CEP"],
            r["ENDERECO"],
            r["NUMERO"],
            complemento,
            r["BAIRRO"],
            r["CNAE_ATIVIDADE_PRINCIPAL"],
            r.get("ATIVIDADE_PRINCIPAL", ""),
            "|".join(secundarios),
        ]


def carregar(conn, caminho: Path) -> int:
    with (
        leitura.ler_csv(caminho, OBRIGATORIAS) as leitor,
        tempfile.TemporaryFile("w+", encoding="utf-8", newline="") as tmp,
    ):
        w = csv.writer(tmp)
        for linha in linhas_carga(leitor):
            w.writerow(linha)
        tmp.seek(0)
        with conn.cursor() as cur:
            cur.execute(f"CREATE TEMP TABLE alvara_carga ({', '.join(c + ' TEXT' for c in CARGA)}) ON COMMIT DROP")
            cur.copy_expert(f"COPY alvara_carga ({', '.join(CARGA)}) FROM STDIN WITH (FORMAT csv)", tmp)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE alvara CASCADE")
        cur.execute("""
            INSERT INTO alvara (numero_alvara, nome_fantasia, inicio_atividade, data_emissao, data_expiracao, cep,
                                logradouro, numero, complemento, bairro, cnae_principal, atividade_principal,
                                cnaes_secundarios, logr_chave, logr_completa, numero_int)
            SELECT DISTINCT ON (numero_alvara) numero_alvara, NULLIF(btrim(nome_fantasia), ''), data_br(inicio),
                   data_br(emissao), data_br(expiracao), norm_cep(cep), NULLIF(btrim(logradouro), ''),
                   NULLIF(btrim(numero), ''), NULLIF(btrim(complemento), ''), NULLIF(btrim(bairro), ''),
                   norm_cnae(cnae), NULLIF(btrim(atividade), ''),
                   ARRAY(SELECT norm_cnae(x) FROM unnest(string_to_array(secundarios, '|')) x WHERE norm_cnae(x) IS NOT NULL),
                   norm_logradouro(logradouro), norm_logradouro_completa(logradouro), norm_numero(numero)
            FROM alvara_carga
            ORDER BY numero_alvara, data_br(emissao) DESC NULLS LAST
        """)
        n = cur.rowcount
        cur.execute("""
            CREATE TEMP TABLE alvara_nome ON COMMIT DROP AS
            SELECT DISTINCT ON (numero_alvara) numero_alvara, norm_nome(nome_empresarial) AS nome_chave
            FROM alvara_carga ORDER BY numero_alvara
        """)
        cur.execute("DROP TABLE alvara_carga")
    return n


def geocodificar_alvaras(conn) -> None:
    geocodificar(
        conn,
        """
        SELECT a.numero_alvara, a.cep, a.logr_chave, a.logr_completa, a.numero_int,
               coalesce(norm_nome(a.nome_fantasia), n.nome_chave), norm_txt(a.bairro)
        FROM alvara a LEFT JOIN alvara_nome n USING (numero_alvara)
    """,
    )
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE alvara a SET geo_precisao = x.geo_precisao, geom = x.geom
            FROM alvo x WHERE x.id = a.numero_alvara
        """)
        cur.execute("DROP TABLE alvo")


def resumo(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*), count(*) FILTER (WHERE data_expiracao < current_date),
                   count(*) FILTER (WHERE geom IS NOT NULL) FROM alvara
        """)
        total, vencidos, geo = cur.fetchone()
        cur.execute("SELECT metodo, count(*), round(avg(pontuacao), 2) FROM alvara_cnpj GROUP BY 1 ORDER BY 1")
        metodos = cur.fetchall()
        cur.execute("""
            SELECT count(*) FILTER (WHERE ativa_sem_alvara), count(*) FILTER (WHERE alvara_de_cnpj_encerrado),
                   count(*) FILTER (WHERE alvara_vencido), count(*) FILTER (WHERE atividade_diverge),
                   count(*) FILTER (WHERE chegada_ao_endereco IS NOT NULL)
            FROM empresa_alvara
        """)
        sem, encerrado, vencido, diverge, chegada = cur.fetchone()
    casados = sum(n for _, n, _ in metodos)
    base = total or 1
    md = [
        "# Base de Alvarás x CNPJ",
        "",
        f"- Alvarás: {total} ({vencidos} vencidos); geocodificados: {geo} ({100 * geo / base:.1f}%)",
        f"- Casados com CNPJ: {casados} ({100 * casados / base:.1f}%)",
        "",
        "| método | alvarás | pontuação média |",
        "|---|---:|---:|",
    ]
    md += [f"| {m} | {n} | {p} |" for m, n, p in metodos]
    md += [
        "",
        "## Sinais por empresa",
        "",
        f"- Ativas em ponto comercial sem alvará casado: {sem}",
        f"- Alvará de CNPJ encerrado (ponto possivelmente vago ou CNPJ trocado): {encerrado}",
        f"- Alvará vencido: {vencido}",
        f"- Atividade do alvará diferente do CNAE da Receita (classe): {diverge}",
        f"- Empresas que chegaram ao endereço depois de abrir (data do alvará posterior): {chegada}",
        "",
        "Alvarás sem CNPJ correspondente ficam na view `alvara_sem_cnpj` (fora do recorte, CNPJ de outra",
        "cidade, nome muito diferente ou atividade sem CNPJ).",
    ]
    return "\n".join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", help="CSV (ou zip) já baixado")
    args = ap.parse_args(argv)
    with db.etapa("alvaras"):
        caminho, origem = obter_arquivo(args.arquivo)
        with db.conectar() as conn:
            db.criar_schema(conn)
            n = carregar(conn, caminho)
            log.info("%d alvarás carregados; geocodificando", n)
            if db.contar(conn, "SELECT count(*) FROM cnefe"):
                geocodificar_alvaras(conn)
            else:
                log.warning("cnefe vazio: alvarás ficam sem geocodificação (rode o M0)")
            db.executar_sql(conn, "50_alvaras.sql")
            md = resumo(conn)
            db.registrar(
                conn,
                FONTE,
                origem,
                caminho.name,
                baixar.sha256(caminho),
                n,
                casados=db.contar(conn, "SELECT count(*) FROM alvara_cnpj"),
            )
    config.RELATORIOS.mkdir(exist_ok=True)
    (config.RELATORIOS / "alvaras.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
