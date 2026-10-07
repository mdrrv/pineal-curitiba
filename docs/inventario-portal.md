# Inventário do Portal de Dados Abertos de Curitiba (7 de outubro de 2026)

Gerado por `python -m etl.fontes.portal_inventario`. Rode de novo para atualizar; a versão de trabalho fica em `relatorios/`.

| base | frequência | última atualização | extensões | arquivos | CNPJ | endereço | coordenada |
|---|---|---|---|---:|:-:|:-:|:-:|
| Base de Alvarás (`pmc_alvaras`) | Mensal | 01/10/2026 05:19:00 | csv | 20 |  | ✔ |  |
| Licitações e Contratações (`pmc_licitacoes`) | Mensal | 01/10/2026 06:00:00 | csv | 69 | ✔ | ✔ |  |
| Licitações e Contratações COVID-19 (`pmc_licitacoes_covid`) | Mensal | 01/10/2026 06:00:00 | csv | 69 | ✔ | ✔ |  |
| Base de receitas e despesas (`pmc_receitas_despesas`) | Mensal | 01/10/2026 06:00:00 | csv | 47 |  |  |  |
| Saldos Orçamentarios (`pmc_saldos_orcamentarios`) | Mensal | 01/10/2026 00:00:00 | csv | 25 |  |  |  |
| Sistema Integrado de Atendimento ao Cidadão - SIAC 156 (`pmc_siac156`) | Diário | 05/10/2026 23:30:00 | csv | 635 |  | ✔ |  |
| pmc_sigmu | erro: 504 Server Error: Gateway Time-out for url: https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe?chave=236fb6f7-f2a0-4b04-99b3-5be5eb34672d | | | | | | |
| SiGesGuarda (`pmc_sigesguarda`) | Mensal | 01/10/2026 05:00:00 | csv | 28 |  | ✔ |  |
| Unidades de Atendimento de Curitiba - Ativas (`pmc_unidades`) | Mensal | 30/09/2026 13:23:00 | csv | 24 |  | ✔ |  |
| Transporte Coletivo de Curitiba (`pmc_transporte`) | Tempo Real | 26/11/2024 15:09:00 |  | 0 |  |  |  |
| Sistema E-Saude - Perfil de atendimento Médico nas Unidades Municipais de Saúde de Curitiba (`pmc_esaude_medico`) | Mensal | 06/09/2026 08:00:00 | csv | 24 |  | ✔ |  |
| Sistema E-Saude - Perfil de atendimento de Enfermagem nas Unidades Municipais de Saúde de Curitiba (`pmc_esaude_enfermagem`) | Mensal | 06/09/2026 08:00:00 | csv | 25 |  | ✔ |  |
| Sistema E-Saude - Perfil de atendimento Odontológico nas Unidades Municipais de Saúde de Curitiba (`pmc_esaude_odonto`) | Mensal | 06/09/2026 08:00:00 | csv | 24 |  | ✔ |  |
| Sistema E-Saude - Perfil de atendimento outros profissionais de Nível Superior nas Unidades Municipa (`pmc_esaude_outros`) | Mensal | 06/09/2026 08:00:00 | csv | 24 |  | ✔ |  |
| Casos de Dengue em Curitiba (`pmc_dengue`) | Mensal | 02/09/2026 07:00:00 | csv | 42 |  | ✔ |  |
| Clique Economia (`pmc_clique_economia`) | Diário | 05/10/2026 17:00:00 | csv | 486 |  | ✔ |  |
| Eventos PMC (`pmc_eventos`) | Diário | 06/10/2026 01:05:00 | csv | 534 |  | ✔ |  |
| Portal FCC (`pmc_fcc`) | Mensal | 01/10/2026 00:00:00 | csv | 299 |  | ✔ |  |
| Fala Curitiba (`pmc_fala_curitiba`) | Trimestral | 01/10/2026 11:21:00 | csv | 8 |  |  |  |

## Base de Alvarás (`pmc_alvaras`)

- Última atualização: 01/10/2026 05:19:00
- Secretaria: SMF
- Responsável: Evelize Andrade D. Tarasiuk
- Frequência de atualização: Mensal
- Espectro temporal: Alvarás ativos até a data da Extração
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/BaseAlvaras/

### .csv: 20 arquivos, mais recente `2026-10-01_Alvaras_-_Base_de_Dados.csv` (543,61 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/BaseAlvaras/2026-10-01_Alvaras_-_Dicionario_de_Dados.csv

Colunas para cruzar: **endereco**: NUMERO_DO_ALVARA, ENDERECO, NUMERO, BAIRRO, CEP; **data**: INICIO_ATIVIDADE, DATA_EMISSAO, DATA_EXPIRACAO

