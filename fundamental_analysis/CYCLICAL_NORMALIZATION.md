# Normalizacao de empresas ciclicas

## Objetivo

Empresas ligadas a metais, mineracao, commodities, quimicos, maquinas pesadas e
automoveis podem parecer muito baratas no pico do ciclo e muito caras no fundo.
O modulo evita extrapolar mecanicamente um unico ano de margem, lucro ou caixa.
Ele nao altera pesos do score nem os limites de Comprar, Observar e Evitar.

Referencias metodologicas:

- Damodaran, normalizacao por margem operacional de 5 a 10 anos aplicada a
  receita corrente: https://pages.stern.nyu.edu/adamodar/New_Home_Page/littlebook/commodityvaluedrivers.htm
- Damodaran, risco de assumir recuperacao instantanea ao substituir lucro
  corrente pelo normalizado: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/normearn.htm
- Damodaran, definicao de FCFF e reinvestimento:
  https://pages.stern.nyu.edu/~adamodar/New_Home_Page/definitions.html
- CFA Institute, uso de lucro de meio de ciclo e medias de ciclo completo em
  empresas ciclicas: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-based-valuation-price-enterprise-value-multiples

## Aplicabilidade

A normalizacao so pode ser aplicada quando:

1. a empresa e do tipo tradicional;
2. o perfil setorial ou a curadoria do benchmark a identifica como ciclica;
3. existem pelo menos cinco anos validos para todos os componentes;
4. a confianca agregada e igual ou superior ao minimo em `config.py`.

Bancos, growth/tech e empresas tradicionais nao ciclicas preservam os valores
correntes. No benchmark historico, a classificacao vem do universo curado e nao
de informacoes setoriais atuais.

## Formulas

Para cada ano, o sistema calcula proporcoes, e nao medias de valores nominais:

```text
margem EBIT = EBIT / receita
margem liquida = lucro liquido / receita
margem FCFF = FCFF / receita
reinvestimento = NOPAT - FCFF
margem de reinvestimento = reinvestimento / receita
```

As series sao limitadas aos intervalos economicos configurados e recebem
winsorizacao de 10% em cada cauda. Depois:

```text
EBIT normalizado = receita corrente x margem EBIT normalizada
NOPAT normalizado = EBIT normalizado x (1 - aliquota normalizada)
lucro normalizado = receita corrente x margem liquida normalizada
reinvestimento normalizado = receita corrente x margem de reinvestimento normalizada
FCFF normalizado = NOPAT normalizado - reinvestimento normalizado
```

O controle independente `receita corrente x margem FCFF normalizada` mede a
consistencia do FCFF por componentes. Divergencias relevantes reduzem confianca
e aparecem nos alertas.

## Uso no valuation

- DCF/FCFF: parte do FCFF corrente e converge linearmente ao FCFF normalizado em
  tres anos. Isso evita presumir uma recuperacao instantanea.
- Graham: usa lucro liquido normalizado por acao.
- EVA: usa NOPAT normalizado sobre o capital investido corrente.
- Crescimento explicito: quando a normalizacao e aplicada, fica limitado a 8%
  ao ano para evitar combinar lucro de meio de ciclo com crescimento extremo.
- FCF negativo: um FCFF normalizado positivo reduz, mas nao elimina, a penalidade
  de confianca do DCF.

## Dados e auditoria

Na analise ao vivo, o Yahoo fornece o historico anual disponivel. Para ampliar a
janela ate dez anos, defina `SEC_USER_AGENT` e o sistema tentara usar filings
anuais da SEC EDGAR. No backtest, cada ano usa somente filings disponiveis na
data-base.

O HTML, Markdown, JSON e CSV historico registram valores atuais e normalizados,
anos usados, confianca, posicao no ciclo, formulas e avisos. Se os dados forem
insuficientes, o modelo preserva os valores correntes em vez de aplicar um
ajuste silencioso.

## Limitacoes

- O Company Facts da SEC pode nao mapear extensoes XBRL especificas da empresa.
- Capital de giro ausente usa aproximacao explicita e reduz a confianca em ate
  18 pontos percentuais, conforme a proporcao de anos afetados.
- Uma janela historica pode conter mudanca estrutural de mix ou aquisicoes;
  normalizar o passado nao garante que ele represente o futuro.
- A receita corrente ainda pode estar em um ponto extremo do ciclo. O uso de
  margens escaladas reduz o problema de tamanho, mas nao resolve volume/preco
  de commodity sem um modelo operacional setorial dedicado.
- Antes de recalibrar o score, os resultados devem ser validados em amostra
  ampla, por setor e fora da amostra.
