"""Fundamental metrics inspired by quality, value, and investment factors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from .data_sources import MetricValue, metric_value, safe_float


@dataclass
class MetricPack:
    values: dict[str, MetricValue] = field(default_factory=dict)

    def get(self, name: str, default: Optional[float] = None) -> Optional[float]:
        metric = self.values.get(name)
        return metric.value if metric and metric.value is not None else default

    def confidence(self) -> float:
        values = [m.confidence for m in self.values.values() if m.is_available]
        return sum(values) / len(values) if values else 0.0


def safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    return None if num is None or den in (None, 0) else num / den


def safe_positive_denominator_div(
    num: Optional[float],
    den: Optional[float],
) -> Optional[float]:
    """Return a leverage multiple only when operating profit is positive."""
    return None if num is None or den is None or den <= 0 else num / den


def safe_accruals_to_assets(
    net_income: Optional[float],
    cfo: Optional[float],
    assets: Optional[float],
) -> Optional[float]:
    if net_income is None or cfo is None:
        return None
    return safe_positive_denominator_div(net_income - cfo, assets)


def cash_burn_amount(cfo: Optional[float], fcff: Optional[float]) -> Optional[float]:
    burns = [abs(value) for value in (cfo, fcff) if value is not None and value < 0]
    return max(burns) if burns else None


def build_metrics(statement_values: Mapping[str, MetricValue]) -> MetricPack:
    v = statement_values
    ni, eq, assets, cfo = v["net_income"].value, v["equity"].value, v["total_assets"].value, v["cfo"].value
    revenue, ebit, debt, cash = v["revenue"].value, v["ebit"].value, v["total_debt"].value, v["cash"].value
    nopat, invested_capital = v["nopat"].value, v["invested_capital"].value
    ca, cl, shares, price = v["current_assets"].value, v["current_liabilities"].value, v["shares"].value, v["price"].value
    bvps, fcff = v["book_value_per_share"].value, v["fcff"].value
    cash_burn = cash_burn_amount(cfo, fcff)
    net_debt = None if debt is None or cash is None else debt - cash
    metrics = {
        "roe": metric_value("roe", safe_positive_denominator_div(ni, eq), "derived", "ROE indisponivel quando o patrimonio liquido nao e positivo." if eq is None or eq <= 0 else "Lucro liquido / patrimonio liquido positivo."),
        "roa": metric_value("roa", safe_positive_denominator_div(ni, assets), "derived"),
        "roic_proxy": metric_value("roic_proxy", safe_positive_denominator_div(nopat, invested_capital), "derived", "NOPAT divided by positive invested capital net of cash"),
        "operating_margin": metric_value("operating_margin", safe_positive_denominator_div(ebit, revenue), "derived"),
        "net_margin": metric_value("net_margin", safe_positive_denominator_div(ni, revenue), "derived"),
        "cfo_to_net_income": metric_value("cfo_to_net_income", safe_positive_denominator_div(cfo, ni), "derived", "CFO / lucro liquido indisponivel quando o lucro nao e positivo." if ni is None or ni <= 0 else "CFO dividido por lucro liquido positivo."),
        "accruals_to_assets": metric_value("accruals_to_assets", safe_accruals_to_assets(ni, cfo, assets), "derived"),
        "debt_to_equity": metric_value("debt_to_equity", safe_positive_denominator_div(debt, eq), "derived", "Divida / patrimonio indisponivel quando o patrimonio nao e positivo." if eq is None or eq <= 0 else "Divida dividida por patrimonio liquido positivo."),
        "net_debt_to_ebit": metric_value(
            "net_debt_to_ebit",
            safe_positive_denominator_div(
                net_debt,
                ebit,
            ),
            "derived",
            (
                "Divida liquida / EBIT exige divida, caixa e EBIT positivo."
                if net_debt is None or ebit is None or ebit <= 0
                else "Divida liquida dividida por EBIT positivo."
            ),
        ),
        "current_ratio": metric_value("current_ratio", safe_positive_denominator_div(ca, cl), "derived"),
        "price_to_book": metric_value("price_to_book", safe_positive_denominator_div(price, bvps), "derived", "P/VP indisponivel quando o valor patrimonial por acao nao e positivo." if bvps is None or bvps <= 0 else "Preco / valor patrimonial por acao positivo."),
        "fcff_yield": metric_value("fcff_yield", safe_positive_denominator_div(fcff, (price or 0.0) * (shares or 0.0)), "derived"),
        "cash_burn": metric_value("cash_burn", cash_burn, "derived", "annual cash burn based on negative CFO/FCFF"),
        "cash_runway_years": metric_value("cash_runway_years", safe_div(cash, cash_burn), "derived", "cash divided by annual cash burn"),
    }
    metrics["piotroski_proxy"] = metric_value("piotroski_proxy", piotroski_proxy(metrics, v), "derived")
    metrics["fama_french_value"] = metric_value("fama_french_value", value_factor_proxy(metrics), "derived")
    metrics["fama_french_profitability"] = metric_value("fama_french_profitability", profitability_factor_proxy(metrics), "derived")
    metrics["earnings_quality"] = metric_value("earnings_quality", earnings_quality_score(metrics), "derived")
    return MetricPack(metrics)


def piotroski_proxy(metrics: Mapping[str, MetricValue], values: Mapping[str, MetricValue]) -> float:
    tests = [
        (metrics["roa"].value or 0) > 0,
        (values["cfo"].value or 0) > 0,
        (metrics["cfo_to_net_income"].value or 0) > 1,
        (metrics["operating_margin"].value or 0) > 0,
        (metrics["current_ratio"].value or 0) > 1,
        metrics["debt_to_equity"].value is not None and metrics["debt_to_equity"].value < 2,
        (metrics["roic_proxy"].value or 0) > 0,
    ]
    return sum(1 for item in tests if item) / len(tests)


def value_factor_proxy(metrics: Mapping[str, MetricValue]) -> Optional[float]:
    pb, fcf_yield = metrics["price_to_book"].value, metrics["fcff_yield"].value
    parts = []
    if pb not in (None, 0):
        parts.append(max(0.0, min(1.0, (3.0 - pb) / 3.0)))
    if fcf_yield is not None:
        parts.append(max(0.0, min(1.0, (fcf_yield + 0.02) / 0.12)))
    return sum(parts) / len(parts) if parts else None


def profitability_factor_proxy(metrics: Mapping[str, MetricValue]) -> Optional[float]:
    parts = [_normalize(metrics["roe"].value, -0.05, 0.25), _normalize(metrics["roic_proxy"].value, -0.05, 0.25), _normalize(metrics["operating_margin"].value, -0.05, 0.30)]
    parts = [p for p in parts if p is not None]
    return sum(parts) / len(parts) if parts else None


def earnings_quality_score(metrics: Mapping[str, MetricValue]) -> Optional[float]:
    cfo_score = _normalize(metrics["cfo_to_net_income"].value, 0.0, 1.5)
    accruals = metrics["accruals_to_assets"].value
    accrual_score = None if accruals is None else max(0.0, min(1.0, 1.0 - abs(accruals) / 0.20))
    parts = [p for p in (cfo_score, accrual_score) if p is not None]
    return sum(parts) / len(parts) if parts else None


def _normalize(value: Optional[float], low: float, high: float) -> Optional[float]:
    value = safe_float(value)
    return None if value is None else max(0.0, min(1.0, (value - low) / (high - low)))

