# Coleta historica point-in-time

## Objetivo

O coletor cria observacoes de score que poderiam ter sido calculadas na data
indicada. Ele combina fatos financeiros da SEC EDGAR, precos historicos e
premissas macro disponiveis na data-base. A trilha de auditoria rejeita dados
futuros em vez de substitui-los silenciosamente por premissas atuais.

Fontes de referencia:

- SEC EDGAR Data APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Regras de acesso automatizado da SEC: https://www.sec.gov/about/webmaster-frequently-asked-questions
- Historico ajustado do yfinance: https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
- U.S. Treasury Daily Treasury Par Yield Curve Rates: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView
- Damodaran Historical Implied Equity Risk Premiums: https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/histimpl.html

## Regras de disponibilidade

Cada snapshot e ligado a um formulario anual original (`10-K`, `20-F` ou
`40-F`) e ao respectivo accession number. Um fato so pode entrar quando:

1. pertence ao mesmo accession number do filing ancora;
2. corresponde ao periodo anual ou data de balanco do filing;
3. foi publicado antes da data-base;
4. respeita o atraso minimo configurado entre filing e analise.

O score e o market cap usam o primeiro fechamento efetivamente negociado em
data igual ou posterior a data-base. Como o Yahoo reajusta `Close`
retrospectivamente por splits posteriores, o coletor reverte esses fatores para
manter consistencia com as acoes historicas informadas no filing. Retorno
futuro, benchmark, drawdown e beta usam fechamentos ajustados; o beta usa apenas
retornos anteriores ao preco inicial.

Para empresas cujo ticker nao existe mais, o universo historico fornece o CIK
da SEC diretamente. Precos devem ser importados com uma identidade permanente,
fonte e serie ajustada auditavel. Em aquisicao em dinheiro, a contraprestacao
terminal e reinvestida no benchmark ate o horizonte original; em cancelamento
sem recuperacao, o retorno terminal e `-100%`. O programa nao inventa precos
para completar uma serie ausente.

## Premissas macro historicas

O custo de capital e reconstruido com duas observacoes datadas:

1. taxa livre de risco: Treasury nominal de 10 anos mais recente em data igual
   ou anterior a data-base, com defasagem maxima configurada de sete dias;
2. premio de risco: ERP implicito anual de Damodaran mais recente que ja estaria
   publicado. Por prudencia, o valor do ano anterior e considerado disponivel
   apenas em 15 de janeiro do ano seguinte.

O CSV registra taxa livre de risco, ERP, datas de referencia, Ke, WACC, taxa de
desconto efetivamente aplicada, metodo, confianca e uso de fallback. A
observacao deixa de ser point-in-time valida se uma das premissas macro ainda
nao estava disponivel na data-base. Nao existe fallback para taxas atuais.

O mesmo CSV preserva, em colunas separadas, score e confianca das seis
dimensoes calculadas na data-base: valuation, crescimento, qualidade, divida,
liquidez e confianca dos dados. Arquivos antigos continuam legiveis; dimensoes
que nao existiam no esquema anterior permanecem ausentes em vez de serem
inferidas.

## Normalizacao point-in-time de empresas ciclicas

Os casos ciclicos definidos no universo de benchmark carregam ate dez filings
anuais que ja estavam disponiveis na data-base. Margens operacionais, lucro,
FCFF e reinvestimento sao normalizados ao longo do ciclo sem consultar
classificacao ou demonstrativos atuais. O CSV registra se o ajuste foi aplicado,
anos usados, confianca, posicao no ciclo, FCFF corrente e normalizado, margem
operacional normalizada e margem de reinvestimento normalizada.

Historico insuficiente ou baixa confianca nao invalida a observacao inteira: os
valores correntes sao preservados e a razao fica registrada nos avisos. A
metodologia completa esta em `fundamental_analysis/CYCLICAL_NORMALIZATION.md`.

## Identificacao obrigatoria na SEC

A SEC exige um `User-Agent` que identifique a aplicacao e um contato. Defina:

```text
SEC_USER_AGENT="Value Investing Research seu-email@exemplo.com"
```

O coletor limita a frequencia abaixo do teto publicado pela SEC e guarda as
respostas em `.cache/sec_edgar/` para nao repetir downloads desnecessarios.
As tabelas macro sao armazenadas por ate 24 horas em
`.cache/historical_macro/`.

## Execucao gradual

Primeiro, valide poucos tickers e poucos anos:

```text
python build_historical_dataset.py MLI NUE --start-year 2020 --max-filings-per-company 3
```

Depois, rode o benchmark completo:

```text
python build_historical_dataset.py --start-year 2015 --end-year 2025 --max-filings-per-company 10 --validation-start-year 2022
```

Para incluir empresas retiradas da bolsa, informe um CSV historico normalizado:

```text
python build_historical_dataset.py --universe expanded --historical-prices-csv historical_prices.csv --start-year 2015 --end-year 2025 --max-filings-per-company 10 --validation-start-year 2022
```

O esquema, as validacoes e o registro inicial de eventos estao em
`fundamental_analysis/SURVIVORSHIP_BIAS.md`. As opcoes `expanded` e
`lifecycle` falham de forma explicita se nenhuma fonte auditada for fornecida.

Como alternativa operacional ao CSV, defina `TIINGO_API_KEY`, execute o
preflight e selecione o provedor:

```text
python check_historical_price_source.py --provider tiingo
python build_historical_dataset.py --universe lifecycle --price-source tiingo
```

O adaptador valida nome, CIK, simbolo historico, datas extremas, quantidade de
pregoes e lacunas. A chave segue no cabecalho HTTPS e nao entra nos artefatos.
Detalhes: `fundamental_analysis/TIINGO_HISTORICAL_PRICES.md`.

Os arquivos sao gravados em `historical_calibration_outputs/`:

- `historical_observations.csv`: observacoes, scores e confiancas dimensionais, premissas macro, custo de capital e auditoria da normalizacao ciclica;
- `collection_manifest.json`: trilha detalhada de sucessos, avisos e erros;
- `collection_report.md`: cobertura por ticker e filing;
- `historical_calibration.md`: Spearman, monotonicidade, retorno e drawdown.
- `out_of_sample_validation.md`: calibracao, embargo, holdout e resultados por grupo;
- `out_of_sample_validation.json`: diagnosticos temporais em formato estruturado.

O protocolo detalhado esta em `fundamental_analysis/BACKTEST_VALIDATION.md`.

## Entradas criticas por perfil

A cobertura geral da SEC nao basta para validar uma observacao. O coletor exige
as entradas que sustentam o modelo daquele perfil e rejeita metricas com
confianca inferior ao piso definido em `config.py`:

- bancos: lucro liquido, patrimonio e acoes;
- growth/tech e early growth: receita, caixa, divida e acoes;
- tradicionais: receita, EBIT, lucro, patrimonio, caixa, divida, depreciacao,
  CAPEX e acoes.

Quando o filing nao publica a quantidade instantanea consolidada de acoes, a
media anual diluida pode ser usada como fallback explicitamente identificado e
com confianca reduzida. Divida zero so e aproximada quando nao ha conceito de
divida nem evidencia financeira positiva no filing ancora. Arrendamentos
operacionais sao informados na nota, mas nao sao somados a divida sem o ajuste
simetrico de EBIT e FCFF.

## Protecoes contra vazamento

Durante o backtest, o programa desativa enriquecimento atual de pares e o
fallback setorial Damodaran atual. Classificacao de modelo vem do universo de
benchmark e e identificada como curada. Nenhum dado atual do Yahoo `info` e
usado para reconstruir demonstracoes passadas.

O coletor de taxa livre de risco nunca escolhe uma observacao posterior a
data-base. O ERP anual tambem passa por uma data conservadora de disponibilidade.

## Limitacoes ainda abertas

- A primeira versao usa demonstracoes anuais; trimestrais e TTM exigem uma
  reconciliacao adicional para evitar misturar acumulados de duracoes distintas.
- Formularios de emenda (`10-K/A`) nao sao usados como ancora nesta fase.
- O Company Facts agrega apenas taxonomias padronizadas; extensoes especificas
  da companhia podem reduzir a cobertura.
- Precos ajustados do Yahoo nao sao uma fonte regulatoria e devem ser
  reconciliados com um provedor institucional antes de uso de producao.
- A pagina historica de Damodaran e uma serie consolidada consultada hoje, nao
  um arquivo de cada versao publicada no passado. Revisoes retroativas da serie
  ainda exigem arquivamento por versao ou provedor institucional point-in-time.
- O WACC pode conter fallback em componentes que a SEC nao fornece diretamente,
  como custo da divida. O CSV identifica essa condicao para permitir filtros.
- Pesos e limiares nao devem ser recalibrados antes de uma amostra ampla,
  segmentada por tipo de empresa e com validacao fora da amostra.
- A cobertura SEC dos casos historicos foi validada, mas o benchmark economico
  ampliado depende da importacao de precos de um provedor com deslistadas.
- O benchmark de 40 empresas e sua decisao de governanca estao resumidos em
  `fundamental_analysis/BENCHMARK_TEMPORAL_40.md`.

