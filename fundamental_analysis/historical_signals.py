"""Derive auditable operating signals from comparable annual statements."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Iterable, Mapping

from .data_sources import MetricValue, get_mapping_value
from .financial_statements import FinancialStatements, build_statement_metrics


HISTORICAL_SIGNAL_NAMES = ("revenue_growth", "fcff_growth", "gross_margin")


def derive_historical_signals(
    history: Iterable[FinancialStatements] | object,
) -> dict[str, MetricValue]:
    """Build like-for-like annual signals without inventing missing observations."""
    periods = _annual_periods(history)
    if not periods:
        return {}

    latest_date, latest_statements = periods[-1]
    previous = periods[-2] if len(periods) >= 2 else None
    signals = {
        "gross_margin": _gross_margin(latest_statements, latest_date),
    }
    if previous is None:
        note = "Sao necessarios dois periodos anuais comparaveis."
        signals["revenue_growth"] = _unavailable_signal(
            "revenue_growth", latest_statements, note, period_end=latest_date
        )
        signals["fcff_growth"] = _unavailable_signal(
            "fcff_growth", latest_statements, note, period_end=latest_date
        )
        return signals

    previous_date, previous_statements = previous
    signals["revenue_growth"] = _growth_signal(
        "revenue_growth",
        _statement_value(latest_statements, "revenue"),
        _statement_value(previous_statements, "revenue"),
        previous_date,
        latest_date,
        "Receita anual mais recente / receita anual anterior - 1.",
        "current_annual_revenue_divided_by_prior_annual_revenue_minus_one",
        require_positive=True,
    )
    signals["fcff_growth"] = _growth_signal(
        "fcff_growth",
        build_statement_metrics(latest_statements).get("fcff"),
        build_statement_metrics(previous_statements).get("fcff"),
        previous_date,
        latest_date,
        (
            "FCFF anual mais recente / FCFF anual anterior - 1; ambos os "
            "periodos usam a mesma formula do modelo."
        ),
        "current_positive_annual_fcff_divided_by_prior_positive_annual_fcff_minus_one",
        require_positive=True,
    )
    return signals


def merge_historical_signals(
    market_data: Mapping[str, object],
    signals: Mapping[str, MetricValue],
) -> dict[str, object]:
    """Prefer dated annual evidence over an undated Yahoo profile estimate."""
    merged = dict(market_data)
    for name, signal in signals.items():
        existing = merged.get(name)
        if not _is_available(existing):
            merged[name] = signal
            continue
        if signal.is_available and _is_undated_yahoo_profile(existing):
            merged[name] = signal
    return merged


def historical_signal_payload(
    signals: Mapping[str, MetricValue],
) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for name in HISTORICAL_SIGNAL_NAMES:
        metric = signals.get(name)
        if metric is None:
            continue
        row = asdict(metric)
        for field_name in ("period_start", "period_end", "filing_date", "as_of"):
            value = row.get(field_name)
            row[field_name] = value.isoformat() if value is not None else None
        payload[name] = row
    return payload


def _annual_periods(
    history: Iterable[FinancialStatements] | object,
) -> list[tuple[date, FinancialStatements]]:
    if not isinstance(history, (list, tuple)):
        return []
    by_period: dict[date, FinancialStatements] = {}
    for statements in history:
        if not isinstance(statements, FinancialStatements):
            continue
        revenue = _statement_value(statements, "revenue")
        if revenue.is_available and revenue.period_end is not None:
            by_period[revenue.period_end] = statements
    return sorted(by_period.items())


def _statement_value(statements: FinancialStatements, name: str) -> MetricValue:
    if name == "gross_profit":
        return get_mapping_value(
            statements.income_statement,
            "gross_profit",
            "Gross Profit",
            source=statements.source,
        )
    return build_statement_metrics(statements).get(name)


def _gross_margin(statements: FinancialStatements, period_end: date) -> MetricValue:
    gross_profit = _statement_value(statements, "gross_profit")
    revenue = _statement_value(statements, "revenue")
    if (
        not gross_profit.is_available
        or not revenue.is_available
        or float(revenue.value) <= 0.0
    ):
        return _unavailable_signal(
            "gross_margin",
            statements,
            "Margem bruta exige lucro bruto e receita anual positiva no mesmo periodo.",
            period_end=period_end,
            inputs=(gross_profit, revenue),
        )
    return _derived_signal(
        "gross_margin",
        float(gross_profit.value) / float(revenue.value),
        (gross_profit, revenue),
        _shared((gross_profit, revenue), "period_start"),
        period_end,
        "Lucro bruto anual / receita anual do mesmo periodo.",
        "annual_gross_profit_divided_by_annual_revenue",
        (("gross_profit", float(gross_profit.value)), ("revenue", float(revenue.value))),
    )


def _growth_signal(
    name: str,
    current: MetricValue,
    prior: MetricValue,
    period_start: date | None,
    period_end: date,
    note: str,
    formula: str,
    *,
    require_positive: bool,
) -> MetricValue:
    observations = tuple(
        (label, float(metric.value))
        for label, metric in (("current", current), ("prior", prior))
        if metric.is_available
    )
    if not current.is_available or not prior.is_available:
        return _unavailable_from_inputs(
            name,
            current,
            prior,
            "Os dois periodos anuais comparaveis precisam estar disponiveis.",
            period_start,
            period_end,
            formula,
            observations,
        )
    current_value = float(current.value)
    prior_value = float(prior.value)
    if require_positive and (current_value <= 0.0 or prior_value <= 0.0):
        return _unavailable_from_inputs(
            name,
            current,
            prior,
            (
                "Taxa percentual recusada: os dois valores anuais precisam ser "
                "positivos; mudanca de sinal nao representa crescimento comparavel."
            ),
            period_start,
            period_end,
            formula,
            observations,
        )
    return _derived_signal(
        name,
        current_value / prior_value - 1.0,
        (current, prior),
        period_start,
        period_end,
        note,
        formula,
        observations,
    )


def _derived_signal(
    name: str,
    value: float,
    inputs: tuple[MetricValue, ...],
    period_start: date,
    period_end: date,
    note: str,
    formula: str,
    observations: tuple[tuple[str, float], ...],
) -> MetricValue:
    source = _derived_source(tuple(metric for metric in inputs if metric.is_available))
    confidence = max(
        0.0,
        min(metric.confidence for metric in inputs if metric.is_available) - 0.05,
    )
    documents = list(
        dict.fromkeys(metric.source_document for metric in inputs if metric.source_document)
    )
    return MetricValue(
        name,
        value,
        source,
        confidence,
        note,
        source_url=_shared(inputs, "source_url"),
        source_document="; ".join(documents) if documents else None,
        period_start=period_start,
        period_end=period_end,
        filing_date=_shared(inputs, "filing_date"),
        as_of=_shared(inputs, "as_of"),
        currency=None,
        scale="ratio",
        basis="derived",
        is_fallback=any(metric.is_fallback for metric in inputs),
        formula=formula,
        input_observations=observations,
    )


def _unavailable_from_inputs(
    name: str,
    current: MetricValue,
    prior: MetricValue,
    note: str,
    period_start: date,
    period_end: date,
    formula: str,
    observations: tuple[tuple[str, float], ...],
) -> MetricValue:
    available = tuple(metric for metric in (current, prior) if metric.is_available)
    return MetricValue(
        name,
        None,
        _derived_source(available),
        0.0,
        note,
        source_url=_shared(available, "source_url"),
        source_document=_shared(available, "source_document"),
        period_start=period_start,
        period_end=period_end,
        filing_date=_shared(available, "filing_date"),
        as_of=_shared(available, "as_of"),
        scale="ratio",
        basis="derived",
        is_fallback=any(metric.is_fallback for metric in available),
        formula=formula,
        input_observations=observations,
    )


def _unavailable_signal(
    name: str,
    statements: FinancialStatements,
    note: str,
    *,
    period_end: date,
    inputs: tuple[MetricValue, ...] = (),
) -> MetricValue:
    return MetricValue(
        name,
        None,
        f"{statements.source}_derived",
        0.0,
        note,
        source_url=_shared(inputs, "source_url"),
        source_document=_shared(inputs, "source_document"),
        period_end=period_end,
        scale="ratio",
        basis="derived",
    )


def _derived_source(metrics: tuple[MetricValue, ...]) -> str:
    sources = {metric.source for metric in metrics}
    documents = " ".join(
        str(metric.source_document or "").lower() for metric in metrics
    )
    if "yahoo finance" in documents and "sec edgar" in documents:
        return "cross_source_derived"
    if "yahoo finance" in documents:
        return "yfinance_derived"
    if "sec edgar" in documents:
        return "sec_edgar_derived"
    return f"{next(iter(sources))}_derived" if len(sources) == 1 else "derived"


def _shared(metrics: tuple[MetricValue, ...], field_name: str) -> object:
    values = {
        getattr(metric, field_name)
        for metric in metrics
        if getattr(metric, field_name) is not None
    }
    return next(iter(values)) if len(values) == 1 else None


def _is_available(value: object) -> bool:
    if isinstance(value, MetricValue):
        return value.is_available
    return value is not None


def _is_undated_yahoo_profile(value: object) -> bool:
    return (
        isinstance(value, MetricValue)
        and value.source == "yfinance"
        and value.period_end is None
        and value.source_document == "Yahoo Finance quote/profile info"
    )


__all__ = [
    "HISTORICAL_SIGNAL_NAMES",
    "derive_historical_signals",
    "historical_signal_payload",
    "merge_historical_signals",
]
