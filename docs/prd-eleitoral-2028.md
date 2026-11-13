# PRD — Módulo Eleitoral (ME): estudo territorial para as eleições municipais de Curitiba 2028

| | |
|---|---|
| **Status** | Rascunho para chancela |
| **Versão** | 0.2 (2026-11-13) |
| **Dono** | Vinícius Madureira |
| **Repositório** | `mdrrv/pineal-curitiba` (módulo ME, ao lado do funil B2B) |

---

## Chancela

O PRD só vale depois de chancelado. Mudança de escopo depois da chancela vira nova versão, com nova linha aqui.

| Papel | Nome | Decisão | Data |
|---|---|---|---|
| Dono do produto | Vinícius Madureira | _pendente_ | |
| Revisão jurídica (LGPD / eleitoral) | _a definir_ | _pendente_ | |
| Revisão técnica | _a definir_ | _pendente_ | |

### Histórico de versões

| Versão | Data | O que mudou |
|---|---|---|
| 0.2 | 2026-11-13 | Taxonomia de pautas do ME2 (dores latentes priorizadas pelo dono do produto: alagamentos, trânsito, situação de rua, mais as mensuráveis), fontes do portal reincluídas do recorte B2B e pedidos LAI 15–18 |
| 0.1 | 2026-11-13 | Primeiro rascunho: escopo, fases ME0–ME3, limites legais, fontes e modelo de dados |

---

## 1. Contexto e problema

O Pineal Curitiba já resolveu a parte cara de qualquer leitura territorial da cidade: chave territorial única (setor censitário 2022, bairro IPPUC, regional, zona, H3 res 8 e 9), geocodificação em níveis com erro medido, Censo 2022 por setor, isócronas a pé e de ônibus, e fontes municipais que são leitura política pura — Fala Curitiba (prioridades declaradas por regional), 156/SIGMU (zeladoria), SiGesGuarda (segurança), E-Saúde, licitações e obras.

O que falta para um estudo eleitoral é a **camada eleitoral**: ninguém sabe, hoje, nesse banco, como cada região da cidade vota, quem vota nela, quanto ela se abstém e o que mudou entre eleições. Esses dados existem, são públicos (Portal de Dados Abertos do TSE) e se encaixam na mesma chave territorial pelo elo **seção eleitoral → local de votação (endereço/coordenada) → bairro/setor/H3**.

**Problema:** não existe hoje um retrato territorial integrado de Curitiba que cruze comportamento eleitoral histórico, perfil do eleitorado e demandas concretas da população por bairro, para orientar estudo e, depois, campanha nas eleições municipais de 2028.

## 2. Objetivos

1. **Diagnóstico territorial eleitoral de Curitiba** (fase de estudo, 2026–2027): série histórica de votação por seção/bairro desde 2016, perfil do eleitorado, abstenção, volatilidade.
2. **Cruzamento voto × pauta** (2027): desempenho eleitoral do incumbente e dos vereadores por região × demandas declaradas (Fala Curitiba, 156, segurança, saúde) — onde a insatisfação não tem representação.
3. **Instrumento operacional de campanha** (2028): score de prioridade territorial (volatilidade + abstenção + densidade de eleitores + intensidade de pautas) e mapas por bairro/hexágono para agenda de rua, usando as isócronas existentes.

### Não-objetivos (fora de escopo, em qualquer fase)

- **Nenhum dado nominal de eleitor.** Só agregados por seção/território, como o TSE publica.
- **Nenhum cruzamento da base de CNPJs/sócios com dados eleitorais.** O funil B2B e o módulo ME compartilham só a infraestrutura territorial (geografia, Censo, geocodificação), nunca dados de empresa ou pessoa.
- **Nenhuma lista de contato, disparo, ou segmentação individual.** O produto é mapa e indicador agregado.
- Pesquisa de intenção de voto, mídia paga, gestão de militância: fora deste repositório.

## 3. Limites legais (condição de existência do módulo)

