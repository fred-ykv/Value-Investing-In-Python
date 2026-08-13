"""Data source adapters and lineage-aware values."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Dict, Mapping, Optional, Sequence

from .config import DATA_SOURCE_CONFIDENCE


@dataclass(frozen=True)
class MetricValue:
    name: str
    value: Optional[float]
    source: str
    confidence: float
    note: str = ""
    source_url: str | None = None
    source_document: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    filing_date: date | None = None
    as_of: datetime | None = None
    currency: str | None = None
    scale: str | None = None
    basis: str = "reported"
    is_fallback: bool = False
    formula: str | None = None

    @property
    def is_available(self) -> bool:
        return self.value is not None and math.isfinite(self.value)


MetricObservation = MetricValue


@dataclass(frozen=True)
class FetchResult:
    source: str
    ok: bool
    payload: Any = None
    confidence: float = 0.0
    error: str = ""


def confidence_for_source(source: str) -> float:
    return DATA_SOURCE_CONFIDENCE.get(source.lower(), DATA_SOURCE_CONFIDENCE["fallback"])


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            text = value.strip().replace(",", "").replace("$", "")
            if text in {"", "-", "nan", "None"}:
                return default
            if text.endswith("%"):
                return float(text[:-1]) / 100.0
            suffix = text[-1:].upper()
            if suffix in {"K", "M", "B", "T"}:
                return float(text[:-1]) * {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
            return float(text)
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def metric_value(
    name: str,
    value: Any,
    source: str,
    note: str = "",
    *,
    source_url: str | None = None,
    source_document: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    filing_date: date | None = None,
    as_of: datetime | None = None,
    currency: str | None = None,
    scale: str | None = None,
    basis: str | None = None,
    is_fallback: bool | None = None,
    formula: str | None = None,
    confidence: float | None = None,
) -> MetricValue:
    numeric = safe_float(value)
    resolved_source = source if numeric is not None else "missing"
    fallback = bool(is_fallback) or source == "fallback"
    return MetricValue(
        name,
        numeric,
        resolved_source,
        confidence if confidence is not None and numeric is not None else confidence_for_source(source) if numeric is not None else 0.0,
        note,
        source_url=source_url,
        source_document=source_document,
        period_start=period_start,
        period_end=period_end,
        filing_date=filing_date,
        as_of=as_of,
        currency=currency,
        scale=scale,
        basis=basis or ("fallback" if fallback else "reported"),
        is_fallback=fallback,
        formula=formula,
    )


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def weighted_confidence(*metrics: MetricValue) -> float:
    values = [item.confidence for item in metrics if item.is_available]
    return sum(values) / len(values) if values else 0.0


def get_mapping_value(data: Mapping[str, Any], *names: str, source: str = "manual") -> MetricValue:
    normalized = {str(k).strip().lower(): v for k, v in data.items()}
    for name in names:
        key = name.strip().lower()
        if key in normalized:
            raw_value = normalized[key]
            if isinstance(raw_value, MetricValue):
                return replace(raw_value, name=names[0])
            return metric_value(name, raw_value, source)
    return MetricValue(names[0], None, "missing", 0.0, "not found")


def parse_finviz_snapshot(html: str, source_url: str | None = None, as_of: datetime | None = None) -> Dict[str, MetricValue]:
    pairs: Dict[str, MetricValue] = {}
    pattern = r">([^<>]{1,40})</td>\s*<td[^>]*>([^<>]{1,80})</td>"
    for label, raw_value in re.findall(pattern, html):
        value = safe_float(raw_value)
        if value is not None:
            pairs[label.strip()] = metric_value(
                label.strip(),
                value,
                "finviz",
                raw_value.strip(),
                source_url=source_url,
                source_document="finviz snapshot",
                as_of=as_of or datetime.utcnow(),
                basis="reported",
            )
    return pairs


class YahooFinanceClient:
    def __init__(self, ticker: str):
        self.ticker = ticker.upper().strip()

    def fetch_info(self) -> FetchResult:
        try:
            import yfinance as yf  # type: ignore
            info = yf.Ticker(self.ticker).info or {}
            return FetchResult("yfinance", True, info, confidence_for_source("yfinance"))
        except Exception as exc:
            return FetchResult("yfinance", False, error=str(exc))

    def fetch_financial_statements(self) -> FetchResult:
        try:
            import yfinance as yf  # type: ignore
            from .financial_statements import FinancialStatements

            ticker = yf.Ticker(self.ticker)
            info = getattr(ticker, "info", {}) or {}
            currency = safe_text(info.get("financialCurrency") or info.get("currency"))
            quote_currency = safe_text(info.get("currency") or info.get("financialCurrency"))
            source_url = f"https://finance.yahoo.com/quote/{self.ticker}"
            financials = getattr(ticker, "financials", None)
            balance_sheet = getattr(ticker, "balance_sheet", None)
            cashflow = getattr(ticker, "cashflow", None)
            income = {
                "revenue": _latest_statement_metric(financials, ("Total Revenue", "Operating Revenue", "Revenue"), source_url=source_url, source_document="Yahoo Finance income statement", currency=currency),
                "ebit": _latest_statement_metric(financials, ("Operating Income", "EBIT"), source_url=source_url, source_document="Yahoo Finance income statement", currency=currency),
                "net_income": _latest_statement_metric(financials, ("Net Income", "Net Income Common Stockholders"), source_url=source_url, source_document="Yahoo Finance income statement", currency=currency),
                "tax_provision": _latest_statement_metric(financials, ("Tax Provision", "Income Tax Expense"), source_url=source_url, source_document="Yahoo Finance income statement", currency=currency),
                "interest_expense": _latest_statement_metric(financials, ("Interest Expense",), source_url=source_url, source_document="Yahoo Finance income statement", currency=currency),
            }
            balance = {
                "total_assets": _latest_statement_metric(balance_sheet, ("Total Assets",), source_url=source_url, source_document="Yahoo Finance balance sheet", currency=currency),
                "total_liabilities": _latest_statement_metric(balance_sheet, ("Total Liabilities Net Minority Interest", "Total Liabilities"), source_url=source_url, source_document="Yahoo Finance balance sheet", currency=currency),
                "equity": _latest_statement_metric(balance_sheet, ("Common Stock Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"), source_url=source_url, source_document="Yahoo Finance balance sheet", currency=currency),
                "cash": _latest_statement_metric(balance_sheet, ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"), source_url=source_url, source_document="Yahoo Finance balance sheet", currency=currency),
                "total_debt": _latest_statement_metric(balance_sheet, ("Total Debt", "Long Term Debt"), source_url=source_url, source_document="Yahoo Finance balance sheet", currency=currency),
                "current_assets": _latest_statement_metric(balance_sheet, ("Current Assets", "Total Current Assets"), source_url=source_url, source_document="Yahoo Finance balance sheet", currency=currency),
                "current_liabilities": _latest_statement_metric(balance_sheet, ("Current Liabilities", "Total Current Liabilities"), source_url=source_url, source_document="Yahoo Finance balance sheet", currency=currency),
            }
            cash_flow = {
                "cfo": _latest_statement_metric(cashflow, ("Operating Cash Flow", "Total Cash From Operating Activities"), source_url=source_url, source_document="Yahoo Finance cash flow statement", currency=currency),
                "capex": _latest_statement_metric(cashflow, ("Capital Expenditure", "Capital Expenditures"), source_url=source_url, source_document="Yahoo Finance cash flow statement", currency=currency),
                "depreciation_amortization": _latest_statement_metric(cashflow, ("Depreciation And Amortization", "Depreciation"), source_url=source_url, source_document="Yahoo Finance cash flow statement", currency=currency),
                "change_in_nwc": _latest_statement_metric(cashflow, ("Change In Working Capital", "Change In Other Working Capital"), source_url=source_url, source_document="Yahoo Finance cash flow statement", currency=currency),
            }
            market = {
                "price": _info_metric("price", info.get("currentPrice") or info.get("regularMarketPrice"), info, source_url, quote_currency),
                "shares": _info_metric("shares", info.get("sharesOutstanding"), info, source_url, None, scale="shares"),
                "market_cap": _info_metric("market_cap", info.get("marketCap"), info, source_url, quote_currency),
                "beta": _info_metric("beta", info.get("beta"), info, source_url, None),
                "revenue_growth": _info_metric("revenue_growth", info.get("revenueGrowth"), info, source_url, None),
                "dividend_per_share": _info_metric("dividend_per_share", info.get("dividendRate"), info, source_url, quote_currency),
            }
            if not market["revenue_growth"].is_available:
                market["revenue_growth"] = _growth_from_statement(financials, ("Total Revenue", "Operating Revenue", "Revenue"), source_url=source_url)
            statements = FinancialStatements(self.ticker, _drop_none(income), _drop_none(balance), _drop_none(cash_flow), _drop_none(market), info, "yfinance")
            return FetchResult("yfinance", True, statements, confidence_for_source("yfinance"))
        except Exception as exc:
            return FetchResult("yfinance", False, error=str(exc))


def _latest_statement_metric(
    statement: Any,
    aliases: Sequence[str],
    *,
    source_url: str | None = None,
    source_document: str | None = None,
    currency: str | None = None,
) -> MetricValue:
    row = _find_statement_row(statement, aliases)
    if row is None:
        return MetricValue(aliases[0], None, "missing", 0.0, "not found")
    row_label = str(getattr(row, "name", aliases[0]))
    for period, value in _iter_row_items(row):
        numeric = safe_float(value)
        if numeric is not None:
            return metric_value(
                aliases[0],
                numeric,
                "yfinance",
                f"statement row: {row_label}",
                source_url=source_url,
                source_document=source_document,
                period_end=_period_to_date(period),
                currency=currency,
                scale="raw",
                basis="reported",
            )
    return MetricValue(aliases[0], None, "missing", 0.0, "not found")


def _latest_statement_value(statement: Any, aliases: Sequence[str]) -> Optional[float]:
    return _latest_statement_metric(statement, aliases).value


def _growth_from_statement(statement: Any, aliases: Sequence[str], source_url: str | None = None) -> MetricValue:
    row = _find_statement_row(statement, aliases)
    if row is None:
        return MetricValue("revenue_growth", None, "missing", 0.0, "not found")
    items = [(period, safe_float(value)) for period, value in _iter_row_items(row)]
    items = [(period, value) for period, value in items if value is not None]
    if len(items) < 2 or items[1][1] == 0:
        return MetricValue("revenue_growth", None, "missing", 0.0, "requires two revenue periods")
    growth = (items[0][1] / items[1][1]) - 1.0
    return metric_value(
        "revenue_growth",
        growth,
        "derived",
        "latest revenue period divided by previous revenue period minus one",
        source_url=source_url,
        source_document="Yahoo Finance income statement",
        period_end=_period_to_date(items[0][0]),
        basis="derived",
        formula="latest_revenue_divided_by_prior_revenue_minus_one",
    )


def _find_statement_row(statement: Any, aliases: Sequence[str]) -> Any:
    if statement is None or getattr(statement, "empty", True):
        return None
    index = {_normalize_label(idx): idx for idx in getattr(statement, "index", [])}
    for alias in aliases:
        normalized = _normalize_label(alias)
        if normalized in index:
            return statement.loc[index[normalized]]
    for alias in aliases:
        normalized = _normalize_label(alias)
        for found, original in index.items():
            if normalized in found:
                return statement.loc[original]
    return None


def _normalize_label(label: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(label).lower()).strip()


def _iter_row_items(row: Any) -> list[tuple[Any, Any]]:
    if hasattr(row, "dropna") and hasattr(row, "items"):
        return list(row.dropna().items())
    if isinstance(row, Mapping):
        return [(key, value) for key, value in row.items() if value is not None]
    values = getattr(row, "tolist", lambda: [])()
    return list(enumerate(values))


def _period_to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        return None


def _info_metric(name: str, value: Any, info: Mapping[str, Any], source_url: str, currency: str | None, scale: str = "raw") -> MetricValue:
    return metric_value(
        name,
        value,
        "yfinance",
        "Yahoo Finance quote/profile info",
        source_url=source_url,
        source_document="Yahoo Finance quote/profile info",
        as_of=datetime.utcnow(),
        currency=currency,
        scale=scale,
        basis="reported",
    )


def safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _drop_none(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in values.items()
        if not (v is None or (isinstance(v, MetricValue) and v.value is None))
    }
