"""Adapter from legacy notebook globals to the modular analysis pipeline."""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional

from .main import AnalysisResult, analyze_ticker_from_inputs


def analyze_from_notebook_globals(namespace: Mapping[str, Any]) -> AnalysisResult:
    ticker = str(_first(namespace, "symbol", "_ticker", "ticker", default="UNKNOWN")).upper()
    info = _as_mapping(_first(namespace, "info", default={}))
    income = {
        "revenue": _num(namespace, "Revenue_last", "Receita_last", "TotalRevenue", "revenue"),
        "ebit": _num(namespace, "EBIT_last", "OperatingIncome_last", "EBIT", "ebit"),
        "net_income": _num(namespace, "NetIncome", "NI_last", "LucroLiquido_last", "net_income"),
        "tax_provision": _num(namespace, "IR_last", "TaxProvision", "tax_provision"),
        "interest_expense": _num(namespace, "interest_expense_last", "DespesaFinanceira", "interest_expense"),
    }
    balance = {
        "total_assets": _num(namespace, "TotalAssets_value", "TotalAssets", "total_assets"),
        "total_liabilities": _num(namespace, "TotalLiabilities_value", "TotalLiabilities", "total_liabilities"),
        "equity": _num(namespace, "CommonEquity", "PL", "PL_value", "equity"),
        "cash": _num(namespace, "cash_total", "CashEquivalents_value", "CashAndInvestments_total", "cash"),
        "total_debt": _num(namespace, "total_debt", "TotalDebt_value", "Po", "Debt", "debt"),
        "current_assets": _num(namespace, "TotalCurrentAssets_value", "TCA_last", "current_assets"),
        "current_liabilities": _num(namespace, "TotalCurrentLiabilities_value", "TCL_last", "current_liabilities"),
    }
    cash_flow = {
        "cfo": _num(namespace, "CFO_reported_last", "FCO", "FCO_value", "cfo"),
        "capex": _num(namespace, "capex_cf_last", "CAPEX_cf_last_value", "Capex_last", "capex_yf", "capex"),
        "depreciation_amortization": _num(namespace, "DA_last", "DepAmort_last", "depreciation_amortization"),
    }
    market = {
        "shares": _num(namespace, "Shares_Outstanding", "shares_out", "shares"),
        "price": _num(namespace, "current_price", "Price", "price"),
        "wacc": _num(namespace, "WACC_value", "WACC"),
        "ke": _num(namespace, "Ke", "Ke_val"),
        "growth_years": _num(namespace, "gLL_M_value", "gNOPAT_value", "g_years"),
        "terminal_growth": _num(namespace, "CP_value", "g_term"),
        "dividend_per_share": _num(namespace, "dividend_per_share", "DividendPS"),
        "revenue_growth": _num(namespace, "Rev_YoY", "revenue_growth"),
        "target_fcf_margin": _num(namespace, "FCF_margin_target", "target_fcf_margin"),
    }
    return analyze_ticker_from_inputs(ticker, _drop(income), _drop(balance), _drop(cash_flow), _drop(market), info, "notebook")


def print_modular_report(result: AnalysisResult) -> None:
    print(result.report["markdown"])


def _first(namespace: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in namespace and namespace[name] is not None:
            return namespace[name]
    return default


def _num(namespace: Mapping[str, Any], *names: str) -> Optional[float]:
    value = _first(namespace, *names)
    if value is None and isinstance(namespace.get("metrics"), Mapping):
        value = _first(namespace["metrics"], *names)
    return _to_float(value)


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if hasattr(value, "iloc"):
            value = value.dropna().iloc[-1]
        if isinstance(value, str):
            value = value.strip().replace("$", "").replace(",", "")
            return float(value[:-1]) / 100.0 if value.endswith("%") else float(value)
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _drop(values: Mapping[str, Optional[float]]) -> dict[str, float]:
    return {key: value for key, value in values.items() if value is not None}
