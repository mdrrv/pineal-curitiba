-- Demanda a partir do Censo 2022 por setor. Quem chama (etl/fontes/ibge_censo_setor.py) já carregou
-- censo_setor_var e setor_h3_domicilio. cd_setor aqui tem só os 15 dígitos.
--
-- setor_demografia  indicadores por setor (variáveis mapeadas em censo_variavel) e o bairro do setor
-- demanda_h3        moradores, domicílios, faixas de idade e renda por hexágono: a população do setor
--                   distribuída pelos endereços de domicílio do CNEFE (sem domicílio no CNEFE: inteira no
--                   hexágono do ponto interno do setor)
-- m2_espaco_livre   por bairro e classe CNAE de comércio e serviço ao morador: empresas ativas, moradores,
--                   oferta esperada pela média da cidade (empresas por morador) e a lacuna

TRUNCATE setor_demografia;
INSERT INTO setor_demografia
WITH v AS (
    SELECT x.cd_setor, cv.indicador, x.valor
    FROM censo_setor_var x JOIN censo_variavel cv USING (tema, variavel)
), p AS (
    SELECT cd_setor,
           max(valor) FILTER (WHERE indicador = 'pessoas') AS pessoas,
           max(valor) FILTER (WHERE indicador = 'domicilios_ocupados') AS domicilios_ocupados,
           max(valor) FILTER (WHERE indicador = 'moradores_por_domicilio') AS moradores_por_domicilio,
           max(valor) FILTER (WHERE indicador = 'homens') AS homens,
           max(valor) FILTER (WHERE indicador = 'mulheres') AS mulheres,
           sum(valor) FILTER (WHERE indicador IN ('idade_0_4', 'idade_5_9', 'idade_10_14')) AS idade_0_14,
           sum(valor) FILTER (WHERE indicador IN ('idade_15_19', 'idade_20_24', 'idade_25_29')) AS idade_15_29,
           sum(valor) FILTER (WHERE indicador IN ('idade_30_39', 'idade_40_49', 'idade_50_59')) AS idade_30_59,
           sum(valor) FILTER (WHERE indicador IN ('idade_60_69', 'idade_70_mais')) AS idade_60_mais,
           max(valor) FILTER (WHERE indicador = 'renda_media_responsavel') AS renda_media_responsavel,
           max(valor) FILTER (WHERE indicador = 'area_km2') AS area_km2
    FROM v GROUP BY 1
), s AS (
    SELECT DISTINCT ON (left(regexp_replace(cd_setor, '\D', '', 'g'), 15))
           left(regexp_replace(cd_setor, '\D', '', 'g'), 15) AS cd_setor, geom
    FROM setor ORDER BY 1, ST_Area(geom) DESC
), b AS (
    SELECT s.cd_setor, (SELECT bb.nome FROM bairro bb WHERE ST_Intersects(bb.geom, ST_PointOnSurface(s.geom))
                        ORDER BY ST_Area(bb.geom), bb.nome LIMIT 1) AS bairro,
           ST_Area(s.geom::geography) / 1e6 AS area_geo
    FROM s
), d AS (
    SELECT cd_setor, sum(enderecos)::INT AS domicilios_cnefe FROM setor_h3_domicilio GROUP BY 1
)
SELECT p.cd_setor, b.bairro,
       coalesce(p.pessoas, p.homens + p.mulheres),
       p.domicilios_ocupados, p.moradores_por_domicilio, p.homens, p.mulheres,
       p.idade_0_14, p.idade_15_29, p.idade_30_59, p.idade_60_mais, p.renda_media_responsavel,
       round(coalesce(p.area_km2, b.area_geo::NUMERIC), 4),
       round(coalesce(p.pessoas, p.homens + p.mulheres) / NULLIF(coalesce(p.area_km2, b.area_geo::NUMERIC), 0), 1),
       round(100 * (p.idade_0_14 + p.idade_60_mais) / NULLIF(p.idade_15_29 + p.idade_30_59, 0), 1),
       round(100 * p.idade_60_mais / NULLIF(p.idade_0_14, 0), 1),
       coalesce(d.domicilios_cnefe, 0)
