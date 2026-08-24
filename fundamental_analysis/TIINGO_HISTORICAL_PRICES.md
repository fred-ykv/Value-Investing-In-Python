# Precos historicos de empresas retiradas da bolsa com Tiingo

## Decisao de fonte

CRSP continua sendo a referencia institucional preferida para uma verificacao
independente, pois combina PERMNO, precos, retornos totais e retornos de
deslistagem. Para viabilizar o proximo benchmark sem depender de uma assinatura
academica ou institucional, o projeto tambem aceita Tiingo EOD.

Segundo a documentacao oficial do Tiingo:

- a serie EOD oferece preco bruto e ajustado;
- o ajuste incorpora splits e dividendos e segue a metodologia CRSP;
- o plano inicial oferece mais de 30 anos de historico e acesso por API;
- tickers deslistados ainda nao reciclados podem permanecer disponiveis.

Referencias:

- https://www.tiingo.com/documentation/end-of-day
- https://www.tiingo.com/documentation/appendix/symbology
- https://www.tiingo.com/about/pricing
- https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-guide-flat-file-format-2-0/

## Cobertura verificada

A lista oficial supported_tickers.zip, consultada em 24/08/2026, continha as
dez empresas do universo historico:

| Caso | Simbolo Tiingo | Inicio | Fim |
|---|---|---|---|
| MDLA | MDLA | 2019-07-19 | 2021-10-29 |
| CLDR | CLDR | 2017-04-28 | 2021-10-11 |
| CSPR | CSPR | 2020-02-06 | 2022-01-24 |
| PLAN | PLAN | 2018-10-12 | 2022-06-22 |
| ZEN | ZEN | 2014-05-15 | 2022-11-21 |
| COUP | COUP | 2016-10-06 | 2023-02-28 |
| MNTV | MNTV | 2018-09-26 | 2023-05-31 |
| XM | XM | 2021-01-28 | 2023-06-28 |
| BBBY | BBBYQ | 1992-06-05 | 2023-09-29 |
| NEWR | NEWR | 2014-12-12 | 2023-11-07 |

BBBYQ e o simbolo historico usado pelo provedor para a antiga Bed Bath &
Beyond. O ticker COUP aparece mais de uma vez na lista historica; por isso o
programa valida nome, CIK e datas de cobertura antes de aceitar a serie.

## Criar e proteger a chave

Crie uma conta diretamente no site do Tiingo e obtenha o token da API. Nao
grave a chave no notebook, no codigo, no JSON ou no GitHub.

No PowerShell:

~~~powershell
$env:TIINGO_API_KEY = "seu-token"
~~~

No Google Colab:

~~~python
import getpass
import os

os.environ["TIINGO_API_KEY"] = getpass.getpass("Token Tiingo: ")
~~~

## Preflight obrigatorio

Antes do benchmark, valide todas as series:

~~~text
python check_historical_price_source.py --provider tiingo --output historical_price_preflight.md
~~~

O preflight exige:

- emissor e janela historica iguais ao registro auditado;
- CIK coerente com os fundamentos SEC;
- primeiro e ultimo preco esperados;
- quantidade minima de pregoes;
- nenhuma lacuna superior a dez dias corridos.

Qualquer divergencia bloqueia o benchmark.

## Execucao gradual

Primeiro, rode somente as empresas retiradas da bolsa:

~~~text
python build_historical_dataset.py --universe lifecycle --price-source tiingo --start-year 2015 --end-year 2025 --max-filings-per-company 10 --outdir historical_calibration_outputs/lifecycle_tiingo
~~~

Depois de revisar cobertura, eventos e retornos terminais, rode o universo
ampliado:

~~~text
python build_historical_dataset.py --universe expanded --price-source tiingo --start-year 2015 --end-year 2025 --max-filings-per-company 10 --validation-start-year 2022 --outdir historical_calibration_outputs/expanded_tiingo
~~~

Yahoo continua sendo usado somente para os benchmarks ativos, como SPY, QQQ,
KBE e IWM. A serie da empresa retirada da bolsa deve vir do Tiingo ou de um CSV
auditado e precisa reconciliar com o CIK esperado.

## Licenca e governanca

Os dados do plano individual sao para uso interno. Nao publique os arquivos de
precos nem os CSVs derivados. Relatorios agregados devem respeitar os termos do
provedor.

Tiingo torna o benchmark operacional, mas nao elimina a necessidade de uma
reconciliacao independente por amostragem. Antes de alterar pesos e limiares:

1. confira eventos terminais com documentos SEC;
2. reconcilie uma amostra de precos e retornos com CRSP ou outra base licenciada;
3. confirme os controles de calibracao e holdout;
4. congele a configuracao antes de consultar o holdout.
