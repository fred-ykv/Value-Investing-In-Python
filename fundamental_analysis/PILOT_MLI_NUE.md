# Piloto point-in-time: MLI e NUE

## Escopo

O piloto executado em 21 de agosto de 2026 avaliou tres filings anuais de MLI e
NUE publicados entre 2023 e 2025. Cada observacao usa demonstracoes do mesmo
accession number da SEC e mede o retorno total nos 12 meses seguintes contra o
SPY.

## Resultado da coleta

- 6 tentativas e 6 observacoes validas;
- 100% de cobertura dos resultados futuros;
- 100% de validacao point-in-time;
- 100% das metricas fundamentais esperadas disponiveis;
- nenhum erro de coleta.

| Ticker | Data-base | Score | Recomendacao | Retorno 12m | Excesso vs. SPY | Drawdown maximo |
|---|---|---:|---|---:|---:|---:|
| MLI | 2023-03-01 | 0.828 | Comprar | 41.2% | 9.3% | -23.3% |
| MLI | 2024-02-29 | 0.734 | Comprar | 58.1% | 39.6% | -19.8% |
| MLI | 2025-02-27 | 0.723 | Observar | 51.4% | 32.8% | -17.6% |
| NUE | 2023-03-02 | 0.871 | Comprar | 7.9% | -22.9% | -25.7% |
| NUE | 2024-02-28 | 0.719 | Comprar | -27.4% | -46.3% | -42.4% |
| NUE | 2025-02-28 | 0.604 | Observar | 33.5% | 16.6% | -24.6% |

## Correcoes encontradas pelo piloto

1. MLI reportou CAPEX como `PaymentsToAcquireProductiveAssets`, conceito que
   ainda nao estava mapeado.
2. MLI e NUE usaram conceitos alternativos de despesa de juros.
3. NUE nao publicou `OperatingIncomeLoss` padronizado. O coletor passou a usar
   um EBIT proxy de menor confianca, calculado por lucro antes dos impostos mais
   despesa de juros e identificado como fallback.
4. O `Close` historico do Yahoo estava reajustado por splits posteriores. O
   coletor agora reverte esses fatores antes de combinar preco e acoes da SEC.
5. A cobertura podia ultrapassar 100% ao contar uma metrica derivada adicional;
   o numerador agora considera somente as metricas esperadas.

## Leitura financeira

O caso NUE/2024 e um falso positivo relevante: a recomendacao foi Comprar pouco
antes de retorno absoluto e relativo negativos. Isso e compativel com o risco de
extrapolar lucro e FCFF de pico em uma empresa ciclica. A evidencia justifica
testar normalizacao de margens, lucros e reinvestimento ao longo do ciclo, mas
nao autoriza alterar pesos ou travas com apenas seis observacoes.

O piloto obteve Spearman de -0.086 e monotonicidade de 50%. A regra configurada
exige pelo menos 100 observacoes, cobertura futura de 90%, validacao
point-in-time de 95% e monotonicidade de 60% antes de recalibrar.

## Proxima etapa

Adicionar premissas macro historicas e uma regra auditavel de normalizacao para
empresas ciclicas. Depois, ampliar o universo por tipo de empresa e executar o
benchmark completo fora da amostra antes de mudar pesos ou recomendacoes.
