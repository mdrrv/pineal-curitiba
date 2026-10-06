-- Chave territorial de cada empresa geocodificada. Camada vazia (ainda não carregada) só deixa a coluna nula.
-- H3 é calculado em Python (etl/territorio.py) depois deste script.
--
-- Ponto na divisa entre dois polígonos (ou dentro de zonas que se sobrepõem) casa com mais de um.
-- Para o resultado não variar entre rodadas, fica o menor polígono (o mais específico) e, no empate,
-- o menor código e depois o menor nome.

UPDATE empresa_geo SET cd_setor = NULL, bairro = NULL, regional = NULL, zona = NULL, h3_8 = NULL, h3_9 = NULL;

UPDATE empresa_geo g SET cd_setor = x.cd_setor
FROM (
    SELECT DISTINCT ON (g2.cnpj) g2.cnpj, s.cd_setor
    FROM empresa_geo g2 JOIN setor s ON ST_Intersects(s.geom, g2.geom)
    ORDER BY g2.cnpj, ST_Area(s.geom), s.cd_setor
) x
WHERE g.cnpj = x.cnpj;

UPDATE empresa_geo g SET bairro = x.nome
FROM (
    SELECT DISTINCT ON (g2.cnpj) g2.cnpj, b.nome
    FROM empresa_geo g2 JOIN bairro b ON ST_Intersects(b.geom, g2.geom)
    ORDER BY g2.cnpj, ST_Area(b.geom), b.codigo NULLS LAST, b.nome
) x
WHERE g.cnpj = x.cnpj;

UPDATE empresa_geo g SET regional = x.nome
FROM (
    SELECT DISTINCT ON (g2.cnpj) g2.cnpj, r.nome
    FROM empresa_geo g2 JOIN regional r ON ST_Intersects(r.geom, g2.geom)
    ORDER BY g2.cnpj, ST_Area(r.geom), r.codigo NULLS LAST, r.nome
) x
WHERE g.cnpj = x.cnpj;

UPDATE empresa_geo g SET zona = x.zona
FROM (
    SELECT DISTINCT ON (g2.cnpj) g2.cnpj, coalesce(z.codigo, z.nome) AS zona
    FROM empresa_geo g2 JOIN zoneamento z ON ST_Intersects(z.geom, g2.geom)
    ORDER BY g2.cnpj, ST_Area(z.geom), z.codigo NULLS LAST, z.nome
) x
WHERE g.cnpj = x.cnpj;

ANALYZE empresa_geo;
