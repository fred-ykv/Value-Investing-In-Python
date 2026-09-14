# Protocolo V2 de validacao historica e auditoria de consistencia

Status: especificacao para implementacao gradual; benchmark V2 ainda nao executado.
Data: 2026-09-14.
Baseline imutavel: commit 03c74c8f4603fb7c75f18dd7da9eecec44d242fc (PR60).
Este PR adiciona documentacao; nao muda calculos, pesos ou recomendacoes.

## 1. Pergunta e limites da conclusao

Testar se as recomendacoes historicas do modelo antecipam retorno total
excedente e risco aceitavel em uma carteira realizavel, e se a evidencia
persiste por setor, porte, regime de mercado e horizonte.
Resultado negativo ou inconclusivo tambem e um resultado valido.
Nao escolher datas, empresas, custos ou regras depois de observar o lucro.

O protocolo complementa BACKTEST_VALIDATION.md. Os controles existentes
continuam operacionais; as exigencias V2 abaixo sao especificacao, nao
checagens ja implementadas. Passar limites de cobertura, Spearman ou
monotonicidade nao comprova rentabilidade nem significancia estatistica.

## 2. Auditoria inicial do baseline

Evidencia: execucao Colab de MLI em 2026-09-14, no commit baseline.
Os numeros abaixo foram observados na tela; os arquivos dessa execucao ainda
precisam ser arquivados e identificados por hash para reproduzir o achado.

| ID | Evidencia e causa no codigo | Classificacao | Criterio de fechamento |
| --- | --- | --- | --- |
| A01 | cyclical_normalization.py, build_cyclical_periods, linhas 281-340: dicionario por period_end e limite por numero de registros. O relatorio mostra 10 observacoes de 2019 a 2025, com datas SEC/Yahoo proximas no mesmo exercicio. | Risco de dupla contagem e cobertura superestimada; bloqueia normalizacao auditada. | Resolver identidade do exercicio fiscal, preservar ambas as fontes e selecionar deterministicamente uma observacao anual; mostrar exercicios unicos, intervalo e conflitos. |
| A02 | peer_selection.py:207-213 calcula confianca pela quantidade aprovada. config.py define min_approved_peers=2; dois aprovados atingem 1.00, independentemente de sua confianca individual. | Semantica de confianca inadequada para interpretar a robustez economica. | Separar atendimento do minimo, qualidade da evidencia e tamanho efetivo da amostra; duas empresas nao podem ser apresentadas como certeza estatistica. |
| A03 | scoring.py:996-1069 decide com score e pilares, sem receber cenarios. Limiares: compra 0.70 e valuation minimo 0.45. MLI: total 0.80, valuation 0.58, margem media -40.48%, todos os cenarios abaixo do preco. | Comportamento coerente com a regra atual, mas conflito entre recomendacao e narrativa; nao e prova de erro aritmetico. | Explicar contribuicao intrinseca versus relativa e conflito com cenarios; qualquer nova trava e uma hipotese de politica, versionada e testada separadamente. |
| A04 | Relatorio usa ATI e CRS como pares de MLI e a justificativa inclui sector/industry/business_model iguais. | Equivalencia economica ainda nao comprovada apenas por esses rotulos. | Registrar produtos, clientes finais, exposicao ciclica e origem de cada classificacao; verificar se modelo de negocio foi inferido circularmente a partir do setor. |
| A05 | Relatorio apresenta risco critico de fallback de DCF, mas mantem Comprar. | Severidade do alerta e politica decisoria precisam ser reconciliadas. | Distinguir premissa declarada, dado ausente e inconsistencia material; registrar quais condicoes sao informativas ou bloqueadoras. |

A01 deve tratar exercicios de 52/53 semanas, mudanca de encerramento fiscal,
periodos de transicao e TTM. Agrupar apenas pelo ano civil ou arredondar datas
nao basta. Conflito nao resolvido entra em quarentena com motivo.
A prova de regressao inclui ordem de fontes invertida e datas proximas,
assegurando que cobertura e resultado nao dependem da ordem de entrada.

