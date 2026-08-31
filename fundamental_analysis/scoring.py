"""Multifactor scoring with reduced valuation double counting."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Iterable, Mapping

from .comparables import ComparableReport
from .config import CompanyType, GROWTH_TECH, SCORE, VALUATION_SCORE, ScoreWeights
from .data_sources import MetricValue
from .metrics import MetricPack
from .valuation import ValuationResult


SCORE_MODEL_VERSION = "multifactor_score_v1"
SCORE_DIMENSIONS = (
    "valuation",
    "growth",
    "quality",
    "debt",
    "liquidity",
    "data_confidence",
)


@dataclass
class DimensionScore:
    name: str
    score: float
    confidence: float
    explanation: str


@dataclass(frozen=True)
class DimensionContribution:
    name: str
    score: float
    confidence: float
    configured_weight: float
    normalized_weight: float
    weighted_contribution: float


@dataclass(frozen=True)
class ScoreComponentAudit:
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


@dataclass(frozen=True)
class ScoreConfigurationAudit:
    model_version: str
    company_type: str
    configured_weights: tuple[tuple[str, float], ...]
    normalized_weights: tuple[tuple[str, float], ...]
    buy_threshold: float
    watch_threshold: float
    min_valuation_score_for_buy: float
    avoid_if_valuation_below: float
    avoid_if_quality_below: float
    max_single_valuation_method_weight: float
    fingerprint: str


@dataclass(frozen=True)
class RecommendationDecision:
    recommendation_before_gates: str
    final_recommendation: str
    gate_code: str
    gate_triggered: bool
    total_score: float
    valuation_score: float | None
    quality_score: float | None
    buy_threshold: float
    watch_threshold: float
    min_valuation_score_for_buy: float
    avoid_if_valuation_below: float
    avoid_if_quality_below: float
    explanation: str


@dataclass
class ScoreReport:
    total_score: float
    recommendation: str
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)
    explanation: str = ""
    recommendation_decision: RecommendationDecision | None = None
    dimension_contributions: tuple[DimensionContribution, ...] = ()
    configuration_audit: ScoreConfigurationAudit | None = None
    component_audit: tuple[ScoreComponentAudit, ...] = ()


def compute_score(company_type: CompanyType, valuations: Iterable[ValuationResult], metrics: MetricPack, current_price: MetricValue, comparables: ComparableReport | None = None) -> ScoreReport:
    configured_weights = SCORE.weights_by_type[company_type]
    weights = configured_weights.normalized()
    valuations = list(valuations)
    dimensions = {
        "valuation": valuation_dimension(valuations, metrics, company_type, comparables),
        "growth": growth_dimension(metrics),
        "quality": quality_dimension(metrics),
        "debt": debt_dimension(metrics, company_type),
        "liquidity": liquidity_dimension(metrics, company_type),
        "data_confidence": data_confidence_dimension(valuations, metrics),
    }
    contributions = tuple(
        DimensionContribution(
            name=name,
            score=dimensions[name].score,
            confidence=dimensions[name].confidence,
            configured_weight=float(getattr(configured_weights, name)),
            normalized_weight=float(getattr(weights, name)),
            weighted_contribution=(
                dimensions[name].score * float(getattr(weights, name))
            ),
        )
        for name in SCORE_DIMENSIONS
    )
    total = sum(item.weighted_contribution for item in contributions)
    configuration_audit = score_configuration_audit(
        company_type,
        configured_weights,
        weights,
    )
    component_audit = score_component_audit(
        company_type,
        valuations,
        metrics,
        comparables,
        dimensions,
    )
    decision = recommendation_decision_from_score(total, dimensions)
    recommendation = decision.final_recommendation
    return ScoreReport(
        total,
        recommendation,
        dimensions,
        explain_score(recommendation, dimensions),
        decision,
        contributions,
        configuration_audit,
        component_audit,
    )


def score_component_audit(
    company_type: CompanyType,
    valuations: list[ValuationResult],
    metrics: MetricPack,
    comparables: ComparableReport | None,
    dimensions: Mapping[str, DimensionScore],
) -> tuple[ScoreComponentAudit, ...]:
    components = [
        *_valuation_component_audit(company_type, valuations, metrics, comparables),
        *_growth_component_audit(metrics),
        *_quality_component_audit(metrics),
        *_debt_component_audit(metrics, company_type),
        *_liquidity_component_audit(metrics, company_type),
        *_data_confidence_component_audit(valuations, metrics),
    ]
    for dimension_name, dimension in dimensions.items():
        reconciled = sum(
            item.weighted_contribution
            for item in components
            if item.dimension == dimension_name
            and item.stage == "dimension"
            and item.used
        )
        if abs(reconciled - dimension.score) > 1e-12:
            raise ValueError(
                f"Componentes de {dimension_name} nao reconciliam com o score da dimensao"
            )
    return tuple(components)


def _valuation_component_audit(
    company_type: CompanyType,
    valuations: list[ValuationResult],
    metrics: MetricPack,
    comparables: ComparableReport | None,
) -> list[ScoreComponentAudit]:
    components: list[ScoreComponentAudit] = []
    available = [
        valuation
        for valuation in valuations
        if valuation.margin_of_safety is not None and valuation.confidence > 0
    ]
    model_weights = {
        id(valuation): min(
            valuation.confidence,
            SCORE.max_single_valuation_method_weight,
        )
        for valuation in available
    }
    model_weight_total = sum(model_weights.values())
    for valuation in valuations:
        used = id(valuation) in model_weights and model_weight_total > 0
        transformed = (
            _score_margin_of_safety(valuation.margin_of_safety)
            if valuation.margin_of_safety is not None
            else None
        )
        configured_weight = model_weights.get(id(valuation), 0.0)
        effective_weight = (
            configured_weight / model_weight_total if used else 0.0
        )
        reason = ""
        if valuation.margin_of_safety is None:
            reason = "Margem de seguranca indisponivel."
        elif valuation.confidence <= 0:
            reason = "Confianca nao positiva."
        components.append(
            ScoreComponentAudit(
                dimension="valuation",
                stage="valuation_models",
                component=valuation.method,
                raw_value=valuation.margin_of_safety,
                transformed_score=transformed,
                configured_weight=configured_weight,
                effective_weight=effective_weight,
                weighted_contribution=(transformed or 0.0) * effective_weight,
                confidence=valuation.confidence,
                source=valuation.source,
                used=used,
                reason=reason,
            )
        )
    if not valuations or not available:
        components.append(
            ScoreComponentAudit(
                "valuation",
                "valuation_models",
                "no_reliable_valuation_model",
                None,
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                "missing",
                True,
                "Nenhum metodo apresentou margem de seguranca com confianca positiva.",
            )
        )

    intrinsic_score = sum(
        item.weighted_contribution
        for item in components
        if item.stage == "valuation_models" and item.used
    )
    intrinsic_confidence = (
        min(1.0, model_weight_total / max(1, len(available)))
        if available
        else 0.0
    )
    if company_type == CompanyType.FINANCIAL:
        bank_components = _bank_valuation_component_audit(
            metrics,
            intrinsic_score if available else None,
            intrinsic_confidence,
        )
        components.extend(bank_components)
        base_score = sum(
            item.weighted_contribution
            for item in components
            if item.stage == "bank_valuation" and item.used
        )
        base_confidence = (
            0.0
            if bank_components[0].component == "no_bank_valuation_metric"
            else max(intrinsic_confidence, metrics.confidence() * 0.80)
        )
        base_source = "bank_valuation"
    else:
        base_score = intrinsic_score
        base_confidence = intrinsic_confidence
        base_source = "valuation_models"

    comparable_usable = (
        comparables is not None
        and comparables.confidence >= VALUATION_SCORE.minimum_relative_confidence
    )
    if comparable_usable:
        intrinsic_weight = VALUATION_SCORE.intrinsic_weight * max(
            base_confidence,
            0.0,
        )
        relative_weight = VALUATION_SCORE.relative_weight * comparables.confidence
        total_weight = intrinsic_weight + relative_weight
        if total_weight > 0:
            components.extend(
                [
                    ScoreComponentAudit(
                        "valuation",
                        "dimension",
                        "intrinsic_or_bank_valuation",
                        base_score,
                        base_score,
                        intrinsic_weight,
                        intrinsic_weight / total_weight,
                        base_score * intrinsic_weight / total_weight,
                        base_confidence,
                        base_source,
                        True,
                    ),
                    ScoreComponentAudit(
                        "valuation",
                        "dimension",
                        "relative_comparables",
                        comparables.overall_score,
                        comparables.overall_score,
                        relative_weight,
                        relative_weight / total_weight,
                        comparables.overall_score * relative_weight / total_weight,
                        comparables.confidence,
                        comparables.basis,
                        True,
                    ),
                ]
            )
            return components
        components.append(
            ScoreComponentAudit(
                "valuation",
                "dimension",
                "relative_comparables",
                comparables.overall_score,
                comparables.overall_score,
                relative_weight,
                1.0,
                comparables.overall_score,
                comparables.confidence,
                comparables.basis,
                True,
                "Valuation intrinseco sem peso efetivo.",
            )
        )
        return components

    components.append(
        ScoreComponentAudit(
            "valuation",
            "dimension",
            "intrinsic_or_bank_valuation",
            base_score,
            base_score,
            1.0,
            1.0,
            base_score,
            base_confidence,
            base_source,
            True,
        )
    )
    components.append(
        ScoreComponentAudit(
            "valuation",
            "dimension",
            "relative_comparables",
            comparables.overall_score if comparables is not None else None,
            comparables.overall_score if comparables is not None else None,
            VALUATION_SCORE.relative_weight,
            0.0,
            0.0,
            comparables.confidence if comparables is not None else 0.0,
            comparables.basis if comparables is not None else "missing",
            False,
            (
                "Confianca dos comparaveis abaixo do minimo exigido."
                if comparables is not None
                else "Relatorio de comparaveis ausente."
            ),
        )
    )
    return components


def _bank_valuation_component_audit(
    metrics: MetricPack,
    model_score: float | None,
    model_confidence: float,
) -> list[ScoreComponentAudit]:
    candidates: list[tuple[str, float | None, float | None, float, float, str, str]] = []
    if model_score is not None:
        candidates.append(
            (
                "valuation_models",
                model_score,
                model_score,
                VALUATION_SCORE.bank_model_weight,
                model_confidence,
                "valuation_models",
                "",
            )
        )
    pb_metric = metrics.values.get("price_to_book")
    roe_metric = metrics.values.get("roe")
    pb = pb_metric.value if pb_metric and pb_metric.value is not None else None
    roe = roe_metric.value if roe_metric and roe_metric.value is not None else None
    if pb is not None:
        candidates.append(
            (
                "price_to_book",
                pb,
                1.0 - _normalize(pb, 0.7, 2.8),
                VALUATION_SCORE.bank_price_to_book_weight,
                pb_metric.confidence,
                pb_metric.source,
                "",
            )
        )
    if roe is not None:
        candidates.append(
            (
                "roe",
                roe,
                _normalize(roe, 0.08, 0.18),
                VALUATION_SCORE.bank_roe_weight,
                roe_metric.confidence,
                roe_metric.source,
                "",
            )
        )
    if pb not in (None, 0) and roe is not None:
        justified_pb = _justified_bank_price_to_book(roe)
        relative_margin = (justified_pb / pb) - 1.0
        candidates.append(
            (
                "justified_price_to_book",
                relative_margin,
                _score_margin_of_safety(relative_margin),
                VALUATION_SCORE.bank_justified_price_to_book_weight,
                min(pb_metric.confidence, roe_metric.confidence),
                "derived",
                "P/VP justificado a partir de ROE, custo de capital e crescimento terminal.",
            )
        )
    if not candidates:
        return [
            ScoreComponentAudit(
                "valuation",
                "bank_valuation",
                "no_bank_valuation_metric",
                None,
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                "missing",
                True,
                "Nenhuma metrica de valuation bancario ficou disponivel.",
            )
        ]
    total_weight = sum(item[3] for item in candidates)
    return [
        ScoreComponentAudit(
            "valuation",
            "bank_valuation",
            name,
            raw_value,
            transformed_score,
            configured_weight,
            configured_weight / total_weight,
            (transformed_score or 0.0) * configured_weight / total_weight,
            confidence,
            source,
            True,
            reason,
        )
        for (
            name,
            raw_value,
            transformed_score,
            configured_weight,
            confidence,
            source,
            reason,
        ) in candidates
    ]


def _metric_average_component_audit(
    dimension: str,
    metrics: MetricPack,
    specifications: tuple[tuple[str, float, float], ...],
    default_score: float,
) -> list[ScoreComponentAudit]:
    available = [
        (name, low, high, metrics.values.get(name))
        for name, low, high in specifications
        if metrics.values.get(name) is not None
        and metrics.values[name].value is not None
    ]
    if not available:
        return [
            ScoreComponentAudit(
                dimension,
                "dimension",
                "default_missing_data",
                None,
                default_score,
                1.0,
                1.0,
                default_score,
                0.0,
                "config",
                True,
                "Nenhum componente da dimensao ficou disponivel.",
            )
        ]
    effective_weight = 1.0 / len(available)
    components = [
        ScoreComponentAudit(
            dimension,
            "dimension",
            name,
            metric.value,
            _normalize(metric.value, low, high),
            1.0,
            effective_weight,
            _normalize(metric.value, low, high) * effective_weight,
            metric.confidence,
            metric.source,
            True,
        )
        for name, low, high, metric in available
    ]
    available_names = {name for name, _, _, _ in available}
    for name, _, _ in specifications:
        if name not in available_names:
            metric = metrics.values.get(name)
            components.append(
                ScoreComponentAudit(
                    dimension,
                    "dimension",
                    name,
                    None,
                    None,
                    1.0,
                    0.0,
                    0.0,
                    metric.confidence if metric else 0.0,
                    metric.source if metric else "missing",
                    False,
                    "Metrica indisponivel; removida da media dinamica.",
                )
            )
    return components


def _growth_component_audit(metrics: MetricPack) -> list[ScoreComponentAudit]:
    return _metric_average_component_audit(
        "growth",
        metrics,
        (("revenue_growth", -0.05, 0.25), ("fcff_growth", -0.10, 0.20)),
        0.50,
    )


def _quality_component_audit(metrics: MetricPack) -> list[ScoreComponentAudit]:
    return _metric_average_component_audit(
        "quality",
        metrics,
        (
            ("fama_french_profitability", 0.0, 1.0),
            ("earnings_quality", 0.0, 1.0),
            ("piotroski_proxy", 0.0, 1.0),
        ),
        0.0,
    )


def _debt_component_audit(
    metrics: MetricPack,
    company_type: CompanyType,
) -> list[ScoreComponentAudit]:
    if company_type == CompanyType.FINANCIAL:
        return [
            ScoreComponentAudit(
                "debt",
                "dimension",
                "financial_neutral_default",
                None,
                0.50,
                1.0,
                1.0,
                0.50,
                metrics.confidence(),
                "sector_rule",
                True,
                "Alavancagem tradicional nao e comparavel para bancos.",
            )
        ]
    components = _metric_average_component_audit(
        "debt",
        metrics,
        (("debt_to_equity", 0.0, 3.0), ("net_debt_to_ebit", 0.0, 5.0)),
        0.50,
    )
    return [
        ScoreComponentAudit(
            item.dimension,
            item.stage,
            item.component,
            item.raw_value,
            (
                1.0 - item.transformed_score
                if item.transformed_score is not None
                and item.component != "default_missing_data"
                else item.transformed_score
            ),
            item.configured_weight,
            item.effective_weight,
            (
                (1.0 - item.transformed_score) * item.effective_weight
                if item.transformed_score is not None
                and item.component != "default_missing_data"
                else item.weighted_contribution
            ),
            item.confidence,
            item.source,
            item.used,
            item.reason,
        )
        for item in components
    ]


def _liquidity_component_audit(
    metrics: MetricPack,
    company_type: CompanyType,
) -> list[ScoreComponentAudit]:
    if company_type == CompanyType.FINANCIAL:
        return [
            ScoreComponentAudit(
                "liquidity",
                "dimension",
                "financial_neutral_default",
                None,
                0.50,
                1.0,
                1.0,
                0.50,
                metrics.confidence(),
                "sector_rule",
                True,
                "Liquidez corrente nao e o principal indicador para bancos.",
            )
        ]
    current_metric = metrics.values.get("current_ratio")
    current_value = (
        current_metric.value
        if current_metric is not None and current_metric.value is not None
        else None
    )
    current_score = (
        _normalize(current_value, 0.8, 2.0)
        if current_value is not None
        else 0.50
    )
    runway_metric = metrics.values.get("cash_runway_years")
    runway_value = (
        runway_metric.value
        if runway_metric is not None and runway_metric.value is not None
        else None
    )
    if company_type == CompanyType.GROWTH_TECH and runway_value is not None:
        runway_score = _normalize(
            runway_value,
            0.5,
            max(GROWTH_TECH.min_cash_runway_years, 0.5),
        )
        return [
            ScoreComponentAudit(
                "liquidity",
                "dimension",
                "current_ratio",
                current_value,
                current_score,
                0.40,
                0.40,
                current_score * 0.40,
                current_metric.confidence if current_metric else 0.0,
                current_metric.source if current_metric else "config",
                True,
                "Fallback neutro aplicado." if current_value is None else "",
            ),
            ScoreComponentAudit(
                "liquidity",
                "dimension",
                "cash_runway_years",
                runway_value,
                runway_score,
                0.60,
                0.60,
                runway_score * 0.60,
                runway_metric.confidence,
                runway_metric.source,
                True,
            ),
        ]
    components = [
        ScoreComponentAudit(
            "liquidity",
            "dimension",
            "current_ratio",
            current_value,
            current_score,
            1.0,
            1.0,
            current_score,
            current_metric.confidence if current_metric else 0.0,
            current_metric.source if current_metric else "config",
            True,
            "Fallback neutro aplicado." if current_value is None else "",
        )
    ]
    if company_type == CompanyType.GROWTH_TECH:
        components.append(
            ScoreComponentAudit(
                "liquidity",
                "dimension",
                "cash_runway_years",
                None,
                None,
                0.60,
                0.0,
                0.0,
                runway_metric.confidence if runway_metric else 0.0,
                runway_metric.source if runway_metric else "missing",
                False,
                "Runway indisponivel; liquidez corrente recebeu todo o peso efetivo.",
            )
        )
    return components


def _data_confidence_component_audit(
    valuations: list[ValuationResult],
    metrics: MetricPack,
) -> list[ScoreComponentAudit]:
    candidates = [
        (valuation.method, valuation.confidence, valuation.source)
        for valuation in valuations
        if valuation.confidence > 0
    ]
    metric_confidence = metrics.confidence()
    candidates.append(("metrics_pack", metric_confidence, "aggregated_metrics"))
    if not candidates:
        return [
            ScoreComponentAudit(
                "data_confidence",
                "dimension",
                "no_confidence_signal",
                None,
                0.0,
                1.0,
                1.0,
                0.0,
                0.0,
                "missing",
                True,
            )
        ]
    effective_weight = 1.0 / len(candidates)
    return [
        ScoreComponentAudit(
            "data_confidence",
            "dimension",
            name,
            value,
            value,
            1.0,
            effective_weight,
            value * effective_weight,
            value,
            source,
            True,
        )
        for name, value, source in candidates
    ]


def score_configuration_audit(
    company_type: CompanyType,
    configured_weights: ScoreWeights,
    normalized_weights: ScoreWeights,
) -> ScoreConfigurationAudit:
    configured = tuple(
        (name, float(getattr(configured_weights, name)))
        for name in SCORE_DIMENSIONS
    )
    normalized = tuple(
        (name, float(getattr(normalized_weights, name)))
        for name in SCORE_DIMENSIONS
    )
    payload = {
        "model_version": SCORE_MODEL_VERSION,
        "company_type": company_type.value,
        "configured_weights": dict(configured),
        "normalized_weights": dict(normalized),
        "buy_threshold": SCORE.buy_threshold,
        "watch_threshold": SCORE.watch_threshold,
        "min_valuation_score_for_buy": SCORE.min_valuation_score_for_buy,
        "avoid_if_valuation_below": SCORE.avoid_if_valuation_below,
        "avoid_if_quality_below": SCORE.avoid_if_quality_below,
        "max_single_valuation_method_weight": (
            SCORE.max_single_valuation_method_weight
        ),
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return ScoreConfigurationAudit(
        model_version=SCORE_MODEL_VERSION,
        company_type=company_type.value,
        configured_weights=configured,
        normalized_weights=normalized,
        buy_threshold=SCORE.buy_threshold,
        watch_threshold=SCORE.watch_threshold,
        min_valuation_score_for_buy=SCORE.min_valuation_score_for_buy,
        avoid_if_valuation_below=SCORE.avoid_if_valuation_below,
        avoid_if_quality_below=SCORE.avoid_if_quality_below,
        max_single_valuation_method_weight=(
            SCORE.max_single_valuation_method_weight
        ),
        fingerprint=fingerprint,
    )


def valuation_dimension(valuations: Iterable[ValuationResult], metrics: MetricPack | None = None, company_type: CompanyType = CompanyType.TRADITIONAL, comparables: ComparableReport | None = None) -> DimensionScore:
    available = [v for v in valuations if v.margin_of_safety is not None and v.confidence > 0]
    if not available:
        base = financial_valuation_dimension(metrics, None, 0.0) if company_type == CompanyType.FINANCIAL and metrics else DimensionScore("valuation", 0.0, 0.0, "Nenhum modelo de valuation confiavel ficou disponivel.")
        return blend_relative_valuation(base, comparables)
    weighted = [(_score_margin_of_safety(v.margin_of_safety), min(v.confidence, SCORE.max_single_valuation_method_weight)) for v in available]
    total_weight = sum(weight for _, weight in weighted)
    score = sum(value * weight for value, weight in weighted) / total_weight if total_weight else 0.0
    confidence = min(1.0, total_weight / max(1, len(available)))
    base = financial_valuation_dimension(metrics, score, confidence) if company_type == CompanyType.FINANCIAL and metrics else DimensionScore("valuation", score, confidence, "Mede a margem de seguranca combinada dos modelos de valuation, com peso limitado por metodo para reduzir dupla contagem.")
    return blend_relative_valuation(base, comparables)


def blend_relative_valuation(base: DimensionScore, comparables: ComparableReport | None = None) -> DimensionScore:
    if comparables is None or comparables.confidence < VALUATION_SCORE.minimum_relative_confidence:
        return base
    intrinsic_weight = VALUATION_SCORE.intrinsic_weight * max(base.confidence, 0.0)
    relative_weight = VALUATION_SCORE.relative_weight * comparables.confidence
    total_weight = intrinsic_weight + relative_weight
    if total_weight <= 0:
        return DimensionScore("valuation", comparables.overall_score, comparables.confidence, "Valuation relativo por multiplos de pares; valuation intrinseco indisponivel.")
    score = ((base.score * intrinsic_weight) + (comparables.overall_score * relative_weight)) / total_weight
    confidence = min(1.0, intrinsic_weight + relative_weight)
    return DimensionScore(
        "valuation",
        score,
        confidence,
        "Combina margem de seguranca dos modelos intrinsecos com multiplos relativos de pares; o peso dos comparaveis e limitado pela confianca da amostra.",
    )


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
        return DimensionScore("valuation", 0.0, 0.0, "Nenhuma metrica confiavel de valuation bancario ficou disponivel.")
    total_weight = sum(weight for _, weight in pieces)
    return DimensionScore("valuation", sum(value * weight for value, weight in pieces) / total_weight, max(model_confidence, metrics.confidence() * 0.80), "Para bancos, combina Lucro Residual/DDM, P/VP e forca do ROE contra o custo de capital.")


def growth_dimension(metrics: MetricPack) -> DimensionScore:
    return DimensionScore("growth", _average([_metric_score(metrics.values.get("revenue_growth"), -0.05, 0.25), _metric_score(metrics.values.get("fcff_growth"), -0.10, 0.20)], 0.50), metrics.confidence(), "Avalia o perfil de crescimento de receita e de fluxo de caixa livre para a firma.")


def quality_dimension(metrics: MetricPack) -> DimensionScore:
    return DimensionScore("quality", _average([_metric_score(metrics.values.get("fama_french_profitability"), 0, 1), _metric_score(metrics.values.get("earnings_quality"), 0, 1), _metric_score(metrics.values.get("piotroski_proxy"), 0, 1)], 0.0), metrics.confidence(), "Avalia rentabilidade, qualidade do lucro, accruals e sinais inspirados no Piotroski F-Score.")


def debt_dimension(metrics: MetricPack, company_type: CompanyType) -> DimensionScore:
    if company_type == CompanyType.FINANCIAL:
        return DimensionScore("debt", 0.50, metrics.confidence(), "Indicadores tradicionais de divida sao menos comparaveis em bancos; por isso o score fica neutro.")
    de, nd = metrics.get("debt_to_equity"), metrics.get("net_debt_to_ebit")
    return DimensionScore("debt", _average([None if de is None else 1.0 - _normalize(de, 0, 3), None if nd is None else 1.0 - _normalize(nd, 0, 5)], 0.50), metrics.confidence(), "Avalia a alavancagem do balanco, principalmente divida sobre patrimonio e divida liquida sobre EBIT.")


def liquidity_dimension(metrics: MetricPack, company_type: CompanyType) -> DimensionScore:
    if company_type == CompanyType.FINANCIAL:
        return DimensionScore("liquidity", 0.50, metrics.confidence(), "Liquidez corrente nao e o principal indicador para bancos; por isso a leitura fica neutra.")
    current_ratio = metrics.get("current_ratio")
    current_ratio_score = _normalize(current_ratio, 0.8, 2.0) if current_ratio is not None else 0.50
    if company_type == CompanyType.GROWTH_TECH:
        runway = metrics.get("cash_runway_years")
        if runway is not None:
            runway_score = _normalize(runway, 0.5, max(GROWTH_TECH.min_cash_runway_years, 0.5))
            score = (current_ratio_score * 0.40) + (runway_score * 0.60)
            return DimensionScore("liquidity", score, metrics.confidence(), "Para growth/tech, combina liquidez corrente com runway de caixa para capturar risco de queima de caixa.")
    return DimensionScore("liquidity", current_ratio_score, metrics.confidence(), "Avalia a folga de liquidez de curto prazo, principalmente ativos circulantes contra passivos circulantes.")


def data_confidence_dimension(valuations: Iterable[ValuationResult], metrics: MetricPack) -> DimensionScore:
    parts = [v.confidence for v in valuations if v.confidence > 0] + [metrics.confidence()]
    score = sum(parts) / len(parts) if parts else 0.0
    return DimensionScore("data_confidence", score, score, "Mede a confianca media das fontes e das metricas derivadas; nao e probabilidade de acerto.")


def recommendation_from_score(score: float, dimensions: Mapping[str, DimensionScore] | None = None) -> str:
    return recommendation_decision_from_score(score, dimensions).final_recommendation


def recommendation_decision_from_score(
    score: float,
    dimensions: Mapping[str, DimensionScore] | None = None,
) -> RecommendationDecision:
    recommendation_before_gates = (
        "Comprar"
        if score >= SCORE.buy_threshold
        else "Observar"
        if score >= SCORE.watch_threshold
        else "Evitar"
    )
    valuation_score: float | None = None
    quality_score: float | None = None
    if dimensions:
        valuation = dimensions.get("valuation")
        quality = dimensions.get("quality")
        valuation_score = valuation.score if valuation else 0.0
        quality_score = quality.score if quality else 0.0
        if score >= SCORE.buy_threshold and valuation_score < SCORE.min_valuation_score_for_buy:
            return RecommendationDecision(
                recommendation_before_gates,
                "Observar",
                "buy_blocked_low_valuation",
                True,
                score,
                valuation_score,
                quality_score,
                SCORE.buy_threshold,
                SCORE.watch_threshold,
                SCORE.min_valuation_score_for_buy,
                SCORE.avoid_if_valuation_below,
                SCORE.avoid_if_quality_below,
                (
                    "Compra bloqueada: o score total atingiu o limiar, mas valuation "
                    f"({valuation_score:.2f}) ficou abaixo do minimo "
                    f"({SCORE.min_valuation_score_for_buy:.2f})."
                ),
            )
        if (
            score >= SCORE.watch_threshold
            and valuation_score < SCORE.avoid_if_valuation_below
            and quality_score < SCORE.avoid_if_quality_below
        ):
            return RecommendationDecision(
                recommendation_before_gates,
                "Evitar",
                "avoid_low_valuation_and_quality",
                True,
                score,
                valuation_score,
                quality_score,
                SCORE.buy_threshold,
                SCORE.watch_threshold,
                SCORE.min_valuation_score_for_buy,
                SCORE.avoid_if_valuation_below,
                SCORE.avoid_if_quality_below,
                (
                    "Trava de seguranca acionada: valuation "
                    f"({valuation_score:.2f}) e qualidade ({quality_score:.2f}) "
                    "ficaram simultaneamente abaixo dos limites."
                ),
            )
    return RecommendationDecision(
        recommendation_before_gates,
        recommendation_before_gates,
        "none",
        False,
        score,
        valuation_score,
        quality_score,
        SCORE.buy_threshold,
        SCORE.watch_threshold,
        SCORE.min_valuation_score_for_buy,
        SCORE.avoid_if_valuation_below,
        SCORE.avoid_if_quality_below,
        "Nenhuma trava adicional alterou a recomendacao definida pelo score total.",
    )


def explain_score(recommendation: str, dimensions: Mapping[str, DimensionScore]) -> str:
    best, worst = max(dimensions.values(), key=lambda d: d.score), min(dimensions.values(), key=lambda d: d.score)
    return f"Recomendacao {recommendation}: a dimensao mais forte foi {best.name} ({best.score:.2f}); a dimensao mais fraca foi {worst.name} ({worst.score:.2f})."


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
