# Negociabilidade historica e quarentena auditavel

## Objetivo e limites

Uma linha armazenada pelo fornecedor nao comprova um novo negocio. O PR59
separa datas de suspensao, ultima cotacao elegivel na janela e data efetiva
de aquisicao/cancelamento. Os precos originais permanecem intactos; somente
a copia usada nos calculos exclui registros a partir do limite revisado.

Nao foram alterados pesos, formulas de valuation, beta, retorno, drawdown,
limiares de recomendacao, valores contratuais ou datas dos eventos. O cadastro
`endDate` do Tiingo continua representando a ultima linha recebida.
Nao se exclui uma linha apenas por ter volume zero, volume ausente ou cair
na data da aquisicao. Volume ausente nao e convertido para zero.

## Arquitetura e controles

### Completude da divida historica

O campo `total_debt` somente recebe valor positivo quando ha um conceito
patrimonial de divida ou de obrigacao financeira no filing ancorado. Uma
despesa de juros na demonstracao de resultados, sozinha, nao determina o
saldo devedor no encerramento e pode estar relacionada a arrendamentos,
descontos ou outros itens. Nessa situacao o sistema pode usar o fallback
conservador de divida zero com confianca reduzida e alerta explicito; isso nao
equivale a afirmar que a empresa nunca teve divida. Esse criterio evita tanto
inventar saldo quanto bloquear empresas que a SEC descreve como sem divida
pendente.

1. `price_eligibility.py`: regras revisadas, vinculadas a ticker, CIK, classe,
   identificador cadastrado, evento e documento SEC. A ligacao entre SEC e
   Tiingo e curada pelo projeto; nao e certificacao do fornecedor para CIK
   ou classe. Outros provedores/classes exigem reconciliacao antes de uso.
2. `lifecycle_evidence.py`: leitura do ZIP do PR58 ou de sua pasta `evidence`,
   sem extrair arquivos ou executar o codigo contido no pacote. Confere
   manifesto completo, hashes, respostas esperadas, metadados e cada preco
   do CSV contra o JSON original. Limites de tamanho e caminhos sao validados.
3. `calculate_price_outcome`: valida identidade, evidencia, duplicidades,
   precos e volumes antes da normalizacao. Aplica a regra de negociabilidade
   antes de selecionar entrada, saida, beta e preco terminal. Evento ausente,
   desconhecido ou divergente bloqueia o fluxo lifecycle. Erro de qualidade
   nao aciona fallback de provedor. A regra terminal e usada para avaliar
   o resultado realizado, nao como informacao preditiva no score.
4. CSV e manifesto da coleta guardam `price_eligibility_audit`: regra,
   fonte, hashes da evidencia e da janela recebida, contagens, datas e cada
   registro excluido com preco, volume e motivo. As datas de cobertura nesse
   campo sao da janela consultada, nao necessariamente da serie inteira.
5. O arquivo de replay guarda os precos recebidos **antes da exclusao**,
   incluindo volume e hash da evidencia. A reproducao reaplica a mesma regra
   e compara as seis saidas. Nao precisa de CSV, ZIP ou provedor externo para
   refazer a analise. Conservar tambem o ZIP para conferir os campos brutos
   que nao sao consumidos pelo modelo, como OHLC e eventos corporativos.
6. Observacoes lifecycle antigas sem auditoria valida ficam fora da amostra
   utilizavel e geram bloqueio explicito de recalibracao. Erros parciais de
   coleta geram codigo de saida diferente de zero, mesmo havendo resultados.

Hashes detectam alteracoes e permitem vincular entradas a resultados, mas
nao sao assinatura digital do fornecedor. As validacoes nao sao uma barreira
contra alguem que altere deliberadamente dados, codigo e todos os hashes.
O campo `eligible_with_audit` significa elegibilidade nesta verificacao de
precos, nao aprovacao financeira ou estatistica da amostra.

## Regras revisadas

Primeira data inelegivel, inclusive; datas em resolucao diaria.

