# Identidade fiscal na normalizacao ciclica

Implementa a primeira correcao do protocolo proposto no PR61 (achado A01).

## Comportamento

O historico anual e reconciliado antes de aplicar a janela maxima. Datas
proximas, inclusive em anos civis diferentes, exigem evidencia de mesmo
exercicio: inicio e fim proximos quando informados, ou receita e lucro
compativeis quando uma fonte anual omite a data inicial. Datas sozinhas
nao autorizam unir periodos de fontes diferentes.

As tolerancias de identidade ficam em CyclicalNormalizationAssumptions:
350 a 380 dias para duracao anual informada (inclui 52/53 semanas), ate
7 dias entre datas equivalentes e 0,5% entre os valores financeiros usados
como ancora. Sao tolerancias operacionais documentadas, nao pesos de score.
Um periodo de transicao fora desses limites fica em quarentena.

A selecao prioriza SEC, intervalo informado, filing mais recente disponivel,
confianca e desempate deterministico pelo conteudo. A admissibilidade temporal
do filing continua sendo responsabilidade do coletor point-in-time existente.
O resolvedor nao transforma dados atuais em dados historicamente disponiveis.

O calculo utiliza uma observacao coerente por exercicio. As observacoes das
fontes, seus valores usados, datas, documento e URL permanecem em
source_observations no JSON. Fontes com datas exatamente iguais tambem sao
preservadas antes da resolucao, mesmo quando o adaptador faz merge de campos.
Grupos ambiguos, periodos sobrepostos, emissores ou moedas diferentes sao
excluidos, com motivo e observacoes na trilha de avisos.

Datas iniciais ausentes sao explicitamente identificadas como duracao inferida
da fonte anual. Uma fonte sem inicio nao comprova por si so a duracao real;
periodos TTM/trimestrais precisam vir identificados pelo contrato de entrada.
Periodos extremos ou mudancas fiscais nao resolvidas exigem revisao e podem
reduzir a cobertura. Nao se atribui um ano fiscal apenas pelo ano civil.

## Evidencia de regressao

Fixtures sinteticas reproduzem as datas observadas no relatorio MLI:
sete exercicios de 2019 a 2025 e tres registros Yahoo adicionais em
2023/2024/2025. O resultado passa de dez candidatos para sete exercicios
unicos, conserva as observacoes e independe da ordem de entrada.
Este teste nao e uma nova coleta da MLI nem um replay dos arquivos originais.

Outros casos cobrem 52/53 semanas, encerramentos distintos no mesmo ano
civil, duplicatas exatas, janela apos reconciliacao, duracao de transicao,
TTM, sobreposicao, conflito de valores, moeda e emissor. Duplicatas nao
desbloqueiam o minimo de cinco exercicios para normalizar.

## Changelog

- Reconciliacao de identidade fiscal antes da contagem e da janela maxima.
- Preservacao de fontes originais no merge historico.
- Quarentena auditavel de identidade ambigua e periodos nao anuais.
- Relatorio com exercicios unicos, intervalo de encerramentos e evidencia.
- Parametros de tolerancia centralizados e testes de regressao.

Pesos, limiares de recomendacao e formulas de valuation nao foram alterados.
Valores normalizados e valuations podem mudar porque a amostra foi corrigida.
A02-A05 (confianca dos pares e coerencia decisoria) continuam pendentes;
esta correcao isolada nao valida a recomendacao Comprar nem o benchmark V2.
