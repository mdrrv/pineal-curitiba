"""Curitiba sintética no tamanho real, nos layouts das fontes, para medir o pipeline antes da rodada real.

Uso:
    python scripts/volume_sintetico.py --dados /caminho/dados --dsn "host=... dbname=pineal_volume" [--fator 1.0]

Escreve em <dados>/bruto/ os arquivos que os ETLs procuram (setores, camadas do IPPUC, CNEFE, alvarás,
SiGesGuarda, Censo, GTFS) e cria dados_rfb.cnpj_consolidado (e dados_rfb.cnae) no banco do --dsn.
Com --fator 1: ~1 milhão de endereços e ~1 milhão de CNPJs. Tudo determinístico (semente fixa).

Não é dado real: nomes, endereços e CNPJs são inventados. Serve só para tempo, memória e plano de consulta.
"""

import argparse
import csv
import io
import math
import random
import zipfile
from pathlib import Path

import geopandas as gpd
import psycopg2
from shapely.geometry import box

LON0, LAT0 = -49.39, -25.60  # canto sudoeste
PASSO_LON, PASSO_LAT = 0.00042, 0.00038  # ~42 m entre cruzamentos
NOMES = [
    "SILVA",
    "SOUZA",
    "PEREIRA",
    "OLIVEIRA",
    "SANTOS",
    "COSTA",
    "RIBEIRO",
    "ALMEIDA",
    "CARVALHO",
    "GOMES",
    "MARTINS",
    "ARAUJO",
    "BARBOSA",
    "ROCHA",
    "DIAS",
    "MOREIRA",
    "NUNES",
    "MENDES",
    "FREITAS",
    "CARDOSO",
    "TEIXEIRA",
    "MONTEIRO",
    "MOURA",
    "CORREIA",
    "PINTO",
    "CAMPOS",
    "VIEIRA",
    "LOPES",
    "FARIAS",
    "BATISTA",
]
PRENOMES = [
    "JOAO",
    "MARIA",
    "JOSE",
    "ANA",
    "PEDRO",
    "PAULO",
    "CARLOS",
    "LUCAS",
    "MARCOS",
    "RAFAEL",
    "BRUNO",
    "FERNANDA",
    "JULIANA",
    "PATRICIA",
    "ANTONIO",
    "FRANCISCO",
    "LUIZ",
    "MANOEL",
    "GERALDO",
    "AUGUSTO",
]
TITULOS = [
    ("DOUTOR", "DR"),
    ("MARECHAL", "MAL"),
    ("PROFESSOR", "PROF"),
    ("GENERAL", "GAL"),
    ("PADRE", "PE"),
    ("", ""),
    ("", ""),
    ("", ""),
    ("", ""),
    ("", ""),
]
TIPOS = [("RUA", "R"), ("AVENIDA", "AV"), ("TRAVESSA", "TV"), ("ALAMEDA", "AL")]
CNAES = [
    "4711302",
    "4712100",
    "4721102",
    "4723700",
    "4744099",
    "4751201",
    "4753900",
    "4755502",
    "4759899",
    "4771701",
    "4772500",
    "4781400",
    "4782201",
    "4789004",
    "5611201",
    "5611203",
    "5612100",
    "5620104",
    "6201501",
    "6202300",
    "6204000",
    "6311900",
    "6911701",
    "6920601",
    "7020400",
    "7111100",
    "7319002",
    "7490104",
    "8121400",
    "8219999",
    "8511200",
    "8513900",
    "8599604",
    "8630501",
    "8630503",
    "8650004",
    "8690999",
    "9313100",
    "9602501",
    "9602502",
    "9609207",
    "4520001",
    "4530703",
    "4120400",
    "4321500",
    "4399103",
    "4930202",
    "5320202",
    "8211300",
    "1091102",
    "1412601",
    "3101200",
    "4635499",
    "4649499",
]
NATUREZAS = [("2062", 0.55), ("2135", 0.35), ("2240", 0.05), ("2305", 0.05)]
ESPECIES = [(1, 0.80), (2, 0.01), (4, 0.01), (5, 0.01), (6, 0.15), (7, 0.01), (8, 0.01)]
NATUREZAS_GM = [
    "FURTO",
    "ROUBO",
    "DANO AO PATRIMONIO PUBLICO",
    "PERTURBACAO DO SOSSEGO",
    "AMEACA",
    "LESAO CORPORAL",
    "QUEDA DE ARVORE",
    "ALAGAMENTO",
    "APOIO A OUTROS ORGAOS",
    "ACIDENTE DE TRANSITO",
    "PICHACAO",
    "VIAS DE FATO",
    "USO DE ENTORPECENTES",
    "FISCALIZACAO DE COMERCIO AMBULANTE",
]


