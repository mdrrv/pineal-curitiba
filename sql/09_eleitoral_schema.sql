-- Módulo ME (eleitoral): tabelas de carga do TSE. Criadas junto com o schema; os ETLs etl/fontes/tse_*.py
-- preenchem e sql/90_eleitoral.sql deriva a ponte seção -> território e os agregados por bairro.
-- Escopo e limites em docs/prd-eleitoral-2028.md: só agregados por seção, como o TSE publica.
-- Nenhum dado nominal de eleitor; nenhum vínculo com as tabelas empresa*.

-- local de votação por eleição: o elo entre a seção eleitoral e a chave territorial
CREATE TABLE IF NOT EXISTS eleicao_local_votacao (
    ano             INT NOT NULL,
    nr_zona         INT NOT NULL,
    nr_secao        INT NOT NULL,
    nr_local        INT,
    nome_local      TEXT,
    endereco        TEXT,
    bairro_tse      TEXT,                   -- bairro como o TSE grafa; o oficial (IPPUC) vai em bairro
    cep             TEXT,
    eleitores       INT,                    -- QT_ELEITOR da seção no ano
    secao_principal INT,                    -- NR_SECAO_PRINCIPAL quando a seção vota agregada em outra
    geo_origem      TEXT,                   -- tse (coordenada do arquivo) | geocodificado | nao_localizado
    geo_precisao    TEXT,                   -- nível do núcleo de geocodificação, quando geocodificado
    geom            geometry(Point, 4326),
    cd_setor        TEXT,
    bairro          TEXT,
    regional        TEXT,
    zona_uso        TEXT,                   -- zona de uso do solo (zona aqui já é a zona eleitoral)
    h3_8            TEXT,
    h3_9            TEXT,
    PRIMARY KEY (ano, nr_zona, nr_secao)
);
CREATE INDEX IF NOT EXISTS eleicao_local_votacao_geom ON eleicao_local_votacao USING gist (geom);

-- votação por seção: nominal e de legenda (NR_VOTAVEL com 2 dígitos = partido; 95/96/97 = branco/nulo/anulado)
CREATE TABLE IF NOT EXISTS eleicao_votacao_secao (
    ano             INT NOT NULL,
    turno           INT NOT NULL,
    nr_zona         INT NOT NULL,
    nr_secao        INT NOT NULL,
    cd_cargo        INT NOT NULL,           -- 11 prefeito, 13 vereador; 1/3/5/6/7 nas gerais
    cargo           TEXT,
    nr_votavel      INT NOT NULL,
    nm_votavel      TEXT,
    votos           INT NOT NULL,
    aptos           INT,                    -- da seção (repetido no arquivo por votável; fica o máximo)
    comparecimento  INT,
    abstencoes      INT,
    PRIMARY KEY (ano, turno, nr_zona, nr_secao, cd_cargo, nr_votavel)
);

-- perfil do eleitorado por seção, agregado em gênero x faixa etária x escolaridade (estado civil fica de fora)
CREATE TABLE IF NOT EXISTS eleicao_perfil_secao (
    ano             INT NOT NULL,
    nr_zona         INT NOT NULL,
    nr_secao        INT NOT NULL,
    genero          TEXT NOT NULL,
    faixa_etaria    TEXT NOT NULL,
    escolaridade    TEXT NOT NULL,
    eleitores       INT NOT NULL,
    PRIMARY KEY (ano, nr_zona, nr_secao, genero, faixa_etaria, escolaridade)
);

-- derivadas (sql/90_eleitoral.sql) -----------------------------------------------------------------

-- ponte seção -> território: o local do ano mais próximo com geometria responde pela seção daquele ano
CREATE TABLE IF NOT EXISTS eleicao_secao_territorio (
    ano         INT NOT NULL,
    nr_zona     INT NOT NULL,
    nr_secao    INT NOT NULL,
    ano_local   INT,                        -- ano do local de votação usado (nem toda eleição tem arquivo)
    cd_setor    TEXT,
    bairro      TEXT,
    regional    TEXT,
    h3_8        TEXT,
    h3_9        TEXT,
    PRIMARY KEY (ano, nr_zona, nr_secao)
);

CREATE TABLE IF NOT EXISTS eleicao_bairro_votacao (
    bairro      TEXT NOT NULL,              -- '(sem território)' para seções sem local localizado
    ano         INT NOT NULL,
    turno       INT NOT NULL,
    cd_cargo    INT NOT NULL,
    cargo       TEXT,
    nr_votavel  INT NOT NULL,
    nm_votavel  TEXT,
    votos       BIGINT NOT NULL,
    pct_cargo   NUMERIC,                    -- % dos votos do cargo no bairro naquele ano/turno
    PRIMARY KEY (ano, turno, cd_cargo, nr_votavel, bairro)
);

CREATE TABLE IF NOT EXISTS eleicao_bairro_participacao (
    bairro          TEXT NOT NULL,
    ano             INT NOT NULL,
    turno           INT NOT NULL,
    secoes          INT,
    aptos           BIGINT,
    comparecimento  BIGINT,
    abstencoes      BIGINT,
    abstencao_pct   NUMERIC,
    PRIMARY KEY (ano, turno, bairro)
);
