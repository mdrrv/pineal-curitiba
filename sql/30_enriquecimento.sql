-- Informação nova a partir do que o M0 já carrega (empresa, empresa_geo, cnefe). Nenhuma fonte nova.
--
--   empresa_perfil   por CNPJ: tipo do ponto, domiciliação, rede (filiais na cidade)
--   ponto_comercial  por endereço: quantos CNPJs já passaram, rotatividade, ponto vago
--   uso_zoneamento   por CNPJ ativo: a atividade é permitida na zona? (só onde há regra em zona_regra)
--
-- O endereço é a chave CEP|logradouro|número normalizada, sem complemento: salas do mesmo prédio
-- contam como o mesmo endereço, que é o que se quer para achar domiciliação.

DROP TABLE IF EXISTS empresa_perfil;
DROP TABLE IF EXISTS ponto_comercial;

-- espécies do CNEFE: 1 e 2 domicílio; 3 agropecuário; 4 ensino; 5 saúde; 6 outras finalidades;
-- 7 em construção; 8 religioso
CREATE TEMP TABLE _especie_endereco ON COMMIT DROP AS
SELECT cep, logr_chave, numero,
       bool_or(especie IN (1, 2)) AS tem_domicilio,
       bool_or(especie IN (3, 4, 5, 6, 8)) AS tem_estabelecimento
FROM cnefe
WHERE cep IS NOT NULL AND logr_chave IS NOT NULL AND numero IS NOT NULL
GROUP BY cep, logr_chave, numero;
CREATE INDEX ON _especie_endereco (cep, logr_chave, numero);

CREATE TEMP TABLE _endereco ON COMMIT DROP AS
SELECT g.cnpj, e.cnpj_basico, e.situacao_cadastral = '02' AS ativa, e.identificador_mf,
       e.data_inicio_atividade, e.data_situacao_cadastral, g.geo_precisao, g.geom,
       CASE WHEN g.cep IS NOT NULL AND g.logr_chave IS NOT NULL AND g.numero IS NOT NULL
            THEN concat_ws('|', g.cep, g.logr_chave, g.numero) END AS endereco_chave,
       CASE WHEN s.tem_domicilio AND s.tem_estabelecimento THEN 'misto'
            WHEN s.tem_estabelecimento THEN 'comercial'
            WHEN s.tem_domicilio THEN 'residencial'
            ELSE 'desconhecido' END AS tipo_ponto
FROM empresa_geo g
JOIN empresa e USING (cnpj)
LEFT JOIN _especie_endereco s ON s.cep = g.cep AND s.logr_chave = g.logr_chave AND s.numero = g.numero;

CREATE TABLE empresa_perfil AS
WITH por_endereco AS (
    SELECT endereco_chave, count(*) FILTER (WHERE ativa) AS ativos
    FROM _endereco WHERE endereco_chave IS NOT NULL
    GROUP BY 1
), rede AS (
    SELECT cnpj_basico,
           count(*) FILTER (WHERE ativa) AS ativos,
           bool_or(ativa AND identificador_mf = '1') AS matriz_ativa
    FROM _endereco
    GROUP BY 1
)
SELECT d.cnpj,
       d.endereco_chave,
       d.tipo_ponto,
       coalesce(p.ativos, 0) AS ativos_no_endereco,
       -- 20 ou mais CNPJs ativos no mesmo endereço: contabilidade, coworking ou escritório virtual
       coalesce(p.ativos, 0) >= 20 AS domiciliacao,
       coalesce(r.ativos, 0) AS ativos_da_raiz_na_cidade,
       coalesce(r.matriz_ativa, false) AS matriz_na_cidade,
       d.identificador_mf = '2' AS filial
FROM _endereco d
LEFT JOIN por_endereco p USING (endereco_chave)
LEFT JOIN rede r USING (cnpj_basico);
ALTER TABLE empresa_perfil ADD PRIMARY KEY (cnpj);
CREATE INDEX ON empresa_perfil (endereco_chave);

CREATE TABLE ponto_comercial AS
SELECT endereco_chave,
       min(tipo_ponto) AS tipo_ponto,
       ST_Centroid(ST_Collect(geom) FILTER (WHERE geo_precisao IN ('estabelecimento', 'endereco',
                                                                    'endereco_sem_cep', 'numero_proximo'))) AS geom,
       count(*) AS cnpjs_total,
       count(*) FILTER (WHERE ativa) AS cnpjs_ativos,
       count(*) FILTER (WHERE NOT ativa) AS cnpjs_encerrados,
       min(data_inicio_atividade) AS primeira_abertura,
       max(data_situacao_cadastral) FILTER (WHERE NOT ativa) AS ultimo_encerramento,
       round(count(*)::NUMERIC
             / greatest(1, extract(YEAR FROM age(current_date, min(data_inicio_atividade))))::NUMERIC, 2)
           AS cnpjs_por_ano,
       count(*) FILTER (WHERE ativa) = 0
           AND max(data_situacao_cadastral) FILTER (WHERE NOT ativa) >= current_date - INTERVAL '3 years'
           AS vago
FROM _endereco
WHERE endereco_chave IS NOT NULL
GROUP BY endereco_chave;
ALTER TABLE ponto_comercial ADD PRIMARY KEY (endereco_chave);
CREATE INDEX ON ponto_comercial USING gist (geom);

CREATE OR REPLACE VIEW uso_zoneamento AS
SELECT g.cnpj, g.zona, e.cnae_fiscal_principal, r.cnae_prefixo AS regra_prefixo, r.permitido
FROM empresa_geo g
JOIN empresa e USING (cnpj)
LEFT JOIN LATERAL (
    SELECT z.cnae_prefixo, z.permitido FROM zona_regra z
    WHERE z.zona = g.zona AND e.cnae_fiscal_principal LIKE z.cnae_prefixo || '%'
    ORDER BY length(z.cnae_prefixo) DESC
    LIMIT 1
) r ON true
WHERE e.situacao_cadastral = '02' AND g.zona IS NOT NULL;
