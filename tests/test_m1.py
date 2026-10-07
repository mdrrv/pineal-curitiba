"""M1: bases da prefeitura com arquivos sintéticos no layout real do portal."""

import os

import pytest

from etl import config, db
from etl.fontes import pmc_alvaras

LON0, LAT0 = -49.2700, -25.4300

CAB_ALVARAS = [
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


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    return tmp_path


def empresa(cur, cnpj, razao, fantasia, cnae, inicio, numero, cep, situacao="02", pf=False, tipo="comercial"):
    cur.execute(
        """INSERT INTO empresa (cnpj, razao_social, nome_fantasia, pessoa_fisica, cnae_fiscal_principal,
                                data_inicio_atividade, situacao_cadastral, logradouro, numero, cep)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'R DR FAIVRE', %s, %s)""",
        (cnpj, razao, fantasia, pf, cnae, inicio, situacao, numero, cep),
    )
    cur.execute("INSERT INTO empresa_perfil (cnpj, tipo_ponto, domiciliacao) VALUES (%s, %s, false)", (cnpj, tipo))


def montar(conn):
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS empresa_perfil (cnpj VARCHAR(14) PRIMARY KEY, tipo_ponto TEXT, domiciliacao BOOLEAN)"
        )
        empresa(cur, "11111111000101", "PADARIA PAO DOURADO LTDA", None, "1091102", "2015-01-01", "10", "80000001")
        empresa(cur, "22222222000101", None, "BELEZA DA MARIA", "9602502", "2018-01-01", "20", "80000002", pf=True)
        empresa(
            cur, "33333333000101", "LOJA ANTIGA LTDA", None, "4781400", "2010-01-01", "30", "80000003", situacao="08"
        )
        empresa(cur, "44444444000101", "OFICINA DO ZE LTDA", None, "4520001", "2012-01-01", "40", "80000004")
        empresa(cur, "55555555000101", "MERCADO BOM LTDA", None, "4711302", "2016-03-01", "50", "80000005")
        for i, (num, cep) in enumerate(
            [(10, "80000001"), (20, "80000002"), (30, "80000003"), (40, "80000004"), (50, "80000005"), (99, "80000009")]
        ):
            cur.execute(
                """INSERT INTO cnefe (cod_unico, cep, logradouro, logr_chave, logr_completa, numero, especie, geom)
                   VALUES (%s, %s, 'RUA DOUTOR FAIVRE', 'FAIVRE', 'DOUTOR FAIVRE', %s, 6,
                           ST_SetSRID(ST_MakePoint(%s, %s), 4326))""",
                (f"c{i}", cep, num, LON0 + i * 0.0002, LAT0),
            )
    conn.commit()


def csv_alvaras(pasta):
    def linha(nome, inicio, numero_alvara, fantasia, emissao, expiracao, numero, cep, cnae):
        return [
            nome,
            inicio,
            numero_alvara,
            fantasia,
            emissao,
            expiracao,
            "RUA DOUTOR FAIVRE",
            numero,
            "",
            "",
            "SALA 2",
            "CENTRO",
            cep,
            cnae,
            "ATIVIDADE",
            "4729-6/99",
            "OUTRA",
        ]

    linhas = [
        linha(
            "PADARIA PAO DOURADO LTDA",
            "01/01/2015",
            "A-1",
            "PAO DOURADO",
            "10/01/2015",
            "31/12/2030",
            "10",
            "80000-001",
            "1091-1/02",
        ),
        linha("OUTRA COISA ME", "01/06/2021", "A-2", "", "01/06/2021", "31/12/2030", "10", "80000-001", "5611-2/01"),
        linha(
            "MARIA DA SILVA 12345678901",
            "05/05/2020",
            "B-1",
            "BELEZA DA MARIA",
            "05/05/2020",
            "01/01/2020",
            "20",
            "80000-002",
            "9602-5/01",
        ),
        linha("LOJA ANTIGA LTDA", "01/01/2010", "C-1", "", "01/01/2010", "31/12/2030", "30", "80000-003", "4781-4/00"),
        linha("MERCADO BOM LTDA", "01/03/2016", "E-1", "", "01/03/2016", "31/12/2030", "50", "80000-005", "5611-2/01"),
        linha("EMPRESA FORA LTDA", "01/01/2019", "X-1", "", "01/01/2019", "31/12/2030", "99", "80000-009", "4711-3/02"),
    ]
    caminho = pasta / "2026-10-01_Alvaras_-_Base_de_Dados.csv"
    with open(caminho, "w", encoding="cp1252", newline="") as f:
        f.write(";".join(CAB_ALVARAS) + "\r\n")
        for li in linhas:
            f.write(";".join(li) + "\r\n")
    return caminho


