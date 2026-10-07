from etl import db, geocodificar, territorio

LON0, LAT0 = -49.2700, -25.4300
PASSO = 0.00005  # ~5 m entre números vizinhos


def cnefe(cur, cod, logradouro, numero, cep, lon, lat, estabelecimento=None, especie=1):
    cur.execute(
        """
        INSERT INTO cnefe (cod_unico, cep, logradouro, logr_chave, logr_completa, numero, especie,
                           estabelecimento, nome_chave, geom)
        VALUES (%s, %s, %s, norm_logradouro(%s), norm_logradouro_completa(%s), %s, %s, %s, norm_nome(%s),
                ST_SetSRID(ST_MakePoint(%s, %s), 4326))
    """,
        (cod, cep, logradouro, logradouro, logradouro, numero, especie, estabelecimento, estabelecimento, lon, lat),
    )


def empresa(cur, cnpj, logradouro, numero, cep, fantasia=None, bairro=None):
    cur.execute(
        """INSERT INTO empresa (cnpj, situacao_cadastral, nome_fantasia, logradouro, numero, cep, bairro)
                   VALUES (%s,'02',%s,%s,%s,%s,%s)""",
        (cnpj, fantasia, logradouro, numero, cep, bairro),
    )


def montar(conn):
    with conn.cursor() as cur:
        i = 0
        for n in range(100, 200):  # pares de um lado, ímpares do outro
            i += 1
            lat = LAT0 + (0.0001 if n % 2 else 0)
            cnefe(cur, f"a{i}", "RUA DOUTOR FAIVRE", n, "80060140", LON0 + (n - 100) * PASSO, lat)
        cnefe(
            cur,
            "estab",
            "RUA DOUTOR FAIVRE",
            300,
            "80060140",
            LON0 + 0.003,
            LAT0 + 0.0005,
            estabelecimento="PADARIA PAO DOURADO",
            especie=6,
        )
        for n in range(1, 60):
            i += 1
            cnefe(cur, f"b{i}", "RUA MARECHAL FLORIANO PEIXOTO", n, "80010130", LON0 + 0.01 + n * PASSO, LAT0)
        for _ in range(3):
            i += 1
            cnefe(cur, f"c{i}", "TRAVESSA UNICA", None, "80000500", LON0 + 0.02 + i * PASSO, LAT0)
        cnefe(cur, "sj", "RUA SAO JOSE", 10, "80000100", LON0 + 0.03, LAT0)
        cur.execute(f"""INSERT INTO bairro (codigo, nome, geom) VALUES
            ('1', 'CENTRO', ST_Multi(ST_MakeEnvelope({LON0 + 0.05}, {LAT0}, {LON0 + 0.06}, {LAT0 + 0.01}, 4326)))""")

        empresa(cur, "00000000000001", "R DR FAIVRE", "150", "80060140")  # endereco
        empresa(cur, "00000000000002", "RUA DOUTOR FAIVRE", "150", "99999999")  # endereco_sem_cep
        empresa(cur, "00000000000003", "R DR FAIVRE", "207", "80060140")  # numero_proximo (199)
        empresa(cur, "00000000000004", "R DR FAIVRE", "S/N", "80060140")  # logradouro
        empresa(cur, "00000000000005", "R MAL FLORIANO PEIXOT", "S/N", "80010130")  # logradouro_aproximado
        empresa(cur, "00000000000006", "TV UNICA", "", None)  # logradouro_sem_cep
        empresa(cur, "00000000000007", "RUA INEXISTENTE", "10", "80060140")  # cep
        empresa(cur, "00000000000008", "RUA INEXISTENTE", "10", None)  # nao_localizado
        empresa(cur, "00000000000009", "R DR FAIVRE", "900", "80060140")  # longe demais: logradouro
        empresa(
            cur, "00000000000010", "R DR FAIVRE", "999", "80060140", fantasia="PADARIA PAO DOURADO LTDA"
        )  # estabelecimento
        empresa(cur, "00000000000011", "R JOSE", "10", "99999999")  # não pode virar R. São José
        empresa(cur, "00000000000012", "RUA INEXISTENTE", "1", None, bairro="Centro")  # bairro