A02 deve ter teste com dois pares de baixa qualidade, candidatos duplicados,
fontes ausentes e retirada de um par. Qualidade da classificacao e numero de
multiplos da mesma empresa nao sao observacoes independentes.
A03 deve manter teste do comportamento baseline e registrar o caminho da
decisao; alterar a trava durante esta auditoria contaminaria a comparacao.

## 3. Congelamento e rastreabilidade

Antes da primeira coleta V2, gerar manifesto contendo:
- SHA do codigo e hash de config.py, dependencias e protocolo;
- universo com identificador permanente, classe, ticker historico, segmento,
  data de inclusao/exclusao e evidencia disponivel na epoca;
- fontes, licencas, instante de coleta, periodo do dado, filing e horario de
  disponibilidade, revisao e politica de normalizacao;
- arquivos brutos e derivados com SHA-256, parametros, calendario e fuso;
- regras de carteira, custos, benchmarks, particoes temporais e seed;
- registro de cada experimento, inclusive tentativas malsucedidas.

Reconstruir offline scores, decisoes, retornos e carteira a partir do pacote.
Hashes dos arquivos devem ser identicos; tolerancias numericas para resultados
devem ser declaradas antes da execucao. Arquivo faltante impede reproducao,
nao aciona coleta silenciosa nem substituicao por dado atual.

## 4. Universo e disponibilidade historica

A cesta atual de empresas ativas e deslistadas e um piloto de engenharia.
Sua curadoria e os eventos ja conhecidos impedem trata-la como amostra
representativa ou teste final intocado.

Construir universo elegivel em cada data a partir de cadastro historico
licenciado ou fonte verificavel, incluindo entradas, saidas, falencias,
aquisicoes, mudancas de ticker e classes de acoes. Se essa fonte nao estiver
disponivel, rotular o estudo como piloto curado e limitar suas conclusoes.

Estratificar por bancos/financeiras, industriais/ciclicas, tecnologia e demais
setores; porte e FCFF negativo sao eixos adicionais, nao grupos exclusivos.
Porte, setor, elegibilidade e liquidez devem refletir a data da decisao.
Relatar universo elegivel, coletado, rejeitado e motivo por data e segmento.
Nao eliminar falhas de coleta silenciosamente nem preencher ausencia com zero.

Demonstrativos devem usar versoes publicadas ate o corte; dados republicados
posteriormente ficam fora daquela decisao. Sem horario de divulgacao, adotar
disponibilidade conservadora na sessao seguinte. WACC historico precisa de
taxa livre de risco, premio, beta, divida e valor de mercado admissiveis na
epoca; premissas fixas sao explicitadas e analisadas como limitacao.
Pares historicos exigem a mesma disciplina. Par atual nao substitui par antigo.

## 5. Dois experimentos distintos

### A. Poder informativo dos sinais

Gerar sinal mensal apos o fechamento da ultima sessao do mes.
Entrada teorica na abertura da proxima sessao elegivel; ausencia de abertura
nao autoriza usar fechamento anterior. Qualquer alternativa de execucao exige
versao propria do experimento.
Avaliar horizontes de 1, 3, 6, 12, 24 e 36 meses de calendario, mapeados para a
primeira sessao elegivel na data-alvo ou depois dela.
Horizonte primario: 12 meses. Os demais sao secundarios e exploratorios.
Janelas ainda incompletas sao censuradas, nao perdas ou retornos zero.

Calcular retorno total com dividendos e eventos, excesso sobre benchmark e
distribuicao por recomendacao e faixas de score congeladas. Nao anualizar
ganhos de um mes como expectativa de retorno anual.
Posicoes sobrepostas do mesmo papel sao observacoes dependentes.

### B. Carteira implementavel

