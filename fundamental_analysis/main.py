"""Orchestration entry points."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .comparables import ComparableReport, build_comparable_report
from .config import CompanyType, MARKET
from .data_sources import MetricValue, YahooFinanceClient, metric_value
from .financial_statements import FinancialStatements, build_statement_metrics, update_market_from_info
from .metrics import MetricPack, build_metrics
from .peer_discovery import discover_peer_candidates
from .peer_enrichment import enrich_peer_candidates
from .peer_selection import PeerSelectionReport, build_peer_selection_report, merge_peer_medians
from .reports import comparable_table, executive_summary, metric_lineage_table, peer_selection_table, render_markdown_report, risk_diagnostics, scenario_table, score_table, valuation_table
from .scenarios import ScenarioResult, build_scenarios
from .scoring import ScoreReport, compute_score
from .sector_rules import classify_company
from .valuation import DCFInput, ValuationResult, dcf_fcff, ddm_bank, eva_value, graham_value, growth_tech_value, residual_income_bank


@dataclass
class AnalysisResult:
    ticker: str
    company_type: str
    valuations: list[ValuationResult]
    scenarios: list[ScenarioResult]
    peer_selection: PeerSelectionReport
    comparables: ComparableReport
    metrics: MetricPack
    score: ScoreReport
    report: dict[str, object]


def analyze_ticker_from_inputs(ticker: str, income_statement: Mapping[str, float], balance_sheet: Mapping[str, float], cash_flow: Mapping[str, float], market_data: Mapping[str, float], info: Mapping[str, object] | None = None, source: str = "manual") -> AnalysisResult:
    statements = FinancialStatements(ticker, income_statement, balance_sheet, cash_flow, market_data, info or {}, source)
    statements = update_market_from_info(statements)
    statement_metrics = build_statement_metrics(statements)
    metrics = build_metrics(statement_metrics.values)
    company_type = classify_company(statements.info, has_negative_fcf=(statement_metrics.get("fcff").value or 0.0) < 0)
    values = statement_metrics.values
    enrich_metrics_with_market_inputs(metrics, market_data, source)
    cost_of_capital = market_data.get("wacc", infer_cost_of_equity(values, market_data))
    dcf_input = DCFInput(values["fcff"], values["shares"], metric_value("wacc", cost_of_capital, source), metric_value("growth_years", market_data.get("growth_years"), source), metric_value("terminal_growth", market_data.get("terminal_growth"), source), values["total_debt"], values["cash"], values["price"])
    valuations = build_valuations(company_type, values, metrics, market_data, source, dcf_input)
    scenarios = build_scenarios(company_type, values, metrics, market_data, source, build_valuations, cost_of_capital)
    use_peer_yahoo = bool(market_data.get("enable_peer_yahoo_enrichment", source == "yfinance"))
    peer_candidates = enrich_peer_candidates(
        discover_peer_candidates({**statements.info, **market_data}, metrics, market_data),
        use_yahoo=use_peer_yahoo,
    )
    peer_selection = build_peer_selection_report({**statements.info, **market_data}, metrics, peer_candidates)
    comparable_market_data = merge_peer_medians(market_data, peer_selection)
    comparables = build_comparable_report(company_type, values, metrics, comparable_market_data)
    score = compute_score(company_type, valuations, metrics, values["price"], comparables)
    metric_lineage = {**values, **metrics.values}
    report = {
        "executive_summary": executive_summary(ticker, score, valuations),
        "valuation_table": valuation_table(valuations),
        "scenario_table": scenario_table(scenarios),
        "peer_selection_table": peer_selection_table(peer_selection),
        "comparable_table": comparable_table(comparables),
        "score_table": score_table(score),
        "metric_lineage_table": metric_lineage_table(metric_lineage),
        "risk_diagnostics": risk_diagnostics(score, valuations, metric_lineage),
        "recommendation": score.recommendation,
        "markdown": render_markdown_report(ticker, score, valuations, metric_lineage, scenarios, comparables, peer_selection),
    }
    return AnalysisResult(ticker, company_type.value, valuations, scenarios, peer_selection, comparables, metrics, score, report)


def analyze_ticker_live(ticker: str) -> AnalysisResult:
    fetch = YahooFinanceClient(ticker).fetch_financial_statements()
    if not fetch.ok:
        raise RuntimeError(f"Could not fetch {ticker} from Yahoo Finance: {fetch.error}")
    statements = fetch.payload
    return analyze_ticker_from_inputs(statements.ticker, statements.income_statement, statements.balance_sheet, statements.cash_flow, statements.market_data, statements.info, statements.source)


def enrich_metrics_with_market_inputs(metrics: MetricPack, market_data: Mapping[str, float], source: str) -> None:
    for name in ("revenue_growth", "fcff_growth", "rule_of_40", "gross_margin", "cash_runway_years"):
        if name in market_data:
            metrics.values[name] = metric_value(name, market_data[name], source)


def build_valuations(company_type: CompanyType, values: Mapping[str, MetricValue], metrics: MetricPack, market_data: Mapping[str, float], source: str, dcf_input: DCFInput) -> list[ValuationResult]:
    current_price = values["price"]
    terminal_growth = metric_value("terminal_growth", market_data.get("terminal_growth"), source)
    ke = metric_value("ke", market_data.get("ke", market_data.get("wacc", infer_cost_of_equity(values, market_data))), source)
    if company_type == CompanyType.FINANCIAL:
        return [
            residual_income_bank(values["book_value_per_share"], metric_value("roe", metrics.get("roe"), "derived"), ke, terminal_growth, current_price),
            ddm_bank(metric_value("dividend_per_share", market_data.get("dividend_per_share"), source), ke, terminal_growth, current_price),
        ]
    if company_type == CompanyType.GROWTH_TECH:
        net_cash = metric_value("net_cash", (values["cash"].value or 0.0) - (values["total_debt"].value or 0.0), "derived")
        return [growth_tech_value(values["revenue"], metric_value("revenue_growth", market_data.get("revenue_growth"), source), metric_value("target_fcf_margin", market_data.get("target_fcf_margin"), source), net_cash, values["shares"], current_price, ke), dcf_fcff(dcf_input)]
    eps = None if values["net_income"].value is None or values["shares"].value in (None, 0) else values["net_income"].value / values["shares"].value
    invested = None if values["equity"].value is None else values["equity"].value + (values["total_debt"].value or 0.0) - (values["cash"].value or 0.0)
    return [dcf_fcff(dcf_input), graham_value(metric_value("eps", eps, "derived"), values["book_value_per_share"], current_price), eva_value(metric_value("invested_capital", invested, "derived"), metric_value("roic", metrics.get("roic_proxy"), "derived"), metric_value("wacc", market_data.get("wacc", infer_cost_of_equity(values, market_data)), source), terminal_growth, values["shares"], current_price)]


def infer_cost_of_equity(values: Mapping[str, MetricValue], market_data: Mapping[str, float]) -> float:
    beta = market_data.get("beta") if market_data.get("beta") is not None else values.get("beta", MetricValue("beta", None, "missing", 0.0)).value
    return MARKET.risk_free_rate + float(beta if beta is not None else MARKET.default_beta) * MARKET.equity_risk_premium
