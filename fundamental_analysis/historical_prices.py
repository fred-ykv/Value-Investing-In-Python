"""Adjusted historical prices, forward outcomes, drawdown, and trailing beta."""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from .config import POINT_IN_TIME, PointInTimeAssumptions


@dataclass(frozen=True)
class PricePoint:
    day: date
    adjusted_close: float


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
    forward_return: float
    benchmark_return: float
    max_drawdown: float
    trailing_beta: float | None
    beta_observations: int
    source: str


class YFinanceHistoricalPriceClient:
    """Fetch adjusted closes once per ticker and reuse them across observations."""

    def __init__(self):
        self._cache: dict[str, PriceSeries] = {}

    def fetch_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        normalized = ticker.upper().strip()
        if normalized not in self._cache:
            import yfinance as yf  # type: ignore

            frame = yf.Ticker(normalized).history(
                period="max",
                auto_adjust=True,
                actions=False,
            )
            if frame is None or getattr(frame, "empty", True):
                raise LookupError(f"Serie historica indisponivel para {normalized}")
            points: list[PricePoint] = []
            close = frame["Close"]
            for raw_day, raw_value in close.items():
                value = float(raw_value)
                if not math.isfinite(value) or value <= 0:
                    continue
                converted = raw_day.to_pydatetime().date() if hasattr(raw_day, "to_pydatetime") else date.fromisoformat(str(raw_day)[:10])
                points.append(PricePoint(converted, value))
            self._cache[normalized] = normalize_price_series(
                PriceSeries(normalized, tuple(points), "yfinance_historical")
            )
        return self._cache[normalized].between(start, end)


def calculate_price_outcome(
    ticker: str,
    benchmark_ticker: str,
    as_of: date,
    provider: HistoricalPriceProvider,
    assumptions: PointInTimeAssumptions = POINT_IN_TIME,
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
        start_price=stock_start.adjusted_close,
        end_price=stock_end.adjusted_close,
        benchmark_start_price=benchmark_start.adjusted_close,
        benchmark_end_price=benchmark_end.adjusted_close,
        forward_return=forward_return,
        benchmark_return=benchmark_return,
        max_drawdown=drawdown,
        trailing_beta=beta,
        beta_observations=beta_observations,
        source="yfinance_historical_adjusted_close",
    )


def normalize_price_series(series: PriceSeries) -> PriceSeries:
    by_day: dict[date, float] = {}
    for point in series.points:
        value = float(point.adjusted_close)
        if math.isfinite(value) and value > 0:
            by_day[point.day] = value
    points = tuple(PricePoint(day, by_day[day]) for day in sorted(by_day))
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


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