Colunas: `NOME_EMPRESARIAL`, `INICIO_ATIVIDADE`, `NUMERO_DO_ALVARA`, `NOME_FANTASIA`, `DATA_EMISSAO`, `DATA_EXPIRACAO`, `ENDERECO`, `NUMERO`, `UNIDADE`, `ANDAR`, `COMPLEMENTO`, `BAIRRO`, `CEP`, `CNAE_ATIVIDADE_PRINCIPAL`, `ATIVIDADE_PRINCIPAL`, `CNAE_ATIVIDADE_SECUNDARIA01`, `ATIVIDADE_SECUNDARIA01`, `CNAE_ATIVIDADE_SECUNDARIA02`, `ATIVIDADE_SECUNDARIA02`, `CNAE_ATIVIDADE_SECUNDARIA03`, `ATIVIDADE_SECUNDARIA03`, `CNAE_ATIVIDADE_SECUNDARIA04`, `ATIVIDADE_SECUNDARIA04`, `CNAE_ATIVIDADE_SECUNDARIA05`, `ATIVIDADE_SECUNDARIA05`, `CNAE_ATIVIDADE_SECUNDARIA06`, `ATIVIDADE_SECUNDARIA06`, `CNAE_ATIVIDADE_SECUNDARIA07`, `ATIVIDADE_SECUNDARIA07`, `CNAE_ATIVIDADE_SECUNDARIA08`, `ATIVIDADE_SECUNDARIA08`, `CNAE_ATIVIDADE_SECUNDARIA09`, `ATIVIDADE_SECUNDARIA09`, `CNAE_ATIVIDADE_SECUNDARIA10`, `ATIVIDADE_SECUNDARIA10`, `CNAE_ATIVIDADE_SECUNDARIA11`, `ATIVIDADE_SECUNDARIA11`, `CNAE_ATIVIDADE_SECUNDARIA12`, `ATIVIDADE_SECUNDARIA12`, `CNAE_ATIVIDADE_SECUNDARIA13`, `ATIVIDADE_SECUNDARIA13`, `CNAE_ATIVIDADE_SECUNDARIA14`, `ATIVIDADE_SECUNDARIA14`, `CNAE_ATIVIDADE_SECUNDARIA15`, `ATIVIDADE_SECUNDARIA15`, `CNAE_ATIVIDADE_SECUNDARIA16`, `ATIVIDADE_SECUNDARIA16`, `CNAE_ATIVIDADE_SECUNDARIA17`, `ATIVIDADE_SECUNDARIA17`, `CNAE_ATIVIDADE_SECUNDARIA18`, `ATIVIDADE_SECUNDARIA18`, `CNAE_ATIVIDADE_SECUNDARIA19`, `ATIVIDADE_SECUNDARIA19`, `CNAE_ATIVIDADE_SECUNDARIA20`, `ATIVIDADE_SECUNDARIA20`, `CNAE_ATIVIDADE_SECUNDARIA21`, `ATIVIDADE_SECUNDARIA21`, `CNAE_ATIVIDADE_SECUNDARIA22`, `ATIVIDADE_SECUNDARIA22`, `CNAE_ATIVIDADE_SECUNDARIA23`, `ATIVIDADE_SECUNDARIA23`, `CNAE_ATIVIDADE_SECUNDARIA24`, `ATIVIDADE_SECUNDARIA24`, `CNAE_ATIVIDADE_SECUNDARIA25`, `ATIVIDADE_SECUNDARIA25`, `CNAE_ATIVIDADE_SECUNDARIA26`, `ATIVIDADE_SECUNDARIA26`, `CNAE_ATIVIDADE_SECUNDARIA27`, `ATIVIDADE_SECUNDARIA27`, `CNAE_ATIVIDADE_SECUNDARIA28`, `ATIVIDADE_SECUNDARIA28`, `CNAE_ATIVIDADE_SECUNDARIA29`, `ATIVIDADE_SECUNDARIA29`, `CNAE_ATIVIDADE_SECUNDARIA30`, `ATIVIDADE_SECUNDARIA30`, `CNAE_ATIVIDADE_SECUNDARIA31`, `ATIVIDADE_SECUNDARIA31`, `CNAE_ATIVIDADE_SECUNDARIA32`, `ATIVIDADE_SECUNDARIA32`, `CNAE_ATIVIDADE_SECUNDARIA33`, `ATIVIDADE_SECUNDARIA33`, `CNAE_ATIVIDADE_SECUNDARIA34`, `ATIVIDADE_SECUNDARIA34`, `CNAE_ATIVIDADE_SECUNDARIA35`, `ATIVIDADE_SECUNDARIA35`, `CNAE_ATIVIDADE_SECUNDARIA36`, `ATIVIDADE_SECUNDARIA36`, `CNAE_ATIVIDADE_SECUNDARIA37`, `ATIVIDADE_SECUNDARIA37`, `CNAE_ATIVIDADE_SECUNDARIA38`, `ATIVIDADE_SECUNDARIA38`, `CNAE_ATIVIDADE_SECUNDARIA39`, `ATIVIDADE_SECUNDARIA39`, `CNAE_ATIVIDADE_SECUNDARIA40`, `ATIVIDADE_SECUNDARIA40`, `CNAE_ATIVIDADE_SECUNDARIA41`, `ATIVIDADE_SECUNDARIA41`, `CNAE_ATIVIDADE_SECUNDARIA42`, `ATIVIDADE_SECUNDARIA42`, `CNAE_ATIVIDADE_SECUNDARIA43`, `ATIVIDADE_SECUNDARIA43`, `CNAE_ATIVIDADE_SECUNDARIA44`, `ATIVIDADE_SECUNDARIA44`, `CNAE_ATIVIDADE_SECUNDARIA45`, `ATIVIDADE_SECUNDARIA45`, `CNAE_ATIVIDADE_SECUNDARIA46`, `ATIVIDADE_SECUNDARIA46`, `CNAE_ATIVIDADE_SECUNDARIA47`, `ATIVIDADE_SECUNDARIA47`, `CNAE_ATIVIDADE_SECUNDARIA48`, `ATIVIDADE_SECUNDARIA48`, `CNAE_ATIVIDADE_SECUNDARIA49`, `ATIVIDADE_SECUNDARIA49`, `CNAE_ATIVIDADE_SECUNDARIA50`, `ATIVIDADE_SECUNDARIA50`, `CNAE_ATIVIDADE_SECUNDARIA51`, `ATIVIDADE_SECUNDARIA51`, `CNAE_ATIVIDADE_SECUNDARIA52`, `ATIVIDADE_SECUNDARIA52`, `CNAE_ATIVIDADE_SECUNDARIA53`, `ATIVIDADE_SECUNDARIA53`, `CNAE_ATIVIDADE_SECUNDARIA54`, `ATIVIDADE_SECUNDARIA54`, `CNAE_ATIVIDADE_SECUNDARIA55`, `ATIVIDADE_SECUNDARIA55`, `CNAE_ATIVIDADE_SECUNDARIA56`, `ATIVIDADE_SECUNDARIA56`, `CNAE_ATIVIDADE_SECUNDARIA57`, `ATIVIDADE_SECUNDARIA57`, `CNAE_ATIVIDADE_SECUNDARIA58`, `ATIVIDADE_SECUNDARIA58`, `CNAE_ATIVIDADE_SECUNDARIA59`, `ATIVIDADE_SECUNDARIA59`, `CNAE_ATIVIDADE_SECUNDARIA60`, `ATIVIDADE_SECUNDARIA60`, `CNAE_ATIVIDADE_SECUNDARIA61`, `ATIVIDADE_SECUNDARIA61`, `CNAE_ATIVIDADE_SECUNDARIA62`, `ATIVIDADE_SECUNDARIA62`, `CNAE_ATIVIDADE_SECUNDARIA63`, `ATIVIDADE_SECUNDARIA63`, `CNAE_ATIVIDADE_SECUNDARIA64`, `ATIVIDADE_SECUNDARIA64`, `CNAE_ATIVIDADE_SECUNDARIA65`, `ATIVIDADE_SECUNDARIA65`, `CNAE_ATIVIDADE_SECUNDARIA66`, `ATIVIDADE_SECUNDARIA66`, `CNAE_ATIVIDADE_SECUNDARIA67`, `ATIVIDADE_SECUNDARIA67`, `CNAE_ATIVIDADE_SECUNDARIA68`, `ATIVIDADE_SECUNDARIA68`, `CNAE_ATIVIDADE_SECUNDARIA69`, `ATIVIDADE_SECUNDARIA69`, `CNAE_ATIVIDADE_SECUNDARIA70`, `ATIVIDADE_SECUNDARIA70`, `CNAE_ATIVIDADE_SECUNDARIA71`, `ATIVIDADE_SECUNDARIA71`, `CNAE_ATIVIDADE_SECUNDARIA72`, `ATIVIDADE_SECUNDARIA72`, `CNAE_ATIVIDADE_SECUNDARIA73`, `ATIVIDADE_SECUNDARIA73`, `CNAE_ATIVIDADE_SECUNDARIA74`, `ATIVIDADE_SECUNDARIA74`, `CNAE_ATIVIDADE_SECUNDARIA75`, `ATIVIDADE_SECUNDARIA75`, `CNAE_ATIVIDADE_SECUNDARIA76`, `ATIVIDADE_SECUNDARIA76`, `CNAE_ATIVIDADE_SECUNDARIA77`, `ATIVIDADE_SECUNDARIA77`, `CNAE_ATIVIDADE_SECUNDARIA78`, `ATIVIDADE_SECUNDARIA78`, `CNAE_ATIVIDADE_SECUNDARIA79`, `ATIVIDADE_SECUNDARIA79`, `CNAE_ATIVIDADE_SECUNDARIA80`, `ATIVIDADE_SECUNDARIA80`, `CNAE_ATIVIDADE_SECUNDARIA81`, `ATIVIDADE_SECUNDARIA81`, `CNAE_ATIVIDADE_SECUNDARIA82`, `ATIVIDADE_SECUNDARIA82`, `CNAE_ATIVIDADE_SECUNDARIA83`, `ATIVIDADE_SECUNDARIA83`, `CNAE_ATIVIDADE_SECUNDARIA84`, `ATIVIDADE_SECUNDARIA84`, `CNAE_ATIVIDADE_SECUNDARIA85`, `ATIVIDADE_SECUNDARIA85`, `CNAE_ATIVIDADE_SECUNDARIA86`, `ATIVIDADE_SECUNDARIA86`, `CNAE_ATIVIDADE_SECUNDARIA87`, `ATIVIDADE_SECUNDARIA87`, `CNAE_ATIVIDADE_SECUNDARIA88`, `ATIVIDADE_SECUNDARIA88`, `CNAE_ATIVIDADE_SECUNDARIA89`, `ATIVIDADE_SECUNDARIA89`, `CNAE_ATIVIDADE_SECUNDARIA90`, `ATIVIDADE_SECUNDARIA90`, `CNAE_ATIVIDADE_SECUNDARIA91`, `ATIVIDADE_SECUNDARIA91`, `CNAE_ATIVIDADE_SECUNDARIA92`, `ATIVIDADE_SECUNDARIA92`, `CNAE_ATIVIDADE_SECUNDARIA93`, `ATIVIDADE_SECUNDARIA93`, `CNAE_ATIVIDADE_SECUNDARIA94`, `ATIVIDADE_SECUNDARIA94`, `CNAE_ATIVIDADE_SECUNDARIA95`, `ATIVIDADE_SECUNDARIA95`, `CNAE_ATIVIDADE_SECUNDARIA96`, `ATIVIDADE_SECUNDARIA96`, `CNAE_ATIVIDADE_SECUNDARIA97`, `ATIVIDADE_SECUNDARIA97`, `CNAE_ATIVIDADE_SECUNDARIA98`, `ATIVIDADE_SECUNDARIA98`, `CNAE_ATIVIDADE_SECUNDARIA99`, `ATIVIDADE_SECUNDARIA99`

