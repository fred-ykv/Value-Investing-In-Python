"""Normalize financial statement inputs used by the valuation pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .data_sources import MetricValue, get_mapping_value, metric_value, safe_float


@dataclass
class FinancialStatements:
    ticker: str
    income_statement: Mapping[str, float] = field(default_factory=dict)
    balance_sheet: Mapping[str, float] = field(default_factory=dict)
    cash_flow: Mapping[str, float] = field(default_factory=dict)
    market_data: Mapping[str, float] = field(default_factory=dict)
    info: Mapping[str, object] = field(default_factory=dict)
    source: str = "manual"


@dataclass
class StatementMetrics:
    values: dict[str, MetricValue]

    def get(self, name: str) -> MetricValue:
        return self.values.get(name, MetricValue(name, None, "missing", 0.0))


def build_statement_metrics(statements: FinancialStatements) -> StatementMetrics:
    source = statements.source
    inc, bs, cf, md = statements.income_statement, statements.balance_sheet, statements.cash_flow, statements.market_data
    values = {
        "revenue": get_mapping_value(inc, "revenue", "total_revenue", "Total Revenue", source=source),
        "ebit": get_mapping_value(inc, "ebit", "EBIT", "Operating Income", source=source),
        "net_income": get_mapping_value(inc, "net_income", "Net Income", source=source),
        "tax_provision": get_mapping_value(inc, "tax_provision", "Tax Provision", source=source),
        "interest_expense": get_mapping_value(inc, "interest_expense", "Interest Expense", source=source),
        "total_assets": get_mapping_value(bs, "total_assets", "Total Assets", source=source),
        "total_liabilities": get_mapping_value(bs, "total_liabilities", "Total Liabilities", source=source),
        "equity": get_mapping_value(bs, "equity", "Common Stock Equity", "Total Equity", source=source),
        "cash": get_mapping_value(bs, "cash", "Cash And Cash Equivalents", source=source),
        "total_debt": get_mapping_value(bs, "total_debt", "Total Debt", source=source),
        "current_assets": get_mapping_value(bs, "current_assets", "Current Assets", source=source),
        "current_liabilities": get_mapping_value(bs, "current_liabilities", "Current Liabilities", source=source),
        "cfo": get_mapping_value(cf, "cfo", "Operating Cash Flow", source=source),
        "capex": get_mapping_value(cf, "capex", "Capital Expenditure", source=source),
        "depreciation_amortization": get_mapping_value(cf, "depreciation_amortization", "Depreciation And Amortization", source=source),
        "shares": get_mapping_value(md, "shares", "shares_outstanding", "Shares Outstanding", source=source),
        "price": get_mapping_value(md, "price", "current_price", "Current Price", source=source),
        "market_cap": get_mapping_value(md, "market_cap", "Market Cap", source=source),
        "beta": get_mapping_value(md, "beta", "Beta", source=source),
    }
    values["fcff"] = compute_fcff(values)
    values["tax_rate"] = compute_tax_rate(values)
    values["book_value_per_share"] = compute_bvps(values)
    values["ncav_per_share"] = compute_ncav(values)
    return StatementMetrics(values)


def compute_fcff(values: Mapping[str, MetricValue]) -> MetricValue:
    cfo, capex = values["cfo"].value, values["capex"].value
    if cfo is None or capex is None:
        return MetricValue("fcff", None, "missing", 0.0, "requires CFO and capex")
    return MetricValue("fcff", cfo - abs(capex), "derived", (values["cfo"].confidence + values["capex"].confidence) / 2, "CFO - abs(CAPEX)")


def compute_tax_rate(values: Mapping[str, MetricValue]) -> MetricValue:
    tax, ebit = values["tax_provision"].value, values["ebit"].value
    pre_tax = None if ebit is None else ebit - abs(values["interest_expense"].value or 0.0)
    if tax is None or pre_tax in (None, 0):
        return metric_value("tax_rate", 0.21, "fallback", "default tax rate")
    return metric_value("tax_rate", max(0.0, min(0.45, abs(tax) / abs(pre_tax))), "derived")


def compute_bvps(values: Mapping[str, MetricValue]) -> MetricValue:
    equity, shares = values["equity"].value, values["shares"].value
    return MetricValue("book_value_per_share", None, "missing", 0.0) if equity is None or shares in (None, 0) else metric_value("book_value_per_share", equity / shares, "derived")


def compute_ncav(values: Mapping[str, MetricValue]) -> MetricValue:
    ca, liabilities, shares = values["current_assets"].value, values["total_liabilities"].value, values["shares"].value
    return MetricValue("ncav_per_share", None, "missing", 0.0) if ca is None or liabilities is None or shares in (None, 0) else metric_value("ncav_per_share", (ca - liabilities) / shares, "derived")


def update_market_from_info(statements: FinancialStatements) -> FinancialStatements:
    market = dict(statements.market_data)
    for target, candidates in {"price": ("currentPrice", "regularMarketPrice"), "shares": ("sharesOutstanding",), "market_cap": ("marketCap",), "beta": ("beta",)}.items():
        if target not in market:
            for candidate in candidates:
                value = safe_float(statements.info.get(candidate))
                if value is not None:
                    market[target] = value
                    break
    return FinancialStatements(statements.ticker, statements.income_statement, statements.balance_sheet, statements.cash_flow, market, statements.info, statements.source)
