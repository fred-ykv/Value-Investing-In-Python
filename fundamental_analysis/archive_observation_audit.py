"""Reconstruct input availability for saved observations, without scoring."""
from datetime import date, timedelta
import json

from .config import POINT_IN_TIME
from .historical_archive import ArchiveReader, ReplaySecClient, ReplayMacroClient, ReplayPriceClient
from .historical_prices import add_months


def audit_observations(path):
    archive = ArchiveReader(path)
    saved = json.loads(archive.load("expected_output", "collection_manifest.json"))
    sec, macro, prices = ReplaySecClient(archive), ReplayMacroClient(archive), ReplayPriceClient(archive)
    cases = {c["ticker"]: c for c in archive.manifest["run"]["cases"]}
    rows = []
    for record in saved["results"]:
        observation = record.get("observation")
        row = {"ticker": record["ticker"], "as_of": record.get("as_of"), "checks": {}, "issues": []}
        rows.append(row)
        if not observation:
            row["issues"].append("observacao ausente no resultado arquivado")
            continue
        ticker = observation["ticker"]
        as_of = date.fromisoformat(observation["as_of"])
        row["as_of"] = as_of.isoformat()
        case = cases[ticker]
        try:
            snapshot = sec.build_snapshot(ticker, as_of,
                anchor_accession=observation["filing_accession"], cik_override=case.get("cik") or None)
            row["checks"]["sec"] = snapshot.audit.point_in_time_valid
        except (ValueError, KeyError, LookupError) as exc:
            row["checks"]["sec"] = False
            row["issues"].append(f"SEC: {exc}")
        try:
            row["checks"]["macro"] = macro.snapshot(as_of).point_in_time_valid
        except (ValueError, KeyError, LookupError) as exc:
            row["checks"]["macro"] = False
            row["issues"].append(f"Macro: {exc}")
        start = add_months(as_of, -POINT_IN_TIME.beta_lookback_months) - timedelta(days=10)
        end = add_months(as_of, POINT_IN_TIME.forward_horizon_months) + timedelta(days=POINT_IN_TIME.price_end_max_lag_days + 2)
        for label, symbol in (("stock_window", ticker), ("benchmark_window", POINT_IN_TIME.benchmark_for_group(case["benchmark_group"]))):
            try:
                series = prices.fetch_series(symbol, start, end)
                row["checks"][label] = bool(series.points) and series.ticker == symbol
            except (ValueError, KeyError, LookupError) as exc:
                row["checks"][label] = False
                row["issues"].append(f"{label}: {exc}")
    return {"archive_sha256": archive.digest, "observations": len(rows),
            "inputs_available": sum(len(r["checks"]) == 4 and all(r["checks"].values()) for r in rows),
            "rows": rows, "benchmark_authorized": False,
            "limitation": "Verifica reconstrucao SEC/macro e presenca das janelas de 12 meses; nao certifica cobertura diaria, eventos terminais, custos ou demais horizontes."}

