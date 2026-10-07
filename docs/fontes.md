# Fontes de dados: Curitiba

Inventário comentado das fontes públicas para o recorte de Curitiba (`cod_ibge 4106902`). A versão que os scripts leem é o [`catalogo.yaml`](../catalogo.yaml); este documento explica o porquê de cada fonte.

**Status**
- ✅ existência confirmada em pesquisa (formato e periodicidade ainda a conferir no download)
- 🔎 conhecida, falta conferir cobertura e formato para Curitiba
- ♻️ já existe no ETL da MINDATA

**Chaves de cruzamento**
- `cnpj`: CNPJ de 14 dígitos
- `end`: endereço normalizado, geocodificado para `lat`/`lon`
- `geo`: coordenada nativa
- `terr`: território já agregado (setor, bairro, regional, município)
- `lote`: indicação fiscal do lote no IPPUC

Todo registro termina com a mesma chave territorial: setor censitário 2022, bairro IPPUC (75), regional, zona de uso do solo e H3 (res 8 e 9).

---

## 1. Prefeitura de Curitiba: Portal de Dados Abertos

Portal: `dadosabertos.curitiba.pr.gov.br` (antigo `curitiba.pr.gov.br/dadosabertos`).

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| Base de Alvarás | Alvarás de funcionamento: nome empresarial e fantasia, início de atividade, endereço, CEP, CNAE principal e secundários, emissão e expiração | `end` / nome / CNAE (sem CNPJ) | ✅ | Cruzamento CNPJ × alvará: informalidade, ponto vago, atividade real, data de chegada ao endereço |
| Licitações e Contratações | Compras regulares e emergenciais, com CNPJ/CPF do fornecedor | `cnpj` | ✅ | Fornecedores da prefeitura, fim de contrato como oportunidade (G4) |
| Base de receitas e despesas | Execução orçamentária | `cnpj` (favorecido) | ✅ | Quanto cada empresa recebe do município |
| SIAC 156 | Solicitações do cidadão: tipo, assunto, local | `end`/`terr` | ✅ | Zeladoria e problemas urbanos por bairro (iluminação, buraco, poda) |
| Transporte Coletivo | GTFS, linhas, pontos, itinerários, posição dos veículos, horários | `geo` | ✅ | Acessibilidade, fluxo potencial por ponto de ônibus, isócronas por transporte público |
| Unidades de Atendimento (ativas) | Equipamentos públicos municipais, estaduais, federais e privados, com coordenadas | `geo` | ✅ | Polos de atração (UBS, escolas, Ruas da Cidadania, terminais) |
| E-Saúde: atendimentos | Atendimentos médicos e odontológicos nas unidades municipais | `terr` (unidade) | ✅ | Demanda de saúde por região: perfil etário, CID, volume |
| Guarda Municipal (SiGesGuarda) | Ocorrências atendidas (estudos citam jan/2009 a mar/2022) | `end`/`geo` | ✅ (atualização a conferir) | Risco por quadra e bairro |
| Clique Economia | Preços de cerca de 750 itens em supermercados médios e grandes | `cnpj`/`end` | ✅ | Preço por bairro e rede, posicionamento do varejo alimentar |
| Casos de dengue / Censo COVID-dengue | Casos por bairro | `terr` | ✅ | Contexto de saúde pública |
| Eventos PMC | Agenda de eventos e festivais | `geo`/`end` | ✅ | Fluxo pontual em áreas comerciais |
| Fala Curitiba | Demandas da consulta pública do orçamento | `terr` | ✅ | Prioridades declaradas por regional |
| SIGMU | Sistema Integrado de Gestão da Manutenção Urbana | `end`/`terr` | ✅ | Zeladoria por bairro, junto com o 156 |
| Licitações e Contratações COVID-19 | Compras emergenciais da pandemia | `cnpj` | ✅ | Histórico de fornecedores |
| Saldos orçamentários | Saldos por dotação | n/a | ✅ | Contexto fiscal |
| Portal FCC | Espaços culturais e Lei de Incentivo | `end` | ✅ | Polos culturais |
| Relação de servidores | Cargos e encargos | n/a | ✅ | Baixo valor para B2B |

