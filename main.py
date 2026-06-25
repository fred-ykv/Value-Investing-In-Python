"""Command-line runner for the modular fundamental analysis toolkit."""

from __future__ import annotations

import argparse
from pathlib import Path

from fundamental_analysis.main import analyze_ticker_live


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a US stock ticker.")
    parser.add_argument("ticker", help="Ticker symbol, e.g. MLI, AAPL, JPM")
    parser.add_argument(
        "--output",
        help="Optional Markdown output path. If omitted, prints to the terminal.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = analyze_ticker_live(args.ticker)
    markdown = str(result.report["markdown"])
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
