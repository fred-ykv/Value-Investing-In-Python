"""Valuation models with explicit assumptions and diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .config import DCF, GROWTH_TECH
from .data_sources import MetricValue, clamp, metric_value, weighted_confidence


@dataclass
class ValuationResult:
    method: str
    fair_value_per_share: Optional[float]
    confidence: float
    source: str = "derived"
    enterprise_value: Optional[float] = None
    equity_value: Optional[float] = None
    margin_of_safety: Optional[float] = None
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass
class DCFInput:
    fcff: MetricValue
    shares: MetricValue
    wacc: MetricValue
    growth_years: MetricValue
    terminal_growth: MetricValue
    debt: MetricValue
    cash: MetricValue
    current_price: MetricValue


def dcf_fcff(inputs: DCFInput) -> ValuationResult:
    fcff0, shares = inputs.fcff.value, inputs.shares.value
    if fcff0 is None:
        return ValuationResult("dcf_fcff", None, 0.0, diagnostics={"error": "missing FCFF"})
    if shares in (None, 0):
        return ValuationResult("dcf_fcff", None, 0.0, diagnostics={"error": "missing shares"})
    wacc = inputs.wacc.value if inputs.wacc.value is not None else DCF.default_wacc
    growth = clamp(inputs.growth_years.value if inputs.growth_years.value is not None else DCF.default_growth_years, DCF.min_growth_years, DCF.max_growth_years)
    terminal_growth = clamp(inputs.terminal_growth.value if inputs.terminal_growth.value is not None else DCF.default_terminal_growth, DCF.min_terminal_growth, DCF.max_terminal_growth)
    diagnostics: dict[str, object] = {
        "fcff_definition": inputs.fcff.formula or "unknown",
        "fcff_note": inputs.fcff.note,
        "discount_rate_label": "WACC" if inputs.wacc.name == "wacc" else "Taxa de desconto proxy",
        "discount_rate_source": inputs.wacc.source,
        "discount_rate_note": inputs.wacc.note,
        "fallback_assumptions": fallback_assumptions(inputs),
    }
    if wacc <= terminal_growth:
        terminal_growth = max(0.0, wacc - DCF.min_spread_wacc_terminal)
        diagnostics["terminal_growth_adjusted"] = terminal_growth
    confidence = weighted_confidence(inputs.fcff, inputs.shares, inputs.wacc, inputs.growth_years, inputs.terminal_growth)
    if inputs.fcff.is_fallback:
        confidence = max(0.0, confidence - 0.10)
    if fcff0 < 0:
        confidence = max(0.0, confidence - DCF.negative_fcff_confidence_penalty)
        diagnostics["negative_fcff"] = True
    projected = []
    value = fcff0
    for _ in range(DCF.horizon_years):
        value *= 1.0 + growth
        projected.append(value)
    pv_stage = sum(cf / ((1.0 + wacc) ** year) for year, cf in enumerate(projected, start=1))
    terminal = projected[-1] * (1.0 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal / ((1.0 + wacc) ** DCF.horizon_years)
    ev = pv_stage + pv_terminal
    if not inputs.debt.is_available or not inputs.cash.is_available:
        diagnostics.update({"error": "missing debt or cash for enterprise-to-equity bridge", "enterprise_value": ev})
        return ValuationResult("dcf_fcff", None, max(0.0, confidence - 0.25), enterprise_value=ev, diagnostics=diagnostics)
    equity = ev - float(inputs.debt.value) + float(inputs.cash.value)
    fair = equity / shares
    margin = None if inputs.current_price.value in (None, 0) else (fair / inputs.current_price.value) - 1.0
    diagnostics.update(
        {
            "growth_years": growth,
            "terminal_growth": terminal_growth,
            "wacc": wacc,
            "pv_explicit_stage": pv_stage,
            "pv_terminal_value": pv_terminal,
            "terminal_value_share": None if ev == 0 else pv_terminal / ev,
            "explicit_stage_share": None if ev == 0 else pv_stage / ev,
            "net_debt_adjustment": float(inputs.debt.value) - float(inputs.cash.value),
            "sensitivity": dcf_sensitivity(inputs),
        }
    )
    return ValuationResult("dcf_fcff", fair, confidence, enterprise_value=ev, equity_value=equity, margin_of_safety=margin, diagnostics=diagnostics)


def dcf_sensitivity(inputs: DCFInput) -> dict[str, dict[str, Optional[float]]]:
    matrix: dict[str, dict[str, Optional[float]]] = {}
    for wacc in DCF.sensitivity_wacc_range:
        row: dict[str, Optional[float]] = {}
        for g in DCF.sensitivity_terminal_growth_range:
            if wacc <= g:
                row[f"{g:.1%}"] = None
                continue
            temp = DCFInput(inputs.fcff, inputs.shares, metric_value("wacc", wacc, "derived"), inputs.growth_years, metric_value("terminal_growth", g, "derived"), inputs.debt, inputs.cash, inputs.current_price)
            row[f"{g:.1%}"] = _dcf_fair_value(temp)
        matrix[f"{wacc:.1%}"] = row
    return matrix


def fallback_assumptions(inputs: DCFInput) -> list[str]:
    assumptions = []
    for metric in (inputs.fcff, inputs.wacc, inputs.growth_years, inputs.terminal_growth):
        if metric.is_fallback:
            assumptions.append(f"{metric.name}: {metric.note or metric.source}")
    return assumptions


def _dcf_fair_value(inputs: DCFInput) -> Optional[float]:
    result = dcf_fcff_no_sensitivity(inputs)
    return result.fair_value_per_share


def dcf_fcff_no_sensitivity(inputs: DCFInput) -> ValuationResult:
    fcff0, shares = inputs.fcff.value, inputs.shares.value
    if fcff0 is None or shares in (None, 0) or not inputs.debt.is_available or not inputs.cash.is_available:
        return ValuationResult("dcf_fcff", None, 0.0)
    wacc = inputs.wacc.value if inputs.wacc.value is not None else DCF.default_wacc
    growth_value = inputs.growth_years.value if inputs.growth_years.value is not None else DCF.default_growth_years
    growth = clamp(growth_value, DCF.min_growth_years, DCF.max_growth_years)
    g = inputs.terminal_growth.value if inputs.terminal_growth.value is not None else DCF.default_terminal_growth
    if wacc <= g:
        return ValuationResult("dcf_fcff", None, 0.0)
    value, projected = fcff0, []
    for _ in range(DCF.horizon_years):
        value *= 1 + growth
        projected.append(value)
    pv = sum(cf / ((1 + wacc) ** year) for year, cf in enumerate(projected, start=1))
    terminal = projected[-1] * (1 + g) / (wacc - g)
    ev = pv + terminal / ((1 + wacc) ** DCF.horizon_years)
    fair = (ev - float(inputs.debt.value) + float(inputs.cash.value)) / shares
    return ValuationResult("dcf_fcff", fair, 0.0)


def graham_value(eps: MetricValue, bvps: MetricValue, current_price: MetricValue) -> ValuationResult:
    if eps.value is None or bvps.value is None or eps.value <= 0 or bvps.value <= 0:
        return ValuationResult("graham", None, 0.0, diagnostics={"error": "requires positive EPS and BVPS"})
    fair = math.sqrt(22.5 * eps.value * bvps.value)
    margin = None if current_price.value in (None, 0) else (fair / current_price.value) - 1.0
    return ValuationResult("graham", fair, weighted_confidence(eps, bvps), margin_of_safety=margin)


def eva_value(invested_capital: MetricValue, roic: MetricValue, wacc: MetricValue, growth: MetricValue, shares: MetricValue, current_price: MetricValue, net_debt: MetricValue | None = None) -> ValuationResult:
    net_debt = net_debt or MetricValue("net_debt", None, "missing", 0.0)
    if invested_capital.value is None or roic.value is None or shares.value in (None, 0) or net_debt.value is None:
        return ValuationResult("eva", None, 0.0, diagnostics={"error": "missing invested capital, ROIC, shares, or net debt"})
    discount = wacc.value if wacc.value is not None else DCF.default_wacc
    g = growth.value if growth.value is not None else DCF.default_terminal_growth
    if discount <= g:
        g = max(0.0, discount - DCF.min_spread_wacc_terminal)
    economic_profit = (roic.value - discount) * invested_capital.value
    pv_economic_profit = economic_profit * (1.0 + g) / (discount - g)
    enterprise = invested_capital.value + pv_economic_profit
    equity = enterprise - net_debt.value
    fair = equity / shares.value
    margin = None if current_price.value in (None, 0) else (fair / current_price.value) - 1.0
    diagnostics = {
        "invested_capital": invested_capital.value,
        "economic_profit": economic_profit,
        "pv_economic_profit": pv_economic_profit,
        "net_debt_adjustment": net_debt.value,
        "wacc": discount,
        "terminal_growth": g,
    }
    return ValuationResult("eva", fair, weighted_confidence(invested_capital, roic, wacc, shares, net_debt), enterprise_value=enterprise, equity_value=equity, margin_of_safety=margin, diagnostics=diagnostics)


def residual_income_bank(bvps: MetricValue, roe: MetricValue, ke: MetricValue, terminal_growth: MetricValue, current_price: MetricValue) -> ValuationResult:
    if bvps.value is None or roe.value is None or ke.value is None:
        return ValuationResult("residual_income", None, 0.0, diagnostics={"error": "missing BVPS, ROE, or Ke"})
    g = terminal_growth.value if terminal_growth.value is not None else DCF.default_terminal_growth
    if ke.value <= g:
        g = max(0.0, ke.value - DCF.min_spread_wacc_terminal)
    fair = bvps.value + ((roe.value - ke.value) / (ke.value - g)) * bvps.value
    margin = None if current_price.value in (None, 0) else (fair / current_price.value) - 1.0
    return ValuationResult("residual_income", fair, weighted_confidence(bvps, roe, ke), margin_of_safety=margin)


def ddm_bank(dividend_per_share: MetricValue, ke: MetricValue, terminal_growth: MetricValue, current_price: MetricValue) -> ValuationResult:
    if dividend_per_share.value is None or ke.value is None:
        return ValuationResult("ddm", None, 0.0, diagnostics={"error": "missing dividend or Ke"})
    g = terminal_growth.value if terminal_growth.value is not None else DCF.default_terminal_growth
    if ke.value <= g:
        g = max(0.0, ke.value - DCF.min_spread_wacc_terminal)
    fair = dividend_per_share.value * (1.0 + g) / (ke.value - g)
    margin = None if current_price.value in (None, 0) else (fair / current_price.value) - 1.0
    return ValuationResult("ddm", fair, weighted_confidence(dividend_per_share, ke), margin_of_safety=margin)


def growth_tech_value(revenue: MetricValue, revenue_growth: MetricValue, target_fcf_margin: MetricValue, net_cash: MetricValue, shares: MetricValue, current_price: MetricValue, discount_rate: MetricValue) -> ValuationResult:
    if revenue.value is None or shares.value in (None, 0) or net_cash.value is None:
        return ValuationResult("growth_tech", None, 0.0, diagnostics={"error": "missing revenue, shares, or net cash"})
    revenue_growth_value = revenue_growth.value if revenue_growth.value is not None else 0.10
    growth = clamp(revenue_growth_value, -0.10, 0.50)
    margin = (
        target_fcf_margin.value
        if target_fcf_margin.value is not None
        else GROWTH_TECH.target_fcf_margin
    )
    rate = discount_rate.value if discount_rate.value is not None else GROWTH_TECH.default_discount_rate
    g_term = min(GROWTH_TECH.terminal_growth, rate - DCF.min_spread_wacc_terminal)
    projected_revenue, pv = revenue.value, 0.0
    for year in range(1, DCF.horizon_years + 1):
        projected_revenue *= 1.0 + growth
        pv += projected_revenue * margin / ((1.0 + rate) ** year)
    terminal = projected_revenue * margin * (1.0 + g_term) / (rate - g_term)
    ev = pv + terminal / ((1.0 + rate) ** DCF.horizon_years)
    equity = ev + net_cash.value
    fair = equity / shares.value
    mos = None if current_price.value in (None, 0) else (fair / current_price.value) - 1.0
    return ValuationResult("growth_tech", fair, weighted_confidence(revenue, revenue_growth, shares), enterprise_value=ev, equity_value=equity, margin_of_safety=mos, diagnostics={"growth": growth, "target_fcf_margin": margin, "discount_rate": rate})

