from __future__ import annotations

import argparse
import json

from fundamental_analysis.portfolio_package import prepare_portfolio_package


def main():
    parser = argparse.ArgumentParser(description="Preparar entradas auditaveis da carteira historica")
    parser.add_argument("--input-archive", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = prepare_portfolio_package(args.input_archive, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())

