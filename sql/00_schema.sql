-- Tudo aqui é criado no schema do Pineal (PINEAL_SCHEMA, padrão cwb): etl/db.py cria o schema
-- e põe ele na frente do search_path antes de rodar este arquivo.

CREATE EXTENSION IF NOT EXISTS postgis SCHEMA public;
CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA public;

-- registro de cada etapa e de cada carga
CREATE TABLE IF NOT EXISTS execucao (
    id           BIGSERIAL PRIMARY KEY,
    run_id       TEXT,
    tipo         TEXT NOT NULL DEFAULT 'carga',   -- carga | etapa
    fonte        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'ok',      -- ok | erro
    origem       TEXT,
    arquivo      TEXT,
    sha256       TEXT,
    linhas       BIGINT,
    duracao_s    NUMERIC(12, 1),
    erro         TEXT,
    detalhes     JSONB,
    executado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE execucao ADD COLUMN IF NOT EXISTS run_id TEXT;
ALTER TABLE execucao ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'carga';
ALTER TABLE execucao ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ok';
ALTER TABLE execucao ADD COLUMN IF NOT EXISTS duracao_s NUMERIC(12, 1);
ALTER TABLE execucao ADD COLUMN IF NOT EXISTS erro TEXT;
CREATE INDEX IF NOT EXISTS execucao_run ON execucao (run_id);

-- território ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS setor (
    cd_setor   TEXT PRIMARY KEY,
    atributos  JSONB,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS setor_geom ON setor USING gist (geom);

CREATE TABLE IF NOT EXISTS bairro (
    codigo     TEXT,
    nome       TEXT NOT NULL,
    atributos  JSONB,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS bairro_geom ON bairro USING gist (geom);

CREATE TABLE IF NOT EXISTS regional (
    codigo     TEXT,
    nome       TEXT NOT NULL,
    atributos  JSONB,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS regional_geom ON regional USING gist (geom);

CREATE TABLE IF NOT EXISTS zoneamento (
    codigo     TEXT,
    nome       TEXT NOT NULL,
    atributos  JSONB,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS zoneamento_geom ON zoneamento USING gist (geom);

-- endereços do CNEFE 2022 ------------------------------------------------

CREATE TABLE IF NOT EXISTS cnefe (
    cod_unico   TEXT PRIMARY KEY,
    cd_setor    TEXT,
    cep         VARCHAR(8),
    logradouro  TEXT,
    logr_chave  TEXT,
    logr_completa TEXT,
    numero      INTEGER,
    especie     SMALLINT,
    estabelecimento TEXT,
    nome_chave  TEXT,
    nv_geo      SMALLINT,
    geom        geometry(Point, 4326) NOT NULL
);
ALTER TABLE cnefe ADD COLUMN IF NOT EXISTS logr_completa TEXT;
ALTER TABLE cnefe ADD COLUMN IF NOT EXISTS nome_chave TEXT;
CREATE INDEX IF NOT EXISTS cnefe_geom ON cnefe USING gist (geom);
CREATE INDEX IF NOT EXISTS cnefe_cep_logr ON cnefe (cep, logr_chave, numero);
CREATE INDEX IF NOT EXISTS cnefe_logr ON cnefe (logr_chave, numero);
CREATE INDEX IF NOT EXISTS cnefe_logr_completa ON cnefe (logr_completa, numero);

-- empresas (recorte do cnpj_consolidado) ---------------------------------
-- LGPD: razao_social fica nula quando a empresa é de pessoa física (MEI ou empresário individual,
-- natureza 2135); o CPF que a Receita põe no fim da razão social é guardado só mascarado.

-- migração da versão com datas em texto: a tabela é recarregada inteira a cada rodada, então recria
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'empresa'
                 AND column_name = 'data_inicio_atividade' AND data_type <> 'date') THEN
        DROP TABLE IF EXISTS empresa_geo;
        DROP TABLE empresa CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS empresa (
    cnpj                    VARCHAR(14) PRIMARY KEY,
    cnpj_basico             VARCHAR(8),
    razao_social            TEXT,
    nome_fantasia           TEXT,
    pessoa_fisica           BOOLEAN NOT NULL DEFAULT false,
    cpf_mascarado           VARCHAR(14),
    situacao_cadastral      VARCHAR(2),
    data_situacao_cadastral DATE,
    data_inicio_atividade   DATE,
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
CREATE INDEX IF NOT EXISTS empresa_cnae ON empresa (cnae_fiscal_principal);
CREATE INDEX IF NOT EXISTS empresa_situacao ON empresa (situacao_cadastral);
CREATE INDEX IF NOT EXISTS empresa_basico ON empresa (cnpj_basico);

CREATE TABLE IF NOT EXISTS empresa_geo (
    cnpj        VARCHAR(14) PRIMARY KEY REFERENCES empresa (cnpj) ON DELETE CASCADE,
    cep         VARCHAR(8),
    logr_chave  TEXT,
    logr_completa TEXT,
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
ALTER TABLE empresa_geo ADD COLUMN IF NOT EXISTS logr_completa TEXT;
CREATE INDEX IF NOT EXISTS empresa_geo_geom ON empresa_geo USING gist (geom);
CREATE INDEX IF NOT EXISTS empresa_geo_bairro ON empresa_geo (bairro);
CREATE INDEX IF NOT EXISTS empresa_geo_setor ON empresa_geo (cd_setor);
CREATE INDEX IF NOT EXISTS empresa_geo_h3_8 ON empresa_geo (h3_8);
CREATE INDEX IF NOT EXISTS empresa_geo_h3_9 ON empresa_geo (h3_9);

-- foto mensal do recorte, para aberturas, fechamentos e mudanças entre competências
CREATE TABLE IF NOT EXISTS empresa_historico (
    competencia             DATE NOT NULL,
    cnpj                    VARCHAR(14) NOT NULL,
    situacao_cadastral      VARCHAR(2),
    data_situacao_cadastral DATE,
    data_inicio_atividade   DATE,
    cnae_fiscal_principal   VARCHAR(7),
    porte_empresa           VARCHAR(2),
    capital_social          NUMERIC(18, 2),
    opcao_mei               VARCHAR(1),
    endereco_chave          TEXT,
    PRIMARY KEY (competencia, cnpj)
);
CREATE INDEX IF NOT EXISTS empresa_historico_cnpj ON empresa_historico (cnpj, competencia);
