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
