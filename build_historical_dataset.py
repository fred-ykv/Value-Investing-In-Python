"""Build the SEC EDGAR plus adjusted-price point-in-time calibration dataset."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from fundamental_analysis.benchmark_universe import DEFAULT_BENCHMARK_CASES
from fundamental_analysis.config import CALIBRATION, POINT_IN_TIME
from fundamental_analysis.historical_calibration import (
    evaluate_historical_outcomes,
    render_historical_calibration_markdown,
    write_historical_calibration_csv,
)
from fundamental_analysis.historical_prices import YFinanceHistoricalPriceClient
from fundamental_analysis.historical_macro import HistoricalMacroClient
from fundamental_analysis.point_in_time_collection import (
    collect_benchmark_history,
    render_collection_markdown,
    write_collection_manifest,
)
from fundamental_analysis.out_of_sample_validation import (
    evaluate_out_of_sample_validation,
    out_of_sample_payload,
    render_out_of_sample_markdown,
)
from fundamental_analysis.sec_edgar import SecEdgarClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build point-in-time score observations from SEC filings and adjusted prices."
    )
    parser.add_argument("tickers", nargs="*", help="Optional subset of benchmark tickers.")
    parser.add_argument("--start-year", type=int, default=POINT_IN_TIME.historical_start_year)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument(
        "--max-filings-per-company",
        type=int,
        default=POINT_IN_TIME.max_annual_filings_per_company,
    )
    parser.add_argument("--outdir", default="historical_calibration_outputs")
    parser.add_argument(
        "--validation-start-year",
        type=int,
        default=CALIBRATION.validation_start_year,
        help="First year reserved for the temporal holdout sample.",
    )
    parser.add_argument(
        "--sec-user-agent",
        default=None,
        help=f"SEC identity header. Prefer the {POINT_IN_TIME.sec_user_agent_env} environment variable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requested = {ticker.upper().strip() for ticker in args.tickers}
    cases = [
        case for case in DEFAULT_BENCHMARK_CASES if not requested or case.ticker in requested
    ]
    unknown = requested - {case.ticker for case in cases}
    if unknown:
        raise SystemExit("Tickers fora do benchmark configurado: " + ", ".join(sorted(unknown)))

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    sec_client = SecEdgarClient(user_agent=args.sec_user_agent)
    price_client = YFinanceHistoricalPriceClient()
    macro_client = HistoricalMacroClient()
    dataset = collect_benchmark_history(
        sec_client,
        price_client,
        macro_client,
        cases=cases,
        start_year=args.start_year,
        end_year=args.end_year,
        max_filings_per_company=args.max_filings_per_company,
    )
    write_historical_calibration_csv(
        dataset.observations,
        outdir / "historical_observations.csv",
    )
    write_collection_manifest(dataset, outdir / "collection_manifest.json")
    collection_markdown = render_collection_markdown(dataset)
    (outdir / "collection_report.md").write_text(collection_markdown, encoding="utf-8")
    historical_summary = evaluate_historical_outcomes(dataset.observations)
    calibration_markdown = render_historical_calibration_markdown(historical_summary)
    (outdir / "historical_calibration.md").write_text(calibration_markdown, encoding="utf-8")
    split_assumptions = replace(
        CALIBRATION,
        validation_start_year=args.validation_start_year,
    )
    out_of_sample = evaluate_out_of_sample_validation(
        dataset.observations,
        split_assumptions,
    )
    out_of_sample_markdown = render_out_of_sample_markdown(out_of_sample)
    (outdir / "out_of_sample_validation.md").write_text(
        out_of_sample_markdown,
        encoding="utf-8",
    )
    (outdir / "out_of_sample_validation.json").write_text(
        json.dumps(out_of_sample_payload(out_of_sample), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(collection_markdown)
    print()
    print(calibration_markdown)
    print()
    print(out_of_sample_markdown)
    return 0 if dataset.observations else 1


if __name__ == "__main__":
    raise SystemExit(main())
