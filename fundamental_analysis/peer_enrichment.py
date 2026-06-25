"""Peer candidate enrichment with source and confidence tracking."""
from __future__ import annotations

from typing import Callable, Mapping, Sequence

from .config import PEER_ENRICHMENT
from .data_sources import FetchResult, YahooFinanceClient, confidence_for_source, safe_float


InfoFetcher = Callable[[str], Mapping[str, object] | FetchResult | None]


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "sector": ("sector",),
    "industry": ("industry",),
    "market_cap": ("market_cap", "marketCap"),
    "price_to_earnings": ("price_to_earnings", "trailingPE", "forwardPE"),
    "price_to_book": ("price_to_book", "priceToBook"),
    "ev_to_sales": ("ev_to_sales", "enterpriseToRevenue"),
    "ev_to_ebitda": ("ev_to_ebitda", "enterpriseToEbitda"),
    "price_to_sales": ("price_to_sales", "priceToSalesTrailing12Months"),
    "revenue_growth": ("revenue_growth", "revenueGrowth"),
    "operating_margin": ("operating_margin", "operatingMargins"),
    "gross_margin": ("gross_margin", "grossMargins"),
    "debt_to_equity": ("debt_to_equity", "debtToEquity"),
    "current_ratio": ("current_ratio", "currentRatio"),
}


def enrich_peer_candidates(
    candidates: Sequence[Mapping[str, object]],
    *,
    fetch_info: InfoFetcher | None = None,
    use_yahoo: bool | None = None,
) -> list[dict[str, object]]:
    enriched = []
    should_use_yahoo = PEER_ENRICHMENT.use_yahoo_info if use_yahoo is None else use_yahoo
    fetcher = fetch_info or yahoo_info_fetcher
    for raw_candidate in candidates:
        candidate = dict(raw_candidate)
        sources = initial_metric_sources(candidate)
        warnings = list(candidate.get("peer_enrichment_warnings", [])) if isinstance(candidate.get("peer_enrichment_warnings"), list) else []
        ticker = str(candidate.get("ticker") or candidate.get("symbol") or "").strip().upper()

        if should_use_yahoo and ticker:
            fetched = fetcher(ticker)
            payload, source, ok, error = unpack_fetch_result(fetched)
            if ok and payload:
                fill_candidate_fields(candidate, payload, source, sources)
            elif error:
                warnings.append(f"{source} failed: {error}")

        candidate["_peer_metric_sources"] = sources
        candidate["peer_data_confidence"] = peer_data_confidence(candidate, sources)
        if warnings:
            candidate["peer_enrichment_warnings"] = warnings
        enriched.append(candidate)
    return enriched


def yahoo_info_fetcher(ticker: str) -> FetchResult:
    return YahooFinanceClient(ticker).fetch_info()


def unpack_fetch_result(value: Mapping[str, object] | FetchResult | None) -> tuple[Mapping[str, object], str, bool, str]:
    if isinstance(value, FetchResult):
        payload = value.payload if isinstance(value.payload, Mapping) else {}
        return payload, value.source, value.ok, value.error
    if isinstance(value, Mapping):
        return value, "yfinance", True, ""
    return {}, "yfinance", False, "no payload"


def fill_candidate_fields(candidate: dict[str, object], payload: Mapping[str, object], source: str, sources: dict[str, str]) -> None:
    for field_name, aliases in FIELD_ALIASES.items():
        if has_usable_value(candidate.get(field_name)):
            continue
        value = first_present(payload, *aliases)
        normalized = normalize_field_value(field_name, value)
        if has_usable_value(normalized):
            candidate[field_name] = normalized
            sources[field_name] = source


def normalize_field_value(field_name: str, value: object) -> object:
    if field_name in {"sector", "industry"}:
        return value if value not in (None, "") else None
    numeric = safe_float(value)
    if numeric is None:
        return None
    if field_name == "debt_to_equity" and numeric > 10:
        return numeric / 100.0
    return numeric


def initial_metric_sources(candidate: Mapping[str, object]) -> dict[str, str]:
    default_source = str(candidate.get("candidate_source") or "manual")
    existing = candidate.get("_peer_metric_sources")
    sources = dict(existing) if isinstance(existing, Mapping) else {}
    for field_name in FIELD_ALIASES:
        if has_usable_value(candidate.get(field_name)):
            sources.setdefault(field_name, default_source)
    return sources


def peer_data_confidence(candidate: Mapping[str, object], sources: Mapping[str, str]) -> float:
    confidence_values = []
    for field_name in FIELD_ALIASES:
        if has_usable_value(candidate.get(field_name)):
            confidence_values.append(confidence_for_source(sources.get(field_name, "fallback")))
    return sum(confidence_values) / len(confidence_values) if confidence_values else 0.0


def has_usable_value(value: object) -> bool:
    if isinstance(value, str):
        return value.strip() != ""
    return value is not None


def first_present(values: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        if values.get(key) not in (None, ""):
            return values[key]
    return None