def test_alvaras(conn, ambiente):
    montar(conn)
    pmc_alvaras.main(["--arquivo", str(csv_alvaras(ambiente))])
    with conn.cursor() as cur:
        cur.execute("SELECT numero_alvara, cnpj, metodo FROM alvara_cnpj ORDER BY 1")
        assert cur.fetchall() == [
            ("A-1", "11111111000101", "mesmo_endereco"),
            ("B-1", "22222222000101", "mesmo_endereco"),
            ("C-1", "33333333000101", "mesmo_endereco"),
            ("E-1", "55555555000101", "mesmo_endereco"),
        ]
        cur.execute("""SELECT cnpj, tem_alvara, ativa_sem_alvara, alvara_de_cnpj_encerrado, alvara_vencido,
                              atividade_diverge, chegada_ao_endereco FROM empresa_alvara ORDER BY cnpj""")
        s = {r[0]: r[1:] for r in cur.fetchall()}
        import datetime

        assert s["11111111000101"] == (True, False, False, False, False, None)
        assert s["22222222000101"] == (True, False, False, True, False, datetime.date(2020, 5, 5))
        assert s["33333333000101"] == (True, False, True, False, False, None)
        assert s["44444444000101"][:2] == (False, True)
        assert s["55555555000101"][4] is True  # alvará de restaurante num CNPJ de supermercado
        cur.execute("SELECT numero_alvara FROM alvara_sem_cnpj ORDER BY 1")
        assert [r[0] for r in cur.fetchall()] == ["A-2", "X-1"]
        cur.execute("""SELECT data_expiracao, cnae_principal, cnaes_secundarios, cep, complemento, geo_precisao
                       FROM alvara WHERE numero_alvara = 'B-1'""")
        exp, cnae, sec, cep, compl, geo = cur.fetchone()
        assert (str(exp), cnae, sec, cep, compl, geo) == (
            "2020-01-01",
            "9602501",
            ["4729699"],
            "80000002",
            "SALA 2",
            "endereco",
        )
        # LGPD: o nome empresarial (nome e CPF da pessoa) não fica em tabela nenhuma
        cur.execute(
            """SELECT count(*) FROM alvara a WHERE a::text LIKE '%%12345678901%%' OR a::text LIKE '%%MARIA DA SILVA%%'"""
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT count(*) FROM information_schema.columns WHERE column_name = 'nome_empresarial' AND table_schema = current_schema()"
        )
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT fonte, status FROM execucao WHERE tipo = 'etapa'")
        assert cur.fetchall() == [("alvaras", "ok")]
    assert "Casados com CNPJ: 4" in (ambiente / "relatorios" / "alvaras.md").read_text()


