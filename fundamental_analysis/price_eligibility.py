"""Reviewed trading boundaries, separate from contractual terminal cash flows."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import TYPE_CHECKING

from .benchmark_universe import HISTORICAL_LIFECYCLE_CASES, HistoricalLifecycleEvent

if TYPE_CHECKING:
    from .historical_prices import PriceSeries


class PriceEligibilityError(ValueError):
    """A quality failure must not trigger another provider's ticker fallback."""


@dataclass(frozen=True)
class LifecycleTradingRule:
    ticker: str
    first_ineligible_date: date
    evidence_kind: str
    source_url: str
    security_class: str


# Each boundary is inclusive. Requested halts are distinguished from reported
# suspensions; cancellation with no intraday timestamp uses daily resolution.
TRADING_RULES = (
    LifecycleTradingRule("MDLA", date(2021, 10, 29), "reported_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1540184/000114036121036202/brhc10030210_8k.htm", "common_stock"),
    LifecycleTradingRule("CLDR", date(2021, 10, 8), "reported_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1535379/000119312521294924/d223205d8k.htm", "common_stock"),
    LifecycleTradingRule("CSPR", date(2022, 1, 25), "requested_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1598674/000114036122002541/brhc10033043_8k.htm", "common_stock"),
    LifecycleTradingRule("PLAN", date(2022, 6, 22), "reported_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1540755/000119312522178282/d333986d8k.htm", "common_stock"),
    LifecycleTradingRule("ZEN", date(2022, 11, 22), "requested_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1463172/000114036122042681/brhc10044488_8k.htm", "common_stock"),
    LifecycleTradingRule("COUP", date(2023, 2, 28), "reported_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1385867/000119312523054081/d455192d8k.htm", "common_stock"),
    LifecycleTradingRule("MNTV", date(2023, 6, 1), "reported_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1739936/000114036123027837/ny20009286x1_8k.htm", "common_stock"),
    LifecycleTradingRule("XM", date(2023, 6, 28), "reported_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1747748/000162828023023743/xm-20230628.htm", "class_a_common_stock"),
    LifecycleTradingRule("BBBY", date(2023, 9, 30), "cancellation_daily_resolution",
        "https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010dex991.htm", "common_stock"),
    LifecycleTradingRule("NEWR", date(2023, 11, 8), "reported_preopen_suspension",
        "https://www.sec.gov/Archives/edgar/data/1448056/000119312523273042/d469974d8k.htm", "common_stock"),
)


def content_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=lambda value: value.isoformat(), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def trading_identity(ticker: str) -> dict:
    # Delayed import keeps the price transport independent of this consumer.
    from .institutional_prices import TIINGO_LIFECYCLE_MAPPINGS

    cases = {case.ticker: case for case in HISTORICAL_LIFECYCLE_CASES}
    rules = {rule.ticker: rule for rule in TRADING_RULES}
    mappings = {mapping.canonical_ticker: mapping for mapping in TIINGO_LIFECYCLE_MAPPINGS}
    if len(rules) != len(TRADING_RULES) or set(rules) != set(cases):
        raise PriceEligibilityError("Cadastro de negociabilidade incompleto ou duplicado")
    if ticker not in cases or ticker not in mappings:
        raise PriceEligibilityError(f"Evento/classe sem regra de negociabilidade revisada: {ticker}")
    case, rule, mapping = cases[ticker], rules[ticker], mappings[ticker]
    return {
        "ticker": ticker, "issuer_cik": case.cik,
        "security_id": mapping.security_id, "security_class": rule.security_class,
        "event": json.loads(json.dumps(asdict(case.lifecycle_event), default=str)),
        "first_ineligible_date": rule.first_ineligible_date.isoformat(),
        "evidence_kind": rule.evidence_kind, "source_url": rule.source_url,
        "identity_basis": "curated_SEC_Tiingo_mapping_not_provider_certified_CIK_or_class",
    }