- **LGPD (Lei 13.709/2018):** o módulo só trata dados agregados e públicos. A disciplina já existente no repo (CPF mascarado, exportação sem nome, `dados/` fora do git) se aplica integralmente.
- **Lei 9.504/1997 e resoluções do TSE sobre propaganda e uso de dados pessoais em campanha:** nada aqui gera cadastro de eleitor nem comunicação dirigida. Qualquer evolução nessa direção exige parecer jurídico prévio e nova chancela.
- **Prestação de contas (fase ME3):** dados públicos do TSE (DivulgaCandContas), usados só para leitura de financiamento, com atribuição.
- Licenças: dados do TSE são abertos com atribuição; valem as mesmas regras de citação do restante do repo.

## 4. Usuários

| Usuário | Uso |
|---|---|
| Analista do estudo (2026–2027) | Roda o ETL, lê relatórios em `relatorios/`, explora o banco |
| Coordenação de campanha (2028) | Consome mapas e scores publicados (mesmo pacote de publicação do M3) |

## 5. Fases e requisitos

A numeração segue o padrão do repo (M0–M3 no B2B; **ME0–ME3** no eleitoral). Cada fase termina com dados reais carregados, testes verdes e relatório em `relatorios/eleitoral.md`.

### ME0 — Fundação eleitoral (esta entrega)

Pré-requisito: M0 rodado com dados reais (setores, bairros, CNEFE) — issue a abrir.

| # | Requisito | Critério de aceite |
|---|---|---|
| ME0.1 | Carga dos **locais de votação** do TSE (`eleitorado_local_votacao_<ano>`), recorte Curitiba, com coordenada do TSE quando houver e geocodificação pelo núcleo existente quando não houver | `eleicao_local_votacao` com ≥95% das seções com geometria; chave territorial (setor, bairro, regional, H3) atribuída |
| ME0.2 | Carga da **votação por seção** (`votacao_secao_<ano>_PR`), eleições 2016–2026, recorte Curitiba | `eleicao_votacao_secao` com votos por ano, turno, cargo e votável; aptos/comparecimento/abstenções por seção |
| ME0.3 | Carga do **perfil do eleitorado por seção** (`perfil_eleitor_secao_<ano>_PR`) | `eleicao_perfil_secao` com eleitores por gênero × faixa etária × escolaridade |
| ME0.4 | **Ponte seção → território**: cada seção de cada eleição ligada ao bairro/setor/H3 pelo local de votação do ano mais próximo disponível | `eleicao_secao_territorio` preenchida; % de seções sem território no relatório |
| ME0.5 | Agregados de partida: votação por bairro (ano, turno, cargo, votável, % no bairro) e participação por bairro (aptos, comparecimento, abstenção) | `eleicao_bairro_votacao` e `eleicao_bairro_participacao`; relatório com top bairros por abstenção e resultado de prefeito por bairro |
| ME0.6 | Orquestrador `python -m etl.me`, testes com arquivos sintéticos no layout real do TSE (padrão do repo), CI verde | `tests/test_eleitoral.py` |

### ME1 — Indicadores eleitorais (estudo)

- Volatilidade por bairro/seção entre eleições (municipal × municipal, geral × municipal).
- Fidelidade partidária e concentração de voto (índice HHI por bairro).
- Abstenção: série histórica, tendência e comparação com o perfil do eleitorado.
- Perfil do eleitorado × Censo 2022 (o eleitor local mora ali? bairros dormitório vs. seções "importadas").
- Desempenho dos vereadores eleitos em 2024 por bairro: quem "é dono" de cada território, com que margem.

### ME2 — Voto × pauta e score territorial

- Cruzamento por bairro: cada pauta da taxonomia abaixo × desempenho do incumbente e abstenção.
- **Score de prioridade territorial de campanha** no arcabouço do `80_score.sql` (tabela de pesos editável): volatilidade, abstenção, eleitores aptos, intensidade de pauta sem resposta.
- Publicação (pacote M3): mapas por bairro/H3 em FlatGeobuf/PMTiles, sem nenhum dado além dos agregados.

