"""Protected entry point for portfolio experiments."""
from datetime import date, timedelta
from hashlib import sha256
from importlib.metadata import version
import json

from .portfolio_simulator import ExecutionRules, simulate


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
    validate_calendar(sessions, start, end)
    # Preflight readiness is necessary, but raw arguments are not yet hash-bound
    # to its evidence. Do not turn a diagnostic pass into benchmark authorization.
    raise ValueError("Entradas da carteira ainda exigem vinculo de hashes com as evidencias do preflight")

