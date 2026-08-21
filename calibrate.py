"""Command-line batch calibration runner."""

from __future__ import annotations

import argparse
from pathlib import Path

from fundamental_analysis.calibration import (
    build_calibration_diagnostics,
    render_calibration_markdown,
    run_benchmark_calibration,
    run_calibration,
    write_calibration_csv,
    write_calibration_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run score calibration for multiple tickers.")
    parser.add_argument("tickers", nargs="*", help="Optional ticker list. Defaults to a mixed calibration basket.")
    parser.add_argument("--outdir", default="calibration_outputs", help="Output directory for CSV/Markdown/JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if args.tickers:
        rows = run_calibration(args.tickers)
        diagnostics = build_calibration_diagnostics(rows)
    else:
        diagnostics = run_benchmark_calibration()
        rows = diagnostics.rows
    write_calibration_csv(rows, outdir / "calibration_scores.csv")
    write_calibration_json(rows, outdir / "calibration_diagnostics.json")
    (outdir / "calibration_summary.md").write_text(render_calibration_markdown(rows), encoding="utf-8")
    print(render_calibration_markdown(rows))
    return 0 if diagnostics.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

