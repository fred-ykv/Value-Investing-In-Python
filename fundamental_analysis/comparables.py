"""Market comparable multiples and relative valuation diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Mapping

from .config import COMPARABLES, CompanyType
from .data_sources import MetricValue, safe_float
from .metrics import MetricPack, safe_div


@dataclass
class ComparableMetric:
    name: str
    company_value: float | None
    peer_median: float | None
    peer_count: int
    premium_discount: float | None
    score: float
    source: str
    interpretation: str


@dataclass
class ComparableReport:
    metrics: list[ComparableMetric]
    overall_score: float
    confidence: float
    summary: str


PEER_ALIASES = {
    "price_to_earnings": ("peer_price_to_earnings", "peer_pe", "sector_pe", "industry_pe"),
    "price_to_book": ("peer_price_to_book", "peer_pb", "sector_pb", "industry_pb"),
    "ev_to_sales": ("peer_ev_to_sales", "peer_ev_sales", "sector_ev_sales", "industry_ev_sales"),
    "ev_to_ebitda": ("peer_ev_to_ebitda", "peer_ev_ebitda", "sector_ev_ebitda", "industry_ev_ebitda"),
    "ev_to_ebit": ("peer_ev_to_ebit", "peer_ev_ebit", "sector_ev_ebit", "industry_ev_ebit"),
    "price_to_sales": ("peer_price_to_sales", "peer_ps", "sector_ps", "industry_ps"),
}


def build_comparable_report(company_type: CompanyType, values: Mapping[str, MetricValue], metrics: MetricPack, market_data: Mapping[str, object]) -> ComparableReport:
    company_multiples = company_multiple_values(values, metrics)
    peer_medians = peer_multiple_values(market_data)
    selected = selected_multiples(company_type)
    rows = [
        compare_multiple(name, company_multiples.get(name), peer_medians.get(name), peer_count(name, market_data), peer_source(name, market_data))
        for name in selected
        if company_multiples.get(name) is not None or peer_medians.get(name) is not None
    ]
    usable = [row for row in rows if row.premium_discount is not None]
    breadth_confidence = min(1.0, len(usable) / max(COMPARABLES.minimum_peer_metrics, len(selected)))
    sample_confidence = average_sample_confidence(usable)
    confidence = breadth_confidence * sample_confidence
    overall = sum(row.score for row in usable) / len(usable) if usable else 0.0
    return ComparableReport(rows, overall, confidence, comparable_summary(overall, confidence, len(usable), sample_confidence))


def company_multiple_values(values: Mapping[str, MetricValue], metrics: MetricPack) -> dict[str, float | None]:
    revenue = metric_number(values.get("revenue"))
    ebit = metric_number(values.get("ebit"))
    depreciation_amortization = metric_number(values.get("depreciation_amortization"))
    net_income = metric_number(values.get("net_income"))
    equity = metric_number(values.get("equity"))
    debt = metric_number(values.get("total_debt")) or 0.0
    cash = metric_number(values.get("cash")) or 0.0
    price = metric_number(values.get("price"))
    shares = metric_number(values.get("shares"))
    market_cap = None if price is None or shares is None else price * shares
    enterprise_value = None if market_cap is None else market_cap + debt - cash
    ebitda = None if ebit is None else ebit + (depreciation_amortization or 0.0)
    return {
        "price_to_earnings": safe_positive_ratio(market_cap, net_income),
        "price_to_book": metrics.get("price_to_book") or safe_positive_ratio(market_cap, equity),
        "ev_to_sales": safe_positive_ratio(enterprise_value, revenue),
        "ev_to_ebitda": safe_positive_ratio(enterprise_value, ebitda),
        "ev_to_ebit": safe_positive_ratio(enterprise_value, ebit),
        "price_to_sales": safe_positive_ratio(market_cap, revenue),
    }


def peer_multiple_values(market_data: Mapping[str, object]) -> dict[str, float | None]:
    peer_medians = market_data.get("peer_medians")
    nested = peer_medians if isinstance(peer_medians, Mapping) else {}
    return {
        name: first_number(nested.get(name), *(market_data.get(alias) for alias in aliases))
        for name, aliases in PEER_ALIASES.items()
    }


def compare_multiple(name: str, company_value: float | None, peer_median: float | None, count: int, source: str) -> ComparableMetric:
    premium = None if company_value in (None, 0) or peer_median in (None, 0) else (company_value / peer_median) - 1.0
    score = score_premium_discount(premium)
    return ComparableMetric(name, company_value, peer_median, count, premium, score, source, interpretation_for(premium, count))


def selected_multiples(company_type: CompanyType) -> tuple[str, ...]:
    if company_type == CompanyType.FINANCIAL:
        return ("price_to_book", "price_to_earnings")
    if company_type == CompanyType.GROWTH_TECH:
        return ("ev_to_sales", "price_to_sales", "price_to_earnings")
    return ("price_to_earnings", "ev_to_ebitda", "ev_to_ebit", "ev_to_sales", "price_to_book")


def score_premium_discount(premium: float | None) -> float:
    if premium is None:
        return 0.0
    low = COMPARABLES.discount_for_strong_score
    high = COMPARABLES.premium_for_weak_score
    if premium <= low:
        return 1.0
    if premium >= high:
        return 0.0
    return 1.0 - ((premium - low) / (high - low))


def comparable_summary(score: float, confidence: float, usable_count: int, sample_confidence: float = 1.0) -> str:
    if usable_count == 0 or confidence == 0:
        return "Sem medianas de pares suficientes para leitura relativa."
    if sample_confidence < 1.0:
        return "Leitura relativa disponivel, mas rebaixada por amostra limitada de pares."
    if score >= 0.65:
        return "Multiplos relativos sugerem desconto contra pares."
    if score <= 0.35:
        return "Multiplos relativos sugerem premio contra pares."
    return "Multiplos relativos parecem proximos dos pares."


def interpretation_for(premium: float | None, peer_count: int = 0) -> str:
    if premium is None:
        return "Comparacao indisponivel por falta de multiplo da empresa ou mediana de pares."
    if 0 < peer_count < COMPARABLES.minimum_peer_metrics:
        return "Comparacao calculada, mas com amostra de pares abaixo do minimo recomendado."
    if premium <= COMPARABLES.discount_for_strong_score:
        return "Desconto relevante contra pares."
    if premium >= COMPARABLES.premium_for_weak_score:
        return "Premio relevante contra pares."
    return "Proximo da faixa dos pares."


def peer_source(name: str, market_data: Mapping[str, object]) -> str:
    peer_medians = market_data.get("peer_medians")
    if isinstance(peer_medians, Mapping) and peer_medians.get(name) is not None:
        return "peer_medians"
    for alias in PEER_ALIASES[name]:
        if market_data.get(alias) is not None:
            return alias
    return "missing"


def peer_count(name: str, market_data: Mapping[str, object]) -> int:
    counts = market_data.get("peer_median_counts")
    if isinstance(counts, Mapping):
        value = safe_float(counts.get(name), 0.0)
        return int(value or 0)
    peer_medians = market_data.get("peer_medians")
    if isinstance(peer_medians, Mapping) and peer_medians.get(name) is not None:
        return COMPARABLES.minimum_peer_metrics
    return 1 if peer_source(name, market_data) != "missing" else 0


def average_sample_confidence(rows: list[ComparableMetric]) -> float:
    if not rows:
        return 0.0
    scores = [min(1.0, row.peer_count / max(1, COMPARABLES.minimum_peer_metrics)) for row in rows]
    return sum(scores) / len(scores)


def safe_positive_ratio(num: float | None, den: float | None) -> float | None:
    value = safe_div(num, den)
    return value if value is not None and value > 0 else None


def metric_number(metric: MetricValue | None) -> float | None:
    return None if metric is None else safe_float(metric.value)


def first_number(*values: object) -> float | None:
    parsed = [safe_float(value) for value in values]
    available = [value for value in parsed if value is not None and value > 0]
    return median(available) if len(available) > 1 else available[0] if available else None
