"""Command-line batch calibration runner."""

from __future__ import annotations

import argparse
from pathlib import Path

from fundamental_analysis.calibration import (
    render_calibration_markdown,
    run_calibration,
    write_calibration_csv,
)


DEFAULT_TICKERS = [
    "MLI",
    "CAT",
    "DE",
    "AAPL",
    "MSFT",
    "NVDA",
    "JPM",
    "BAC",
    "WFC",
    "RIVN",
    "SNOW",
    "PLTR",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run score calibration for multiple tickers.")
    parser.add_argument("tickers", nargs="*", help="Optional ticker list. Defaults to a mixed calibration basket.")
    parser.add_argument("--outdir", default="calibration_outputs", help="Output directory for CSV/Markdown.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tickers = args.tickers or DEFAULT_TICKERS
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rows = run_calibration(tickers)
    write_calibration_csv(rows, outdir / "calibration_scores.csv")
    (outdir / "calibration_summary.md").write_text(render_calibration_markdown(rows), encoding="utf-8")
    print(render_calibration_markdown(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
