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

O simulador e independente do coletor. A entrada protegida reexecuta o preflight
quando disponivel, mas permanece bloqueada mesmo com status ready: falta vincular
os dados de entrada aos hashes das evidencias. Nao e uma integracao concluida.
O calendario XNYS e validado com exchange_calendars e registra versao e hash das
sessoes. Instale requirements-backtest.txt e execute check_portfolio_calendar.py
para a verificacao independente de feriados, lacunas e ordenacao.
Ainda faltam tratamento de fracoes e relatorio de performance versus benchmarks.
Dividendos ordinarios registram direitos pelas acoes mantidas antes da negociacao
na ex-date. A venda posterior preserva o recebivel; compras na ex-date nao recebem.
Recebiveis integram o patrimonio, mas so viram caixa na primeira sessao na data
de pagamento ou depois. Direitos pendentes ao fim permanecem no patrimonio.
Dividendos especiais com due bills nao sao suportados. Split e dividendo na mesma
data sao rejeitados ate reconciliar a base por acao. Eventos terminais impedem
recompra do ticker em todos os rebalanceamentos posteriores.
Os arquivos atuais de 12 meses nao bastam para comprovar esses requisitos.

