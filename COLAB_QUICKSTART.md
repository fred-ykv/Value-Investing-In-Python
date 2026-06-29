# Guia rapido para rodar no Google Colab

Este guia mostra o caminho mais simples para rodar o novo toolkit modular no
Google Colab, gerar a analise fundamentalista e baixar os relatorios finais.

## 1. Criar um notebook no Colab

Abra o Google Colab e crie um notebook novo.

Use as celulas abaixo na ordem.

## 2. Instalar o projeto e dependencias

```python
!git clone https://github.com/fred-ykv/Value-Investing-In-Python.git
%cd Value-Investing-In-Python
!pip install -r requirements.txt
```

## 3. Rodar uma acao com dados do Yahoo Finance

Execute a celula abaixo e digite o ticker quando o Colab perguntar.

```python
from fundamental_analysis import run_colab_analysis

LAST = {}
run = run_colab_analysis(default_ticker="MLI", state=LAST)
result = run["result"]
artifacts = run["artifacts"]
```

Se voce apertar Enter sem digitar nada, o fallback sera `MLI`. O ticker fica
salvo em `LAST["ticker"]` para reuso nas proximas celulas.

## 4. Ver o relatorio HTML no proprio Colab

```python
from IPython.display import HTML, display

display(HTML(result.report["html"]))
```

## 5. Salvar Markdown, HTML e JSON auditavel

O passo 3 ja salva os arquivos em `outputs`. Se quiser salvar novamente em outra
pasta, rode:

```python
from fundamental_analysis import save_report_artifacts

artifacts = save_report_artifacts(result.ticker, result.report, "outputs")
artifacts
```

O resultado tera tres arquivos:

* `*_analysis.md`: relatorio em Markdown.
* `*_analysis.html`: relatorio visual para abrir no navegador.
* `*_tables.json`: tabelas e diagnosticos em formato auditavel.

## 6. Baixar os arquivos gerados

```python
from google.colab import files

for path in artifacts.values():
    files.download(path)
```

## 7. Rodar com dados manuais ou vindos de notebook

Se voce ja tem demonstrativos no notebook, use a funcao de inputs manuais:

```python
from fundamental_analysis import analyze_ticker_from_inputs

result = analyze_ticker_from_inputs(
    "EXEMPLO",
    income_statement={
        "revenue": 1_000_000,
        "ebit": 200_000,
        "net_income": 120_000,
    },
    balance_sheet={
        "total_assets": 1_500_000,
        "total_liabilities": 600_000,
        "equity": 900_000,
        "cash": 100_000,
        "total_debt": 250_000,
        "current_assets": 500_000,
        "current_liabilities": 250_000,
    },
    cash_flow={
        "cfo": 150_000,
        "capex": -40_000,
    },
    market_data={
        "shares": 10_000,
        "price": 60,
        "wacc": 0.10,
        "growth_years": 0.04,
        "terminal_growth": 0.02,
    },
    info={
        "sector": "Industrials",
    },
)

display(HTML(result.report["html"]))
```

## Observacoes importantes

* A analise live depende de Yahoo Finance e de acesso a internet no Colab.
* O resultado nao e recomendacao de investimento; e uma ferramenta de apoio
  para organizar premissas, valuation, scoring e riscos.
* Quando faltar dado, revise a tabela de fontes e confianca antes de tomar uma
  decisao.
