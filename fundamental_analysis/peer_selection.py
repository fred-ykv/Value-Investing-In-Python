"""Assisted peer selection with explainable equivalence scoring."""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Mapping, Sequence

from .config import PEER_SELECTION
from .data_sources import safe_float
from .metrics import MetricPack


@dataclass
class PeerCandidateResult:
    ticker: str
    score: float
    status: str
    reasons: list[str] = field(default_factory=list)
    vetoes: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class PeerSelectionReport:
    approved: list[PeerCandidateResult]
    rejected: list[PeerCandidateResult]
    peer_medians: dict[str, float]
    confidence: float
    summary: str


MULTIPLE_FIELDS = (
    "price_to_earnings",
    "price_to_book",
    "ev_to_sales",
    "ev_to_ebit",
    "price_to_sales",
)

MODEL_VETO_GROUPS = (
    ("traditional_auto", "ev_pure_play"),
    ("bank", "insurance"),
    ("bank", "fintech"),
    ("saas", "semiconductor"),
    ("marketplace", "physical_retail"),
    ("reit", "homebuilder"),
    ("pre_revenue_biotech", "large_pharma"),
)


def build_peer_selection_report(target_info: Mapping[str, object], target_metrics: MetricPack, candidates: Sequence[Mapping[str, object]] | None) -> PeerSelectionReport:
    target_profile = company_profile(target_info, target_metrics)
    results = [score_candidate(target_profile, candidate) for candidate in candidates or []]
    approved = [result for result in results if result.status in {"strong", "acceptable"}]
    rejected = [result for result in results if result.status not in {"strong", "acceptable"}]
    medians = median_multiples(approved)
    confidence = min(1.0, len(approved) / max(1, PEER_SELECTION.min_approved_peers))
    return PeerSelectionReport(approved, rejected, medians, confidence, peer_selection_summary(approved, rejected, confidence))


def company_profile(info: Mapping[str, object], metrics: MetricPack) -> dict[str, object]:
    return {
        "sector": normalized_text(info.get("sector")),
        "industry": normalized_text(info.get("industry")),
        "sic": normalized_text(first_present(info, "sic", "sic_code")),
        "business_model": normalized_model(first_present(info, "business_model", "model", "company_type_detail")),
        "market_cap": safe_float(first_present(info, "market_cap", "marketCap")),
        "revenue_growth": safe_float(first_present(info, "revenue_growth", "growth")) if first_present(info, "revenue_growth", "growth") is not None else metrics.get("revenue_growth"),
        "operating_margin": safe_float(first_present(info, "operating_margin")) if first_present(info, "operating_margin") is not None else metrics.get("operating_margin"),
        "debt_to_equity": safe_float(first_present(info, "debt_to_equity")) if first_present(info, "debt_to_equity") is not None else metrics.get("debt_to_equity"),
    }


def score_candidate(target: Mapping[str, object], candidate: Mapping[str, object]) -> PeerCandidateResult:
    candidate_profile = company_profile(candidate, MetricPack({}))
    reasons: list[str] = []
    vetoes = model_vetoes(str(target.get("business_model") or ""), str(candidate_profile.get("business_model") or ""))
    pieces = [
        categorical_piece("sector", target, candidate_profile, PEER_SELECTION.sector_weight, reasons),
        categorical_piece("industry", target, candidate_profile, PEER_SELECTION.industry_weight, reasons),
        categorical_piece("sic", target, candidate_profile, PEER_SELECTION.sic_weight, reasons),
        categorical_piece("business_model", target, candidate_profile, PEER_SELECTION.business_model_weight, reasons),
        numeric_piece("market_cap", target, candidate_profile, PEER_SELECTION.size_weight, 1.0, reasons),
        numeric_piece("revenue_growth", target, candidate_profile, PEER_SELECTION.growth_weight, 0.20, reasons),
        numeric_piece("operating_margin", target, candidate_profile, PEER_SELECTION.margin_weight, 0.20, reasons),
        numeric_piece("debt_to_equity", target, candidate_profile, PEER_SELECTION.leverage_weight, 2.0, reasons),
    ]
    total_weight = sum(weight for _, weight in pieces)
    score = sum(value * weight for value, weight in pieces) / total_weight if total_weight else 0.0
    status = peer_status(score, vetoes)
    return PeerCandidateResult(str(candidate.get("ticker") or candidate.get("symbol") or "UNKNOWN"), score, status, reasons, vetoes, candidate_multiples(candidate))