## Licitações e Contratações (`pmc_licitacoes`)

- Última atualização: 01/10/2026 06:00:00
- Secretaria: SMATI
- Responsável: Paulo Cesar Bozza
- Frequência de atualização: Mensal
- Espectro temporal: Últimos 5 anos
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/LicitacoesContratacoes

### .csv: 69 arquivos, mais recente `2026-10-01_Licitacoes_Contratacoes_Itens_Processo_-_Base_de_Dados.csv` (12,84 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/LicitacoesContratacoes/2026-10-01_Licitacoes_Contratacoes_Itens_Processo_-_Dicionario_de_Dados.csv

Colunas para cruzar: **cnpj**: CNPJ/CPF; **cpf**: CNPJ/CPF; **endereco**: Número do Processo, Número do Contrato; **data**: Inicio da Vigência do Contrato

Colunas: `Órgão`, `Número do Processo`, `Modalidade`, `Item`, `Quantidade`, `Unidade de Medida`, `Contratato/Fornecedor`, `CNPJ/CPF`, `Número do Contrato`, `Inicio da Vigência do Contrato`, `Fim da Vigência do Contrato`, `Valor Unitário`, `Valor Total/Global`

## Licitações e Contratações COVID-19 (`pmc_licitacoes_covid`)

- Última atualização: 01/10/2026 06:00:00
- Secretaria: SMATI
- Responsável: Paulo Cesar Bozza
- Frequência de atualização: Mensal
- Espectro temporal: Últimos 5 anos
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/LicitacoesContratacoesCovid19

