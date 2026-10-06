from etl import db, geocodificar, territorio

LON0, LAT0 = -49.2700, -25.4300
PASSO = 0.00005  # ~5 m entre números vizinhos


def cnefe(cur, cod, logradouro, numero, cep, lon, lat):
    cur.execute("""
        INSERT INTO cwb.cnefe (cod_unico, cep, logradouro, logr_chave, numero, geom)
        VALUES (%s, %s, %s, cwb.norm_logradouro(%s), %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
    """, (cod, cep, logradouro, logradouro, numero, lon, lat))


def empresa(cur, cnpj, logradouro, numero, cep):
    cur.execute("INSERT INTO cwb.empresa (cnpj, situacao_cadastral, logradouro, numero, cep) VALUES (%s,'02',%s,%s,%s)",
                (cnpj, logradouro, numero, cep))


def montar(conn):
    with conn.cursor() as cur:
        i = 0
        for n in range(100, 200):  # pares de um lado, ímpares do outro
            i += 1
            lat = LAT0 + (0.0001 if n % 2 else 0)
            cnefe(cur, f"a{i}", "RUA DOUTOR FAIVRE", n, "80060140", LON0 + (n - 100) * PASSO, lat)
        for n in range(1, 60):
            i += 1
            cnefe(cur, f"b{i}", "RUA MARECHAL FLORIANO PEIXOTO", n, "80010130", LON0 + 0.01 + n * PASSO, LAT0)
        for n in (0, 0, 0):
            i += 1
            cnefe(cur, f"c{i}", "TRAVESSA UNICA", None, "80000500", LON0 + 0.02 + i * PASSO, LAT0)

        empresa(cur, "00000000000001", "R DR FAIVRE", "150", "80060140")       # endereco
        empresa(cur, "00000000000002", "RUA FAIVRE", "150", "99999999")         # endereco_sem_cep
        empresa(cur, "00000000000003", "R DR FAIVRE", "207", "80060140")        # numero_proximo (199)
        empresa(cur, "00000000000004", "R DR FAIVRE", "S/N", "80060140")        # logradouro
        empresa(cur, "00000000000005", "R MAL FLORIANO PEIXOT", "S/N", "80010130")  # logradouro_aproximado
        empresa(cur, "00000000000006", "TV UNICA", "", None)                   # logradouro_sem_cep
        empresa(cur, "00000000000007", "RUA INEXISTENTE", "10", "80060140")     # cep
        empresa(cur, "00000000000008", "RUA INEXISTENTE", "10", None)           # nao_localizado
        empresa(cur, "00000000000009", "R DR FAIVRE", "900", "80060140")        # longe demais: logradouro


def niveis(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT cnpj, geo_precisao, ST_X(geom), ST_Y(geom) FROM cwb.empresa_geo ORDER BY cnpj")
        return {c: (p, x, y) for c, p, x, y in cur.fetchall()}


def test_niveis(conn):
    montar(conn)
    db.executar_sql(conn, "10_geocodificar.sql")
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


def test_resumo_e_relatorio(conn):
    montar(conn)
    db.executar_sql(conn, "10_geocodificar.sql")
    linhas = geocodificar.resumo(conn)
    assert [p for p, _, _ in linhas] == geocodificar.ORDEM
    assert sum(t for _, t, _ in linhas) == 9
    md = geocodificar.relatorio(linhas)
    assert "| nao_localizado | 1 |" in md


def test_territorio(conn):
    montar(conn)
    db.executar_sql(conn, "10_geocodificar.sql")
    caixa = f"ST_Multi(ST_MakeEnvelope({LON0 - 0.001}, {LAT0 - 0.001}, {LON0 + 0.006}, {LAT0 + 0.001}, 4326))"
    with conn.cursor() as cur:
        cur.execute(f"INSERT INTO cwb.setor (cd_setor, geom) VALUES ('410690205000001', {caixa})")
        cur.execute(f"INSERT INTO cwb.bairro (codigo, nome, geom) VALUES ('1', 'CENTRO', {caixa})")
    db.executar_sql(conn, "20_territorio.sql")
    assert territorio.gravar_h3(conn) == 8
    with conn.cursor() as cur:
        cur.execute("SELECT cd_setor, bairro, regional, h3_8, h3_9 FROM cwb.empresa_geo WHERE cnpj = '00000000000001'")
        setor, bairro, regional, h3_8, h3_9 = cur.fetchone()
        cur.execute("SELECT count(*) FROM cwb.empresa_geo WHERE bairro IS NULL AND geom IS NOT NULL")
        fora = cur.fetchone()[0]
    assert (setor, bairro, regional) == ("410690205000001", "CENTRO", None)
    assert h3_8.startswith("88") and h3_9.startswith("89")
    assert fora == 2  # Floriano Peixoto e Travessa Única ficam fora da caixa
    assert "| bairro |" in territorio.resumo(conn)
