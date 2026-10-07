-- Agregados e índice de risco por bairro a partir de seguranca_ocorrencia (todas as fontes).
-- Sempre agregado por território, nunca por pessoa.
--
-- Janela: os 12 meses que terminam no último mês com dado (não a data de hoje), para o índice
-- não cair só porque a base ainda não foi atualizada.
--
-- risco_bairro: por bairro do IPPUC e categoria, ocorrências na janela, por km² e por mil empresas
-- ativas do bairro, e o percentil entre os bairros (0 a 100) da taxa usada pela categoria:
--   patrimonial  por mil empresas ativas (risco para o comércio estabelecido)
--   demais       por km² (até o Censo por setor entrar, #16)
-- risco_bairro_indice: percentis de patrimonial, violento e físico e o índice (média dos três).

DROP TABLE IF EXISTS seguranca_bairro_mes;
CREATE TABLE seguranca_bairro_mes AS
SELECT o.fonte, o.bairro, date_trunc('month', o.data)::DATE AS mes, c.categoria, count(*)::INT AS ocorrencias
FROM seguranca_ocorrencia o
CROSS JOIN LATERAL unnest(coalesce(o.categorias, ARRAY['outros'])) AS c(categoria)
WHERE o.data IS NOT NULL
GROUP BY 1, 2, 3, 4;

CREATE TEMP TABLE _janela ON COMMIT DROP AS
SELECT (date_trunc('month', max(data)) + INTERVAL '1 month')::DATE AS fim,
       (date_trunc('month', max(data)) - INTERVAL '11 months')::DATE AS inicio
FROM seguranca_ocorrencia;

DROP TABLE IF EXISTS seguranca_h3;
CREATE TABLE seguranca_h3 AS
SELECT o.h3_9, c.categoria, count(*)::INT AS ocorrencias_12m
FROM seguranca_ocorrencia o
CROSS JOIN LATERAL unnest(coalesce(o.categorias, ARRAY['outros'])) AS c(categoria)
CROSS JOIN _janela j
WHERE o.h3_9 IS NOT NULL AND o.data >= j.inicio AND o.data < j.fim
GROUP BY 1, 2;
ALTER TABLE seguranca_h3 ADD PRIMARY KEY (h3_9, categoria);

CREATE TEMP TABLE _bairro_base ON COMMIT DROP AS
SELECT b.nome AS bairro,
       ST_Area(b.geom::geography) / 1e6 AS area_km2,
       (SELECT count(*) FROM empresa_geo g JOIN empresa e USING (cnpj)
        WHERE g.bairro = b.nome AND e.situacao_cadastral = '02') AS empresas_ativas
FROM (SELECT DISTINCT ON (nome) nome, geom FROM bairro ORDER BY nome, ST_Area(geom) DESC) b;

DROP TABLE IF EXISTS risco_bairro;
CREATE TABLE risco_bairro AS
WITH oc AS (
    SELECT o.bairro, c.categoria, count(*) AS n
    FROM seguranca_ocorrencia o
    CROSS JOIN LATERAL unnest(coalesce(o.categorias, ARRAY['outros'])) AS c(categoria)
    CROSS JOIN _janela j
    WHERE o.data >= j.inicio AND o.data < j.fim
    GROUP BY 1, 2
), grade AS (
    SELECT b.*, cat.categoria, coalesce(oc.n, 0)::INT AS ocorrencias_12m
    FROM _bairro_base b
    CROSS JOIN (VALUES ('patrimonial'), ('violento'), ('fisico'), ('ordem_publica'), ('transito')) cat(categoria)
    LEFT JOIN oc ON oc.bairro = b.bairro AND oc.categoria = cat.categoria
), taxa AS (
    SELECT *,
           round((ocorrencias_12m / NULLIF(area_km2, 0))::NUMERIC, 2) AS por_km2,
           round((1000.0 * ocorrencias_12m / NULLIF(empresas_ativas, 0))::NUMERIC, 2) AS por_mil_empresas
    FROM grade
)
SELECT bairro, categoria, ocorrencias_12m, round(area_km2::NUMERIC, 3) AS area_km2, empresas_ativas, por_km2,
       por_mil_empresas,
       round((100 * percent_rank() OVER (
           PARTITION BY categoria
           ORDER BY CASE WHEN categoria = 'patrimonial' THEN coalesce(por_mil_empresas, 0) ELSE por_km2 END
       ))::NUMERIC, 1) AS percentil,
       (SELECT inicio FROM _janela) AS janela_inicio,
       (SELECT fim - 1 FROM _janela) AS janela_fim
FROM taxa;
ALTER TABLE risco_bairro ADD PRIMARY KEY (bairro, categoria);

DROP TABLE IF EXISTS risco_bairro_indice;
CREATE TABLE risco_bairro_indice AS
SELECT bairro,
       max(percentil) FILTER (WHERE categoria = 'patrimonial') AS patrimonial,
       max(percentil) FILTER (WHERE categoria = 'violento') AS violento,
       max(percentil) FILTER (WHERE categoria = 'fisico') AS fisico,
       round(avg(percentil) FILTER (WHERE categoria IN ('patrimonial', 'violento', 'fisico')), 1) AS indice
FROM risco_bairro
GROUP BY bairro;
ALTER TABLE risco_bairro_indice ADD PRIMARY KEY (bairro);