### .csv: 69 arquivos, mais recente `2026-10-01_Licitacoes_Contratacoes_Covid_Itens_Processo_-_Base_de_Dados.csv` (391,47 KB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/LicitacoesContratacoesCovid19/2026-10-01_Licitacoes_Contratacoes_Covid_Itens_Processo_-_Dicionario_de_Dados.csv

Colunas para cruzar: **cnpj**: CNPJ/CPF; **cpf**: CNPJ/CPF; **endereco**: Número do Processo, Número do Contrato; **data**: Inicio da Vigência do Contrato

Colunas: `Órgão`, `Número do Processo`, `Modalidade`, `Item`, `Quantidade`, `Unidade de Medida`, `Contratato/Fornecedor`, `CNPJ/CPF`, `Número do Contrato`, `Inicio da Vigência do Contrato`, `Fim da Vigência do Contrato`, `Valor Unitário`, `Valor Total/Global`

## Base de receitas e despesas (`pmc_receitas_despesas`)

- Última atualização: 01/10/2026 06:00:00
- Secretaria: SMF
- Responsável: Carlos Eduardo Kukolj
- Frequência de atualização: Mensal
- Espectro temporal: Últimos três meses
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/BaseReceitaDespesa/

### .csv: 47 arquivos, mais recente `2026-10-01_Receitas_-_Base_de_Dados.csv` (19,74 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/BaseReceitaDespesa/2024-11-26_Receitas_-_Dicionario_de_Dados.xlsx

Colunas para cruzar: **data**: DT_APROPRIACAO

Colunas: `CD_RECEITA`, `CD_CATEGORIA`, `DESCRICAO_CATEGORIA`, `CD_ORIGEM`, `DESCRICAO_ORIGEM`, `CD_ESPECIE`, `DESCRICAO_ESPECIE`, `CD_RUBRICA`, `DESCRICAO_RUBRICA`, `CD_ALINEA`, `DESCRICAO_ALINEA`, `CD_SUBALINEA`, `DESCRICAO_SUBALINEA`, `CD_EXERCICIO`, `DT_APROPRIACAO`, `TP_RECEITA_ORC`, `CD_EMPRESA`, `NM_EMPRESA`, `VL_RECEITA`, `DS_FONTE`

## Saldos Orçamentarios (`pmc_saldos_orcamentarios`)

- Última atualização: 01/10/2026 00:00:00
- Secretaria: SMF
- Responsável: Carlos Eduardo Kukolj
- Frequência de atualização: Mensal
- Espectro temporal: Últimos três meses
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/SaldosOrcamentarios/