| Ticker | Limite | Evidencia e ressalva |
|---|---|---|
| MDLA | 2021-10-29 | [Suspensao antes da abertura, item 3.01](https://www.sec.gov/Archives/edgar/data/1540184/000114036121036202/brhc10030210_8k.htm) |
| CLDR | 2021-10-08 | [Suspensao antes da abertura, item 3.01](https://www.sec.gov/Archives/edgar/data/1535379/000119312521294924/d223205d8k.htm) |
| CSPR | 2022-01-25 | [Pedido de suspensao antes da abertura](https://www.sec.gov/Archives/edgar/data/1598674/000114036122002541/brhc10033043_8k.htm); nao apresentar pedido como confirmacao operacional da bolsa |
| PLAN | 2022-06-22 | [Suspensao antes da abertura](https://www.sec.gov/Archives/edgar/data/1540755/000119312522178282/d333986d8k.htm) |
| ZEN | 2022-11-22 | [Pedido de retirada antes da abertura](https://www.sec.gov/Archives/edgar/data/1463172/000114036122042681/brhc10044488_8k.htm); mesma ressalva de CSPR |
| COUP | 2023-02-28 | [Suspensao antes da abertura](https://www.sec.gov/Archives/edgar/data/1385867/000119312523054081/d455192d8k.htm) |
| MNTV | 2023-06-01 | [Suspensao no dia seguinte a aquisicao](https://www.sec.gov/Archives/edgar/data/1739936/000114036123027837/ny20009286x1_8k.htm); preservar 31/05 |
| XM | 2023-06-28 | [Suspensao da classe A antes da abertura](https://www.sec.gov/Archives/edgar/data/1747748/000162828023023743/xm-20230628.htm) |
| BBBY/BBBYQ | 2023-09-30 | [Data de eficacia 29/09](https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010dex991.htm) e [plano](https://www.sec.gov/Archives/edgar/data/886158/000119312523238592/d521320dex21.htm): preservar a linha de 29/09 na resolucao diaria, sem presumir horario intradiario. O pagamento terminal continua zero; a saida da Nasdaq nao elimina o historico OTC |
| NEWR | 2023-11-08 | [Suspensao antes da abertura](https://www.sec.gov/Archives/edgar/data/1448056/000119312523273042/d469974d8k.htm) |

O preco negociado nao substitui o valor contratual da aquisicao. A convencao
existente de reinvestir o pagamento no benchmark na data efetiva permanece;
nao comprova a data real de recebimento do dinheiro pelo investidor.

## Como usar no Colab

Depois de atualizar o repositorio em uma pasta separada e instalar suas
dependencias, envie `lifecycle_evidence.zip` ao Colab. Nao e necessario
informar novamente a chave Tiingo para ler esse pacote. A coleta de
demonstrativos SEC e benchmarks ainda precisa de internet e de
`SEC_USER_AGENT` com o contato do pesquisador.

Na pasta do repositorio, use nomes novos para preservar coletas anteriores:

```python
!python build_historical_dataset.py --universe lifecycle --lifecycle-evidence /content/lifecycle_evidence.zip --start-year 2015 --end-year 2023 --max-filings-per-company 100 --outcomes-available-through 2026-09-08 --outdir historical_calibration_outputs/lifecycle_59 --archive-dir historical_calibration_outputs/archive_59
```

O intervalo acima mantem as datas da rodada de validacao; nao amplia a amostra.
SPY, IWM e QQQ continuam sendo escolhidos pela configuracao existente. Uma
nova consulta desses ETFs pode produzir uma nova versao dos precos ajustados;
por isso, arquivar e conferir cada coleta, sem misturar versoes implicitamente.

Em seguida, usando a mesma versao do codigo:

```python
!python -I -S replay_historical_dataset.py historical_calibration_outputs/archive_59 --outdir historical_calibration_outputs/replay_59
```

Exigir `passed: true`, `errors: 0`, `network_attempts: []` e seis resultados
identicos. A alternativa `--historical-prices-csv evidence/normalized_prices.csv`
exige o pacote completo na mesma pasta, nao apenas o CSV isolado. Um manifesto
incompleto nunca e aproveitado parcialmente para liberar o benchmark.

Arquivos antigos continuam reproduziveis com seu codigo original; a versao
nova nao deve substituir silenciosamente a referencia antiga.

## Evidencia desta implementacao

- Suite local: 268 testes aprovados, incluindo pacotes adulterados,
  metadados divergentes, CSV/JSON nao reconciliados, regras ausentes,
  valores invalidos, volume ausente, MNTV e BBBY, fallback e replay isolado.
- Pacote privado: 18.794 registros preservados, seis em quarentena de cinco
  empresas. Nenhuma linha excluida de MNTV ou BBBY.
- Diagnostico de precos: 50 janelas identicas a referencia corrigida na
  auditoria independente, usando o mesmo SPY. A referencia original sem
  quarentena tinha cinco datas terminais diferentes, sem diferenca numerica
  nessas janelas. Isso nao prova ausencia de impacto em outros dados.
- Coleta financeira real: 50 observacoes de dez empresas; zero erros de
  execucao e 50 auditorias de negociabilidade validas. Usou novos documentos
  SEC, o ZIP privado e as series SPY/IWM/QQQ e dados macro ja congelados.
- Replay completo: 126 objetos (10 SEC, 99 janelas de precos, 11 macro e seis
  saidas); seis arquivos identicos e zero tentativas de rede.
- 46 observacoes passam os controles financeiros point-in-time. Quatro da
  NEWR (2015 a 2018) continuam rejeitadas por ausencia de divida total. Nao
  foram preenchidas com zero. Execucao concluida nao equivale a dado aprovado.
- A coleta completa nao e o diagnostico pareado com SPY: conserva os ETFs
  setoriais da configuracao. Nao se afirma igualdade de scores ou retornos
  com vintages financeiras antigas.

SHA-256 do manifesto de replay privado:
`d8f5cc106f9aed7b9373395c0495b0489f8a09f6f526d8c89b27efa09b4c3633`.

O modelo continua **nao pronto para recalibracao**. Antes de integrar a rodada
as 345 observacoes ativas, investigar a lacuna de divida da NEWR e conferir
compatibilidade de codigo, configuracao, universo, periodos e fontes. Nunca
usar o holdout ja inspecionado para escolher pesos. Nenhum dado licenciado,
resposta SEC em massa, token ou ZIP privado foi adicionado ao repositorio.
