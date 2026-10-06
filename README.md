# Pineal Curitiba

Funil de inteligência territorial B2B para Curitiba. Cruza a base de empresas da MINDATA (CNPJ, CNAE, porte, situação) com dados públicos gerais (IBGE, Receita, CAGED) e com as fontes oficiais da cidade (IPPUC, Portal de Dados Abertos da prefeitura, segurança pública), sempre pela mesma chave territorial.

É o piloto municipal do módulo Pineal (Inteligência Comercial), planejado em [mdrrv/mindata-data-monetization#251](https://github.com/mdrrv/mindata-data-monetization/issues/251). Roda local primeiro; a estrutura de plataforma vem depois.

---

## Sumário

- [Como funciona](#como-funciona)
- [Estado atual e fases](#estado-atual-e-fases)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Rodando o M0](#rodando-o-m0)
- [O que sai no banco](#o-que-sai-no-banco)
- [Geocodificação: como ler os níveis](#geocodificação-como-ler-os-níveis)
- [Catálogo de fontes](#catálogo-de-fontes)
- [Testes](#testes)
- [Problemas comuns](#problemas-comuns)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Dados pessoais e licenças](#dados-pessoais-e-licenças)

---

## Como funciona

```
 fontes                    bruto                  padronizado (schema cwb)                produto
 ───────                   ─────                  ────────────────────────                ───────
 IBGE (setores, CNEFE)  ─┐                        território: setor, bairro,
 IPPUC (bairros, zonas) ─┤  dados/bruto/<fonte>/  regional, zoneamento                    agregados por
 RFB (cnpj_consolidado) ─┼─▶ arquivo original  ─▶ empresas geocodificadas com chave  ─▶  território (M2)
 Portal da prefeitura   ─┤  + sha256 + registro   territorial (setor, bairro, regional,   mapa local e
 Segurança, LAI, ...    ─┘  em cwb.execucao       zona, H3 8 e 9)                         plataforma (M3)
```

1. **Bruto.** Cada fonte é baixada uma vez para `dados/bruto/<fonte>/`. Cada carga fica registrada em `cwb.execucao` com origem, arquivo, hash e número de linhas.
2. **Padronizado.** Tudo vai para o schema `cwb` do PostGIS, em coordenadas geográficas (EPSG:4326). Endereços passam pela mesma normalização dos dois lados do cruzamento.
3. **Chave territorial.** Todo registro com coordenada recebe setor censitário 2022, bairro do IPPUC, regional, zona de uso do solo e hexágonos H3 (resolução 8, cerca de 0,7 km², e 9, cerca de 0,1 km²). Cruzar fontes vira juntar pela chave.

---

## Estado atual e fases

| Fase | Conteúdo | Situação |
|---|---|---|
| **M0** Fundação territorial | Setores IBGE, camadas IPPUC, CNEFE, recorte de CNPJs, geocodificação, chave territorial | **Scripts prontos e testados com dados sintéticos.** Falta a primeira rodada com dados reais |
| M1 Prefeitura e IPPUC | Alvarás (cruzamento CNPJ × alvará), licitações, 156, SIGMU, unidades de atendimento, transporte | Inventário pronto (`portal_inventario`); ETLs depois do inventário |
| M1-seg Segurança | CAPE/SESP-PR, Guarda Municipal, Bombeiros, Defesa Civil | Pedidos via LAI em rascunho |
| M1b Listas com CNPJ | MDIC, BNDES, IBAMA, IAT, CADASTUR, ANATEL, MAPA, e-MEC, CNES, ANP | Planejado |
| M2 Agregados e mapa local | Saturação por bairro, aberturas e fechamentos, raio-x de endereço, divergências CNPJ × alvará | Planejado |
| M3 Plataforma | Publicação dos agregados no módulo Pineal | Planejado |

---

## Requisitos

- **Python 3.11 ou mais novo.**
- **PostgreSQL 14+ com PostGIS 3** e as extensões `unaccent` e `pg_trgm` (vêm no pacote contrib do Postgres).
  - Windows: instale o PostGIS pelo Stack Builder que acompanha o instalador do PostgreSQL.
  - Sem Postgres local: `docker compose up -d` sobe um PostGIS na porta 5433 (ver `docker-compose.yml`).
- **Banco do ETL da MINDATA** com `dados_rfb.cnpj_consolidado` populado, para o recorte de CNPJs. Pode ser o mesmo servidor e até o mesmo banco do Pineal.
- Não precisa de GDAL instalado: o `pyogrio` já traz o necessário.
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
pip install -r requirements.txt
copy .env.example .env
```

Linux e macOS:

```bash
git clone https://github.com/mdrrv/pineal-curitiba.git
cd pineal-curitiba
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

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
| `RFB_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | Banco com `dados_rfb.cnpj_consolidado` | Sem `RFB_DB_NAME`, usa o banco do Pineal |
| `RFB_DSN` | Alternativa: DSN completo do banco RFB | |
| `PINEAL_COD_IBGE` | Código IBGE do município | `4106902` |
| `PINEAL_COD_RFB` | Código do município na Receita (coluna `municipio` do consolidado) | `7535` |
| `PINEAL_NOME_MUNICIPIO`, `PINEAL_UF` | Filtro de reserva pelo nome do município | `CURITIBA`, `PR` |
| `PINEAL_DADOS` | Pasta dos arquivos baixados | `./dados` |
| `PINEAL_TEST_DSN` | Banco descartável para os testes | |

O recorte de CNPJs usa `uf = PINEAL_UF AND (municipio = PINEAL_COD_RFB OR upper(nome_municipio) = PINEAL_NOME_MUNICIPIO)`. Para outra cidade, troque as quatro variáveis do município e os padrões de arquivo no `catalogo.yaml`.

---

## Rodando o M0

### 1. Inventário do portal da prefeitura (opcional, recomendado)

```bash
python -m etl.fontes.portal_inventario            # só os links de download de cada base
python -m etl.fontes.portal_inventario --baixar   # baixa e descreve colunas e preenchimento
```

Gera `relatorios/inventario_portal.md`. É aqui que se confirma se a Base de Alvarás traz CNPJ, o que define o desenho do M1. O relatório mostra só nomes de colunas e porcentagem de preenchimento, nunca valores.

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

Sem essas camadas o M0 roda do mesmo jeito: `bairro`, `regional` e `zona` ficam vazios até a camada ser carregada.

### 3. M0 completo

```bash
python -m etl.m0
```

Etapas, nesta ordem:

| Etapa | Comando isolado | O que faz |
|---|---|---|
| `schema` | | Cria o schema `cwb`, as tabelas e as funções de normalização |
| `setores` | `python -m etl.fontes.ibge_setores` | Acha o zip do PR no FTP do IBGE, baixa e grava os setores de Curitiba |
| `ippuc` | `python -m etl.fontes.ippuc` | Grava bairros, regionais e zoneamento a partir de `dados/bruto/ippuc/` |
| `cnefe` | `python -m etl.fontes.ibge_cnefe` | Acha o CSV do CNEFE de Curitiba no FTP do IBGE, baixa e grava os endereços com coordenada |
| `cnpj` | `python -m etl.fontes.cnpj_recorte` | Copia os estabelecimentos de Curitiba de `dados_rfb.cnpj_consolidado`, em todas as situações cadastrais |
| `geocodificar` | `python -m etl.geocodificar` | Localiza cada CNPJ pelo CNEFE e grava `relatorios/geocodificacao.md` |
| `territorio` | `python -m etl.territorio` | Atribui setor, bairro, regional, zona e H3; grava `relatorios/territorio.md` |

Rodar só parte:

```bash
python -m etl.m0 --so cnpj --so geocodificar --so territorio
python -m etl.m0 --pular setores
```

Cada etapa substitui o conteúdo da sua tabela: rodar de novo não duplica nada. Arquivo já baixado não é baixado de novo; para forçar, apague-o de `dados/bruto/<fonte>/`.

Os scripts do IBGE aceitam arquivo baixado à mão, se o FTP mudar de lugar:

```bash
python -m etl.fontes.ibge_setores --arquivo C:/downloads/PR_setores_CD2022.zip
python -m etl.fontes.ibge_cnefe --arquivo C:/downloads/4106902_CURITIBA.zip
```

Também basta colocar o arquivo em `dados/bruto/ibge_setores/` ou `dados/bruto/ibge_cnefe/`.

### 4. Conferir o resultado

```sql
-- acerto da geocodificação
SELECT geo_precisao, count(*) FROM cwb.empresa_geo GROUP BY 1 ORDER BY 2 DESC;

-- empresas ativas por bairro
SELECT g.bairro, count(*) AS ativas
FROM cwb.empresa e JOIN cwb.empresa_geo g USING (cnpj)
WHERE e.situacao_cadastral = '02'
GROUP BY 1 ORDER BY 2 DESC;

-- histórico de cargas
SELECT fonte, arquivo, linhas, executado_em FROM cwb.execucao ORDER BY id DESC;
```

---

## O que sai no banco

Schema `cwb`:

| Tabela | Conteúdo | Chave |
|---|---|---|
| `setor` | Setores censitários 2022 de Curitiba, atributos originais em `atributos` (jsonb) | `cd_setor` |
| `bairro`, `regional`, `zoneamento` | Camadas do IPPUC: `codigo`, `nome`, `atributos`, `geom` | |
| `cnefe` | Endereços do CNEFE com coordenada, logradouro original e chave normalizada, número, espécie | `cod_unico` |
| `empresa` | Recorte de `dados_rfb.cnpj_consolidado` | `cnpj` |
| `empresa_geo` | Localização e chave territorial de cada CNPJ: `geom`, `geo_precisao`, `cd_setor`, `bairro`, `regional`, `zona`, `h3_8`, `h3_9` | `cnpj` |
| `execucao` | Registro de cada carga: fonte, origem, arquivo, sha256, linhas, detalhes | `id` |

Funções de normalização, usadas nos dois lados do cruzamento:

| Função | Exemplo |
|---|---|
| `cwb.norm_logradouro(text)` | `'R. MAL. FLORIANO PEIXOTO'` e `'Rua Marechal Floriano Peixoto'` viram `'FLORIANO PEIXOTO'` |
| `cwb.norm_numero(text)` | `'1234-A'` vira `1234`; `'S/N'` e `'0'` viram `NULL` |
| `cwb.norm_cep(text)` | `'80.010-000'` vira `'80010000'`; `'00000000'` vira `NULL` |

A chave do logradouro tira o tipo no começo do nome (rua, avenida, alameda, travessa...), os títulos (doutor, marechal, padre, presidente...) e as palavras de ligação (de, da, do...). Como as duas bases passam pela mesma função, abreviação e grafia diferentes caem na mesma chave.

---

## Geocodificação: como ler os níveis

Cada CNPJ fica com o primeiro nível que casar, do mais preciso ao menos preciso. `geo_precisao` diz qual foi.

| Nível | Regra | Serve para |
|---|---|---|
| `endereco` | CEP, logradouro e número iguais aos do CNEFE | Quadra, raio de 250 m |
| `endereco_sem_cep` | Logradouro e número iguais, CEP diferente, e todos os pontos com esse endereço a menos de 300 m entre si | Quadra |
| `numero_proximo` | Mesmo CEP e logradouro, número mais próximo do mesmo lado da rua (mesma paridade) a até 30 de diferença | Quadra |
| `logradouro` | Mesmo CEP e logradouro, sem número que case; usa o endereço do CNEFE mais perto do centro da rua | Setor e bairro |
| `logradouro_aproximado` | Mesmo CEP, nome parecido (similaridade de trigramas de 0,6 ou mais) | Setor e bairro |
| `logradouro_sem_cep` | Logradouro único na cidade (pontos a menos de 1,5 km entre si) | Bairro |
| `cep` | Ponto central do CEP, só quando o CEP cobre menos de 1,5 km | Bairro e regional |
| `nao_localizado` | Nenhum dos anteriores | Fora das análises por área |

O relatório `relatorios/geocodificacao.md` mostra quantos caíram em cada nível, para todas as empresas e só para as ativas, com o acumulado. As tolerâncias estão no topo de `sql/10_geocodificar.sql`.

---

## Catálogo de fontes

`catalogo.yaml` é o inventário único: as 57 fontes mapeadas, com dono, fase, status, chaves de cruzamento e, quando há script, onde baixar. `docs/fontes.md` explica o porquê de cada uma. `docs/pedidos-lai.md` tem os rascunhos dos pedidos via Lei de Acesso à Informação.

| Status | Significado |
|---|---|
| `ativo` | Script pronto e conferido |
| `a_conferir` | Script ou link pronto; formato e colunas se confirmam na primeira rodada |
| `planejado` | Mapeada, sem script |
| `lai` | Só sai por pedido de acesso à informação |
| `convenio` | Depende de parceria (ex.: Waze for Cities) |

Para adicionar uma fonte:
1. Inclua a entrada no `catalogo.yaml` (`id`, `nome`, `dono`, `fase`, `status`, `chaves` e onde baixar: `url`, `url_diretorio` + `padrao_arquivo` ou `portal_chave`).
2. Crie `etl/fontes/<id>.py` seguindo os existentes: baixa com `baixar.baixar`, grava no schema `cwb` substituindo o conteúdo da tabela, registra com `db.registrar`.
3. Se a fonte tiver endereço, normalize com as funções `cwb.norm_*` para cruzar com o CNEFE e com os CNPJs.

---

## Testes

Os testes de banco precisam de um PostgreSQL com PostGIS descartável: **o schema `cwb` é apagado e recriado.**

```bash
createdb -U postgres pineal_teste
# no .env, ou no terminal:
#   PINEAL_TEST_DSN="host=localhost port=5432 dbname=pineal_teste user=postgres password=..."
python -m pytest -q
```

Sem `PINEAL_TEST_DSN`, só os testes sem banco rodam e os demais são pulados.

| Arquivo | Cobre |
|---|---|
| `tests/test_normalizacao.py` | Logradouro, número e CEP |
| `tests/test_geocodificar.py` | Cada nível da geocodificação, relatório e chave territorial com H3 |
| `tests/test_leitura.py` | Leitura do CNEFE (zip, Latin-1, vírgula decimal, filtro de município), links do portal, descrição de CSV sem vazar valores |
| `tests/test_m0.py` | M0 de ponta a ponta com shapefile zipado, camada sem `.prj`, GeoJSON, GPKG, CNEFE e um `cnpj_consolidado` falso; e a segunda rodada sem duplicar |

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
| `cwb.cnefe vazio` ao geocodificar | Etapa `cnefe` não rodou | `python -m etl.m0 --so cnefe` |
| Muitos `nao_localizado` | CEP genérico ou logradouro muito diferente do CNEFE | Veja amostras com `SELECT e.logradouro, e.numero, e.cep FROM cwb.empresa e JOIN cwb.empresa_geo g USING (cnpj) WHERE g.geo_precisao = 'nao_localizado' LIMIT 50` e amplie as listas em `sql/01_normalizacao.sql` |

---

## Estrutura do repositório

```
pineal-curitiba/
├── catalogo.yaml              inventário das fontes (lido pelos scripts)
├── requirements.txt
├── .env.example
├── docker-compose.yml         PostGIS local opcional
├── docs/
│   ├── fontes.md              fontes comentadas, por tema
│   └── pedidos-lai.md         rascunhos dos pedidos de acesso à informação
├── sql/
│   ├── 00_schema.sql          schema cwb e tabelas
│   ├── 01_normalizacao.sql    funções de normalização de endereço
│   ├── 10_geocodificar.sql    geocodificação em níveis
│   └── 20_territorio.sql      chave territorial
├── etl/
│   ├── config.py              .env, caminhos e catálogo
│   ├── db.py                  conexão, execução de SQL, registro de cargas
│   ├── baixar.py              download com cache e busca em listagem de diretório
│   ├── geo.py                 leitura de camadas vetoriais e gravação de polígonos
│   ├── fontes/
│   │   ├── ibge_setores.py
│   │   ├── ibge_cnefe.py
│   │   ├── ippuc.py
│   │   ├── cnpj_recorte.py
│   │   └── portal_inventario.py
│   ├── geocodificar.py
│   ├── territorio.py
│   └── m0.py                  orquestrador
├── tests/
├── dados/                     arquivos baixados (fora do git)
└── relatorios/                relatórios gerados (fora do git)
```

---

## Dados pessoais e licenças

- **Nada sobre pessoa física sai deste repositório.** Saúde, segurança e benefícios entram só agregados por território. O recorte de CNPJs não traz sócios nem CPF.
- `dados/` e `relatorios/` estão no `.gitignore`: dados baixados e resultados não vão para o git.
- Mapa Cadastral e Guia Amarela do IPPUC são consultas por lote: usar sob demanda, sem raspagem em massa.
- O Portal de Dados Abertos de Curitiba publica sob **CC BY 4.0**: qualquer uso público precisa citar a fonte. IBGE, Receita e demais fontes federais são dados abertos com atribuição.