O portal tem 32 conjuntos (levantamento de 06/10/2026). O inventário de 07/10/2026, com colunas, frequência e arquivos de cada base, está em [`inventario-portal.md`](inventario-portal.md): a Base de Alvarás **não tem CNPJ** (cruzamento por endereço, nome e CNAE) e as Licitações têm CNPJ/CPF do fornecedor. Os de interesse estão no `catalogo.yaml` com a `portal_chave`; o comando `python -m etl.fontes.portal_inventario --baixar` confere links, formato e colunas de cada um. Ficaram de fora, por não terem uso B2B: Aprendere, Estágio, Previdência municipal, Fila de Pretendentes (Cohab), Conecta Curitiba, Oficina de Música, Legisladoc, Saúde Já, Censo e Casos de COVID, Incentivo ao Esporte e Piso da Enfermagem.

## 2. IPPUC: geografia oficial

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| Base vetorial municipal (SHP/DXF) | Arruamento, quadras, **lotes**, hidrografia, parques, praças, áreas verdes, zoneamento | `geo`/`lote` | ✅ | Malha mais fina que o setor censitário |
| Bairros (75) e regionais | Limites oficiais | `geo` | ✅ | Unidade de leitura do produto |
| Zoneamento (Lei 15.511/2019) | Zonas e usos permitidos | `geo` | ✅ | "Este ponto permite este uso?" para escolha de ponto (G6) |
| Eixos de logradouro com numeração | Geocodificação por número | `end` | 🔎 | Geocodificação melhor que o CNEFE. Houve cessão da numeração predial ao OSM em 2018: conferir o que já está no OSM |
| GeoCuritiba / Mapa Cadastral | Consulta por lote: indicação fiscal, inscrição imobiliária, planta de loteamento | `lote` | ✅ | Consulta pontual. **Não fazer raspagem em massa** sem convênio |
| Guia Amarela (Consulta Informativa do Lote) | Zoneamento, usos e parâmetros construtivos do lote, alertas e bloqueios | `lote` | ✅ | Idem: consulta sob demanda no cartão do endereço |
| Curitiba em Dados / Nosso Bairro | Indicadores e perfis por bairro | `terr` | 🔎 | Validação dos agregados e indicadores prontos |

## 3. Trânsito e mobilidade

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| Setran: autuações | Multas de 2019 a abr/2025 por infração e **local**, receita mensal | `end` | ✅ | Proxy de fluxo de veículos por via e de pontos críticos |
| Setran: radares | 262 radares com endereço e tipo (PDF) | `end` | ✅ | Fluxo e controle por via |
| URBS / GTFS | Ver Transporte Coletivo | `geo` | ✅ | |
| DETRAN-PR: anuário estatístico | Frota por categoria e município, acidentes | `terr` | ✅ | Contexto de frota (oficinas, autopeças, postos) |
| SENATRAN: frota por município | Frota mensal por tipo de veículo | `terr` | 🔎 | Série mensal mais curta que o anuário |
| PRF: acidentes em rodovias federais | Acidentes com lat/lon (BR-116, BR-277, BR-376 no contorno) | `geo` | 🔎 | Risco logístico nas bordas da cidade |
| OSM / Overture | Vias, hierarquia viária, POIs | `geo` | 🔎 | Rede para OSRM/Valhalla e isócronas |

