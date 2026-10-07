-- Cruzamento alvará x CNPJ e sinais. Quem chama (etl/fontes/pmc_alvaras.py) deixa na sessão a tabela
-- temporária alvara_nome (numero_alvara, nome_chave) com o nome empresarial normalizado, que nunca vai
-- para tabela permanente.
--
-- Candidatos: empresa no mesmo CEP + logradouro + número (mesmo_endereco) ou, sem número que bata, na
-- mesma rua do mesmo CEP (mesma_rua). Pontuação de 0 a 1:
--   0,5 x similaridade de nome (melhor par entre nome empresarial/fantasia do alvará e razão social/fantasia
--         da empresa; a razão social de pessoa física é nula, então MEI casa por fantasia, CNAE e data)
--   0,25 se o CNAE principal é igual
--   0,25 se a data de início de atividade é igual
-- Na mesma rua (sem número igual) a pontuação é multiplicada por 0,8.
-- Aceita a partir de 0,5. Cada alvará fica com o melhor CNPJ e cada CNPJ com o melhor alvará.

TRUNCATE alvara_cnpj;

-- sem o enriquecimento rodado, os sinais saem sem tipo de ponto nem domiciliação
CREATE TABLE IF NOT EXISTS empresa_perfil (cnpj VARCHAR(14) PRIMARY KEY, tipo_ponto TEXT, domiciliacao BOOLEAN);

-- os dois lados normalizados uma vez só, em tabelas com índice (em CTE o planejador chamaria as funções de
-- normalização a cada par comparado).
CREATE TEMP TABLE _alv ON COMMIT DROP AS
SELECT a.numero_alvara, a.cep, a.logr_chave, a.numero_int, n.nome_chave AS nome_emp,
       norm_nome(a.nome_fantasia) AS fantasia, a.cnae_principal, a.inicio_atividade
FROM alvara a LEFT JOIN alvara_nome n USING (numero_alvara)
WHERE a.cep IS NOT NULL AND a.logr_chave IS NOT NULL;
ANALYZE _alv;

CREATE TEMP TABLE _emp ON COMMIT DROP AS
SELECT e.cnpj, norm_cep(e.cep) AS cep, norm_logradouro(e.logradouro) AS logr_chave,
       norm_numero(e.numero) AS numero, norm_nome(e.razao_social) AS razao, norm_nome(e.nome_fantasia) AS fantasia,
       e.cnae_fiscal_principal AS cnae, e.data_inicio_atividade AS inicio
FROM empresa e;
CREATE INDEX ON _emp (cep, logr_chave);
ANALYZE _emp;

-- Só vira candidato o par que ainda pode chegar a 0,5: na mesma rua sem CNAE nem data iguais o máximo é
-- 0,5 x 1 x 0,8 = 0,4, então o par precisa do mesmo número, do mesmo CNAE ou da mesma data de início.
-- Corta a maior parte dos pares (todas as empresas da rua contra todos os alvarás da rua) sem mudar o resultado.
CREATE TEMP TABLE _cand ON COMMIT DROP AS
SELECT a.numero_alvara, e.cnpj,
       CASE WHEN a.numero_int IS NOT DISTINCT FROM e.numero AND a.numero_int IS NOT NULL
            THEN 'mesmo_endereco' ELSE 'mesma_rua' END AS metodo,
       greatest(coalesce(similarity(a.nome_emp, e.razao), 0), coalesce(similarity(a.nome_emp, e.fantasia), 0),
                coalesce(similarity(a.fantasia, e.razao), 0), coalesce(similarity(a.fantasia, e.fantasia), 0)) AS nome_sim,
       a.cnae_principal = e.cnae AS cnae_igual,
       a.inicio_atividade = e.inicio AS inicio_igual
FROM _alv a
JOIN _emp e ON e.cep = a.cep AND e.logr_chave = a.logr_chave
WHERE a.numero_int = e.numero OR a.cnae_principal = e.cnae OR a.inicio_atividade = e.inicio;

CREATE TEMP TABLE _pont ON COMMIT DROP AS
SELECT *, round(((0.5 * nome_sim + 0.25 * coalesce(cnae_igual, false)::INT + 0.25 * coalesce(inicio_igual, false)::INT)
                 * CASE WHEN metodo = 'mesmo_endereco' THEN 1 ELSE 0.8 END)::NUMERIC, 3) AS pontuacao
FROM _cand;
DELETE FROM _pont WHERE pontuacao < 0.5;

-- emparelhamento guloso: melhor par primeiro; cada alvará e cada CNPJ entram uma vez
INSERT INTO alvara_cnpj (numero_alvara, cnpj, metodo, pontuacao, nome_similaridade, cnae_igual, inicio_igual)
SELECT numero_alvara, cnpj, metodo, pontuacao, round(nome_sim::NUMERIC, 3), cnae_igual, inicio_igual
FROM (
    SELECT p.*,
           row_number() OVER (PARTITION BY numero_alvara ORDER BY pontuacao DESC, cnpj) AS r_alv,
           row_number() OVER (PARTITION BY cnpj ORDER BY pontuacao DESC, numero_alvara) AS r_cnpj
    FROM _pont p
) x
WHERE r_alv = 1 AND r_cnpj = 1;

-- sinais por empresa ----------------------------------------------------------------

DROP TABLE IF EXISTS empresa_alvara;
CREATE TABLE empresa_alvara AS
SELECT e.cnpj,
       ac.numero_alvara,
       ac.numero_alvara IS NOT NULL AS tem_alvara,
       -- ativa, em ponto comercial ou misto, fora de domiciliação e sem alvará casado
       e.situacao_cadastral = '02' AND ac.numero_alvara IS NULL
           AND coalesce(p.tipo_ponto, 'desconhecido') IN ('comercial', 'misto')
           AND NOT coalesce(p.domiciliacao, false) AS ativa_sem_alvara,
       e.situacao_cadastral <> '02' AND ac.numero_alvara IS NOT NULL AS alvara_de_cnpj_encerrado,
       a.data_expiracao < current_date AS alvara_vencido,
       left(a.cnae_principal, 5) IS DISTINCT FROM left(e.cnae_fiscal_principal, 5)
           AND ac.numero_alvara IS NOT NULL AS atividade_diverge,
       a.cnae_principal AS cnae_alvara,
       -- alvará posterior à abertura do CNPJ: data em que a empresa chegou ao endereço atual
       CASE WHEN a.inicio_atividade > e.data_inicio_atividade THEN a.inicio_atividade END AS chegada_ao_endereco
FROM empresa e
LEFT JOIN alvara_cnpj ac USING (cnpj)
LEFT JOIN alvara a USING (numero_alvara)
LEFT JOIN empresa_perfil p USING (cnpj);
ALTER TABLE empresa_alvara ADD PRIMARY KEY (cnpj);

CREATE OR REPLACE VIEW alvara_sem_cnpj AS
SELECT a.*
FROM alvara a
WHERE NOT EXISTS (SELECT 1 FROM alvara_cnpj ac WHERE ac.numero_alvara = a.numero_alvara);
