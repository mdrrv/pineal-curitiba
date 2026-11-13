"""Módulo ME: carga dos arquivos do TSE, geocodificação dos locais, ponte seção -> território e agregados."""

import os
import zipfile
from decimal import Decimal

import pytest

from etl import config, me

LON0, LAT0 = -49.2700, -25.4300

LOCAIS_CAB = (
    "AA_ELEICAO;SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;NR_LOCAL_VOTACAO;NM_LOCAL_VOTACAO;"
    "DS_ENDERECO;NM_BAIRRO;NR_CEP;QT_ELEITOR;NR_SECAO_PRINCIPAL;NR_LATITUDE;NR_LONGITUDE"
)
VOTACAO_CAB = (
    "ANO_ELEICAO;NR_TURNO;SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;CD_CARGO;DS_CARGO;"
    "NR_VOTAVEL;NM_VOTAVEL;QT_VOTOS;QT_APTOS;QT_COMPARECIMENTO;QT_ABSTENCOES"
)
PERFIL_CAB = (
    "ANO_ELEICAO;SG_UF;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;NR_SECAO;DS_GENERO;DS_ESTADO_CIVIL;"
    "DS_FAIXA_ETARIA;DS_GRAU_ESCOLARIDADE;QT_ELEITORES_PERFIL"
)


def zipar(pasta, nome_zip, nome_csv, texto):
    with zipfile.ZipFile(pasta / nome_zip, "w") as z:
        z.writestr(nome_csv, texto.encode("cp1252"))


