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
        actions = yfinance_corporate_action_evidence(frame, ticker)
        actions["events"] = [item for item in actions["events"]
                             if start <= date.fromisoformat(item["day"]) <= end]
        actions["unresolved_dividends"] = [item for item in actions["unresolved_dividends"]
                                           if start <= date.fromisoformat(item["ex_date"]) <= end]
        return series.between(start, end), actions


def create_market_supplement_request(base_archives, output):
    """Export only the immutable price identities needed by an online collector."""
    required, source_hashes = {}, []
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
                    required[(ticker, point["day"])] = {
                        "ticker": ticker, "day": point["day"],
                        "raw_close": point["raw_close"], "adjusted_close": point["adjusted_close"],
                    }
    payload = {"schema_version": 1, "source_archive_sha256": sorted(source_hashes),
               "required_points": [required[key] for key in sorted(required)]}
    raw = canonical_json(payload)
    path = Path(output)
    path.write_bytes(raw)
    path.with_suffix(".sha256").write_text(sha256(raw), encoding="ascii")
    return {"request_sha256": sha256(raw), "required_volume_points": len(required),
            "source_archive_sha256": payload["source_archive_sha256"]}


def _load_request(path):
    path = Path(path)
    raw = path.read_bytes()
    if path.with_suffix(".sha256").read_text(encoding="ascii").strip() != sha256(raw):
        raise ValueError("integridade da requisicao de mercado reprovada")
    payload = json.loads(raw)
    if payload.get("schema_version") != 1 or not isinstance(payload.get("required_points"), list):
        raise ValueError("requisicao de mercado invalida")
    required = {}
    for point in payload["required_points"]:
        key = (point["ticker"].upper(), point["day"])
        if key in required:
            raise ValueError("ponto duplicado na requisicao de mercado")
        required[key] = point
    return required, payload["source_archive_sha256"], sha256(raw)


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


def collect_market_supplement(base_archives, output, provider=None, tolerance=0.005, request_path=None):
    provider = provider or YFinanceSupplementProvider()
    if request_path:
        required, source_hashes, request_digest = _load_request(request_path)
    else:
        required, source_hashes, request_digest = {}, [], ""
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
    entries, issues, warnings, unresolved, captured = [], [], [], [], 0
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
                expected_raw = float(original["raw_close"])
                if abs(point.valuation_close - expected_raw) / expected_raw > tolerance:
                    raise ValueError(f"raw_close diverge em {day}")
                expected_adjusted = float(original["adjusted_close"])
                if abs(point.adjusted_close - expected_adjusted) / expected_adjusted > tolerance:
                    warnings.append(f"{ticker}: adjusted_close revisado em {day}")
                accepted.append({"day": day.isoformat(), "adjusted_close": expected_adjusted,
                                 "raw_close": expected_raw, "volume": point.volume,
                                 "provider_raw_close": point.valuation_close,
                                 "provider_adjusted_close": point.adjusted_close})
            payload = {"ticker": ticker, "points": accepted, "source": "yfinance_supplement_reconciled",
                       "security_id": "", "issuer_cik": "", "input_evidence_sha256": ""}
            entries.append(("price_series", _price_key(ticker, min(days), max(days)), payload))
            captured += len(accepted)
            all_events.extend(actions["events"])
            unresolved.extend(actions["unresolved_dividends"])
        except (LookupError, ValueError, TypeError, RuntimeError) as exc:
            issues.append(f"{ticker}: {exc}")
    if by_ticker and not issues and not unresolved:
        start = min(day for days in by_ticker.values() for day in days)
        end = max(day for days in by_ticker.values() for day in days)
        entries.append(("corporate_events", "XNYS", {"start": start.isoformat(), "end": end.isoformat(),
                                                       "events": all_events, "source": "yfinance_actions"}))
    report = {"status": "complete_with_pending_events" if not issues else "partial",
              "source_archive_sha256": sorted(source_hashes), "required_volume_points": len(required),
              "captured_volume_points": captured, "issues": issues, "warnings": warnings,
              "unresolved_dividends": unresolved, "corporate_event_coverage_written": bool(by_ticker and not issues and not unresolved)}
    if request_digest:
        report["request_sha256"] = request_digest
    entries.append(("market_evidence_report", "report", report))
    _write_archive(output, entries, report)
    return report

