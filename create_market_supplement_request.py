import argparse
import json

from fundamental_analysis.market_supplement import create_market_supplement_request


def main():
    parser = argparse.ArgumentParser(description="Criar requisicao compacta para coleta de volume no Colab")
    parser.add_argument("--input-archive", action="append", required=True)
    parser.add_argument("--output", default="market_supplement_request.json")
    args = parser.parse_args()
    print(json.dumps(create_market_supplement_request(args.input_archive, args.output), indent=2))


if __name__ == "__main__":
    main()