#### Taxonomia de pautas do ME2

As três primeiras são as dores latentes priorizadas pelo dono do produto (2026-11); as demais completam o que
as pesquisas de percepção apontam e o banco consegue medir. O **Fala Curitiba é o gabarito**: diz o que a
população *declara* por regional; as fontes abaixo medem a dor *objetiva*; a distância entre as duas, e entre
ambas e o voto no incumbente, é o indicador central do ME2. Achado de estrutura: o filtro "sem uso B2B" do
inventário do portal descartou justamente fontes de dor social (fila do Saúde Já, Fila de Pretendentes da
Cohab) — reincluídas aqui com fase ME.

| # | Pauta | Dor medida | Fontes | Indicador por bairro | Situação |
|---|---|---|---|---|---|
| P1 | **Alagamentos e drenagem** | Chamado recorrente a cada temporal | 156/SIGMU (boca de lobo, galeria, alagamento), SiGesGuarda (`defesa_civil`), chuva INMET, hidrografia IPPUC; Defesa Civil (LAI 9) | Chamados por 1.000 domicílios em dia de chuva forte (sensibilidade à chuva) | Fontes já no repo; LAI 9 completa |
| P2 | **Trânsito** | Congestionamento, acidentes, custo do transporte | GTFS/isócronas (oferta, já no repo); acidentes BPTran/SESP (LAI 15), autuações Setran (LAI 14), contagens (LAI 5), bilhetagem URBS (LAI 6) | Acidentes por km de via; tempo de acesso ao Centro por transporte público; demanda por linha | A dor (acidentes, fluxo) depende das LAIs; janela política: nova concessão do transporte (15 anos) em debate |
| P3 | **População em situação de rua** | Concentração junto a áreas comerciais; ausência de contagem oficial é a própria pauta | 156 (abordagem social), SiGesGuarda; FAS agregada (LAI 17) | Chamados de abordagem social × perfil comercial do ponto (o Pineal já calcula) | Proxies já no repo; LAI 17 completa. Atenção redobrada ao limite: só agregados, nunca indivíduo |
| P4 | Segurança | 1º problema nas pesquisas de percepção | SiGesGuarda + `risco_bairro_indice` (prontos); CAPE/SESP (LAI 7) | Índice de risco por bairro (existe) | Pronto; LAI 7 enriquece |
| P5 | Saúde | Fila de especialista, pressão nas UPAs | E-Saúde (carregado); fila do Saúde Já (`pmc_saude_fila`, reincluída; senão LAI 18); dengue (`pmc_dengue`) | Espera por especialidade por regional; atendimentos por unidade | E-Saúde pronto; fila a conferir no portal |
| P6 | Habitação | Déficit, fila da Cohab, ocupações | Fila de Pretendentes (`pmc_cohab_fila`, reincluída do portal) | Pretendentes por regional | A conferir no portal |
| P7 | Creches | Fila por vaga em CMEI | SME (LAI 16); Censo Escolar INEP (planejado M2) | Crianças em espera por regional | Depende da LAI 16 |
| P8 | Emprego local | 2º problema nas pesquisas | O próprio Pineal: `m2_movimento`, risco de fechamento, saturação | Saldo de abertura/fechamento e risco por bairro | Pronto (reuso direto do B2B, agregado) |
| P9 | Zeladoria geral | Iluminação, buraco, poda | 156/SIGMU (ativos) | Chamados por tipo por 1.000 domicílios | Pronto |

Entregável da fase: tabela `pauta_bairro` (pauta × bairro × indicador normalizado 0–100) alimentando o score
territorial, e o cruzamento com `eleicao_bairro_votacao`/`eleicao_bairro_participacao`.

### ME3 — Financiamento e concorrência (opcional, mediante chancela específica)

- Prestação de contas 2020/2024 (receitas por candidato/partido, origem territorial das doações agregada).
- Base de candidaturas e histórico dos concorrentes prováveis.
- Isócronas para logística de agenda (já existentes no repo).

