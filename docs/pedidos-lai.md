# Pedidos via Lei de Acesso à Informação

Rascunhos para os dados que não estão abertos. Cada pedido vai pelo canal de acesso à informação do órgão:
- **Prefeitura de Curitiba** (SMF, SMU, Setran, SMDST, Defesa Civil, IPPUC, URBS): e-SIC municipal, pelo Portal da Transparência ou pela Central 156.
- **Governo do Paraná** (SESP-PR, CBMPR): SIC do Portal da Transparência do Paraná.

Regras que valem para todos:
- A LAI não exige justificativa (art. 10, § 3º). Os textos não trazem motivo.
- Todos pedem formato aberto e legível por máquina (art. 8º, § 3º, II), como CSV ou shapefile. PDF não serve.
- Prazo de 20 dias, prorrogável por mais 10 (art. 11). Registre protocolo e data em `catalogo.yaml` (campo `obs`).
- Nenhum pedido inclui dado pessoal. Onde a base tem pessoa, o pedido já vem agregado ou sem identificação.

Ordem sugerida, pelo valor para o produto: 1, 2, 7, 8, 4, 13, 3, 6, 5, 14, 12, 9, 11 (o 10 não precisa mais).

---

## 1. Cadastro imobiliário por lote (SMF / IPPUC)

> Solicito, em formato aberto (CSV ou shapefile), a base do cadastro imobiliário de Curitiba com os seguintes campos por lote ou unidade: indicação fiscal, bairro, uso do imóvel (residencial, comercial, industrial, misto ou outro), área do terreno, área construída, tipologia ou padrão construtivo e ano da construção. Não solicito nome, CPF/CNPJ ou qualquer dado do proprietário ou contribuinte. Caso a base por unidade não possa ser fornecida, solicito os mesmos campos agregados por quadra fiscal.

## 2. Transações de ITBI (SMF)

> Solicito, em formato aberto (CSV), as transações imobiliárias que geraram ITBI em Curitiba de 2015 até a data mais recente disponível, agregadas por quadra fiscal (ou, se não for possível, por bairro) e por mês, com: quantidade de transações, soma, média e mediana do valor da base de cálculo, área do terreno e área construída médias, e tipo de imóvel. Não solicito identificação de compradores, vendedores ou imóveis individuais.

## 3. Planta Genérica de Valores (SMF / IPPUC)

> Solicito a Planta Genérica de Valores vigente de Curitiba em formato vetorial (shapefile ou GeoPackage), com o valor do metro quadrado do terreno por face de quadra ou zona de valor, e a norma que a instituiu. Se houver versões anteriores em formato vetorial, solicito também.

## 4. Alvarás de construção (SMU)

> Solicito, em formato aberto (CSV), a relação de alvarás de construção emitidos em Curitiba de 2015 até a data mais recente disponível, com: número do alvará, tipo (construção, reforma, ampliação, regularização, restauro), indicação fiscal, endereço da obra, uso previsto, área licenciada, número de unidades, data de emissão e, quando houver, data do certificado de conclusão da obra. Não solicito dados pessoais de requerentes ou responsáveis técnicos.

## 5. EstaR e contagens de tráfego (Setran)

> Solicito, em formato aberto (shapefile ou CSV com coordenadas), os trechos de via com Estacionamento Regulamentado (EstaR) em Curitiba, com número de vagas e horário de funcionamento. Solicito também, em CSV, as contagens volumétricas de veículos realizadas pela Setran de 2019 em diante, com local, data, faixa horária e volume.

## 6. Passageiros do transporte coletivo (URBS)

> Solicito, em formato aberto (CSV), a quantidade de passageiros do transporte coletivo de Curitiba por linha, terminal e estação-tubo, por dia e faixa horária, de 2023 até a data mais recente disponível.

## 7. Estatísticas criminais de Curitiba por bairro (SESP-PR / CAPE)

> Solicito, em formato aberto (CSV), o número de ocorrências registradas no município de Curitiba de 2018 até a data mais recente disponível, por bairro, por natureza da ocorrência e por mês, conforme a base do Boletim de Ocorrência Unificado e do SCOL usada pelo CAPE. Solicito que furtos e roubos a estabelecimentos comerciais apareçam separados dos demais. Não solicito dados de vítimas ou autores.

