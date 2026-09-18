"""Run input diagnostics in an isolated, network-blocked process."""
import argparse
import json
from pathlib import Path
import sys

from replay_historical_dataset import OfflineGuard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    guard = OfflineGuard()
    sys.addaudithook(guard)
    from fundamental_analysis.archive_observation_audit import audit_observations
    results = [audit_observations(path) for path in args.archives]
    report = {"archives": results, "network_attempts": guard.attempts, "benchmark_authorized": False}
    with Path(args.output).open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    for result in results:
        print(f"Entradas disponiveis: {result['inputs_available']}/{result['observations']}")
    return 2 if guard.attempts or any(r["inputs_available"] != r["observations"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

