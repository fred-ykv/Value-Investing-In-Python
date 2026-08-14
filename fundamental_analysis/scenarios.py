"""Scenario engine for fundamental valuation stress testing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .config import CompanyType, DCF, GROWTH_TECH, REVERSE_DCF, SCENARIOS, ScenarioCase
from .data_sources import MetricValue, clamp, metric_value, weighted_confidence
from .metrics import MetricPack
from .valuation import DCFInput, ValuationResult, dcf_fcff_no_sensitivity


ValuationBuilder = Callable[
    [CompanyType, Mapping[str, MetricValue], MetricPack, Mapping[str, float], str, DCFInput],
    list[ValuationResult],
]


@dataclass
class ScenarioResult:
    key: str
    label: str
    description: str
    assumptions: dict[str, float]
    valuations: list[ValuationResult]
    fair_value_per_share: float | None
    margin_of_safety: float | None
    confidence: float


@dataclass
class ReverseDCFResult:
    current_price: float | None
    implied_growth_years: float | None
    base_growth_years: float | None
    discount_rate: float | None
    terminal_growth: float | None
    confidence: float
    status: str
    interpretation: str
    assumptions: dict[str, float | None]


def build_scenarios(
    company_type: CompanyType,
    values: Mapping[str, MetricValue],
    metrics: MetricPack,
    market_data: Mapping[str, float],
    source: str,
    valuation_builder: ValuationBuilder,
    cost_of_capital: float,
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for case in SCENARIOS.cases:
        scenario_market = scenario_market_data(case, metrics, market_data, cost_of_capital)
        scenario_values = scenario_statement_values(values, case)
        dcf_input = DCFInput(
            scenario_values["fcff"],
            scenario_values["shares"],
            metric_value("wacc", scenario_market["wacc"], "scenario"),
            metric_value("growth_years", scenario_market["growth_years"], "scenario"),
            metric_value("terminal_growth", scenario_market["terminal_growth"], "scenario"),
            scenario_values["total_debt"],
            scenario_values["cash"],
            scenario_values["price"],
        )
        valuations = valuation_builder(company_type, scenario_values, metrics, scenario_market, source, dcf_input)
        results.append(
            ScenarioResult(
                key=case.key,
                label=case.label,
                description=case.description,
                assumptions=scenario_assumptions(case, scenario_market),
                valuations=valuations,
                fair_value_per_share=aggregate_fair_value(valuations),
                margin_of_safety=aggregate_margin_of_safety(valuations),
                confidence=aggregate_confidence(valuations),
            )
        )
    return results


def build_reverse_dcf(
    values: Mapping[str, MetricValue],
    market_data: Mapping[str, float],
    cost_of_capital: float,
) -> ReverseDCFResult:
    fcff = values["fcff"]
    current_price = values["price"]
    base_growth = first_number(market_data.get("growth_years"), market_data.get("revenue_growth"), DCF.default_growth_years)
    terminal_growth = first_number(market_data.get("terminal_growth"), DCF.default_terminal_growth)
    discount_rate = first_number(market_data.get("wacc"), cost_of_capital, DCF.default_wacc)
    terminal_growth = clamp(terminal_growth, DCF.min_terminal_growth, min(DCF.max_terminal_growth, discount_rate - DCF.min_spread_wacc_terminal))
    assumptions = {
        "min_growth": REVERSE_DCF.min_growth,
        "max_growth": REVERSE_DCF.max_growth,
        "base_growth_years": base_growth,
        "discount_rate": discount_rate,
        "terminal_growth": terminal_growth,
    }
    confidence = weighted_confidence(fcff, values["shares"], current_price, metric_value("wacc", discount_rate, "derived"), metric_value("terminal_growth", terminal_growth, "derived"))
    if fcff.value is None or values["shares"].value in (None, 0) or current_price.value in (None, 0):
        return ReverseDCFResult(current_price.value, None, base_growth, discount_rate, terminal_growth, 0.0, "indisponivel", "Reverse DCF indisponivel: faltam FCFF, numero de acoes ou preco atual.", assumptions)
    if fcff.value <= 0:
        return ReverseDCFResult(current_price.value, None, base_growth, discount_rate, terminal_growth, max(0.0, confidence - DCF.negative_fcff_confidence_penalty), "indisponivel", "Reverse DCF nao conclusivo porque o FCFF atual e negativo; neste caso a tese depende de virada operacional, runway e margem futura.", assumptions)
    if discount_rate <= terminal_growth:
        return ReverseDCFResult(current_price.value, None, base_growth, discount_rate, terminal_growth, 0.0, "indisponivel", "Reverse DCF indisponivel: crescimento terminal precisa ficar abaixo da taxa de desconto.", assumptions)

    low = REVERSE_DCF.min_growth
    high = min(REVERSE_DCF.max_growth, discount_rate - DCF.min_spread_wacc_terminal)
    low_price = _reverse_dcf_price_at_growth(values, discount_rate, terminal_growth, low)
    high_price = _reverse_dcf_price_at_growth(values, discount_rate, terminal_growth, high)
    target = float(current_price.value)
    if low_price is None or high_price is None:
        return ReverseDCFResult(target, None, base_growth, discount_rate, terminal_growth, 0.0, "indisponivel", "Reverse DCF indisponivel por falta de dados validos no DCF.", assumptions)
    if target < low_price:
        return ReverseDCFResult(target, low, base_growth, discount_rate, terminal_growth, confidence, "abaixo_da_faixa", "O preco atual ja fica abaixo do valor estimado mesmo no limite inferior de crescimento testado.", assumptions)
    if target > high_price:
        return ReverseDCFResult(target, high, base_growth, discount_rate, terminal_growth, confidence, "acima_da_faixa", "O preco atual exige crescimento acima do limite maximo testado; a premissa embutida parece muito agressiva.", assumptions)

    implied = _solve_implied_growth(values, discount_rate, terminal_growth, target, low, high)
    status, interpretation = reverse_dcf_interpretation(implied, base_growth)
    return ReverseDCFResult(target, implied, base_growth, discount_rate, terminal_growth, confidence, status, interpretation, assumptions)


def scenario_market_data(case: ScenarioCase, metrics: MetricPack, market_data: Mapping[str, float], cost_of_capital: float) -> dict[str, float]:
    base_growth = first_number(market_data.get("growth_years"), market_data.get("revenue_growth"), metrics.get("revenue_growth"), DCF.default_growth_years)
    base_terminal_growth = first_number(market_data.get("terminal_growth"), DCF.default_terminal_growth)
    base_revenue_growth = first_number(market_data.get("revenue_growth"), base_growth)
    base_target_fcf_margin = first_number(market_data.get("target_fcf_margin"), GROWTH_TECH.target_fcf_margin)
    discount_rate = max(0.01, cost_of_capital + case.discount_rate_delta)
    terminal_growth = clamp(base_terminal_growth + case.terminal_growth_delta, DCF.min_terminal_growth, min(DCF.max_terminal_growth, discount_rate - DCF.min_spread_wacc_terminal))
    growth_years = clamp(base_growth + case.growth_delta, DCF.min_growth_years, DCF.max_growth_years)
    return {
        **{key: float(value) for key, value in market_data.items() if isinstance(value, (int, float))},
        "wacc": discount_rate,
        "ke": discount_rate,
        "growth_years": growth_years,
        "terminal_growth": terminal_growth,
        "revenue_growth": clamp(base_revenue_growth + case.growth_delta, -0.20, 0.60),
        "target_fcf_margin": clamp(base_target_fcf_margin + case.target_fcf_margin_delta, -0.20, 0.40),
    }


def scenario_statement_values(values: Mapping[str, MetricValue], case: ScenarioCase) -> dict[str, MetricValue]:
    adjusted = dict(values)
    fcff = values.get("fcff")
    if fcff and fcff.value is not None:
        adjusted["fcff"] = metric_value("fcff", adjusted_fcff(fcff.value, case.fcff_adjustment), "scenario", case.label)
    return adjusted


def scenario_assumptions(case: ScenarioCase, market_data: Mapping[str, float]) -> dict[str, float]:
    return {
        "growth_years": market_data["growth_years"],
        "revenue_growth": market_data["revenue_growth"],
        "discount_rate": market_data["wacc"],
        "terminal_growth": market_data["terminal_growth"],
        "target_fcf_margin": market_data["target_fcf_margin"],
        "fcff_adjustment": case.fcff_adjustment,
    }


def adjusted_fcff(value: float, adjustment: float) -> float:
    factor = 1.0 + adjustment if value >= 0 else 1.0 - adjustment
    return value * max(0.0, factor)


def aggregate_fair_value(valuations: list[ValuationResult]) -> float | None:
    available = [(v.fair_value_per_share, v.confidence) for v in valuations if v.fair_value_per_share is not None and v.confidence > 0]
    return weighted_average(available)


def aggregate_margin_of_safety(valuations: list[ValuationResult]) -> float | None:
    available = [(v.margin_of_safety, v.confidence) for v in valuations if v.margin_of_safety is not None and v.confidence > 0]
    return weighted_average(available)


def aggregate_confidence(valuations: list[ValuationResult]) -> float:
    available = [v.confidence for v in valuations if v.confidence > 0]
    return sum(available) / len(available) if available else 0.0


def first_number(*values: object) -> float:
    for value in values:
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def weighted_average(values: list[tuple[float | None, float]]) -> float | None:
    available = [(float(value), weight) for value, weight in values if value is not None and weight > 0]
    total_weight = sum(weight for _, weight in available)
    return sum(value * weight for value, weight in available) / total_weight if total_weight else None


def _solve_implied_growth(values: Mapping[str, MetricValue], discount_rate: float, terminal_growth: float, target_price: float, low: float, high: float) -> float:
    for _ in range(REVERSE_DCF.max_iterations):
        mid = (low + high) / 2.0
        price = _reverse_dcf_price_at_growth(values, discount_rate, terminal_growth, mid)
        if price is None:
            break
        if abs(price - target_price) <= max(0.01, target_price * REVERSE_DCF.tolerance):
            return mid
        if price < target_price:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _reverse_dcf_price_at_growth(values: Mapping[str, MetricValue], discount_rate: float, terminal_growth: float, growth: float) -> float | None:
    result = dcf_fcff_no_sensitivity(
        DCFInput(
            values["fcff"],
            values["shares"],
            metric_value("wacc", discount_rate, "reverse_dcf"),
            metric_value("growth_years", growth, "reverse_dcf"),
            metric_value("terminal_growth", terminal_growth, "reverse_dcf"),
            values["total_debt"],
            values["cash"],
            values["price"],
        )
    )
    return result.fair_value_per_share


def reverse_dcf_interpretation(implied_growth: float, base_growth: float | None) -> tuple[str, str]:
    if implied_growth <= REVERSE_DCF.plausible_growth:
        status = "plausivel"
        read = "O preco atual exige crescimento moderado dentro da faixa considerada plausivel pelo modelo."
    elif implied_growth <= REVERSE_DCF.demanding_growth:
        status = "exigente"
        read = "O preco atual exige crescimento relevante; a tese precisa confirmar vantagem competitiva, margem e reinvestimento."
    else:
        status = "agressivo"
        read = "O preco atual exige crescimento muito alto; ha menor margem para decepcao nos resultados futuros."
    if base_growth is not None:
        gap = implied_growth - base_growth
        if gap > 0.03:
            read += f" A exigencia fica acima da premissa base em {gap * 100:.1f} p.p."
        elif gap < -0.03:
            read += f" A exigencia fica abaixo da premissa base em {abs(gap) * 100:.1f} p.p."
        else:
            read += " A exigencia esta proxima da premissa base."
    return status, read