## 4. Saúde pública

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| E-Saúde (prefeitura) | Ver seção 1 | `terr` | ✅ | |
| CNES (DATASUS) | Estabelecimentos de saúde com CNPJ, endereço, leitos, equipamentos, profissionais | `cnpj`/`end` | 🔎 | Mapa do setor de saúde privado e público, cruzado com CNAE 86xx |
| SIH / SIA (DATASUS) | Internações e produção ambulatorial (SIH traz CEP de residência) | `terr`/CEP | 🔎 | Demanda de saúde por área |
| SIM / SINASC | Óbitos e nascimentos | `terr` | 🔎 | Envelhecimento, natalidade (baby, educação infantil) |
| ANVISA | Licenças e registros | `cnpj` | ♻️ | |

## 5. Obras e mercado imobiliário

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| Painel de Obras do Município | Obras em execução com CNPJ da empresa, projetos, datas, medições (Lei 16.278/2023) | `cnpj`/`end` | ✅ | Construtoras com contrato público, obras perto de um ponto |
| Plano de Contratações Anual de Obras (PCA) | Obras previstas | `cnpj`/`end` | ✅ | Oportunidade antes da licitação |
| Alvarás de construção (SMU) | Construção, reforma, ampliação, regularização | `lote` | 🔎 | Não achei base aberta: verificar no portal ou pedir via LAI. É o melhor sinal de expansão urbana |
| ITBI / Planta Genérica de Valores | Transações e valor do m² | `lote`/`terr` | 🔎 | Não achei base aberta em Curitiba. Pedir via LAI. Proxy de valor do solo e renda |

## 6. Contratos e compras públicas

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| Licitações e Contratações (prefeitura) | Ver seção 1 | `cnpj` | ✅ | |
| TCE-PR (PIT) | Contratos municipais de todo o PR | `cnpj` | ♻️ `scripts/etl_tce_pr.py` | |
| PNCP | Compras de todas as esferas | `cnpj` | ♻️ `scripts/etl_pncp.py` | |
| Portal da Transparência (CGU) | Gastos federais por favorecido, convênios, CEIS/CNEP | `cnpj` | ♻️ parcial | |
| Portal da Transparência do PR | Compras e contratos estaduais | `cnpj` | 🔎 | Fornecedores do governo do estado sediados em Curitiba |
| Câmara Municipal de Curitiba | Contratos e despesas da Câmara | `cnpj` | 🔎 | Complemento |

## 7. Junta Comercial e dinâmica empresarial

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| Receita Federal (CNPJ) | Abertura, baixa, endereço, CNAE, sócios, Simples/MEI | `cnpj`/`end` | ♻️ `cnpj_consolidado` | Base da oferta |
| JUCEPAR: Empresas PR | Aberturas e fechamentos por município, região, atividade, natureza jurídica e porte, mensal | `terr` | ✅ | Validação mensal da dinâmica que derivamos da RFB. Registros individuais não são abertos |
| Mapa de Empresas (gov.br / REDESIM) | Tempo de abertura e contagem por município | `terr` | 🔎 | Contexto de ambiente de negócios |
| Diário Oficial do Município | Atos, licitações, alvarás publicados | `cnpj` (texto) | 🔎 | Mineração de texto. Conferir cobertura de Curitiba no Querido Diário |

## 8. Impostos e finanças públicas

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| Base de receitas e despesas (prefeitura) | Arrecadação municipal (ISS, IPTU, ITBI, taxas) | município | ✅ | Peso de cada tributo, série histórica |
| Siconfi / FINBRA (Tesouro) | Receitas e despesas declaradas, comparáveis entre capitais | município | 🔎 | Curitiba contra outras capitais |
| SEFA-PR: ICMS por município e atividade | ICMS arrecadado por CNAE no município | município × CNAE | 🔎 | Peso econômico por setor. Conferir se está aberto ou só sob pedido |
| PGFN: dívida ativa | Devedores da União | `cnpj` | ♻️ | Saúde da carteira (G4) |
| Simples Nacional / MEI | Regime tributário | `cnpj` | ♻️ | Porte fiscal |
| IRPF por município (Receita) | Grandes números do IRPF | município | 🔎 | Já previsto no G1 |

