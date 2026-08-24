"""Auditable mid-cycle normalization for mature cyclical companies."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Iterable, Mapping

from .config import CYCLICAL, CompanyType, CyclicalNormalizationAssumptions
from .data_sources import MetricValue, clamp, metric_value
from .financial_statements import FinancialStatements, build_statement_metrics


@dataclass(frozen=True)
class CyclicalPeriod:
    period_end: date
    revenue: float
    operating_margin: float | None
    net_margin: float | None
    tax_rate: float | None
    fcff_margin: float | None
    reinvestment_margin: float | None
    confidence: float
    fcff_uses_nwc_fallback: bool
    source_document: str = ""


@dataclass(frozen=True)
class CyclicalNormalizationResult:
    is_cyclical: bool
    applied: bool
    status: str
    periods: tuple[CyclicalPeriod, ...]
    confidence: float
    cycle_position: str
    normalized_operating_margin: float | None
    normalized_net_margin: float | None
    normalized_tax_rate: float | None
    normalized_fcff_margin: float | None
    normalized_reinvestment_margin: float | None
    current_operating_margin: float | None
    current_net_margin: float | None
    current_fcff_margin: float | None
    normalized_ebit: MetricValue
    normalized_nopat: MetricValue
    normalized_net_income: MetricValue
    normalized_reinvestment: MetricValue
    normalized_fcff: MetricValue
    normalized_fcff_direct: MetricValue
    normalized_roic: MetricValue
    transition_years: int
    warnings: tuple[str, ...] = ()

    @property
    def sample_years(self) -> int:
        return len(self.periods)


def is_cyclical_profile(
    info: Mapping[str, object],
    market_data: Mapping[str, object],
    assumptions: CyclicalNormalizationAssumptions = CYCLICAL,
) -> bool:
    explicit = market_data.get("is_cyclical")
    if explicit is not None:
        if isinstance(explicit, str):
            return explicit.strip().lower() in {"1", "true", "sim", "yes"}
        return bool(explicit)
    text = " ".join(
        str(value or "").lower()
        for value in (
            info.get("sector"),
            info.get("industry"),
            info.get("business_model"),
            market_data.get("sector_bucket"),
        )
    )
    return any(keyword in text for keyword in assumptions.industry_keywords)


def normalize_cyclical_financials(
    company_type: CompanyType,
    current_values: Mapping[str, MetricValue],
    history: Iterable[FinancialStatements] | object,
    info: Mapping[str, object],
    market_data: Mapping[str, object],
    assumptions: CyclicalNormalizationAssumptions = CYCLICAL,
) -> CyclicalNormalizationResult:
    cyclical = company_type == CompanyType.TRADITIONAL and is_cyclical_profile(
        info,
        market_data,
        assumptions,
    )
    if not cyclical:
        return _unavailable_result(False, "not_applicable", assumptions)

    periods, period_warnings = build_cyclical_periods(history, assumptions)
    warnings = list(period_warnings)
    history_warning = market_data.get("cyclical_history_warning")
    if history_warning:
        warnings.append(str(history_warning))
    current_revenue = _number(current_values.get("revenue"))
    if current_revenue is None or current_revenue <= 0:
        warnings.append("Receita corrente invalida; a normalizacao nao foi aplicada.")
        return _unavailable_result(
            True,
            "invalid_current_revenue",
            assumptions,
            periods=periods,
            warnings=warnings,
        )

    series = {
        "operating": [p.operating_margin for p in periods if p.operating_margin is not None],
        "net": [p.net_margin for p in periods if p.net_margin is not None],
        "tax": [p.tax_rate for p in periods if p.tax_rate is not None],
        "fcff": [p.fcff_margin for p in periods if p.fcff_margin is not None],
        "reinvestment": [
            p.reinvestment_margin for p in periods if p.reinvestment_margin is not None
        ],
    }
    minimum_count = min((len(values) for values in series.values()), default=0)
    if minimum_count < assumptions.minimum_years:
        counts = ", ".join(f"{name}={len(values)}" for name, values in series.items())
        warnings.append(
            f"Historico insuficiente para normalizar o ciclo: {counts}; "
            f"minimo {assumptions.minimum_years} por componente."
        )
        return _unavailable_result(
            True,
            "insufficient_history",
            assumptions,
            periods=periods,
            warnings=warnings,
            current_values=current_values,
        )

    operating_margin = _bounded_robust_mean(
        series["operating"], assumptions.operating_margin_bounds, assumptions
    )
    net_margin = _bounded_robust_mean(
        series["net"], assumptions.net_margin_bounds, assumptions
    )
    tax_rate = _bounded_robust_mean(
        series["tax"], assumptions.tax_rate_bounds, assumptions
    )
    fcff_margin = _bounded_robust_mean(
        series["fcff"], assumptions.fcff_margin_bounds, assumptions
    )
    reinvestment_margin = _bounded_robust_mean(
        series["reinvestment"], assumptions.reinvestment_margin_bounds, assumptions
    )

    normalized_ebit_value = current_revenue * operating_margin
    normalized_nopat_value = normalized_ebit_value * (1.0 - tax_rate)
    normalized_net_income_value = current_revenue * net_margin
    normalized_reinvestment_value = current_revenue * reinvestment_margin
    normalized_fcff_value = normalized_nopat_value - normalized_reinvestment_value
    normalized_fcff_direct_value = current_revenue * fcff_margin
    crosscheck_gap = abs(normalized_fcff_value - normalized_fcff_direct_value) / current_revenue

    confidence = _normalization_confidence(periods, minimum_count, crosscheck_gap, assumptions)
    if crosscheck_gap > assumptions.maximum_fcff_crosscheck_gap:
        warnings.append(
            f"FCFF por componentes diverge {crosscheck_gap:.1%} da margem FCFF historica."
        )
    nwc_fallback_count = sum(period.fcff_uses_nwc_fallback for period in periods)
    if nwc_fallback_count:
        warnings.append(
            f"Variacao de capital de giro indisponivel em {nwc_fallback_count} de "
            f"{len(periods)} periodos; o FCFF desses anos usou aproximacao explicita."
        )

    cycle_position = _cycle_position(
        _ratio(_number(current_values.get("ebit")), current_revenue),
        series["operating"],
        operating_margin,
        assumptions,
    )
    applied = confidence >= assumptions.minimum_confidence
    if not applied:
        warnings.append(
            f"Confianca de {confidence:.2f} abaixo do minimo de "
            f"{assumptions.minimum_confidence:.2f}; valores correntes foram preservados."
        )
    status = "applied" if applied else "low_confidence"
    lineage = _lineage(periods, current_values, confidence)
    normalized_ebit = _normalized_metric(
        "normalized_ebit",
        normalized_ebit_value,
        "Receita corrente x margem EBIT normalizada do ciclo",
        "current_revenue_times_normalized_operating_margin",
        lineage,
    )
    normalized_nopat = _normalized_metric(
        "normalized_nopat",
        normalized_nopat_value,
        "EBIT normalizado x (1 - aliquota normalizada)",
        "normalized_ebit_after_tax",
        lineage,
    )
    normalized_net_income = _normalized_metric(
        "normalized_net_income",
        normalized_net_income_value,
        "Receita corrente x margem liquida normalizada do ciclo",
        "current_revenue_times_normalized_net_margin",
        lineage,
    )
    normalized_reinvestment = _normalized_metric(
        "normalized_reinvestment",
        normalized_reinvestment_value,
        "Receita corrente x margem historica de reinvestimento",
        "current_revenue_times_normalized_reinvestment_margin",
        lineage,
    )
    normalized_fcff = _normalized_metric(
        "normalized_fcff",
        normalized_fcff_value,
        "NOPAT normalizado - reinvestimento normalizado",
        "normalized_nopat_minus_normalized_reinvestment",
        lineage,
    )
    normalized_fcff_direct = _normalized_metric(
        "normalized_fcff_direct",
        normalized_fcff_direct_value,
        "Receita corrente x margem FCFF normalizada; controle de reconciliacao",
        "current_revenue_times_normalized_fcff_margin",
        lineage,
    )
    invested_capital = _number(current_values.get("invested_capital"))
    normalized_roic_value = (
        normalized_nopat_value / invested_capital
        if invested_capital is not None and invested_capital > 0
        else None
    )
    normalized_roic = _normalized_metric(
        "normalized_roic",
        normalized_roic_value,
        "NOPAT normalizado / capital investido corrente",
        "normalized_nopat_divided_by_current_invested_capital",
        lineage,
    )
    if not applied:
        normalized_ebit = _disabled_metric(normalized_ebit)
        normalized_nopat = _disabled_metric(normalized_nopat)
        normalized_net_income = _disabled_metric(normalized_net_income)
        normalized_reinvestment = _disabled_metric(normalized_reinvestment)
        normalized_fcff = _disabled_metric(normalized_fcff)
        normalized_fcff_direct = _disabled_metric(normalized_fcff_direct)
        normalized_roic = _disabled_metric(normalized_roic)

    return CyclicalNormalizationResult(
        is_cyclical=True,
        applied=applied,
        status=status,
        periods=periods,
        confidence=confidence,
        cycle_position=cycle_position,
        normalized_operating_margin=operating_margin,
        normalized_net_margin=net_margin,
        normalized_tax_rate=tax_rate,
        normalized_fcff_margin=fcff_margin,
        normalized_reinvestment_margin=reinvestment_margin,
        current_operating_margin=_ratio(_number(current_values.get("ebit")), current_revenue),
        current_net_margin=_ratio(_number(current_values.get("net_income")), current_revenue),
        current_fcff_margin=_ratio(_number(current_values.get("fcff")), current_revenue),
        normalized_ebit=normalized_ebit,
        normalized_nopat=normalized_nopat,
        normalized_net_income=normalized_net_income,
        normalized_reinvestment=normalized_reinvestment,
        normalized_fcff=normalized_fcff,
        normalized_fcff_direct=normalized_fcff_direct,
        normalized_roic=normalized_roic,
        transition_years=assumptions.transition_years,
        warnings=tuple(warnings),
    )


def build_cyclical_periods(
    history: Iterable[FinancialStatements] | object,
    assumptions: CyclicalNormalizationAssumptions = CYCLICAL,
) -> tuple[tuple[CyclicalPeriod, ...], tuple[str, ...]]:
    if not isinstance(history, Iterable) or isinstance(history, (str, bytes, Mapping)):
        return (), ()
    by_period: dict[date, CyclicalPeriod] = {}
    warnings: list[str] = []
    for statements in history:
        if not isinstance(statements, FinancialStatements):
            continue
        values = build_statement_metrics(statements).values
        revenue_metric = values["revenue"]
        revenue = _number(revenue_metric)
        period_end = revenue_metric.period_end or _period_end(values)
        if revenue is None or revenue <= 0 or period_end is None:
            continue
        ebit = _number(values.get("ebit"))
        net_income = _number(values.get("net_income"))
        tax_rate = _number(values.get("tax_rate"))
        fcff = _number(values.get("fcff"))
        nopat = _number(values.get("nopat"))
        confidence_metrics = [
            metric
            for metric in (
                revenue_metric,
                values.get("ebit"),
                values.get("net_income"),
                values.get("fcff"),
            )
            if metric is not None and metric.is_available
        ]
        confidence = mean(metric.confidence for metric in confidence_metrics) if confidence_metrics else 0.0
        fcff_metric = values.get("fcff")
        period = CyclicalPeriod(
            period_end=period_end,
            revenue=revenue,
            operating_margin=_ratio(ebit, revenue),
            net_margin=_ratio(net_income, revenue),
            tax_rate=tax_rate,
            fcff_margin=_ratio(fcff, revenue),
            reinvestment_margin=(
                _ratio(nopat - fcff, revenue)
                if nopat is not None and fcff is not None
                else None
            ),
            confidence=confidence,
            fcff_uses_nwc_fallback=bool(
                fcff_metric
                and fcff_metric.formula
                and "nwc_fallback" in fcff_metric.formula
            ),
            source_document=revenue_metric.source_document or statements.source,
        )
        by_period[period_end] = period
    ordered = tuple(sorted(by_period.values(), key=lambda item: item.period_end))
    if len(ordered) > assumptions.maximum_years:
        ordered = ordered[-assumptions.maximum_years :]
    if ordered:
        expected_span = ordered[-1].period_end.year - ordered[0].period_end.year + 1
        if expected_span > len(ordered) + 1:
            warnings.append("O historico anual possui lacunas relevantes dentro da janela do ciclo.")
    return ordered, tuple(warnings)


def _normalization_confidence(
    periods: tuple[CyclicalPeriod, ...],
    minimum_count: int,
    crosscheck_gap: float,
    assumptions: CyclicalNormalizationAssumptions,
) -> float:
    coverage = min(1.0, minimum_count / assumptions.target_years)
    span = (
        periods[-1].period_end.year - periods[0].period_end.year + 1
        if periods
        else 0
    )
    span_score = min(1.0, span / assumptions.target_years)
    source_score = mean(period.confidence for period in periods) if periods else 0.0
    fallback_ratio = (
        sum(period.fcff_uses_nwc_fallback for period in periods) / len(periods)
        if periods
        else 1.0
    )
    crosscheck_penalty = min(
        0.15,
        max(0.0, crosscheck_gap - assumptions.maximum_fcff_crosscheck_gap),
    )
    return clamp(
        0.40 * coverage
        + 0.20 * span_score
        + 0.40 * source_score
        - assumptions.nwc_fallback_confidence_penalty * fallback_ratio
        - crosscheck_penalty,
        0.0,
        1.0,
    )


def _bounded_robust_mean(
    values: list[float | None],
    bounds: tuple[float, float],
    assumptions: CyclicalNormalizationAssumptions,
) -> float:
    available = [clamp(float(value), bounds[0], bounds[1]) for value in values if value is not None]
    ordered = sorted(available)
    lower = _percentile(ordered, assumptions.winsor_tail_fraction)
    upper = _percentile(ordered, 1.0 - assumptions.winsor_tail_fraction)
    return mean(clamp(value, lower, upper) for value in ordered)


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("Serie vazia")
    if len(values) == 1:
        return values[0]
    position = clamp(probability, 0.0, 1.0) * (len(values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _cycle_position(
    current_margin: float | None,
    history: list[float | None],
    normalized_margin: float,
    assumptions: CyclicalNormalizationAssumptions,
) -> str:
    available = sorted(float(value) for value in history if value is not None)
    if current_margin is None or not available:
        return "indeterminada"
    lower = _percentile(available, 0.25)
    upper = _percentile(available, 0.75)
    gap = assumptions.cycle_position_margin_gap
    if current_margin >= upper and current_margin >= normalized_margin + gap:
        return "acima_do_meio_do_ciclo"
    if current_margin <= lower and current_margin <= normalized_margin - gap:
        return "abaixo_do_meio_do_ciclo"
    return "proximo_do_meio_do_ciclo"


def _lineage(
    periods: tuple[CyclicalPeriod, ...],
    current_values: Mapping[str, MetricValue],
    confidence: float,
) -> dict[str, object]:
    revenue = current_values.get("revenue", MetricValue("revenue", None, "missing", 0.0))
    start = periods[0].period_end if periods else None
    end = periods[-1].period_end if periods else None
    documents = list(dict.fromkeys(period.source_document for period in periods if period.source_document))
    return {
        "confidence": confidence,
        "source_url": revenue.source_url,
        "source_document": (
            f"Normalizacao de {len(periods)} demonstracoes anuais ({start} a {end}); "
            + "; ".join(documents[:3])
        ),
        "period_start": start,
        "period_end": end,
        "filing_date": max(
            (
                metric.filing_date
                for metric in current_values.values()
                if metric.filing_date is not None
            ),
            default=None,
        ),
        "as_of": revenue.as_of,
        "currency": revenue.currency,
    }


def _normalized_metric(
    name: str,
    value: float | None,
    note: str,
    formula: str,
    lineage: Mapping[str, object],
) -> MetricValue:
    return metric_value(
        name,
        value,
        "cyclical_normalization",
        note,
        source_url=lineage.get("source_url"),
        source_document=lineage.get("source_document"),
        period_start=lineage.get("period_start"),
        period_end=lineage.get("period_end"),
        filing_date=lineage.get("filing_date"),
        as_of=lineage.get("as_of"),
        currency=lineage.get("currency"),
        scale="raw",
        basis="normalized",
        formula=formula,
        confidence=float(lineage.get("confidence") or 0.0),
    )


def _disabled_metric(metric: MetricValue) -> MetricValue:
    return MetricValue(
        metric.name,
        None,
        "missing",
        0.0,
        "Normalizacao calculada, mas nao aplicada por baixa confianca.",
        basis="normalized",
        formula=metric.formula,
    )


def _unavailable_result(
    is_cyclical: bool,
    status: str,
    assumptions: CyclicalNormalizationAssumptions,
    *,
    periods: tuple[CyclicalPeriod, ...] = (),
    warnings: Iterable[str] = (),
    current_values: Mapping[str, MetricValue] | None = None,
) -> CyclicalNormalizationResult:
    def missing(name: str) -> MetricValue:
        return MetricValue(name, None, "missing", 0.0, basis="normalized")
    current_values = current_values or {}
    revenue = _number(current_values.get("revenue"))
    return CyclicalNormalizationResult(
        is_cyclical=is_cyclical,
        applied=False,
        status=status,
        periods=periods,
        confidence=0.0,
        cycle_position="indeterminada",
        normalized_operating_margin=None,
        normalized_net_margin=None,
        normalized_tax_rate=None,
        normalized_fcff_margin=None,
        normalized_reinvestment_margin=None,
        current_operating_margin=_ratio(_number(current_values.get("ebit")), revenue),
        current_net_margin=_ratio(_number(current_values.get("net_income")), revenue),
        current_fcff_margin=_ratio(_number(current_values.get("fcff")), revenue),
        normalized_ebit=missing("normalized_ebit"),
        normalized_nopat=missing("normalized_nopat"),
        normalized_net_income=missing("normalized_net_income"),
        normalized_reinvestment=missing("normalized_reinvestment"),
        normalized_fcff=missing("normalized_fcff"),
        normalized_fcff_direct=missing("normalized_fcff_direct"),
        normalized_roic=missing("normalized_roic"),
        transition_years=assumptions.transition_years,
        warnings=tuple(warnings),
    )


def _number(metric: MetricValue | None) -> float | None:
    return float(metric.value) if metric is not None and metric.is_available else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def _period_end(values: Mapping[str, MetricValue]) -> date | None:
    dates = [metric.period_end for metric in values.values() if metric.period_end is not None]
    return max(dates, default=None)


__all__ = [
    "CyclicalNormalizationResult",
    "CyclicalPeriod",
    "build_cyclical_periods",
    "is_cyclical_profile",
    "normalize_cyclical_financials",
]
