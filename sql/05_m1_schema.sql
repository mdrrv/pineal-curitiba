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

-- número no formato brasileiro ("1.234,56", "4,599", "1.234") ou com ponto decimal ("1234.5")
CREATE OR REPLACE FUNCTION valor_br(t TEXT) RETURNS NUMERIC
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    s TEXT := regexp_replace(btrim(coalesce(t, '')), '[R$\s]', '', 'g');
BEGIN
    IF s = '' THEN
        RETURN NULL;
    END IF;
    IF s ~ ',\d+$' THEN                       -- vírgula decimal: pontos são milhar
        s := replace(replace(s, '.', ''), ',', '.');
    ELSIF s ~ '^-?\d{1,3}(\.\d{3})+$' THEN   -- só pontos em grupos de 3: milhar ("1.234", "12.345.678")
        s := replace(s, '.', '');
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

-- Ocorrências de segurança e defesa civil. Sem dado de pessoa (vítima, autor, solicitante): só o fato,
-- quando e onde. A coluna fonte deixa somar CAPE, Bombeiros e Defesa Civil quando chegarem (LAI).
CREATE TABLE IF NOT EXISTS seguranca_ocorrencia (
    fonte           TEXT NOT NULL,
    codigo          TEXT NOT NULL,
    data            DATE,
    hora            SMALLINT,
    bairro          TEXT,
    regional        TEXT,
    logradouro      TEXT,
    naturezas       TEXT[],
    categorias      TEXT[],
    defesa_civil    BOOLEAN,
    equipamento_urbano TEXT,
    flagrante       BOOLEAN,
    geo_precisao    TEXT,
    geom            geometry(Point, 4326),
    h3_9            TEXT,
    PRIMARY KEY (fonte, codigo)
);
CREATE INDEX IF NOT EXISTS seguranca_ocorrencia_data ON seguranca_ocorrencia (data);
CREATE INDEX IF NOT EXISTS seguranca_ocorrencia_geom ON seguranca_ocorrencia USING gist (geom);

-- natureza (texto livre do sistema de origem) -> categoria do índice. Primeiro padrão que casar, por ordem.
-- Editável: a carga só semeia a tabela vazia; o que for alterado ou apagado fica como está.
CREATE TABLE IF NOT EXISTS natureza_categoria (
    padrao      TEXT PRIMARY KEY,   -- regex sobre norm_txt(natureza)
    categoria   TEXT NOT NULL,      -- patrimonial | violento | fisico | ordem_publica | transito | outros
    ordem       INT NOT NULL
);
INSERT INTO natureza_categoria (padrao, categoria, ordem)
SELECT * FROM (VALUES
    ('\mALARMES?\M', 'outros', 5),  -- "disparo de alarme" é frequente e não é violência
    ('\m(ROUBO|ASSALTO|LATROCINIO)\M', 'violento', 10),
    ('\m(HOMICIDIO|LESAO CORPORAL|AGRESSAO|VIAS DE FATO|ESTUPRO|SEQUESTRO|AMEACA|VIOLENCIA|DISPARO DE ARMA|ARMAS? DE FOGO|BRIGA|RIXA)\M', 'violento', 20),
    ('\m(FURTO|ARROMBAMENTO|DANO|DEPREDACAO|VANDALISMO|PICHACAO|INVASAO|RECEPTACAO|ESTELIONATO)\M', 'patrimonial', 30),
    ('\m(ALAGAMENTO|INUNDACAO|ENXURRADA|DESTELHAMENTO|VENDAVAL|GRANIZO|ARVORES?|DESLIZAMENTO|DESABAMENTO|INCENDIO|FOGO|RISCO ESTRUTURAL|DEFESA CIVIL)\M', 'fisico', 40),
    ('\m(ACIDENTE|TRANSITO|ATROPELAMENTO|COLISAO|EMBRIAGUEZ AO VOLANTE)\M', 'transito', 50),
    ('\m(PERTURBACAO|SOSSEGO|SOM|EMBRIAGUEZ|ENTORPECENTE|DROGAS?|TRAFICO|AMBULANTE|COMERCIO IRREGULAR|ATO OBSCENO|DESORDEM|MORADOR DE RUA|SITUACAO DE RUA)\M', 'ordem_publica', 60)
) v WHERE NOT EXISTS (SELECT 1 FROM natureza_categoria);

CREATE OR REPLACE FUNCTION categoria_natureza(n TEXT) RETURNS TEXT
LANGUAGE sql STABLE PARALLEL SAFE SET search_path FROM CURRENT AS $$
    SELECT coalesce(
        (SELECT categoria FROM natureza_categoria WHERE norm_txt(n) ~ padrao ORDER BY ordem LIMIT 1),
        CASE WHEN nullif(btrim(n), '') IS NOT NULL THEN 'outros' END)
$$;

-- Listas públicas com CNPJ (M1b). Só linhas de empresas do recorte; sem CPF, contato ou nome de pessoa.
CREATE TABLE IF NOT EXISTS lista_spec (
    lista   TEXT PRIMARY KEY,
    nivel   TEXT NOT NULL,      -- estabelecimento (CNPJ igual) | empresa (mesma raiz)
    agregar TEXT NOT NULL       -- soma | media (do valor)
);

CREATE TABLE IF NOT EXISTS lista_registro (
    lista       TEXT NOT NULL,
    arquivo     TEXT,
    cnpj        VARCHAR(14),    -- nulo quando a lista só traz a raiz
    cnpj_basico VARCHAR(8) NOT NULL,
    rotulo      TEXT,
    data        DATE,
    valor       NUMERIC,
    atributos   JSONB
);
CREATE INDEX IF NOT EXISTS lista_registro_lista ON lista_registro (lista);
CREATE INDEX IF NOT EXISTS lista_registro_cnpj ON lista_registro (cnpj);
CREATE INDEX IF NOT EXISTS lista_registro_basico ON lista_registro (cnpj_basico);

CREATE TABLE IF NOT EXISTS empresa_lista (
    cnpj        VARCHAR(14) NOT NULL,
    lista       TEXT NOT NULL,
    via         TEXT NOT NULL,  -- cnpj | raiz
    registros   INT,
    valor       NUMERIC,
    data_min    DATE,
    data_max    DATE,
    rotulos     TEXT[],
    PRIMARY KEY (cnpj, lista)
);
CREATE INDEX IF NOT EXISTS empresa_lista_lista ON empresa_lista (lista);
