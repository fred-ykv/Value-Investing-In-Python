"""Orchestration entry points."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import date
from typing import Mapping

from .comparable_reporting import append_comparable_diagnostics_to_html, append_comparable_diagnostics_to_markdown, comparable_diagnostics_table
from .comparables import ComparableReport, build_comparable_report
from .cash_flow_reconciliation import CashFlowReconciliation, append_cash_flow_reconciliation_to_html, append_cash_flow_reconciliation_to_markdown, reconcile_cash_flows
from .config import CYCLICAL, CompanyType, DCF, PEER_ENRICHMENT
from .cost_of_capital import CostOfCapitalResult, calculate_cost_of_capital
from .cost_of_capital_reporting import append_cost_of_capital_to_html, append_cost_of_capital_to_markdown, cost_of_capital_payload
from .cyclical_normalization import CyclicalNormalizationResult, is_cyclical_profile, normalize_cyclical_financials
from .cyclical_reporting import append_cyclical_normalization_to_html, append_cyclical_normalization_to_markdown, cyclical_normalization_payload
from .data_sources import MetricValue, YahooFinanceClient, clamp, metric_value, safe_float
from .dcf_sensitivity_reporting import append_dcf_sensitivity_to_html, append_dcf_sensitivity_to_markdown, dcf_sensitivity_table
from .didactic_reporting import apply_didactic_layer_to_html, apply_didactic_layer_to_markdown, didactic_summary_table
from .executive_reporting import executive_decision_summary
from .financial_statements import FinancialStatements, build_statement_metrics, update_market_from_info
from .html_reports import render_html_report
from .metrics import MetricPack, build_metrics
from .peer_discovery import discover_peer_candidates
from .peer_enrichment import enrich_peer_candidates
from .peer_reporting import append_peer_selection_to_html, append_peer_selection_to_markdown, peer_median_detail_table, peer_selection_visual_table
from .peer_selection import PeerSelectionReport, build_peer_selection_report, merge_peer_medians
from .reports import comparable_table, executive_summary, key_indicator_table, metric_lineage_table, peer_selection_table, render_markdown_report, risk_diagnostics, scenario_table, score_table, valuation_table
from .reverse_dcf_reporting import append_reverse_dcf_to_html, append_reverse_dcf_to_markdown, reverse_dcf_table
from .scenarios import ReverseDCFResult, ScenarioResult, build_reverse_dcf, build_scenarios
from .scoring import ScoreReport, compute_score
from .sector_rules import classify_company
from .valuation import DCFInput, ValuationResult, dcf_fcff, ddm_bank, eva_value, graham_value, growth_tech_value, residual_income_bank
from .visual_reporting import apply_visual_polish_to_html


@dataclass
class AnalysisResult:
    ticker: str
    company_type: str
    valuations: list[ValuationResult]
    scenarios: list[ScenarioResult]
    reverse_dcf: ReverseDCFResult
    peer_selection: PeerSelectionReport
    comparables: ComparableReport
    metrics: MetricPack
    cost_of_capital: CostOfCapitalResult
    cyclical_normalization: CyclicalNormalizationResult
    cash_flow_reconciliation: CashFlowReconciliation
    score: ScoreReport
    report: dict[str, object]


def analyze_ticker_from_inputs(ticker: str, income_statement: Mapping[str, object], balance_sheet: Mapping[str, object], cash_flow: Mapping[str, object], market_data: Mapping[str, object], info: Mapping[str, object] | None = None, source: str = "manual") -> AnalysisResult:
    statements = FinancialStatements(ticker, income_statement, balance_sheet, cash_flow, market_data, info or {}, source)
    statements = update_market_from_info(statements)
    statement_metrics = build_statement_metrics(statements)
    metrics = build_metrics(statement_metrics.values)
    company_type = classify_company(statements.info, has_negative_fcf=(statement_metrics.get("fcff").value or 0.0) < 0)
    values = statement_metrics.values
    cyclical_normalization = normalize_cyclical_financials(
        company_type,
        values,
        market_data.get("cyclical_history", ()),
        statements.info,
        market_data,
    )
    enrich_metrics_with_market_inputs(metrics, market_data, source)
    capital = calculate_cost_of_capital(company_type, values, market_data, source)
    growth_years = resolve_valuation_assumption("growth_years", market_data.get("growth_years"), DCF.default_growth_years, DCF.min_growth_years, DCF.max_growth_years, source)
    if (
        cyclical_normalization.applied
        and growth_years.value is not None
        and growth_years.value > CYCLICAL.maximum_normalized_growth
    ):
        growth_years = replace(
            growth_years,
            value=CYCLICAL.maximum_normalized_growth,
            note=(
                f"Crescimento limitado a {CYCLICAL.maximum_normalized_growth:.1%} "
                "por partir de lucros normalizados do ciclo"
            ),
            is_fallback=True,
            confidence=max(0.0, growth_years.confidence - 0.05),
        )
    terminal_growth = resolve_valuation_assumption("terminal_growth", market_data.get("terminal_growth"), DCF.default_terminal_growth, DCF.min_terminal_growth, min(DCF.max_terminal_growth, capital.discount_rate - DCF.min_spread_wacc_terminal), source)
    ke = metric_value("ke", capital.cost_of_equity, "derived", capital.sources.get("cost_of_equity", "Custo do patrimonio calculado"), confidence=capital.component_confidences.get("cost_of_equity", capital.confidence))
    resolved_market_data = {
        **market_data,
        "wacc": capital.discount_rate_metric(),
        "ke": ke,
        "growth_years": growth_years,
        "terminal_growth": terminal_growth,
        "cyclical_normalization": cyclical_normalization,
    }
    dcf_input = DCFInput(
        values["fcff"],
        values["shares"],
        capital.discount_rate_metric(),
        growth_years,
        terminal_growth,
        values["total_debt"],
        values["cash"],
        values["price"],
        cyclical_normalization.normalized_fcff if cyclical_normalization.applied else None,
        cyclical_normalization.transition_years if cyclical_normalization.applied else 0,
    )
    valuations = build_valuations(company_type, values, metrics, resolved_market_data, source, dcf_input)
    scenarios = build_scenarios(company_type, values, metrics, resolved_market_data, source, build_valuations, capital.discount_rate)
    reverse_dcf = build_reverse_dcf(values, resolved_market_data, capital.discount_rate)
    use_peer_yahoo = peer_yahoo_enrichment_enabled(market_data)
    peer_candidates = enrich_peer_candidates(
        discover_peer_candidates({**statements.info, **market_data}, metrics, market_data),
        use_yahoo=use_peer_yahoo,
    )
    peer_selection = build_peer_selection_report({**statements.info, **market_data}, metrics, peer_candidates)
    comparable_market_data = {**statements.info, **merge_peer_medians(market_data, peer_selection)}
    comparables = build_comparable_report(company_type, values, metrics, comparable_market_data)
    score = compute_score(company_type, valuations, metrics, values["price"], comparables)
    cash_flow_reconciliation = reconcile_cash_flows(values)
    metric_lineage = {**values, **metrics.values}
    markdown = render_markdown_report(ticker, score, valuations, metric_lineage, scenarios, comparables, None)
    markdown = append_peer_selection_to_markdown(markdown, peer_selection)
    markdown = append_comparable_diagnostics_to_markdown(markdown, comparables)
    markdown = append_cost_of_capital_to_markdown(markdown, capital)
    markdown = append_cash_flow_reconciliation_to_markdown(markdown, cash_flow_reconciliation)
    markdown = append_cyclical_normalization_to_markdown(markdown, cyclical_normalization, metric_lineage)
    markdown = append_dcf_sensitivity_to_markdown(markdown, valuations)
    markdown = append_reverse_dcf_to_markdown(markdown, reverse_dcf)
    markdown = apply_didactic_layer_to_markdown(markdown, score, metric_lineage, valuations)
    html = render_html_report(ticker, score, valuations, metric_lineage, scenarios, comparables, None)
    html = append_peer_selection_to_html(html, peer_selection)
    html = append_comparable_diagnostics_to_html(html, comparables)
    html = append_cost_of_capital_to_html(html, capital)
    html = append_cash_flow_reconciliation_to_html(html, cash_flow_reconciliation)
    html = append_cyclical_normalization_to_html(html, cyclical_normalization, metric_lineage)
    html = append_dcf_sensitivity_to_html(html, valuations)
    html = append_reverse_dcf_to_html(html, reverse_dcf)
    html = apply_didactic_layer_to_html(html, score, metric_lineage, valuations)
    html = apply_visual_polish_to_html(html, score.recommendation)
    report = {
        "executive_summary": executive_summary(ticker, score, valuations),
        "executive_decision": executive_decision_summary(score, valuations),
        "valuation_table": valuation_table(valuations),
        "cost_of_capital": cost_of_capital_payload(capital),
        "cyclical_normalization": cyclical_normalization_payload(cyclical_normalization, metric_lineage),
        "cash_flow_reconciliation": cash_flow_reconciliation.payload(),
        "dcf_sensitivity_table": dcf_sensitivity_table(valuations),
        "scenario_table": scenario_table(scenarios),
        "reverse_dcf": reverse_dcf_table(reverse_dcf),
        "peer_selection_table": peer_selection_table(peer_selection),
        "peer_selection_visual_table": peer_selection_visual_table(peer_selection),
        "peer_median_detail_table": peer_median_detail_table(peer_selection),
        "comparable_table": comparable_table(comparables),
        "comparable_diagnostics": comparable_diagnostics_table(comparables),
        "key_indicator_table": key_indicator_table(metric_lineage),
        "score_table": score_table(score),
        "metric_lineage_table": metric_lineage_table(metric_lineage),
        "risk_diagnostics": risk_diagnostics(score, valuations, metric_lineage),
        "didactic_summary": didactic_summary_table(score, metric_lineage, valuations),
        "recommendation": score.recommendation,
        "markdown": markdown,
        "html": html,
    }
    return AnalysisResult(ticker, company_type.value, valuations, scenarios, reverse_dcf, peer_selection, comparables, metrics, capital, cyclical_normalization, cash_flow_reconciliation, score, report)


def analyze_ticker_live(
    ticker: str,
    *,
    sec_user_agent: str | None = None,
) -> AnalysisResult:
    fetch = YahooFinanceClient(ticker).fetch_financial_statements()
    if not fetch.ok:
        raise RuntimeError(f"Could not fetch {ticker} from Yahoo Finance: {fetch.error}")
    statements = fetch.payload
    statements = _enrich_live_cyclical_history(statements, sec_user_agent)
    return analyze_ticker_from_inputs(statements.ticker, statements.income_statement, statements.balance_sheet, statements.cash_flow, statements.market_data, statements.info, statements.source)


def _enrich_live_cyclical_history(
    statements: FinancialStatements,
    sec_user_agent: str | None,
) -> FinancialStatements:
    market_data = dict(statements.market_data)
    if not is_cyclical_profile(statements.info, market_data):
        return statements

    market_data["is_cyclical"] = True
    user_agent = (sec_user_agent or os.getenv("SEC_USER_AGENT", "")).strip()
    if not user_agent:
        market_data["cyclical_history_warning"] = (
            "Historico SEC nao consultado porque SEC_USER_AGENT nao foi configurado; "
            "foi mantido apenas o historico anual disponivel no Yahoo Finance."
        )
        return replace(statements, market_data=market_data)

    try:
        from .sec_edgar import SecEdgarClient

        snapshots = SecEdgarClient(user_agent).build_annual_history(
            statements.ticker,
            date.today(),
            max_filings=CYCLICAL.maximum_years,
        )
        sec_history = [snapshot.as_financial_statements() for snapshot in snapshots]
        if sec_history:
            market_data["cyclical_history"] = _merge_cyclical_history(
                market_data.get("cyclical_history", ()),
                sec_history,
            )
        else:
            market_data["cyclical_history_warning"] = (
                "A SEC nao retornou demonstracoes anuais suficientes; foi mantido o "
                "historico anual disponivel no Yahoo Finance."
            )
    except Exception as exc:
        market_data["cyclical_history_warning"] = (
            "Historico SEC indisponivel; foi mantido o historico anual do Yahoo "
            f"Finance ({type(exc).__name__}: {exc})."
        )
    return replace(statements, market_data=market_data)


def _merge_cyclical_history(
    yahoo_history: object,
    sec_history: list[FinancialStatements],
) -> list[FinancialStatements]:
    combined: dict[date, FinancialStatements] = {}
    candidates: list[object] = []
    if isinstance(yahoo_history, (list, tuple)):
        candidates.extend(yahoo_history)
    candidates.extend(sec_history)
    for item in candidates:
        if not isinstance(item, FinancialStatements):
            continue
        revenue = build_statement_metrics(item).values.get("revenue")
        if revenue is not None and revenue.period_end is not None:
            combined[revenue.period_end] = item
    return [combined[period] for period in sorted(combined)][-CYCLICAL.maximum_years :]


def enrich_metrics_with_market_inputs(metrics: MetricPack, market_data: Mapping[str, object], source: str) -> None:
    for name in ("revenue_growth", "fcff_growth", "rule_of_40", "gross_margin", "cash_runway_years", "dividend_per_share", "revenue_cagr_5y", "earnings_cagr_5y"):
        if name in market_data:
            metrics.values[name] = metric_value(name, market_data[name], source)


def peer_yahoo_enrichment_enabled(market_data: Mapping[str, object]) -> bool:
    if "enable_peer_yahoo_enrichment" in market_data:
        return bool(market_data.get("enable_peer_yahoo_enrichment"))
    return PEER_ENRICHMENT.use_yahoo_info


def build_valuations(company_type: CompanyType, values: Mapping[str, MetricValue], metrics: MetricPack, market_data: Mapping[str, object], source: str, dcf_input: DCFInput) -> list[ValuationResult]:
    current_price = values["price"]
    terminal_growth = preserve_metric("terminal_growth", market_data.get("terminal_growth"), source)
    ke = preserve_metric("ke", market_data.get("ke"), source)
    if not ke.is_available:
        ke = metric_value("ke", infer_cost_of_equity(values, market_data), source)
    wacc = preserve_metric("wacc", market_data.get("wacc"), source)
    if not wacc.is_available:
        wacc = metric_value("wacc", ke.value, source)
    if company_type == CompanyType.FINANCIAL:
        return [
            residual_income_bank(values["book_value_per_share"], metric_value("roe", metrics.get("roe"), "derived"), ke, terminal_growth, current_price),
            ddm_bank(metric_value("dividend_per_share", market_data.get("dividend_per_share"), source), ke, terminal_growth, current_price),
        ]
    if company_type == CompanyType.GROWTH_TECH:
        net_debt = values["net_debt"]
        net_cash = metric_value(
            "net_cash",
            None if not net_debt.is_available else -float(net_debt.value),
            "derived",
            "Net cash = cash - total debt",
            confidence=net_debt.confidence,
        )
        return [growth_tech_value(values["revenue"], metric_value("revenue_growth", market_data.get("revenue_growth"), source), metric_value("target_fcf_margin", market_data.get("target_fcf_margin"), source), net_cash, values["shares"], current_price, wacc), dcf_fcff(dcf_input)]
    normalization = market_data.get("cyclical_normalization")
    normalized = (
        normalization
        if isinstance(normalization, CyclicalNormalizationResult) and normalization.applied
        else None
    )
    income = normalized.normalized_net_income if normalized else values["net_income"]
    eps = None if income.value is None or values["shares"].value in (None, 0) else income.value / values["shares"].value
    eps_metric = metric_value(
        "eps",
        eps,
        "cyclical_normalization" if normalized else "derived",
        "Lucro liquido normalizado / acoes" if normalized else "Lucro liquido corrente / acoes",
        source_url=income.source_url,
        source_document=income.source_document,
        period_start=income.period_start,
        period_end=income.period_end,
        filing_date=income.filing_date,
        as_of=income.as_of,
        currency=income.currency,
        scale="per_share",
        basis="normalized" if normalized else "derived",
        formula="normalized_net_income_divided_by_shares" if normalized else "net_income_divided_by_shares",
        confidence=min(income.confidence, values["shares"].confidence) if eps is not None else 0.0,
    )
    roic = (
        normalized.normalized_roic
        if normalized and normalized.normalized_roic.is_available
        else metric_value("roic", metrics.get("roic_proxy"), "derived")
    )
    return [
        dcf_fcff(dcf_input),
        graham_value(eps_metric, values["book_value_per_share"], current_price),
        eva_value(
            values["invested_capital"],
            roic,
            wacc,
            terminal_growth,
            values["shares"],
            current_price,
            values["net_debt"],
        ),
    ]


def infer_cost_of_equity(values: Mapping[str, MetricValue], market_data: Mapping[str, object]) -> float:
    return calculate_cost_of_capital(CompanyType.FINANCIAL, values, market_data).cost_of_equity


def preserve_metric(name: str, value: object, source: str) -> MetricValue:
    if isinstance(value, MetricValue):
        return value
    return metric_value(name, value, source)


def resolve_valuation_assumption(name: str, value: object, default: float, lower: float, upper: float, source: str) -> MetricValue:
    if isinstance(value, MetricValue) and value.is_available:
        bounded = clamp(float(value.value), lower, upper)
        if bounded == value.value:
            return replace(value, name=name)
        return replace(
            value,
            name=name,
            value=bounded,
            note=f"Premissa limitada de {value.value:.2%} para {bounded:.2%}",
            is_fallback=True,
            confidence=max(0.0, value.confidence - 0.15),
        )
    numeric = safe_float(value)
    if numeric is not None:
        bounded = clamp(numeric, lower, upper)
        return metric_value(name, bounded, source, "Premissa informada" if bounded == numeric else f"Premissa limitada de {numeric:.2%} para {bounded:.2%}", is_fallback=bounded != numeric)
    return metric_value(name, clamp(default, lower, upper), "fallback", "Premissa padrao de config.py", is_fallback=True)