@pytest.fixture
def ambiente(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_DSN", os.environ["PINEAL_TEST_DSN"])
    monkeypatch.setattr(config, "DADOS_BRUTO", tmp_path / "bruto")
    monkeypatch.setattr(config, "RELATORIOS", tmp_path / "relatorios")
    envelope = "ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
    with conn.cursor() as cur:
        # Centro à esquerda, Batel à direita; um setor dentro do Centro; uma regional cobrindo tudo
        cur.execute(
            f"INSERT INTO bairro (codigo, nome, geom) VALUES ('1', 'Centro', {envelope})",
            (LON0 - 0.002, LAT0 - 0.002, LON0 + 0.001, LAT0 + 0.002),
        )
        cur.execute(
            f"INSERT INTO bairro (codigo, nome, geom) VALUES ('2', 'Batel', {envelope})",
            (LON0 + 0.001, LAT0 - 0.002, LON0 + 0.003, LAT0 + 0.002),
        )
        cur.execute(
            f"INSERT INTO regional (codigo, nome, geom) VALUES ('1', 'Matriz', {envelope})",
            (LON0 - 0.002, LAT0 - 0.002, LON0 + 0.003, LAT0 + 0.002),
        )
        cur.execute(
            f"INSERT INTO setor (cd_setor, geom) VALUES ('410690205000001', {envelope})",
            (LON0 - 0.002, LAT0 - 0.002, LON0 + 0.001, LAT0 + 0.002),
        )
        # endereço do CNEFE para a seção sem coordenada do TSE (nível 'endereco': cep + logradouro + número)
        cur.execute(
            """INSERT INTO cnefe (cod_unico, cep, logradouro, logr_chave, logr_completa, numero, especie, geom)
               VALUES ('xv100', '80020310', 'RUA XV DE NOVEMBRO', norm_logradouro('RUA XV DE NOVEMBRO'),
                       norm_logradouro_completa('RUA XV DE NOVEMBRO'), 100, 6,
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326))""",
            (LON0 + 0.002, LAT0 + 0.0005),
        )
    conn.commit()

    bruto = tmp_path / "bruto"
    lat, lon = f"{LAT0 + 0.0005:.4f}".replace(".", ","), f"{LON0 + 0.0005:.4f}".replace(".", ",")
    pasta = bruto / "tse_locais_votacao"
    pasta.mkdir(parents=True)
    zipar(
        pasta,
        "eleitorado_local_votacao_2024.zip",
        "eleitorado_local_votacao_2024.csv",
        LOCAIS_CAB + "\n"
        # seções 1 e 2 no mesmo local, com coordenada do TSE (decimal com vírgula); a 1 duplicada (fica o menor local)
        f'2024;PR;75353;CURITIBA;1;1;1015;"COLÉGIO ALFA";"RUA A, 10 - CENTRO";CENTRO;80010000;250;;{lat};{lon}\n'
        f'2024;PR;75353;CURITIBA;1;1;1023;"COLÉGIO ALFA ANEXO";"RUA A, 10 - CENTRO";CENTRO;80010000;250;;{lat};{lon}\n'
        f'2024;PR;75353;CURITIBA;1;2;1015;"COLÉGIO ALFA";"RUA A, 10 - CENTRO";CENTRO;80010000;300;;{lat};{lon}\n'
        # seção 3 sem coordenada (-1): geocodificada pelo CNEFE (cai no Batel)
        '2024;PR;75353;CURITIBA;1;3;1031;"ESCOLA BETA";"RUA XV DE NOVEMBRO, 100 - CENTRO";CENTRO;80020310;120;;-1;-1\n'
        # seção 4 agregada à 1, sem coordenada nem endereço: herda o território da principal
        '2024;PR;75353;CURITIBA;1;4;1015;"COLÉGIO ALFA";;CENTRO;80010000;80;1;-1;-1\n'
        # outro município: fica de fora
        f"2024;PR;76910;LONDRINA;5;1;1015;ESCOLA;RUA B, 20;CENTRO;86000000;100;;{lat};{lon}\n",
    )
    pasta = bruto / "tse_votacao_secao"
    pasta.mkdir(parents=True)
    zipar(
        pasta,
        "votacao_secao_2024_PR.zip",
        "votacao_secao_2024_PR.csv",
        VOTACAO_CAB + "\n"
        "2024;1;PR;75353;CURITIBA;1;1;11;Prefeito;10;FULANO;120;250;200;50\n"
        "2024;1;PR;75353;CURITIBA;1;1;11;Prefeito;20;BELTRANO;60;250;200;50\n"
        "2024;1;PR;75353;CURITIBA;1;1;11;Prefeito;96;Nulo;20;250;200;50\n"
        "2024;1;PR;75353;CURITIBA;1;1;13;Vereador;10123;SICRANO;30;250;200;50\n"
        "2024;1;PR;75353;CURITIBA;1;2;11;Prefeito;10;FULANO;80;200;170;30\n"
        "2024;1;PR;75353;CURITIBA;1;2;11;Prefeito;20;BELTRANO;90;200;170;30\n"
        "2024;1;PR;75353;CURITIBA;1;3;11;Prefeito;10;FULANO;10;50;40;10\n"
        # seção 5 não existe nos locais: cai em '(sem território)'
        "2024;1;PR;75353;CURITIBA;1;5;11;Prefeito;20;BELTRANO;5;60;45;15\n"
        "2024;1;PR;76910;LONDRINA;5;1;11;Prefeito;10;OUTRO;999;999;999;0\n",
    )
    # ano sem arquivo de locais: a ponte usa o ano mais próximo (2024); csv solto em utf-8
    (pasta / "votacao_secao_2020_PR.csv").write_text(
        VOTACAO_CAB + "\n2020;1;PR;75353;CURITIBA;1;1;11;Prefeito;55;ANTIGO;100;240;190;50\n",
        encoding="utf-8",
    )
    pasta = bruto / "tse_perfil_eleitorado"
    pasta.mkdir(parents=True)
    zipar(
        pasta,
        "perfil_eleitor_secao_2024_PR.zip",
        "perfil_eleitor_secao_2024_PR.csv",
        PERFIL_CAB + "\n"
        # estados civis diferentes somam na mesma chave
        "2024;PR;75353;CURITIBA;1;1;FEMININO;SOLTEIRO;25 a 34 anos;SUPERIOR COMPLETO;50\n"
        "2024;PR;75353;CURITIBA;1;1;FEMININO;CASADO;25 a 34 anos;SUPERIOR COMPLETO;30\n"
        "2024;PR;75353;CURITIBA;1;1;MASCULINO;SOLTEIRO;25 a 34 anos;SUPERIOR COMPLETO;40\n"
        "2024;PR;76910;LONDRINA;5;1;FEMININO;SOLTEIRO;25 a 34 anos;SUPERIOR COMPLETO;99\n",
    )
    return tmp_path


def test_eleitoral(conn, ambiente):
    me.main([])
    with conn.cursor() as cur:
        cur.execute("""SELECT nr_secao, nr_local, eleitores, secao_principal, geo_origem, geo_precisao,
                              bairro, regional, cd_setor, h3_9 IS NOT NULL
                       FROM eleicao_local_votacao ORDER BY nr_secao""")
        linhas = cur.fetchall()
        assert len(linhas) == 4
        assert linhas[0] == (1, 1015, 250, None, "tse", None, "Centro", "Matriz", "410690205000001", True)
        assert linhas[1][:5] == (2, 1015, 300, None, "tse")
        assert linhas[2] == (3, 1031, 120, None, "geocodificado", "endereco", "Batel", "Matriz", None, True)
        assert linhas[3][:7] == (4, 1015, 80, 1, None, None, None)

        cur.execute("""SELECT ano, nr_secao, ano_local, bairro FROM eleicao_secao_territorio
                       ORDER BY ano, nr_secao""")
        assert cur.fetchall() == [
            (2020, 1, 2024, "Centro"),
            (2024, 1, 2024, "Centro"),
            (2024, 2, 2024, "Centro"),
            (2024, 3, 2024, "Batel"),
            (2024, 4, 2024, "Centro"),  # agregada: herda o território da seção principal
            (2024, 5, None, None),  # sem local de votação
        ]

        # COLLATE "C": a ordem de '(sem território)' em relação às letras varia com o locale do banco
        cur.execute("""SELECT bairro, nr_votavel, nm_votavel, votos, pct_cargo FROM eleicao_bairro_votacao
                       WHERE ano = 2024 AND cd_cargo = 11 ORDER BY bairro COLLATE "C", nr_votavel""")
        D = Decimal
        assert cur.fetchall() == [
            ("(sem território)", 20, "BELTRANO", 5, D("100.00")),
            ("Batel", 10, "FULANO", 10, D("100.00")),
            ("Centro", 10, "FULANO", 200, D("54.05")),
            ("Centro", 20, "BELTRANO", 150, D("40.54")),
            ("Centro", 96, "Nulo", 20, D("5.41")),
        ]
        cur.execute("SELECT bairro, votos FROM eleicao_bairro_votacao WHERE cd_cargo = 13")
        assert cur.fetchall() == [("Centro", 30)]
        cur.execute("SELECT bairro, votos, pct_cargo FROM eleicao_bairro_votacao WHERE ano = 2020")
        assert cur.fetchall() == [("Centro", 100, D("100.00"))]

        cur.execute("""SELECT bairro, secoes, aptos, comparecimento, abstencoes, abstencao_pct
                       FROM eleicao_bairro_participacao WHERE ano = 2024 ORDER BY bairro COLLATE "C" """)
        assert cur.fetchall() == [
            ("(sem território)", 1, 60, 45, 15, D("25.00")),
            ("Batel", 1, 50, 40, 10, D("20.00")),
            ("Centro", 2, 450, 370, 80, D("17.78")),
        ]

        cur.execute("""SELECT genero, faixa_etaria, escolaridade, eleitores FROM eleicao_perfil_secao
                       ORDER BY genero""")
        assert cur.fetchall() == [
            ("FEMININO", "25 a 34 anos", "SUPERIOR COMPLETO", 80),
            ("MASCULINO", "25 a 34 anos", "SUPERIOR COMPLETO", 40),
        ]

    md = (config.RELATORIOS / "eleitoral.md").read_text(encoding="utf-8")
    assert "| 2024 | 1 | 560 |" in md  # participação da cidade soma os bairros
    assert "FULANO" in md and "ANTIGO" in md
