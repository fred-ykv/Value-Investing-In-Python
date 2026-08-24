# Benchmark temporal de 40 empresas

## Decisao

**Pesos, travas e limites de recomendacao permanecem congelados.** A coleta
ficou materialmente mais completa, mas o score ainda nao ordena retorno
excedente de forma estavel na calibracao ou no holdout.

## Protocolo executado

- universo: 40 empresas, com 10 casos em cada perfil;
- filings anuais: 2015 a 2025, ate 10 por empresa;
- retorno futuro: 12 meses contra SPY, QQQ, KBE ou IWM conforme o grupo;
- calibracao: retorno futuro encerrado antes de `01/01/2022`;
- embargo: observacoes cujo retorno atravessa o inicio do holdout;
- validacao: data-base a partir de `01/01/2022`;
- pesos e limiares: configuracao existente, sem ajuste durante o teste.

## Resultado geral

| Controle | Resultado | Minimo | Status |
|---|---:|---:|---|
| Observacoes coletadas | 345 | 100 | passou |
| Erros de coleta | 0 | - | passou |
| Observacoes utilizaveis | 321 | - | informativo |
| Integridade point-in-time | 93.0% | 95.0% | falhou |
| Spearman geral | 0.018 | 0.100 | falhou |
| Monotonicidade geral | 50.0% | 60.0% | falhou |

## Separacao temporal

| Amostra | Total | Utilizaveis | Integridade | Spearman | Monotonicidade |
|---|---:|---:|---:|---:|---:|
| Calibracao | 155 | 139 | 89.7% | 0.014 | 50.0% |
| Embargo | 34 | - | - | - | - |
| Validacao | 156 | 149 | 95.5% | -0.057 | 25.0% |

O holdout passou o controle de integridade, mas falhou os dois testes
economicos. Score maior nao antecipou retorno excedente maior de forma
consistente.

## Leitura por recomendacao

| Amostra | Recomendacao | N util | Excesso medio | Acerto relativo |
|---|---|---:|---:|---:|
| Calibracao | Comprar | 28 | 17.0% | 53.6% |
| Calibracao | Observar | 106 | 6.0% | 55.7% |
| Calibracao | Evitar | 5 | 27.2% | 80.0% |
| Validacao | Comprar | 23 | 3.4% | 47.8% |
| Validacao | Observar | 112 | 7.6% | 56.2% |
| Validacao | Evitar | 14 | 22.4% | 42.9% |

A cauda de score baixo contem recuperacoes especulativas muito grandes. Isso
faz `Evitar` apresentar retorno medio alto sem oferecer boa taxa de acerto no
holdout. Ao mesmo tempo, `Comprar` ficou abaixo de `Observar` na validacao. A
media isolada, portanto, nao sustenta os rotulos de decisao atuais.

## Cobertura e lacunas

- bancos: 98 de 100 observacoes validas;
- growth/tech: 94 de 97;
- tradicionais/ciclicas: 88 de 100;
- FCF negativo/early growth: 41 de 48;
- 24 observacoes foram rejeitadas por entradas criticas ausentes;
- as lacunas mais frequentes foram receita (11), divida (5), caixa (4) e acoes
  (3).

O grupo early growth possui apenas quatro observacoes de calibracao, todas de
um unico ticker. Empresas recentes nao existiam no periodo anterior ao
holdout, portanto esse perfil ainda nao tem calibracao temporal diversificada.

## Melhorias de dados aplicadas

- ticker SEC do Bank of New York Mellon atualizado para `BNY`;
- fallback de acoes pela media anual diluida com confianca reduzida;
- conceitos adicionais de divida total, capital lease e notes payable;
- proxy de EBIT por juros liquidos com penalidade adicional de confianca;
- aproximacao de divida financeira zero somente sem evidencia positiva no
  filing, sempre marcada como fallback;
- arrendamentos operacionais permanecem fora da divida ate que EBIT e FCFF
  sejam ajustados de forma simetrica.

## Proximo estudo permitido

1. Corrigir a base de calibracao de early growth com um universo historico que
   inclua empresas adquiridas, falidas e delistadas.
2. Investigar o comportamento em U das faixas de score e separar qualidade da
   empresa de risco de recuperacao especulativa.
3. Definir candidatos de pesos apenas na calibracao e por perfil de empresa.
4. Reservar um novo holdout ou universo intocado antes de aceitar qualquer
   configuracao escolhida com conhecimento destes resultados.

O universo usa empresas conhecidas hoje e ainda possui vies de sobrevivencia.
Este benchmark e evidencia de diagnostico, nao uma simulacao de carteira
investivel nem recomendacao de investimento.
