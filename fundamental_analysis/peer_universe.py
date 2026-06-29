"""Peer universe providers.

This module supplies candidate peers before the stricter discovery and
equivalence scoring steps. It intentionally prefers transparent, auditable
rules over opaque broad-screen matching.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .config import PEER_UNIVERSE


@dataclass(frozen=True)
class PeerUniverseResult:
    candidates: list[dict[str, object]]
    sources: list[str]
    warnings: list[str]


DEFAULT_SEED_UNIVERSES: dict[str, tuple[dict[str, object], ...]] = {
    "traditional_auto": (
        {"ticker": "GM", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "traditional_auto"},
        {"ticker": "STLA", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "traditional_auto"},
        {"ticker": "TM", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "traditional_auto"},
        {"ticker": "HMC", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "traditional_auto"},
    ),
    "ev_pure_play": (
        {"ticker": "TSLA", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "ev_pure_play"},
        {"ticker": "RIVN", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "ev_pure_play"},
        {"ticker": "LCID", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "ev_pure_play"},
        {"ticker": "NIO", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "ev_pure_play"},
    ),
    "bank": (
        {"ticker": "JPM", "sector": "Financial Services", "industry": "Banks - Diversified", "sic": "6021", "business_model": "bank"},
        {"ticker": "BAC", "sector": "Financial Services", "industry": "Banks - Diversified", "sic": "6021", "business_model": "bank"},
        {"ticker": "WFC", "sector": "Financial Services", "industry": "Banks - Diversified", "sic": "6021", "business_model": "bank"},
        {"ticker": "C", "sector": "Financial Services", "industry": "Banks - Diversified", "sic": "6021", "business_model": "bank"},
        {"ticker": "USB", "sector": "Financial Services", "industry": "Banks - Regional", "sic": "6021", "business_model": "bank"},
        {"ticker": "PNC", "sector": "Financial Services", "industry": "Banks - Regional", "sic": "6021", "business_model": "bank"},
    ),
    "saas": (
        {"ticker": "CRM", "sector": "Technology", "industry": "Software - Application", "sic": "7372", "business_model": "saas"},
        {"ticker": "NOW", "sector": "Technology", "industry": "Software - Application", "sic": "7372", "business_model": "saas"},
        {"ticker": "ADBE", "sector": "Technology", "industry": "Software - Application", "sic": "7372", "business_model": "saas"},
        {"ticker": "SNOW", "sector": "Technology", "industry": "Software - Application", "sic": "7372", "business_model": "saas"},
        {"ticker": "DDOG", "sector": "Technology", "industry": "Software - Application", "sic": "7372", "business_model": "saas"},
    ),
    "semiconductor": (
        {"ticker": "NVDA", "sector": "Technology", "industry": "Semiconductors", "sic": "3674", "business_model": "semiconductor"},
        {"ticker": "AMD", "sector": "Technology", "industry": "Semiconductors", "sic": "3674", "business_model": "semiconductor"},
        {"ticker": "INTC", "sector": "Technology", "industry": "Semiconductors", "sic": "3674", "business_model": "semiconductor"},
        {"ticker": "QCOM", "sector": "Technology", "industry": "Semiconductors", "sic": "3674", "business_model": "semiconductor"},
        {"ticker": "AVGO", "sector": "Technology", "industry": "Semiconductors", "sic": "3674", "business_model": "semiconductor"},
    ),
    "metal_fabrication": (
        {"ticker": "MLI", "sector": "Industrials", "industry": "Metal Fabrication", "sic": "3350", "business_model": "metal_fabrication"},
        {"ticker": "ATI", "sector": "Industrials", "industry": "Metal Fabrication", "sic": "3312", "business_model": "metal_fabrication"},
        {"ticker": "CRS", "sector": "Industrials", "industry": "Metal Fabrication", "sic": "3312", "business_model": "metal_fabrication"},
        {"ticker": "CENX", "sector": "Industrials", "industry": "Aluminum", "sic": "3350", "business_model": "metal_fabrication"},
        {"ticker": "NUE", "sector": "Basic Materials", "industry": "Steel", "sic": "3312", "business_model": "metal_fabrication"},
        {"ticker": "STLD", "sector": "Basic Materials", "industry": "Steel", "sic": "3312", "business_model": "metal_fabrication"},
    ),
    "marketplace": (
        {"ticker": "AMZN", "sector": "Consumer Cyclical", "industry": "Internet Retail", "sic": "5961", "business_model": "marketplace"},
        {"ticker": "MELI", "sector": "Consumer Cyclical", "industry": "Internet Retail", "sic": "5961", "business_model": "marketplace"},
        {"ticker": "EBAY", "sector": "Consumer Cyclical", "industry": "Internet Retail", "sic": "5961", "business_model": "marketplace"},
        {"ticker": "ETSY", "sector": "Consumer Cyclical", "industry": "Internet Retail", "sic": "5961", "business_model": "marketplace"},
    ),
    "physical_retail": (
        {"ticker": "WMT", "sector": "Consumer Defensive", "industry": "Discount Stores", "sic": "5331", "business_model": "physical_retail"},
        {"ticker": "TGT", "sector": "Consumer Defensive", "industry": "Discount Stores", "sic": "5331", "business_model": "physical_retail"},
        {"ticker": "COST", "sector": "Consumer Defensive", "industry": "Discount Stores", "sic": "5331", "business_model": "physical_retail"},
        {"ticker": "HD", "sector": "Consumer Cyclical", "industry": "Home Improvement Retail", "sic": "5211", "business_model": "physical_retail"},
        {"ticker": "LOW", "sector": "Consumer Cyclical", "industry": "Home Improvement Retail", "sic": "5211", "business_model": "physical_retail"},
    ),
    "reit": (
        {"ticker": "PLD", "sector": "Real Estate", "industry": "REIT - Industrial", "sic": "6798", "business_model": "reit"},
        {"ticker": "AMT", "sector": "Real Estate", "industry": "REIT - Specialty", "sic": "6798", "business_model": "reit"},
        {"ticker": "SPG", "sector": "Real Estate", "industry": "REIT - Retail", "sic": "6798", "business_model": "reit"},
        {"ticker": "O", "sector": "Real Estate", "industry": "REIT - Retail", "sic": "6798", "business_model": "reit"},
        {"ticker": "EQIX", "sector": "Real Estate", "industry": "REIT - Specialty", "sic": "6798", "business_model": "reit"},
    ),
    "large_pharma": (
        {"ticker": "JNJ", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "sic": "2834", "business_model": "large_pharma"},
        {"ticker": "PFE", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "sic": "2834", "business_model": "large_pharma"},
        {"ticker": "MRK", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "sic": "2834", "business_model": "large_pharma"},
        {"ticker": "ABBV", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "sic": "2834", "business_model": "large_pharma"},
        {"ticker": "BMY", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "sic": "2834", "business_model": "large_pharma"},
    ),
}

INDUSTRY_TO_SEED_KEY = {
    "auto manufacturers": "traditional_auto",
    "banks - diversified": "bank",
    "banks - regional": "bank",
    "software - application": "saas",
    "semiconductors": "semiconductor",
    "metal fabrication": "metal_fabrication",
    "aluminum": "metal_fabrication",
    "steel": "metal_fabrication",
    "internet retail": "marketplace",
    "discount stores": "physical_retail",
    "drug manufacturers - general": "large_pharma",
}

SIC_PREFIX_TO_SEED_KEY = {
    "371": "traditional_auto",
    "602": "bank",
    "737": "saas",
    "367": "semiconductor",
    "331": "metal_fabrication",
    "335": "metal_fabrication",
    "596": "marketplace",
    "533": "physical_retail",
    "679": "reit",
    "283": "large_pharma",
}


def build_peer_universe(target_info: Mapping[str, object], market_data: Mapping[str, object]) -> PeerUniverseResult:
    candidates: list[dict[str, object]] = []
    sources: list[str] = []
    warnings: list[str] = []
    target_ticker = normalize(first_present(target_info, "ticker", "symbol") or first_present(market_data, "ticker", "symbol"))

    configured = configured_universe(target_info, market_data)
    if configured:
        sources.append("configured_peer_universe")
        candidates.extend(configured)

    has_manual_universe = any(
        market_data.get(name) for name in ("peer_candidates", "peer_universe", "candidate_universe", "comparable_universe")
    )
    if PEER_UNIVERSE.use_builtin_seed_universe and not has_manual_universe:
        keys = seed_keys_for_target(target_info)
        for key in keys:
            sources.append(f"builtin_seed:{key}")
            candidates.extend(dict(candidate, candidate_source=f"builtin_seed:{key}") for candidate in DEFAULT_SEED_UNIVERSES.get(key, ()))

    deduped = dedupe_candidates(candidates, target_ticker)
    if not deduped:
        warnings.append("no_peer_universe_candidates")
    return PeerUniverseResult(deduped[: PEER_UNIVERSE.max_seed_candidates], unique(sources), warnings)


def configured_universe(target_info: Mapping[str, object], market_data: Mapping[str, object]) -> list[dict[str, object]]:
    value = market_data.get("configured_peer_universe")
    if value is None:
        value = market_data.get("peer_universe_config")
    if isinstance(value, Mapping):
        selected: list[object] = []
        normalized_mapping = {normalize(key): raw_value for key, raw_value in value.items()}
        for key in configured_lookup_keys(target_info):
            raw = normalized_mapping.get(key)
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                selected.extend(raw)
        return normalize_candidates(selected, "configured_peer_universe")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return normalize_candidates(value, "configured_peer_universe")
    return []


def configured_lookup_keys(target_info: Mapping[str, object]) -> list[str]:
    raw_keys = [
        first_present(target_info, "ticker", "symbol"),
        target_info.get("business_model"),
        target_info.get("industry"),
        target_info.get("sector"),
        target_info.get("sic"),
        "default",
    ]
    return unique([normalize(key) for key in raw_keys if normalize(key)])


def seed_keys_for_target(target_info: Mapping[str, object]) -> list[str]:
    business_model = normalize(target_info.get("business_model"))
    industry = normalize(target_info.get("industry"))
    sic = normalize(target_info.get("sic"))
    keys = []
    if business_model in DEFAULT_SEED_UNIVERSES:
        keys.append(business_model)
    if industry in INDUSTRY_TO_SEED_KEY:
        keys.append(INDUSTRY_TO_SEED_KEY[industry])
    for prefix, key in SIC_PREFIX_TO_SEED_KEY.items():
        if sic.startswith(prefix):
            keys.append(key)
            break
    return unique(keys)


def normalize_candidates(values: Sequence[object], source: str) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for item in values:
        if isinstance(item, str):
            normalized.append({"ticker": item, "candidate_source": source})
        elif isinstance(item, Mapping):
            candidate = dict(item)
            candidate.setdefault("candidate_source", source)
            normalized.append(candidate)
    return normalized


def dedupe_candidates(candidates: Sequence[Mapping[str, object]], target_ticker: str) -> list[dict[str, object]]:
    seen = set()
    deduped: list[dict[str, object]] = []
    for candidate in candidates:
        ticker = normalize(first_present(candidate, "ticker", "symbol"))
        key = ticker or str(sorted(candidate.items()))
        if ticker and ticker == target_ticker:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(candidate))
    return deduped


def first_present(values: Mapping[str, object], *names: str) -> object:
    for name in names:
        value = values.get(name)
        if value not in (None, ""):
            return value
    return None


def normalize(value: object) -> str:
    return str(value).strip().lower() if value not in (None, "") else ""


def unique(values: Sequence[str]) -> list[str]:
    output: list[str] = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
