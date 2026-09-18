# Auditoria de execucao dos arquivos existentes

Auditoria local de 2026-09-16; diagnostico, nao autorizacao de benchmark.

| Verificacao | Ativas | Lifecycle |
|---|---:|---:|
| Observacoes | 345 | 50 |
| Regras de precos existentes aprovadas | 345 | 50 |
| Retornos reproduzidos sem divergencia (tolerancia 1e-10) | 345 | 50 |
| Observacoes com sessoes ausentes frente ao benchmark | 0 | 0 |
| Entrada na propria data do sinal | 254 | 37 |
| Observacoes sem volume completo | 345 | 0 |

As sessoes foram comparadas a serie arquivada do benchmark, e nao a um
calendario independente de bolsa. Lacunas simultaneas nas duas series nao
sao detectadas por esse teste. Volume disponivel nao comprova, sozinho,
capacidade de executar uma ordem.

O calculo existente foi reaplicado com os eventos terminais e a auditoria de
negociabilidade cadastrados. Isso verifica coerencia interna; nao constitui
nova verificacao externa das fontes SEC dos eventos.

## Diferencas que bloqueiam o contrato

- A entrada existente usa o primeiro fechamento na data do sinal ou depois.
  O manifesto exige o proximo pregao elegivel. Ha 291 entradas na mesma data.
- As series ativas arquivadas nao fornecem volume completo para verificar o
  teto de participacao de 10%.
- O executor de coleta e avaliacao calcula retornos por observacao. Ele nao
  implementa carteira mensal, ordens, custos de 10 bps por lado, limite setorial,
  acoes inteiras, giro e alocacao de caixa.
- Aquisicoes em dinheiro usam reinvestimento no benchmark no calculo existente;
  a compatibilidade com a regra de caixa da carteira precisa ser explicitada.
- Esta auditoria usa somente o horizonte existente de 12 meses. Os demais
  horizontes ainda precisam de janelas e verificacoes proprias.

## Sequencia de implementacao

1. Concluir a correcao de contagens do manifesto no PR67.
2. Fixar regras operacionais faltantes (momento/preco de execucao, calendario,
   caixa apos aquisicao, desempates e saidas) em revisao versionada, antes de
   observar resultados do novo experimento.
3. Completar e arquivar volume e precos exigidos, mantendo os arquivos antigos.
4. Implementar simulador de carteira e custos com testes de ordens e eventos.
5. Verificar cobertura e replay antes de liberar o benchmark completo.

Pesos e formulas de valuation permanecem inalterados. Os arquivos privados
de precos e os relatorios detalhados por observacao nao sao publicados.

