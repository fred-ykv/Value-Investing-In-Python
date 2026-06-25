"""Candidate peer discovery before final equivalence scoring."""
from __future__ import annotations

from typing import Mapping, Sequence

from .config import PEER_DISCOVERY
from .data_sources import safe_float
from .metrics import MetricPack
from .peer_selection import company_profile, first_present, normalized_model, normalized_text


def discover_peer_candidates(target_info: Mapping[str, object], target_metrics: MetricPack, market_data: Mapping[str, object]) -> list[dict[str, object]]:
    explicit = [dict(candidate) for candidate in sequence_of_mappings(market_data.get("peer_candidates"))]
    universe = sequence_of_mappings(first_present(market_data, "peer_universe", "candidate_universe", "comparable_universe"))
    if not universe:
        return explicit

    target = company_profile(target_info, target_metrics)
    target_ticker = normalized_text(first_present(target_info, "ticker", "symbol"))
    discovered = []
    for raw_candidate in universe:
        candidate = dict(raw_candidate)
        ticker = normalized_text(first_present(candidate, "ticker", "symbol"))
        if ticker and target_ticker and ticker == target_ticker:
            continue
        score, reasons = discovery_score(target, candidate)
        if score >= PEER_DISCOVERY.min_candidate_score:
            candidate["discovery_score"] = score
            candidate["discovery_reasons"] = reasons
            candidate.setdefault("candidate_source", "peer_universe")
            discovered.append(candidate)

    ranked = sorted(discovered, key=lambda item: safe_float(item.get("discovery_score"), 0.0) or 0.0, reverse=True)
    return merge_candidates(explicit, ranked[: PEER_DISCOVERY.max_candidates])


def discovery_score(target: Mapping[str, object], candidate: Mapping[str, object]) -> tuple[float, list[str]]:
    candidate_profile = company_profile(candidate, MetricPack({}))
    reasons: list[str] = []
    pieces = [
        categorical_score("sector", target, candidate_profile, PEER_DISCOVERY.sector_weight, reasons),
        categorical_score("industry", target, candidate_profile, PEER_DISCOVERY.industry_weight, reasons),
        sic_score(target, candidate_profile, PEER_DISCOVERY.sic_weight, reasons),
        model_score(target, candidate_profile, PEER_DISCOVERY.business_model_weight, reasons),
        size_score(target, candidate_profile, PEER_DISCOVERY.size_weight, reasons),
        numeric_similarity("revenue_growth", target, candidate_profile, PEER_DISCOVERY.growth_weight, 0.20, reasons),
        numeric_similarity("operating_margin", target, candidate_profile, PEER_DISCOVERY.margin_weight, 0.20, reasons),
    ]
    total_weight = sum(weight for _, weight in pieces)
    score = sum(value * weight for value, weight in pieces) / total_weight if total_weight else 0.0
    return score, reasons


def categorical_score(name: str, target: Mapping[str, object], candidate: Mapping[str, object], weight: float, reasons: list[str]) -> tuple[float, float]:
    left, right = target.get(name), candidate.get(name)
    if not left or not right:
        return 0.0, 0.0
    match = left == right
    reasons.append(f"{name} {'match' if match else 'mismatch'}")
    return (1.0 if match else 0.0), weight


def sic_score(target: Mapping[str, object], candidate: Mapping[str, object], weight: float, reasons: list[str]) -> tuple[float, float]:
    left, right = normalized_text(target.get("sic")), normalized_text(candidate.get("sic"))
    if not left or not right:
        return 0.0, 0.0
    if left == right:
        reasons.append("sic exact")
        return 1.0, weight
    if left[:2] == right[:2]:
        reasons.append("sic family")
        return 0.6, weight
    reasons.append("sic mismatch")
    return 0.0, weight


def model_score(target: Mapping[str, object], candidate: Mapping[str, object], weight: float, reasons: list[str]) -> tuple[float, float]:
    left, right = normalized_model(target.get("business_model")), normalized_model(candidate.get("business_model"))
    if not left or not right:
        return 0.0, 0.0
    match = left == right
    reasons.append(f"business_model {'match' if match else 'mismatch'}")
    return (1.0 if match else 0.0), weight


def size_score(target: Mapping[str, object], candidate: Mapping[str, object], weight: float, reasons: list[str]) -> tuple[float, float]:
    left, right = safe_float(target.get("market_cap")), safe_float(candidate.get("market_cap"))
    if left is None or right is None:
        return 0.0, 0.0
    ratio = min(left, right) / max(left, right) if max(left, right) else 0.0
    reasons.append(f"size similarity {ratio:.2f}")
    return ratio, weight


def numeric_similarity(name: str, target: Mapping[str, object], candidate: Mapping[str, object], weight: float, tolerance: float, reasons: list[str]) -> tuple[float, float]:
    left, right = safe_float(target.get(name)), safe_float(candidate.get(name))
    if left is None or right is None:
        return 0.0, 0.0
    score = max(0.0, 1.0 - abs(left - right) / tolerance)
    reasons.append(f"{name} similarity {score:.2f}")
    return score, weight


def merge_candidates(explicit: Sequence[Mapping[str, object]], discovered: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen = set()
    for source in (explicit, discovered):
        for candidate in source:
            ticker = normalized_text(first_present(candidate, "ticker", "symbol"))
            key = ticker or str(candidate)
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(candidate))
    return merged


def sequence_of_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]
