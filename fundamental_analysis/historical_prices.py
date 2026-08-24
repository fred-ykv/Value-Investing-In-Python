"""Historical valuation prices, adjusted returns, drawdown, and trailing beta."""

from __future__ import annotations

import calendar
import csv
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol

from .benchmark_universe import HistoricalLifecycleEvent
from .config import POINT_IN_TIME, PointInTimeAssumptions


@dataclass(frozen=True)
class PricePoint:
    day: date
    adjusted_close: float
    raw_close: float | None = None

    @property
    def valuation_close(self) -> float:
        return self.raw_close if self.raw_close is not None else self.adjusted_close


@dataclass(frozen=True)
class PriceSeries:
    ticker: str
    points: tuple[PricePoint, ...]
    source: str

    def between(self, start: date, end: date) -> "PriceSeries":
        return PriceSeries(
            self.ticker,
            tuple(point for point in self.points if start <= point.day <= end),
            self.source,
        )


class HistoricalPriceProvider(Protocol):
    def fetch_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        ...


class CsvHistoricalPriceClient:
    """Read normalized research-grade prices, including delisted securities."""

    REQUIRED_COLUMNS = {
        "security_id",
        "ticker",
        "date",
        "adjusted_close",
        "raw_close",
        "source",
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._series = self._load()

    def _load(self) -> dict[str, PriceSeries]:
        by_ticker: dict[str, list[PricePoint]] = {}
        identities: dict[str, str] = {}
        sources: dict[str, set[str]] = {}
        seen_days: dict[str, set[date]] = {}
        with self.path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = self.REQUIRED_COLUMNS - set(reader.fieldnames or ())
            if missing:
                raise ValueError(
                    "CSV historico sem colunas obrigatorias: "
                    + ", ".join(sorted(missing))
                )
            for line_number, row in enumerate(reader, start=2):
                ticker = row["ticker"].upper().strip()
                security_id = row["security_id"].strip()
                source = row["source"].strip()
                if not ticker or not security_id or not source:
                    raise ValueError(
                        f"Identidade, ticker ou fonte ausente na linha {line_number}"
                    )
                previous_identity = identities.setdefault(ticker, security_id)
                if previous_identity != security_id:
                    raise ValueError(
                        f"Mais de uma identidade permanente para {ticker}: "
                        f"{previous_identity}, {security_id}"
                    )
                try:
                    point = PricePoint(
                        date.fromisoformat(row["date"].strip()),
                        float(row["adjusted_close"]),
                        float(row["raw_close"]),
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Preco historico invalido na linha {line_number}: {exc}"
                    ) from exc
                if (
                    not math.isfinite(point.adjusted_close)
                    or point.adjusted_close <= 0
                    or point.raw_close is None
                    or not math.isfinite(point.raw_close)
                    or point.raw_close <= 0
                ):
                    raise ValueError(
                        f"Preco nao positivo ou nao finito na linha {line_number}"
                    )
                if point.day in seen_days.setdefault(ticker, set()):
                    raise ValueError(
                        f"Preco duplicado para {ticker} em {point.day}"
                    )
                seen_days[ticker].add(point.day)
                by_ticker.setdefault(ticker, []).append(point)
                sources.setdefault(ticker, set()).add(source)
        return {
            ticker: normalize_price_series(
                PriceSeries(
                    ticker,
                    tuple(points),
                    "normalized_csv["
                    + identities[ticker]
                    + "]:"
                    + ";".join(sorted(sources[ticker])),
                )
            )
            for ticker, points in by_ticker.items()
        }

    def fetch_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        normalized = ticker.upper().strip()
        if normalized not in self._series:
            raise LookupError(
                f"Serie historica de {normalized} ausente no CSV {self.path.name}"
            )
        return self._series[normalized].between(start, end)


class CompositeHistoricalPriceClient:
    """Try providers in order while preserving a useful failure trail."""

    def __init__(self, *providers: HistoricalPriceProvider):
        if not providers:
            raise ValueError("Informe ao menos um provedor de precos historicos")
        self.providers = providers

    def fetch_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.fetch_series(ticker, start, end)
            except LookupError as exc:
                errors.append(str(exc))
        raise LookupError(" | ".join(errors))


@dataclass(frozen=True)
class PriceOutcome:
    ticker: str
    benchmark_ticker: str
    as_of: date
    target_end_date: date
    price_start_date: date
    price_end_date: date
    start_price: float
    end_price: float
    benchmark_start_price: float
    benchmark_end_price: float
    start_adjusted_price: float
    end_adjusted_price: float
    forward_return: float
    benchmark_return: float
    max_drawdown: float
    trailing_beta: float | None
    beta_observations: int
    source: str
    outcome_method: str = "market_price_12m"
    stock_terminal_date: date | None = None
    lifecycle_event_type: str = ""
    lifecycle_event_date: date | None = None
    terminal_value_per_share: float | None = None
    lifecycle_source_url: str = ""


class YFinanceHistoricalPriceClient:
    """Fetch historical prices once per ticker and reuse them across observations."""

    def __init__(self):
        self._cache: dict[str, PriceSeries] = {}

    def fetch_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        normalized = ticker.upper().strip()
        if normalized not in self._cache:
            import yfinance as yf  # type: ignore

            frame = yf.Ticker(normalized).history(
                period="max",
                auto_adjust=False,
                actions=True,
            )
            if frame is None or getattr(frame, "empty", True):
                raise LookupError(f"Serie historica indisponivel para {normalized}")
            points = yfinance_price_points(frame)
            self._cache[normalized] = normalize_price_series(
                PriceSeries(normalized, tuple(points), "yfinance_historical")
            )
        return self._cache[normalized].between(start, end)


def yfinance_price_points(frame: object) -> list[PricePoint]:
    """Restore as-traded closes because Yahoo back-adjusts Close for later splits."""

    raw_close = frame["Close"]
    adjusted_close = frame["Adj Close"] if "Adj Close" in frame else raw_close
    splits = frame["Stock Splits"] if "Stock Splits" in frame else None
    points: list[PricePoint] = []
    future_split_factor = 1.0
    for raw_day in reversed(frame.index):
        close_value = float(raw_close.loc[raw_day])
        adjusted_value = float(adjusted_close.loc[raw_day])
        valuation_value = close_value * future_split_factor
        if (
            math.isfinite(valuation_value)
            and valuation_value > 0
            and math.isfinite(adjusted_value)
            and adjusted_value > 0
        ):
            converted = (
                raw_day.to_pydatetime().date()
                if hasattr(raw_day, "to_pydatetime")
                else date.fromisoformat(str(raw_day)[:10])
            )
            points.append(PricePoint(converted, adjusted_value, valuation_value))
        if splits is not None:
            split_factor = float(splits.loc[raw_day])
            if math.isfinite(split_factor) and split_factor > 0:
                future_split_factor *= split_factor
    points.reverse()
    return points


def calculate_price_outcome(
    ticker: str,
    benchmark_ticker: str,
    as_of: date,
    provider: HistoricalPriceProvider,
    assumptions: PointInTimeAssumptions = POINT_IN_TIME,
    lifecycle_event: HistoricalLifecycleEvent | None = None,
) -> PriceOutcome:
    target_end = add_months(as_of, assumptions.forward_horizon_months)
    lookback_start = add_months(as_of, -assumptions.beta_lookback_months) - timedelta(days=10)
    fetch_end = target_end + timedelta(days=assumptions.price_end_max_lag_days + 2)
    stock = normalize_price_series(provider.fetch_series(ticker, lookback_start, fetch_end))
    benchmark = normalize_price_series(provider.fetch_series(benchmark_ticker, lookback_start, fetch_end))

    stock_start = _first_on_or_after(
        stock,
        as_of,
        assumptions.price_start_max_lag_days,
        "inicio da acao",
    )
    benchmark_start = _first_on_or_after(
        benchmark,
        stock_start.day,
        assumptions.price_start_max_lag_days,
        "inicio do benchmark",
    )
    if lifecycle_event is not None and lifecycle_event.effective_date <= as_of:
        raise LookupError(
            f"Evento terminal de {ticker.upper().strip()} ocorreu antes da data-base"
        )
    if (
        lifecycle_event is not None
        and lifecycle_event.effective_date <= target_end
    ):
        return _calculate_lifecycle_outcome(
            ticker,
            benchmark_ticker,
            as_of,
            target_end,
            stock,
            benchmark,
            stock_start,
            benchmark_start,
            lifecycle_event,
            assumptions,
        )
    stock_end = _first_on_or_after(
        stock,
        target_end,
        assumptions.price_end_max_lag_days,
        "fim da acao",
    )
    benchmark_end = _first_on_or_after(
        benchmark,
        stock_end.day,
        assumptions.price_end_max_lag_days,
        "fim do benchmark",
    )
    if benchmark_start.day != stock_start.day or benchmark_end.day != stock_end.day:
        raise LookupError(
            "Acao e benchmark nao possuem precos nas mesmas datas de inicio e fim"
        )

    forward_return = stock_end.adjusted_close / stock_start.adjusted_close - 1.0
    benchmark_return = benchmark_end.adjusted_close / benchmark_start.adjusted_close - 1.0
    drawdown = maximum_drawdown(stock, stock_start.day, stock_end.day)
    beta, beta_observations = trailing_beta(
        stock,
        benchmark,
        stock_start.day,
        add_months(stock_start.day, -assumptions.beta_lookback_months),
        assumptions.minimum_beta_return_observations,
    )
    return PriceOutcome(
        ticker=ticker.upper().strip(),
        benchmark_ticker=benchmark_ticker.upper().strip(),
        as_of=as_of,
        target_end_date=target_end,
        price_start_date=stock_start.day,
        price_end_date=stock_end.day,
        start_price=stock_start.valuation_close,
        end_price=stock_end.valuation_close,
        benchmark_start_price=benchmark_start.adjusted_close,
        benchmark_end_price=benchmark_end.adjusted_close,
        start_adjusted_price=stock_start.adjusted_close,
        end_adjusted_price=stock_end.adjusted_close,
        forward_return=forward_return,
        benchmark_return=benchmark_return,
        max_drawdown=drawdown,
        trailing_beta=beta,
        beta_observations=beta_observations,
        source=stock.source + ";" + benchmark.source,
        stock_terminal_date=stock_end.day,
    )


def _calculate_lifecycle_outcome(
    ticker: str,
    benchmark_ticker: str,
    as_of: date,
    target_end: date,
    stock: PriceSeries,
    benchmark: PriceSeries,
    stock_start: PricePoint,
    benchmark_start: PricePoint,
    event: HistoricalLifecycleEvent,
    assumptions: PointInTimeAssumptions,
) -> PriceOutcome:
    stock_terminal = _last_on_or_before(
        stock,
        event.effective_date,
        assumptions.terminal_event_price_max_lag_days,
        "ultimo preco antes do evento terminal",
    )
    benchmark_terminal = _first_on_or_after(
        benchmark,
        event.effective_date,
        assumptions.price_end_max_lag_days,
        "benchmark no evento terminal",
    )
    benchmark_end = _first_on_or_after(
        benchmark,
        target_end,
        assumptions.price_end_max_lag_days,
        "fim do benchmark",
    )
    if benchmark_start.day != stock_start.day:
        raise LookupError("Acao e benchmark nao possuem o mesmo inicio")
    if stock_terminal.day < stock_start.day:
        raise LookupError("Evento terminal nao possui historico posterior ao inicio")

    if event.event_type == "cash_acquisition":
        terminal_adjustment = (
            stock_terminal.adjusted_close / stock_terminal.valuation_close
        )
        terminal_adjusted_value = event.terminal_value_per_share * terminal_adjustment
    elif event.event_type == "cancelled_zero":
        terminal_adjusted_value = 0.0
    else:
        raise ValueError(f"Evento terminal nao suportado: {event.event_type}")

    event_wealth = terminal_adjusted_value / stock_start.adjusted_close
    benchmark_reinvestment = (
        benchmark_end.adjusted_close / benchmark_terminal.adjusted_close
    )
    forward_return = event_wealth * benchmark_reinvestment - 1.0
    benchmark_return = (
        benchmark_end.adjusted_close / benchmark_start.adjusted_close - 1.0
    )
    drawdown = maximum_drawdown_with_terminal_reinvestment(
        stock,
        benchmark,
        stock_start,
        stock_terminal,
        benchmark_terminal,
        benchmark_end,
        terminal_adjusted_value,
    )
    beta, beta_observations = trailing_beta(
        stock,
        benchmark,
        stock_start.day,
        add_months(stock_start.day, -assumptions.beta_lookback_months),
        assumptions.minimum_beta_return_observations,
    )
    return PriceOutcome(
        ticker=ticker.upper().strip(),
        benchmark_ticker=benchmark_ticker.upper().strip(),
        as_of=as_of,
        target_end_date=target_end,
        price_start_date=stock_start.day,
        price_end_date=benchmark_end.day,
        start_price=stock_start.valuation_close,
        end_price=event.terminal_value_per_share,
        benchmark_start_price=benchmark_start.adjusted_close,
        benchmark_end_price=benchmark_end.adjusted_close,
        start_adjusted_price=stock_start.adjusted_close,
        end_adjusted_price=terminal_adjusted_value,
        forward_return=forward_return,
        benchmark_return=benchmark_return,
        max_drawdown=drawdown,
        trailing_beta=beta,
        beta_observations=beta_observations,
        source=stock.source + ";" + benchmark.source + ";sec_terminal_event",
        outcome_method=(
            "cash_acquisition_reinvested_in_benchmark"
            if event.event_type == "cash_acquisition"
            else "cancelled_zero"
        ),
        stock_terminal_date=stock_terminal.day,
        lifecycle_event_type=event.event_type,
        lifecycle_event_date=event.effective_date,
        terminal_value_per_share=event.terminal_value_per_share,
        lifecycle_source_url=event.source_url,
    )


def normalize_price_series(series: PriceSeries) -> PriceSeries:
    by_day: dict[date, PricePoint] = {}
    for point in series.points:
        adjusted = float(point.adjusted_close)
        raw = float(point.raw_close) if point.raw_close is not None else None
        if math.isfinite(adjusted) and adjusted > 0 and (raw is None or math.isfinite(raw) and raw > 0):
            by_day[point.day] = PricePoint(point.day, adjusted, raw)
    points = tuple(by_day[day] for day in sorted(by_day))
    if not points:
        raise LookupError(f"Serie historica vazia para {series.ticker}")
    return PriceSeries(series.ticker.upper().strip(), points, series.source)


def maximum_drawdown(series: PriceSeries, start: date, end: date) -> float:
    points = [point for point in series.points if start <= point.day <= end]
    if not points:
        raise LookupError(f"Sem precos para calcular drawdown de {series.ticker}")
    peak = points[0].adjusted_close
    worst = 0.0
    for point in points:
        peak = max(peak, point.adjusted_close)
        worst = min(worst, point.adjusted_close / peak - 1.0)
    return worst


def maximum_drawdown_with_terminal_reinvestment(
    stock: PriceSeries,
    benchmark: PriceSeries,
    stock_start: PricePoint,
    stock_terminal: PricePoint,
    benchmark_terminal: PricePoint,
    benchmark_end: PricePoint,
    terminal_adjusted_value: float,
) -> float:
    wealth: list[tuple[date, float]] = [
        (point.day, point.adjusted_close / stock_start.adjusted_close)
        for point in stock.points
        if stock_start.day <= point.day <= stock_terminal.day
    ]
    terminal_wealth = terminal_adjusted_value / stock_start.adjusted_close
    wealth.append((benchmark_terminal.day, terminal_wealth))
    wealth.extend(
        (
            point.day,
            terminal_wealth
            * point.adjusted_close
            / benchmark_terminal.adjusted_close,
        )
        for point in benchmark.points
        if benchmark_terminal.day < point.day <= benchmark_end.day
    )
    if not wealth:
        raise LookupError("Sem precos para calcular drawdown do evento terminal")
    by_day = {day: value for day, value in wealth}
    peak = by_day[min(by_day)]
    worst = 0.0
    for day in sorted(by_day):
        value = by_day[day]
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0 if peak else -1.0)
    return worst


