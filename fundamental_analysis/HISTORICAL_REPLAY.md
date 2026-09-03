# Arquivo historico e reproducao sem internet

O objetivo e refazer a mesma analise com as mesmas entradas, sem consultar
Yahoo, SEC, Tiingo, Treasury ou Damodaran durante a reproducao. Isso verifica
o software e a rastreabilidade, nao a validade economica da recomendacao.
Nenhum peso, formula ou limite financeiro e alterado por este recurso.

## 1. Coletar e arquivar

Na pasta do repositorio, com as dependencias instaladas e SEC_USER_AGENT ja
configurado com o contato do pesquisador:

```bash
python build_historical_dataset.py NUE MSFT JPM RIVN --start-year 2024 --end-year 2025 --max-filings-per-company 2 --outcomes-available-through 2026-09-03 --outdir historical_calibration_outputs/captura_01 --archive-dir historical_calibration_outputs/arquivo_01
```

No Colab, acrescente `!` antes do comando. Para repetir uma nova coleta, use
outro nome de pasta, por exemplo captura_02 e arquivo_02. Nao apague nem
sobrescreva um pacote usado como evidencia. Chamadas sem --archive-dir
continuam funcionando como antes, mas nao produzem um pacote de replay.

## 2. Reproduzir sem provedores

Use a mesma versao do codigo. Nao sao necessarios token Tiingo, contato SEC
ou pacotes de coleta para este comando:

```bash
python -I -S replay_historical_dataset.py historical_calibration_outputs/arquivo_01 --outdir historical_calibration_outputs/replay_01
```

Tambem pode ser executado em um computador sem conexao, desde que Python,
esta versao do repositorio e a pasta arquivo_01 estejam disponiveis localmente.
No Colab, o comando desabilita o acesso a rede no processo de reproducao;
o navegador e a sessao do Colab continuam conectados.

O modo -I -S ignora configuracoes Python do usuario e site-packages. O replay
instala um bloqueio de auditoria Python para sockets, processos externos e
carregamento nativo via ctypes. Nao e um firewall nem uma barreira contra
codigo hostil. Os clientes de replay somente leem o pacote e nao instanciam
provedores de precos nem consultam caches da coleta original.

## 3. Conferir o resultado

O arquivo replay_verification.json deve mostrar:

- passed: true;
- network_attempts: lista vazia;
- errors: 0 e pelo menos uma observacao reproduzida;
- outputs_identical: true para os seis arquivos de referencia.

A verificacao compara todo o conteudo, sem tolerancia numerica para aceitar
scores diferentes. Apenas finais de linha de arquivos texto sao normalizados
na leitura. Outra versao do Python pode ser registrada, mas so sera aprovada
se o resultado completo continuar identico. Alteracao de codigo bloqueia o
replay; use o commit original para provar reproducibilidade. Estudos de uma
nova versao do modelo sao outra atividade e nao devem substituir a referencia.

## O que fica guardado

- manifest.json e manifest.sha256: versao, parametros de execucao, universo,
  eventos terminais, limite dos resultados futuros e indice dos objetos.
- objects/: conteudo JSON identificado por SHA-256, sem caminhos arbitrarios.
- price_series: janela exata solicitada, ticker, datas, adjusted_close,
  raw_close usado no valuation, source, security_id e issuer_cik quando
  fornecidos pelo provedor. A janela anterior usada no beta tambem e salva.
- sec_json e macro_text: respostas efetivamente consumidas pelos parsers.
- expected_output: CSV de observacoes, manifesto da coleta, relatorio da
  coleta, resumo historico e relatorios temporal Markdown/JSON.

O arquivo nao troca o nome da fonte por "replay": preserva a origem usada
no calculo, e a comprovacao da reproducao fica no relatorio de verificacao.
O horario captured_at_utc indica quando a entrada foi congelada, nao quando
o documento foi publicado nem quando um cache foi originalmente baixado.
Datas dos filings e observacoes macro continuam nos documentos e na auditoria.

## Limites importantes

1. Um piloto antigo sem precos arquivados nao pode ser certificado retroativamente.
   Uma nova coleta arquivada constitui nova referencia, mesmo para as mesmas datas.
2. O pacote guarda os precos normalizados entregues ao calculo. Nao e a resposta
   HTTP bruta nem uma vintage certificada dos ajustes historicos do fornecedor.
3. Os hashes detectam corrupcao e alteracoes acidentais; nao sao assinatura
   digital contra alguem que possa substituir tambem o manifesto e seu hash.
4. Falta de objeto, entrada fora do pacote, divergencia ou tentativa de rede
   reprovam o replay. Nao ha preenchimento automatico por cotacao atual.
5. Os resultados de uma coleta com erros nao recebem aprovacao de replay.
6. Nao publique os pacotes de dados no GitHub publico. Conserve-os localmente
   e respeite as condicoes de uso e redistribuicao de cada fornecedor.
7. O benchmark amplo, incluindo empresas retiradas da bolsa e eventos terminais,
   continua pendente. Reproduzir oito observacoes nao elimina vies de sobrevivencia,
   nao valida o holdout e nao autoriza recalibrar pesos.
