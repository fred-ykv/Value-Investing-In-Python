"""Point-in-time validation of scores against forward market outcomes."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Callable, Iterable, TypeVar

from .config import CALIBRATION, CalibrationAssumptions


_MappingValue = TypeVar("_MappingValue")


@dataclass(frozen=True)
class HistoricalScoreDimensionContribution:
    name: str
    score: float
    confidence: float
    configured_weight: float
    normalized_weight: float
    weighted_contribution: float


@dataclass(frozen=True)
class HistoricalScoreComponentAudit:
    dimension: str
    stage: str
    component: str
    raw_value: float | None
    transformed_score: float | None
    configured_weight: float
    effective_weight: float
    weighted_contribution: float
    confidence: float
    source: str
    used: bool
    reason: str = ""
    source_document: str = ""
    period_start: str = ""
    period_end: str = ""
    filing_date: str = ""
    formula: str = ""
    note: str = ""
    is_fallback: bool = False
    input_observations: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class HistoricalValuationAssumptionAudit:
    name: str
    input_value: float | None
    effective_value: float | None
    source: str
    confidence: float
    is_fallback: bool = False
    note: str = ""
    formula: str = ""


@dataclass(frozen=True)
class HistoricalValuationMethodAudit:
    method: str
    used_in_score: bool
    fair_value_per_share: float | None
    margin_of_safety: float | None
    confidence: float
    source: str
    exclusion_reason: str = ""
    enterprise_value: float | None = None
    equity_value: float | None = None
    model_outputs: tuple[tuple[str, float], ...] = ()
    assumptions: tuple[HistoricalValuationAssumptionAudit, ...] = ()


@dataclass(frozen=True)
class HistoricalCalibrationObservation:
    ticker: str
    as_of: date
    company_type: str
    total_score: float
    recommendation: str
    data_confidence: float
    forward_return: float | None
    benchmark_return: float | None
    max_drawdown: float | None
    point_in_time_validated: bool
    latest_filing_date: date | None = None
    benchmark_ticker: str = ""
    price_start_date: date | None = None
    price_end_date: date | None = None
    price_source: str = ""
    filing_accession: str = ""
    fundamental_coverage: float = 0.0
    risk_free_rate: float | None = None
    risk_free_rate_date: date | None = None
    equity_risk_premium: float | None = None
    erp_reference_year: int | None = None
    erp_available_date: date | None = None
    macro_point_in_time_validated: bool = False
    discount_rate: float | None = None
    discount_rate_label: str = ""
    wacc: float | None = None
    cost_of_equity: float | None = None
    cost_of_capital_method: str = ""
    cost_of_capital_confidence: float | None = None
    cost_of_capital_is_fallback: bool = False
    is_cyclical: bool = False
    cyclical_normalization_applied: bool = False
    cyclical_normalization_years: int = 0
    cyclical_normalization_confidence: float | None = None
    cycle_position: str = ""
    current_fcff: float | None = None
    normalized_fcff: float | None = None
    normalized_operating_margin: float | None = None
    normalized_reinvestment_margin: float | None = None
    benchmark_group: str = ""
    sector_bucket: str = ""
    critical_metric_coverage: float = 0.0
    missing_critical_metrics: str = ""
    analysis_input_validated: bool = False
    security_cik: str = ""
    universe_status: str = "active"
    outcome_method: str = "market_price_12m"
    lifecycle_event_type: str = ""
    lifecycle_event_date: date | None = None
    stock_terminal_date: date | None = None
    terminal_value_per_share: float | None = None
    lifecycle_source_url: str = ""
    dimension_valuation_score: float | None = None
    dimension_valuation_confidence: float | None = None
    dimension_growth_score: float | None = None
    dimension_growth_confidence: float | None = None
    dimension_quality_score: float | None = None
    dimension_quality_confidence: float | None = None
    dimension_debt_score: float | None = None
    dimension_debt_confidence: float | None = None
    dimension_liquidity_score: float | None = None
    dimension_liquidity_confidence: float | None = None
    dimension_data_confidence_score: float | None = None
    dimension_data_confidence_confidence: float | None = None
    calculated_wacc: float | None = None
    beta: float | None = None
    pre_tax_cost_of_debt: float | None = None
    after_tax_cost_of_debt: float | None = None
    tax_rate: float | None = None
    market_value_equity: float | None = None
    debt_value: float | None = None
    equity_weight: float | None = None
    debt_weight: float | None = None
    cost_of_capital_sources: tuple[tuple[str, str], ...] = ()
    cost_of_capital_component_confidences: tuple[tuple[str, float], ...] = ()
    cost_of_capital_component_fallbacks: tuple[tuple[str, bool], ...] = ()
    cost_of_capital_notes: tuple[str, ...] = ()
    valuation_price: float | None = None
    recommendation_before_gates: str = ""
    recommendation_gate_code: str = ""
    recommendation_gate_triggered: bool = False
    recommendation_gate_explanation: str = ""
    recommendation_buy_threshold: float | None = None
    recommendation_watch_threshold: float | None = None
    recommendation_min_valuation_score_for_buy: float | None = None
    recommendation_avoid_if_valuation_below: float | None = None
    recommendation_avoid_if_quality_below: float | None = None
    valuation_method_audit: tuple[HistoricalValuationMethodAudit, ...] = ()
    score_model_version: str = ""
    score_config_fingerprint: str = ""
    score_configured_weights: tuple[tuple[str, float], ...] = ()
    score_normalized_weights: tuple[tuple[str, float], ...] = ()
    score_weighted_total: float | None = None
    score_reconciliation_difference: float | None = None
    score_dimension_contributions: tuple[
        HistoricalScoreDimensionContribution, ...
    ] = ()
    score_component_audit: tuple[HistoricalScoreComponentAudit, ...] = ()

    @property
    def excess_return(self) -> float | None:
        if self.forward_return is None or self.benchmark_return is None:
            return None
        return self.forward_return - self.benchmark_return

    @property
    def has_complete_outcome(self) -> bool:
        return self.excess_return is not None and self.max_drawdown is not None

    @property
    def is_point_in_time_valid(self) -> bool:
        if not self.point_in_time_validated:
            return False
        if self.latest_filing_date is not None and self.latest_filing_date > self.as_of:
            return False
        if self.price_start_date is not None and self.price_start_date < self.as_of:
            return False
        if not self.macro_point_in_time_validated:
            return False
        macro_rates = (
            self.risk_free_rate,
            self.equity_risk_premium,
            self.discount_rate,
        )
        if any(value is None or not math.isfinite(value) for value in macro_rates):
            return False
        if self.risk_free_rate_date is None or self.risk_free_rate_date > self.as_of:
            return False
        return self.erp_available_date is not None and self.erp_available_date <= self.as_of


@dataclass(frozen=True)
class OutcomeBucketSummary:
    bucket: int
    count: int
    min_score: float
    max_score: float
    average_score: float
    average_forward_return: float
    average_excess_return: float
    excess_return_hit_rate: float
    average_max_drawdown: float
    worst_max_drawdown: float


@dataclass(frozen=True)
class HistoricalCalibrationSummary:
    observations: list[HistoricalCalibrationObservation]
    usable_observations: int
    outcome_coverage: float
    point_in_time_ratio: float
    buckets: list[OutcomeBucketSummary]
    spearman_score_to_excess_return: float
    monotonic_bucket_steps: int
    possible_monotonic_steps: int
    monotonic_bucket_ratio: float
    warnings: tuple[str, ...]
    is_ready_for_weight_changes: bool


def evaluate_historical_outcomes(
    observations: Iterable[HistoricalCalibrationObservation],
    assumptions: CalibrationAssumptions = CALIBRATION,
) -> HistoricalCalibrationSummary:
    observations = list(observations)
    complete = [observation for observation in observations if observation.has_complete_outcome]
    point_in_time = [
        observation for observation in observations if observation.is_point_in_time_valid
    ]
    usable = [observation for observation in complete if observation.is_point_in_time_valid]
    outcome_coverage = len(complete) / len(observations) if observations else 0.0
    point_in_time_ratio = len(point_in_time) / len(observations) if observations else 0.0
    buckets = _build_outcome_buckets(usable, assumptions.outcome_bucket_count)

    score_values = [observation.total_score for observation in usable]
    excess_returns = [float(observation.excess_return) for observation in usable]
    spearman = _spearman(score_values, excess_returns)
    monotonic_steps = sum(
        1
        for previous, current in zip(buckets, buckets[1:])
        if current.average_excess_return > previous.average_excess_return
    )
    possible_steps = max(0, len(buckets) - 1)
    monotonic_ratio = monotonic_steps / possible_steps if possible_steps else 0.0

    warnings: list[str] = []
    if len(observations) < assumptions.minimum_historical_observations:
        warnings.append(
            f"Historico insuficiente: {len(observations)} de "
            f"{assumptions.minimum_historical_observations} observacoes minimas."
        )
    if outcome_coverage < assumptions.minimum_outcome_coverage:
        warnings.append(
            f"Cobertura de resultados futuros de {outcome_coverage:.1%} e menor que o minimo de "
            f"{assumptions.minimum_outcome_coverage:.1%}."
        )
    if point_in_time_ratio < assumptions.minimum_point_in_time_ratio:
        warnings.append(
            f"Validacao point-in-time de {point_in_time_ratio:.1%} e menor que o minimo de "
            f"{assumptions.minimum_point_in_time_ratio:.1%}."
        )
    if len(buckets) < assumptions.outcome_bucket_count:
        warnings.append(
            f"Amostra util nao suporta {assumptions.outcome_bucket_count} faixas de score."
        )
    if spearman < assumptions.minimum_spearman_correlation:
        warnings.append(
            f"Correlacao de Spearman entre score e retorno excedente ({spearman:.3f}) e menor que "
            f"{assumptions.minimum_spearman_correlation:.3f}."
        )
    if monotonic_ratio < assumptions.minimum_monotonic_bucket_ratio:
        warnings.append(
            f"Monotonicidade entre faixas de score ({monotonic_ratio:.1%}) e menor que "
            f"{assumptions.minimum_monotonic_bucket_ratio:.1%}."
        )

    return HistoricalCalibrationSummary(
        observations=observations,
        usable_observations=len(usable),
        outcome_coverage=outcome_coverage,
        point_in_time_ratio=point_in_time_ratio,
        buckets=buckets,
        spearman_score_to_excess_return=spearman,
        monotonic_bucket_steps=monotonic_steps,
        possible_monotonic_steps=possible_steps,
        monotonic_bucket_ratio=monotonic_ratio,
        warnings=tuple(warnings),
        is_ready_for_weight_changes=not warnings,
    )


def _build_outcome_buckets(
    observations: list[HistoricalCalibrationObservation],
    bucket_count: int,
) -> list[OutcomeBucketSummary]:
    if not observations or bucket_count <= 0:
        return []
    ordered = sorted(observations, key=lambda observation: observation.total_score)
    tied_scores: list[list[HistoricalCalibrationObservation]] = []
    for observation in ordered:
        if not tied_scores or tied_scores[-1][0].total_score != observation.total_score:
            tied_scores.append([])
        tied_scores[-1].append(observation)
    actual_bucket_count = min(bucket_count, len(tied_scores))
    grouped: list[list[HistoricalCalibrationObservation]] = [
        [] for _ in range(actual_bucket_count)
    ]
    for index, tied_group in enumerate(tied_scores):
        bucket_index = min(
            (index * actual_bucket_count) // len(tied_scores),
            actual_bucket_count - 1,
        )
        grouped[bucket_index].extend(tied_group)

    summaries: list[OutcomeBucketSummary] = []
    for index, bucket in enumerate(grouped, start=1):
        scores = [observation.total_score for observation in bucket]
        forward_returns = [float(observation.forward_return) for observation in bucket]
        excess_returns = [float(observation.excess_return) for observation in bucket]
        drawdowns = [float(observation.max_drawdown) for observation in bucket]
        summaries.append(
            OutcomeBucketSummary(
                bucket=index,
                count=len(bucket),
                min_score=min(scores),
                max_score=max(scores),
                average_score=mean(scores),
                average_forward_return=mean(forward_returns),
                average_excess_return=mean(excess_returns),
                excess_return_hit_rate=sum(value > 0.0 for value in excess_returns) / len(bucket),
                average_max_drawdown=mean(drawdowns),
                worst_max_drawdown=min(drawdowns),
            )
        )
    return summaries


def _spearman(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks(right)
    left_mean = mean(left_ranks)
    right_mean = mean(right_ranks)
    numerator = sum(
        (left_rank - left_mean) * (right_rank - right_mean)
        for left_rank, right_rank in zip(left_ranks, right_ranks)
    )
    left_variance = sum((rank - left_mean) ** 2 for rank in left_ranks)
    right_variance = sum((rank - right_mean) ** 2 for rank in right_ranks)
    denominator = (left_variance * right_variance) ** 0.5
    return numerator / denominator if denominator else 0.0


def spearman_correlation(left: list[float], right: list[float]) -> float:
    """Public tie-aware Spearman helper used by segmented validation reports."""
    return _spearman(left, right)


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        average_rank = ((index + 1) + (end + 1)) / 2.0
        for ordered_index in range(index, end + 1):
            original_index = ordered[ordered_index][0]
            ranks[original_index] = average_rank
        index = end + 1
    return ranks


def write_historical_calibration_csv(
    observations: Iterable[HistoricalCalibrationObservation],
    path: str | Path,
) -> None:
    fieldnames = [
        "ticker",
        "as_of",
        "company_type",
        "total_score",
        "score_model_version",
        "score_config_fingerprint",
        "score_configured_weights",
        "score_normalized_weights",
        "score_weighted_total",
        "score_reconciliation_difference",
        "score_dimension_contributions",
        "score_component_audit",
        "recommendation",
        "recommendation_before_gates",
        "recommendation_gate_code",
        "recommendation_gate_triggered",
        "recommendation_gate_explanation",
        "recommendation_buy_threshold",
        "recommendation_watch_threshold",
        "recommendation_min_valuation_score_for_buy",
        "recommendation_avoid_if_valuation_below",
        "recommendation_avoid_if_quality_below",
        "data_confidence",
        "dimension_valuation_score",
        "dimension_valuation_confidence",
        "dimension_growth_score",
        "dimension_growth_confidence",
        "dimension_quality_score",
        "dimension_quality_confidence",
        "dimension_debt_score",
        "dimension_debt_confidence",
        "dimension_liquidity_score",
        "dimension_liquidity_confidence",
        "dimension_data_confidence_score",
        "dimension_data_confidence_confidence",
        "forward_return",
        "benchmark_return",
        "max_drawdown",
        "point_in_time_validated",
        "latest_filing_date",
        "benchmark_ticker",
        "price_start_date",
        "price_end_date",
        "valuation_price",
        "price_source",
        "filing_accession",
        "fundamental_coverage",
        "risk_free_rate",
        "risk_free_rate_date",
        "equity_risk_premium",
        "erp_reference_year",
        "erp_available_date",
        "macro_point_in_time_validated",
        "discount_rate",
        "discount_rate_label",
        "wacc",
        "calculated_wacc",
        "cost_of_equity",
        "beta",
        "pre_tax_cost_of_debt",
        "after_tax_cost_of_debt",
        "tax_rate",
        "market_value_equity",
        "debt_value",
        "equity_weight",
        "debt_weight",
        "cost_of_capital_method",
        "cost_of_capital_confidence",
        "cost_of_capital_is_fallback",
        "cost_of_capital_sources",
        "cost_of_capital_component_confidences",
        "cost_of_capital_component_fallbacks",
        "cost_of_capital_notes",
        "valuation_method_audit",
        "is_cyclical",
        "cyclical_normalization_applied",
        "cyclical_normalization_years",
        "cyclical_normalization_confidence",
        "cycle_position",
        "current_fcff",
        "normalized_fcff",
        "normalized_operating_margin",
        "normalized_reinvestment_margin",
        "benchmark_group",
        "sector_bucket",
        "critical_metric_coverage",
        "missing_critical_metrics",
        "analysis_input_validated",
        "security_cik",
        "universe_status",
        "outcome_method",
        "lifecycle_event_type",
        "lifecycle_event_date",
        "stock_terminal_date",
        "terminal_value_per_share",
        "lifecycle_source_url",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for observation in observations:
            writer.writerow(
                {
                    "ticker": observation.ticker,
                    "as_of": observation.as_of.isoformat(),
                    "company_type": observation.company_type,
                    "total_score": f"{observation.total_score:.6f}",
                    "score_model_version": observation.score_model_version,
                    "score_config_fingerprint": (
                        observation.score_config_fingerprint
                    ),
                    "score_configured_weights": _format_mapping(
                        observation.score_configured_weights
                    ),
                    "score_normalized_weights": _format_mapping(
                        observation.score_normalized_weights
                    ),
                    "score_weighted_total": _format_optional(
                        observation.score_weighted_total
                    ),
                    "score_reconciliation_difference": _format_optional(
                        observation.score_reconciliation_difference
                    ),
                    "score_dimension_contributions": (
                        _format_score_dimension_contributions(
                            observation.score_dimension_contributions
                        )
                    ),
                    "score_component_audit": _format_score_component_audit(
                        observation.score_component_audit
                    ),
                    "recommendation": observation.recommendation,
                    "recommendation_before_gates": (
                        observation.recommendation_before_gates
                    ),
                    "recommendation_gate_code": observation.recommendation_gate_code,
                    "recommendation_gate_triggered": (
                        "1" if observation.recommendation_gate_triggered else "0"
                    ),
                    "recommendation_gate_explanation": (
                        observation.recommendation_gate_explanation
                    ),
                    "recommendation_buy_threshold": _format_optional(
                        observation.recommendation_buy_threshold
                    ),
                    "recommendation_watch_threshold": _format_optional(
                        observation.recommendation_watch_threshold
                    ),
                    "recommendation_min_valuation_score_for_buy": _format_optional(
                        observation.recommendation_min_valuation_score_for_buy
                    ),
                    "recommendation_avoid_if_valuation_below": _format_optional(
                        observation.recommendation_avoid_if_valuation_below
                    ),
                    "recommendation_avoid_if_quality_below": _format_optional(
                        observation.recommendation_avoid_if_quality_below
                    ),
                    "data_confidence": f"{observation.data_confidence:.6f}",
                    "dimension_valuation_score": _format_optional(
                        observation.dimension_valuation_score
                    ),
                    "dimension_valuation_confidence": _format_optional(
                        observation.dimension_valuation_confidence
                    ),
                    "dimension_growth_score": _format_optional(
                        observation.dimension_growth_score
                    ),
                    "dimension_growth_confidence": _format_optional(
                        observation.dimension_growth_confidence
                    ),
                    "dimension_quality_score": _format_optional(
                        observation.dimension_quality_score
                    ),
                    "dimension_quality_confidence": _format_optional(
                        observation.dimension_quality_confidence
                    ),
                    "dimension_debt_score": _format_optional(
                        observation.dimension_debt_score
                    ),
                    "dimension_debt_confidence": _format_optional(
                        observation.dimension_debt_confidence
                    ),
                    "dimension_liquidity_score": _format_optional(
                        observation.dimension_liquidity_score
                    ),
                    "dimension_liquidity_confidence": _format_optional(
                        observation.dimension_liquidity_confidence
                    ),
                    "dimension_data_confidence_score": _format_optional(
                        observation.dimension_data_confidence_score
                    ),
                    "dimension_data_confidence_confidence": _format_optional(
                        observation.dimension_data_confidence_confidence
                    ),
                    "forward_return": _format_optional(observation.forward_return),
                    "benchmark_return": _format_optional(observation.benchmark_return),
                    "max_drawdown": _format_optional(observation.max_drawdown),
                    "point_in_time_validated": "1" if observation.point_in_time_validated else "0",
                    "latest_filing_date": (
                        observation.latest_filing_date.isoformat()
                        if observation.latest_filing_date is not None
                        else ""
                    ),
                    "benchmark_ticker": observation.benchmark_ticker,
                    "price_start_date": (
                        observation.price_start_date.isoformat()
                        if observation.price_start_date is not None
                        else ""
                    ),
                    "price_end_date": (
                        observation.price_end_date.isoformat()
                        if observation.price_end_date is not None
                        else ""
                    ),
                    "valuation_price": _format_optional(observation.valuation_price),
                    "price_source": observation.price_source,
                    "filing_accession": observation.filing_accession,
                    "fundamental_coverage": f"{observation.fundamental_coverage:.6f}",
                    "risk_free_rate": _format_optional(observation.risk_free_rate),
                    "risk_free_rate_date": (
                        observation.risk_free_rate_date.isoformat()
                        if observation.risk_free_rate_date is not None
                        else ""
                    ),
                    "equity_risk_premium": _format_optional(
                        observation.equity_risk_premium
                    ),
                    "erp_reference_year": observation.erp_reference_year or "",
                    "erp_available_date": (
                        observation.erp_available_date.isoformat()
                        if observation.erp_available_date is not None
                        else ""
                    ),
                    "macro_point_in_time_validated": (
                        "1" if observation.macro_point_in_time_validated else "0"
                    ),
                    "discount_rate": _format_optional(observation.discount_rate),
                    "discount_rate_label": observation.discount_rate_label,
                    "wacc": _format_optional(observation.wacc),
                    "calculated_wacc": _format_optional(
                        observation.calculated_wacc
                    ),
                    "cost_of_equity": _format_optional(observation.cost_of_equity),
                    "beta": _format_optional(observation.beta),
                    "pre_tax_cost_of_debt": _format_optional(
                        observation.pre_tax_cost_of_debt
                    ),
                    "after_tax_cost_of_debt": _format_optional(
                        observation.after_tax_cost_of_debt
                    ),
                    "tax_rate": _format_optional(observation.tax_rate),
                    "market_value_equity": _format_optional(
                        observation.market_value_equity
                    ),
                    "debt_value": _format_optional(observation.debt_value),
                    "equity_weight": _format_optional(observation.equity_weight),
                    "debt_weight": _format_optional(observation.debt_weight),
                    "cost_of_capital_method": observation.cost_of_capital_method,
                    "cost_of_capital_confidence": _format_optional(
                        observation.cost_of_capital_confidence
                    ),
                    "cost_of_capital_is_fallback": (
                        "1" if observation.cost_of_capital_is_fallback else "0"
                    ),
                    "cost_of_capital_sources": _format_mapping(
                        observation.cost_of_capital_sources
                    ),
                    "cost_of_capital_component_confidences": _format_mapping(
                        observation.cost_of_capital_component_confidences
                    ),
                    "cost_of_capital_component_fallbacks": _format_mapping(
                        observation.cost_of_capital_component_fallbacks
                    ),
                    "cost_of_capital_notes": json.dumps(
                        observation.cost_of_capital_notes,
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                    "valuation_method_audit": _format_valuation_method_audit(
                        observation.valuation_method_audit
                    ),
                    "is_cyclical": "1" if observation.is_cyclical else "0",
                    "cyclical_normalization_applied": (
                        "1" if observation.cyclical_normalization_applied else "0"
                    ),
                    "cyclical_normalization_years": observation.cyclical_normalization_years,
                    "cyclical_normalization_confidence": _format_optional(
                        observation.cyclical_normalization_confidence
                    ),
                    "cycle_position": observation.cycle_position,
                    "current_fcff": _format_optional(observation.current_fcff),
                    "normalized_fcff": _format_optional(observation.normalized_fcff),
                    "normalized_operating_margin": _format_optional(
                        observation.normalized_operating_margin
                    ),
                    "normalized_reinvestment_margin": _format_optional(
                        observation.normalized_reinvestment_margin
                    ),
                    "benchmark_group": observation.benchmark_group,
                    "sector_bucket": observation.sector_bucket,
                    "critical_metric_coverage": f"{observation.critical_metric_coverage:.6f}",
                    "missing_critical_metrics": observation.missing_critical_metrics,
                    "analysis_input_validated": (
                        "1" if observation.analysis_input_validated else "0"
                    ),
                    "security_cik": observation.security_cik,
                    "universe_status": observation.universe_status,
                    "outcome_method": observation.outcome_method,
                    "lifecycle_event_type": observation.lifecycle_event_type,
                    "lifecycle_event_date": (
                        observation.lifecycle_event_date.isoformat()
                        if observation.lifecycle_event_date is not None
                        else ""
                    ),
                    "stock_terminal_date": (
                        observation.stock_terminal_date.isoformat()
                        if observation.stock_terminal_date is not None
                        else ""
                    ),
                    "terminal_value_per_share": _format_optional(
                        observation.terminal_value_per_share
                    ),
                    "lifecycle_source_url": observation.lifecycle_source_url,
                }
            )


def read_historical_calibration_csv(path: str | Path) -> list[HistoricalCalibrationObservation]:
    observations: list[HistoricalCalibrationObservation] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            filing_date = row.get("latest_filing_date", "").strip()
            price_start_date = row.get("price_start_date", "").strip()
            price_end_date = row.get("price_end_date", "").strip()
            risk_free_rate_date = row.get("risk_free_rate_date", "").strip()
            erp_reference_year = row.get("erp_reference_year", "").strip()
            erp_available_date = row.get("erp_available_date", "").strip()
            lifecycle_event_date = row.get("lifecycle_event_date", "").strip()
            stock_terminal_date = row.get("stock_terminal_date", "").strip()
            legacy_data_confidence = float(row["data_confidence"])
            dimension_data_confidence_score = _parse_optional_float(
                row.get("dimension_data_confidence_score", "")
            )
            dimension_data_confidence_confidence = _parse_optional_float(
                row.get("dimension_data_confidence_confidence", "")
            )
            observations.append(
                HistoricalCalibrationObservation(
                    ticker=row["ticker"].upper().strip(),
                    as_of=date.fromisoformat(row["as_of"]),
                    company_type=row["company_type"],
                    total_score=float(row["total_score"]),
                    score_model_version=row.get(
                        "score_model_version", ""
                    ).strip(),
                    score_config_fingerprint=row.get(
                        "score_config_fingerprint", ""
                    ).strip(),
                    score_configured_weights=_parse_mapping(
                        row.get("score_configured_weights", ""),
                        float,
                    ),
                    score_normalized_weights=_parse_mapping(
                        row.get("score_normalized_weights", ""),
                        float,
                    ),
                    score_weighted_total=_parse_optional_float(
                        row.get("score_weighted_total", "")
                    ),
                    score_reconciliation_difference=_parse_optional_float(
                        row.get("score_reconciliation_difference", "")
                    ),
                    score_dimension_contributions=(
                        _parse_score_dimension_contributions(
                            row.get("score_dimension_contributions", "")
                        )
                    ),
                    score_component_audit=_parse_score_component_audit(
                        row.get("score_component_audit", "")
                    ),
                    recommendation=row["recommendation"],
                    recommendation_before_gates=row.get(
                        "recommendation_before_gates", ""
                    ).strip(),
                    recommendation_gate_code=row.get(
                        "recommendation_gate_code", ""
                    ).strip(),
                    recommendation_gate_triggered=_parse_bool(
                        row.get("recommendation_gate_triggered", "")
                    ),
                    recommendation_gate_explanation=row.get(
                        "recommendation_gate_explanation", ""
                    ).strip(),
                    recommendation_buy_threshold=_parse_optional_float(
                        row.get("recommendation_buy_threshold", "")
                    ),
                    recommendation_watch_threshold=_parse_optional_float(
                        row.get("recommendation_watch_threshold", "")
                    ),
                    recommendation_min_valuation_score_for_buy=_parse_optional_float(
                        row.get("recommendation_min_valuation_score_for_buy", "")
                    ),
                    recommendation_avoid_if_valuation_below=_parse_optional_float(
                        row.get("recommendation_avoid_if_valuation_below", "")
                    ),
                    recommendation_avoid_if_quality_below=_parse_optional_float(
                        row.get("recommendation_avoid_if_quality_below", "")
                    ),
                    data_confidence=legacy_data_confidence,
                    forward_return=_parse_optional_float(row.get("forward_return", "")),
                    benchmark_return=_parse_optional_float(row.get("benchmark_return", "")),
                    max_drawdown=_parse_optional_float(row.get("max_drawdown", "")),
                    point_in_time_validated=row.get("point_in_time_validated", "").lower()
                    in {"1", "true", "sim", "yes"},
                    latest_filing_date=date.fromisoformat(filing_date) if filing_date else None,
                    benchmark_ticker=row.get("benchmark_ticker", "").upper().strip(),
                    price_start_date=date.fromisoformat(price_start_date) if price_start_date else None,
                    price_end_date=date.fromisoformat(price_end_date) if price_end_date else None,
                    valuation_price=_parse_optional_float(
                        row.get("valuation_price", "")
                    ),
                    price_source=row.get("price_source", "").strip(),
                    filing_accession=row.get("filing_accession", "").strip(),
                    fundamental_coverage=float(row.get("fundamental_coverage", "0") or 0.0),
                    risk_free_rate=_parse_optional_float(row.get("risk_free_rate", "")),
                    risk_free_rate_date=(
                        date.fromisoformat(risk_free_rate_date)
                        if risk_free_rate_date
                        else None
                    ),
                    equity_risk_premium=_parse_optional_float(
                        row.get("equity_risk_premium", "")
                    ),
                    erp_reference_year=(
                        int(erp_reference_year) if erp_reference_year else None
                    ),
                    erp_available_date=(
                        date.fromisoformat(erp_available_date)
                        if erp_available_date
                        else None
                    ),
                    macro_point_in_time_validated=(
                        row.get("macro_point_in_time_validated", "").lower()
                        in {"1", "true", "sim", "yes"}
                    ),
                    discount_rate=_parse_optional_float(row.get("discount_rate", "")),
                    discount_rate_label=row.get("discount_rate_label", "").strip(),
                    wacc=_parse_optional_float(row.get("wacc", "")),
                    calculated_wacc=_parse_optional_float(
                        row.get("calculated_wacc", "")
                    ),
                    cost_of_equity=_parse_optional_float(row.get("cost_of_equity", "")),
                    beta=_parse_optional_float(row.get("beta", "")),
                    pre_tax_cost_of_debt=_parse_optional_float(
                        row.get("pre_tax_cost_of_debt", "")
                    ),
                    after_tax_cost_of_debt=_parse_optional_float(
                        row.get("after_tax_cost_of_debt", "")
                    ),
                    tax_rate=_parse_optional_float(row.get("tax_rate", "")),
                    market_value_equity=_parse_optional_float(
                        row.get("market_value_equity", "")
                    ),
                    debt_value=_parse_optional_float(row.get("debt_value", "")),
                    equity_weight=_parse_optional_float(
                        row.get("equity_weight", "")
                    ),
                    debt_weight=_parse_optional_float(row.get("debt_weight", "")),
                    cost_of_capital_method=row.get("cost_of_capital_method", "").strip(),
                    cost_of_capital_confidence=_parse_optional_float(
                        row.get("cost_of_capital_confidence", "")
                    ),
                    cost_of_capital_is_fallback=(
                        row.get("cost_of_capital_is_fallback", "").lower()
                        in {"1", "true", "sim", "yes"}
                    ),
                    cost_of_capital_sources=_parse_mapping(
                        row.get("cost_of_capital_sources", ""),
                        str,
                    ),
                    cost_of_capital_component_confidences=_parse_mapping(
                        row.get("cost_of_capital_component_confidences", ""),
                        float,
                    ),
                    cost_of_capital_component_fallbacks=_parse_mapping(
                        row.get("cost_of_capital_component_fallbacks", ""),
                        _parse_bool,
                    ),
                    cost_of_capital_notes=_parse_string_sequence(
                        row.get("cost_of_capital_notes", "")
                    ),
                    valuation_method_audit=_parse_valuation_method_audit(
                        row.get("valuation_method_audit", "")
                    ),
                    is_cyclical=(
                        row.get("is_cyclical", "").lower()
                        in {"1", "true", "sim", "yes"}
                    ),
                    cyclical_normalization_applied=(
                        row.get("cyclical_normalization_applied", "").lower()
                        in {"1", "true", "sim", "yes"}
                    ),
                    cyclical_normalization_years=int(
                        row.get("cyclical_normalization_years", "0") or 0
                    ),
                    cyclical_normalization_confidence=_parse_optional_float(
                        row.get("cyclical_normalization_confidence", "")
                    ),
                    cycle_position=row.get("cycle_position", "").strip(),
                    current_fcff=_parse_optional_float(row.get("current_fcff", "")),
                    normalized_fcff=_parse_optional_float(
                        row.get("normalized_fcff", "")
                    ),
                    normalized_operating_margin=_parse_optional_float(
                        row.get("normalized_operating_margin", "")
                    ),
                    normalized_reinvestment_margin=_parse_optional_float(
                        row.get("normalized_reinvestment_margin", "")
                    ),
                    benchmark_group=row.get("benchmark_group", "").strip(),
                    sector_bucket=row.get("sector_bucket", "").strip(),
                    critical_metric_coverage=float(
                        row.get("critical_metric_coverage", "0") or 0.0
                    ),
                    missing_critical_metrics=row.get(
                        "missing_critical_metrics", ""
                    ).strip(),
                    analysis_input_validated=(
                        row.get("analysis_input_validated", "").lower()
                        in {"1", "true", "sim", "yes"}
                    ),
                    security_cik=row.get("security_cik", "").strip(),
                    universe_status=(
                        row.get("universe_status", "active").strip() or "active"
                    ),
                    outcome_method=(
                        row.get("outcome_method", "market_price_12m").strip()
                        or "market_price_12m"
                    ),
                    lifecycle_event_type=row.get(
                        "lifecycle_event_type", ""
                    ).strip(),
                    lifecycle_event_date=(
                        date.fromisoformat(lifecycle_event_date)
                        if lifecycle_event_date
                        else None
                    ),
                    stock_terminal_date=(
                        date.fromisoformat(stock_terminal_date)
                        if stock_terminal_date
                        else None
                    ),
                    terminal_value_per_share=_parse_optional_float(
                        row.get("terminal_value_per_share", "")
                    ),
                    lifecycle_source_url=row.get(
                        "lifecycle_source_url", ""
                    ).strip(),
                    dimension_valuation_score=_parse_optional_float(
                        row.get("dimension_valuation_score", "")
                    ),
                    dimension_valuation_confidence=_parse_optional_float(
                        row.get("dimension_valuation_confidence", "")
                    ),
                    dimension_growth_score=_parse_optional_float(
                        row.get("dimension_growth_score", "")
                    ),
                    dimension_growth_confidence=_parse_optional_float(
                        row.get("dimension_growth_confidence", "")
                    ),
                    dimension_quality_score=_parse_optional_float(
                        row.get("dimension_quality_score", "")
                    ),
                    dimension_quality_confidence=_parse_optional_float(
                        row.get("dimension_quality_confidence", "")
                    ),
                    dimension_debt_score=_parse_optional_float(
                        row.get("dimension_debt_score", "")
                    ),
                    dimension_debt_confidence=_parse_optional_float(
                        row.get("dimension_debt_confidence", "")
                    ),
                    dimension_liquidity_score=_parse_optional_float(
                        row.get("dimension_liquidity_score", "")
                    ),
                    dimension_liquidity_confidence=_parse_optional_float(
                        row.get("dimension_liquidity_confidence", "")
                    ),
                    dimension_data_confidence_score=(
                        dimension_data_confidence_score
                        if dimension_data_confidence_score is not None
                        else legacy_data_confidence
                    ),
                    dimension_data_confidence_confidence=(
                        dimension_data_confidence_confidence
                        if dimension_data_confidence_confidence is not None
                        else legacy_data_confidence
                    ),
                )
            )
    return observations


def render_historical_calibration_markdown(
    summary: HistoricalCalibrationSummary,
    assumptions: CalibrationAssumptions = CALIBRATION,
) -> str:
    lines = [
        "# Validacao Historica Point-in-Time",
        "",
        f"- Horizonte futuro: {assumptions.forward_horizon_months} meses",
        f"- Observacoes totais: {len(summary.observations)}",
        f"- Observacoes utilizaveis: {summary.usable_observations}",
        f"- Cobertura de resultados: {summary.outcome_coverage:.1%}",
        f"- Cobertura point-in-time: {summary.point_in_time_ratio:.1%}",
        f"- Spearman score x retorno excedente: {summary.spearman_score_to_excess_return:.3f}",
        f"- Monotonicidade das faixas: {summary.monotonic_bucket_ratio:.1%}",
        f"- Pronto para alterar pesos: {'sim' if summary.is_ready_for_weight_changes else 'nao'}",
        "",
        "## Alertas",
    ]
    if summary.warnings:
        lines.extend(f"- {warning}" for warning in summary.warnings)
    else:
        lines.append("- Nenhum alerta de validade historica.")
    lines.extend(
        [
            "",
            "## Resultado por faixa de score",
            "| Faixa | N | Score medio | Intervalo | Retorno futuro | Retorno excedente | Acerto relativo | Drawdown medio | Pior drawdown |",
            "|---:|---:|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for bucket in summary.buckets:
        lines.append(
            f"| {bucket.bucket} | {bucket.count} | {bucket.average_score:.3f} | "
            f"{bucket.min_score:.3f} a {bucket.max_score:.3f} | "
            f"{bucket.average_forward_return:.1%} | {bucket.average_excess_return:.1%} | "
            f"{bucket.excess_return_hit_rate:.1%} | {bucket.average_max_drawdown:.1%} | "
            f"{bucket.worst_max_drawdown:.1%} |"
        )
    return "\n".join(lines)


def _format_optional(value: float | None) -> str:
    return "" if value is None else f"{value:.8f}"


def _parse_optional_float(value: str | None) -> float | None:
    value = (value or "").strip()
    return float(value) if value else None


def _format_mapping(values: Iterable[tuple[str, object]]) -> str:
    return json.dumps(
        dict(values),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_mapping(
    value: str | None,
    converter: Callable[[object], _MappingValue],
) -> tuple[tuple[str, _MappingValue], ...]:
    value = (value or "").strip()
    if not value:
        return ()
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Mapeamento de custo de capital invalido no CSV")
    return tuple(
        sorted((str(key), converter(raw_value)) for key, raw_value in payload.items())
    )


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "sim", "yes"}


def _parse_string_sequence(value: str | None) -> tuple[str, ...]:
    value = (value or "").strip()
    if not value:
        return ()
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("Notas de custo de capital invalidas no CSV")
    return tuple(str(item) for item in payload)


def _format_score_dimension_contributions(
    contributions: Iterable[HistoricalScoreDimensionContribution],
) -> str:
    return json.dumps(
        [asdict(contribution) for contribution in contributions],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_score_dimension_contributions(
    value: str | None,
) -> tuple[HistoricalScoreDimensionContribution, ...]:
    value = (value or "").strip()
    if not value:
        return ()
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("Contribuicoes dimensionais do score invalidas no CSV")
    contributions: list[HistoricalScoreDimensionContribution] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Contribuicao dimensional do score invalida no CSV")
        contributions.append(
            HistoricalScoreDimensionContribution(
                name=str(item.get("name", "")).strip(),
                score=float(item.get("score", 0.0) or 0.0),
                confidence=float(item.get("confidence", 0.0) or 0.0),
                configured_weight=float(
                    item.get("configured_weight", 0.0) or 0.0
                ),
                normalized_weight=float(
                    item.get("normalized_weight", 0.0) or 0.0
                ),
                weighted_contribution=float(
                    item.get("weighted_contribution", 0.0) or 0.0
                ),
            )
        )
    return tuple(contributions)


def _format_score_component_audit(
    components: Iterable[HistoricalScoreComponentAudit],
) -> str:
    return json.dumps(
        [asdict(component) for component in components],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_score_component_audit(
    value: str | None,
) -> tuple[HistoricalScoreComponentAudit, ...]:
    value = (value or "").strip()
    if not value:
        return ()
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("Auditoria dos componentes do score invalida no CSV")
    components: list[HistoricalScoreComponentAudit] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Componente do score invalido no CSV")
        components.append(
            HistoricalScoreComponentAudit(
                dimension=str(item.get("dimension", "")).strip(),
                stage=str(item.get("stage", "")).strip(),
                component=str(item.get("component", "")).strip(),
                raw_value=_parse_optional_number(item.get("raw_value")),
                transformed_score=_parse_optional_number(
                    item.get("transformed_score")
                ),
                configured_weight=float(
                    item.get("configured_weight", 0.0) or 0.0
                ),
                effective_weight=float(
                    item.get("effective_weight", 0.0) or 0.0
                ),
                weighted_contribution=float(
                    item.get("weighted_contribution", 0.0) or 0.0
                ),
                confidence=float(item.get("confidence", 0.0) or 0.0),
                source=str(item.get("source", "")).strip(),
                used=_parse_bool(item.get("used", False)),
                reason=str(item.get("reason", "")).strip(),
                source_document=str(item.get("source_document", "")).strip(),
                period_start=str(item.get("period_start", "")).strip(),
                period_end=str(item.get("period_end", "")).strip(),
                filing_date=str(item.get("filing_date", "")).strip(),
                formula=str(item.get("formula", "")).strip(),
                note=str(item.get("note", "")).strip(),
                is_fallback=_parse_bool(item.get("is_fallback", False)),
                input_observations=_parse_numeric_pairs(
                    item.get("input_observations", [])
                ),
            )
        )
    return tuple(components)


def _format_valuation_method_audit(
    methods: Iterable[HistoricalValuationMethodAudit],
) -> str:
    return json.dumps(
        [asdict(method) for method in methods],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_valuation_method_audit(
    value: str | None,
) -> tuple[HistoricalValuationMethodAudit, ...]:
    value = (value or "").strip()
    if not value:
        return ()
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError("Auditoria dos metodos de valuation invalida no CSV")
    methods: list[HistoricalValuationMethodAudit] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Metodo de valuation invalido no CSV")
        methods.append(
            HistoricalValuationMethodAudit(
                method=str(item.get("method", "")).strip(),
                used_in_score=_parse_bool(item.get("used_in_score", False)),
                fair_value_per_share=_parse_optional_number(
                    item.get("fair_value_per_share")
                ),
                margin_of_safety=_parse_optional_number(
                    item.get("margin_of_safety")
                ),
                confidence=float(item.get("confidence", 0.0) or 0.0),
                source=str(item.get("source", "")).strip(),
                exclusion_reason=str(item.get("exclusion_reason", "")).strip(),
                enterprise_value=_parse_optional_number(
                    item.get("enterprise_value")
                ),
                equity_value=_parse_optional_number(item.get("equity_value")),
                model_outputs=_parse_numeric_pairs(item.get("model_outputs", [])),
                assumptions=_parse_valuation_assumptions(
                    item.get("assumptions", [])
                ),
            )
        )
    return tuple(methods)


def _parse_optional_number(value: object) -> float | None:
    return None if value is None or value == "" else float(value)


def _parse_numeric_pairs(value: object) -> tuple[tuple[str, float], ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise ValueError("Saidas intermediarias de valuation invalidas no CSV")
    pairs: list[tuple[str, float]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("Saida intermediaria de valuation invalida no CSV")
        pairs.append((str(item[0]), float(item[1])))
    return tuple(pairs)


def _parse_valuation_assumptions(
    value: object,
) -> tuple[HistoricalValuationAssumptionAudit, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise ValueError("Premissas de valuation invalidas no CSV")
    assumptions: list[HistoricalValuationAssumptionAudit] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Premissa de valuation invalida no CSV")
        assumptions.append(
            HistoricalValuationAssumptionAudit(
                name=str(item.get("name", "")).strip(),
                input_value=_parse_optional_number(item.get("input_value")),
                effective_value=_parse_optional_number(
                    item.get("effective_value")
                ),
                source=str(item.get("source", "")).strip(),
                confidence=float(item.get("confidence", 0.0) or 0.0),
                is_fallback=_parse_bool(item.get("is_fallback", False)),
                note=str(item.get("note", "")).strip(),
                formula=str(item.get("formula", "")).strip(),
            )
        )
    return tuple(assumptions)
