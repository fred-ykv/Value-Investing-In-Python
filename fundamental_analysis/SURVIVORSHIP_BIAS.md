# Universo historico e vies de sobrevivencia

## Por que esta camada existe

Um benchmark formado apenas por empresas listadas hoje elimina silenciosamente
companhias adquiridas, falidas ou retiradas da bolsa. Isso pode fazer um score
parecer mais seguro do que teria sido em tempo real.

A SEC informa que o CIK e uma identidade unica e nao reciclada. Por isso, o
coletor usa o CIK para encontrar fundamentos de empresas que ja nao aparecem no
mapa atual de tickers:

- https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces

## Universo adicionado

O benchmark historico adiciona dez empresas ao universo ativo de quarenta.
Todos os eventos e valores terminais foram conferidos em documentos da SEC e
permanecem versionados em `benchmark_universe.py`.

| Ticker | CIK | Grupo | Evento | Data | Valor terminal |
|---|---|---|---|---|---:|
| MDLA | 0001540184 | FCF negativo/early growth | Aquisicao em dinheiro | 2021-10-29 | USD 34.00 |
| CLDR | 0001535379 | FCF negativo/early growth | Aquisicao em dinheiro | 2021-10-08 | USD 16.00 |
| CSPR | 0001598674 | FCF negativo/early growth | Aquisicao em dinheiro | 2022-01-25 | USD 6.90 |
| PLAN | 0001540755 | FCF negativo/early growth | Aquisicao em dinheiro | 2022-06-22 | USD 63.75 |
| ZEN | 0001463172 | Growth/tech | Aquisicao em dinheiro | 2022-11-22 | USD 77.50 |
| COUP | 0001385867 | FCF negativo/early growth | Aquisicao em dinheiro | 2023-02-28 | USD 81.00 |
| MNTV | 0001739936 | FCF negativo/early growth | Aquisicao em dinheiro | 2023-05-31 | USD 9.46 |
| XM | 0001747748 | FCF negativo/early growth | Aquisicao em dinheiro | 2023-06-28 | USD 18.15 |
| BBBY | 0000886158 | Tradicional/ciclica | Acoes canceladas sem recuperacao | 2023-09-29 | USD 0.00 |
| NEWR | 0001448056 | FCF negativo/early growth | Aquisicao em dinheiro | 2023-11-08 | USD 87.00 |

O caso BBBY usa o plano confirmado, que cancela as participacoes sem
distribuicao, e o aviso da data efetiva. Os demais casos usam o 8-K de
fechamento da aquisicao.

## Precos historicos

Yahoo Finance e APIs que validam somente o mapa atual de tickers nao preservam
necessariamente series de empresas extintas. O sistema nao preenche essa lacuna
com zero, ultimo preco ou ticker reutilizado.

Para o universo `expanded` ou `lifecycle`, use Tiingo EOD ou forneca um CSV
obtido de uma base com cobertura de delistings. CRSP usa o identificador
permanente PERMNO para seguir uma acao por mudancas de nome, fusoes e
reorganizacoes. Nasdaq Data Link oferece bases premium de precos e fundamentos;
Alpha Vantage oferece uma lista historica de ativos ativos e delistados, util
para descoberta e controle de universo.

- CRSP e PERMNO: https://www.crsp.org/research/
- Nasdaq Data Link: https://docs.data.nasdaq.com/docs/data-organization
- Alpha Vantage Listing Status: https://www.alphavantage.co/documentation/#listing-status

O runner tambem possui um adaptador Tiingo EOD. A fonte publica precos brutos e
ajustados por splits e dividendos, e a cobertura oficial inclui os dez casos do
registro historico. O uso exige token e preflight; veja
`fundamental_analysis/TIINGO_HISTORICAL_PRICES.md`.

O CSV normalizado exige:

```text
security_id,issuer_cik,ticker,date,adjusted_close,raw_close,source
PERMNO_12345,0001463172,ZEN,2021-01-04,142.83,143.20,crsp_export
PERMNO_12345,0001463172,ZEN,2021-01-05,145.17,145.55,crsp_export
```

- `security_id`: identidade permanente da seguranca, como PERMNO;
- `issuer_cik`: CIK da empresa emissora, usado para reconciliar precos e SEC;
- `ticker`: ticker historico canonico usado no benchmark;
- `date`: data em `YYYY-MM-DD`;
- `adjusted_close`: fechamento ajustado para retorno total;
- `raw_close`: fechamento negociado, usado no valuation da data-base;
- `source`: provedor ou exportacao que permite auditar a origem.

Identidades ou CIKs inconsistentes, datas duplicadas, valores nao positivos e
colunas ausentes geram erro explicito. Quando o universo informa um CIK, a
coleta tambem rejeita uma serie sem CIK ou pertencente a outro emissor. Isso
protege contra reutilizacao de ticker.

## Retorno de saida

Se a empresa continua listada durante os doze meses, o calculo permanece igual.
Se ocorre uma aquisicao em dinheiro antes do fim da janela:

1. o valor por acao do 8-K substitui a cotacao terminal;
2. o ajuste acumulado da serie preserva splits e distribuicoes anteriores;
3. o caixa e reinvestido no benchmark do grupo ate completar doze meses;
4. o drawdown acompanha a acao ate a saida e o benchmark depois dela.

Quando a acao e cancelada sem recuperacao, o retorno e `-100%` e o drawdown
terminal tambem e `-100%`.

## Como executar

Benchmark ativo, ainda sujeito a vies de sobrevivencia:

```text
python build_historical_dataset.py --universe active
```

Benchmark ampliado com uma exportacao licenciada ou institucional:

```text
python build_historical_dataset.py --universe expanded --historical-prices-csv C:\dados\historical_prices.csv
```

Piloto apenas com empresas retiradas da bolsa:

```text
python build_historical_dataset.py --universe lifecycle --historical-prices-csv C:\dados\historical_prices.csv
```

Benchmark historico via Tiingo:

```text
python check_historical_price_source.py --provider tiingo
python build_historical_dataset.py --universe lifecycle --price-source tiingo
```

## Controles de governanca

A validacao fora da amostra agora exige, na calibracao:

- pelo menos cinco tickers que posteriormente sairam da bolsa;
- pelo menos um caso de cancelamento ou perda total;
- os controles anteriores de cobertura, diversidade, Spearman e monotonicidade.

Um benchmark apenas com empresas ativas pode continuar sendo usado para
diagnostico, mas nao pode autorizar recalibracao final.

## Piloto de cobertura SEC

O piloto de CIK e fundamentos, de 2015 a 2025, encontrou:

- 50 filings anuais nas dez empresas historicas;
- 46 filings com todas as entradas criticas do perfil;
- 30 candidatos de calibracao, dos quais 26 passaram a auditoria critica;
- 11 candidatos de validacao, todos com entradas criticas completas;
- nove observacoes no embargo temporal.

Esse resultado valida a aplicabilidade da camada SEC. O benchmark economico
ampliado permanece bloqueado ate a importacao de precos que inclua delistings.
