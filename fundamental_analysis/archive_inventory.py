"""Inspect archived inputs without executing bundled code or scoring."""
from collections import Counter
from datetime import date
import json
import math

from .historical_archive import ArchiveReader


def inspect_archive(path):
    reader = ArchiveReader(path)
    kinds = Counter()
    windows = []
    issues = []
    for entry in reader.manifest["entries"]:
        kind, key = entry["kind"], entry["key"]
        kinds[kind] += 1
        payload = reader.load(kind, key)
        if kind != "price_series":
            continue
        try:
            ticker, start, end = json.loads(key)
            start, end = date.fromisoformat(start), date.fromisoformat(end)
            if payload["ticker"] != ticker or start > end:
                raise ValueError("identidade ou intervalo divergente")
            days = [date.fromisoformat(p["day"]) for p in payload["points"]]
            if not days or days != sorted(set(days)) or days[0] < start or days[-1] > end:
                raise ValueError("datas ausentes, duplicadas ou fora da janela")
            for point in payload["points"]:
                for field in ("raw_close", "adjusted_close"):
                    value = point[field]
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                        raise ValueError("preco invalido")
            windows.append({"ticker": ticker, "requested_start": start.isoformat(),
                            "requested_end": end.isoformat(), "first": days[0].isoformat(),
                            "last": days[-1].isoformat(), "points": len(days),
                            "issuer_cik": payload.get("issuer_cik", ""), "source": payload.get("source", "")})
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(f"Janela {key}: {exc}")
    run = reader.manifest.get("run", {})
    cases = run.get("cases", [])
    return {"manifest_sha256": reader.digest, "integrity_verified": True,
            "input_counts": dict(kinds), "run": run,
            "tickers": sorted({case["ticker"] for case in cases}),
            "groups": dict(Counter(case["benchmark_group"] for case in cases)),
            "price_windows": windows, "issues": issues,
            "benchmark_authorized": False,
            "limitation": "Inventario e integridade nao certificam cobertura temporal nem elegibilidade financeira."}

