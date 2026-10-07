-- Fontes extras: marcas do INPI (só titular pessoa jurídica casado com o recorte) e clima diário (INMET).

CREATE TABLE IF NOT EXISTS inpi_marca (
    processo            TEXT PRIMARY KEY,
    cnpj                VARCHAR(14) NOT NULL,   -- matriz em Curitiba do titular (casado pela razão social)
    data_deposito       DATE,
    marca               TEXT,
    apresentacao        TEXT,                   -- nominativa, mista, figurativa...
    natureza            TEXT,                   -- de produto, de serviço...
    classes_nice        TEXT[],
    ultimo_despacho     TEXT,
    ultimo_despacho_nome TEXT,
    revista             INT                     -- número da RPI do último despacho
);
CREATE INDEX IF NOT EXISTS inpi_marca_cnpj ON inpi_marca (cnpj);

CREATE TABLE IF NOT EXISTS clima_dia (
    estacao             TEXT NOT NULL,
    data                DATE NOT NULL,
    precipitacao_mm     NUMERIC,
    horas_com_chuva     INT,
    temp_media          NUMERIC,
    temp_min            NUMERIC,
    temp_max            NUMERIC,
    horas_medidas       INT,
    PRIMARY KEY (estacao, data)
);