## 9. Segurança pública

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| SESP-PR: estatísticas criminais | Ocorrências por natureza e **bairro** de Curitiba, trimestrais | `terr` | ✅ (formato a conferir) | Índice de risco por bairro e tipo de crime (furto a comércio separado de homicídio) |
| Guarda Municipal | Ver seção 1 | `end`/`geo` | ✅ | |
| SESP-PR: BI do CAPE | Painel público com a mesma base (BOU, que reúne PM e Polícia Civil, e SCOL) | `terr` | ✅ | Se não exportar, pedir a série via LAI |
| Corpo de Bombeiros: ocorrências (SYSBM, SIATE) | Incêndio, resgate, trauma. Curitiba teve 17.860 ocorrências em 2025 | `terr` | LAI | Risco de incêndio e acidente por área |
| Corpo de Bombeiros: Certificado de Vistoria (CVCB, PREVFOGO) | Validade de 1 ano, consulta individual | `cnpj`/`end` | LAI | Vistoria vencida ou reprovada é lead para prevenção de incêndio |
| Defesa Civil de Curitiba | Pontos de alagamento, destelhamento e queda de árvore com coordenada | `geo` | LAI | Risco físico do ponto |
| SINESP | Ocorrências por município | município | 🔎 | Comparação com outras capitais |

PM e Polícia Civil não têm base própria aberta: os registros das duas entram no Boletim de Ocorrência Unificado e saem pelo CAPE. Unidades especializadas (ROTAM, BPMOA) não têm dado público por unidade, e não buscamos: baixo valor B2B e informação operacional sensível.

## 10. Contexto socioeconômico e infraestrutura

| Base | Conteúdo | Chave | Status | Uso no Pineal |
|---|---|---|---|---|
| IPARDES: BDEweb | Cerca de 2.500 variáveis de 32 temas para os 399 municípios do PR (energia Copel, saneamento Sanepar, emprego, saúde) | município | ✅ | Indicadores prontos. A prefeitura tem cooperação técnica com o IPARDES |
| Censo 2022 / CNEFE | Ver plano (G0 e G1) | setor | ♻️ planejado | |
| CAGED / RAIS | Ver plano (G1) | município × CNAE | ♻️ planejado | |
| TSE: eleitorado por seção e local de votação | Perfil por idade, sexo e escolaridade, com endereço do local de votação | `end` | 🔎 | Perfil fino do eleitor por local, complementar ao setor censitário |
| INEP: Censo Escolar | Escolas com localização e matrículas | `geo`/`cnpj` | 🔎 | Demanda de serviços ligados a escolas, mapa de escolas privadas |
| ANP: preços e revendedores | Postos com CNPJ, endereço e preço semanal | `cnpj`/`end` | 🔎 | Concorrência e preço de combustível por bairro |
| ANEEL: geração distribuída | Instalações solares por município, classe e potência | município/CEP | 🔎 | Sinal de investimento e mercado de energia solar |
| ANATEL | Banda larga por município e empresa, ERBs com coordenadas | município/`geo` | 🔎 | Infraestrutura digital |
| BCB: ESTBAN e agências | Saldos de crédito e depósitos por agência, agências com endereço | `end`/município | 🔎 | Crédito local, mapa bancário |
| Previdência / CadÚnico / Bolsa Família | Benefícios por município | município | 🔎 | Renda de transferência (CadÚnico já está no G1) |
| ANS: beneficiários de planos de saúde | Por município | município | 🔎 | Proxy de renda formal |

## 11. Listas com CNPJ (M1b)