def niveis(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT cnpj, geo_precisao, ST_X(geom), ST_Y(geom) FROM empresa_geo ORDER BY cnpj")
        return {c: (p, x, y) for c, p, x, y in cur.fetchall()}


def test_niveis(conn):
    montar(conn)
    geocodificar.gravar_empresas(conn)
    r = niveis(conn)
    assert r["00000000000001"][0] == "endereco"
    assert abs(r["00000000000001"][1] - (LON0 + 50 * PASSO)) < 1e-9
    assert r["00000000000002"][0] == "endereco_sem_cep"
    assert r["00000000000003"][0] == "numero_proximo"
    assert abs(r["00000000000003"][1] - (LON0 + 99 * PASSO)) < 1e-9  # pegou o 199, mesmo lado
    assert r["00000000000004"][0] == "logradouro"
    assert r["00000000000005"][0] == "logradouro_aproximado"
    assert r["00000000000006"][0] == "logradouro_sem_cep"
    assert r["00000000000007"][0] == "cep"
    assert r["00000000000008"] == ("nao_localizado", None, None)
    assert r["00000000000009"][0] == "logradouro"
    assert r["00000000000010"][0] == "estabelecimento"
    assert abs(r["00000000000010"][1] - (LON0 + 0.003)) < 1e-9
    assert r["00000000000011"] == ("nao_localizado", None, None)
    assert r["00000000000012"][0] == "bairro"


def test_resumo_e_relatorio(conn):
    montar(conn)
    geocodificar.gravar_empresas(conn)
    linhas = geocodificar.resumo(conn)
    assert [p for p, _, _ in linhas] == geocodificar.ORDEM
    assert sum(t for _, t, _ in linhas) == 12
    md = geocodificar.relatorio(linhas)
    assert "| nao_localizado | 2 |" in md


def test_avaliacao_em_metros(conn):
    from etl import avaliar_geocodificacao

    montar(conn)
    linhas = avaliar_geocodificacao.avaliar(conn, amostra=20, semente="x")
    assert sum(r[1] for r in linhas) == 20
    por = {r[0]: r for r in linhas}
    # escondendo o próprio ponto, o vizinho mais próximo de mesma paridade fica a ~10 m
    assert "numero_proximo" in por and por["numero_proximo"][2] < 20
    assert "| numero_proximo |" in avaliar_geocodificacao.relatorio(linhas, 20)


def test_territorio(conn):
    montar(conn)
    geocodificar.gravar_empresas(conn)
    caixa = f"ST_Multi(ST_MakeEnvelope({LON0 - 0.001}, {LAT0 - 0.001}, {LON0 + 0.006}, {LAT0 + 0.001}, 4326))"
    with conn.cursor() as cur:
        cur.execute("DELETE FROM bairro")
        cur.execute(f"INSERT INTO setor (cd_setor, geom) VALUES ('410690205000001', {caixa})")
        cur.execute(f"INSERT INTO bairro (codigo, nome, geom) VALUES ('1', 'CENTRO', {caixa})")
    assert territorio.calcular_h3(conn) == 10
    db.executar_sql(conn, "20_territorio.sql")
    with conn.cursor() as cur:
        cur.execute("SELECT cd_setor, bairro, regional, h3_8, h3_9 FROM empresa_geo WHERE cnpj = '00000000000001'")
        setor, bairro, regional, h3_8, h3_9 = cur.fetchone()
        cur.execute("SELECT count(*) FROM empresa_geo WHERE bairro IS NULL AND geom IS NOT NULL")
        fora = cur.fetchone()[0]
    assert (setor, bairro, regional) == ("410690205000001", "CENTRO", None)
    assert h3_8.startswith("88") and h3_9.startswith("89")
    assert fora == 3  # Floriano Peixoto, Travessa Única e o ponto do bairro de teste ficam fora da caixa
    assert "| bairro |" in territorio.resumo(conn)


def test_desempate_na_divisa_e_sobreposicao(conn):
    """Ponto na divisa de dois bairros e dentro de duas zonas sobrepostas: sempre o mesmo resultado."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO empresa (cnpj) VALUES ('1')")
        cur.execute(
            f"INSERT INTO empresa_geo (cnpj, geom) VALUES ('1', ST_SetSRID(ST_MakePoint({LON0}, {LAT0}), 4326))"
        )
        # dois bairros de mesma área que se tocam exatamente no ponto
        cur.execute(f"""INSERT INTO bairro (codigo, nome, geom) VALUES
            ('2', 'B', ST_Multi(ST_MakeEnvelope({LON0}, {LAT0 - 0.01}, {LON0 + 0.01}, {LAT0 + 0.01}, 4326))),
            ('1', 'A', ST_Multi(ST_MakeEnvelope({LON0 - 0.01}, {LAT0 - 0.01}, {LON0}, {LAT0 + 0.01}, 4326)))""")
        # zona grande e zona pequena sobrepostas
        cur.execute(f"""INSERT INTO zoneamento (codigo, nome, geom) VALUES
            ('ZR', 'GRANDE', ST_Multi(ST_MakeEnvelope({LON0 - 0.1}, {LAT0 - 0.1}, {LON0 + 0.1}, {LAT0 + 0.1}, 4326))),
            ('ZC', 'PEQUENA', ST_Multi(ST_MakeEnvelope({LON0 - 0.001}, {LAT0 - 0.001}, {LON0 + 0.001}, {LAT0 + 0.001}, 4326)))""")
    resultados = set()
    territorio.calcular_h3(conn)
    for _ in range(3):
        db.executar_sql(conn, "20_territorio.sql")
        with conn.cursor() as cur:
            cur.execute("SELECT bairro, zona FROM empresa_geo WHERE cnpj = '1'")
            resultados.add(cur.fetchone())
    assert resultados == {("A", "ZC")}
