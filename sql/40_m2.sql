-- Primeiros indicadores do M2. Rodar depois de 30_enriquecimento.sql.
-- Contam só empresas ativas fora de endereço de domiciliação (que não operam onde estão registradas).
-- Nenhuma tabela aqui tem nome, razão social ou CPF: só código de atividade, território e contagens.
--
--   m2_saturacao_bairro     ativos por bairro x divisão CNAE, com quociente locacional (QL)
--   m2_sobrevivencia        % de empresas vivas 1, 3 e 5 anos depois de abrir, por coorte e divisão
--   m2_densidade_h3         ativos por hexágono H3 res 9 x divisão (divisao NULL = todas)
--   m2_movimento            aberturas, fechamentos, reativações, saídas e mudanças entre competências
--   raio_x(lat, lon, raio)  o que há num raio do ponto, comparado com a densidade da cidade

DROP TABLE IF EXISTS m2_saturacao_bairro, m2_sobrevivencia, m2_densidade_h3, m2_movimento;

CREATE TEMP TABLE _ativa ON COMMIT DROP AS
SELECT e.cnpj, left(e.cnae_fiscal_principal, 2) AS divisao, g.bairro, g.h3_9, g.geo_precisao, g.geom
FROM empresa e
JOIN empresa_geo g USING (cnpj)
LEFT JOIN empresa_perfil p USING (cnpj)
WHERE e.situacao_cadastral = '02' AND NOT coalesce(p.domiciliacao, false) AND e.cnae_fiscal_principal IS NOT NULL;

-- QL = (participação da divisão no bairro) / (participação da divisão na cidade).
-- QL > 1: o bairro concentra a atividade mais que a cidade (polo ou saturação); QL < 1: espaço livre.
CREATE TABLE m2_saturacao_bairro AS
WITH bd AS (
    SELECT bairro, divisao, count(*) AS ativos FROM _ativa WHERE bairro IS NOT NULL GROUP BY 1, 2
), b AS (
    SELECT bairro, sum(ativos) AS ativos_bairro FROM bd GROUP BY 1
), d AS (
    SELECT divisao, sum(ativos) AS ativos_divisao FROM bd GROUP BY 1
), t AS (
    SELECT sum(ativos) AS total FROM bd
)
SELECT bd.bairro, bd.divisao,
       (SELECT max(c.divisao_descricao) FROM cnae c WHERE c.divisao = bd.divisao) AS divisao_descricao,
       bd.ativos, b.ativos_bairro, d.ativos_divisao, t.total,
       round((bd.ativos::NUMERIC / b.ativos_bairro) / (d.ativos_divisao::NUMERIC / t.total), 3) AS ql
FROM bd JOIN b USING (bairro) JOIN d USING (divisao) CROSS JOIN t;
ALTER TABLE m2_saturacao_bairro ADD PRIMARY KEY (bairro, divisao);

-- Viva k anos depois de abrir: ainda ativa, ou encerrada depois de completar k anos.
-- Só entram coortes que já completaram k anos inteiros; as recentes ficam NULL.
CREATE TABLE m2_sobrevivencia AS
WITH base AS (
    SELECT extract(YEAR FROM data_inicio_atividade)::INT AS coorte, left(cnae_fiscal_principal, 2) AS divisao,
           data_inicio_atividade AS inicio,
           CASE WHEN situacao_cadastral = '02' THEN NULL ELSE coalesce(data_situacao_cadastral, data_inicio_atividade) END AS fim
    FROM empresa
    WHERE data_inicio_atividade IS NOT NULL AND cnae_fiscal_principal IS NOT NULL
), conta AS (
    SELECT coorte, divisao, count(*) AS abertas,
           count(*) FILTER (WHERE fim IS NULL) AS ativas_hoje,
           count(*) FILTER (WHERE fim IS NULL OR fim >= inicio + INTERVAL '1 year') AS vivas_1a,
           count(*) FILTER (WHERE fim IS NULL OR fim >= inicio + INTERVAL '3 years') AS vivas_3a,
           count(*) FILTER (WHERE fim IS NULL OR fim >= inicio + INTERVAL '5 years') AS vivas_5a
    FROM base
    GROUP BY GROUPING SETS ((coorte, divisao), (coorte))
)
SELECT coorte, divisao, abertas, ativas_hoje,
       CASE WHEN coorte + 1 < extract(YEAR FROM current_date) THEN round(100.0 * vivas_1a / abertas, 1) END AS sobrevivencia_1a,
       CASE WHEN coorte + 3 < extract(YEAR FROM current_date) THEN round(100.0 * vivas_3a / abertas, 1) END AS sobrevivencia_3a,
       CASE WHEN coorte + 5 < extract(YEAR FROM current_date) THEN round(100.0 * vivas_5a / abertas, 1) END AS sobrevivencia_5a
FROM conta;
COMMENT ON TABLE m2_sobrevivencia IS 'divisao NULL = todas as atividades da coorte';

CREATE TABLE m2_densidade_h3 AS
SELECT h3_9, divisao, count(*) AS ativos
FROM _ativa
WHERE h3_9 IS NOT NULL
GROUP BY GROUPING SETS ((h3_9, divisao), (h3_9));
CREATE INDEX ON m2_densidade_h3 (h3_9);
COMMENT ON TABLE m2_densidade_h3 IS 'divisao NULL = todas as atividades do hexágono';