| Fonte | O que traz | Por que importa |
|---|---|---|
| MDIC: exportadoras e importadoras | CNPJ, município, faixa de valor por ano | Empresa com operação internacional |
| BNDES: operações | CNPJ, valor, produto, data | Empresa que acabou de captar crédito está investindo |
| IBAMA: Cadastro Técnico Federal | CNPJ e atividade potencialmente poluidora | Indústria real, alvo de consultoria ambiental |
| IAT-PR: licenciamento ambiental | Licenças com CNPJ, tipo e validade | Licença vencendo é lead |
| CADASTUR | Hotéis, agências, eventos com CNPJ | Cadeia de turismo |
| ANATEL: provedores (SCM) | CNPJ e acessos por município | Mercado de telecom local |
| MAPA: estabelecimentos com SIF | Frigoríficos e laticínios | Indústria de alimentos |
| e-MEC | Faculdades e polos com endereço | Polos de fluxo e demanda jovem |
| CNES | Estabelecimentos de saúde com CNPJ | Setor de saúde privado e público |
| ANP | Postos com CNPJ e preço | Concorrência no varejo de combustível |

## 12. Cruzamentos e edificações (M2, scripts prontos)

| Fonte | O que traz | Script |
|---|---|---|
| PNCP, TCE-PR, PGFN e sanções federais | Contratos públicos, dívida ativa e sanções por CNPJ, lidos das tabelas que o ETL da MINDATA já carrega | `etl/fontes/mindata_cruzamentos.py` |
| Hierarquia da CNAE (IBGE) | Seção, divisão, grupo e classe de cada subclasse, para os agregados saírem legíveis | `etl/fontes/apoio.py` |
| Overture Buildings | Edificações com altura e andares; agregadas em área construída por hexágono H3 | `etl/fontes/overture_edificacoes.py` |
| INPI (planejado) | Marcas por CNPJ titular: empresa que investe em marca | acesso em lote a confirmar |
| Simepar e INMET (planejado) | Chuva e temperatura diárias: sazonalidade do varejo | |

## Fora de propósito

- Google Places e popular times: pagos e com termos que proíbem o uso.
- Raspagem de portais imobiliários: termos de uso e LGPD.
- Protestos: só por fornecedor pago.
- Ookla Open Data: licença CC BY-NC, que proíbe uso comercial.
- Dados de segurança, saúde ou benefícios por pessoa: entram sempre agregados.

---

## Prioridade para o M0 e M1

1. **Base vetorial do IPPUC** (bairros, regionais, quadras, lotes, zoneamento, eixos): fundação territorial.
2. **Base de Alvarás**: o cruzamento que diferencia o produto.
3. **GTFS URBS + Unidades de Atendimento**: acesso e polos de atração.
4. **Licitações e Contratações + Painel de Obras**: somam aos ETLs de PNCP e TCE-PR já existentes.
5. **SIAC 156, SESP-PR e Guarda Municipal**: índice de risco e zeladoria por bairro.
6. **Setran (autuações por local)**: proxy de fluxo viário.
7. **CNES, INEP, ANP e IPARDES**: enriquecimento setorial.

## Pedidos via LAI

Rascunhos prontos em [`pedidos-lai.md`](pedidos-lai.md).

## Ressalvas

- Mapa Cadastral e Guia Amarela são consultas por lote. Usar sob demanda no produto, sem raspagem em massa.
- Dados de saúde e segurança entram só agregados por território, nunca por pessoa (LGPD).
- Formatos, colunas e periodicidade marcados como ✅ foram confirmados por pesquisa, não por download. O inventário do portal (`etl.fontes.portal_inventario`) fecha essa conferência.

## Referências da pesquisa

