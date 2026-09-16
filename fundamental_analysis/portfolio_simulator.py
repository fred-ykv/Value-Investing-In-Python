"""Deterministic research simulator; consumes prepared point-in-time inputs."""
from dataclasses import dataclass
from datetime import date
from math import floor, isfinite


@dataclass(frozen=True)
class ExecutionRules:
    initial_cash: float = 100000.0
    cost_bps: float = 10.0
    target_weight: float = 0.05
    sector_limit: float = 0.25
    max_positions: int = 20
    volume_participation: float = 0.10


@dataclass(frozen=True)
class Signal:
    ticker: str
    sector: str
    score: float
    available_on: date
    eligible: bool = True


@dataclass(frozen=True)
class Bar:
    close: float
    volume: int


@dataclass(frozen=True)
class Event:
    ticker: str
    kind: str
    value: float


def simulate(sessions, signals, bars, events=None, rules=ExecutionRules()):
    """signals maps month-end dates to full eligible snapshots; bars use raw USD.

    sessions must be a complete, independently validated exchange calendar.
    Event dividends are cash on payment date; splits precede that day's close.
    Missing held-asset prices or liquidity abort rather than silently fill.
    """
    sessions = tuple(sessions)
    events = events or {}
    if not sessions or sessions != tuple(sorted(set(sessions))):
        raise ValueError("Calendario vazio, duplicado ou fora de ordem")
    if (not all(isfinite(x) for x in (rules.initial_cash, rules.cost_bps, rules.target_weight, rules.sector_limit, rules.volume_participation))
            or rules.initial_cash <= 0 or not 0 <= rules.cost_bps < 10000
            or not 0 < rules.target_weight <= rules.sector_limit <= 1
            or type(rules.max_positions) is not int or rules.max_positions <= 0
            or not 0 < rules.volume_participation <= 1):
        raise ValueError("Regras de execucao invalidas")
    month_ends = {a for a, b in zip(sessions, sessions[1:]) if (a.year, a.month) != (b.year, b.month)}
    if set(signals) - month_ends or set(events) - set(sessions):
        raise ValueError("Sinais devem ocorrer no fim de mes com pregao seguinte; eventos exigem sessao")
    cash, holdings, sectors = rules.initial_cash, {}, {}
    ledger, curve = [], []
    pending = None
    fee = rules.cost_bps / 10000
    def bar(day, ticker):
        item = bars.get((day, ticker))
        if item is None or not isfinite(item.close) or item.close <= 0 or type(item.volume) is not int or item.volume < 0:
            raise ValueError(f"Preco/volume invalido: {ticker} {day}")
        return item
    for day in sessions:
        terminated = set()
        for event in events.get(day, ()):
            if not isfinite(event.value) or event.value < 0 or event.kind not in {"split", "dividend", "cash_acquisition", "cancelled_zero"}:
                raise ValueError("Evento corporativo invalido")
            qty = holdings.get(event.ticker, 0)
            if event.kind == "split":
                new_qty = qty * event.value
                if event.value <= 0 or not float(new_qty).is_integer():
                    raise ValueError("Split exige tratamento explicito de fracao")
                if qty:
                    holdings[event.ticker] = int(new_qty)
            elif event.kind == "dividend":
                cash += qty * event.value
            else:
                if event.kind == "cancelled_zero" and event.value != 0:
                    raise ValueError("Cancelamento exige valor zero")
                cash += qty * event.value
                holdings.pop(event.ticker, None)
                terminated.add(event.ticker)
            ledger.append({"date": str(day), "ticker": event.ticker, "event": event.kind, "value": event.value, "shares": qty})
        if pending is not None:
            ranked = [s for s in pending if s.eligible and s.ticker not in terminated]
            ranked.sort(key=lambda s: (-s.score, s.ticker))
            nav = cash + sum(q * bar(day, t).close for t, q in holdings.items())
            targets, sector_targets = {}, {}
            for signal in ranked:
                if len(targets) >= rules.max_positions:
                    break
                used = sector_targets.get(signal.sector, 0.0)
                if used + rules.target_weight > rules.sector_limit + 1e-12:
                    continue
                targets[signal.ticker] = floor(nav * rules.target_weight / bar(day, signal.ticker).close)
                sectors[signal.ticker] = signal.sector
                sector_targets[signal.sector] = used + rules.target_weight
            # Require executable sales; a liquidity failure invalidates the run.
            for ticker in sorted(holdings):
                qty = max(0, holdings[ticker] - targets.get(ticker, 0))
                if qty:
                    item = bar(day, ticker)
                    if qty > floor(item.volume * rules.volume_participation):
                        raise ValueError(f"Venda excede liquidez: {ticker} {day}")
                    cost = qty * item.close * fee
                    cash += qty * item.close - cost
                    holdings[ticker] -= qty
                    ledger.append({"date": str(day), "ticker": ticker, "side": "sell", "shares": qty, "price": item.close, "cost": cost})
            holdings = {t: q for t, q in holdings.items() if q}
            for signal in ranked:
                ticker = signal.ticker
                if ticker not in targets:
                    continue
                item = bar(day, ticker)
                qty = max(0, targets[ticker] - holdings.get(ticker, 0))
                qty = min(qty, floor(cash / (item.close * (1 + fee))))
                if qty > floor(item.volume * rules.volume_participation):
                    raise ValueError(f"Compra excede liquidez: {ticker} {day}")
                if qty:
                    cost = qty * item.close * fee
                    cash -= qty * item.close + cost
                    holdings[ticker] = holdings.get(ticker, 0) + qty
                    ledger.append({"date": str(day), "ticker": ticker, "side": "buy", "shares": qty, "price": item.close, "cost": cost})
        pending = None
        nav = cash + sum(q * bar(day, t).close for t, q in holdings.items())
        curve.append({"date": str(day), "cash": cash, "nav": nav, "holdings": dict(holdings)})
        if day in signals:
            pending = tuple(signals[day])
            if len({s.ticker for s in pending}) != len(pending):
                raise ValueError("Ticker duplicado no sinal")
            if any(s.available_on > day or not s.sector or not s.ticker or not isfinite(s.score) or not 0 <= s.score <= 1 for s in pending):
                raise ValueError("Sinal invalido ou contem informacao futura")
    return {"ledger": ledger, "equity_curve": curve, "total_cost": sum(r.get("cost", 0) for r in ledger),
            "benchmark_authorized": False, "limitations": ["Calendario e evidencias PIT precisam de validacao externa ao simulador", "Limites de pesos aplicados nos alvos de rebalanceamento; oscilacoes entre datas podem excede-los", "Dividendos exigem direitos por acao e datas de pagamento pre-processados; fracionamentos nao inteiros bloqueiam"]}

