# Manifesto experimental do backtest historico

Este documento congela as regras antes da proxima rodada. O contrato executavel
esta em `EXPERIMENT_MANIFEST.json`; `experiment_manifest.py` o valida.

## Escopo

- Universo fixado em 40 empresas padrao e 10 casos lifecycle, distribuido nos
  grupos tradicionais/ciclicas, growth/tech, bancos/financeiras e FCF negativo.
- Demonstrativos point-in-time da SEC EDGAR e precos historicos arquivados,
  com identidade, volume, ajustes e hashes. Yahoo Finance nao substitui a
  evidencia historica do benchmark.
- Periodo fundamental de 2015 a 2025, com sinal na ultima informacao elegivel
  publicada ate a data-base.

## Datas e comparacao

O horizonte principal e de 12 meses; tambem serao medidos 1, 3, 6, 24 e 36
meses. A particao operacional termina antes de 2022-01-01 para calibracao e
comeca em 2022-01-01 para validacao. Como essa divisao ja foi observada em
rodadas anteriores, ela nao pode ser chamada de holdout intocado.

O retorno sera comparado com SPY para tradicionais, QQQ para growth/tech, KBE
para bancos e IWM para FCF negativo/early growth, alem de uma carteira
equal-weight do proprio universo.

## Carteira e custos

Carteira long-only em USD, sem alavancagem, short ou derivativos, com capital
inicial de US$ 100.000, ate 20 posicoes, alvo de 5% por posicao e teto de 25%
por setor. Sinais mensais entram no proximo pregao elegivel; apenas acoes
inteiras sao compradas e o caixa residual rende zero.

O caso-base usa 10 bps por lado. Sensibilidades usam 5 e 25 bps por lado,
incluindo spread e slippage sem dupla cobranca. Impostos, retencao e cambio
BRL/USD ficam fora do caso-base e serao tratados como limitacoes.

## Regras de qualidade

Dados criticos ausentes excluem a observacao e geram motivo auditavel. Coleta
parcial bloqueia o benchmark. Eventos terminais exigem evidencia documental.
Nenhum resultado permite alterar pesos, formulas, travas ou limiares durante a
mesma rodada.

O benchmark so pode sustentar estudo de recalibracao se cumprir os gates de
point-in-time, cobertura de retornos, correlacao de Spearman, monotonicidade e
amostra minima definidos em `config.py`. Todo replay deve funcionar offline,
com hashes SHA-256 e resultados preservados.

**Estado inicial:** manifesto congelado; benchmark ainda nao executado.

