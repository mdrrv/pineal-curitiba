-- Tabelas de apoio para os agregados saírem legíveis.
-- porte e situação cadastral são fixas (tabelas da Receita); CNAE e natureza jurídica são carregadas
-- por etl/fontes/apoio.py (API de CNAE do IBGE, com reserva nas tabelas da Receita no banco RFB).

CREATE TABLE IF NOT EXISTS porte (
    codigo    VARCHAR(2) PRIMARY KEY,
    descricao TEXT NOT NULL
);
INSERT INTO porte VALUES
    ('00', 'Não informado'), ('01', 'Microempresa'), ('03', 'Empresa de pequeno porte'), ('05', 'Demais')
ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE IF NOT EXISTS situacao_cadastral (
    codigo    VARCHAR(2) PRIMARY KEY,
    descricao TEXT NOT NULL
);
INSERT INTO situacao_cadastral VALUES
    ('01', 'Nula'), ('02', 'Ativa'), ('03', 'Suspensa'), ('04', 'Inapta'), ('08', 'Baixada')
ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE IF NOT EXISTS cnae (
    subclasse           VARCHAR(7) PRIMARY KEY,
    descricao           TEXT,
    classe              VARCHAR(5),
    classe_descricao    TEXT,
    grupo               VARCHAR(3),
    grupo_descricao     TEXT,
    divisao             VARCHAR(2),
    divisao_descricao   TEXT,
    secao               VARCHAR(1),
    secao_descricao     TEXT
);
CREATE INDEX IF NOT EXISTS cnae_divisao ON cnae (divisao);

CREATE TABLE IF NOT EXISTS natureza_juridica (
    codigo    VARCHAR(4) PRIMARY KEY,
    descricao TEXT
);

-- regras de uso por zona (Lei de Zoneamento): preenchidas à mão ou por um ETL futuro.
-- cnae_prefixo casa pelo começo do código (ex.: '47' = todo o varejo, '4711' = supermercados).
-- Vale a regra de prefixo mais longo.
CREATE TABLE IF NOT EXISTS zona_regra (
    zona          TEXT NOT NULL,
    cnae_prefixo  TEXT NOT NULL,
    permitido     BOOLEAN NOT NULL,
    fonte         TEXT,
    PRIMARY KEY (zona, cnae_prefixo)
);