def categorical_piece(name: str, target: Mapping[str, object], candidate: Mapping[str, object], weight: float, reasons: list[str]) -> tuple[float, float]:
    left, right = target.get(name), candidate.get(name)
    if not left or not right:
        return 0.0, 0.0
    match = left == right
    reasons.append(f"{name} {'igual' if match else 'diferente'}")
    return (1.0 if match else 0.0), weight


def numeric_piece(name: str, target: Mapping[str, object], candidate: Mapping[str, object], weight: float, tolerance: float, reasons: list[str]) -> tuple[float, float]:
    left, right = safe_float(target.get(name)), safe_float(candidate.get(name))
    if left is None or right is None:
        return 0.0, 0.0
    if name == "market_cap":
        ratio = min(left, right) / max(left, right) if max(left, right) else 0.0
        reasons.append(f"{name} similaridade {ratio:.2f}")
        return ratio, weight
    diff = abs(left - right)
    score = max(0.0, 1.0 - diff / tolerance)
    reasons.append(f"{name} similaridade {score:.2f}")
    return score, weight


def model_vetoes(target_model: str, candidate_model: str) -> list[str]:
    if not target_model or not candidate_model:
        return []
    vetoes = []
    for left, right in MODEL_VETO_GROUPS:
        if {target_model, candidate_model} == {left, right}:
            vetoes.append(f"modelo economico incompativel: {target_model} vs {candidate_model}")
    return vetoes


def peer_status(score: float, vetoes: list[str]) -> str:
    if vetoes:
        return "rejected_veto"
    if score >= PEER_SELECTION.strong_threshold:
        return "strong"
    if score >= PEER_SELECTION.acceptable_threshold:
        return "acceptable"
    if score >= PEER_SELECTION.weak_threshold:
        return "weak_reference"
    return "rejected_low_similarity"


def median_multiples(approved: Sequence[PeerCandidateResult]) -> dict[str, float]:
    medians = {}
    for field_name in MULTIPLE_FIELDS:
        values = [candidate.metrics[field_name] for candidate in approved if candidate.metrics.get(field_name) is not None]
        if values:
            medians[field_name] = median(values)
    return medians


def candidate_multiples(candidate: Mapping[str, object]) -> dict[str, float]:
    metrics = {}
    for field_name in MULTIPLE_FIELDS:
        value = first_present(candidate, field_name, f"peer_{field_name}")
        numeric = safe_float(value)
        if numeric is not None and numeric > 0:
            metrics[field_name] = numeric
    return metrics


def merge_peer_medians(market_data: Mapping[str, object], peer_selection: PeerSelectionReport) -> dict[str, object]:
    merged = dict(market_data)
    if merged.get("peer_medians") or not peer_selection.peer_medians:
        return merged
    merged["peer_medians"] = peer_selection.peer_medians
    return merged


def peer_selection_summary(approved: Sequence[PeerCandidateResult], rejected: Sequence[PeerCandidateResult], confidence: float) -> str:
    if not approved:
        return "Nenhum par aprovado pelo filtro de equivalencia."
    return f"{len(approved)} pares aprovados, {len(rejected)} rejeitados; confianca da selecao {confidence:.2f}."


def normalized_text(value: object) -> str:
    return str(value or "").strip().lower()


def normalized_model(value: object) -> str:
    return normalized_text(value).replace(" ", "_").replace("-", "_")


def first_present(values: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        if values.get(key) is not None:
            return values[key]
    return None