### .csv: 25 arquivos, mais recente `2026-10-01_Saldos_Orcamentarios_-_Base_de_Dados.csv` (5,3 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/SaldosOrcamentarios/2025-06-18_Saldos_Orcamentarios_-_Dicionario_de_Dados.xlsx

Colunas para cruzar: **data**: ANO_DOTACAO, DATA

Colunas: `ANO_DOTACAO`, `EMPRESA`, `SIGLA_EMPRESA`, `CD_ORGAO`, `DS_ORGAO`, `SIGLA_ORGAO`, `CD_UNIDADE`, `DS_UNIDADE`, `SIGLA_UNIDADE`, `CD_FUNCAO`, `DS_FUNCAO`, `CD_SUBFUNCAO`, `DS_SUBFUNCAO`, `CD_PROGRAMA`, `DS_PROGRAMA`, `CD_ACAO`, `DS_ACAO`, `CD_CATEGORIA_DESPESA`, `DS_CATEGORIA_DESPESA`, `CD_MODALIDADE_DESPESA`, `DS_MODALIDADE_DESPESA`, `CD_GRUPO_DESPESA`, `DS_GRUPO_DESPESA`, `CD_ELEMENTO_DESPESA`, `DS_ELEMENTO_DESPESA`, `CD_DESPESA`, `DS_DESPESA`, `CD_FONTE`, `DS_FONTE`, `DATA`, `ORCADO_INICIAL`, `ORCADO_ATUALIZADO`, `VL_EMPENHADO`, `VL_LIQUIDADO`, `VL_PAGO_DEVOLVIDO`, `VALOR_EMP_ANULADO`, `VL_PAGO`, `VL_CONSIGNADO`

## Sistema Integrado de Atendimento ao Cidadão - SIAC 156 (`pmc_siac156`)

- Última atualização: 05/10/2026 23:30:00
- Secretaria: SGM
- Responsável: Leandro Fischer de Souza
- Frequência de atualização: Diário
- Espectro temporal: Ano corrente
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/156/

### .csv: 635 arquivos, mais recente `2026-10-05_156_-_Base_de_Dados.csv` (111,74 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/156/2024-11-26_156_-_Dicionario_de_Dados.xlsx

Colunas para cruzar: **endereco**: Logradouro, Bairro; **data**: DataCriacao, DataResposta

Colunas: `Tipo`, `Orgao`, `DataCriacao`, `Assunto`, `Subdivisao`, `Situacao`, `Logradouro`, `Bairro`, `Regional`, `DataResposta`, `Origem`, `Column1`

## SiGesGuarda (`pmc_sigesguarda`)

- Última atualização: 01/10/2026 05:00:00
- Secretaria: SMDT
- Responsável: CRISTIANO TOBLER
- Frequência de atualização: Mensal
- Espectro temporal: De 2023 até o momento da extração.
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/Sigesguarda/

### .csv: 28 arquivos, mais recente `2026-10-01_sigesguarda_-_Base_de_Dados.csv` (38,88 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/Sigesguarda/2024-11-26_sigesguarda_-_Dicionario_de_Dados.xlsx

Colunas para cruzar: **endereco**: ATENDIMENTO_BAIRRO_NOME, LOGRADOURO_NOME, NUMERO_PROTOCOLO_156; **data**: OCORRENCIA_DATA

Colunas: `ATENDIMENTO_BAIRRO_NOME`, `EQUIPAMENTO_URBANO_NOME`, `FLAG_EQUIPAMENTO_URBANO`, `FLAG_FLAGRANTE`, `LOGRADOURO_NOME`, `NATUREZA1_DEFESA_CIVIL`, `NATUREZA1_DESCRICAO`, `SUBCATEGORIA1_DESCRICAO`, `NATUREZA2_DEFESA_CIVIL`, `NATUREZA2_DESCRICAO`, `SUBCATEGORIA2_DESCRICAO`, `NATUREZA3_DEFESA_CIVIL`, `NATUREZA3_DESCRICAO`, `SUBCATEGORIA3_DESCRICAO`, `NATUREZA4_DEFESA_CIVIL`, `NATUREZA4_DESCRICAO`, `SUBCATEGORIA4_DESCRICAO`, `NATUREZA5_DEFESA_CIVIL`, `NATUREZA5_DESCRICAO`, `SUBCATEGORIA5_DESCRICAO`, `OCORRENCIA_ANO`, `OCORRENCIA_CODIGO`, `OCORRENCIA_DATA`, `OCORRENCIA_DIA_SEMANA`, `OCORRENCIA_HORA`, `OCORRENCIA_MES`, `OPERACAO_DESCRICAO`, `ORIGEM_CHAMADO_DESCRICAO`, `REGIONAL_FATO_NOME`, `SECRETARIA_NOME`, `SECRETARIA_SIGLA`, `SERVICO_NOME`, `SITUACAO_EQUIPE_DESCRICAO`, `NUMERO_PROTOCOLO_156`

## Unidades de Atendimento de Curitiba - Ativas (`pmc_unidades`)