def trailing_beta(
    stock: PriceSeries,
    benchmark: PriceSeries,
    cutoff: date,
    lookback_start: date,
    minimum_observations: int,
) -> tuple[float | None, int]:
    stock_returns = _daily_returns(stock, lookback_start, cutoff)
    benchmark_returns = _daily_returns(benchmark, lookback_start, cutoff)
    common_days = sorted(set(stock_returns) & set(benchmark_returns))
    if len(common_days) < minimum_observations:
        return None, len(common_days)
    stock_values = [stock_returns[day] for day in common_days]
    benchmark_values = [benchmark_returns[day] for day in common_days]
    stock_mean = sum(stock_values) / len(stock_values)
    benchmark_mean = sum(benchmark_values) / len(benchmark_values)
    covariance = sum(
        (stock_value - stock_mean) * (benchmark_value - benchmark_mean)
        for stock_value, benchmark_value in zip(stock_values, benchmark_values)
    )
    benchmark_variance = sum(
        (benchmark_value - benchmark_mean) ** 2 for benchmark_value in benchmark_values
    )
    return (covariance / benchmark_variance if benchmark_variance else None), len(common_days)


def _daily_returns(series: PriceSeries, start: date, cutoff: date) -> dict[date, float]:
    points = [point for point in series.points if start <= point.day < cutoff]
    returns: dict[date, float] = {}
    for previous, current in zip(points, points[1:]):
        returns[current.day] = current.adjusted_close / previous.adjusted_close - 1.0
    return returns


def _first_on_or_after(
    series: PriceSeries,
    target: date,
    maximum_lag_days: int,
    label: str,
) -> PricePoint:
    candidates = [point for point in series.points if point.day >= target]
    if not candidates:
        raise LookupError(f"Preco ausente para {label} em {series.ticker}")
    selected = candidates[0]
    if (selected.day - target).days > maximum_lag_days:
        raise LookupError(
            f"Preco de {label} para {series.ticker} esta {selected.day - target} dias apos a data-alvo"
        )
    return selected


def _last_on_or_before(
    series: PriceSeries,
    target: date,
    maximum_lag_days: int,
    label: str,
) -> PricePoint:
    candidates = [point for point in series.points if point.day <= target]
    if not candidates:
        raise LookupError(f"Preco ausente para {label} em {series.ticker}")
    selected = candidates[-1]
    if (target - selected.day).days > maximum_lag_days:
        raise LookupError(
            f"Preco de {label} para {series.ticker} esta "
            f"{target - selected.day} dias antes da data-alvo"
        )
    return selected


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
