import argparse
import json
from fundamental_analysis.dividend_evidence import collect_dividend_evidence


def main():
    parser = argparse.ArgumentParser(description="Coletar evidencia de datas de dividendos via Tiingo")
    parser.add_argument("--source-archive", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = collect_dividend_evidence(args.source_archive, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    return 0 if not report["errors"] and report["dates_matched"] == report["expected_dividends"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