- Última atualização: 30/09/2026 13:23:00
- Secretaria: IPPUC
- Responsável: Klaus Landgraf
- Frequência de atualização: Mensal
- Espectro temporal: Mesmo mês da extração
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/UnidadesAtendimentoCuritiba/

### .csv: 24 arquivos, mais recente `2026-09-30_Unidades12_Atendimento_Ativas_Curitiba_-_Base_de_Dados.csv` (2,32 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/UnidadesAtendimentoCuritiba/2024-11-26_Unidades12_Atendimento_Ativas_Curitiba_-_Dicionario_de_Dados.xls

Colunas para cruzar: **endereco**: NUMERO_EQUI, CD_BAIRRO, NM_BAIRRO

Colunas: `CD_EQUI`, `CD_LOCAL`, `CD_TEMA`, `DS_TEMA`, `CD_TP_EQUIPAMENTO`, `DS_TP_EQUIPAMENTO`, `CD_SUBTIPO_EQUIPAMENTO`, `DS_SUBTIPO_EQUIPAMENTO`, `CD_DEP_ADMINISTRATIVA`, `DS_DEP_ADMINISTRATIVA`, `NM_EQUI`, `NM_ABREV_EQUI`, `CD_FONTE`, `FONTE_FONTE`, `FUNCIONAMENTO_MANHA_EQUI`, `FUNCIONAMENTO_TARDE_EQUI`, `FUNCIONAMENTO_NOITE_EQUI`, `FUNCIONAMENTO_24HRS_EQUI`, `CD_RUA`, `NM_RUA`, `CD_RUANAOOFICIAL`, `NM_RUANAOOFICIAL`, `NUMERO_EQUI`, `COMPLEMENTO_EQUI`, `CD_BAIRRO`, `NM_BAIRRO`, `QUADRICULA_BQ`, `CD_REGIONAL`, `NM_REGIONAL`, `TELEFONE_EQUI`, `RAMAL_EQUI`, `EMAIL_EQUI`, `SITE_EQUI`, `FAX_EQUI`

## Transporte Coletivo de Curitiba (`pmc_transporte`)

- Última atualização: 26/11/2024 15:09:00
- Secretaria: URBS
- Responsável: Lucineide Vilar Possebom Wieczorkovski
- Frequência de atualização: Tempo Real
- Espectro temporal: De 2012 até o momento da extração
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitibaurbs/

## Sistema E-Saude - Perfil de atendimento Médico nas Unidades Municipais de Saúde de Curitiba (`pmc_esaude_medico`)

- Última atualização: 06/09/2026 08:00:00
- Secretaria: SMS
- Responsável: Leandro Carlos da Silva
- Frequência de atualização: Mensal
- Espectro temporal: Últimos 3 meses
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/SESPAMedicoUnidadesMunicipaisDeSaude/

### .csv: 24 arquivos, mais recente `2026-09-06_Sistema_E-Saude_Medicos_-_Base_de_Dados.csv` (475,81 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/SESPAMedicoUnidadesMunicipaisDeSaude/2024-11-26_Sistema_E-Saude_Medicos_-_Dicionario_de_Dados.csv

Colunas para cruzar: **endereco**: Bairro; **data**: Data do Atendimento, Data de Nascimento, Data do Internamento

Colunas: `Data do Atendimento`, `Data de Nascimento`, `Sexo`, `Código do Tipo de Unidade`, `Tipo de Unidade`, `Código da Unidade`, `Descrição da Unidade`, `Código do Procedimento`, `Descrição do Procedimento`, `Código do CBO`, `Descrição do CBO`, `Código do CID`, `Descrição do CID`, `Solicitação de Exames`, `Qtde Prescrita Farmácia Curitibana`, `Qtde Dispensada Farmácia Curitibana`, `Qtde de Medicamento Não Padronizado`, `Encaminhamento para Atendimento Especialista`, `Área de Atuação`, `Desencadeou Internamento`, `Data do Internamento`, `Estabelecimento Solicitante`, `Estabelecimento Destino`, `CID do Internamento`, `Tratamento no Domicílio`, `Abastecimento`, `Energia Elétrica`, `Tipo de Habitação`, `Destino Lixo`, `Fezes/Urina`, `Cômodos`, `Em Caso de Doença`, `Grupo Comunitário`, `Meio de Comunicacao`, `Meio de Transporte`, `Municício`, `Bairro`, `Nacionalidade`, `cod_usuario`, `origem_usuario`, `residente`, `cod_profissional`

## Sistema E-Saude - Perfil de atendimento de Enfermagem nas Unidades Municipais de Saúde de Curitiba (`pmc_esaude_enfermagem`)

- Última atualização: 06/09/2026 08:00:00
- Secretaria: SMS
- Responsável: Leandro Carlos da Silva
- Frequência de atualização: Mensal
- Espectro temporal: Últimos 3 meses
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/SESPAEnfermagem/

### .csv: 25 arquivos, mais recente `2026-09-06_Sistema_E-Saude_Enfermagem_-_Base_de_Dados.csv` (471,97 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/sespaenfermagem/2024-11-26_Sistema_E-Saude_Enfermagem_-_Dicionario_de_Dados.csv

Colunas para cruzar: **endereco**: Bairro; **data**: Data do Atendimento, Data de Nascimento, Data do Internamento

