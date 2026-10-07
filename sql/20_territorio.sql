-- Chave territorial de cada empresa geocodificada. Camada vazia (ainda não carregada) só deixa a coluna nula.
-- Quem chama (etl/territorio.py) já deixou na sessão a tabela temporária h3_carga (cnpj, h3_8, h3_9).
--
-- Ponto na divisa entre dois polígonos (ou dentro de zonas que se sobrepõem) casa com mais de um.
-- Para o resultado não variar entre rodadas, fica o menor polígono (o mais específico) e, no empate,
-- o menor código e depois o menor nome.
--
-- Tudo é calculado numa tabela temporária e gravado num UPDATE só: com uma passada por camada, cada uma
-- reescrevia o milhão de linhas de empresa_geo (5 minutos no volume de Curitiba).

DROP TABLE IF EXISTS _chave;
CREATE TEMP TABLE _chave ON COMMIT DROP AS
SELECT g.cnpj,
       (SELECT s.cd_setor FROM setor s WHERE ST_Intersects(s.geom, g.geom)
        ORDER BY ST_Area(s.geom), s.cd_setor LIMIT 1) AS cd_setor,
       (SELECT b.nome FROM bairro b WHERE ST_Intersects(b.geom, g.geom)
        ORDER BY ST_Area(b.geom), b.codigo NULLS LAST, b.nome LIMIT 1) AS bairro,
       (SELECT r.nome FROM regional r WHERE ST_Intersects(r.geom, g.geom)
        ORDER BY ST_Area(r.geom), r.codigo NULLS LAST, r.nome LIMIT 1) AS regional,
       (SELECT coalesce(z.codigo, z.nome) FROM zoneamento z WHERE ST_Intersects(z.geom, g.geom)
        ORDER BY ST_Area(z.geom), z.codigo NULLS LAST, z.nome LIMIT 1) AS zona
FROM empresa_geo g
WHERE g.geom IS NOT NULL;

UPDATE empresa_geo g
SET cd_setor = x.cd_setor, bairro = x.bairro, regional = x.regional, zona = x.zona, h3_8 = x.h3_8, h3_9 = x.h3_9
FROM (
    SELECT g2.cnpj, k.cd_setor, k.bairro, k.regional, k.zona, h.h3_8, h.h3_9
    FROM empresa_geo g2
    LEFT JOIN _chave k USING (cnpj)
    LEFT JOIN h3_carga h USING (cnpj)
) x
WHERE g.cnpj = x.cnpj;

ANALYZE empresa_geo;
