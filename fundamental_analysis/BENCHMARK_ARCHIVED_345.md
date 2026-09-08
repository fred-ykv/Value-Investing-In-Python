# Benchmark historico arquivado: 345 observacoes

## Decisao

**Reproducao aprovada; recalibracao nao autorizada.** Esta rodada diagnostica
preserva pesos, formulas, travas, classificacoes e parametros financeiros.
Reproduzir um resultado comprova consistencia computacional, nao qualidade
da recomendacao de investimento.

Protocolo registrado localmente em 2026-09-04, antes da coleta: os 40 tickers
ativos de `DEFAULT_BENCHMARK_CASES`, filings de 2015 a 2025, no maximo dez por
empresa, retornos disponiveis ate 2026-09-03 e divisao temporal em 2022.
Base congelada: `09a5aca0c6a805920152b1c66614b4e424d2c4ac` (PR #57).
Auditoria consolidada em 2026-09-08.

## Reproducibilidade

| Verificacao | Resultado |
|---|---:|
| Empresas ativas | 40 |
| Observacoes produzidas | 345 |
| Erros de execucao / casos ignorados | 0 / 0 |
| Observacoes aprovadas nos controles de dados point-in-time | 325 |
| Observacoes reprovadas por dados criticos | 20 |
| Arquivos de codigo comparados com a base GitHub | 123, sem divergencia |
| Verificacoes computacionais do diagnostico | 4.773, todas aprovadas |
| Resultados identicos no replay offline | 6 de 6 |
| Tentativas de rede durante o replay | 0 |

O arquivo contem 673 objetos: 41 respostas SEC, 613 janelas de precos,
13 entradas macro e seis saidas de referencia. Captura e replay usaram
Python 3.12.14. O bloqueio de rede e o isolamento sao os descritos no
[procedimento de replay](HISTORICAL_REPLAY.md), nao um firewall do sistema.

SHA-256 do manifesto:
`05915d73cc5b85f0bd55533f7fb49b1eea2fe1abfbbfb7487c848ebc828bbb0f`.

As verificacoes incluem reconciliacao do score, pesos normalizados, limites
das dimensoes, datas e rastreabilidade. Nao sao 4.773 testes unitarios nem
observacoes independentes. Os precos e respostas integrais permanecem em
arquivo privado; este documento publica apenas o diagnostico agregado.

## Cobertura e poder de discriminacao

| Amostra temporal | Total | Utilizaveis | Dados point-in-time aprovados | Spearman score x retorno excedente | Monotonicidade |
|---|---:|---:|---:|---:|---:|
| Calibracao | 155 | 143 | 92,3% | 0,066 | 25,0% |
| Validacao | 156 | 149 | 95,5% | -0,095 | 25,0% |
| Embargo por sobreposicao temporal | 34 | Nao usado nesta comparacao | - | - | - |

Os 325 aprovados nos controles de dados incluem observacoes em embargo.
Portanto, nao equivalem a 325 observacoes utilizaveis para calibracao.
Spearman mede se scores maiores acompanham retornos excedentes maiores;
estes resultados nao demonstram uma ordenacao financeira robusta.
Monotonicidade mede a consistencia dessa ordenacao entre faixas de score.

O universo ativo foi escolhido retrospectivamente e preserva vies de
sobrevivencia e selecao. A parcela chamada validacao/holdout ja foi
inspecionada: nao e uma amostra independente nunca observada e nao deve
orientar a escolha de parametros. Ha observacoes repetidas por empresa e
retornos possivelmente sobrepostos, sem inferencia de significancia aqui.

## Alertas prioritarios

1. **Amostra incompleta para recalibracao.** Nao ha empresas retiradas nem
   cancelamentos de capital nesta captura. O grupo FCF negativo/early growth
   tem apenas quatro observacoes de uma empresa na calibracao, abaixo dos
   minimos existentes de oito observacoes e tres empresas.
2. **Dados criticos insuficientes em 20 observacoes.** Investigar demonstrativo,
   identidade do emissor e extracao antes de qualquer preenchimento. Zero
   economico e ausencia de dado nao sao equivalentes.
3. **Premissas substitutas frequentes no custo de capital.** 244 de 345
   observacoes sinalizam fallback na taxa aplicada. Em 215, o padrao inclui
   custo da divida pre-impostos substituto com beta sem fallback. Isto nao
   significa que todo o WACC/Ke tenha sido arbitrado: auditar por componente.
4. **Valuation saturado em empresas com FCFF negativo.** Em 16 observacoes,
   apenas Growth-Tech produziu valuation e a dimensao atingiu aproximadamente
   1; quatro receberam Comprar. Verificar reinvestimento, diluicao, convergencia
   de margens e incerteza antes de propor mudancas. Nao e prova isolada de bug.
5. **Crescimento do FCFF frequentemente substituido.** O fallback ocorre em
   79/100 observacoes de bancos, 48/48 de early growth, 23/97 de tech e 5/100
   de tradicionais. Nos bancos FCFF nao e a base economica central; em fluxos
   negativos, rejeitar crescimento percentual sem significado e intencional.
6. **Comparaveis historicos nao validados.** Pares atuais foram excluidos de
   todas as observacoes. Esta rodada nao testa o componente relativo do
   score e nao deve ser comparada ao relatorio atual sem essa ressalva.

### Observacoes com dados criticos reprovados

Os anos abaixo sao os anos das observacoes/filings, nao necessariamente o
exercicio fiscal do demonstrativo.

| Empresa | Anos | Dados apontados |
|---|---|---|
| CAT | 2016, 2017, 2018 | Caixa |
| DE | 2016 | Divida |
| F | 2016, 2019, 2022 | Divida em 2016/2022; EBIT em 2019 |
| GM | 2016, 2017 | Depreciacao e amortizacao |
| META | 2018, 2019 | Divida |
| TFC | 2015, 2016 | Lucro liquido, patrimonio e acoes |
| LCID | 2021 | Receita, caixa e acoes |
| JOBY | 2022, 2023 | Receita |
| ACHR | 2022, 2023, 2024, 2025 | Receita |

Revisar especialmente empresas pre-receita, antecessoras e reorganizacoes.
Nao completar divida, receita ou lucro ausentes com zero automaticamente.

## Empresas retiradas: conciliacao pendente

Foram confrontados dez eventos com 11 documentos oficiais SEC. O pacote
antigo contem resultados, nao as series integrais utilizadas. Por isso nao
foi anexado ao replay nem usado para calcular o impacto das divergencias.
Valores por acao abaixo sao termos de aquisicao/cancelamento, nao cotacoes.

| Empresa | Evento / valor por acao | Evidencia SEC e situacao |
|---|---|---|
| MDLA | 2021-10-29 / US$ 34,00 | [Suspensao antes da abertura em 29/10](https://www.sec.gov/Archives/edgar/data/1540184/000114036121036202/brhc10030210_8k.htm); resultado antigo usa preco de 29/10. Investigar. |
| CLDR | 2021-10-08 / US$ 16,00 | [Suspensao antes da abertura em 08/10](https://www.sec.gov/Archives/edgar/data/1535379/000119312521294924/d223205d8k.htm); resultado antigo usa 08/10 e cadastro encerra em 11/10. Investigar. |
| CSPR | 2022-01-25 / US$ 6,90 | [Conclusao da aquisicao](https://www.sec.gov/Archives/edgar/data/1598674/000114036122002541/brhc10033043_ex99-1.htm); preco antigo de 24/01. Horario exato da suspensao ainda nao estabelecido nesta auditoria. |
| PLAN | 2022-06-22 / US$ 63,75 | [Suspensao antes da abertura em 22/06](https://www.sec.gov/Archives/edgar/data/1540755/000119312522178282/d333986d8k.htm); resultado antigo usa 22/06. Investigar. |
| ZEN | 2022-11-22 / US$ 77,50 | [Conclusao da aquisicao](https://www.sec.gov/Archives/edgar/data/1463172/000114036122042681/brhc10044488_8k.htm); preco antigo de 21/11. Horario exato da suspensao ainda nao estabelecido nesta auditoria. |
| COUP | 2023-02-28 / US$ 81,00 | [Suspensao antes da abertura em 28/02](https://www.sec.gov/Archives/edgar/data/1385867/000119312523054081/d455192d8k.htm); resultado antigo usa 28/02. Investigar. |
| MNTV | 2023-05-31 / US$ 9,46 | [Suspensao em 01/06 antes da abertura](https://www.sec.gov/Archives/edgar/data/1739936/000114036123027837/ny20009286x1_8k.htm); preco antigo de 31/05 nao conflita com essa data. |
| XM | 2023-06-28 / US$ 18,15 | [Suspensao antes da abertura em 28/06](https://www.sec.gov/Archives/edgar/data/1747748/000162828023023743/xm-20230628.htm); resultado antigo usa 28/06. Investigar. |
| BBBY | 2023-09-29 / US$ 0,00 | [Cancelamento sem recuperacao para acoes](https://www.sec.gov/Archives/edgar/data/886158/000119312523238592/d521320dex21.htm) e [data de eficacia](https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010dex991.htm). Zero e o evento juridico, nao preenchimento de preco ausente. |
| NEWR | 2023-11-08 / US$ 87,00 | [Suspensao antes da abertura em 08/11](https://www.sec.gov/Archives/edgar/data/1448056/000119312523273042/d469974d8k.htm); preco antigo de 07/11 nao conflita com essa data. |

Uma linha no dia da suspensao pode ser ajuste/registro de liquidacao do
provedor, e nao necessariamente negocio executavel. As cinco divergencias
nao autorizam alterar datas ou excluir todos os precos do dia do evento.
Conferir volume, splits, dividendos e explicacao do provedor; volume positivo
isolado tambem nao comprova negociabilidade.

A regra atual de retorno reinveste o pagamento terminal no benchmark na data
efetiva, sem custos ou impostos. Trata-se de convencao de calculo, nao prova
de disponibilidade imediata do dinheiro para o investidor. A sensibilidade
a atrasos de liquidacao deve ser estudada separadamente.

## Proxima sequencia

1. Executar [o notebook de evidencias Tiingo](../COLAB_LIFECYCLE_EVIDENCE.ipynb),
   mantendo a chave apenas no Colab. Conservar o ZIP privado.
2. Reconciliar datas de negociacao e tratamento economico, documentando cada
   decisao. O novo coletor nao corrige datas nem libera o benchmark.
3. Corrigir apenas lacunas comprovadas de dados/identidade, com testes.
4. Recolher a amostra lifecycle com codigo congelado e arquivo completo;
   repetir os seis resultados offline antes de combinar universos.
5. Predefinir uma nova avaliacao que considere selecao, dependencia entre
   observacoes e eventos adversos. So depois discutir pesos e limites,
   sem ajustar o modelo ao holdout ja observado.
