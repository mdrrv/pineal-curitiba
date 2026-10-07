-- Tabelas do M1 (bases da prefeitura). Criadas junto com o schema; cada ETL substitui o conteúdo da sua.

-- data em texto nos formatos que o portal usa (DD/MM/AAAA, AAAA-MM-DD, AAAAMMDD, com ou sem hora)
CREATE OR REPLACE FUNCTION data_br(t TEXT) RETURNS DATE
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    s TEXT := btrim(coalesce(t, ''));
BEGIN
    IF s ~ '^\d{2}/\d{2}/\d{4}' THEN
        RETURN make_date(substr(s, 7, 4)::INT, substr(s, 4, 2)::INT, substr(s, 1, 2)::INT);
    ELSIF s ~ '^\d{4}-\d{2}-\d{2}' THEN
        RETURN make_date(substr(s, 1, 4)::INT, substr(s, 6, 2)::INT, substr(s, 9, 2)::INT);
    ELSIF s ~ '^\d{8}$' AND s <> '00000000' THEN
        RETURN make_date(substr(s, 1, 4)::INT, substr(s, 5, 2)::INT, substr(s, 7, 2)::INT);
    END IF;
    RETURN NULL;
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;

-- CNAE em qualquer formato ("4711-3/01", "4711301") vira os 7 dígitos
CREATE OR REPLACE FUNCTION norm_cnae(t TEXT) RETURNS VARCHAR(7)
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN length(d) = 7 THEN d END
    FROM (SELECT regexp_replace(coalesce(t, ''), '[^0-9]', '', 'g') AS d) x
$$;

-- valor em reais no formato brasileiro ("1.234,56") ou com ponto decimal
CREATE OR REPLACE FUNCTION valor_br(t TEXT) RETURNS NUMERIC
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    s TEXT := regexp_replace(btrim(coalesce(t, '')), '[R$\s]', '', 'g');
BEGIN
    IF s = '' THEN
        RETURN NULL;
    END IF;
    IF s ~ ',\d{1,2}$' THEN
        s := replace(replace(s, '.', ''), ',', '.');
    END IF;
    RETURN s::NUMERIC;
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;

-- Base de Alvarás. Sem nome empresarial (no MEI é o nome da pessoa): ele só existe durante o cruzamento.
CREATE TABLE IF NOT EXISTS alvara (
    numero_alvara       TEXT PRIMARY KEY,
    nome_fantasia       TEXT,
    inicio_atividade    DATE,
    data_emissao        DATE,
    data_expiracao      DATE,
    cep                 VARCHAR(8),
    logradouro          TEXT,
    numero              TEXT,
    complemento         TEXT,
    bairro              TEXT,
    cnae_principal      VARCHAR(7),
    atividade_principal TEXT,
    cnaes_secundarios   VARCHAR(7)[],
    logr_chave          TEXT,
    logr_completa       TEXT,
    numero_int          INTEGER,
    geo_precisao        TEXT,
    geom                geometry(Point, 4326)
);
CREATE INDEX IF NOT EXISTS alvara_geom ON alvara USING gist (geom);
CREATE INDEX IF NOT EXISTS alvara_end ON alvara (cep, logr_chave, numero_int);

-- par alvará x CNPJ escolhido pelo cruzamento (no máximo um CNPJ por alvará e um alvará por CNPJ)
CREATE TABLE IF NOT EXISTS alvara_cnpj (
    numero_alvara   TEXT PRIMARY KEY,
    cnpj            VARCHAR(14) NOT NULL UNIQUE,
    metodo          TEXT NOT NULL,        -- mesmo_endereco | mesma_rua
    pontuacao       NUMERIC(4, 3) NOT NULL,
    nome_similaridade NUMERIC(4, 3),
    cnae_igual      BOOLEAN,
    inicio_igual    BOOLEAN
);

-- Licitações e contratações da prefeitura (itens de processo). Só CNPJ: fornecedor pessoa física (CPF)
-- fica com cnpj NULL e sem nome.
CREATE TABLE IF NOT EXISTS contrato_pmc_item (
    base            TEXT NOT NULL,          -- pmc_licitacoes | pmc_licitacoes_covid
    orgao           TEXT,
    processo        TEXT,
    modalidade      TEXT,
    item            TEXT,
    quantidade      NUMERIC,
    unidade_medida  TEXT,
    cnpj            VARCHAR(14),
    pessoa_fisica   BOOLEAN NOT NULL DEFAULT false,
    contrato        TEXT,
    inicio_vigencia DATE,
    fim_vigencia    DATE,
    valor_unitario  NUMERIC,
    valor_total     NUMERIC
);
CREATE INDEX IF NOT EXISTS contrato_pmc_item_cnpj ON contrato_pmc_item (cnpj);

-- 156 (solicitações do cidadão) agregado por bairro, mês e assunto. Sem texto livre nem solicitante.
CREATE TABLE IF NOT EXISTS siac156_bairro_mes (
    bairro          TEXT,
    regional        TEXT,
    mes             DATE,
    tipo            TEXT,
    assunto         TEXT,
    solicitacoes    INT,
    respondidas     INT,
    dias_resposta_mediana NUMERIC
);

-- SIGMU (manutenção urbana) agregado por bairro, mês e serviço.
CREATE TABLE IF NOT EXISTS sigmu_bairro_mes (
    bairro          TEXT,
    mes             DATE,
    servico         TEXT,
    solicitacoes    INT,
    realizadas      INT,
    dias_realizacao_mediana NUMERIC
);

-- Unidades de atendimento (equipamentos públicos e privados), geocodificadas pelo núcleo.
CREATE TABLE IF NOT EXISTS unidade_atendimento (
    codigo          TEXT PRIMARY KEY,
    nome            TEXT,
    tema            TEXT,
    tipo            TEXT,
    subtipo         TEXT,
    dependencia     TEXT,
    turnos          TEXT,
    logradouro      TEXT,
    numero          TEXT,
    bairro          TEXT,
    regional        TEXT,
    geo_precisao    TEXT,
    geom            geometry(Point, 4326),
    h3_9            TEXT
);
CREATE INDEX IF NOT EXISTS unidade_atendimento_geom ON unidade_atendimento USING gist (geom);

-- Transporte coletivo (GTFS): pontos com linhas e partidas, e agregado por hexágono.
CREATE TABLE IF NOT EXISTS onibus_ponto (
    stop_id     TEXT PRIMARY KEY,
    nome        TEXT,
    linhas      INT,
    partidas    INT,
    h3_9        TEXT,
    geom        geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS onibus_ponto_geom ON onibus_ponto USING gist (geom);

CREATE TABLE IF NOT EXISTS onibus_h3 (
    h3_9        TEXT PRIMARY KEY,
    pontos      INT,
    linhas      INT,
    partidas    INT
);