- [Portal de Dados Abertos: conjuntos de dados](https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe?chave=ca40f13b-ef61-472b-810f-dd705f85fd2e)
- [SIAC 156](https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe/?chave=0d5a7b06-3940-4be9-876e-bc8f23e96530)
- [Unidades de Atendimento ativas](https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe/?chave=680ed5ed-c8b7-4e81-a2af-637d2757027a)
- [Clique Economia](https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe/?chave=245ef1b9-f82a-42ed-a711-1dec4ccd4be1)
- [Base de receitas e despesas](https://dadosabertos.curitiba.pr.gov.br/conjuntodado/detalhe/?chave=5ddffbe8-313b-4d94-a862-73ab74b3817c)
- [Dicionário de Licitações e Contratações](https://mid-transparencia.curitiba.pr.gov.br/home/Dicionario_Licitacoes_Contratacoes_19082020.pdf)
- [Novo portal de dados abertos de Curitiba](https://www.curitiba.pr.gov.br/noticias/curitiba-tem-novo-portal-de-dados-abertos-para-o-cidadao/75468)
- [Painel de Obras: referência em transparência](https://www.curitiba.pr.gov.br/noticias/prefeitura-de-curitiba-e-referencia-em-transparencia-em-obras-publicas/82811)
- [Setran divulga multas por local](https://www.curitiba.pr.gov.br/noticias/portal-da-setran-passa-a-divulgar-dados-referentes-aos-numeros-e-locais-das-multas-de-transito/77187)
- [Plataforma GeoCuritiba do IPPUC](https://www.curitiba.pr.gov.br/noticias/nova-plataforma-de-mapas-do-ippuc-usa-mesma-tecnologia-adotada-pela-nasa/63090)
- [Cessão da numeração predial do IPPUC ao OSM](https://lists.openstreetmap.org/pipermail/talk-br/2018-November/012458.html)
- [Consulta Informativa do Lote](https://www.curitiba.pr.gov.br/servicos/alertas-e-bloqueios-consulta-informativa-do-lote/divida-ativa/61)
- [Guarda Municipal: estudo com dados abertos](https://riut.utfpr.edu.br/jspui/bitstream/1/28036/1/CT_CCEDA_2019_02_13.pdf)
- [E-Saúde: estudo com dados abertos](https://portaldeinformacao.utfpr.edu.br/Record/riut-1-4651/Description)
- [JUCEPAR: ferramenta Empresas PR](https://www.parana.pr.gov.br/Noticia/Ferramenta-da-Junta-Comercial-agiliza-acesso-informacoes-estatisticas-sobre-empresas)
- [IPARDES: nova Base de Dados do Estado](https://www.parana.pr.gov.br/Audio/Ipardes-lanca-nova-versao-da-Base-de-Dados-do-Estado-com-informacoes-dos-399-municipios)
- [Cooperação Prefeitura × IPARDES](https://www.curitiba.pr.gov.br/noticias/prefeitura-de-curitiba-firma-cooperacao-tecnica-com-ipardes-para-fortalecer-analise-de-dados-economicos-e-sociais/81928)
- [SESP-PR: ocorrências por bairro em Curitiba (1º tri 2026)](https://www.tribunapr.com.br/noticias/curitiba-regiao/centro-lidera-ranking-crimes-curitiba-dez-bairros-mais-ocorrencias-2026/)
- [CAPE: Estatísticas](https://www.seguranca.pr.gov.br/CAPE/Estatisticas)
- [CONSEG: Estatística Pública](https://www.conseg.pr.gov.br/Pagina/Estatistica-Publica)
- [SINESP: Ocorrências Criminais](https://dados.mj.gov.br/dataset/sistema-nacional-de-estatisticas-de-seguranca-publica)
- [CBMPR: NPA 001 (vistoria e CVCB)](https://www.bombeiros.pr.gov.br/sites/bombeiros/arquivos_restritos/files/documento/2026-04/npa001_portaria199.pdf)
- [Bombeiros PR: balanço 2025](https://www.bemparana.com.br/noticias/parana/a-cada-quatro-minutos-um-pedido-de-socorro-bombeiros-atenderam-mais-de-27-mil-casos-no-parana-em-2025/)
- [Defesa Civil: alagamentos em Curitiba (FAE)](https://revistafae.fae.edu/revistafae/article/viewFile/147/91)
- [DETRAN-PR: anuário estatístico 2022](https://www.detran.pr.gov.br/sites/default/arquivos_restritos/files/documento/2024-10/anuario_estatistico_2022-1.pdf)