def apply_price_eligibility(
    series: PriceSeries, ticker: str, event: HistoricalLifecycleEvent | None,
) -> tuple[PriceSeries, dict]:
    ticker = ticker.upper().strip()
    known = any(case.ticker == ticker or case.cik == series.issuer_cik for case in HISTORICAL_LIFECYCLE_CASES)
    if event is None and not known:
        return series, {}
    identity = trading_identity(ticker)
    if event is None or json.loads(json.dumps(asdict(event), default=str)) != identity["event"]:
        raise PriceEligibilityError(f"Evento ausente ou divergente do cadastro SEC: {ticker}")
    if (series.ticker != ticker or series.issuer_cik != identity["issuer_cik"]
            or series.security_id != identity["security_id"]):
        raise PriceEligibilityError(f"Identidade/classe de preco nao reconciliada: {ticker}")
    if not _is_hash(series.input_evidence_sha256):
        raise PriceEligibilityError(f"Evidencia de entrada ausente para {ticker}; use Tiingo ou CSV com manifesto completo")
    seen = set()
    eligible, excluded = [], []
    boundary = date.fromisoformat(identity["first_ineligible_date"])
    for point in series.points:
        if point.day in seen:
            raise PriceEligibilityError(f"Preco duplicado em {ticker}: {point.day}")
        seen.add(point.day)
        for value in (point.adjusted_close, point.raw_close):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise PriceEligibilityError(f"Preco bruto/ajustado invalido em {ticker}: {point.day}")
        if point.volume is not None and (isinstance(point.volume, bool)
                or not isinstance(point.volume, (int, float))
                or not math.isfinite(point.volume) or point.volume < 0):
            raise PriceEligibilityError(f"Volume invalido em {ticker}: {point.day}")
        if point.day >= boundary:
            row = json.loads(json.dumps(asdict(point), default=str))
            excluded.append({
                **row, "row_sha256": content_hash(row),
                "reason": "on_or_after_reviewed_trading_boundary",
                "source_url": identity["source_url"],
            })
        else:
            eligible.append(point)
    if not eligible:
        raise PriceEligibilityError(f"Nenhum preco elegivel na janela de {ticker}")
    audit = {
        "schema_version": 1, "status": "eligible_with_audit", "identity": identity,
        "rule_sha256": content_hash(identity),
        "input_evidence_sha256": series.input_evidence_sha256,
        "raw_window_sha256": content_hash(asdict(series)),
        "raw_row_count": len(series.points), "eligible_row_count": len(eligible),
        "provider_last_date_in_window": max(seen).isoformat(),
        "last_eligible_date_in_window": max(p.day for p in eligible).isoformat(),
        "quarantined_rows": sorted(excluded, key=lambda row: row["day"]),
        "source": series.source,
        "volume_policy": "missing_or_zero_volume_alone_does_not_exclude",
    }
    audit["audit_sha256"] = content_hash(audit)
    return replace(series, points=tuple(eligible)), audit


def valid_price_eligibility_audit(audit: object, ticker: str, cik: str, terminal_date: date | None) -> bool:
    """Validate serialized telemetry; authenticity still requires its frozen inputs."""
    if not isinstance(audit, dict):
        return False
    try:
        identity = trading_identity(ticker)
        if (audit["schema_version"] != 1 or audit["status"] != "eligible_with_audit"
                or audit["identity"] != identity or cik != identity["issuer_cik"]
                or audit["rule_sha256"] != content_hash(identity)
                or not _is_hash(audit["input_evidence_sha256"])
                or not _is_hash(audit["raw_window_sha256"])
                or audit["audit_sha256"] != content_hash({k: v for k, v in audit.items() if k != "audit_sha256"})):
            return False
        last = date.fromisoformat(audit["last_eligible_date_in_window"])
        boundary = date.fromisoformat(identity["first_ineligible_date"])
        if last >= boundary or date.fromisoformat(audit["provider_last_date_in_window"]) < last:
            return False
        if terminal_date is None or terminal_date >= boundary or terminal_date > last:
            return False
        rows = audit["quarantined_rows"]
        if (audit["eligible_row_count"] <= 0
                or audit["raw_row_count"] != audit["eligible_row_count"] + len(rows)):
            return False
        for row in rows:
            if (date.fromisoformat(row["day"]) < boundary
                    or row["source_url"] != identity["source_url"]
                    or row["reason"] != "on_or_after_reviewed_trading_boundary"
                    or row["row_sha256"] != content_hash({key: row[key] for key in ("day", "adjusted_close", "raw_close", "volume")})):
                return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
