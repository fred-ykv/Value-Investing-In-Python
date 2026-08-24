# Changelog

## Survivorship-aware historical universe

- Added ten historical lifecycle cases covering cash acquisitions and an
  equity cancellation, each linked to stable SEC CIK and official event data.
- Added normalized CSV and composite historical-price clients for licensed or
  institutional delisted-security histories with permanent identity checks.
- Added terminal-return handling for cash consideration, benchmark reinvestment
  to the original horizon, cancellation at zero, and lifecycle drawdown.
- Persisted lifecycle status, event, terminal value, source, price end date,
  and outcome method in calibration observations and reports.
- Added readiness gates requiring delisted and adverse lifecycle coverage
  before score recalibration can be considered.
- Expanded SEC XBRL concept fallbacks and allowed explicit CIK overrides for
  issuers absent from the current SEC ticker map.
- Validated 46 of 50 critical annual SEC snapshots in a ten-company pilot;
  score weights and recommendation thresholds remain unchanged pending audited
  delisted-price histories.

## Temporal out-of-sample validation

- Added a fixed temporal split between calibration and a 2022+ holdout sample.
- Added an embargo for calibration observations whose forward outcomes overlap the holdout.
- Persisted benchmark group and sector bucket in every historical observation.
- Added minimum observation and distinct-ticker coverage controls per group and split.
- Added segmented excess return, hit rate, drawdown, and Spearman diagnostics by group and recommendation.
- Added Markdown and JSON out-of-sample artifacts to the historical dataset runner.
- Increased the default annual filing window to ten years while preserving point-in-time cutoffs.
- Kept score weights, gates, and recommendation thresholds unchanged.
- Added profile-specific critical-input validation with configurable confidence floors.
- Expanded audited SEC XBRL fallbacks for debt, finance leases, notes payable, diluted shares, and net interest used by the EBIT proxy.
- Added an explicit low-confidence zero-financial-debt approximation only when the anchor filing has no positive financing evidence.
- Kept operating leases outside financial debt until EBIT and FCFF can be adjusted symmetrically, while disclosing the limitation in metric lineage.
- Updated the Bank of New York Mellon benchmark ticker from `BK` to the SEC-listed `BNY`.
- Completed a 345-observation, 40-company temporal benchmark; the score failed the economic validation gates, so no weights or thresholds were changed.

## Cyclical normalization

- Added explicit cyclical classification with curated benchmark overrides and conservative sector keywords.
- Added five-to-ten-year normalization of operating margin, net margin, tax rate, FCFF margin, and reinvestment margin using bounded winsorized averages.
- Applied normalized ratios to current revenue instead of averaging nominal historical dollars.
- Added a component FCFF calculation (`normalized NOPAT - normalized reinvestment`) with a direct FCFF-margin reconciliation control.
- Added gradual three-year DCF transition from current to normalized FCFF, normalized EPS for Graham, and normalized ROIC for EVA.
- Preserved current values whenever history or confidence is insufficient and surfaced the reason in HTML, Markdown, JSON, and historical CSV outputs.
- Added SEC EDGAR annual-history enrichment for live and point-in-time analyses without using future filings.
- Persisted cyclical status, sample length, confidence, cycle position, current/normalized FCFF, and normalized margins in calibration observations.
- Kept score weights and recommendation thresholds unchanged pending a broader out-of-sample benchmark.

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
- Added cash burn and cash runway metrics for growth/tech and negative-FCF companies.
- Updated growth/tech liquidity scoring to blend current ratio with cash runway, reducing false comfort from high current ratios during cash burn.
- Added runway diagnostics and explanatory report notes when estimated runway is below the configured minimum.
- Added tests for growth/tech runway scoring and short-runway report explanations.
- Fixed sector classification for short keywords such as EV/AI so consumer defensive names like beverages are not misclassified as growth/tech.
- Added sector-rule tests for consumer defensive beverages and standalone EV acronyms.
- Ran a 30-ticker benchmark across industrials, big tech, banks, value/defensive names, and growth/negative-FCF companies.

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
- Replaced the short justification with a thesis-style recommendation narrative.
- Added explicit notes when valuation gates block a Buy rating or when weak valuation and weak quality keep a stock at Avoid.
- Added explanatory report notes for recommendation labels, margin of safety, data confidence, and negative-FCFF DCF cases.

## Professional calibration protocol

- Added a balanced 40-ticker benchmark universe across traditional/cyclical, growth/tech, financial, and negative-FCF/early-growth calibration groups.
- Added cross-sectional diagnostics for score quartiles, dispersion, recommendation concentration, valuation gates, data confidence, and collection errors.
- Added explicit minimum-sample and calibration-readiness controls in `config.py`.
- Added point-in-time historical evaluation for forward return, benchmark-relative return, maximum drawdown, Spearman correlation, and score-bucket monotonicity.
- Added CSV, JSON, and Markdown calibration artifacts plus a documented anti-look-ahead protocol.
- Preserved all current score weights and recommendation thresholds until empirical benchmark evidence is available.

## Point-in-time historical collector

- Added an SEC EDGAR Company Facts adapter anchored to original annual filing accession numbers and publication dates.
- Added explicit filing lag, source lineage, metric coverage, caching, and SEC fair-access controls.
- Added raw historical close for valuation plus adjusted-price outcomes, benchmark-relative returns, maximum drawdown, and trailing beta using only prior prices.
- Added a benchmark history runner that skips incomplete forward windows and exports CSV, JSON, and Markdown audit artifacts.
- Disabled current Yahoo peer enrichment and current sector-benchmark fallbacks during historical score reconstruction.
- Extended historical observations with benchmark, price-window, filing-accession, and fundamental-coverage fields.
- Documented remaining limitations, including annual-only statements and constant macro assumptions.
- Preserved score weights and recommendation thresholds pending a sufficiently covered point-in-time sample.
- Expanded SEC concept coverage for interest expense and productive-asset CAPEX after the MLI/NUE live pilot.
- Added a lower-confidence, explicitly flagged EBIT proxy from pretax income plus interest expense when reported EBIT is unavailable.
- Fixed fundamental coverage so derived supplemental metrics cannot push the ratio above 100%.
- Restored as-traded historical closes from Yahoo split events before combining prices with SEC share counts.
- Documented the six-observation MLI/NUE pilot and the unresolved cyclical false-positive risk without changing score calibration.
- Added point-in-time U.S. Treasury 10-year rates and historical Damodaran implied ERP to historical score reconstruction.
- Added strict availability dates, staleness controls, source lineage, caching, and rejection of unavailable macro observations without a current-data fallback.
- Persisted risk-free rate, ERP, Ke, WACC or applied discount rate, cost-of-capital method, confidence, and fallback status in historical calibration CSVs.
- Re-ran the MLI/NUE pilot with 6/6 valid macro observations and documented recommendation sensitivity without changing score weights or thresholds.
