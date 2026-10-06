-- Núcleo da geocodificação. Quem chama (etl/geocodificar.py) prepara, na mesma sessão:
--   alvo        tabela temporária: id, cep, logr_chave, logr_completa, numero, nome_chave, bairro_chave,
--               geo_precisao (NULL), geom (NULL)
--   cnefe_base  view temporária com os endereços do CNEFE que podem ser usados
-- O mesmo núcleo serve aos CNPJs (base = CNEFE inteiro) e à medição do erro em metros
-- (alvo = amostra do CNEFE, base = CNEFE sem a amostra).
--
-- Cada alvo fica com o primeiro nível que casar:
--   estabelecimento        mesmo CEP e nome do estabelecimento no CNEFE parecido com o nome da empresa
--                          (trigramas >= 0,5 na mesma rua, ou >= 0,7 em qualquer rua do CEP)
--   endereco               CEP + logradouro + número exatos
--   endereco_sem_cep       logradouro (chave completa) + número exatos na cidade, pontos a < 300 m entre si
--   numero_proximo         CEP + logradouro, número de mesma paridade a até 30 de distância
--   logradouro             CEP + logradouro, endereço do CNEFE mais perto do centro da rua
--   logradouro_aproximado  mesmo CEP, nome da rua parecido (trigramas >= 0,6)
--   logradouro_sem_cep     logradouro (chave completa) único na cidade, pontos a < 1,5 km entre si
--   cep                    ponto central do CEP, só quando o CEP cobre < 1,5 km
--   bairro                 bairro declarado à Receita casado pelo nome com o bairro do IPPUC
--   nao_localizado         nenhum dos anteriores
-- Os níveis sem CEP usam a chave completa do logradouro (com títulos), para "R. São José" e
-- "R. José" não virarem a mesma rua.

CREATE TEMP TABLE _cnefe_estab ON COMMIT DROP AS
SELECT cep, logr_chave, numero, nome_chave, geom
FROM cnefe_base
WHERE cep IS NOT NULL AND nome_chave IS NOT NULL;
CREATE INDEX ON _cnefe_estab (cep);

CREATE TEMP TABLE _cnefe_end ON COMMIT DROP AS
SELECT cep, logr_chave, numero, ST_Centroid(ST_Collect(geom)) AS geom
FROM cnefe_base
WHERE cep IS NOT NULL AND logr_chave IS NOT NULL AND numero IS NOT NULL
GROUP BY cep, logr_chave, numero;
CREATE INDEX ON _cnefe_end (cep, logr_chave, numero);

CREATE TEMP TABLE _cnefe_end_cidade ON COMMIT DROP AS
SELECT logr_completa, numero, ST_Centroid(ST_Collect(geom)) AS geom
FROM cnefe_base
WHERE logr_completa IS NOT NULL AND numero IS NOT NULL
GROUP BY logr_completa, numero
HAVING ST_Distance(ST_SetSRID(ST_MakePoint(min(ST_X(geom)), min(ST_Y(geom))), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(max(ST_X(geom)), max(ST_Y(geom))), 4326)::geography) < 300;
CREATE INDEX ON _cnefe_end_cidade (logr_completa, numero);

CREATE TEMP TABLE _cnefe_logr ON COMMIT DROP AS
SELECT cep, logr_chave, ST_ClosestPoint(ST_Collect(geom), ST_Centroid(ST_Collect(geom))) AS geom
FROM cnefe_base
WHERE cep IS NOT NULL AND logr_chave IS NOT NULL
GROUP BY cep, logr_chave;
CREATE INDEX ON _cnefe_logr (cep, logr_chave);

CREATE TEMP TABLE _cnefe_logr_cidade ON COMMIT DROP AS
SELECT logr_completa, ST_ClosestPoint(ST_Collect(geom), ST_Centroid(ST_Collect(geom))) AS geom
FROM cnefe_base
WHERE logr_completa IS NOT NULL
GROUP BY logr_completa
HAVING ST_Distance(ST_SetSRID(ST_MakePoint(min(ST_X(geom)), min(ST_Y(geom))), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(max(ST_X(geom)), max(ST_Y(geom))), 4326)::geography) < 1500;
CREATE INDEX ON _cnefe_logr_cidade (logr_completa);

