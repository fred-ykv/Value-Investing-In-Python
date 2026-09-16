# Regras operacionais propostas - simulador de pesquisa

Este adendo e uma proposta revisavel. Nao substitui o manifesto 1.1 nem
autoriza a execucao do benchmark. Nenhum resultado real foi usado para defini-lo.

- Sinal: fechamento do ultimo pregao do mes, usando dados disponiveis ate ali.
- Execucao: fechamento bruto em USD do primeiro pregao seguinte, apos vendas.
- Ranking: score decrescente; empate resolvido por ticker em ordem alfabetica.
- Saida: remocao do ranking no rebalanceamento seguinte ou evento terminal.
- Alvos: 5% por posicao, 20 posicoes, 25% por setor na formacao dos alvos.
  Oscilacoes entre rebalanceamentos nao disparam vendas automaticas.
- Custos: 10 bps por lado; sensibilidades separadas de 5 e 25 bps. Caixa
  disponivel limita compras apos custos; quantidades inteiras.
- Liquidez: ordens acima de 10% do volume diario invalidam a simulacao.
- Aquisicao: contraprestacao documentada vira caixa, sem reinvestimento
  automatico no benchmark. Cancelamento documentado tem valor zero.
- Caixa rende zero. Nao ha alavancagem, short, impostos ou conversao cambial.
- Precos brutos exigem eventos corporativos separados para evitar dupla contagem.
  Calendario, sinais, classificacao setorial PIT e eventos exigem evidencia.

## Limites desta primeira implementacao

O simulador e independente do coletor. Ainda faltam integracao ao preflight,
calendario validado, cadastro temporal de direitos a dividendos (ex-date versus
pagamento), tratamento de fracoes e relatorio de performance versus benchmarks.
O mecanismo simples de dividendos por acao mantida so serve para fixtures sem
negociacao entre ex-date e pagamento. Nao usar essa aproximacao em dados reais.
Os arquivos atuais de 12 meses nao bastam para comprovar esses requisitos.

