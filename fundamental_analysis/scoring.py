"""Multifactor scoring with reduced valuation double counting."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .config import CompanyType, SCORE, VALUATION_SCORE
from .data_sources import MetricValue
from .metrics import MetricPack
from .valuation import ValuationResult


@dataclass
class DimensionScore:
    name: str
    score: float
    confidence: float
    explanation: str


@dataclass
class ScoreReport:
    total_score: float
    recommendation: str
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)
    explanation: str = ""


def compute_score(company_type: CompanyType, valuations: Iterable[ValuationResult], metrics: MetricPack, current_price: MetricValue) -> ScoreReport:
    weights = SCORE.weights_by_type[company_type].normalized()
    valuations = list(valuations)
    dimensions = {
        "valuation": valuation_dimension(valuations, metrics, company_type),
        "growth": growth_dimension(metrics),
        "quality": quality_dimension(metrics),
        "debt": debt_dimension(metrics, company_type),
        "liquidity": liquidity_dimension(metrics, company_type),
        "data_confidence": data_confidence_dimension(valuations, metrics),
    }
    total = sum([
        dimensions["valuation"].score * weights.valuation,
        dimensions["growth"].score * weights.growth,
        dimensions["quality"].score * weights.quality,
        dimensions["debt"].score * weights.debt,
        dimensions["liquidity"].score * weights.liquidity,
        dimensions["data_confidence"].score * weights.data_confidence,
    ])
    recommendation = recommendation_from_score(total, dimensions)
    return ScoreReport(total, recommendation, dimensions, explain_score(recommendation, dimensions))


def valuation_dimension(valuations: Iterable[ValuationResult], metrics: MetricPack | None = None, company_type: CompanyType = CompanyType.TRADITIONAL) -> DimensionScore:
    available = [v for v in valuations if v.margin_of_safety is not None and v.confidence > 0]
    if not available:
        return financial_valuation_dimension(metrics, None, 0.0) if company_type == CompanyType.FINANCIAL and metrics else DimensionScore("valuation", 0.0, 0.0, "No reliable valuation model available.")
    weighted = [(_score_margin_of_safety(v.margin_of_safety), min(v.confidence, SCORE.max_single_valuation_method_weight)) for v in available]
    total_weight = sum(weight for _, weight in weighted)
    score = sum(value * weight for value, weight in weighted) / total_weight if total_weight else 0.0
    confidence = min(1.0, total_weight / max(1, len(available)))
    return financial_valuation_dimension(metrics, score, confidence) if company_type == CompanyType.FINANCIAL and metrics else DimensionScore("valuation", score, confidence, "Upside/margin of safety across capped valuation models.")


def financial_valuation_dimension(metrics: MetricPack, model_score: float | None, model_confidence: float) -> DimensionScore:
    pieces: list[tuple[float, float]] = []
    if model_score is not None:
        pieces.append((model_score, VALUATION_SCORE.bank_model_weight))
    pb, roe = metrics.get("price_to_book"), metrics.get("roe")
    if pb is not None:
        pieces.append((1.0 - _normalize(pb, 0.7, 2.8), VALUATION_SCORE.bank_price_to_book_weight))
    if roe is not None:
        pieces.append((_normalize(roe, 0.08, 0.18), VALUATION_SCORE.bank_roe_weight))
    if pb not in (None, 0) and roe is not None:
        justified_pb = _justified_bank_price_to_book(roe)
        relative_margin = (justified_pb / pb) - 1.0
        pieces.append((_score_margin_of_safety(relative_margin), VALUATION_SCORE.bank_justified_price_to_book_weight))
    if not pieces:
        return DimensionScore("valuation", 0.0, 0.0, "No reliable bank valuation metrics available.")
    total_weight = sum(weight for _, weight in pieces)
    return DimensionScore("valuation", sum(value * weight for value, weight in pieces) / total_weight, max(model_confidence, metrics.confidence() * 0.80), "Bank valuation blends RI/DDM margin, P/B, and ROE strength.")


def growth_dimension(metrics: MetricPack) -> DimensionScore:
    return DimensionScore("growth", _average([_metric_score(metrics.values.get("revenue_growth"), -0.05, 0.25), _metric_score(metrics.values.get("fcff_growth"), -0.10, 0.20)], 0.50), metrics.confidence(), "Revenue/FCFF growth profile.")


def quality_dimension(metrics: MetricPack) -> DimensionScore:
    return DimensionScore("quality", _average([_metric_score(metrics.values.get("fama_french_profitability"), 0, 1), _metric_score(metrics.values.get("earnings_quality"), 0, 1), _metric_score(metrics.values.get("piotroski_proxy"), 0, 1)], 0.0), metrics.confidence(), "Profitability, accruals, and Piotroski-style quality.")


def debt_dimension(metrics: MetricPack, company_type: CompanyType) -> DimensionScore:
    if company_type == CompanyType.FINANCIAL:
        return DimensionScore("debt", 0.50, metrics.confidence(), "Debt ratios are less meaningful for banks; neutral score.")
    de, nd = metrics.get("debt_to_equity"), metrics.get("net_debt_to_ebit")
    return DimensionScore("debt", _average([None if de is None else 1.0 - _normalize(de, 0, 3), None if nd is None else 1.0 - _normalize(nd, 0, 5)], 0.50), metrics.confidence(), "Balance sheet leverage.")


def liquidity_dimension(metrics: MetricPack, company_type: CompanyType) -> DimensionScore:
    if company_type == CompanyType.FINANCIAL:
        return DimensionScore("liquidity", 0.50, metrics.confidence(), "Current ratio is not central for banks; neutral score.")
    current_ratio = metrics.get("current_ratio")
    return DimensionScore("liquidity", _normalize(current_ratio, 0.8, 2.0) if current_ratio is not None else 0.50, metrics.confidence(), "Short-term liquidity.")


def data_confidence_dimension(valuations: Iterable[ValuationResult], metrics: MetricPack) -> DimensionScore:
    parts = [v.confidence for v in valuations if v.confidence > 0] + [metrics.confidence()]
    score = sum(parts) / len(parts) if parts else 0.0
    return DimensionScore("data_confidence", score, score, "Average confidence of sources and derived metrics.")


def recommendation_from_score(score: float, dimensions: Mapping[str, DimensionScore] | None = None) -> str:
    if dimensions:
        valuation = dimensions.get("valuation")
        quality = dimensions.get("quality")
        valuation_score = valuation.score if valuation else 0.0
        quality_score = quality.score if quality else 0.0
        if score >= SCORE.buy_threshold and valuation_score < SCORE.min_valuation_score_for_buy:
            return "Observar"
        if (
            score >= SCORE.watch_threshold
            and valuation_score < SCORE.avoid_if_valuation_below
            and quality_score < SCORE.avoid_if_quality_below
        ):
            return "Evitar"
    return "Comprar" if score >= SCORE.buy_threshold else "Observar" if score >= SCORE.watch_threshold else "Evitar"


def explain_score(recommendation: str, dimensions: Mapping[str, DimensionScore]) -> str:
    best, worst = max(dimensions.values(), key=lambda d: d.score), min(dimensions.values(), key=lambda d: d.score)
    return f"Recommendation {recommendation}: strongest dimension is {best.name} ({best.score:.2f}); weakest dimension is {worst.name} ({worst.score:.2f})."


def _metric_score(metric: MetricValue | None, low: float, high: float) -> float | None:
    return None if metric is None or metric.value is None else _normalize(metric.value, low, high)


def _normalize(value: float | None, low: float, high: float) -> float:
    return 0.0 if value is None else max(0.0, min(1.0, (value - low) / (high - low)))


def _score_margin_of_safety(margin: float | None) -> float:
    if margin is None:
        return 0.0
    curve = VALUATION_SCORE.margin_score_curve
    if margin <= curve[0][0]:
        return curve[0][1]
    for (left_margin, left_score), (right_margin, right_score) in zip(curve, curve[1:]):
        if margin <= right_margin:
            span = right_margin - left_margin
            if span == 0:
                return right_score
            progress = (margin - left_margin) / span
            return left_score + progress * (right_score - left_score)
    return curve[-1][1]


def _justified_bank_price_to_book(roe: float) -> float:
    ke = VALUATION_SCORE.bank_default_cost_of_equity
    g = VALUATION_SCORE.bank_terminal_growth
    if ke <= g:
        return 1.0
    return max(0.0, (roe - g) / (ke - g))


def _average(values: list[float | None], default: float) -> float:
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else default
