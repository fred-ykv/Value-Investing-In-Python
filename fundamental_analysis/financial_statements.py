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
        "change_in_nwc": get_mapping_value(cf, "change_in_nwc", "Change In Working Capital", "Change In Other Working Capital", source=source),
        "shares": get_mapping_value(md, "shares", "shares_outstanding", "Shares Outstanding", source=source),
        "price": get_mapping_value(md, "price", "current_price", "Current Price", source=source),
        "market_cap": get_mapping_value(md, "market_cap", "Market Cap", source=source),
        "beta": get_mapping_value(md, "beta", "Beta", source=source),
    }
    values["tax_rate"] = compute_tax_rate(values)
    values["free_cash_flow_after_capex"] = compute_free_cash_flow_after_capex(values)
    values["fcff"] = compute_fcff(values)
    values["book_value_per_share"] = compute_bvps(values)
    values["ncav_per_share"] = compute_ncav(values)
    return StatementMetrics(values)


def compute_free_cash_flow_after_capex(values: Mapping[str, MetricValue]) -> MetricValue:
    cfo, capex = values["cfo"].value, values["capex"].value
    if cfo is None or capex is None:
        return MetricValue("free_cash_flow_after_capex", None, "missing", 0.0, "requires CFO and capex", basis="derived")
    return MetricValue(
        "free_cash_flow_after_capex",
        cfo - abs(capex),
        "derived",
        (values["cfo"].confidence + values["capex"].confidence) / 2,
        "CFO - abs(CAPEX); levered cash-flow proxy, not unlevered FCFF",
        basis="derived",
        formula="cfo_minus_capex",
    )


def compute_fcff(values: Mapping[str, MetricValue]) -> MetricValue:
    ebit = values["ebit"].value
    tax_rate = values["tax_rate"].value
    depreciation = values["depreciation_amortization"].value
    capex = values["capex"].value
    if ebit is None or tax_rate is None or depreciation is None or capex is None:
        return MetricValue("fcff", None, "missing", 0.0, "requires EBIT, tax rate, D&A, and capex", basis="derived")

    change_in_nwc = values["change_in_nwc"].value
    used_nwc_fallback = change_in_nwc is None
    if used_nwc_fallback:
        change_in_nwc = 0.0

    normalized_capex = abs(capex)
    fcff = ebit * (1.0 - tax_rate) + depreciation - normalized_capex - change_in_nwc
    inputs = [values["ebit"], values["tax_rate"], values["depreciation_amortization"], values["capex"]]
    if values["change_in_nwc"].is_available:
        inputs.append(values["change_in_nwc"])
    confidence = sum(item.confidence for item in inputs if item.is_available) / len(inputs)
    if used_nwc_fallback:
        confidence = max(0.0, confidence - 0.15)
    if values["tax_rate"].is_fallback:
        confidence = max(0.0, confidence - 0.10)
    note = "FCFF = EBIT * (1 - tax_rate) + D&A - abs(CAPEX) - change_in_nwc"
    if used_nwc_fallback:
        note += "; change_in_nwc unavailable, used explicit 0 approximation with confidence penalty"
    return MetricValue(
        "fcff",
        fcff,
        "derived",
        confidence,
        note,
        basis="derived",
        is_fallback=used_nwc_fallback or values["tax_rate"].is_fallback,
        formula="nopat_plus_da_minus_capex_minus_delta_nwc",
    )


def compute_tax_rate(values: Mapping[str, MetricValue]) -> MetricValue:
    tax, ebit = values["tax_provision"].value, values["ebit"].value
    pre_tax = None if ebit is None else ebit - abs(values["interest_expense"].value or 0.0)
    if tax is None or pre_tax in (None, 0):
        return metric_value("tax_rate", 0.21, "fallback", "default tax rate", basis="fallback", is_fallback=True, formula="default_tax_rate")
    raw_tax_rate = abs(tax) / abs(pre_tax)
    normalized = max(0.0, min(0.45, raw_tax_rate))
    note = "tax_provision / pretax_income"
    if normalized != raw_tax_rate:
        note += f"; clamped from {raw_tax_rate:.4f}"
    return metric_value("tax_rate", normalized, "derived", note, basis="derived", formula="tax_provision_divided_by_pretax_income")


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
