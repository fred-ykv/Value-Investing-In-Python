# Piloto point-in-time: MLI e NUE

## Escopo

O piloto executado em 21 de agosto de 2026 avaliou tres filings anuais de MLI e
NUE publicados entre 2023 e 2025. Cada observacao usa demonstracoes do mesmo
accession number da SEC e mede o retorno total nos 12 meses seguintes contra o
SPY.

## Resultado da coleta com premissas macro historicas

- 6 tentativas e 6 observacoes validas;
- 100% de cobertura dos resultados futuros;
- 100% de validacao point-in-time;
- 100% das metricas fundamentais esperadas disponiveis;
- nenhum erro de coleta.

| Ticker | Data-base | Rf | ERP | WACC aplicado | Score | Recomendacao | Excesso vs. SPY |
|---|---|---:|---:|---:|---:|---|---:|
| MLI | 2023-03-01 | 4.01% | 5.94% | 10.34% | 0.829 | Comprar | 9.3% |
| MLI | 2024-02-29 | 4.25% | 4.60% | 9.03% | 0.749 | Comprar | 39.6% |
| MLI | 2025-02-27 | 4.29% | 4.33% | 9.36% | 0.748 | Comprar | 32.8% |
| NUE | 2023-03-02 | 4.08% | 5.94% | 11.12% | 0.873 | Comprar | -22.9% |
| NUE | 2024-02-28 | 4.27% | 4.60% | 9.77% | 0.741 | Comprar | -46.3% |
| NUE | 2025-02-28 | 4.24% | 4.33% | 9.25% | 0.618 | Observar | 16.6% |

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
6. O coletor macro passou a usar o Treasury de 10 anos observado ate a data-base
   e o ERP anual mais recente ja disponivel, registrando tambem o WACC aplicado.

## Leitura financeira

O caso NUE/2024 e um falso positivo relevante: a recomendacao foi Comprar pouco
antes de retorno absoluto e relativo negativos. Isso e compativel com o risco de
extrapolar lucro e FCFF de pico em uma empresa ciclica. A evidencia justifica
testar normalizacao de margens, lucros e reinvestimento ao longo do ciclo, mas
nao autoriza alterar pesos ou travas com apenas seis observacoes.

A substituicao das premissas macro constantes pelas historicas elevou os scores
mais recentes entre 0.014 e 0.025 ponto. MLI/2025 mudou de Observar para Comprar.
Essa mudanca mostra sensibilidade material da recomendacao ao custo de capital;
nao prova melhora preditiva. NUE/2024 permaneceu Comprar e continuou como falso
positivo, portanto a principal lacuna do piloto segue sendo a normalizacao do
ciclo, nao um simples ajuste de WACC.

O piloto obteve Spearman de -0.086 e monotonicidade de 50%. A regra configurada
exige pelo menos 100 observacoes, cobertura futura de 90%, validacao
point-in-time de 95% e monotonicidade de 60% antes de recalibrar.

## Proxima etapa

Adicionar uma regra auditavel de normalizacao de margens, lucro e reinvestimento
para empresas ciclicas. Depois, ampliar o universo por tipo de empresa e
executar o benchmark completo fora da amostra antes de mudar pesos ou
recomendacoes.
