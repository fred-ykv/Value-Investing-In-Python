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
- Calibrated valuation scoring so moderate overvaluation is not treated as near-zero value while Buy recommendations still require adequate valuation.
- Fixed short-keyword sector classification so EV/AI acronyms do not match unrelated words such as beverages or defensive.

## Validation

- Unit test suite passes locally: `python -m unittest discover -s tests -v`.
- Current local result: 16 tests passing.
- Current suite covers:
  - traditional industrial company profile
  - big tech company profile
  - bank/financial company profile
  - negative-FCF company profile
  - DCF sensitivity and negative-FCFF handling
  - 0% growth assumptions that must not be replaced by defaults
  - scoring calibration for valuation curve, bank P/B vs ROE, and avoid gates
  - sector classification for consumer defensive and standalone EV acronyms
  - notebook adapter behavior
  - Markdown report sections and metric lineage output
- 30-ticker benchmark completed locally with 30 successes and 0 errors.
- Live Yahoo Finance runs and batch calibration require network access and dependencies from
  `requirements.txt`; generated live outputs are intentionally not committed.

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
