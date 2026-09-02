"""Peer candidate enrichment with source and confidence tracking."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from .config import PEER_ENRICHMENT
from .data_sources import FetchResult, YahooFinanceClient, confidence_for_source, safe_float


InfoFetcher = Callable[[str], Mapping[str, object] | FetchResult | None]


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "sector": ("sector",),
    "industry": ("industry",),
    "market_cap": ("market_cap", "marketCap"),
    "price_to_earnings": ("price_to_earnings", "trailingPE"),
    "price_to_book": ("price_to_book", "priceToBook"),
    "ev_to_sales": ("ev_to_sales", "enterpriseToRevenue"),
    "ev_to_ebitda": ("ev_to_ebitda", "enterpriseToEbitda"),
    "ev_to_ebit": ("ev_to_ebit",),
    "price_to_sales": ("price_to_sales", "priceToSalesTrailing12Months"),
    "enterprise_value": ("enterprise_value", "enterpriseValue"),
    "total_revenue": ("total_revenue", "totalRevenue"),
    "ebitda": ("ebitda",),
    "net_income": ("net_income", "netIncomeToCommon"),
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
        lineage = initial_metric_lineage(candidate, sources)
        warnings = list(candidate.get("peer_enrichment_warnings", [])) if isinstance(candidate.get("peer_enrichment_warnings"), list) else []
        ticker = str(candidate.get("ticker") or candidate.get("symbol") or "").strip().upper()

        if should_use_yahoo and ticker:
            fetched = fetcher(ticker)
            payload, source, ok, error = unpack_fetch_result(fetched)
            if ok and payload:
                observed_at = datetime.now(timezone.utc).isoformat()
                fill_candidate_fields(
                    candidate, payload, source, sources, lineage, ticker, observed_at
                )
                derive_candidate_multiples(
                    candidate, source, sources, lineage, ticker, observed_at
                )
            elif error:
                warnings.append(f"{source} failed: {error}")

        candidate["_peer_metric_sources"] = sources
        candidate["_peer_metric_lineage"] = lineage
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


def fill_candidate_fields(
    candidate: dict[str, object],
    payload: Mapping[str, object],
    source: str,
    sources: dict[str, str],
    lineage: dict[str, dict[str, object]],
    ticker: str,
    observed_at: str,
) -> None:
    for field_name, aliases in FIELD_ALIASES.items():
        if has_usable_value(candidate.get(field_name)):
            continue
        source_field, value = first_present_with_key(payload, *aliases)
        normalized = normalize_field_value(field_name, value)
        if has_usable_value(normalized):
            candidate[field_name] = normalized
            sources[field_name] = source
            lineage[field_name] = {
                "source": source,
                "source_url": _source_url(source, ticker),
                "source_document": _source_document(source),
                "as_of": observed_at,
                "basis": "reported",
                "source_field": source_field,
                "formula": None,
                "input_observations": [],
            }


def derive_candidate_multiples(
    candidate: dict[str, object],
    source: str,
    sources: dict[str, str],
    lineage: dict[str, dict[str, object]],
    ticker: str,
    observed_at: str,
) -> None:
    derived_source = f"{source}_derived" if source else "derived"
    market_cap = safe_float(candidate.get("market_cap"))
    enterprise_value = safe_float(candidate.get("enterprise_value"))
    total_revenue = safe_float(candidate.get("total_revenue"))
    ebitda = safe_float(candidate.get("ebitda"))
    net_income = safe_float(candidate.get("net_income"))
    operating_margin = safe_float(candidate.get("operating_margin"))
    ebit = None if total_revenue is None or operating_margin is None else total_revenue * operating_margin
    derived_values = {
        "price_to_sales": safe_positive_ratio(market_cap, total_revenue),
        "ev_to_sales": safe_positive_ratio(enterprise_value, total_revenue),
        "ev_to_ebitda": safe_positive_ratio(enterprise_value, ebitda),
        "ev_to_ebit": safe_positive_ratio(enterprise_value, ebit),
        "price_to_earnings": safe_positive_ratio(market_cap, net_income),
    }
    derivations = {
        "price_to_sales": ("market_cap_divided_by_total_revenue", ("market_cap", "total_revenue")),
        "ev_to_sales": ("enterprise_value_divided_by_total_revenue", ("enterprise_value", "total_revenue")),
        "ev_to_ebitda": ("enterprise_value_divided_by_ebitda", ("enterprise_value", "ebitda")),
        "ev_to_ebit": ("enterprise_value_divided_by_derived_ebit", ("enterprise_value", "total_revenue", "operating_margin")),
        "price_to_earnings": ("market_cap_divided_by_net_income", ("market_cap", "net_income")),
    }
    for field_name, value in derived_values.items():
        if has_usable_value(candidate.get(field_name)) or not has_usable_value(value):
            continue
        candidate[field_name] = value
        sources[field_name] = derived_source
        formula, input_names = derivations[field_name]
        lineage[field_name] = {
            "source": derived_source,
            "source_url": _source_url(source, ticker),
            "source_document": _source_document(source),
            "as_of": observed_at,
                "basis": "derived",
                "source_field": None,
            "formula": formula,
            "input_observations": [
                {"name": name, "value": safe_float(candidate.get(name))}
                for name in input_names
            ],
        }


def safe_positive_ratio(numerator: object, denominator: object) -> float | None:
    left = safe_float(numerator)
    right = safe_float(denominator)
    if left is None or right is None or right <= 0:
        return None
    value = left / right
    return value if value > 0 else None


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


def initial_metric_lineage(
    candidate: Mapping[str, object], sources: Mapping[str, str]
) -> dict[str, dict[str, object]]:
    existing = candidate.get("_peer_metric_lineage")
    lineage = {
        str(name): dict(value)
        for name, value in existing.items()
        if isinstance(existing, Mapping) and isinstance(value, Mapping)
    } if isinstance(existing, Mapping) else {}
    for field_name in FIELD_ALIASES:
        if not has_usable_value(candidate.get(field_name)):
            continue
        lineage.setdefault(
            field_name,
            {
                "source": sources.get(field_name, "manual"),
                "source_url": candidate.get("source_url"),
                "source_document": candidate.get("source_document"),
                "as_of": candidate.get("as_of"),
                "basis": "reported",
                "source_field": field_name,
                "formula": None,
                "input_observations": [],
            },
        )
    return lineage


def _source_url(source: str, ticker: str) -> str | None:
    if source.startswith("yfinance") and ticker:
        return f"https://finance.yahoo.com/quote/{ticker}"
    return None


def _source_document(source: str) -> str:
    return "Yahoo Finance quote/profile info" if source.startswith("yfinance") else source


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


def first_present_with_key(
    values: Mapping[str, object], *keys: str
) -> tuple[str | None, object]:
    for key in keys:
        if values.get(key) not in (None, ""):
            return key, values[key]
    return None, None