Configuracao inicial proposta, a registrar no manifesto antes de medir:
carteira long-only em USD, sem alavancagem, sinais mensais, ate 20 posicoes,
alocacao alvo de 5% do patrimonio por posicao e limite setorial de 25%.
Selecionar Comprar por score decrescente; desempate pelo identificador
permanente. Aplicar o limite setorial durante a selecao. Posicoes fora da
selecao saem no rebalanceamento seguinte; uma nova recomendacao nao duplica
uma posicao existente. Caixa residual recebe retorno zero no caso primario.

Simular acoes inteiras, capital inicial de USD 100.000 e registrar limites de
participacao no volume, ordens parciais e ordens nao executadas. A capacidade
precisa ser verificada com liquidez conhecida antes da ordem.
Parametrizar custos por lado em 5, 10 e 25 pontos-base, usando 10 no caso
primario. Sao hipoteses de pesquisa, nao cotacoes de corretora; spreads,
comissoes e impacto devem ser reconciliados para evitar dupla cobranca.
O implementador deve registrar limite de participacao antes da execucao e
bloquear o teste de capacidade se faltar volume historico utilizavel.

Dividendos entram em caixa; splits ajustam quantidade e custo por acao.
Nao somar dividendos novamente a uma serie de retorno total ajustada.
Aquisicao em dinheiro entra em caixa na data de recebimento documentada;
suspensao impede venda ficticia. Recuperacao, cancelamento e troca de acoes
seguem evidencia do evento. A convencao legada de reinvestir pagamento no
benchmark permanece apenas no diagnostico legado, nao nesta carteira.

Apresentar retorno liquido dos custos de negociacao, antes de impostos
pessoais. Retencoes de dividendos e cambio exigem cenarios identificados;
resultado em USD nao e automaticamente retorno liquido de residente brasileiro.
Os parametros acima pertencerao a configuracao experimental versionada;
nao substituir os pesos financeiros em config.py.

## 6. Benchmarks

Escolher e congelar os identificadores e fontes antes de obter resultados:
mercado amplo americano com retorno total, referencia setorial e carteira de
pesos iguais do mesmo universo elegivel. Se um indice historico licenciado
nao estiver disponivel, declarar proxy negociavel e sua data de inicio.
Nao inventar historico anterior ao nascimento de um ETF.

Usar mesmas datas, moeda e tratamento de dividendos. Mostrar benchmark
investido integralmente e controle com exposicao comparavel para distinguir
selecao de acoes de efeito do caixa. Carteira de pesos iguais recebe custos
coerentes com seu giro; indice teorico bruto deve ser identificado como tal.

## 7. Particoes temporais e prevencao de overfitting

A divisao legada em 2022 ja foi exposta ao desenvolvimento. Nao presumir
que ela continua sendo teste final intocado. Inventariar periodos consultados.
Se nao houver historico ainda nao consultado, validar prospectivamente com
simulacao a partir do congelamento e chamar os resultados passados de
retrospectivos.

Fixar datas exatas das particoes no manifesto apos verificar cobertura e
antes de consultar resultados. Usar desenvolvimento, validacao walk-forward
e teste final reservado. Nao executar calibracao com datas ainda indefinidas.
Excluir da calibracao qualquer observacao cujo retorno futuro alcance a
proxima particao; o expurgo deve acompanhar cada horizonte, ate 36 meses.
Mesma regra entre folds; dados financeiros do passado podem servir de
contexto, mas resultados futuros de treino nao podem invadir o teste.

Congelar numero de variantes e criterios de selecao. Registrar todas as
tentativas e corrigir inferencia para multiplas comparacoes.
Consultar teste final uma unica vez; novo ajuste torna o teste desenvolvimento.

## 8. Resultados e criterios de decisao

