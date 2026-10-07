"""Regras de uso por zona (Lei de Zoneamento de Curitiba, 15.511/2019 e decretos) em zona_regra.

Uso:
    python -m etl.fontes.zona_regra                  # carrega apoio/zona_regra.csv (versionado no repositório)
    python -m etl.fontes.zona_regra --modelo         # gera relatorios/zona_regra_modelo.csv para preencher
    python -m etl.fontes.zona_regra --amostra 50     # amostra de "fora do uso permitido" para revisar

apoio/zona_regra.csv (separador ;): zona, cnae_prefixo, permitido, fonte, observacao.
    zona          código da zona como está em empresa_geo.zona (código da camada do IPPUC, ou o nome)
    cnae_prefixo  começo do código CNAE (2 a 7 dígitos; vale a regra de prefixo mais longo)
    permitido     S/N (também sim/não, true/false, 1/0)
    fonte         artigo, anexo ou decreto de onde saiu a regra (obrigatório: nada de regra sem fonte)
O arquivo é a fonte da verdade: a carga substitui zona_regra inteira. Zona que não existe na camada de
zoneamento e linha repetida dão erro, com a linha do arquivo.

--modelo lista, por zona, as divisões CNAE com empresas ativas (as que mais importam primeiro), com
permitido em branco. --amostra sorteia (de forma reproduzível) empresas classificadas fora do uso, sem nome,
para conferir no mapa e na lei antes de usar como sinal.
"""

import argparse
import csv
import logging
import re
from pathlib import Path

from etl import config, db, leitura

log = logging.getLogger("zona_regra")
ARQUIVO = config.RAIZ / "apoio" / "zona_regra.csv"
SIM = {"S", "SIM", "TRUE", "T", "1", "PERMITIDO"}
NAO = {"N", "NAO", "FALSE", "F", "0", "PROIBIDO"}


def ler_regras(caminho: Path, zonas: set[str]) -> list[tuple[str, str, bool, str]]:
    regras, erros, vistas = [], [], set()
    with leitura.ler_csv(caminho, ["zona", "cnae_prefixo", "permitido", "fonte"]) as leitor:
        for n, r in enumerate(leitor, start=2):
            zona = (r["ZONA"] or "").strip()
            prefixo = re.sub(r"\D", "", r["CNAE_PREFIXO"] or "")
            valor = leitura.norm_coluna(r["PERMITIDO"] or "")
            fonte = (r["FONTE"] or "").strip()
            if not zona and not prefixo:
                continue
            if zonas and zona not in zonas:
                erros.append(f"linha {n}: zona '{zona}' não existe na camada de zoneamento")
            if not 2 <= len(prefixo) <= 7:
                erros.append(f"linha {n}: cnae_prefixo '{r['CNAE_PREFIXO']}' precisa de 2 a 7 dígitos")
            if valor not in SIM | NAO:
                erros.append(f"linha {n}: permitido '{r['PERMITIDO']}' não é S/N")
            if not fonte:
                erros.append(f"linha {n}: sem fonte (artigo, anexo ou decreto)")
            if (zona, prefixo) in vistas:
                erros.append(f"linha {n}: regra repetida para {zona} x {prefixo}")
            vistas.add((zona, prefixo))
            regras.append((zona, prefixo, valor in SIM, fonte))
    if erros:
        raise ValueError(f"{caminho.name}:\n" + "\n".join(erros))
    return regras