def test_funcoes_m1(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT data_br('05/05/2020'), data_br('2020-05-05 10:00'), data_br('20200505'), data_br('31/02/2020'),
                              norm_cnae('4711-3/01'), norm_cnae('47113'), valor_br('1.234,56'), valor_br('1234.5'),
                              valor_br('R$ 10,00'), valor_br('abc')""")
        import datetime
        import decimal

        d = datetime.date(2020, 5, 5)
        assert cur.fetchone() == (
            d,
            d,
            d,
            None,
            "4711301",
            None,
            decimal.Decimal("1234.56"),
            decimal.Decimal("1234.5"),
            decimal.Decimal("10.00"),
            None,
        )


def escrever(caminho, cabecalho, linhas, enc="cp1252"):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding=enc, newline="") as f:
        f.write(";".join(cabecalho) + "\r\n")
        for li in linhas:
            f.write(";".join(li) + "\r\n")
    return caminho


CAB_LIC = [
    "Órgão",
    "Número do Processo",
    "Modalidade",
    "Item",
    "Quantidade",
    "Unidade de Medida",
    "Contratato/Fornecedor",
    "CNPJ/CPF",
    "Número do Contrato",
    "Inicio da Vigência do Contrato",
    "Fim da Vigência do Contrato",
    "Valor Unitário",
    "Valor Total/Global",
]


def arquivos_m1(bruto):
    escrever(
        bruto / "pmc_licitacoes" / "2026-10-01_Licitacoes_Contratacoes_Itens_Processo_-_Base_de_Dados.csv",
        CAB_LIC,
        [
            [
                "SMS",
                "P1",
                "Pregão",
                "Luvas",
                "1.000",
                "CX",
                "PADARIA PAO DOURADO LTDA",
                "11.111.111/0001-01",
                "C1",
                "01/01/2025",
                "31/12/2030",
                "1,50",
                "1.500,00",
            ],
            [
                "SMS",
                "P1",
                "Pregão",
                "Máscaras",
                "10",
                "CX",
                "PADARIA PAO DOURADO LTDA",
                "11.111.111/0001-01",
                "C1",
                "01/01/2025",
                "31/12/2030",
                "10,00",
                "100,00",
            ],
            [
                "SME",
                "P2",
                "Dispensa",
                "Palestra",
                "1",
                "UN",
                "JOSE DA SILVA",
                "123.456.789-01",
                "C2",
                "01/01/2020",
                "31/12/2020",
                "500,00",
                "500,00",
            ],
            [
                "SMOP",
                "P3",
                "Concorrência",
                "Obra",
                "1",
                "UN",
                "CONSTRUTORA DE FORA SA",
                "99.999.999/0001-99",
                "C3",
                "01/01/2019",
                "31/12/2019",
                "9.000,00",
                "9.000,00",
            ],
        ],
    )
    escrever(
        bruto / "pmc_licitacoes_covid" / "2026-10-01_Licitacoes_Contratacoes_Covid_Itens_Processo_-_Base_de_Dados.csv",
        CAB_LIC,
        [
            [
                "SMS",
                "PC1",
                "Dispensa",
                "Álcool",
                "5",
                "L",
                "PADARIA PAO DOURADO LTDA",
                "11111111000101",
                "CC1",
                "01/04/2020",
                "31/12/2020",
                "4,00",
                "20,00",
            ]
        ],
    )
    escrever(
        bruto / "pmc_siac156" / "2026-10-05_156_-_Base_de_Dados.csv",
        [
            "Tipo",
            "Orgao",
            "DataCriacao",
            "Assunto",
            "Subdivisao",
            "Situacao",
            "Logradouro",
            "Bairro",
            "Regional",
            "DataResposta",
            "Origem",
            "Column1",
        ],
        [
            [
                "SOLICITACAO",
                "SMMA",
                "01/09/2026 10:00:00",
                "PODA DE ARVORE",
                "X",
                "RESPONDIDA",
                "R A",
                "Centro",
                "MATRIZ",
                "05/09/2026 10:00:00",
                "TELEFONE",
                "",
            ],
            [
                "SOLICITACAO",
                "SMMA",
                "10/09/2026 10:00:00",
                "PODA DE ARVORE",
                "X",
                "ABERTA",
                "R B",
                "CENTRO",
                "MATRIZ",
                "",
                "APP",
                "",
            ],
            [
                "RECLAMACAO",
                "SMOP",
                "02/08/2026 08:00:00",
                "BURACO",
                "Y",
                "RESPONDIDA",
                "R C",
                "BATEL",
                "MATRIZ",
                "12/08/2026 08:00:00",
                "APP",
                "",
            ],
        ],
    )
    escrever(
        bruto / "pmc_sigmu" / "2026-10-06_Sigmu_-_SERVICO_SOLICITADO_-_Base_de_Dados.csv",
        [
            "SSO_IDF",
            "SGR_IDF",
            "SSO_DATA_SOLICITACAO",
            "SET_IDF",
            "SSO_OBSERVACAO",
            "SSO_NOME_BAIRRO",
            "SSO_DATA_REALIZACAO",
        ],
        [
            ["1", "1", "2026-09-01 08:00:00", "10", "texto livre do cidadão", "CENTRO", "2026-09-03 08:00:00"],
            ["2", "1", "2026-09-15 08:00:00", "10", "", "CENTRO", ""],
            ["3", "1", "2026-08-01 08:00:00", "20", "", "BATEL", "2026-08-02 08:00:00"],
        ],
    )
    escrever(
        bruto / "pmc_sigmu" / "2026-10-06_Sigmu_-_SERVICO_TAB_-_Base_de_Dados.csv",
        ["SET_IDF", "SET_DESCRICAO", "SGR_IDF"],
        [["10", "TAPA-BURACO", "1"], ["20", "LIMPEZA DE BOCA DE LOBO", "1"]],
    )
    escrever(
        bruto / "pmc_unidades" / "2026-09-30_Unidades12_Atendimento_Ativas_Curitiba_-_Base_de_Dados.csv",
        [
            "CD_EQUI",
            "NM_EQUI",
            "DS_TEMA",
            "DS_TP_EQUIPAMENTO",
            "DS_SUBTIPO_EQUIPAMENTO",
            "DS_DEP_ADMINISTRATIVA",
            "FUNCIONAMENTO_MANHA_EQUI",
            "FUNCIONAMENTO_TARDE_EQUI",
            "FUNCIONAMENTO_NOITE_EQUI",
            "FUNCIONAMENTO_24HRS_EQUI",
            "NM_RUA",
            "NUMERO_EQUI",
            "NM_BAIRRO",
            "NM_REGIONAL",
        ],
        [
            [
                "1",
                "UBS FAIVRE",
                "SAÚDE",
                "UNIDADE DE SAÚDE",
                "UBS",
                "MUNICIPAL",
                "S",
                "S",
                "N",
                "N",
                "RUA DOUTOR FAIVRE",
                "10",
                "CENTRO",
                "MATRIZ",
            ],
            [
                "2",
                "ESCOLA SEM ENDEREÇO",
                "EDUCAÇÃO",
                "ESCOLA",
                "EF",
                "MUNICIPAL",
                "S",
                "N",
                "N",
                "N",
                "RUA INEXISTENTE",
                "1",
                "BAIRRO NENHUM",
                "MATRIZ",
            ],
        ],
    )
    import zipfile

    (bruto / "urbs_gtfs").mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bruto / "urbs_gtfs" / "gtfs.zip", "w") as z:
        z.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon,location_type\n"
            f"S1,Ponto 1,{LAT0},{LON0},0\nS2,Ponto 2,{LAT0},{LON0 + 0.00005},\nE1,Estação,{LAT0},{LON0},1\n",
        )
        z.writestr("trips.txt", "route_id,service_id,trip_id\nR1,U,T1\nR1,U,T2\nR2,U,T3\n")
        z.writestr(
            "stop_times.txt",
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T1,08:00:00,08:00:00,S1,1\nT2,09:00:00,09:00:00,S1,1\nT3,10:00:00,10:00:00,S1,1\nT3,10:05:00,10:05:00,S2,2\n",
        )


def test_licitacoes(conn, ambiente):
    from etl.fontes import pmc_licitacoes

    montar(conn)
    arquivos_m1(ambiente / "bruto")
    pmc_licitacoes.main([])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cnpj, contratos, itens, valor_total, contratos_vigentes, na_cidade FROM empresa_contratos_pmc ORDER BY 1"
        )
        import decimal

        assert cur.fetchall() == [
            ("11111111000101", 2, 3, decimal.Decimal("1620.00"), 1, True),
            ("99999999000199", 1, 1, decimal.Decimal("9000.00"), 0, False),
        ]
        cur.execute("SELECT count(*) FROM contrato_pmc_item WHERE pessoa_fisica AND cnpj IS NULL")
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT count(*) FROM contrato_pmc_item c WHERE c::text LIKE '%%JOSE DA SILVA%%' OR c::text LIKE '%%12345678901%%'"
        )
        assert cur.fetchone()[0] == 0


def test_zeladoria(conn, ambiente):
    from etl.fontes import pmc_zeladoria

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO bairro (codigo, nome, geom) VALUES ('1', 'Centro', ST_Multi(ST_MakeEnvelope(0, 0, 1, 1, 4326)))"
        )
    conn.commit()
    arquivos_m1(ambiente / "bruto")
    pmc_zeladoria.main([])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bairro, mes, assunto, solicitacoes, respondidas, dias_resposta_mediana FROM siac156_bairro_mes ORDER BY 2, 1"
        )
        import datetime

        r = cur.fetchall()
        assert r[0][:5] == ("BATEL", datetime.date(2026, 8, 1), "BURACO", 1, 1) and r[0][5] == 10
        assert r[1][:5] == ("Centro", datetime.date(2026, 9, 1), "PODA DE ARVORE", 2, 1) and r[1][5] == 4
        cur.execute("SELECT bairro, servico, solicitacoes, realizadas FROM sigmu_bairro_mes ORDER BY 1")
        assert cur.fetchall() == [("BATEL", "LIMPEZA DE BOCA DE LOBO", 1, 1), ("Centro", "TAPA-BURACO", 2, 1)]
        cur.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() AND column_name ILIKE '%%observacao%%'"
        )
        assert cur.fetchone()[0] == 0


def test_unidades_e_transporte(conn, ambiente):
    from etl.fontes import pmc_unidades, urbs_gtfs

    montar(conn)
    arquivos_m1(ambiente / "bruto")
    pmc_unidades.main([])
    urbs_gtfs.main([])
    with conn.cursor() as cur:
        cur.execute("SELECT codigo, turnos, geo_precisao, h3_9 IS NOT NULL FROM unidade_atendimento ORDER BY 1")
        assert cur.fetchall() == [("1", "manha,tarde", "endereco_sem_cep", True), ("2", "manha", "nao_localizado", False)]
        cur.execute("SELECT stop_id, linhas, partidas FROM onibus_ponto ORDER BY 1")
        assert cur.fetchall() == [("S1", 2, 3), ("S2", 1, 1)]
        cur.execute("SELECT sum(pontos), sum(partidas) FROM onibus_h3")
        assert cur.fetchone() == (2, 4)


def test_m1_orquestrador(conn, ambiente):
    from etl import m1

    montar(conn)
    arquivos_m1(ambiente / "bruto")
    (ambiente / "bruto" / "pmc_alvaras").mkdir(parents=True)
    csv_alvaras(ambiente / "bruto" / "pmc_alvaras")
    m1.main([])
    assert db.contar(conn, "SELECT count(*) FROM alvara") == 6
    with conn.cursor() as cur:
        cur.execute("SELECT fonte, status FROM execucao WHERE tipo = 'etapa' ORDER BY id")
        assert cur.fetchall() == [(e, "ok") for e in ["alvaras", "licitacoes", "zeladoria", "unidades", "transporte"]]
