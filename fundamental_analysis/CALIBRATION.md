# Protocolo de calibracao do score

Este protocolo existe para impedir que pesos, travas e recomendacoes sejam
ajustados apenas porque alguns casos conhecidos pareceram duros ou lenientes.
O objetivo e medir primeiro e alterar depois.

## Etapa A - diagnostico transversal

O benchmark corrente usa quatro grupos de calibracao:

1. empresas tradicionais e ciclicas;
2. growth e tecnologia;
3. bancos e financeiras;
4. empresas em fase inicial ou com historico recente de FCF negativo.

Os grupos nao sao classificacoes imutaveis. O quarto grupo, em especial, deve
ser confirmado em cada data-base. A fotografia transversal mede:

- dispersao dos scores;
- concentracao em Comprar, Observar ou Evitar;
- quartis por grupo;
- frequencia da trava de valuation;
- cobertura e confianca dos dados;
- erros de coleta ou calculo.

Essa etapa detecta problemas de escala e cobertura, mas nao demonstra poder
preditivo. Portanto, um diagnostico transversal aprovado nao autoriza sozinho
a mudanca dos pesos.

## Etapa B - validacao historica point-in-time

Cada observacao historica deve guardar o score que seria conhecido na
data-base, usando somente demonstracoes financeiras publicadas ate aquela
data. A regra minima e:

`latest_filing_date <= as_of`

Para cada observacao, o protocolo mede no horizonte configurado:

- retorno futuro da acao;
- retorno do benchmark no mesmo periodo;
- retorno excedente da acao;
- drawdown maximo;
- cobertura point-in-time e cobertura dos resultados.

Os scores sao separados em faixas de tamanho semelhante. Um modelo util deve,
em amostra ampla, apresentar relacao positiva entre score e retorno excedente,
alem de progressao razoavelmente monotona entre as faixas. A correlacao de
Spearman reduz a dependencia de uma relacao linear exata.

## Controles contra vieses

- Nao usar demonstracoes publicadas depois da data-base.
- Nao substituir empresas que deixaram de existir apenas por sobreviventes.
- Nao calibrar contra rotulos subjetivos de Comprar, Observar ou Evitar.
- Nao escolher pesos olhando repetidamente para a mesma amostra de teste.
- Separar periodo de desenvolvimento, validacao e teste final fora da amostra.
- Registrar versao do codigo, fonte, data de coleta e premissas de mercado.
- Comparar retorno excedente com benchmark coerente com o grupo e o periodo.

## Criterio para alterar pesos

Todos os limites arbitrarios ficam em `config.py`, na classe
`CalibrationAssumptions`. A alteracao de pesos so deve comecar quando os
diagnosticos transversais e historicos estiverem sem alertas bloqueadores.
Depois da alteracao, o teste fora da amostra deve ser executado uma unica vez.

## Fonte historica

Esta entrega cria a camada de avaliacao e os formatos CSV, mas nao inventa um
historico fundamentalista. A etapa seguinte deve implementar um adaptador de
dados point-in-time, preferencialmente com fatos e datas de publicacao da SEC
EDGAR, combinado com uma fonte de precos ajustados e benchmarks. Dados atuais
do Yahoo Finance nao devem ser reutilizados como se estivessem disponiveis no
passado.

