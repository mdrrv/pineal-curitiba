-- Geocodificação dos CNPJs pelo CNEFE 2022, em níveis do mais preciso ao menos preciso.
-- Cada empresa fica com o primeiro nível que casar; geo_precisao diz qual foi.
--
--   endereco              CEP + logradouro + número exatos
--   endereco_sem_cep      logradouro + número exatos na cidade, quando todos os pontos ficam a < 300 m
--   numero_proximo        CEP + logradouro, número de mesma paridade a até 30 de distância
--   logradouro            CEP + logradouro, ponto do CNEFE mais perto do centro da rua
--   logradouro_aproximado mesmo CEP, nome parecido (trigram >= 0,6), mesmo critério acima
--   logradouro_sem_cep    logradouro único na cidade (pontos a < 1,5 km), sem número
--   cep                   ponto central do CEP, só quando o CEP cobre < 1,5 km
--   nao_localizado        nenhum dos anteriores

TRUNCATE cwb.empresa_geo;

INSERT INTO cwb.empresa_geo (cnpj, cep, logr_chave, numero)
SELECT cnpj, cwb.norm_cep(cep), cwb.norm_logradouro(logradouro), cwb.norm_numero(numero)
FROM cwb.empresa;

-- agregados do CNEFE ----------------------------------------------------------

DROP TABLE IF EXISTS cwb._cnefe_end;
CREATE UNLOGGED TABLE cwb._cnefe_end AS
SELECT cep, logr_chave, numero, ST_Centroid(ST_Collect(geom)) AS geom
FROM cwb.cnefe
WHERE cep IS NOT NULL AND logr_chave IS NOT NULL AND numero IS NOT NULL
GROUP BY cep, logr_chave, numero;
CREATE INDEX ON cwb._cnefe_end (cep, logr_chave, numero);

DROP TABLE IF EXISTS cwb._cnefe_end_cidade;
CREATE UNLOGGED TABLE cwb._cnefe_end_cidade AS
SELECT logr_chave, numero, ST_Centroid(ST_Collect(geom)) AS geom
FROM cwb._cnefe_end
GROUP BY logr_chave, numero
HAVING ST_Distance(ST_SetSRID(ST_MakePoint(min(ST_X(geom)), min(ST_Y(geom))), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(max(ST_X(geom)), max(ST_Y(geom))), 4326)::geography) < 300;
CREATE INDEX ON cwb._cnefe_end_cidade (logr_chave, numero);

DROP TABLE IF EXISTS cwb._cnefe_logr;
CREATE UNLOGGED TABLE cwb._cnefe_logr AS
SELECT cep, logr_chave,
       ST_ClosestPoint(ST_Collect(geom), ST_Centroid(ST_Collect(geom))) AS geom
FROM cwb.cnefe
WHERE cep IS NOT NULL AND logr_chave IS NOT NULL
GROUP BY cep, logr_chave;
CREATE INDEX ON cwb._cnefe_logr (cep, logr_chave);
CREATE INDEX ON cwb._cnefe_logr USING gist (logr_chave gist_trgm_ops);

DROP TABLE IF EXISTS cwb._cnefe_logr_cidade;
CREATE UNLOGGED TABLE cwb._cnefe_logr_cidade AS
SELECT logr_chave,
       ST_ClosestPoint(ST_Collect(geom), ST_Centroid(ST_Collect(geom))) AS geom
FROM cwb.cnefe
WHERE logr_chave IS NOT NULL
GROUP BY logr_chave
HAVING ST_Distance(ST_SetSRID(ST_MakePoint(min(ST_X(geom)), min(ST_Y(geom))), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(max(ST_X(geom)), max(ST_Y(geom))), 4326)::geography) < 1500;
CREATE INDEX ON cwb._cnefe_logr_cidade (logr_chave);

DROP TABLE IF EXISTS cwb._cnefe_cep;
CREATE UNLOGGED TABLE cwb._cnefe_cep AS
SELECT cep, ST_ClosestPoint(ST_Collect(geom), ST_Centroid(ST_Collect(geom))) AS geom
FROM cwb.cnefe
WHERE cep IS NOT NULL
GROUP BY cep
HAVING ST_Distance(ST_SetSRID(ST_MakePoint(min(ST_X(geom)), min(ST_Y(geom))), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(max(ST_X(geom)), max(ST_Y(geom))), 4326)::geography) < 1500;
CREATE INDEX ON cwb._cnefe_cep (cep);

ANALYZE cwb.empresa_geo;

-- níveis ----------------------------------------------------------------------

UPDATE cwb.empresa_geo g SET geom = a.geom, geo_precisao = 'endereco'
FROM cwb._cnefe_end a
WHERE g.geo_precisao IS NULL
  AND a.cep = g.cep AND a.logr_chave = g.logr_chave AND a.numero = g.numero;

UPDATE cwb.empresa_geo g SET geom = a.geom, geo_precisao = 'endereco_sem_cep'
FROM cwb._cnefe_end_cidade a
WHERE g.geo_precisao IS NULL
  AND a.logr_chave = g.logr_chave AND a.numero = g.numero;

WITH m AS (
    SELECT g.cnpj, x.geom
    FROM cwb.empresa_geo g
    CROSS JOIN LATERAL (
        SELECT a.geom FROM cwb._cnefe_end a
        WHERE a.cep = g.cep AND a.logr_chave = g.logr_chave
          AND a.numero % 2 = g.numero % 2 AND abs(a.numero - g.numero) <= 30
        ORDER BY abs(a.numero - g.numero), a.numero
        LIMIT 1
    ) x
    WHERE g.geo_precisao IS NULL AND g.numero IS NOT NULL
)
UPDATE cwb.empresa_geo g SET geom = m.geom, geo_precisao = 'numero_proximo'
FROM m WHERE g.cnpj = m.cnpj;

UPDATE cwb.empresa_geo g SET geom = a.geom, geo_precisao = 'logradouro'
FROM cwb._cnefe_logr a
WHERE g.geo_precisao IS NULL
  AND a.cep = g.cep AND a.logr_chave = g.logr_chave;

WITH m AS (
    SELECT g.cnpj, x.geom
    FROM cwb.empresa_geo g
    CROSS JOIN LATERAL (
        SELECT a.geom FROM cwb._cnefe_logr a
        WHERE a.cep = g.cep AND similarity(a.logr_chave, g.logr_chave) >= 0.6
        ORDER BY similarity(a.logr_chave, g.logr_chave) DESC, a.logr_chave
        LIMIT 1
    ) x
    WHERE g.geo_precisao IS NULL AND g.cep IS NOT NULL AND g.logr_chave IS NOT NULL
)
UPDATE cwb.empresa_geo g SET geom = m.geom, geo_precisao = 'logradouro_aproximado'
FROM m WHERE g.cnpj = m.cnpj;

UPDATE cwb.empresa_geo g SET geom = a.geom, geo_precisao = 'logradouro_sem_cep'
FROM cwb._cnefe_logr_cidade a
WHERE g.geo_precisao IS NULL AND a.logr_chave = g.logr_chave;

UPDATE cwb.empresa_geo g SET geom = a.geom, geo_precisao = 'cep'
FROM cwb._cnefe_cep a
WHERE g.geo_precisao IS NULL AND a.cep = g.cep;

UPDATE cwb.empresa_geo SET geo_precisao = 'nao_localizado' WHERE geo_precisao IS NULL;

DROP TABLE cwb._cnefe_end, cwb._cnefe_end_cidade, cwb._cnefe_logr, cwb._cnefe_logr_cidade, cwb._cnefe_cep;

ANALYZE cwb.empresa_geo;
