"""Data source adapters and lineage-aware values."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

from .config import DATA_SOURCE_CONFIDENCE


@dataclass(frozen=True)
class MetricValue:
    name: str
    value: Optional[float]
    source: str
    confidence: float
    note: str = ""

    @property
    def is_available(self) -> bool:
        return self.value is not None and math.isfinite(self.value)


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


def metric_value(name: str, value: Any, source: str, note: str = "") -> MetricValue:
    numeric = safe_float(value)
    return MetricValue(name, numeric, source if numeric is not None else "missing", confidence_for_source(source) if numeric is not None else 0.0, note)


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
            return metric_value(name, normalized[key], source)
    return MetricValue(names[0], None, "missing", 0.0, "not found")


def parse_finviz_snapshot(html: str) -> Dict[str, MetricValue]:
    pairs: Dict[str, MetricValue] = {}
    pattern = r">([^<>]{1,40})</td>\s*<td[^>]*>([^<>]{1,80})</td>"
    for label, raw_value in re.findall(pattern, html):
        value = safe_float(raw_value)
        if value is not None:
            pairs[label.strip()] = metric_value(label.strip(), value, "finviz", raw_value.strip())
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
            financials = getattr(ticker, "financials", None)
            balance_sheet = getattr(ticker, "balance_sheet", None)
            cashflow = getattr(ticker, "cashflow", None)
            income = {
                "revenue": _latest_statement_value(financials, ("Total Revenue", "Operating Revenue", "Revenue")),
                "ebit": _latest_statement_value(financials, ("Operating Income", "EBIT")),
                "net_income": _latest_statement_value(financials, ("Net Income", "Net Income Common Stockholders")),
                "tax_provision": _latest_statement_value(financials, ("Tax Provision", "Income Tax Expense")),
                "interest_expense": _latest_statement_value(financials, ("Interest Expense",)),
            }
            balance = {
                "total_assets": _latest_statement_value(balance_sheet, ("Total Assets",)),
                "total_liabilities": _latest_statement_value(balance_sheet, ("Total Liabilities Net Minority Interest", "Total Liabilities")),
                "equity": _latest_statement_value(balance_sheet, ("Common Stock Equity", "Stockholders Equity", "Total Equity Gross Minority Interest")),
                "cash": _latest_statement_value(balance_sheet, ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")),
                "total_debt": _latest_statement_value(balance_sheet, ("Total Debt", "Long Term Debt")),
                "current_assets": _latest_statement_value(balance_sheet, ("Current Assets", "Total Current Assets")),
                "current_liabilities": _latest_statement_value(balance_sheet, ("Current Liabilities", "Total Current Liabilities")),
            }
            cash_flow = {
                "cfo": _latest_statement_value(cashflow, ("Operating Cash Flow", "Total Cash From Operating Activities")),
                "capex": _latest_statement_value(cashflow, ("Capital Expenditure", "Capital Expenditures")),
                "depreciation_amortization": _latest_statement_value(cashflow, ("Depreciation And Amortization", "Depreciation")),
            }
            market = {
                "price": safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
                "shares": safe_float(info.get("sharesOutstanding")),
                "market_cap": safe_float(info.get("marketCap")),
                "beta": safe_float(info.get("beta")),
                "revenue_growth": safe_float(info.get("revenueGrowth")),
                "dividend_per_share": safe_float(info.get("dividendRate")),
            }
            if market["revenue_growth"] is None:
                market["revenue_growth"] = _growth_from_statement(financials, ("Total Revenue", "Operating Revenue", "Revenue"))
            statements = FinancialStatements(self.ticker, _drop_none(income), _drop_none(balance), _drop_none(cash_flow), _drop_none(market), info, "yfinance")
            return FetchResult("yfinance", True, statements, confidence_for_source("yfinance"))
        except Exception as exc:
            return FetchResult("yfinance", False, error=str(exc))


def _latest_statement_value(statement: Any, aliases: Sequence[str]) -> Optional[float]:
    row = _find_statement_row(statement, aliases)
    if row is None:
        return None
    for value in row.dropna().tolist():
        numeric = safe_float(value)
        if numeric is not None:
            return numeric
    return None


def _growth_from_statement(statement: Any, aliases: Sequence[str]) -> Optional[float]:
    row = _find_statement_row(statement, aliases)
    if row is None:
        return None
    values = [safe_float(v) for v in row.dropna().tolist()]
    values = [v for v in values if v is not None]
    return None if len(values) < 2 or values[1] == 0 else (values[0] / values[1]) - 1.0


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


def _drop_none(values: Mapping[str, Optional[float]]) -> dict[str, float]:
    return {k: v for k, v in values.items() if v is not None}