## 6. Fontes novas (entradas no `catalogo.yaml`, família `tse_*`)

| Fonte | Arquivo | Fase | Observação |
|---|---|---|---|
| Locais de votação | `eleitorado_local_votacao_<ano>.zip` (nacional) | ME0 | Traz lat/lon nas extrações recentes; `-1` = sem coordenada |
| Votação por seção | `votacao_secao_<ano>_PR.zip` | ME0 | 2016, 2018, 2020, 2022, 2024, 2026 |
| Perfil do eleitorado por seção | `perfil_eleitor_secao_<ano>_PR.zip` | ME0 | Gênero, faixa etária, escolaridade |
| Prestação de contas | DivulgaCandContas | ME3 | Só com chancela da fase |
| Câmara Municipal (vereadores, proposições) | portal da CMC | ME1 | Levantar formato |

Layouts do TSE variam entre anos: como nas listas M1b, o layout real se confere na primeira carga e o leitor tolera coluna ausente não-obrigatória. Código TSE de Curitiba (`CD_MUNICIPIO`) configurável em `PINEAL_COD_TSE`, com filtro de reserva por nome + UF, no mesmo padrão do recorte RFB.

## 7. Modelo de dados (ME0)

Mesmo schema PostGIS do Pineal (`cwb`), tabelas com prefixo `eleicao_`, criadas em `sql/09_eleitoral_schema.sql`; derivadas em `sql/90_eleitoral.sql`:

- `eleicao_local_votacao` — local por ano/zona/seção, com geometria (origem `tse` ou `geocodificado`), chave territorial completa.
- `eleicao_votacao_secao` — votos por ano, turno, zona, seção, cargo, votável; aptos/comparecimento/abstenções.
- `eleicao_perfil_secao` — eleitores por gênero × faixa etária × escolaridade.
- `eleicao_secao_territorio` — ponte seção → território (derivada).
- `eleicao_bairro_votacao`, `eleicao_bairro_participacao` — agregados de partida (derivadas).

## 8. Métricas de sucesso

| Fase | Métrica | Alvo |
|---|---|---|
| ME0 | Seções com território atribuído | ≥95% |
| ME0 | Soma de votos por bairro = soma oficial do município (por ano/cargo) | 100% (tolerância: seções sem local) |
| ME1 | Diagnóstico escrito do estudo com os indicadores | Entregue até 2027-06 |
| ME2 | Score territorial validado contra 2024 (backtest, como o risco de fechamento fez) | Antes de 2028-07 |

## 9. Cronograma de referência (calendário eleitoral 2028)

| Quando | Marco |
|---|---|
| 2026-Q4 | ME0 com dados reais (depende da rodada real do M0) |
| 2027-S1 | ME1: diagnóstico territorial do estudo |
| 2027-S2 | ME2: voto × pauta, score, primeiros mapas |
| 2028-04 | Janela de filiação/domicílio: estudo fechado |
| 2028-07 | Convenções: pacote operacional publicado |
| 2028-08 a 10 | Campanha: uso operacional (mapas, agenda, isócronas) |

## 10. Riscos

| Risco | Mitigação |
|---|---|
| Layout do TSE muda entre anos | Leitor por coluna nomeada com obrigatórias mínimas; teste sintético por layout; conferência na primeira carga real |
| Seções agregadas/remanejadas entre eleições quebram a série | Ponte usa o local do ano mais próximo; % sem território é métrica do relatório |
| M0 real não rodado (tudo validado só em sintético) | Issue de rodada real é pré-requisito do ME0 com dados reais |
| Deriva de escopo para uso de dado individual | Não-objetivos + revisão jurídica na chancela; qualquer mudança exige nova versão do PRD |
| Confusão entre o produto B2B (MINDATA) e o uso eleitoral | Módulo separado (ME), sem leitura das tabelas `empresa*`; se os destinos divergirem, extrair o núcleo territorial para pacote comum |
