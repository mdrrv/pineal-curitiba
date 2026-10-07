-- Score de lead por CNPJ ativo. Quem chama (etl/score.py) já gravou empresa_risco.
-- Pontos por critério na tabela lead_peso (editável: a carga não sobrescreve pesos alterados). O score é a
-- soma dos pontos, limitada a 0..100. Tabelas de passos que não rodaram (empresa_perfil, empresa_sinais,
-- empresa_alvara, empresa_contratos_pmc) viram tabelas temporárias vazias antes deste arquivo.
-- Sem nome nem CPF: só CNPJ, critérios e pontos.

CREATE TABLE IF NOT EXISTS lead_peso (
    criterio    TEXT PRIMARY KEY,
    pontos      INT NOT NULL,
    descricao   TEXT
);
INSERT INTO lead_peso (criterio, pontos, descricao) VALUES
    ('porte_epp', 10, 'Empresa de pequeno porte'),
    ('porte_demais', 15, 'Porte acima de EPP'),
    ('nao_mei', 5, 'Não é MEI'),
    ('idade_2a', 10, 'Ativa há 2 anos ou mais'),
    ('ponto_comercial', 10, 'Endereço comercial ou misto, fora de domiciliação'),
    ('rede', 10, 'Mais de um CNPJ ativo da mesma raiz em Curitiba'),
    ('fornecedor_publico', 15, 'Contrato no PNCP, TCE-PR ou prefeitura'),
    ('lista_exportadora', 10, 'Exportadora ou importadora (MDIC)'),
    ('lista_credito', 10, 'Crédito do BNDES'),
    ('lista_outras', 5, 'Em outra lista pública (CADASTUR, CNES, SIF, ANP, ANATEL, IBAMA, IAT, e-MEC)'),
    ('alvara_ok', 5, 'Alvará casado e não vencido'),
    ('hexagono_crescendo', 5, 'Hexágono com mais aberturas que fechamentos nos últimos 12 meses'),
    ('risco_baixo', 10, 'Risco de fechamento abaixo da mediana da divisão'),
    ('divida_pgfn', -10, 'Inscrição em dívida ativa da União'),
    ('sancao', -30, 'Sanção federal ativa')
ON CONFLICT (criterio) DO NOTHING;

CREATE TEMP TABLE _ref ON COMMIT DROP AS
SELECT greatest(max(data_inicio_atividade), max(data_situacao_cadastral)) AS d FROM empresa;

CREATE TEMP TABLE _hex ON COMMIT DROP AS
SELECT g.h3_9,
       count(*) FILTER (WHERE e.data_inicio_atividade > r.d - INTERVAL '12 months')
       - count(*) FILTER (WHERE e.situacao_cadastral <> '02' AND e.data_situacao_cadastral > r.d - INTERVAL '12 months') AS saldo
FROM empresa e JOIN empresa_geo g USING (cnpj) CROSS JOIN _ref r
WHERE g.h3_9 IS NOT NULL
GROUP BY 1;

CREATE TEMP TABLE _crit ON COMMIT DROP AS
WITH base AS (
    SELECT e.cnpj, e.porte_empresa, e.opcao_mei, e.data_inicio_atividade, left(e.cnae_fiscal_principal, 2) AS divisao,
           to_jsonb(p) AS p, to_jsonb(s) AS s, to_jsonb(a) AS a, c.cnpj IS NOT NULL AS pmc,
           h.saldo, rk.risco_12m,
           (SELECT array_agg(l.lista) FROM empresa_lista l WHERE l.cnpj = e.cnpj) AS listas
    FROM empresa e
    LEFT JOIN empresa_perfil p USING (cnpj)
    LEFT JOIN empresa_sinais s USING (cnpj)
    LEFT JOIN empresa_alvara a USING (cnpj)
    LEFT JOIN empresa_contratos_pmc c USING (cnpj)
    LEFT JOIN empresa_geo g USING (cnpj)
    LEFT JOIN _hex h USING (h3_9)
    LEFT JOIN empresa_risco rk USING (cnpj)
    WHERE e.situacao_cadastral = '02'
), med AS (
    SELECT divisao, percentile_cont(0.5) WITHIN GROUP (ORDER BY risco_12m) AS mediana
    FROM base WHERE risco_12m IS NOT NULL GROUP BY 1
)
SELECT b.cnpj, x.criterio
FROM base b
LEFT JOIN med m USING (divisao)
CROSS JOIN _ref r
CROSS JOIN LATERAL (VALUES
    ('porte_epp', b.porte_empresa = '03'),
    ('porte_demais', b.porte_empresa = '05'),
    ('nao_mei', coalesce(b.opcao_mei, 'N') <> 'S'),
    ('idade_2a', b.data_inicio_atividade <= r.d - INTERVAL '2 years'),
    ('ponto_comercial', b.p ->> 'tipo_ponto' IN ('comercial', 'misto') AND NOT coalesce((b.p ->> 'domiciliacao')::BOOLEAN, false)),
    ('rede', coalesce((b.p ->> 'ativos_da_raiz_na_cidade')::INT, 0) > 1),
    ('fornecedor_publico', b.pmc OR coalesce((b.s ->> 'pncp_contratos')::INT, 0) > 0
                           OR coalesce((b.s ->> 'tce_pr_contratos')::INT, 0) > 0),
    ('lista_exportadora', 'mdic_exportadoras' = ANY(b.listas)),
    ('lista_credito', 'bndes_operacoes' = ANY(b.listas)),
    ('lista_outras', b.listas && ARRAY['cadastur', 'cnes', 'mapa_sif', 'anp_revendas', 'anatel_scm', 'ibama_ctf',
                                       'iat_licencas', 'emec']),
    ('alvara_ok', coalesce((b.a ->> 'tem_alvara')::BOOLEAN, false) AND NOT coalesce((b.a ->> 'alvara_vencido')::BOOLEAN, false)),
    ('hexagono_crescendo', b.saldo > 0),
    ('risco_baixo', b.risco_12m < m.mediana),
    ('divida_pgfn', coalesce((b.s ->> 'pgfn_inscricoes')::INT, 0) > 0),
    ('sancao', coalesce((b.s ->> 'sancoes_ativas')::INT, 0) > 0)
) x(criterio, ok)
WHERE x.ok;

DROP TABLE IF EXISTS empresa_lead;
CREATE TABLE empresa_lead AS
SELECT e.cnpj,
       greatest(0, least(100, coalesce(sum(w.pontos), 0)))::INT AS score,
       coalesce(array_agg(c.criterio ORDER BY w.pontos DESC, c.criterio) FILTER (WHERE c.criterio IS NOT NULL), '{}') AS criterios,
       rk.risco_12m
FROM empresa e
LEFT JOIN _crit c USING (cnpj)
LEFT JOIN lead_peso w USING (criterio)
LEFT JOIN empresa_risco rk USING (cnpj)
WHERE e.situacao_cadastral = '02'
GROUP BY e.cnpj, rk.risco_12m;
ALTER TABLE empresa_lead ADD PRIMARY KEY (cnpj);
CREATE INDEX ON empresa_lead (score DESC);
