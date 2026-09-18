from __future__ import annotations

import argparse
import json
from pathlib import Path

from fundamental_analysis.benchmark_preflight import build_preflight, render_markdown
from fundamental_analysis.archive_inventory import inspect_archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Validar cobertura antes do benchmark historico")
    parser.add_argument("--lifecycle-evidence")
    parser.add_argument("--historical-observations")
    parser.add_argument("--output", default="benchmark_preflight")
    parser.add_argument("--input-archive", action="append", default=[], help="Pasta de arquivo historico; pode repetir.")
    parser.add_argument("--portfolio-attestation", help="Atestado assinado das entradas preparadas para a carteira.")
    args = parser.parse_args()
    archives = []
    for path in args.input_archive:
        try:
            archives.append({"path": path, **inspect_archive(path)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            archives.append({"path": path, "integrity_verified": False, "error": str(exc)})
    verified = [item["manifest_sha256"] for item in archives if item.get("integrity_verified")]
    result = build_preflight(lifecycle_evidence=args.lifecycle_evidence,
                             historical_observations=args.historical_observations,
                             portfolio_attestation=args.portfolio_attestation,
                             verified_archive_sha256=verified)
    result["archives"] = archives
    for item in archives:
        if not item.get("integrity_verified"):
            result["status"] = "blocked"
            result["blocking_reasons"].append(f"arquivo historico rejeitado: {item['path']}")
    out = Path(args.output)
    out.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "expected_companies", "observed_companies", "eligible_companies", "blocking_reasons")}, ensure_ascii=False))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())

