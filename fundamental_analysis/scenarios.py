"""Scenario engine for fundamental valuation stress testing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .config import CompanyType, DCF, GROWTH_TECH, SCENARIOS, ScenarioCase
from .data_sources import MetricValue, clamp, metric_value
from .metrics import MetricPack
from .valuation import DCFInput, ValuationResult


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
    available = [v.fair_value_per_share for v in valuations if v.fair_value_per_share is not None and v.confidence > 0]
    return sum(available) / len(available) if available else None


def aggregate_margin_of_safety(valuations: list[ValuationResult]) -> float | None:
    available = [v.margin_of_safety for v in valuations if v.margin_of_safety is not None and v.confidence > 0]
    return sum(available) / len(available) if available else None


def aggregate_confidence(valuations: list[ValuationResult]) -> float:
    available = [v.confidence for v in valuations if v.confidence > 0]
    return sum(available) / len(available) if available else 0.0


def first_number(*values: object) -> float:
    for value in values:
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0
