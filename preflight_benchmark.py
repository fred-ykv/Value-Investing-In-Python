from __future__ import annotations

import argparse
import json
from pathlib import Path

from fundamental_analysis.benchmark_preflight import build_preflight, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Validar cobertura antes do benchmark historico")
    parser.add_argument("--lifecycle-evidence")
    parser.add_argument("--historical-observations")
    parser.add_argument("--output", default="benchmark_preflight")
    args = parser.parse_args()
    result = build_preflight(lifecycle_evidence=args.lifecycle_evidence, historical_observations=args.historical_observations)
    out = Path(args.output)
    out.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "expected_companies", "observed_companies", "eligible_companies", "blocking_reasons")}, ensure_ascii=False))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())