## 8. Corpo de Bombeiros: ocorrências e Certificados de Vistoria (CBMPR)

> Solicito, em formato aberto (CSV):
> a) as ocorrências atendidas pelo Corpo de Bombeiros no município de Curitiba de 2018 até a data mais recente disponível, por bairro, tipo de ocorrência e mês, sem dados de vítimas;
> b) a relação de Certificados de Vistoria do Corpo de Bombeiros (CVCB) emitidos para estabelecimentos em Curitiba, com CNPJ do estabelecimento, endereço, tipo de ocupação, data de emissão, data de validade e resultado da vistoria (aprovado ou reprovado).

## 9. Defesa Civil: pontos de ocorrência (Defesa Civil de Curitiba / IPPUC)

> Solicito, em formato aberto (CSV com latitude e longitude ou shapefile), as ocorrências registradas pela Defesa Civil de Curitiba de 2015 até a data mais recente disponível, com tipo (alagamento, destelhamento, queda de árvore, deslizamento e outros), data e localização.

## 10. Série atualizada do SiGesGuarda (SMDST)

> O conjunto "SiGesGuarda" do Portal de Dados Abertos de Curitiba traz as ocorrências atendidas pela Guarda Municipal. Solicito a série completa e atualizada até a data mais recente disponível, no mesmo formato publicado, e a informação sobre a periodicidade de atualização do conjunto.

**Não enviar.** O inventário de 07/10/2026 mostra a série atualizada (arquivo mensal de 01/10/2026, de 2023 até a extração), já carregada por `etl/fontes/pmc_sigesguarda.py`. Antes de 2023, o histórico está em dadosabertos.c3sl.ufpr.br/curitiba/Sigesguarda/.

## 11. Base vetorial do IPPUC

> Solicito, em formato vetorial (shapefile ou GeoPackage), as seguintes camadas da base cartográfica de Curitiba: divisão de bairros, administrações regionais, zoneamento de uso e ocupação do solo vigente (Lei 15.511/2019 e alterações), eixos de logradouro com numeração predial, quadras e lotes com indicação fiscal.

Enviar só se o download direto no site do IPPUC não estiver disponível.

## 12. Licenças ambientais emitidas em Curitiba (IAT-PR)

> Solicito, em formato aberto (CSV ou planilha), a relação das licenças ambientais e autorizações emitidas pelo Instituto Água e Terra para empreendimentos localizados no município de Curitiba nos últimos cinco anos e vigentes, com: CNPJ do empreendedor (pessoa jurídica), tipo de licença, atividade licenciada, endereço do empreendimento, data de emissão e data de validade. Não solicito dados de pessoas físicas.

Enviar se não houver arquivo aberto no site do IAT. A resposta vai para `dados/bruto/iat_licencas/` e é lida por `etl/fontes/listas_cnpj.py` (licença perto do vencimento é lead para consultoria ambiental).

## 13. Obras públicas do Município em formato aberto (SMOP / SMF)

> Solicito, em formato aberto (CSV), a base que alimenta o Painel de Obras do Município de Curitiba, com: identificador da obra, descrição, secretaria responsável, endereço ou coordenada, bairro, CNPJ e razão social da empresa contratada, número do contrato, valor contratado, valores medidos e pagos por medição, datas de início, previsão de término e conclusão, e situação. Solicito também a informação sobre a periodicidade de atualização do painel.

Enviar se o painel não tiver exportação nem endpoint aberto (conferir no navegador: aba de rede do painel). Entra somado a `empresa_contratos_pmc` (fornecedor público) e como camada de obras por bairro (#22).

## 14. Autuações de trânsito por local (Setran)

> Solicito, em formato aberto (CSV), as autuações de trânsito lavradas em Curitiba de 2019 em diante, agregadas por logradouro (ou trecho) e mês, com o tipo de infração (código e descrição do CTB) e a quantidade. Não solicito dados de veículos, condutores ou agentes.

Enviar se a Setran só publicar painel ou PDF. Serve para fluxo e fiscalização por via (#22).