-- eventos entre cada competência e a anterior (a primeira foto não gera eventos: não há com o que comparar)
CREATE TABLE m2_movimento AS
WITH comp AS (
    SELECT competencia, lag(competencia) OVER (ORDER BY competencia) AS anterior
    FROM (SELECT DISTINCT competencia FROM empresa_historico) c
), par AS (
    SELECT c.competencia, x.*
    FROM comp c
    CROSS JOIN LATERAL (
        SELECT coalesce(a.cnpj, b.cnpj) AS cnpj,
               b.situacao_cadastral AS sit_antes, a.situacao_cadastral AS sit_depois,
               b.endereco_chave AS end_antes, a.endereco_chave AS end_depois,
               b.cnae_fiscal_principal AS cnae_antes, a.cnae_fiscal_principal AS cnae_depois
        FROM (SELECT * FROM empresa_historico WHERE competencia = c.competencia) a
        FULL JOIN (SELECT * FROM empresa_historico WHERE competencia = c.anterior) b ON a.cnpj = b.cnpj
    ) x
    WHERE c.anterior IS NOT NULL
)
SELECT competencia, cnpj, evento, coalesce(cnae_depois, cnae_antes) AS cnae
FROM par
CROSS JOIN LATERAL (VALUES
    (CASE WHEN sit_antes IS NULL AND sit_depois = '02' THEN 'abertura' END),
    (CASE WHEN sit_antes = '02' AND sit_depois IS NOT NULL AND sit_depois <> '02' THEN 'fechamento' END),
    -- sumiu do recorte: mudou de município ou saiu da base; não dá para saber qual
    (CASE WHEN sit_antes = '02' AND sit_depois IS NULL THEN 'saiu_do_recorte' END),
    (CASE WHEN sit_antes IS NOT NULL AND sit_antes <> '02' AND sit_depois = '02' THEN 'reativacao' END),
    (CASE WHEN sit_antes = '02' AND sit_depois = '02' AND end_antes IS DISTINCT FROM end_depois THEN 'mudanca_endereco' END),
    (CASE WHEN sit_antes = '02' AND sit_depois = '02' AND cnae_antes IS DISTINCT FROM cnae_depois THEN 'mudanca_cnae' END)
) v (evento)
WHERE evento IS NOT NULL;
CREATE INDEX ON m2_movimento (competencia, evento);

-- O que há num raio do ponto, por divisão CNAE, comparado com a cidade.
-- Só entram empresas com localização de quadra (estabelecimento, endereço ou número próximo).
-- indice = densidade no raio / densidade na cidade x 100 (100 = igual à média da cidade).
-- Com o Censo carregado: moradores no raio (moradores_raio) e empresas por mil moradores no raio e na
-- cidade; indice_moradores < 100 = menos oferta por morador que a média da cidade (espaço livre).
DROP FUNCTION IF EXISTS raio_x(DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION);
CREATE FUNCTION raio_x(lat DOUBLE PRECISION, lon DOUBLE PRECISION, raio_m DOUBLE PRECISION DEFAULT 250)
RETURNS TABLE (divisao TEXT, divisao_descricao TEXT, ativos_raio BIGINT, por_km2_raio NUMERIC,
               por_km2_cidade NUMERIC, indice NUMERIC, moradores_raio NUMERIC, por_mil_moradores_raio NUMERIC,
               por_mil_moradores_cidade NUMERIC, indice_moradores NUMERIC)
LANGUAGE sql STABLE SET search_path FROM CURRENT AS $$
    WITH ponto AS (
        SELECT ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography AS g
    ), area_cidade AS (
        SELECT coalesce((SELECT ST_Area(ST_Union(geom)::geography) FROM bairro),
                        (SELECT ST_Area(ST_Union(geom)::geography) FROM setor)) / 1e6 AS km2
    ), precisa AS (
        SELECT e.cnpj, left(e.cnae_fiscal_principal, 2) AS divisao, g.geom
        FROM empresa e JOIN empresa_geo g USING (cnpj) LEFT JOIN empresa_perfil p USING (cnpj)
        WHERE e.situacao_cadastral = '02' AND NOT coalesce(p.domiciliacao, false)
          AND g.geo_precisao IN ('estabelecimento', 'endereco', 'endereco_sem_cep', 'numero_proximo')
    ), raio AS (
        SELECT p.divisao, count(*) AS n
        FROM precisa p, ponto
        WHERE ST_DWithin(p.geom::geography, ponto.g, raio_m)
        GROUP BY 1
    ), cidade AS (
        SELECT divisao, count(*) AS n FROM precisa GROUP BY 1
    ), mor AS (
        SELECT NULLIF((SELECT moradores FROM moradores_raio(lat, lon, raio_m)), 0) AS raio,
               NULLIF((SELECT sum(pessoas) FROM setor_demografia), 0) AS cidade
    )
    SELECT r.divisao,
           (SELECT max(c2.divisao_descricao) FROM cnae c2 WHERE c2.divisao = r.divisao),
           r.n,
           round((r.n / (pi() * raio_m ^ 2 / 1e6))::NUMERIC, 1),
           round((c.n / NULLIF(a.km2, 0))::NUMERIC, 1),
           round((100 * (r.n / (pi() * raio_m ^ 2 / 1e6)) / NULLIF(c.n / NULLIF(a.km2, 0), 0))::NUMERIC, 0),
           m.raio,
           round(1000 * r.n / m.raio, 2),
           round(1000 * c.n / m.cidade, 2),
           round(100 * (r.n / m.raio) / (c.n / m.cidade), 0)
    FROM raio r JOIN cidade c USING (divisao) CROSS JOIN area_cidade a CROSS JOIN mor m
    ORDER BY r.n DESC, r.divisao
$$;