Colunas: `Data do Atendimento`, `Data de Nascimento`, `Sexo`, `Código do Tipo de Unidade`, `Tipo de Unidade`, `Código da Unidade`, `Descrição da Unidade`, `Código do Procedimento`, `Descrição do Procedimento`, `Código do CBO`, `Descrição do CBO`, `Código do CID`, `Descrição do CID`, `Solicitação de Exames`, `Qtde Prescrita Farmácia Curitibana`, `Qtde Dispensada Farmácia Curitibana`, `Qtde de Medicamento Não Padronizado`, `Encaminhamento para Atendimento Especialista`, `Área de Atuação`, `Desencadeou Internamento`, `Data do Internamento`, `Estabelecimento Solicitante`, `Estabelecimento Destino`, `CID do Internamento`, `Tratamento no Domicílio`, `Abastecimento`, `Energia Elétrica`, `Tipo de Habitação`, `Destino Lixo`, `Fezes/Urina`, `Cômodos`, `Em Caso de Doença`, `Grupo Comunitário`, `Meio de Comunicacao`, `Meio de Transporte`, `Municício`, `Bairro`, `Nacionalidade`, `cod_usuario`, `origem_usuario`, `residente`, `cod_profissional`

## Sistema E-Saude - Perfil de atendimento Odontológico nas Unidades Municipais de Saúde de Curitiba (`pmc_esaude_odonto`)

- Última atualização: 06/09/2026 08:00:00
- Secretaria: SMS
- Responsável: Leandro Carlos da Silva
- Frequência de atualização: Mensal
- Espectro temporal: Últimos 3 meses
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/SESPAOdontologico/

### .csv: 24 arquivos, mais recente `2026-09-06_Sistema_E-Saude_Odontologico_-_Base_de_Dados.csv` (135,4 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/sespaodontologico/2024-11-26_Sistema_E-Saude_Odontologico_-_Dicionario_de_Dados.csv

Colunas para cruzar: **endereco**: Bairro; **data**: Data do Atendimento, Data de Nascimento, Data do Internamento

Colunas: `Data do Atendimento`, `Data de Nascimento`, `Sexo`, `Código do Tipo de Unidade`, `Tipo de Unidade`, `Código da Unidade`, `Descrição da Unidade`, `Código do Procedimento`, `Descrição do Procedimento`, `Código do CBO`, `Descrição do CBO`, `Código do CID`, `Descrição do CID`, `Solicitação de Exames`, `Qtde Prescrita Farmácia Curitibana`, `Qtde Dispensada Farmácia Curitibana`, `Qtde de Medicamento Não Padronizado`, `Encaminhamento para Atendimento Especialista`, `Área de Atuação`, `Desencadeou Internamento`, `Data do Internamento`, `Estabelecimento Solicitante`, `Estabelecimento Destino`, `CID do Internamento`, `Tratamento no Domicílio`, `Abastecimento`, `Energia Elétrica`, `Tipo de Habitação`, `Destino Lixo`, `Fezes/Urina`, `Cômodos`, `Em Caso de Doença`, `Grupo Comunitário`, `Meio de Comunicacao`, `Meio de Transporte`, `Municício`, `Bairro`, `Nacionalidade`, `cod_usuario`, `origem_usuario`, `residente`, `cod_profissional`

## Sistema E-Saude - Perfil de atendimento outros profissionais de Nível Superior nas Unidades Municipa (`pmc_esaude_outros`)

- Última atualização: 06/09/2026 08:00:00
- Secretaria: SMS
- Responsável: Leandro Carlos da Silva
- Frequência de atualização: Mensal
- Espectro temporal: Últimos 3 meses
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/SESPAOutrosProfissionaisDeNivelSuperior/

### .csv: 24 arquivos, mais recente `2026-09-06_Sistema_E-Saude_Outros_Niveis_Superior_-_Base_de_Dados.csv` (21,08 MB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/SESPAOutrosProfissionaisDeNivelSuperior/2024-11-26_Sistema_E-Saude_Outros_Niveis_Superior_-_Dicionario_de_Dados.csv

Colunas para cruzar: **endereco**: Bairro; **data**: Data do Atendimento, Data de Nascimento, Data do Internamento

Colunas: `Data do Atendimento`, `Data de Nascimento`, `Sexo`, `Código do Tipo de Unidade`, `Tipo de Unidade`, `Código da Unidade`, `Descrição da Unidade`, `Código do Procedimento`, `Descrição do Procedimento`, `Código do CBO`, `Descrição do CBO`, `Código do CID`, `Descrição do CID`, `Solicitação de Exames`, `Qtde Prescrita Farmácia Curitibana`, `Qtde Dispensada Farmácia Curitibana`, `Qtde de Medicamento Não Padronizado`, `Encaminhamento para Atendimento Especialista`, `Área de Atuação`, `Desencadeou Internamento`, `Data do Internamento`, `Estabelecimento Solicitante`, `Estabelecimento Destino`, `CID do Internamento`, `Tratamento no Domicílio`, `Abastecimento`, `Energia Elétrica`, `Tipo de Habitação`, `Destino Lixo`, `Fezes/Urina`, `Cômodos`, `Em Caso de Doença`, `Grupo Comunitário`, `Meio de Comunicacao`, `Meio de Transporte`, `Municício`, `Bairro`, `Nacionalidade`, `cod_usuario`, `origem_usuario`, `residente`, `cod_profissional`

