-- Censo 2022 por setor (demanda). Criadas junto com o schema; o ETL (etl/fontes/ibge_censo_setor.py) preenche.

-- formato longo: toda variável V#### dos arquivos de agregados, só dos setores do município
CREATE TABLE IF NOT EXISTS censo_setor_var (
    cd_setor    TEXT NOT NULL,
    tema        TEXT NOT NULL,      -- basico, demografia, renda_responsavel... (do nome do arquivo)
    variavel    TEXT NOT NULL,      -- V0001, V01031...; AREA_KM2
    valor       NUMERIC,            -- 'X' (sigilo) e '.' viram NULL
    PRIMARY KEY (cd_setor, tema, variavel)
);

-- variável do IBGE -> indicador do Pineal. Conferir com o dicionário de cada tema; a carga não sobrescreve
-- linhas alteradas aqui.
CREATE TABLE IF NOT EXISTS censo_variavel (
    tema        TEXT NOT NULL,
    variavel    TEXT NOT NULL,
    indicador   TEXT NOT NULL,
    descricao   TEXT,
    PRIMARY KEY (tema, variavel)
);
INSERT INTO censo_variavel (tema, variavel, indicador, descricao) VALUES
    ('basico', 'V0001', 'pessoas', 'Total de pessoas'),
    ('basico', 'V0002', 'domicilios', 'Total de domicílios'),
    ('basico', 'V0007', 'domicilios_ocupados', 'Domicílios particulares ocupados'),
    ('basico', 'V0005', 'moradores_por_domicilio', 'Média de moradores em domicílios particulares ocupados'),
    ('basico', 'AREA_KM2', 'area_km2', 'Área do setor em km²'),
    ('demografia', 'V01007', 'homens', 'Pessoas do sexo masculino'),
    ('demografia', 'V01008', 'mulheres', 'Pessoas do sexo feminino'),
    ('demografia', 'V01031', 'idade_0_4', '0 a 4 anos'),
    ('demografia', 'V01032', 'idade_5_9', '5 a 9 anos'),
    ('demografia', 'V01033', 'idade_10_14', '10 a 14 anos'),
    ('demografia', 'V01034', 'idade_15_19', '15 a 19 anos'),
    ('demografia', 'V01035', 'idade_20_24', '20 a 24 anos'),
    ('demografia', 'V01036', 'idade_25_29', '25 a 29 anos'),
    ('demografia', 'V01037', 'idade_30_39', '30 a 39 anos'),
    ('demografia', 'V01038', 'idade_40_49', '40 a 49 anos'),
    ('demografia', 'V01039', 'idade_50_59', '50 a 59 anos'),
    ('demografia', 'V01040', 'idade_60_69', '60 a 69 anos'),
    ('demografia', 'V01041', 'idade_70_mais', '70 anos ou mais'),
    ('renda_responsavel', 'V06004', 'renda_media_responsavel', 'Rendimento nominal médio mensal dos responsáveis (R$)')
ON CONFLICT (tema, variavel) DO NOTHING;

CREATE TABLE IF NOT EXISTS setor_demografia (
    cd_setor                TEXT PRIMARY KEY,
    bairro                  TEXT,
    pessoas                 NUMERIC,
    domicilios_ocupados     NUMERIC,
    moradores_por_domicilio NUMERIC,
    homens                  NUMERIC,
    mulheres                NUMERIC,
    idade_0_14              NUMERIC,
    idade_15_29             NUMERIC,
    idade_30_59             NUMERIC,
    idade_60_mais           NUMERIC,
    renda_media_responsavel NUMERIC,
    area_km2                NUMERIC,
    densidade_km2           NUMERIC,
    dependencia             NUMERIC,    -- (0-14 + 60+) / (15-59) x 100
    envelhecimento          NUMERIC,    -- 60+ / 0-14 x 100
    domicilios_cnefe        INT         -- endereços de domicílio do CNEFE no setor (base da distribuição)
);

-- endereços de domicílio do CNEFE por setor e hexágono: distribui a população do setor no espaço
CREATE TABLE IF NOT EXISTS setor_h3_domicilio (
    cd_setor    TEXT NOT NULL,
    h3_9        TEXT NOT NULL,
    enderecos   INT NOT NULL,
    PRIMARY KEY (cd_setor, h3_9)
);

-- moradores no raio: em cada setor, a fração dos domicílios do CNEFE dentro do raio (ou, sem CNEFE, a fração
-- da área) vezes a população do setor
CREATE OR REPLACE FUNCTION moradores_raio(lat DOUBLE PRECISION, lon DOUBLE PRECISION, raio_m DOUBLE PRECISION DEFAULT 500)
RETURNS TABLE (moradores NUMERIC, domicilios NUMERIC, renda_media_responsavel NUMERIC)
LANGUAGE sql STABLE SET search_path FROM CURRENT AS $$
    WITH ponto AS (
        SELECT ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography AS g
    ), dom AS (
        SELECT left(regexp_replace(c.cd_setor, '\D', '', 'g'), 15) AS cd_setor, count(*) AS n
        FROM cnefe c, ponto
        WHERE c.especie IN (1, 2) AND ST_DWithin(c.geom::geography, ponto.g, raio_m)
        GROUP BY 1
    ), fr AS (
        SELECT d.*, CASE
                   WHEN d.domicilios_cnefe > 0 THEN coalesce(dom.n, 0)::NUMERIC / d.domicilios_cnefe
                   ELSE (ST_Area(ST_Intersection(s.geom::geography, ST_Buffer(ponto.g, raio_m)))
                         / NULLIF(ST_Area(s.geom::geography), 0))::NUMERIC
               END AS fracao
        FROM setor_demografia d
        JOIN setor s ON left(regexp_replace(s.cd_setor, '\D', '', 'g'), 15) = d.cd_setor
        CROSS JOIN ponto
        LEFT JOIN dom ON dom.cd_setor = d.cd_setor
        WHERE ST_DWithin(s.geom::geography, ponto.g, raio_m)
    )
    SELECT round(sum(pessoas * fracao)), round(sum(domicilios_ocupados * fracao)),
           round(sum(renda_media_responsavel * domicilios_ocupados * fracao)
                 / NULLIF(sum(domicilios_ocupados * fracao) FILTER (WHERE renda_media_responsavel IS NOT NULL), 0), 2)
    FROM fr
$$;