def escolher(rng, pares):
    x, acc = rng.random(), 0.0
    for v, p in pares:
        acc += p
        if x < acc:
            return v
    return pares[-1][0]


def dv(base: str) -> str:
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        r = sum(int(d) * p for d, p in zip(base, pesos, strict=True)) % 11
        base += "0" if r < 2 else str(11 - r)
    return base


class Cidade:
    """Grade de ruas: linhas horizontais e verticais cortadas em trechos com nome e CEP próprios."""

    def __init__(self, n: int, rng: random.Random):
        self.n = n  # cruzamentos por lado
        self.trecho = 25  # cruzamentos por trecho de rua com o mesmo nome
        self.rng = rng
        self.ruas = {}  # (orientacao, linha, trecho) -> (tipo, titulo, nome, cep)
        cep = 80000000
        for orient in "HV":
            for linha in range(n):
                for t in range(math.ceil(n / self.trecho)):
                    tipo = TIPOS[0] if orient == "H" else rng.choice(TIPOS)
                    titulo = rng.choice(TITULOS)
                    nome = f"{rng.choice(PRENOMES)} {rng.choice(NOMES)}"
                    cep += rng.randint(1, 7)
                    self.ruas[(orient, linha, t)] = (tipo, titulo, nome, f"{cep:08d}")

    def lonlat(self, i, j):
        return LON0 + i * PASSO_LON, LAT0 + j * PASSO_LAT

    def bairro(self, i, j):
        lado = max(1, self.n // 9)
        return f"B{min(j // lado, 8)}{min(i // lado, 8)}"

    def setor(self, i, j):
        lado = 7
        return f"4106902{(j // lado):04d}{(i // lado):04d}P"


def logradouro_completo(rua):
    (tipo, _), (titulo, _), nome, _ = rua
    return tipo, titulo, nome


def grafia_rfb(rng, rua) -> str:
    """Como a Receita costuma escrever: abreviado, sem título, com ponto."""
    (tipo, tipo_abr), (titulo, titulo_abr), nome, _ = rua
    r = rng.random()
    if r < 0.4:
        return " ".join(x for x in (tipo_abr, titulo_abr, nome) if x)
    if r < 0.7:
        return " ".join(x for x in (tipo, titulo, nome) if x)
    if r < 0.9:
        return " ".join(x for x in (tipo_abr + ".", (titulo_abr + ".") if titulo_abr else "", nome) if x)
    return " ".join(x for x in (tipo_abr, nome) if x)  # sem o título


def gerar(dados: Path, dsn: str, fator: float, semente: int = 42):
    rng = random.Random(semente)
    n = max(30, int(500 * math.sqrt(fator)))
    cidade = Cidade(n, rng)
    bruto = dados / "bruto"
    for p in ["ibge_setores", "ippuc", "ibge_cnefe", "pmc_alvaras", "pmc_sigesguarda", "ibge_censo_setor", "urbs_gtfs"]:
        (bruto / p).mkdir(parents=True, exist_ok=True)

    # --- CNEFE: endereços dos dois lados de cada rua, em cada cruzamento ---------------------------------
    print(f"grade {n} x {n}: gerando CNEFE")
    enderecos = []  # (i, j, orient, numero, especie, cep, rua)
    buf = io.StringIO()
    buf.write(
        "COD_UNICO_ENDERECO;COD_UF;COD_MUNICIPIO;COD_SETOR;CEP;NOM_TIPO_SEGLOGR;NOM_TITULO_SEGLOGR;"
        "NOM_SEGLOGR;NUM_ENDERECO;LATITUDE;LONGITUDE;NV_GEO_COORD;COD_ESPECIE;DSC_ESTABELECIMENTO\n"
    )
    cod = 0
    for orient in "HV":
        for linha in range(n):
            for pos in range(n):
                i, j = (pos, linha) if orient == "H" else (linha, pos)
                rua = cidade.ruas[(orient, linha, pos // cidade.trecho)]
                tipo, titulo, nome = logradouro_completo(rua)
                for lado in (0, 1):
                    numero = (pos % cidade.trecho) * 40 + 10 + lado
                    especie = escolher(rng, ESPECIES)
                    lon, lat = cidade.lonlat(i, j)
                    lon += (rng.random() - 0.5) * 0.00008 + (0.00005 if lado else -0.00005) * (orient == "V")
                    lat += (rng.random() - 0.5) * 0.00008 + (0.00005 if lado else -0.00005) * (orient == "H")
                    estab = (
                        f"{rng.choice(NOMES)} {rng.choice(['COMERCIO', 'SERVICOS', 'MERCADO', 'PADARIA'])}"
                        if especie == 6 and rng.random() < 0.3
                        else ""
                    )
                    cod += 1
                    buf.write(
                        f"{cod};41;4106902;{cidade.setor(i, j)};{rua[3]};{tipo};{titulo};{nome};{numero};"
                        f"{str(round(lat, 7)).replace('.', ',')};{str(round(lon, 7)).replace('.', ',')};1;{especie};{estab}\n"
                    )
                    enderecos.append((i, j, orient, numero, especie, rua))
    with zipfile.ZipFile(bruto / "ibge_cnefe" / "4106902_CURITIBA.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("4106902_CURITIBA.csv", buf.getvalue().encode("utf-8"))
    print(f"  {cod} endereços")

    # --- setores, bairros, regionais, zoneamento -----------------------------------------------------------
    lado_s = 7
    setores = {}
    for sj in range(math.ceil(n / lado_s)):
        for si in range(math.ceil(n / lado_s)):
            x0, y0 = cidade.lonlat(si * lado_s - 0.5, sj * lado_s - 0.5)
            x1, y1 = cidade.lonlat(min((si + 1) * lado_s, n) - 0.5, min((sj + 1) * lado_s, n) - 0.5)
            setores[f"4106902{sj:04d}{si:04d}P"] = box(x0, y0, x1, y1)
    pasta = dados / "_shp"
    pasta.mkdir(exist_ok=True)
    gpd.GeoDataFrame(
        {"CD_SETOR": list(setores), "CD_MUN": "4106902", "NM_MUN": "Curitiba"},
        geometry=list(setores.values()),
        crs=4674,
    ).to_file(pasta / "PR_setores_CD2022.shp")
    with zipfile.ZipFile(bruto / "ibge_setores" / "PR_setores_CD2022.zip", "w") as z:
        for p in pasta.glob("PR_setores_CD2022.*"):
            z.write(p, p.name)
    lado_b = max(1, n // 9)
    bairros, nomes_b = [], []
    for bj in range(9):
        for bi in range(9):
            x0, y0 = cidade.lonlat(bi * lado_b - 0.5, bj * lado_b - 0.5)
            x1, y1 = cidade.lonlat(
                (n if bi == 8 else (bi + 1) * lado_b) - 0.5, (n if bj == 8 else (bj + 1) * lado_b) - 0.5
            )
            bairros.append(box(x0, y0, x1, y1))
            nomes_b.append(f"B{bj}{bi}")
    gpd.GeoDataFrame({"NOME": nomes_b, "CODIGO": list(range(1, 82))}, geometry=bairros, crs=4326).to_crs(31982).to_file(
        bruto / "ippuc" / "DIVISA_DE_BAIRROS.shp"
    )
    regionais = [
        box(*cidade.lonlat(-0.5, -0.5), *cidade.lonlat(n / 2, n)),
        box(*cidade.lonlat(n / 2, -0.5), *cidade.lonlat(n, n)),
    ]
    gpd.GeoDataFrame({"NOME_REGIO": ["OESTE", "LESTE"]}, geometry=regionais, crs=4326).to_file(
        bruto / "ippuc" / "regionais.geojson", driver="GeoJSON"
    )
    zonas = []
    for _ in range(30):
        x0, y0 = cidade.lonlat(rng.randint(0, n - 50), rng.randint(0, n - 50))
        zonas.append(box(x0, y0, x0 + 50 * PASSO_LON, y0 + 50 * PASSO_LAT))
    gpd.GeoDataFrame(
        {"SG_ZONA": [f"Z{k}" for k in range(30)], "NM_ZONA": [f"ZONA {k}" for k in range(30)]}, geometry=zonas, crs=4326
    ).to_file(bruto / "ippuc" / "zoneamento.gpkg", driver="GPKG")

    # --- CNPJs (dados_rfb.cnpj_consolidado) ----------------------------------------------------------------
    n_cnpj = int(1_000_000 * fator)
    print(f"gerando {n_cnpj} CNPJs")
    comerciais = [e for e in enderecos if e[4] == 6]
    salas = rng.sample(comerciais, max(1, len(comerciais) // 2000))  # endereços de domiciliação
    out = io.StringIO()
    w = csv.writer(out)
    ativos = []
    raiz = 10_000_000
    k = 0
    while k < n_cnpj:
        raiz += rng.randint(1, 3)
        natureza = escolher(rng, NATUREZAS)
        mei = natureza == "2135" and rng.random() < 0.9
        filiais = 1 if natureza == "2135" or rng.random() < 0.95 else rng.randint(2, 6)
        nome_base = (
            f"{rng.choice(NOMES)} {rng.choice(['COMERCIO', 'SERVICOS', 'DISTRIBUIDORA', 'CONSULTORIA', 'ALIMENTOS'])}"
        )
        for f in range(1, filiais + 1):
            if k >= n_cnpj:
                break
            k += 1
            cnpj = dv(f"{raiz:08d}{f:04d}")
            if natureza == "2135":
                razao = f"{rng.choice(PRENOMES)} {rng.choice(NOMES)} {rng.randint(10**10, 10**11 - 1)}"
            else:
                razao = f"{nome_base} LTDA"
            e = (
                rng.choice(salas)
                if rng.random() < 0.03
                else (rng.choice(comerciais) if rng.random() < 0.55 else rng.choice(enderecos))
            )
            i, j, orient, numero, especie, rua = e
            inicio_ano = rng.choices(range(1990, 2027), weights=[1] * 20 + [2] * 10 + [4] * 7)[0]
            inicio = f"{inicio_ano}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
            r = rng.random()
            situacao, data_sit = ("02", inicio) if r < 0.5 else (("08", None) if r < 0.95 else ("04", None))
            if situacao != "02":
                fim_ano = min(2026, inicio_ano + int(rng.expovariate(1 / 4)))
                data_sit = f"{fim_ano}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
                if data_sit < inicio:
                    data_sit = inicio
            cep = rua[3] if rng.random() > 0.05 else f"{80000000 + rng.randint(0, 99999):08d}"
            num = str(numero) if rng.random() > 0.03 else "SN"
            cnae = rng.choice(CNAES)
            w.writerow(
                [
                    cnpj,
                    cnpj[:8],
                    razao,
                    rng.choice(["", "", nome_base.split()[0] + " " + cnae[:2]]),
                    situacao,
                    data_sit or "",
                    inicio,
                    cnae,
                    natureza,
                    f"{rng.randint(1, 500) * 1000}.00",
                    "01" if mei else rng.choice(["01", "03", "05"]),
                    "S" if rng.random() < 0.6 else "N",
                    "S" if mei else "N",
                    "1" if f == 1 else "2",
                    grafia_rfb(rng, rua),
                    num,
                    rng.choice(["", "", "SALA 1", "LOJA 2", "APTO 31"]),
                    cidade.bairro(i, j),
                    cep,
                    "PR",
                    "7535",
                    "CURITIBA",
                ]
            )
            if situacao == "02":
                ativos.append((cnpj, razao, cnae, inicio, e))
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("""
            DROP SCHEMA IF EXISTS dados_rfb CASCADE;
            CREATE SCHEMA dados_rfb;
            CREATE TABLE dados_rfb.cnpj_consolidado (
                cnpj VARCHAR(14), cnpj_basico VARCHAR(8), razao_social TEXT, nome_fantasia TEXT, situacao_cadastral VARCHAR(2),
                data_situacao_cadastral VARCHAR(8), data_inicio_atividade VARCHAR(8), cnae_fiscal_principal VARCHAR(7),
                natureza_juridica VARCHAR(4), capital_social NUMERIC(18,2), porte_empresa VARCHAR(2),
                opcao_pelo_simples VARCHAR(1), opcao_mei VARCHAR(1), identificador_mf VARCHAR(1), logradouro TEXT,
                numero TEXT, complemento TEXT, bairro TEXT, cep VARCHAR(8), uf VARCHAR(2), municipio VARCHAR(4),
                nome_municipio TEXT);
            CREATE TABLE dados_rfb.cnae (codigo VARCHAR(7), descricao TEXT);
        """)
        out.seek(0)
        cur.copy_expert("COPY dados_rfb.cnpj_consolidado FROM STDIN WITH (FORMAT csv)", out)
        cur.executemany("INSERT INTO dados_rfb.cnae VALUES (%s, %s)", [(c, f"ATIVIDADE {c}") for c in CNAES])
        cur.execute("CREATE INDEX ON dados_rfb.cnpj_consolidado (uf, municipio)")
    print(f"  {k} CNPJs, {len(ativos)} ativos")

    # --- alvarás: 60% dos ativos em ponto comercial têm alvará; mais ruído --------------------------------
    print("gerando alvarás")
    cab = [
        "NOME_EMPRESARIAL",
        "INICIO_ATIVIDADE",
        "NUMERO_DO_ALVARA",
        "NOME_FANTASIA",
        "DATA_EMISSAO",
        "DATA_EXPIRACAO",
        "ENDERECO",
        "NUMERO",
        "UNIDADE",
        "ANDAR",
        "COMPLEMENTO",
        "BAIRRO",
        "CEP",
        "CNAE_ATIVIDADE_PRINCIPAL",
        "ATIVIDADE_PRINCIPAL",
        "CNAE_ATIVIDADE_SECUNDARIA01",
        "ATIVIDADE_SECUNDARIA01",
    ]
    linhas = [";".join(cab)]
    na = 0
    for _cnpj, razao, cnae, inicio, e in ativos:
        if e[4] != 6 or rng.random() > 0.6:
            continue
        na += 1
        i, j, _, numero, _, rua = e
        tipo, titulo, nome = logradouro_completo(rua)
        d = f"{inicio[6:8]}/{inicio[4:6]}/{inicio[:4]}"
        linhas.append(
            ";".join(
                [
                    razao,
                    d,
                    f"A{na:07d}",
                    "",
                    "01/01/2025",
                    "31/12/2027" if rng.random() > 0.1 else "31/12/2024",
                    " ".join(x for x in (tipo, titulo, nome) if x),
                    str(numero),
                    "",
                    "",
                    "",
                    cidade.bairro(i, j),
                    rua[3][:5] + "-" + rua[3][5:],
                    f"{cnae[:4]}-{cnae[4]}/{cnae[5:]}",
                    "ATIVIDADE",
                    "",
                    "",
                ]
            )
        )
    for _ in range(na // 3):  # alvarás sem CNPJ correspondente
        na += 1
        e = rng.choice(enderecos)
        tipo, titulo, nome = logradouro_completo(e[5])
        linhas.append(
            ";".join(
                [
                    f"{rng.choice(NOMES)} ME",
                    "01/01/2015",
                    f"A{na:07d}",
                    "",
                    "01/01/2025",
                    "31/12/2027",
                    " ".join(x for x in (tipo, titulo, nome) if x),
                    str(e[3]),
                    "",
                    "",
                    "",
                    "X",
                    e[5][3],
                    rng.choice(CNAES),
                    "ATIVIDADE",
                    "",
                    "",
                ]
            )
        )
    (bruto / "pmc_alvaras" / "2026-10-01_Alvaras_-_Base_de_Dados.csv").write_bytes("\r\n".join(linhas).encode("cp1252"))
    print(f"  {na} alvarás")

    # --- SiGesGuarda --------------------------------------------------------------------------------------
    n_oc = int(300_000 * fator)
    cab = [
        "ATENDIMENTO_BAIRRO_NOME",
        "LOGRADOURO_NOME",
        "NATUREZA1_DEFESA_CIVIL",
        "NATUREZA1_DESCRICAO",
        "NATUREZA2_DEFESA_CIVIL",
        "NATUREZA2_DESCRICAO",
        "OCORRENCIA_CODIGO",
        "OCORRENCIA_DATA",
        "OCORRENCIA_HORA",
        "REGIONAL_FATO_NOME",
        "FLAG_FLAGRANTE",
        "EQUIPAMENTO_URBANO_NOME",
    ]
    linhas = [";".join(cab)]
    for c in range(n_oc):
        e = rng.choice(enderecos)
        tipo, titulo, nome = logradouro_completo(e[5])
        n1 = rng.choice(NATUREZAS_GM)
        n2 = rng.choice(NATUREZAS_GM) if rng.random() < 0.2 else ""
        linhas.append(
            ";".join(
                [
                    cidade.bairro(e[0], e[1]),
                    " ".join(x for x in (tipo, titulo, nome) if x),
                    "S" if n1 in ("QUEDA DE ARVORE", "ALAGAMENTO") else "N",
                    n1,
                    "N" if n2 else "",
                    n2,
                    str(c + 1),
                    f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.choice([2023, 2024, 2025, 2026])}",
                    f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
                    "MATRIZ",
                    "N",
                    "",
                ]
            )
        )
    (bruto / "pmc_sigesguarda" / "2026-10-01_sigesguarda_-_Base_de_Dados.csv").write_bytes(
        "\r\n".join(linhas).encode("cp1252")
    )
    print(f"  {n_oc} ocorrências")

    # --- Censo por setor ------------------------------------------------------------------------------------
    basico = ["CD_SETOR;CD_MUN;AREA_KM2;v0001;v0002;v0005;v0007"]
    demo = ["CD_setor;V01007;V01008;" + ";".join(f"V0103{i}" for i in range(1, 10)) + ";V01040;V01041"]
    renda = ["CD_SETOR;V06001;V06004"]
    for cd in setores:
        p = rng.randint(200, 1200)
        dom = p // 3
        basico.append(f"{cd};4106902;0,0400;{p};{dom + 5};{str(round(p / dom, 2)).replace('.', ',')};{dom}")
        idades = [p // 11] * 11
        demo.append(f"{cd[:-1]};{p // 2};{p - p // 2};" + ";".join(map(str, idades)))
        renda.append(f"{cd};{dom};{rng.randint(1500, 15000)},00")
    for nome, li in [("basico", basico), ("demografia", demo), ("renda_responsavel", renda)]:
        (bruto / "ibge_censo_setor" / f"Agregados_por_setores_{nome}_BR.csv").write_text(
            "\n".join(li), encoding="utf-8"
        )

    # --- GTFS: linhas retas ao longo das ruas H e V -------------------------------------------------------
    stops, stop_times, trips = (
        ["stop_id,stop_name,stop_lat,stop_lon"],
        ["trip_id,arrival_time,departure_time,stop_id,stop_sequence"],
        ["route_id,service_id,trip_id"],
    )
    n_linhas = int(250 * math.sqrt(fator)) or 10
    vistos = set()
    for r_ in range(n_linhas):
        orient = "H" if r_ % 2 else "V"
        linha = rng.randint(0, n - 1)
        pts = list(range(0, n, 8))
        for pos in pts:
            i, j = (pos, linha) if orient == "H" else (linha, pos)
            sid = f"S{i}_{j}"
            if sid not in vistos:
                vistos.add(sid)
                lon, lat = cidade.lonlat(i, j)
                stops.append(f"{sid},P,{lat:.6f},{lon:.6f}")
        for v in range(60):
            tid = f"T{r_}_{v}"
            trips.append(f"R{r_},U,{tid}")
            t0 = 5 * 3600 + v * 15 * 60
            for s, pos in enumerate(pts):
                i, j = (pos, linha) if orient == "H" else (linha, pos)
                t = t0 + s * 60
                hh = f"{t // 3600:02d}:{t % 3600 // 60:02d}:00"
                stop_times.append(f"{tid},{hh},{hh},S{i}_{j},{s + 1}")
    with zipfile.ZipFile(bruto / "urbs_gtfs" / "gtfs.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("stops.txt", "\n".join(stops))
        z.writestr("trips.txt", "\n".join(trips))
        z.writestr("stop_times.txt", "\n".join(stop_times))
        z.writestr(
            "calendar.txt",
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "U,1,1,1,1,1,1,1,20200101,20301231",
        )
    print(f"  GTFS: {len(stops) - 1} pontos, {len(stop_times) - 1} paradas")

    # --- vias (para as isócronas): a própria grade -------------------------------------------------------
    from shapely.geometry import LineString

    linhas_v = [LineString([cidade.lonlat(0, j), cidade.lonlat(n - 1, j)]) for j in range(n)]
    linhas_v += [LineString([cidade.lonlat(i, 0), cidade.lonlat(i, n - 1)]) for i in range(n)]
    (bruto / "osm_vias").mkdir(exist_ok=True)
    gpd.GeoDataFrame({"highway": ["residential"] * len(linhas_v)}, geometry=linhas_v, crs=4326).to_file(
        bruto / "osm_vias" / "vias.gpkg", driver="GPKG"
    )
    print("pronto")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", type=Path, required=True)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--fator", type=float, default=1.0)
    a = ap.parse_args()
    gerar(a.dados, a.dsn, a.fator)