## Casos de Dengue em Curitiba (`pmc_dengue`)

- Última atualização: 02/09/2026 07:00:00
- Secretaria: SMS
- Responsável: Alcides Augusto Souto de Oliveira
- Frequência de atualização: Mensal
- Espectro temporal: De 08/04/2024 até o momento da extração.
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/CasosDengue/

### .csv: 42 arquivos, mais recente `2026-09-02_Casos_Dengue_-_Base_de_Dados.csv` (148,22 KB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/CasosDengue/2024-11-26_Casos_Dengue_-_Dicionario_de_Dados.csv

Colunas para cruzar: **endereco**: BAIRRO DE RESIDÊNCIA; **data**: DATA DA NOTIFICAÇÃO, DATA DOS PRIMEIROS SINTOMAS

Colunas: `DATA DA NOTIFICAÇÃO`, `DATA DOS PRIMEIROS SINTOMAS`, `BAIRRO DE RESIDÊNCIA`, `SEXO`, `classificacao`, `IDADE (anos)`, `CRITÉRIO DE CONFIRMAÇÃO`, `LOCAL DE INFECÇÃO`, `EVOLUÇÃO`

## Clique Economia (`pmc_clique_economia`)

- Última atualização: 05/10/2026 17:00:00
- Responsável: Adriano Cardoso da Silva
- Frequência de atualização: Diário
- Espectro temporal: Diário
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/CliqueEconomia

### .csv: 486 arquivos, mais recente `2026-10-05_Clique_Economia_-_Cotacoes_-_Base_de_Dados.csv` (488 KB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/CliqueEconomia/2026-10-05_Clique_Economia_-_Cotacoes_-_Dicionario_de_Dados.csv

Colunas para cruzar: **endereco**: endereco_completo; **data**: data_pesquisa

Colunas: `data_pesquisa`, `id_empresa`, `rede`, `endereco_completo`, `codigo_categoria`, `id_produto`, `descricao`, `preco_regular`, `preco_atacado`, `preco_atacado_qtd`, `preco_promocao`, `preco_fidelidade`

## Eventos PMC (`pmc_eventos`)

- Última atualização: 06/10/2026 01:05:00
- Secretaria: SMCS
- Responsável: Elziane Cazura Xavier
- Frequência de atualização: Diário
- Espectro temporal: A partir de março de 2016.
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/AgendaPMC/

### .csv: 534 arquivos, mais recente `2026-10-06_Eventos_-_Base_de_Dados.csv` (817,71 KB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/agendapmc/2024-11-26_Eventos_-_Dicionario_de_dados.xlsx

Colunas para cruzar: **endereco**: EVE_ENDERECO; **data**: EVE_DATA_INICIO, EVE_DATA_TERMINO, EVE_DATA_CADASTRO

Colunas: `EVE_IDF`, `EVE_TITULO`, `EVE_DESCRICAO`, `EVE_PUBLICADO`, `EVE_DATA_INICIO`, `EVE_DATA_TERMINO`, `SEE_STR_NOME`, `EVE_DATA_CADASTRO`, `EVE_LOCAL`, `EVE_ENDERECO`, `EVE_HORARIO`, `EVE_REPETIR`, `EVE_DIA`, `BAI_DESCRICAO`, `ETE_DESCRICAO`, `ETI_DESCRICAO`, `REG_DESCRICAO`

## Portal FCC (`pmc_fcc`)

- Última atualização: 01/10/2026 00:00:00
- Secretaria: FCC
- Responsável: Rogerio Rabitto
- Frequência de atualização: Mensal
- Espectro temporal: Informações ativas
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/FundacaoCultural/

### .csv: 299 arquivos, mais recente `2026-10-01_Fundacao_Cultural_-_Nucleo_-_Base_de_Dados.csv` (1,82 KB)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/FundacaoCultural/2024-11-26_Fundacao_Cultural_-_Nucleo_-_Dicionario_de_Dados.xlsx

Colunas para cruzar: **endereco**: endereco_id; **data**: data_criacao, data_ultima_alteracao

Colunas: `id`, `nome`, `horario`, `email`, `endereco_id`, `codigo`, `data_criacao`, `data_ultima_alteracao`, `meta_description`, `meta_keywords`

## Fala Curitiba (`pmc_fala_curitiba`)

- Última atualização: 01/10/2026 11:21:00
- Secretaria: IMAP
- Responsável: Simone Cristina Iubel
- Frequência de atualização: Trimestral
- Espectro temporal: Últimos 3 meses
- Histórico (mais de um ano): http://dadosabertos.c3sl.ufpr.br/curitiba/FalaCuritiba/

### .csv: 8 arquivos, mais recente `2026-10-01_Fala_Curitiba_-_Base_de_Dados.csv` (217 B)

Dicionário: https://mid-dadosabertos.curitiba.pr.gov.br/falacuritiba/2024-11-26_Fala_Curitiba_-_Dicionario_de_Dados.csv

Colunas: `Nome do Campo`, `Descricao`, `Tipo`, `Tamanho`