def zonas_da_camada(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT coalesce(codigo, nome) FROM zoneamento")
        return {z for (z,) in cur.fetchall()}


def carregar(conn, caminho: Path) -> int:
    regras = ler_regras(caminho, zonas_da_camada(conn))
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT subclasse FROM cnae")
        subclasses = [s for (s,) in cur.fetchall()]
        if subclasses:  # planilha que perdeu o zero à esquerda ("111301") passa na validação mas não casa com nada
            for zona, prefixo, _, _ in regras:
                if not any(s.startswith(prefixo) for s in subclasses):
                    log.warning(
                        "prefixo %s (zona %s) não é começo de nenhum CNAE: zero à esquerda perdido?", prefixo, zona
                    )
        cur.execute("TRUNCATE zona_regra")
        cur.executemany("INSERT INTO zona_regra (zona, cnae_prefixo, permitido, fonte) VALUES (%s, %s, %s, %s)", regras)
    return len(regras)


def modelo(conn, destino: Path) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT g.zona, (SELECT max(z.nome) FROM zoneamento z WHERE coalesce(z.codigo, z.nome) = g.zona),
                   left(e.cnae_fiscal_principal, 2) AS divisao,
                   (SELECT max(c.divisao_descricao) FROM cnae c WHERE c.divisao = left(e.cnae_fiscal_principal, 2)),
                   count(*) AS ativas
            FROM empresa_geo g JOIN empresa e USING (cnpj)
            WHERE e.situacao_cadastral = '02' AND g.zona IS NOT NULL AND e.cnae_fiscal_principal IS NOT NULL
            GROUP BY 1, 2, 3, 4
            ORDER BY 1, 5 DESC, 3
        """)
        linhas = cur.fetchall()
        cur.execute("SELECT zona, cnae_prefixo, permitido, fonte FROM zona_regra")
        atuais = {(z, p): (perm, f) for z, p, perm, f in cur.fetchall()}
    destino.parent.mkdir(exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["zona", "cnae_prefixo", "permitido", "fonte", "observacao"])
        for zona, nome, divisao, descricao, ativas in linhas:
            perm, fonte = atuais.get((zona, divisao), (None, ""))
            w.writerow(
                [
                    zona,
                    divisao,
                    "" if perm is None else ("S" if perm else "N"),
                    fonte,
                    f"{nome or ''} | {descricao or ''} | {ativas} ativas",
                ]
            )
    return len(linhas)


def amostra(conn, n: int, destino: Path) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.cnpj, u.zona, u.cnae_fiscal_principal, c.descricao, u.regra_prefixo, r.fonte, g.bairro,
                   g.geo_precisao, round(ST_Y(g.geom)::NUMERIC, 6), round(ST_X(g.geom)::NUMERIC, 6)
            FROM uso_zoneamento u
            JOIN empresa e USING (cnpj)
            JOIN empresa_geo g USING (cnpj)
            LEFT JOIN cnae c ON c.subclasse = u.cnae_fiscal_principal
            LEFT JOIN zona_regra r ON r.zona = u.zona AND r.cnae_prefixo = u.regra_prefixo
            WHERE u.permitido IS FALSE AND e.situacao_cadastral = '02'
            ORDER BY md5(u.cnpj)
            LIMIT %s
            """,
            (n,),
        )
        linhas = cur.fetchall()
    destino.parent.mkdir(exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(
            [
                "cnpj",
                "zona",
                "cnae",
                "atividade",
                "regra_prefixo",
                "fonte",
                "bairro",
                "geo_precisao",
                "lat",
                "lon",
                "confere (S/N)",
                "nota",
            ]
        )
        w.writerows([[*li, "", ""] for li in linhas])
    return len(linhas)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", type=Path, default=ARQUIVO)
    ap.add_argument("--modelo", action="store_true")
    ap.add_argument("--amostra", type=int)
    args = ap.parse_args(argv)
    with db.etapa("zona_regra"), db.conectar() as conn:
        db.criar_schema(conn)
        if args.modelo:
            n = modelo(conn, config.RELATORIOS / "zona_regra_modelo.csv")
            print(f"{n} pares zona x divisão em relatorios/zona_regra_modelo.csv: preencha e copie para {ARQUIVO}")
            return
        if args.amostra:
            n = amostra(conn, args.amostra, config.RELATORIOS / "uso_zoneamento_amostra.csv")
            print(f"{n} casos fora do uso permitido em relatorios/uso_zoneamento_amostra.csv")
            return
        n = carregar(conn, args.arquivo)
        db.registrar(conn, "zona_regra", str(args.arquivo), args.arquivo.name, linhas=n)
    print(f"{n} regras carregadas em zona_regra; rode python -m etl.enriquecer para atualizar uso_zoneamento")


if __name__ == "__main__":
    main()
