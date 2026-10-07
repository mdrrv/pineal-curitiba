-- Rede de caminhada (OSM ou eixos do IPPUC, nodada no PostGIS) e isócronas calculadas por etl/isocronas.py.

CREATE TABLE IF NOT EXISTS via_no (
    id          INT PRIMARY KEY,
    principal   BOOLEAN NOT NULL DEFAULT false,   -- no maior componente conexo (partida das isócronas)
    geom        geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS via_no_geom ON via_no USING gist (geom);

CREATE TABLE IF NOT EXISTS via_aresta (
    id              INT PRIMARY KEY,
    u               INT NOT NULL,
    v               INT NOT NULL,
    comprimento_m   DOUBLE PRECISION NOT NULL,
    tipo            TEXT,
    geom            geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS via_aresta_geom ON via_aresta USING gist (geom);

CREATE TABLE IF NOT EXISTS isocrona (
    id          SERIAL PRIMARY KEY,
    nome        TEXT,
    modo        TEXT NOT NULL,          -- pe | onibus (ônibus + caminhada)
    minutos     INT NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    saida       TEXT,                   -- dia e hora de saída (só ônibus)
    criada_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    geom        geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS isocrona_geom ON isocrona USING gist (geom);

-- moradores numa área qualquer (isócrona, bairro desenhado): mesma regra de moradores_raio
CREATE OR REPLACE FUNCTION moradores_area(area geometry)
RETURNS TABLE (moradores NUMERIC, domicilios NUMERIC, renda_media_responsavel NUMERIC)
LANGUAGE sql STABLE SET search_path FROM CURRENT AS $$
    WITH dom AS (
        SELECT left(regexp_replace(c.cd_setor, '\D', '', 'g'), 15) AS cd_setor, count(*) AS n
        FROM cnefe c
        WHERE c.especie IN (1, 2) AND ST_Intersects(c.geom, area)
        GROUP BY 1
    ), fr AS (
        SELECT d.*, CASE
                   WHEN d.domicilios_cnefe > 0 THEN coalesce(dom.n, 0)::NUMERIC / d.domicilios_cnefe
                   ELSE (ST_Area(ST_Intersection(s.geom, area)::geography) / NULLIF(ST_Area(s.geom::geography), 0))::NUMERIC
               END AS fracao
        FROM setor_demografia d
        JOIN setor s ON left(regexp_replace(s.cd_setor, '\D', '', 'g'), 15) = d.cd_setor
        LEFT JOIN dom ON dom.cd_setor = d.cd_setor
        WHERE ST_Intersects(s.geom, area)
    )
    SELECT round(sum(pessoas * fracao)), round(sum(domicilios_ocupados * fracao)),
           round(sum(renda_media_responsavel * domicilios_ocupados * fracao)
                 / NULLIF(sum(domicilios_ocupados * fracao) FILTER (WHERE renda_media_responsavel IS NOT NULL), 0), 2)
    FROM fr
$$;