Publicar CAGR da carteira, retorno acumulado, volatilidade, queda maxima,
tempo de recuperacao (incluindo nao recuperado), giro, exposicao, custos,
concentracao e desempenho relativo. Para sinais, publicar mediana, caudas,
taxa de acerto, Spearman e ordenacao das faixas; score nao e probabilidade.

Estimar incerteza com reamostragem em blocos temporais que preserve relacao
entre acoes e sobreposicao dos horizontes, registrando tamanho do bloco e
sensibilidade. Nao usar teste que suponha cada ticker-mes independente.
Mostrar sensibilidade a custos, retirada dos maiores ganhadores, segmentos
e regimes definidos antecipadamente.

Antes de iniciar busca de pesos:
1. Fechar A01 e reconciliar A02-A05 com evidencias e testes.
2. Passar reproducao offline e controles de temporalidade e eventos.
3. Publicar baseline completo, inclusive resultados ruins e dados ausentes.
4. Confirmar cobertura dos segmentos e particoes, sem tratar numero minimo
   de observacoes como garantia de poder estatistico.

Para afirmar evidencia favoravel no horizonte primario, exigir excesso
liquido positivo fora da amostra frente aos controles definidos, intervalo
de incerteza compativel com a conclusao e robustez aos custos e concentracao.
Fixar previamente tolerancia de queda e orcamento de risco no manifesto;
sem esses limites nao classificar risco como aceitavel.
Se intervalo incluir zero, cobertura for insuficiente ou ganhos dependerem
de poucos casos, classificar como inconclusivo e explicar a limitacao.
Nao procurar novas configuracoes ate obter um resultado positivo.

## 9. Cenarios fundamentais

Comparar previsoes de receita, margem, FCFF e reinvestimento com realizacoes
de mesma definicao e horizonte. Manter o caminho projetado original.
Cenarios conservador/base/otimista nao sao intervalos probabilisticos sem
probabilidades calibradas. Relatar erro, vies e frequencia fora da faixa,
sem interpretar faixa como intervalo de confianca.
Preco de mercado e valor intrinseco sao avaliados separadamente.
Sem trajetorias arquivadas, marcar avaliacao de cenarios indisponivel.

## 10. Entregas e sequencia de implementacao

| Etapa | Entrega | Condicao para avancar |
| --- | --- | --- |
| PR61 | Este protocolo e auditoria inicial rastreavel | Revisao do documento; nenhum benchmark V2 alegado |
| Seguinte | Correcao de identidade fiscal e cobertura A01, com fixtures | Testes de 52/53 semanas, fontes duplicadas, transicoes e ordem de entrada |
| Seguinte | Explicacao e telemetria A02-A05 | Distinguir dado, confianca, politica e conflito; preservar baseline decisorio |
| Seguinte | Manifesto experimental, universo e contratos de dados | Datas, fontes, liquidez, benchmarks e risco definidos; pacote offline |
| Seguinte | Avaliacao multi-horizonte e carteira contabilizada | Testes de dividendos, splits, gaps, ordens parciais, custos e eventos |
| Seguinte | Execucao baseline e relatorio de incerteza | Publicar cobertura, falhas e resultados por segmento |
| Condicional | Experimentos de calibracao | Somente apos os controles e com validacao independente |

Artefatos previstos: experiment_manifest.json, audit_findings.json,
eligibility.csv, observations.csv, orders.csv, fills.csv, cash_ledger.csv,
positions.csv, equity_curve.csv, scenario_realizations.csv e validation.html.
Cada linha deve remeter a fontes e identificadores do manifesto.
Estes nomes especificam entregas futuras, nao arquivos ja gerados.

## Changelog deste PR

- Registrado baseline PR60 e cinco achados de consistencia.
- Definidos experimentos de sinal e carteira, horizontes e custos.
- Documentadas limitacoes do universo curado e do holdout ja consultado.
- Definidos controles de eventos, disponibilidade, reproducao e incerteza.
- Estabelecida sequencia de implementacao e condicoes para estudar pesos.