CREATE TEMP TABLE _cnefe_cep ON COMMIT DROP AS
SELECT cep, ST_ClosestPoint(ST_Collect(geom), ST_Centroid(ST_Collect(geom))) AS geom
FROM cnefe_base
WHERE cep IS NOT NULL
GROUP BY cep
HAVING ST_Distance(ST_SetSRID(ST_MakePoint(min(ST_X(geom)), min(ST_Y(geom))), 4326)::geography,
                   ST_SetSRID(ST_MakePoint(max(ST_X(geom)), max(ST_Y(geom))), 4326)::geography) < 1500;
CREATE INDEX ON _cnefe_cep (cep);

CREATE TEMP TABLE _bairro_ponto ON COMMIT DROP AS
SELECT DISTINCT ON (norm_txt(nome)) norm_txt(nome) AS bairro_chave, ST_PointOnSurface(geom) AS geom
FROM bairro
ORDER BY norm_txt(nome), ST_Area(geom) DESC;

ANALYZE alvo;

-- níveis ----------------------------------------------------------------------

WITH m AS (
    SELECT a.id, x.geom
    FROM alvo a
    CROSS JOIN LATERAL (
        SELECT e.geom FROM _cnefe_estab e
        WHERE e.cep = a.cep
          AND (similarity(e.nome_chave, a.nome_chave) >= 0.7
               OR (e.logr_chave = a.logr_chave AND similarity(e.nome_chave, a.nome_chave) >= 0.5))
        ORDER BY (e.numero IS NOT DISTINCT FROM a.numero) DESC, similarity(e.nome_chave, a.nome_chave) DESC,
                 e.nome_chave, e.numero
        LIMIT 1
    ) x
    WHERE a.geo_precisao IS NULL AND a.cep IS NOT NULL AND length(a.nome_chave) >= 4
)
UPDATE alvo a SET geom = m.geom, geo_precisao = 'estabelecimento' FROM m WHERE a.id = m.id;

UPDATE alvo a SET geom = e.geom, geo_precisao = 'endereco'
FROM _cnefe_end e
WHERE a.geo_precisao IS NULL
  AND e.cep = a.cep AND e.logr_chave = a.logr_chave AND e.numero = a.numero;

UPDATE alvo a SET geom = e.geom, geo_precisao = 'endereco_sem_cep'
FROM _cnefe_end_cidade e
WHERE a.geo_precisao IS NULL
  AND e.logr_completa = a.logr_completa AND e.numero = a.numero;

WITH m AS (
    SELECT a.id, x.geom
    FROM alvo a
    CROSS JOIN LATERAL (
        SELECT e.geom FROM _cnefe_end e
        WHERE e.cep = a.cep AND e.logr_chave = a.logr_chave
          AND e.numero % 2 = a.numero % 2 AND abs(e.numero - a.numero) <= 30
        ORDER BY abs(e.numero - a.numero), e.numero
        LIMIT 1
    ) x
    WHERE a.geo_precisao IS NULL AND a.numero IS NOT NULL
)
UPDATE alvo a SET geom = m.geom, geo_precisao = 'numero_proximo' FROM m WHERE a.id = m.id;

UPDATE alvo a SET geom = e.geom, geo_precisao = 'logradouro'
FROM _cnefe_logr e
WHERE a.geo_precisao IS NULL AND e.cep = a.cep AND e.logr_chave = a.logr_chave;

WITH m AS (
    SELECT a.id, x.geom
    FROM alvo a
    CROSS JOIN LATERAL (
        SELECT e.geom FROM _cnefe_logr e
        WHERE e.cep = a.cep AND similarity(e.logr_chave, a.logr_chave) >= 0.6
        ORDER BY similarity(e.logr_chave, a.logr_chave) DESC, e.logr_chave
        LIMIT 1
    ) x
    WHERE a.geo_precisao IS NULL AND a.cep IS NOT NULL AND a.logr_chave IS NOT NULL
)
UPDATE alvo a SET geom = m.geom, geo_precisao = 'logradouro_aproximado' FROM m WHERE a.id = m.id;

UPDATE alvo a SET geom = e.geom, geo_precisao = 'logradouro_sem_cep'
FROM _cnefe_logr_cidade e
WHERE a.geo_precisao IS NULL AND e.logr_completa = a.logr_completa;

UPDATE alvo a SET geom = e.geom, geo_precisao = 'cep'
FROM _cnefe_cep e
WHERE a.geo_precisao IS NULL AND e.cep = a.cep;

UPDATE alvo a SET geom = b.geom, geo_precisao = 'bairro'
FROM _bairro_ponto b
WHERE a.geo_precisao IS NULL AND b.bairro_chave = a.bairro_chave;

UPDATE alvo SET geo_precisao = 'nao_localizado' WHERE geo_precisao IS NULL;
