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
        "change_in_nwc": get_mapping_value(cf, "change_in_nwc", "delta_nwc", "change_in_non_cash_working_capital", source=source),
        "change_in_nwc_cash_effect": get_mapping_value(cf, "change_in_nwc_cash_effect", "Change In Working Capital", "Change In Other Working Capital", source=source),
        "shares": get_mapping_value(md, "shares", "shares_outstanding", "Shares Outstanding", source=source),
        "price": get_mapping_value(md, "price", "current_price", "Current Price", source=source),
        "market_cap": get_mapping_value(md, "market_cap", "Market Cap", source=source),
        "beta": get_mapping_value(md, "beta", "Beta", source=source),
    }
    values["tax_rate"] = compute_tax_rate(values)
    values["nopat"] = compute_nopat(values)
    values["free_cash_flow_after_capex"] = compute_free_cash_flow_after_capex(values)
    values["fcff"] = compute_fcff(values)
    values["net_debt"] = compute_net_debt(values)
    values["invested_capital"] = compute_invested_capital(values)
    values["book_value_per_share"] = compute_bvps(values)
    values["ncav_per_share"] = compute_ncav(values)
    return StatementMetrics(values)


def compute_free_cash_flow_after_capex(values: Mapping[str, MetricValue]) -> MetricValue:
    cfo_metric, capex_metric = values["cfo"], values["capex"]
    cfo, capex = cfo_metric.value, capex_metric.value
    if cfo is None or capex is None:
        return MetricValue("free_cash_flow_after_capex", None, "missing", 0.0, "requires CFO and capex", basis="derived")
    return _derived_metric(
        "free_cash_flow_after_capex",
        cfo - abs(capex),
        (cfo_metric, capex_metric),
        (cfo_metric.confidence + capex_metric.confidence) / 2,
        "CFO - abs(CAPEX); levered cash-flow proxy, not unlevered FCFF",
        formula="cfo_minus_capex",
    )


def compute_fcff(values: Mapping[str, MetricValue]) -> MetricValue:
    required_inputs = {
        "ebit": values["ebit"],
        "tax_rate": values["tax_rate"],
        "depreciation_amortization": values["depreciation_amortization"],
        "capex": values["capex"],
    }
    missing_inputs = tuple(
        name for name, metric in required_inputs.items() if not metric.is_available
    )
    if missing_inputs:
        return MetricValue(
            "fcff",
            None,
            "missing",
            0.0,
            "requires EBIT, tax rate, D&A, and capex; missing: "
            + ", ".join(missing_inputs),
            basis="derived",
        )
    ebit = float(required_inputs["ebit"].value)
    tax_rate = float(required_inputs["tax_rate"].value)
    depreciation = float(required_inputs["depreciation_amortization"].value)
    capex = float(required_inputs["capex"].value)

    economic_delta = values.get("change_in_nwc", MetricValue("change_in_nwc", None, "missing", 0.0))
    cash_effect = values.get("change_in_nwc_cash_effect", MetricValue("change_in_nwc_cash_effect", None, "missing", 0.0))
    used_nwc_fallback = not economic_delta.is_available and not cash_effect.is_available
    if cash_effect.is_available:
        working_capital_adjustment = float(cash_effect.value)
        working_capital_metric = cash_effect
        working_capital_note = "cash-flow statement working-capital effect added to FCFF"
        formula = "nopat_plus_da_minus_capex_plus_nwc_cash_effect"
    elif economic_delta.is_available:
        working_capital_adjustment = -float(economic_delta.value)
        working_capital_metric = economic_delta
        working_capital_note = "economic increase in non-cash working capital subtracted from FCFF"
        formula = "nopat_plus_da_minus_capex_minus_delta_nwc"
    else:
        working_capital_adjustment = 0.0
        working_capital_metric = None
        missing_nwc_notes = tuple(
            item.note
            for item in (economic_delta, cash_effect)
            if item.note and item.note not in {"not found", "not found in anchor filing"}
        )
        working_capital_note = (
            "change_in_nwc unavailable, used explicit 0 approximation with "
            "confidence penalty"
        )
        if missing_nwc_notes:
            working_capital_note += "; reason: " + " | ".join(missing_nwc_notes)
        formula = "nopat_plus_da_minus_capex_nwc_fallback_zero"

    normalized_capex = abs(capex)
    fcff = ebit * (1.0 - tax_rate) + depreciation - normalized_capex + working_capital_adjustment
    inputs = [values["ebit"], values["tax_rate"], values["depreciation_amortization"], values["capex"]]
    if working_capital_metric is not None:
        inputs.append(working_capital_metric)
    fallback_inputs = tuple(item.name for item in inputs if item.is_fallback)
    confidence = sum(item.confidence for item in inputs if item.is_available) / len(inputs)
    if used_nwc_fallback:
        confidence = max(0.0, confidence - 0.15)
    if values["tax_rate"].is_fallback:
        confidence = max(0.0, confidence - 0.10)
    note = f"FCFF = EBIT * (1 - tax_rate) + D&A - abs(CAPEX) + working_capital_adjustment; {working_capital_note}"
    if fallback_inputs:
        note += "; fallback inputs: " + ", ".join(fallback_inputs)
    return _derived_metric(
        "fcff",
        fcff,
        tuple(inputs),
        confidence,
        note,
        is_fallback=used_nwc_fallback or bool(fallback_inputs),
        formula=formula,
    )


