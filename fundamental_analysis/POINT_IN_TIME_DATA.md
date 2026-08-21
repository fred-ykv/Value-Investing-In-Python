# Coleta historica point-in-time

## Objetivo

O coletor cria observacoes de score que poderiam ter sido calculadas na data
indicada. Ele combina fatos financeiros da SEC EDGAR com precos historicos
ajustados e mantem a trilha de auditoria necessaria para rejeitar look-ahead.

Fontes de referencia:

- SEC EDGAR Data APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Regras de acesso automatizado da SEC: https://www.sec.gov/about/webmaster-frequently-asked-questions
- Historico ajustado do yfinance: https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html

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

## Identificacao obrigatoria na SEC

A SEC exige um `User-Agent` que identifique a aplicacao e um contato. Defina:

```text
SEC_USER_AGENT="Value Investing Research seu-email@exemplo.com"
```

O coletor limita a frequencia abaixo do teto publicado pela SEC e guarda as
respostas em `.cache/sec_edgar/` para nao repetir downloads desnecessarios.

## Execucao gradual

Primeiro, valide poucos tickers e poucos anos:

```text
python build_historical_dataset.py MLI NUE --start-year 2020 --max-filings-per-company 3
```

Depois, rode o benchmark completo:

```text
python build_historical_dataset.py --start-year 2015 --max-filings-per-company 5
```

Os arquivos sao gravados em `historical_calibration_outputs/`:

- `historical_observations.csv`: observacoes prontas para avaliacao;
- `collection_manifest.json`: trilha detalhada de sucessos, avisos e erros;
- `collection_report.md`: cobertura por ticker e filing;
- `historical_calibration.md`: Spearman, monotonicidade, retorno e drawdown.

## Protecoes contra vazamento

Durante o backtest, o programa desativa enriquecimento atual de pares e o
fallback setorial Damodaran atual. Classificacao de modelo vem do universo de
benchmark e e identificada como curada. Nenhum dado atual do Yahoo `info` e
usado para reconstruir demonstracoes passadas.

## Limitacoes ainda abertas

- A primeira versao usa demonstracoes anuais; trimestrais e TTM exigem uma
  reconciliacao adicional para evitar misturar acumulados de duracoes distintas.
- Formularios de emenda (`10-K/A`) nao sao usados como ancora nesta fase.
- O Company Facts agrega apenas taxonomias padronizadas; extensoes especificas
  da companhia podem reduzir a cobertura.
- Precos ajustados do Yahoo nao sao uma fonte regulatoria e devem ser
  reconciliados com um provedor institucional antes de uso de producao.
- Taxa livre de risco e premio de risco historicos ainda nao sao coletados;
  as premissas configuradas continuam constantes. Pesos e limiares nao devem
  ser recalibrados definitivamente antes dessa camada macro ser adicionada ou
  o impacto da premissa constante ser testado.
