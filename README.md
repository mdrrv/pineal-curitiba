# Pineal Curitiba

Funil de inteligência territorial B2B para Curitiba. Cruza a base de empresas da MINDATA (CNPJ, CNAE, porte, situação) com dados públicos gerais (IBGE, Receita, PNCP, PGFN) e com as fontes oficiais da cidade (IPPUC, Portal de Dados Abertos da prefeitura, segurança pública), sempre pela mesma chave territorial.

É o piloto municipal do módulo Pineal (Inteligência Comercial), planejado em [mdrrv/mindata-data-monetization#251](https://github.com/mdrrv/mindata-data-monetization/issues/251). Roda local primeiro; a estrutura de plataforma vem depois.

---

## Sumário

- [Como funciona](#como-funciona)
- [Estado atual e fases](#estado-atual-e-fases)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Rodando o M0](#rodando-o-m0)
- [Rodando o M1](#rodando-o-m1)
- [Rodando o M2](#rodando-o-m2)
- [O que sai no banco](#o-que-sai-no-banco)
- [Geocodificação: como ler os níveis](#geocodificação-como-ler-os-níveis)
- [Catálogo de fontes](#catálogo-de-fontes)
- [Testes e CI](#testes-e-ci)
- [Problemas comuns](#problemas-comuns)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Dados pessoais e licenças](#dados-pessoais-e-licenças)

---

## Como funciona

```
 fontes                    bruto                  padronizado (schema do Pineal)          produto
 ───────                   ─────                  ──────────────────────────────          ───────
 IBGE (setores, CNEFE)  ─┐                        território: setor, bairro,
 IPPUC (bairros, zonas) ─┤  dados/bruto/<fonte>/  regional, zoneamento                    indicadores (M2):
 RFB (cnpj_consolidado) ─┼─▶ arquivo original  ─▶ empresas geocodificadas com chave  ─▶  saturação, coortes,
 PNCP, PGFN, TCE-PR     ─┤  + sha256 + registro   territorial (setor, bairro, regional,   densidade, raio-x,
 Overture, prefeitura   ─┘  em execucao           zona, H3 8 e 9) + perfil do ponto       GeoParquet; plataforma (M3)
```

1. **Bruto.** Cada fonte é baixada uma vez para `dados/bruto/<fonte>/`. Cada carga e cada etapa ficam registradas na tabela `execucao`, com o `run_id` da rodada, status, duração, origem, arquivo, hash e linhas.
2. **Padronizado.** Tudo vai para um schema do PostGIS (`cwb` por padrão, configurável), em coordenadas geográficas (EPSG:4326). Endereços e nomes passam pela mesma normalização dos dois lados de todo cruzamento.
3. **Chave territorial.** Todo registro com coordenada recebe setor censitário 2022, bairro do IPPUC, regional, zona de uso do solo e hexágonos H3 (resolução 8, cerca de 0,7 km², e 9, cerca de 0,1 km²). Cruzar fontes vira juntar pela chave.
4. **Indicadores.** Em cima da chave saem o perfil de cada ponto (comercial, residencial, domiciliação, rede), o histórico dos endereços e os primeiros produtos do M2.

---

## Estado atual e fases

| Fase | Conteúdo | Situação |
|---|---|---|
| **M0** Fundação territorial | Setores IBGE, camadas IPPUC, CNEFE, recorte de CNPJs, geocodificação em 10 níveis com erro medido em metros, chave territorial | **Pronto e testado com dados sintéticos.** Falta a primeira rodada com dados reais |
| **M2** Enriquecimento e indicadores | Perfil do ponto, domiciliação, histórico do ponto, redes, uso x zoneamento, saturação (QL), sobrevivência por coorte, densidade H3, movimentos mensais, raio-x, cruzamentos PNCP/TCE-PR/PGFN/sanções, edificações do Overture, exportação GeoParquet, demanda do Censo 2022 por setor (moradores por hexágono e no raio, espaço livre por bairro), isócronas a pé e de ônibus com raio-x da área | **Pronto e testado com dados sintéticos.** Códigos das variáveis do Censo a conferir com o dicionário do IBGE |
| **M1** Prefeitura e IPPUC | Alvarás (cruzamento CNPJ × alvará), licitações, 156, SIGMU, unidades de atendimento, transporte (GTFS) | **Pronto e testado com arquivos sintéticos no layout real.** Painel de Obras e autuações da Setran sem fonte em arquivo (#22) |
| M1-seg Segurança | SiGesGuarda (Guarda Municipal) e índice de risco por bairro; CAPE/SESP-PR, Bombeiros e Defesa Civil | **SiGesGuarda e índice prontos e testados.** CAPE, Bombeiros e Defesa Civil dependem da LAI (#14) e entram na mesma tabela |
| M1b Listas com CNPJ | MDIC, BNDES, IBAMA, IAT, CADASTUR, ANATEL, MAPA, e-MEC, CNES, ANP | **Leitor pronto e testado com arquivos sintéticos.** Layout de cada órgão a conferir na primeira carga real (arquivos baixados à mão em `dados/bruto/<lista>/`) |
| M3 Plataforma | Publicação dos agregados no módulo Pineal | Planejado |

---

## Requisitos

- **Python 3.11 ou mais novo.**
- **PostgreSQL 14+ com PostGIS 3** e as extensões `unaccent` e `pg_trgm` (vêm no pacote contrib do Postgres).
  - Windows: instale o PostGIS pelo Stack Builder que acompanha o instalador do PostgreSQL.
  - Sem Postgres local: `docker compose up -d` sobe um PostGIS na porta 5433 (ver `docker-compose.yml`).
- **Banco do ETL da MINDATA** com `dados_rfb.cnpj_consolidado` populado, para o recorte de CNPJs. Pode ser o mesmo servidor e até o mesmo banco do Pineal. Os cruzamentos do M2 também leem, se existirem, `dados_rfb.pncp_contratos`, `tce_pr_contratos`, `pgfn_divida_ativa`, `sancoes_federais`, `cnae` e `natju`.
- Não precisa de GDAL instalado: o `pyogrio` já traz o necessário. O DuckDB (edificações do Overture) também vem pelo `pip`.
- O usuário do banco precisa poder criar extensões. Se não puder, peça ao DBA para rodar uma vez no banco do Pineal:
  ```sql
  CREATE EXTENSION postgis; CREATE EXTENSION unaccent; CREATE EXTENSION pg_trgm;
  ```

---

## Instalação

Windows (PowerShell):

```powershell
git clone https://github.com/mdrrv/pineal-curitiba.git
cd pineal-curitiba
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

Linux e macOS:

```bash
git clone https://github.com/mdrrv/pineal-curitiba.git
cd pineal-curitiba
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

As versões das dependências estão fixas no `pyproject.toml`: é a combinação que o CI testa. Para atualizar, troque todas juntas e rode os testes.

Crie o banco do Pineal. O schema e as extensões o próprio ETL cria:

```bash
createdb -U postgres pineal
```

---

## Configuração

Tudo fica no `.env` (modelo em `.env.example`).

| Variável | Para que serve | Padrão |
|---|---|---|
| `PINEAL_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | Banco do Pineal | `localhost`, `5432`, `pineal`, `postgres`, vazio |
| `PINEAL_DSN` | Alternativa: DSN completo do banco do Pineal | |
| `PINEAL_SCHEMA` | Schema onde tudo é criado. Uma cidade por schema | `cwb` |
| `RFB_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | Banco com `dados_rfb.cnpj_consolidado` | Sem `RFB_DB_NAME`, usa o banco do Pineal |
| `RFB_DSN` | Alternativa: DSN completo do banco RFB | |
| `PINEAL_COD_IBGE` | Código IBGE do município | `4106902` |
| `PINEAL_COD_RFB` | Código do município na Receita (coluna `municipio` do consolidado) | `7535` |
| `PINEAL_NOME_MUNICIPIO`, `PINEAL_UF` | Filtro de reserva pelo nome do município | `CURITIBA`, `PR` |
| `PINEAL_COMPETENCIA` | Competência (AAAA-MM) da foto mensal do recorte | mês corrente |
| `PINEAL_RUN_ID` | Identificador da rodada em `execucao` | gerado por processo |
| `PINEAL_DADOS` | Pasta dos arquivos baixados e exportados | `./dados` |
| `PINEAL_TEST_DSN` | Banco descartável para os testes | |

O recorte de CNPJs usa `uf = PINEAL_UF AND (municipio = PINEAL_COD_RFB OR upper(nome_municipio) = PINEAL_NOME_MUNICIPIO)`.

**Outra cidade:** troque as variáveis do município, aponte `PINEAL_SCHEMA` para um schema novo (ex.: `poa`) e ajuste os padrões de arquivo no `catalogo.yaml`. As duas cidades convivem no mesmo banco sem se misturar.

---

## Rodando o M0

### 1. Inventário do portal da prefeitura (opcional, recomendado)

```bash
python -m etl.fontes.portal_inventario            # metadados, arquivos e colunas de cada base
python -m etl.fontes.portal_inventario --baixar   # também baixa o mais recente e mede o preenchimento
```

Gera `relatorios/inventario_portal.md` e `.json`: frequência, última atualização, quantos arquivos mensais existem, o mais recente (URL, tamanho, dicionário de dados), as colunas e quais servem para cruzar (CNPJ, endereço, coordenada, data). O relatório mostra só nomes de colunas e porcentagem de preenchimento, nunca valores. A última versão está em [`docs/inventario-portal.md`](docs/inventario-portal.md).

O portal guarda os arquivos em `mid-dadosabertos.curitiba.pr.gov.br` (último ano) e no espelho da UFPR `dadosabertos.c3sl.ufpr.br` (mais antigos). Os ETLs do M1 baixam de lá: libere esses hosts se a rede tiver lista de permissão.

O que o inventário de outubro de 2026 mostrou:
- **Base de Alvarás não tem CNPJ.** O cruzamento com as empresas é por CEP, endereço, nome empresarial ou fantasia e CNAE (ver [Rodando o M1](#rodando-o-m1)).
- **Licitações e Contratações** têm `CNPJ/CPF` do fornecedor, valor e vigência do contrato.
- **156 e SiGesGuarda** têm logradouro (sem número), bairro, regional, data e natureza: servem para agregados por bairro. O SiGesGuarda está atualizado (28 arquivos mensais).
- **Unidades de Atendimento** têm rua, número e bairro, sem coordenada: são geocodificadas pelo mesmo núcleo dos CNPJs.
- **Transporte coletivo** não tem arquivo no portal, só o webservice da URBS.
- **E-Saúde** traz dados por atendimento, com data de nascimento e código do usuário: entra só agregado.

### 2. Camadas do IPPUC

O IPPUC não tem link direto estável para todas as camadas. Baixe no site do IPPUC (ou no GeoCuritiba) e coloque em `dados/bruto/ippuc/`:

| Camada | O nome do arquivo precisa conter | Formatos aceitos |
|---|---|---|
| Bairros | `bairro` | `.shp` (com `.dbf` e `.shx`), `.zip`, `.gpkg`, `.geojson` |
| Regionais | `regiona` | idem |
| Zoneamento | `zone` ou `zona` | idem |

Depois confira o que o script encontrou e quais colunas vai usar:

```bash
python -m etl.fontes.ippuc --listar
```

Se a coluna do nome não for detectada, ajuste `campo_nome` (e `campo_codigo`) da camada no `catalogo.yaml`. Arquivo sem `.prj` é lido como SIRGAS 2000 / UTM 22S (EPSG:31982); mude `crs_padrao` se for outro.

Sem essas camadas o M0 roda do mesmo jeito: `bairro`, `regional` e `zona` ficam vazios até a camada ser carregada, e o nível de geocodificação `bairro` não é usado.

### 3. M0 completo

```bash
python -m etl.m0
```

| Etapa | Comando isolado | O que faz |
|---|---|---|
| `schema` | | Cria o schema, as tabelas, as funções de normalização e as tabelas de apoio fixas |
| `setores` | `python -m etl.fontes.ibge_setores` | Acha o zip do PR no FTP do IBGE, baixa e grava os setores de Curitiba |
| `ippuc` | `python -m etl.fontes.ippuc` | Grava bairros, regionais e zoneamento a partir de `dados/bruto/ippuc/` |
| `cnefe` | `python -m etl.fontes.ibge_cnefe` | Acha o CSV do CNEFE de Curitiba no FTP do IBGE, baixa e grava os endereços com coordenada |
| `cnpj` | `python -m etl.fontes.cnpj_recorte [--competencia AAAA-MM]` | Copia os estabelecimentos de Curitiba de `dados_rfb.cnpj_consolidado` (todas as situações) e grava a foto mensal |
| `geocodificar` | `python -m etl.geocodificar` | Localiza cada CNPJ e grava `relatorios/geocodificacao.md` |
| `territorio` | `python -m etl.territorio` | Atribui setor, bairro, regional, zona e H3; grava `relatorios/territorio.md` |

Rodar só parte:

```bash
python -m etl.m0 --so cnpj --so geocodificar --so territorio
python -m etl.m0 --pular setores
```

Cada etapa substitui o conteúdo da sua tabela: rodar de novo não duplica nada (a foto mensal substitui só a da mesma competência). Arquivo já baixado não é baixado de novo; para forçar, apague-o de `dados/bruto/<fonte>/`.

Os scripts do IBGE aceitam arquivo baixado à mão, se o FTP mudar de lugar:

```bash
python -m etl.fontes.ibge_setores --arquivo C:/downloads/PR_setores_CD2022.zip
python -m etl.fontes.ibge_cnefe --arquivo C:/downloads/4106902_CURITIBA.zip
```

Também basta colocar o arquivo em `dados/bruto/ibge_setores/` ou `dados/bruto/ibge_cnefe/`.

### 4. Erro da geocodificação em metros

```bash
python -m etl.avaliar_geocodificacao --amostra 20000
```

Sorteia endereços do CNEFE, esconde o ponto de cada um da base e geocodifica o endereço com o mesmo núcleo usado nos CNPJs. Grava `relatorios/erro_geocodificacao.md` com o erro mediano, o p90 e a fração até 50 m e até 250 m por nível. Como o próprio ponto some da base, a estimativa é conservadora.

### 5. Conferir o resultado

```sql
SET search_path TO cwb, public;

-- acerto da geocodificação
SELECT geo_precisao, count(*) FROM empresa_geo GROUP BY 1 ORDER BY 2 DESC;

-- empresas ativas por bairro
SELECT g.bairro, count(*) AS ativas
FROM empresa e JOIN empresa_geo g USING (cnpj)
WHERE e.situacao_cadastral = '02'
GROUP BY 1 ORDER BY 2 DESC;

-- etapas da última rodada
SELECT fonte, status, duracao_s, erro FROM execucao
WHERE run_id = (SELECT run_id FROM execucao ORDER BY id DESC LIMIT 1) AND tipo = 'etapa' ORDER BY id;
```

---

## Rodando o M1

Bases da prefeitura, depois do M0:

```bash
python -m etl.m1
```

| Etapa | Comando isolado | O que faz |
|---|---|---|
| `alvaras` | `python -m etl.fontes.pmc_alvaras [--arquivo ...]` | Base de Alvarás: carga, geocodificação e cruzamento com os CNPJs; grava `relatorios/alvaras.md` |
| `licitacoes` | `python -m etl.fontes.pmc_licitacoes` | Licitações e Contratações (e a base da COVID-19): itens por CNPJ e resumo em `empresa_contratos_pmc` |
| `zeladoria` | `python -m etl.fontes.pmc_zeladoria` | 156 e SIGMU agregados por bairro, mês e assunto/serviço, com tempo de resposta |
| `unidades` | `python -m etl.fontes.pmc_unidades` | Unidades de Atendimento geocodificadas (escolas, UBS, Ruas da Cidadania...) com H3 |
| `transporte` | `python -m etl.fontes.urbs_gtfs [--arquivo gtfs.zip]` | Pontos de ônibus com linhas e partidas, e agregado por hexágono, a partir de um GTFS |
| `listas` | `python -m etl.fontes.listas_cnpj [--so lista]` | Listas públicas com CNPJ (M1b) que estiverem em `dados/bruto/<lista>/`; grava `relatorios/listas_cnpj.md` |
| `seguranca` | `python -m etl.fontes.pmc_sigesguarda [--arquivo ...]` | Ocorrências da Guarda Municipal, agregados por bairro, mês e hexágono, e o índice de risco por bairro; grava `relatorios/seguranca.md` |

Os arquivos vêm do portal (o mais recente de cada base, achado pelo cliente `etl/portal.py`) ou de `dados/bruto/<fonte>/`, se você já tiver baixado.

### Alvarás x CNPJ

A Base de Alvarás não tem CNPJ. O cruzamento (`sql/50_alvaras.sql`) procura a empresa no mesmo CEP e logradouro e pontua de 0 a 1:

| Componente | Peso |
|---|---|
| Similaridade de nome (melhor par entre nome empresarial/fantasia do alvará e razão social/fantasia da empresa) | 0,5 |
| CNAE principal igual | 0,25 |
| Mesma data de início de atividade | 0,25 |

Mesmo número de porta vale pontuação cheia (`mesmo_endereco`); só a mesma rua, 80% (`mesma_rua`). O par é aceito a partir de 0,5, e cada alvará e cada CNPJ entram em um par só. MEI, que não tem razão social no banco (LGPD), casa por nome fantasia, CNAE e data.

| Tabela | Conteúdo |
|---|---|
| `alvara` | Alvarás com nome fantasia, datas de início, emissão e expiração, endereço, CNAE principal e secundários, geocodificação. **Sem nome empresarial**: no MEI ele é o nome da pessoa, e só existe numa tabela temporária durante o cruzamento |
| `alvara_cnpj` | Par alvará x CNPJ com método, pontuação, similaridade de nome, CNAE igual e data igual |
| `empresa_alvara` | Sinais por CNPJ: `tem_alvara`, `ativa_sem_alvara` (ativa em ponto comercial, fora de domiciliação, sem alvará), `alvara_de_cnpj_encerrado`, `alvara_vencido`, `atividade_diverge` (classe CNAE diferente), `chegada_ao_endereco` (início no alvará posterior à abertura do CNPJ) |
| `alvara_sem_cnpj` (view) | Alvarás sem par: fora do recorte, CNPJ de outra cidade ou nome muito diferente |

Para refazer o cruzamento depois de atualizar o M0, rode `python -m etl.m1 --so alvaras` de novo: o arquivo já baixado é reaproveitado.

### Demais bases do M1

| Tabela | Conteúdo | Observações |
|---|---|---|
| `contrato_pmc_item` | Itens de licitação e contratação: órgão, processo, modalidade, item, quantidade, CNPJ, contrato, vigência, valores | Fornecedor pessoa física fica com `cnpj` nulo e sem nome (LGPD) |
| `empresa_contratos_pmc` | Por CNPJ: contratos, itens, valor total, contratos vigentes, fim do último contrato, se tem estabelecimento em Curitiba | Fornecedor da prefeitura é lead e sinal de capacidade |
| `siac156_bairro_mes` | Pedidos ao 156 por bairro, regional, mês, tipo e assunto, com quantos foram respondidos e o tempo mediano de resposta | Zeladoria e problemas urbanos por bairro |
| `sigmu_bairro_mes` | Pedidos de manutenção urbana por bairro, mês e serviço, com quantos foram realizados e o tempo mediano | Da SIGMU só entram `SERVICO_SOLICITADO` e `SERVICO_TAB`; texto livre e solicitante ficam de fora |
| `unidade_atendimento` | Equipamentos públicos e privados com tema, tipo, dependência administrativa, turnos e localização | Sem CEP na base: geocodificação pelos níveis sem CEP |
| `onibus_ponto`, `onibus_h3` | Pontos de ônibus com número de linhas e de partidas no feed; soma por hexágono | O portal não publica arquivo do transporte: o ETL lê um GTFS em `dados/bruto/urbs_gtfs/` (ver pedido 6 em `docs/pedidos-lai.md`) |

### Segurança e índice de risco

O SiGesGuarda traz o fato, sem pessoa: código, data, hora, bairro, regional, rua (sem número), até cinco naturezas, marca de defesa civil, equipamento urbano e flagrante. Linhas repetidas do mesmo código viram uma ocorrência com todas as naturezas.

**Categorias.** Cada natureza vira uma categoria pela tabela `natureza_categoria` (regex sobre o texto normalizado, o primeiro padrão por `ordem` vence). Ocorrência com marca de defesa civil também conta como `fisico`. A tabela é editável e a carga não sobrescreve linhas alteradas; `relatorios/seguranca.md` lista as naturezas que caíram em `outros` para ajustar.

| Categoria | Exemplos |
|---|---|
| `violento` | roubo, assalto, agressão, lesão corporal, ameaça, arma, briga |
| `patrimonial` | furto, arrombamento, dano, depredação, pichação, invasão |
| `fisico` | alagamento, destelhamento, queda de árvore, incêndio, deslizamento |
| `transito` | acidente, atropelamento, colisão |
| `ordem_publica` | perturbação do sossego, drogas, ambulante, desordem |

**Localização.** Sem número, o ponto é o endereço do CNEFE mais perto do centro da rua dentro do bairro (`logradouro_no_bairro`). Sem a rua no bairro, fica o ponto do bairro (`bairro`), que não entra em análise por hexágono com a mesma confiança.

**Índice.** Janela de 12 meses que termina no último mês com dado. Por bairro do IPPUC e categoria, `risco_bairro` guarda ocorrências, área, empresas ativas, taxa por km², taxa por mil empresas ativas e o percentil entre os bairros (0 a 100):

- `patrimonial` usa a taxa por mil empresas ativas (risco para o comércio estabelecido);
- as demais usam a taxa por km², até o Censo por setor entrar (#16) e dar a taxa por habitante.

`risco_bairro_indice` junta os percentis de patrimonial, violento e físico e o `indice` (média dos três). Tudo é agregado por território. A coluna `fonte` de `seguranca_ocorrencia` recebe CAPE, Bombeiros e Defesa Civil quando os pedidos de LAI forem respondidos, e o índice passa a somar as fontes sem mudar.

| Tabela | Conteúdo |
|---|---|
| `seguranca_ocorrencia` | Uma linha por ocorrência e fonte: data, hora, bairro, rua, naturezas, categorias, localização, `h3_9` |
| `seguranca_bairro_mes` | Ocorrências por fonte, bairro, mês e categoria (série completa) |
| `seguranca_h3` | Ocorrências por hexágono e categoria na janela de 12 meses |
| `risco_bairro`, `risco_bairro_indice` | Taxas, percentis e índice por bairro |

### Listas com CNPJ (M1b)

Listas federais e estaduais que dizem algo da empresa: exporta, tem crédito do BNDES, licença ambiental, inspeção federal, cadastro turístico, é provedor de internet, hospital ou posto. Os hosts desses órgãos mudam de endereço e de layout, então o download é manual: baixe o CSV na página do campo `url` do `catalogo.yaml` e coloque em `dados/bruto/<lista>/` (vários arquivos por lista são somados; zip com um CSV também serve; planilha `.xlsx`, salve como CSV).

| Lista | Nível | Data | Valor | Rótulo |
|---|---|---|---|---|
| `mdic_exportadoras` | empresa | ano | | faixa de valor |
| `bndes_operacoes` | empresa | contratação | soma do contratado | produto |
| `ibama_ctf` | empresa | início da atividade | | categoria |
| `iat_licencas` | estabelecimento | validade | | tipo de licença (pedido 12 da LAI se não houver arquivo) |
| `cadastur` | estabelecimento | validade do certificado | | atividade |
| `anatel_scm` | empresa | mês | soma dos acessos | tecnologia |
| `mapa_sif` | estabelecimento | | | classificação |
| `emec` | empresa (mantenedora) | início do funcionamento | | organização acadêmica |
| `cnes` | estabelecimento | atualização | | tipo de unidade |
| `anp_revendas` | estabelecimento | coleta | preço médio | produto |

**Leitura tolerante.** A coluna do CNPJ, da data, do valor e do rótulo é a primeira que existir numa lista de nomes possíveis (`LISTAS` em `etl/fontes/listas_cnpj.py`); cabeçalho normalizado, separador e codificação detectados. O log diz qual coluna foi usada em cada arquivo. Se um órgão mudar o nome da coluna, acrescente o nome novo na lista.

**Casamento.** O CNPJ passa pelo dígito verificador (zeros à esquerda perdidos numa planilha são repostos quando a coluna é só de CNPJ). Lista de estabelecimento casa pelo CNPJ igual; lista de empresa casa pela raiz e vale para todas as unidades de Curitiba. Só entram linhas de empresas do recorte.

**LGPD.** Linha com CPF não entra. Colunas de CPF, e-mail, telefone, responsável, representante, sócio e contato não vão para `atributos`.

| Tabela | Conteúdo |
|---|---|
| `lista_registro` | Linhas casadas: lista, arquivo, CNPJ (ou só a raiz), rótulo, data, valor e as demais colunas em `atributos` (jsonb) |
| `empresa_lista` | Por CNPJ de Curitiba e lista: `via` (`cnpj` ou `raiz`), registros, valor, primeira e última data, até 5 rótulos |

---

## Rodando o M2

Depois do M0:

```bash
python -m etl.m2
```

| Etapa | Comando isolado | O que faz |
|---|---|---|
| `apoio` | `python -m etl.fontes.apoio` | Hierarquia CNAE (API do IBGE; reserva em `dados_rfb.cnae`) e natureza jurídica |
| `censo` | `python -m etl.fontes.ibge_censo_setor [--arquivo ...]` | Censo 2022 por setor (temas básico, demografia, renda do responsável), moradores distribuídos pelos domicílios do CNEFE e espaço livre por bairro; grava `relatorios/demanda.md`. Precisa do FTP do IBGE ou dos zips em `dados/bruto/ibge_censo_setor/` |
| `cruzamentos` | `python -m etl.fontes.mindata_cruzamentos` | PNCP, TCE-PR, PGFN e sanções federais por CNPJ, das tabelas da MINDATA; tabela ausente é pulada |
| `edificacoes` | `python -m etl.fontes.overture_edificacoes` | Edificações do Overture por hexágono H3 (área construída estimada). Precisa de internet; `--arquivo` aceita GeoParquet já baixado |
| `enriquecer` | `python -m etl.enriquecer` | Perfil do ponto, domiciliação, rede, histórico do ponto, uso x zoneamento; grava `relatorios/enriquecimento.md` |
| `indicadores` | `python -m etl.indicadores` | Saturação, sobrevivência, densidade, movimentos e a função `raio_x`; grava `relatorios/indicadores.md` |
| `exportar` | `python -m etl.exportar` | GeoParquet em `dados/exportar/` para QGIS, Kepler.gl ou Lonboard |

```bash
python -m etl.m2 --pular edificacoes       # sem internet
python -m etl.m2 --so enriquecer --so indicadores --so exportar
```

### O que cada indicador responde

| Tabela ou função | Pergunta |
|---|---|
| `empresa_perfil.tipo_ponto` | A empresa está em ponto comercial, em casa (`residencial`) ou num prédio misto? |
| `empresa_perfil.domiciliacao` | O endereço é de contabilidade ou escritório virtual (20+ CNPJs ativos)? Essas empresas saem dos indicadores por bairro |
| `empresa_perfil.ativos_da_raiz_na_cidade`, `filial` | É rede ou independente? Quantos pontos tem na cidade? |
| `ponto_comercial` | Quantos CNPJs já passaram pelo endereço, com que rotatividade, e se está vago (sem ativos, último encerramento nos últimos 3 anos) |
| `uso_zoneamento` | A atividade é permitida na zona? Só onde há regra em `zona_regra` (preencher a partir da Lei de Zoneamento) |
| `m2_saturacao_bairro.ql` | O bairro concentra a atividade mais que a cidade (QL > 1) ou tem espaço livre (QL < 1)? |
| `m2_sobrevivencia` | Quantas empresas abertas em cada ano seguem vivas 1, 3 e 5 anos depois, por divisão CNAE |
| `m2_densidade_h3` | Quantas empresas ativas há em cada hexágono de cerca de 0,1 km², por divisão |
| `m2_movimento` | Aberturas, fechamentos, reativações, saídas do recorte e mudanças de endereço ou CNAE entre competências |
| `raio_x(lat, lon, raio_m)` | O que há num raio do ponto, por divisão, e quanto isso está acima ou abaixo da densidade média da cidade (índice 100 = média). Com o Censo: moradores no raio, empresas por mil moradores no raio e na cidade, e `indice_moradores` (< 100 = menos oferta por morador que a média) |
| `moradores_raio(lat, lon, raio_m)` | Moradores, domicílios e renda média do responsável num raio |
| `setor_demografia` | Por setor: pessoas, domicílios, faixas de idade, renda média do responsável, densidade, dependência e envelhecimento, bairro |
| `demanda_h3` | Moradores, domicílios, crianças, idosos e renda por hexágono |
| `m2_espaco_livre` | Por bairro e classe CNAE de comércio e serviço ao morador: empresas ativas, esperadas pela média da cidade por morador, lacuna e índice. Onde falta farmácia, academia, pet shop |
| `empresa_sinais` | Contratos públicos (PNCP, TCE-PR), dívida ativa da União e sanções federais de cada CNPJ |
| `edificacao_h3` | Área construída por hexágono, proxy de densidade urbana |

```sql
-- o que há num raio de 250 m da Praça Tiradentes
SELECT * FROM raio_x(-25.4284, -49.2733, 250);
```

### Demanda: Censo 2022 por setor

Os agregados por setor do IBGE são nacionais, um zip por tema. Ficam só os setores de Curitiba. Toda coluna `V####` vai para `censo_setor_var` (formato longo); `censo_variavel` diz qual variável vira qual indicador. Os códigos de lá seguem a documentação do IBGE, mas **confira com o dicionário de cada tema** na primeira carga: o relatório lista as variáveis mapeadas que não vieram, e a tabela é editável.

A população de cada setor é distribuída pelos endereços de domicílio do CNEFE (espécies 1 e 2): dá moradores por hexágono e no raio sem supor população uniforme no setor. Setor sem domicílio no CNEFE fica inteiro no ponto interno (no hexágono) ou pela fração da área (no raio).

`m2_espaco_livre` compara, por bairro, as empresas ativas de cada classe de comércio e serviço ao morador (divisões 47, 56, 75, 85, 86, 93, 95, 96) com as esperadas se o bairro tivesse a mesma oferta por morador da cidade. Mede só moradores: o Centro, com fluxo de quem trabalha e passa, aparece saturado e é normal.

```sql
-- quantos moradores e qual renda num raio de 500 m
SELECT * FROM moradores_raio(-25.4284, -49.2733, 500);
-- onde faltam farmácias (classe 47717)
SELECT bairro, ativos, esperado, lacuna FROM m2_espaco_livre WHERE classe = '47717' ORDER BY lacuna DESC LIMIT 10;
```

### Área de influência: isócronas a pé e de ônibus

Sem serviço pago nem servidor de rotas: a rede de caminhada fica no próprio banco e o cálculo é em Python.

```bash
# 1. rede (uma vez): recorte Sul do OSM, do Geofabrik (~350 MB), ou --arquivo com os eixos do IPPUC
python -m etl.fontes.osm_vias
# 2. isócronas a pé de 5, 10 e 15 min
python -m etl.isocronas --lat -25.4284 --lon -49.2733
# 3. de ônibus + caminhada, saindo numa quinta às 8h (GTFS em dados/bruto/urbs_gtfs/)
python -m etl.isocronas --lat -25.4284 --lon -49.2733 --modo onibus --minutos 15 30 --saida "2026-10-08 08:00"
```

| Peça | Como funciona |
|---|---|
| Rede (`via_no`, `via_aresta`) | Do `.osm.pbf`, só a camada `lines` no retângulo da cidade, sem autoestrada, canaleta exclusiva, obra ou `foot=no`. As linhas são nodadas no PostGIS; o maior componente conexo é marcado (`principal`) e só ele serve de partida |
| A pé | Dijkstra a 4,8 km/h (80 m por minuto) a partir do nó mais perto do ponto |
| Ônibus | Caminha até os pontos, embarca nas viagens do dia (calendário do GTFS) que partem na janela, com transferência a pé entre pontos a até 300 m (Connection Scan), e caminha de cada ponto alcançado com o tempo que sobra |
| Área | União das ruas alcançadas com 40 m de cada lado, gravada em `isocrona` (modo, minutos, ponto, saída) |
| Raio-x | `raio_x_area(geom)` tem as colunas de `raio_x` para qualquer polígono; `moradores_area(geom)` dá moradores, domicílios e renda |

```sql
SELECT * FROM raio_x_area((SELECT geom FROM isocrona WHERE id = 1));
SELECT * FROM moradores_area((SELECT geom FROM isocrona WHERE id = 1));
```

Limites: viaduto vira cruzamento na nodagem (para caminhada é aceitável); o tempo de ônibus é o da tabela do GTFS, sem trânsito real nem espera além do horário.

`m2_movimento` só tem eventos a partir da segunda foto mensal. Rode `python -m etl.fontes.cnpj_recorte` a cada atualização da base da Receita (ou `python -m etl.m0 --so cnpj`) para acumular competências.

---

## O que sai no banco

No schema do Pineal (`cwb` por padrão):

| Tabela | Conteúdo | Chave |
|---|---|---|
| `setor` | Setores censitários 2022, atributos originais em `atributos` (jsonb) | `cd_setor` |
| `bairro`, `regional`, `zoneamento` | Camadas do IPPUC: `codigo`, `nome`, `atributos`, `geom` | |
| `cnefe` | Endereços do CNEFE com coordenada, chaves de logradouro, número, espécie, nome do estabelecimento | `cod_unico` |
| `empresa` | Recorte de `dados_rfb.cnpj_consolidado`, com datas em `DATE`, `pessoa_fisica` e `cpf_mascarado` | `cnpj` |
| `empresa_historico` | Foto mensal do recorte (situação, datas, CNAE, porte, chave do endereço) | `competencia`, `cnpj` |
| `empresa_geo` | Localização e chave territorial: `geom`, `geo_precisao`, `cd_setor`, `bairro`, `regional`, `zona`, `h3_8`, `h3_9` | `cnpj` |
| `empresa_perfil`, `ponto_comercial`, `uso_zoneamento` | Enriquecimento (ver [Rodando o M2](#rodando-o-m2)) | |
| `m2_*`, `raio_x()` | Indicadores do M2 | |
| `empresa_sinais`, `edificacao_h3` | Cruzamentos e edificações | |
| `alvara*`, `contrato_pmc_item`, `siac156_*`, `sigmu_*`, `unidade_atendimento`, `onibus_*` | Bases da prefeitura (ver [Rodando o M1](#rodando-o-m1)) | |
| `seguranca_*`, `risco_bairro*`, `natureza_categoria` | Segurança e índice de risco | |
| `lista_registro`, `empresa_lista` | Listas com CNPJ (M1b) | |
| `censo_*`, `setor_demografia`, `setor_h3_domicilio`, `demanda_h3` | Censo 2022 por setor e demanda | |
| `via_no`, `via_aresta`, `isocrona` | Rede de caminhada e isócronas | |
| `cnae`, `natureza_juridica`, `porte`, `situacao_cadastral`, `zona_regra` | Tabelas de apoio | |
| `execucao` | Cada carga e cada etapa: `run_id`, `tipo`, `status`, `duracao_s`, `erro`, origem, arquivo, sha256, linhas | `id` |

Funções de normalização, usadas nos dois lados de todo cruzamento:

| Função | Exemplo |
|---|---|
| `norm_logradouro(text)` (chave curta) | `'R. MAL. FLORIANO PEIXOTO'` e `'Rua Marechal Floriano Peixoto'` viram `'FLORIANO PEIXOTO'` |
| `norm_logradouro_completa(text)` | `'R DR FAIVRE'` vira `'DOUTOR FAIVRE'`; `'R. São José'` e `'R. José'` continuam diferentes |
| `norm_nome(text)` | `'PADARIA PAO DOURADO LTDA - ME'` vira `'PADARIA PAO DOURADO'` |
| `norm_numero(text)` | `'1234-A'` vira `1234`; `'S/N'` e `'0'` viram `NULL` |
| `norm_cep(text)` | `'80.010-000'` vira `'80010000'`; `'00000000'` vira `NULL` |
| `data_rfb(text)` | `'20230115'` vira `2023-01-15`; `'20230231'` e `'00000000'` viram `NULL` |
| `mascarar_cpf(cpf_no_texto(text))` | `'JOAO DA SILVA 12345678901'` vira `'***.456.789-**'` |

---

## Geocodificação: como ler os níveis

Cada CNPJ fica com o primeiro nível que casar, do mais preciso ao menos preciso. `geo_precisao` diz qual foi.

| Nível | Regra | Serve para |
|---|---|---|
| `estabelecimento` | Mesmo CEP, nome do estabelecimento no CNEFE parecido com o nome fantasia ou a razão social (trigramas ≥ 0,5 na mesma rua, ou ≥ 0,7 em qualquer rua do CEP) | Quadra, raio de 250 m |
| `endereco` | CEP, logradouro e número iguais aos do CNEFE | Quadra, raio de 250 m |
| `endereco_sem_cep` | Logradouro (chave completa) e número iguais, CEP diferente, pontos a menos de 300 m entre si | Quadra |
| `numero_proximo` | Mesmo CEP e logradouro, número mais próximo do mesmo lado da rua a até 30 de diferença | Quadra |
| `logradouro` | Mesmo CEP e logradouro, sem número que case | Setor e bairro |
| `logradouro_aproximado` | Mesmo CEP, nome da rua parecido (trigramas ≥ 0,6) | Setor e bairro |
| `logradouro_sem_cep` | Logradouro (chave completa) único na cidade, pontos a menos de 1,5 km entre si | Bairro |
| `cep` | Ponto central do CEP, só quando o CEP cobre menos de 1,5 km | Bairro e regional |
| `bairro` | Bairro declarado à Receita casado pelo nome com o bairro do IPPUC | Bairro e regional |
| `nao_localizado` | Nenhum dos anteriores | Fora das análises por área |

**Duas chaves de logradouro.** A curta tira títulos ("Dr.", "São", "Presidente") e só é usada quando o CEP já confirma a rua. Os níveis sem CEP usam a completa, com os títulos por extenso, para "R. São José" e "R. José" não virarem a mesma rua.

Relatórios:
- `relatorios/geocodificacao.md`: quantos CNPJs caíram em cada nível, todos e só ativos, com o acumulado.
- `relatorios/erro_geocodificacao.md`: erro em metros por nível (ver [passo 4](#4-erro-da-geocodificação-em-metros)).
- `relatorios/territorio.md`: preenchimento da chave territorial e a concordância entre o bairro declarado à Receita e o bairro calculado, por nível.

Ponto na divisa entre dois polígonos, ou dentro de zonas que se sobrepõem, fica com o menor polígono (o mais específico) e, no empate, o menor código: o resultado não varia entre rodadas.

---

## Catálogo de fontes

`catalogo.yaml` é o inventário único: as 63 fontes mapeadas, com dono, fase, status, chaves de cruzamento e, quando há script, onde baixar. `docs/fontes.md` explica o porquê de cada uma. `docs/pedidos-lai.md` tem os rascunhos dos pedidos via Lei de Acesso à Informação.

| Status | Significado |
|---|---|
| `ativo` | Script pronto e conferido |
| `a_conferir` | Script ou link pronto; formato e colunas se confirmam na primeira rodada |
| `planejado` | Mapeada, sem script |
| `lai` | Só sai por pedido de acesso à informação |
| `convenio` | Depende de parceria (ex.: Waze for Cities) |
| `fora` | Mapeada e descartada, com o motivo em `obs` (ex.: Ookla, licença não comercial) |

Para adicionar uma fonte:
1. Inclua a entrada no `catalogo.yaml` (`id`, `nome`, `dono`, `fase`, `status`, `chaves` e onde baixar: `url`, `url_diretorio` + `padrao_arquivo` ou `portal_chave`).
2. Crie `etl/fontes/<id>.py` seguindo os existentes: `main()` dentro de `db.etapa(...)`, baixa com `baixar.baixar`, grava substituindo o conteúdo da tabela e registra com `db.registrar`. Não use o nome do schema no SQL: o `search_path` já aponta para ele.
3. Se a fonte tiver endereço ou nome, normalize com as funções `norm_*` para cruzar com o CNEFE e com os CNPJs.

---

## Testes e CI

Os testes de banco precisam de um PostgreSQL com PostGIS descartável. Eles usam o schema `teste_pineal`, que é apagado e recriado; o `dados_rfb` falso dos testes também é apagado.

```bash
createdb -U postgres pineal_teste
# no .env, ou no terminal:
#   PINEAL_TEST_DSN="host=localhost port=5432 dbname=pineal_teste user=postgres password=..."
pytest
ruff check . && ruff format --check .
```

Sem `PINEAL_TEST_DSN`, só os testes sem banco rodam e os demais são pulados. No GitHub, o workflow `.github/workflows/testes.yml` sobe um `postgis/postgis:16-3.4` e roda `ruff` e `pytest` com o banco a cada PR, então nada é pulado.

| Arquivo | Cobre |
|---|---|
| `tests/test_normalizacao.py` | Chaves curta e completa, colisões de título, nome, número, CEP, datas, máscara de CPF |
| `tests/test_geocodificar.py` | Cada nível da geocodificação, erro em metros, chave territorial com H3, desempate na divisa e em zonas sobrepostas |
| `tests/test_leitura.py` | Leitura do CNEFE (zip, Latin-1, vírgula decimal, filtro de município), links do portal, descrição de CSV sem vazar valores |
| `tests/test_m2.py` | Perfil do ponto, domiciliação, rede, ponto vago, zoneamento, QL, coortes, densidade, raio-x, movimentos entre competências, apoio, cruzamentos, edificações, exportação sem dados pessoais |
| `tests/test_portal.py` | Cliente do portal: metadados, colunas e lista de arquivos no formato real |
| `tests/test_m1.py` | Alvarás (carga em Windows-1252 com `;`, cruzamento, sinais, LGPD), licitações, 156, SIGMU, unidades, GTFS e o orquestrador do M1 |
| `tests/test_m0.py` | M0 e M2 de ponta a ponta com shapefile zipado, camada sem `.prj`, GeoJSON, GPKG, CNEFE e um `cnpj_consolidado` falso: LGPD, datas, schema configurável, `run_id`, etapa com erro registrada, segunda rodada sem duplicar |

---

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `nenhum arquivo casa com /.../` no IBGE | O IBGE mudou nome ou pasta | Baixe à mão e use `--arquivo`, ou ajuste `url_diretorio` e `padrao_arquivo` no `catalogo.yaml` |
| `colunas obrigatórias ausentes no CNEFE` | Layout do CNEFE diferente do esperado | A mensagem lista o cabeçalho encontrado; ajuste `OBRIGATORIAS` e `linhas_saida` em `etl/fontes/ibge_cnefe.py` |
| `camada X: defina campo_nome` | Coluna do nome não detectada no arquivo do IPPUC | Rode `python -m etl.fontes.ippuc --listar` e preencha `campo_nome` no catálogo |
| Bairros fora de Curitiba no mapa | Arquivo sem `.prj` em outro sistema de coordenadas | Ajuste `crs_padrao` (ex.: 29192 para SAD69 / UTM 22S) |
| `recorte vazio` no CNPJ | Código do município diferente na base RFB | Confira com `SELECT DISTINCT municipio, nome_municipio FROM dados_rfb.cnpj_consolidado WHERE uf = 'PR' AND nome_municipio ILIKE 'curitiba%'` e ajuste `PINEAL_COD_RFB` |
| `permission denied to create extension` | Usuário sem permissão | Peça ao DBA para criar as extensões (ver [Requisitos](#requisitos)) |
| `cnefe vazio` ao geocodificar | Etapa `cnefe` não rodou | `python -m etl.m0 --so cnefe` |
| Muitos `nao_localizado` | CEP genérico ou logradouro muito diferente do CNEFE | Veja amostras com `SELECT e.logradouro, e.numero, e.cep FROM empresa e JOIN empresa_geo g USING (cnpj) WHERE g.geo_precisao = 'nao_localizado' LIMIT 50` e amplie as listas em `sql/01_normalizacao.sql` |
| Concordância de bairro baixa em todos os níveis | Nomes de bairro diferentes entre Receita e IPPUC | Compare `SELECT DISTINCT bairro FROM empresa` com `SELECT nome FROM bairro` |
| `empresa_perfil não existe` | `indicadores` antes de `enriquecer` | `python -m etl.m2 --so enriquecer --so indicadores` |
| `não listei as releases do Overture` | Sem acesso ao bucket público do Overture | Informe `--release` ou `release` no catálogo, ou pule com `python -m etl.m2 --pular edificacoes` |
| Uma etapa falhou e não sei qual | | `SELECT fonte, erro FROM execucao WHERE status = 'erro' ORDER BY id DESC` |

---

## Estrutura do repositório

```
pineal-curitiba/
├── catalogo.yaml              inventário das fontes (lido pelos scripts)
├── pyproject.toml             dependências com versão fixa, ruff, pytest
├── .env.example
├── docker-compose.yml         PostGIS local opcional
├── .github/workflows/         CI: ruff + pytest com PostGIS
├── docs/
│   ├── fontes.md              fontes comentadas, por tema
│   └── pedidos-lai.md         rascunhos dos pedidos de acesso à informação
├── sql/
│   ├── 00_schema.sql          tabelas
│   ├── 01_normalizacao.sql    normalização de endereço, nome, datas, máscara de CPF
│   ├── 02_apoio.sql           porte, situação, CNAE, natureza jurídica, regras de zoneamento
│   ├── 10_geocodificar.sql    núcleo da geocodificação em níveis
│   ├── 05_m1_schema.sql       tabelas e funções do M1 (datas, CNAE e valores do portal)
│   ├── 06_censo_schema.sql    tabelas do Censo por setor e moradores_raio
│   ├── 07_rede_schema.sql     rede de caminhada, isócronas e moradores_area
│   ├── 20_territorio.sql      chave territorial com desempate
│   ├── 30_enriquecimento.sql  perfil do ponto, domiciliação, rede, ponto comercial, zoneamento
│   ├── 40_m2.sql              saturação, sobrevivência, densidade, movimentos, raio_x
│   ├── 50_alvaras.sql         cruzamento alvará x CNPJ e sinais
│   ├── 60_seguranca.sql       agregados de segurança e índice de risco por bairro
│   └── 70_demanda.sql         demografia por setor, demanda por hexágono, espaço livre
├── etl/
│   ├── config.py, db.py       .env, schema, run_id, conexão, registro de etapas e cargas
│   ├── baixar.py, geo.py      download com cache; leitura de camadas vetoriais
│   ├── fontes/                ibge_setores, ibge_cnefe, ippuc, cnpj_recorte, portal_inventario,
│   │                          apoio, mindata_cruzamentos, overture_edificacoes, pmc_alvaras,
│   │                          pmc_licitacoes, pmc_zeladoria, pmc_unidades, urbs_gtfs,
│   │                          pmc_sigesguarda, listas_cnpj, ibge_censo_setor, osm_vias
│   ├── geocodificar.py, avaliar_geocodificacao.py, territorio.py
│   ├── enriquecer.py, indicadores.py, exportar.py
│   ├── isocronas.py           isócronas a pé e de ônibus
│   ├── portal.py, leitura.py  cliente do portal da prefeitura; leitura de CSV grande
│   └── m0.py, m1.py, m2.py    orquestradores
├── tests/
├── dados/                     arquivos baixados e exportados (fora do git)
└── relatorios/                relatórios gerados (fora do git)
```

---

## Dados pessoais e licenças

- **Pessoa física não tem nome no banco.** Quando o CNPJ é de MEI ou empresário individual (natureza 2135), a razão social, que é o nome da pessoa, não é gravada: fica `NULL`, com `pessoa_fisica = true`. O CPF que a Receita põe no fim da razão social fica só mascarado (`***.456.789-**`). Nome fantasia com CPF dentro também não é gravado. Os dados passam por uma tabela temporária e nunca chegam inteiros à tabela final.
- **Indicadores e exportações não têm nome, razão social nem CPF**: só código de atividade, situação, território e contagens. Saúde, segurança e benefícios entram só agregados por território.
- `dados/` e `relatorios/` estão no `.gitignore`: dados baixados e resultados não vão para o git.
- Mapa Cadastral e Guia Amarela do IPPUC são consultas por lote: usar sob demanda, sem raspagem em massa.
- Licenças: o Portal de Dados Abertos de Curitiba publica sob **CC BY 4.0**; Overture e OpenStreetMap sob **ODbL**. Qualquer uso público cita a fonte. IBGE, Receita e demais fontes federais são dados abertos com atribuição. Ookla ficou de fora por proibir uso comercial.
