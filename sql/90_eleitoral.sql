-- Derivadas do módulo ME: chave territorial dos locais de votação, ponte seção -> território e agregados
-- por bairro. Roda depois de qualquer carga tse_* (cada ETL chama; etl/me.py também). Idempotente.
-- Desempate igual ao 20_territorio.sql: fica o menor polígono e, no empate, o menor código/nome.

-- chave territorial dos locais com geometria (volume pequeno: milhares de linhas)
UPDATE eleicao_local_votacao g
SET cd_setor = (SELECT s.cd_setor FROM setor s WHERE ST_Intersects(s.geom, g.geom)
                ORDER BY ST_Area(s.geom), s.cd_setor LIMIT 1),
    bairro   = (SELECT b.nome FROM bairro b WHERE ST_Intersects(b.geom, g.geom)
                ORDER BY ST_Area(b.geom), b.codigo NULLS LAST, b.nome LIMIT 1),
    regional = (SELECT r.nome FROM regional r WHERE ST_Intersects(r.geom, g.geom)
                ORDER BY ST_Area(r.geom), r.codigo NULLS LAST, r.nome LIMIT 1),
    zona_uso = (SELECT coalesce(z.codigo, z.nome) FROM zoneamento z WHERE ST_Intersects(z.geom, g.geom)
                ORDER BY ST_Area(z.geom), z.codigo NULLS LAST, z.nome LIMIT 1)
WHERE g.geom IS NOT NULL AND g.bairro IS NULL;

-- ponte seção -> território: para cada seção que aparece na votação ou no perfil, o local com geometria
-- do ano mais próximo (seção agregada sem local próprio herda o da seção principal do mesmo ano)
TRUNCATE eleicao_secao_territorio;
INSERT INTO eleicao_secao_territorio (ano, nr_zona, nr_secao, ano_local, cd_setor, bairro, regional, h3_8, h3_9)
SELECT s.ano, s.nr_zona, s.nr_secao, l.ano, l.cd_setor, l.bairro, l.regional, l.h3_8, l.h3_9
FROM (
    SELECT DISTINCT ano, nr_zona, nr_secao FROM eleicao_votacao_secao
    UNION
    SELECT DISTINCT ano, nr_zona, nr_secao FROM eleicao_perfil_secao
    UNION
    SELECT DISTINCT ano, nr_zona, nr_secao FROM eleicao_local_votacao
) s
LEFT JOIN LATERAL (
    SELECT l.ano, l.cd_setor, l.bairro, l.regional, l.h3_8, l.h3_9
    FROM eleicao_local_votacao l
    WHERE l.nr_zona = s.nr_zona AND l.geom IS NOT NULL
      AND (l.nr_secao = s.nr_secao
           OR l.nr_secao = (SELECT a.secao_principal FROM eleicao_local_votacao a
                            WHERE a.ano = l.ano AND a.nr_zona = s.nr_zona AND a.nr_secao = s.nr_secao))
    ORDER BY l.nr_secao = s.nr_secao DESC, abs(l.ano - s.ano), l.ano
    LIMIT 1
) l ON true;

-- votação por bairro, ano, turno, cargo e votável
TRUNCATE eleicao_bairro_votacao;
INSERT INTO eleicao_bairro_votacao (bairro, ano, turno, cd_cargo, cargo, nr_votavel, nm_votavel, votos, pct_cargo)
SELECT b.bairro, b.ano, b.turno, b.cd_cargo, b.cargo, b.nr_votavel, b.nm_votavel, b.votos,
       round(100.0 * b.votos / sum(b.votos) OVER (PARTITION BY b.bairro, b.ano, b.turno, b.cd_cargo), 2)
FROM (
    SELECT coalesce(t.bairro, '(sem território)') AS bairro, v.ano, v.turno, v.cd_cargo, min(v.cargo) AS cargo,
           v.nr_votavel, min(v.nm_votavel) AS nm_votavel, sum(v.votos) AS votos
    FROM eleicao_votacao_secao v
    LEFT JOIN eleicao_secao_territorio t USING (ano, nr_zona, nr_secao)
    GROUP BY 1, 2, 3, 4, 6
) b;

-- participação por bairro: aptos, comparecimento e abstenção (por seção, o arquivo repete por votável; fica o máximo)
TRUNCATE eleicao_bairro_participacao;
INSERT INTO eleicao_bairro_participacao (bairro, ano, turno, secoes, aptos, comparecimento, abstencoes, abstencao_pct)
SELECT bairro, ano, turno, count(*), sum(aptos), sum(comparecimento), sum(abstencoes),
       round(100.0 * sum(abstencoes) / NULLIF(sum(aptos), 0), 2)
FROM (
    SELECT coalesce(t.bairro, '(sem território)') AS bairro, v.ano, v.turno, v.nr_zona, v.nr_secao,
           max(v.aptos) AS aptos, max(v.comparecimento) AS comparecimento, max(v.abstencoes) AS abstencoes
    FROM eleicao_votacao_secao v
    LEFT JOIN eleicao_secao_territorio t USING (ano, nr_zona, nr_secao)
    GROUP BY 1, 2, 3, 4, 5
) s
GROUP BY 1, 2, 3;

ANALYZE eleicao_local_votacao, eleicao_secao_territorio, eleicao_bairro_votacao, eleicao_bairro_participacao;
