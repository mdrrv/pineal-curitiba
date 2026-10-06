-- Chave territorial de cada empresa geocodificada. Camada vazia (ainda não carregada) só deixa a coluna nula.
-- H3 é calculado em Python (etl/territorio.py) depois deste script.

UPDATE cwb.empresa_geo SET cd_setor = NULL, bairro = NULL, regional = NULL, zona = NULL, h3_8 = NULL, h3_9 = NULL;

UPDATE cwb.empresa_geo g SET cd_setor = s.cd_setor
FROM cwb.setor s
WHERE g.geom IS NOT NULL AND ST_Intersects(s.geom, g.geom);

UPDATE cwb.empresa_geo g SET bairro = b.nome
FROM cwb.bairro b
WHERE g.geom IS NOT NULL AND ST_Intersects(b.geom, g.geom);

UPDATE cwb.empresa_geo g SET regional = r.nome
FROM cwb.regional r
WHERE g.geom IS NOT NULL AND ST_Intersects(r.geom, g.geom);

UPDATE cwb.empresa_geo g SET zona = coalesce(z.codigo, z.nome)
FROM cwb.zoneamento z
WHERE g.geom IS NOT NULL AND ST_Intersects(z.geom, g.geom);

ANALYZE cwb.empresa_geo;