FROM p
LEFT JOIN b USING (cd_setor)
LEFT JOIN d USING (cd_setor);

DROP TABLE IF EXISTS demanda_h3;
CREATE TABLE demanda_h3 AS
WITH f AS (
    SELECT h.h3_9, d.*,
           CASE WHEN d.domicilios_cnefe > 0 THEN h.enderecos::NUMERIC / d.domicilios_cnefe ELSE 1 END AS fr
    FROM setor_h3_domicilio h JOIN setor_demografia d USING (cd_setor)
    WHERE d.domicilios_cnefe > 0 OR h.enderecos = 0  -- enderecos = 0: setor sem domicílio no CNEFE (ponto interno)
)
SELECT h3_9,
       round(sum(pessoas * fr)) AS moradores,
       round(sum(domicilios_ocupados * fr)) AS domicilios,
       round(sum(idade_0_14 * fr)) AS idade_0_14,
       round(sum(idade_60_mais * fr)) AS idade_60_mais,
       round(sum(renda_media_responsavel * domicilios_ocupados * fr)
             / NULLIF(sum(domicilios_ocupados * fr) FILTER (WHERE renda_media_responsavel IS NOT NULL), 0), 2)
           AS renda_media_responsavel
FROM f
GROUP BY 1;
ALTER TABLE demanda_h3 ADD PRIMARY KEY (h3_9);

-- Comércio e serviço ao morador: varejo (47), alimentação (56), veterinária (75), educação (85), saúde (86),
-- esporte e lazer (93), reparação (95), serviços pessoais (96). Sem domiciliação.
-- Mede só moradores: bairro com muito fluxo de quem trabalha ou passa (Centro) aparece saturado e é normal.
DROP TABLE IF EXISTS m2_espaco_livre;
CREATE TABLE m2_espaco_livre AS
WITH mor AS (
    SELECT bairro, sum(pessoas) AS moradores,
           round(sum(renda_media_responsavel * domicilios_ocupados)
                 / NULLIF(sum(domicilios_ocupados) FILTER (WHERE renda_media_responsavel IS NOT NULL), 0), 2) AS renda
    FROM setor_demografia WHERE bairro IS NOT NULL GROUP BY 1
), ativ AS (
    SELECT g.bairro, left(e.cnae_fiscal_principal, 5) AS classe, count(*) AS n
    FROM empresa e
    JOIN empresa_geo g USING (cnpj)
    LEFT JOIN empresa_perfil p USING (cnpj)
    WHERE e.situacao_cadastral = '02' AND NOT coalesce(p.domiciliacao, false) AND g.bairro IS NOT NULL
      AND left(e.cnae_fiscal_principal, 2) IN ('47', '56', '75', '85', '86', '93', '95', '96')
    GROUP BY 1, 2
), cid AS (
    SELECT a.classe, sum(a.n) AS n FROM ativ a JOIN mor USING (bairro) GROUP BY 1
), tot AS (
    SELECT sum(moradores) AS m FROM mor
), base AS (
    SELECT mor.bairro, cid.classe, coalesce(a.n, 0) AS ativos, mor.moradores, mor.renda,
           mor.moradores * cid.n / NULLIF(tot.m, 0) AS esperado, cid.n AS ativos_cidade, tot.m AS moradores_cidade
    FROM mor CROSS JOIN cid CROSS JOIN tot
    LEFT JOIN ativ a ON a.bairro = mor.bairro AND a.classe = cid.classe
)
SELECT bairro, classe,
       (SELECT max(c.classe_descricao) FROM cnae c WHERE c.classe = base.classe) AS classe_descricao,
       ativos, moradores, renda AS renda_media_responsavel,
       round(1000 * ativos / NULLIF(moradores, 0), 3) AS por_mil_moradores,
       round(1000 * ativos_cidade / NULLIF(moradores_cidade, 0), 3) AS por_mil_moradores_cidade,
       round(esperado, 1) AS esperado,
       round(esperado - ativos, 1) AS lacuna,
       round(100 * ativos / NULLIF(esperado, 0)) AS indice
FROM base;
ALTER TABLE m2_espaco_livre ADD PRIMARY KEY (bairro, classe);
