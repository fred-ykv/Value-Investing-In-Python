"""Protected entry point for portfolio experiments."""
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from hashlib import sha256
from importlib.metadata import version
import json

from .portfolio_simulator import ExecutionRules, simulate


INPUT_KEYS = ("sessions", "signals", "bars", "events", "rules")


def _canonical(value):
    if is_dataclass(value):
        return _canonical(asdict(value))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        entries = [[_canonical(key), _canonical(item)] for key, item in value.items()]
        return {"__mapping__": sorted(entries, key=lambda pair: json.dumps(pair[0], sort_keys=True))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"Tipo nao serializavel no atestado: {type(value).__name__}")


def input_hashes(sessions, signals, bars, events, rules):
    """Return deterministic hashes for every simulator input family."""
    values = {
        "sessions": tuple(sessions), "signals": signals, "bars": bars,
        "events": events or {}, "rules": rules,
    }
    result = {}
    for key in INPUT_KEYS:
        payload = json.dumps(_canonical(values[key]), sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("ascii")
        result[key] = sha256(payload).hexdigest()
    return result


def verify_input_binding(expected, actual):
    if not isinstance(expected, dict) or set(expected) != set(INPUT_KEYS):
        raise ValueError("Preflight nao forneceu atestado completo das entradas da carteira")
    invalid = [key for key in INPUT_KEYS if expected.get(key) != actual.get(key)]
    if invalid:
        raise ValueError("Entradas divergem das evidencias aprovadas: " + ", ".join(invalid))


def validate_calendar(sessions, start, end):
    if type(start) is not date or type(end) is not date or start >= end:
        raise ValueError("Intervalo do calendario invalido")
    try:
        import exchange_calendars as calendars
    except ImportError as exc:
        raise ValueError("Instale requirements-backtest.txt para validar o calendario") from exc
    calendar = calendars.get_calendar("XNYS", start=(start - timedelta(days=7)).isoformat(),
                                      end=(end + timedelta(days=7)).isoformat())
    expected = tuple(stamp.date() for stamp in calendar.sessions_in_range(start.isoformat(), end.isoformat()))
    if tuple(sessions) != expected:
        raise ValueError("Pregoes ausentes, extras ou fora de ordem frente ao calendario XNYS")
    payload = json.dumps([day.isoformat() for day in expected]).encode("ascii")
    return {"exchange": "XNYS", "provider": "exchange_calendars", "version": version("exchange-calendars"),
            "start": start.isoformat(), "end": end.isoformat(), "sessions_sha256": sha256(payload).hexdigest()}


def run_portfolio(sessions, signals, bars, *, start, end, lifecycle_evidence=None,
                  historical_observations=None, events=None, rules=ExecutionRules()):
    """Re-run the preflight, never accept a caller-provided ready boolean."""
    try:
        from .benchmark_preflight import build_preflight
    except ImportError as exc:
        raise ValueError("Preflight PR66 ainda nao integrado; execucao bloqueada") from exc
    result = build_preflight(lifecycle_evidence=lifecycle_evidence,
                             historical_observations=historical_observations)
    if result.get("status") != "ready" or result.get("blocking_reasons"):
        raise ValueError("Preflight bloqueou execucao: " + "; ".join(result.get("blocking_reasons", [])))
    sessions = tuple(sessions)
    calendar = validate_calendar(sessions, start, end)
    actual = input_hashes(sessions, signals, bars, events, rules)
    verify_input_binding(result.get("portfolio_input_hashes"), actual)
    if result.get("calendar_sessions_sha256") != calendar["sessions_sha256"]:
        raise ValueError("Calendario diverge do hash aprovado pelo preflight")
    output = simulate(sessions, signals, bars, events=events, rules=rules)
    output["input_attestation"] = {
        "portfolio_input_hashes": actual,
        "calendar": calendar,
        "preflight_experiment_id": result.get("experiment_id"),
        "preflight_manifest_version": result.get("manifest_version"),
    }
    return output

