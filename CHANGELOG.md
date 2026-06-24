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

## Live runner and report lineage

- Added structured annual statement mapping in `YahooFinanceClient.fetch_financial_statements()`.
- Added `analyze_ticker_live()` to orchestrate a live Yahoo Finance analysis.
- Added root `main.py` CLI runner that prints or saves a Markdown report.
- Added Markdown report rendering with executive summary, valuation table, score dimensions, metric lineage, risks, and final recommendation.
- Added report tests for required Markdown sections and metric source/confidence output.

## Valuation and scoring hardening

- Added CAPM fallback for cost of equity when `Ke`/`WACC` is not explicitly provided.
- Added market assumptions for risk-free rate, equity risk premium, and default beta in `config.py`.
- Improved sector classification for EV/auto manufacturers with negative FCF.
- Added regression tests for traditional industrial, big tech, bank/financial, and negative-FCF company profiles.
- Fixed zero-valued assumptions, such as 0% growth, so they are not replaced by default assumptions.
- Added regression tests for 0% DCF growth, 0% terminal growth in DDM, and 0% Growth-Tech revenue growth.
- Added configurable valuation score curve so moderately negative margins of safety are not scored as near zero.
- Reduced valuation weight for traditional, growth/tech, and financial profiles while keeping valuation as a buy gate.
- Added bank valuation calibration using ROE-adjusted justified P/B in addition to RI/DDM, raw P/B, and ROE.
- Added recommendation gates so weak valuation prevents a Buy rating and weak valuation plus weak quality remains Avoid.
- Added scoring calibration tests for moderate overvaluation, weak growth/tech quality, and bank P/B vs ROE logic.

## Batch score calibration scaffolding

- Added `fundamental_analysis/calibration.py` for batch ticker diagnostics.
- Added root `calibrate.py` CLI to generate calibration CSV and Markdown summaries.
- Calibrated financial-sector valuation scoring to blend RI/DDM margin, P/B, and ROE.
- Batch calibration is available as a CLI workflow, but live calibration outputs are intentionally not committed.

## Explainable reports

- Added a Portuguese narrative section to Markdown reports.
- Reports now include justification, valuation comments, score dimensions, metric source/confidence lineage, risks, and final recommendation.
- Updated report tests to assert the required explanatory and lineage sections are present.
- Avoided labeling high data confidence as a weak point in narrative output.
