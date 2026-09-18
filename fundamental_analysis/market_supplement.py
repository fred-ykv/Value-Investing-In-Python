"""Create immutable volume and corporate-action supplements without rewriting archives."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
from pathlib import Path

from .historical_archive import ArchiveReader, canonical_json, code_fingerprints, sha256, _price_key
from .historical_prices import PriceSeries, normalize_price_series, yfinance_corporate_action_evidence, yfinance_price_points


class YFinanceSupplementProvider:
    def fetch(self, ticker: str, start: date, end: date):
        import yfinance as yf  # type: ignore
        frame = yf.Ticker(ticker).history(period="max", auto_adjust=False, actions=True)
        if frame is None or getattr(frame, "empty", True):
            raise LookupError(f"serie Yahoo vazia: {ticker}")
        series = normalize_price_series(PriceSeries(ticker, tuple(yfinance_price_points(frame)), "yfinance_supplement"))
        return series.between(start, end), yfinance_corporate_action_evidence(frame, ticker)


def _write_archive(output, entries, run):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "objects").mkdir()
    manifest_entries = []
    for kind, key, payload in entries:
        raw = canonical_json(payload, sort_keys=False)
        digest = sha256(raw)
        (output / "objects" / f"{digest}.json").write_bytes(raw)
        manifest_entries.append({"kind": kind, "key": key, "sha256": digest,
                                 "captured_at_utc": datetime.now(timezone.utc).isoformat()})
    manifest = {"schema_version": 1, "state": "complete",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "python": "market-supplement", "code_sha256": code_fingerprints(),
                "run": run, "entries": manifest_entries,
                "limitations": ["Yahoo Finance nao certifica identidade permanente nem data de pagamento de dividendos."]}
    raw = canonical_json(manifest)
    (output / "manifest.json").write_bytes(raw)
    (output / "manifest.sha256").write_text(sha256(raw) + "\n", encoding="ascii")


def collect_market_supplement(base_archives, output, provider=None, tolerance=0.005):
    provider = provider or YFinanceSupplementProvider()
    required = {}
    source_hashes = []
    for path in base_archives:
        reader = ArchiveReader(path)
        source_hashes.append(reader.digest)
        for entry in reader.manifest["entries"]:
            if entry["kind"] != "price_series":
                continue
            payload = reader.load(entry["kind"], entry["key"])
            ticker = payload["ticker"].upper()
            for point in payload["points"]:
                if point.get("volume") is None:
                    required[(ticker, point["day"])] = point
    by_ticker = {}
    for ticker, day in required:
        by_ticker.setdefault(ticker, []).append(date.fromisoformat(day))
    entries, issues, unresolved, captured = [], [], [], 0
    all_events = []
    for ticker, days in sorted(by_ticker.items()):
        try:
            series, actions = provider.fetch(ticker, min(days), max(days))
            points = {point.day: point for point in series.points}
            accepted = []
            for day in sorted(days):
                point, original = points.get(day), required[(ticker, day.isoformat())]
                if point is None or point.volume is None or not math.isfinite(point.volume) or point.volume < 0:
                    raise ValueError(f"volume ausente em {day}")
                for field, observed in (("raw_close", point.valuation_close), ("adjusted_close", point.adjusted_close)):
                    expected = float(original[field])
                    if abs(observed - expected) / expected > tolerance:
                        raise ValueError(f"{field} diverge em {day}")
                accepted.append({"day": day.isoformat(), "adjusted_close": point.adjusted_close,
                                 "raw_close": point.valuation_close, "volume": point.volume})
            payload = {"ticker": ticker, "points": accepted, "source": "yfinance_supplement_reconciled",
                       "security_id": "", "issuer_cik": "", "input_evidence_sha256": ""}
            entries.append(("price_series", _price_key(ticker, min(days), max(days)), payload))
            captured += len(accepted)
            all_events.extend(actions["events"])
            unresolved.extend(actions["unresolved_dividends"])
        except (LookupError, ValueError, TypeError) as exc:
            issues.append(f"{ticker}: {exc}")
    if by_ticker and not issues and not unresolved:
        start = min(day for days in by_ticker.values() for day in days)
        end = max(day for days in by_ticker.values() for day in days)
        entries.append(("corporate_events", "XNYS", {"start": start.isoformat(), "end": end.isoformat(),
                                                       "events": all_events, "source": "yfinance_actions"}))
    report = {"status": "complete_with_pending_events" if not issues else "partial",
              "source_archive_sha256": sorted(source_hashes), "required_volume_points": len(required),
              "captured_volume_points": captured, "issues": issues,
              "unresolved_dividends": unresolved, "corporate_event_coverage_written": bool(by_ticker and not issues and not unresolved)}
    entries.append(("market_evidence_report", "report", report))
    _write_archive(output, entries, report)
    return report

