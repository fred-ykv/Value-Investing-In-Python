# Changelog

## Refactor foundation

- Added a modular Python package under `fundamental_analysis/`.
- Centralized arbitrary assumptions and score weights in `config.py`.
- Added lineage-aware metric objects with value, source, confidence, and notes.
- Added conservative data source helpers for Yahoo Finance and Finviz scraping.
- Added financial statement normalization and core derived metrics.
- Added valuation models for DCF/FCFF, Graham, EVA, bank RI/DDM, and Growth-Tech.
- Added multifactor scoring by valuation, growth, quality, debt, liquidity, and data confidence.
- Added report generation helpers for executive summary, valuation table, score table, risks, and recommendation.
- Added `requirements.txt`.

No original notebook was edited in this step.

## Notebook integration layer

- Added `fundamental_analysis/notebook_adapter.py` to convert legacy notebook globals into explicit modular inputs.
- Exposed `analyze_from_notebook_globals` from the package root.
- Added adapter tests that simulate common variables produced by the 2026 notebook.

Original notebooks remain unchanged.

## Live runner and Yahoo Finance mapping

- Added structured annual statement mapping in `YahooFinanceClient.fetch_financial_statements()`.
- Added `analyze_ticker_live()` to orchestrate a live Yahoo Finance analysis.
- Added root `main.py` CLI runner that prints or saves a Markdown report.
- Added Markdown report rendering with executive summary, valuation table, score dimensions, risks, and final recommendation.
- Added tests for Yahoo statement aliases and Markdown report sections.

## Live validation calibration

- Validated the CLI/pipeline with `MLI`, `AAPL`, `JPM`, and `RIVN`.
- Added CAPM fallback for cost of equity when `Ke`/`WACC` is not explicitly provided.
- Added market assumptions for risk-free rate, equity risk premium, and default beta in `config.py`.
- Improved sector classification for EV/auto manufacturers with negative FCF.
- Added regression tests for banks without explicit `Ke` and negative-FCF auto manufacturers.
- Generated live Markdown reports under `work_outputs_live/`.

## Batch score calibration

- Added `fundamental_analysis/calibration.py` for batch ticker diagnostics.
- Added root `calibrate.py` CLI to generate calibration CSV and Markdown summaries.
- Added tests for calibration rows, summaries, and Markdown output.
- Calibrated financial-sector valuation scoring to blend RI/DDM margin, P/B, and ROE.
- Added a regression test for financial valuation using P/B and ROE.
- Re-ran the 12-ticker calibration basket and saved updated CSV/Markdown outputs.

## Explainable reports

- Added a Portuguese narrative section to Markdown reports.
- Reports now include justification, strengths, attention points, valuation comments, risks, and final recommendation.
- Updated report tests to assert the explanatory sections are present.
- Avoided labeling high data confidence as a weak point in narrative output.
