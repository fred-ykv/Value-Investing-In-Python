# Protocolo de calibracao e validacao temporal

## Objetivo

O benchmark mede se scores maiores antecedem retorno excedente melhor e risco
de queda mais controlado. Ele nao demonstra causalidade e nao transforma
resultado hipotetico em retorno realizavel.

Referencias metodologicas:

- CFA Institute, backtesting, rolling windows, vieses de sobrevivencia e
  look-ahead: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation
- Damodaran, necessidade de testar uma estrategia em periodo ou universo
  diferente daquele usado para deriva-la: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/invphillectures/testmkt.html
- SEC, riscos de otimizacao retrospectiva e necessidade de explicar premissas,
  criterios e limitacoes: https://www.sec.gov/newsroom/speeches-statements/lee-crenshaw-marketing-2020-12-22

## Divisao temporal

Por padrao, o holdout comeca em `01/01/2022`.

1. **Calibracao:** a observacao so entra quando a janela de retorno futuro
   termina antes do inicio do holdout.
2. **Validacao:** a data-base da analise deve ser igual ou posterior ao inicio
   do holdout.
3. **Embargo:** observacoes anteriores ao holdout cujo retorno termina dentro
   dele ficam fora das duas amostras.

O embargo impede que o resultado futuro usado para avaliar uma observacao de
calibracao atravesse o periodo reservado para validacao.

## Controles minimos

- 100 observacoes totais;
- 60 observacoes de calibracao;
- 40 observacoes de validacao;
- 90% de cobertura dos resultados futuros;
- 95% de observacoes point-in-time validas;
- pelo menos 8 observacoes e 3 tickers distintos por grupo em cada amostra;
- Spearman score x retorno excedente de pelo menos 0.10;
- monotonicidade minima de 60% entre faixas de score.

Esses limites sao premissas de governanca em `config.py`, nao verdades
estatisticas. A aprovacao dos controles permite iniciar um estudo de pesos; nao
autoriza automaticamente alterar o modelo.

## Uso correto do holdout

Pesos, travas e limites devem ser escolhidos usando somente a calibracao. O
holdout pode ser consultado uma vez para testar a configuracao congelada. Se o
holdout for usado para escolher uma nova configuracao, ele deixa de ser fora da
amostra e um novo periodo ou universo deve ser reservado.

O relatorio apresenta resultados gerais, por grupo de benchmark e por
recomendacao. Uma media agregada positiva nao compensa ausencia de cobertura em
bancos, empresas ciclicas, growth/tech ou casos de FCF negativo.

## Limitacoes remanescentes

- O universo atual foi curado a partir de empresas hoje conhecidas e ainda tem
  vies de sobrevivencia. Empresas extintas, falidas ou adquiridas devem entrar
  em uma etapa posterior com identificadores e precos historicos adequados.
- Yahoo Finance nao e uma fonte institucional de precos point-in-time.
- O benchmark nao inclui custos de transacao, impostos, liquidez ou impacto de
  mercado.
- Retornos de empresas diferentes podem compartilhar o mesmo regime macro e
  nao sao observacoes totalmente independentes.
- Testar repetidamente muitas configuracoes aumenta o risco de overfitting,
  mesmo com uma divisao temporal.

## Arquivos produzidos

- `historical_observations.csv`: observacoes e linhagem completa;
- `historical_calibration.md`: leitura agregada de toda a amostra;
- `out_of_sample_validation.md`: divisao temporal e diagnosticos segmentados;
- `out_of_sample_validation.json`: dados estruturados da validacao;
- `collection_manifest.json`: erros, avisos e cobertura da coleta.

O primeiro benchmark temporal completo esta documentado em
`fundamental_analysis/BENCHMARK_TEMPORAL_40.md`. O resultado nao autorizou
recalibracao de pesos ou limiares.
