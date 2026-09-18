# Evidencias de dividendos e splits

O suplemento de volume recebido cobre 117.095 pontos em 44 simbolos.
Suas 1.359 pendencias de dividendos abrangem 31 simbolos. Ele nao preservou
splits: a versao anterior so gravava eventos quando nao havia dividendos
pendentes. Essa perda foi corrigida para novas coletas.

## Coleta de datas

Configure TIINGO_API_KEY no ambiente (no Colab, use Secrets). Execute:

```sh
python collect_dividend_evidence.py --source-archive market_supplement_archive --output dividend_evidence_archive
```

O diretorio de saida deve ser novo. Cada resposta completa fica arquivada
com URL sem token, hash e horario de captura. Falhas por ticker preservam
os resultados parciais. A chave nunca e escrita no pacote.

Documentacao do provedor:
https://www.tiingo.com/documentation/corporate-actions/dividends

A disponibilidade do endpoint e a cobertura historica dependem da conta.
Datas nulas sao pendencias; nao sao estimadas. Declaracao posterior a ex-date,
pagamento anterior a ex-date e multiplas distribuicoes na mesma data exigem
revisao. O coletor nao publica valores como fluxos de caixa aprovados:
identidade permanente, moeda, base por acao e tipo de distribuicao ainda
precisam ser reconciliados. Valores Yahoo podem estar ajustados por splits.

## Cobertura

Novas coletas de mercado salvam corporate_action_candidates por ticker,
mesmo com dividendos pendentes ou falha de reconciliacao de volume.
Uma resposta sem dividendos nao certifica ausencia de splits, aquisicoes ou
cancelamentos. Por isso nenhuma cobertura global e emitida automaticamente.
Os 10 casos lifecycle e os eventos terminais exigem sua propria verificacao.

Hashes comprovam integridade relativa aos manifestos, nao assinatura digital
nem autenticidade independente do provedor. O benchmark permanece bloqueado.

