# Pull Request Draft

## Summary

This refactor preserves the original notebooks and adds a modular fundamental
analysis toolkit for US stocks.

## Main changes

- Added `fundamental_analysis/` package with modules for data sources,
  statement normalization, metrics, valuation, scoring, sector rules,
  reporting, notebook adaptation, and calibration.
- Added CLI entry points:
  - `python main.py AAPL`
  - `python main.py AAPL --output AAPL_report.md`
  - `python calibrate.py`
- Added a notebook adapter so existing notebook globals can feed the modular report pipeline.
- Added `requirements.txt`, `.gitignore`, `CHANGELOG.md`, and tests.
- Added explainable Markdown reports in Portuguese.

## Validation

- Unit test suite passes locally.
- Live validation was run against:
  - `MLI` traditional industrial
  - `AAPL` big tech
  - `JPM` bank/financial
  - `RIVN` negative-FCF growth/EV
- Batch calibration was run against 12 mixed tickers.

## Files intentionally not committed

The following are generated/local artifacts and should remain ignored:

- `.vendor/`
- `work_outputs_live/`
- `calibration_outputs/`
- `__pycache__/`
- `*.pyc`

## Notes

The scoring model is intentionally conservative. Arbitrary financial
assumptions are centralized in `fundamental_analysis/config.py` so future
calibration is explicit and auditable.