def compute_net_debt(values: Mapping[str, MetricValue]) -> MetricValue:
    debt, cash = values["total_debt"], values["cash"]
    if not debt.is_available or not cash.is_available:
        return MetricValue("net_debt", None, "missing", 0.0, "requires total debt and cash", basis="derived")
    return _derived_metric(
        "net_debt",
        float(debt.value) - float(cash.value),
        (debt, cash),
        (debt.confidence + cash.confidence) / 2.0,
        "Net debt = total debt - cash",
        formula="total_debt_minus_cash",
    )


def compute_nopat(values: Mapping[str, MetricValue]) -> MetricValue:
    ebit, tax_rate = values["ebit"], values["tax_rate"]
    if not ebit.is_available or not tax_rate.is_available:
        return MetricValue("nopat", None, "missing", 0.0, "requires EBIT and tax rate", basis="derived")
    return _derived_metric(
        "nopat",
        float(ebit.value) * (1.0 - float(tax_rate.value)),
        (ebit, tax_rate),
        (ebit.confidence + tax_rate.confidence) / 2.0,
        "NOPAT = EBIT * (1 - tax rate)",
        is_fallback=tax_rate.is_fallback,
        formula="ebit_after_tax",
    )


def compute_invested_capital(values: Mapping[str, MetricValue]) -> MetricValue:
    equity = values["equity"]
    net_debt = values.get("net_debt")
    if net_debt is None:
        net_debt = compute_net_debt(values)
    if not equity.is_available or not net_debt.is_available:
        return MetricValue("invested_capital", None, "missing", 0.0, "requires equity, total debt, and cash", basis="derived")
    return _derived_metric(
        "invested_capital",
        float(equity.value) + float(net_debt.value),
        (equity, net_debt),
        (equity.confidence + net_debt.confidence) / 2.0,
        "Invested capital = equity + net debt",
        formula="equity_plus_net_debt",
    )


def _derived_metric(
    name: str,
    value: float,
    inputs: tuple[MetricValue, ...],
    confidence: float,
    note: str,
    *,
    is_fallback: bool = False,
    formula: str,
) -> MetricValue:
    documents = list(dict.fromkeys(item.source_document for item in inputs if item.source_document))
    source_document = f"Derivado de {'; '.join(documents)}" if documents else None
    return MetricValue(
        name,
        value,
        "derived",
        confidence,
        note,
        source_url=_shared_lineage_value(inputs, "source_url"),
        source_document=source_document,
        period_start=_shared_lineage_value(inputs, "period_start"),
        period_end=_shared_lineage_value(inputs, "period_end"),
        filing_date=_shared_lineage_value(inputs, "filing_date"),
        as_of=_shared_lineage_value(inputs, "as_of"),
        currency=_shared_lineage_value(inputs, "currency"),
        scale="raw",
        basis="derived",
        is_fallback=is_fallback,
        formula=formula,
    )


def _shared_lineage_value(inputs: tuple[MetricValue, ...], field_name: str):
    values = list(dict.fromkeys(getattr(item, field_name) for item in inputs if getattr(item, field_name) is not None))
    return values[0] if len(values) == 1 else None


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
