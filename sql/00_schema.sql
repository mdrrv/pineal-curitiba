CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS cwb;

-- registro de cada arquivo baixado e de cada carga
CREATE TABLE IF NOT EXISTS cwb.execucao (
    id          BIGSERIAL PRIMARY KEY,
    fonte       TEXT NOT NULL,
    origem      TEXT,
    arquivo     TEXT,
    sha256      TEXT,
    linhas      BIGINT,
    detalhes    JSONB,
    executado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- território ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cwb.setor (
    cd_setor   TEXT PRIMARY KEY,
    atributos  JSONB,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS setor_geom ON cwb.setor USING gist (geom);

CREATE TABLE IF NOT EXISTS cwb.bairro (
    codigo     TEXT,
    nome       TEXT NOT NULL,
    atributos  JSONB,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS bairro_geom ON cwb.bairro USING gist (geom);

CREATE TABLE IF NOT EXISTS cwb.regional (
    codigo     TEXT,
    nome       TEXT NOT NULL,
    atributos  JSONB,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS regional_geom ON cwb.regional USING gist (geom);

CREATE TABLE IF NOT EXISTS cwb.zoneamento (
    codigo     TEXT,
    nome       TEXT NOT NULL,
    atributos  JSONB,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS zoneamento_geom ON cwb.zoneamento USING gist (geom);

-- endereços do CNEFE 2022 ------------------------------------------------

CREATE TABLE IF NOT EXISTS cwb.cnefe (
    cod_unico   TEXT PRIMARY KEY,
    cd_setor    TEXT,
    cep         VARCHAR(8),
    logradouro  TEXT,
    logr_chave  TEXT,
    numero      INTEGER,
    especie     SMALLINT,
    estabelecimento TEXT,
    nv_geo      SMALLINT,
    geom        geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS cnefe_geom ON cwb.cnefe USING gist (geom);
CREATE INDEX IF NOT EXISTS cnefe_cep_logr ON cwb.cnefe (cep, logr_chave, numero);
CREATE INDEX IF NOT EXISTS cnefe_logr ON cwb.cnefe (logr_chave, numero);

-- empresas (recorte do cnpj_consolidado) ---------------------------------

CREATE TABLE IF NOT EXISTS cwb.empresa (
    cnpj                    VARCHAR(14) PRIMARY KEY,
    razao_social            TEXT,
    nome_fantasia           TEXT,
    situacao_cadastral      VARCHAR(2),
    data_situacao_cadastral VARCHAR(8),
    data_inicio_atividade   VARCHAR(8),
    cnae_fiscal_principal   VARCHAR(7),
    natureza_juridica       VARCHAR(4),
    capital_social          NUMERIC(18, 2),
    porte_empresa           VARCHAR(2),
    opcao_pelo_simples      VARCHAR(1),
    opcao_mei               VARCHAR(1),
    identificador_mf        VARCHAR(1),
    logradouro              TEXT,
    numero                  TEXT,
    complemento             TEXT,
    bairro                  TEXT,
    cep                     VARCHAR(8)
);

CREATE TABLE IF NOT EXISTS cwb.empresa_geo (
    cnpj        VARCHAR(14) PRIMARY KEY REFERENCES cwb.empresa (cnpj) ON DELETE CASCADE,
    cep         VARCHAR(8),
    logr_chave  TEXT,
    numero      INTEGER,
    geo_precisao TEXT,
    geom        geometry(Point, 4326),
    cd_setor    TEXT,
    bairro      TEXT,
    regional    TEXT,
    zona        TEXT,
    h3_8        TEXT,
    h3_9        TEXT
);
CREATE INDEX IF NOT EXISTS empresa_geo_geom ON cwb.empresa_geo USING gist (geom);
CREATE INDEX IF NOT EXISTS empresa_geo_h3_9 ON cwb.empresa_geo (h3_9);
