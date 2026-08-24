"""Validate delisted-security price coverage before running the benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from fundamental_analysis.historical_price_readiness import (
    audit_historical_price_coverage,
    render_historical_price_readiness_markdown,
)
from fundamental_analysis.institutional_prices import TiingoHistoricalPriceClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate historical delisted-security price coverage."
    )
    parser.add_argument("--provider", choices=("tiingo",), default="tiingo")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.provider != "tiingo":
        raise SystemExit(f"Provedor nao suportado: {args.provider}")
    try:
        provider = TiingoHistoricalPriceClient()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    report = audit_historical_price_coverage(
        provider,
        provider_name="Tiingo EOD",
    )
    markdown = render_historical_price_readiness_markdown(report)
    print(markdown)
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    return 0 if report.is_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
