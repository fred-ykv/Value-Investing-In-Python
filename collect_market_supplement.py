import argparse
import json

from fundamental_analysis.market_supplement import collect_market_supplement


def main():
    parser = argparse.ArgumentParser(description="Complementar volume e eventos sem alterar arquivos historicos")
    parser.add_argument("--input-archive", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = collect_market_supplement(args.input_archive, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["captured_volume_points"] == result["required_volume_points"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

