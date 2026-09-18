"""Prepare hash-bound portfolio inputs exclusively from verified archives."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path

from .historical_archive import ArchiveReader, canonical_json


INPUT_KEYS = ("sessions", "signals", "bars", "events", "rules")
DEFAULT_RULES = {
    "initial_cash": 100000.0, "cost_bps": 10.0, "target_weight": 0.05,
    "sector_limit": 0.25, "max_positions": 20, "volume_participation": 0.10,
}


def _canonical_for_runner(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        entries = [[_canonical_for_runner(key), _canonical_for_runner(item)] for key, item in value.items()]
        return {"__mapping__": sorted(entries, key=lambda pair: json.dumps(pair[0], sort_keys=True))}
    if isinstance(value, (list, tuple)):
        return [_canonical_for_runner(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"Tipo nao serializavel no pacote: {type(value).__name__}")


def _hash_inputs(inputs):
    return {
        key: sha256(json.dumps(_canonical_for_runner(inputs[key]), sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
        for key in INPUT_KEYS
    }


def _exchange_sessions(start, end):
    try:
        import exchange_calendars as calendars
    except ImportError as exc:
        raise ValueError("exchange_calendars ausente; instale requirements-backtest.txt") from exc
    if not hasattr(calendars, "get_calendar"):
        raise ValueError("exchange_calendars incompleto; reinstale requirements-backtest.txt")
    calendar = calendars.get_calendar("XNYS", start=(start - timedelta(days=7)).isoformat(),
                                      end=(end + timedelta(days=7)).isoformat())
    return tuple(stamp.date() for stamp in calendar.sessions_in_range(start.isoformat(), end.isoformat()))


def _load_archives(paths):
    readers = [ArchiveReader(path) for path in paths]
    observations, prices, events, event_coverage, conflicts = [], {}, [], [], []
    for reader in readers:
        for entry in reader.manifest["entries"]:
            kind, key = entry["kind"], entry["key"]
            if kind == "expected_output" and key == "collection_manifest.json":
                saved = json.loads(reader.load(kind, key))
                observations.extend(record["observation"] for record in saved.get("results", []) if record.get("observation"))
            elif kind == "price_series":
                payload = reader.load(kind, key)
                ticker = payload["ticker"].upper()
                for point in payload["points"]:
                    identity = (ticker, point["day"])
                    normalized = {field: point.get(field) for field in ("raw_close", "adjusted_close", "volume")}
                    if identity in prices and prices[identity] != normalized:
                        conflicts.append(f"preco conflitante: {ticker} {point['day']}")
                    prices[identity] = normalized
            elif kind == "corporate_events":
                payload = reader.load(kind, key)
                event_coverage.append((date.fromisoformat(payload["start"]), date.fromisoformat(payload["end"])))
                events.extend(payload.get("events", []))
    return readers, observations, prices, events, event_coverage, sorted(set(conflicts))


def prepare_portfolio_package(archive_paths, output_directory, *, sessions=None,
                              experiment_id="historical_backtest_v1", manifest_version="1.1",
                              minimum_signals_per_ticker=2, rules=None):
    """Write a package only when verified inputs satisfy execution requirements."""
    readers, observations, prices, archived_events, event_coverage, issues = _load_archives(archive_paths)
    output = Path(output_directory)
    if output.exists():
        raise ValueError("diretorio de saida ja existe")
    by_ticker = defaultdict(list)
    for item in observations:
        ticker = str(item.get("ticker", "")).upper()
        if ticker:
            by_ticker[ticker].append(item)
    if not observations:
        issues.append("nenhum sinal point-in-time arquivado")
    for ticker, items in sorted(by_ticker.items()):
        valid = [item for item in items if item.get("point_in_time_validated") is True
                 and item.get("analysis_input_validated") is True]
        if len(valid) < minimum_signals_per_ticker:
            issues.append(f"historico longitudinal insuficiente: {ticker} {len(valid)}/{minimum_signals_per_ticker}")
    missing_volume = sorted({ticker for (ticker, _), point in prices.items()
                             if point.get("volume") is None})
    if missing_volume:
        issues.append("volume ausente: " + ", ".join(missing_volume))
    if not prices:
        issues.append("nenhuma barra de preco arquivada")
    dates = sorted({date.fromisoformat(day) for _, day in prices})
    if dates and not any(start <= dates[0] and end >= dates[-1] for start, end in event_coverage):
        issues.append("cobertura auditada de eventos corporativos ausente ou incompleta")
    if sessions is None and dates:
        try:
            sessions = _exchange_sessions(dates[0], dates[-1])
        except ValueError as exc:
            issues.append(str(exc))
            sessions = ()
    sessions = tuple(sessions or ())
    if not sessions:
        issues.append("calendario XNYS vazio")
    elif sessions != tuple(sorted(set(sessions))):
        issues.append("calendario XNYS duplicado ou fora de ordem")

    report = {
        "status": "blocked" if issues else "ready", "issues": sorted(set(issues)),
        "source_archive_sha256": sorted(reader.digest for reader in readers),
        "observations": len(observations), "tickers_with_signals": len(by_ticker),
        "price_points": len(prices), "sessions": len(sessions),
        "package_written": False,
    }
    output.mkdir(parents=True)
    (output / "preparation_report.json").write_bytes(canonical_json(report))
    if issues:
        return report

    latest = {}
    signal_map = defaultdict(list)
    ordered_observations = sorted(observations, key=lambda item: (item["as_of"], item["ticker"]))
    observation_index = 0
    for index, day in enumerate(sessions):
        while observation_index < len(ordered_observations) and date.fromisoformat(ordered_observations[observation_index]["as_of"]) <= day:
            item = ordered_observations[observation_index]
            latest[item["ticker"].upper()] = item
            observation_index += 1
        is_month_end = index + 1 < len(sessions) and (day.year, day.month) != (sessions[index + 1].year, sessions[index + 1].month)
        if is_month_end:
            for ticker, item in sorted(latest.items()):
                signal_map[day].append({"ticker": ticker, "sector": item["sector_bucket"],
                                        "score": float(item["total_score"]), "available_on": item["as_of"],
                                        "eligible": True})
    bars = {(date.fromisoformat(day), ticker): {"close": float(point["raw_close"]), "volume": int(point["volume"])}
            for (ticker, day), point in prices.items() if date.fromisoformat(day) in set(sessions)}
    events = defaultdict(list)
    for item in archived_events:
        events[date.fromisoformat(item["day"])].append({
            "ticker": item["ticker"].upper(), "kind": item["kind"], "value": float(item["value"]),
            "payment_date": item.get("payment_date"),
        })
    inputs = {"sessions": sessions, "signals": dict(signal_map), "bars": bars,
              "events": dict(events), "rules": dict(rules or DEFAULT_RULES)}
    hashes = _hash_inputs(inputs)
    calendar_hash = sha256(json.dumps([day.isoformat() for day in sessions]).encode("ascii")).hexdigest()
    serializable = {
        "schema_version": 1,
        "sessions": [day.isoformat() for day in sessions],
        "signals": [{"day": day.isoformat(), "items": items} for day, items in signal_map.items()],
        "bars": [{"day": day.isoformat(), "ticker": ticker, **bar} for (day, ticker), bar in bars.items()],
        "events": [{"day": day.isoformat(), "items": items} for day, items in events.items()],
        "rules": inputs["rules"],
    }
    (output / "portfolio_inputs.json").write_bytes(canonical_json(serializable))
    attestation = {
        "schema_version": 1, "experiment_id": experiment_id, "manifest_version": manifest_version,
        "source_archive_sha256": report["source_archive_sha256"],
        "portfolio_input_hashes": hashes, "calendar_sessions_sha256": calendar_hash,
    }
    raw = canonical_json(attestation)
    (output / "portfolio_attestation.json").write_bytes(raw)
    (output / "portfolio_attestation.sha256").write_text(sha256(raw).hexdigest(), encoding="ascii")
    report.update({"status": "ready", "package_written": True,
                   "portfolio_input_hashes": hashes, "calendar_sessions_sha256": calendar_hash})
    (output / "preparation_report.json").write_bytes(canonical_json(report))
    return report

