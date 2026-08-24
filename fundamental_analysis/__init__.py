"""Modular fundamental analysis toolkit.

This package is a refactor target for the original notebooks. It keeps the
financial thesis intact while moving assumptions, data lineage, validation,
valuation, scoring, and reporting into auditable Python modules.
"""

from .main import analyze_ticker_from_inputs, analyze_ticker_live
from .notebook_adapter import analyze_from_notebook_globals
from .calibration import build_calibration_diagnostics, run_benchmark_calibration, run_calibration
from .benchmark_universe import DEFAULT_BENCHMARK_CASES, benchmark_tickers
from .historical_calibration import evaluate_historical_outcomes
from .historical_prices import YFinanceHistoricalPriceClient, calculate_price_outcome
from .historical_macro import HistoricalMacroClient
from .point_in_time_collection import collect_benchmark_history, collect_point_in_time_observation
from .sec_edgar import SecEdgarClient
from .scenarios import build_scenarios
from .comparables import build_comparable_report
from .cost_of_capital import calculate_cost_of_capital
from .cash_flow_reconciliation import reconcile_cash_flows
from .cyclical_normalization import CyclicalNormalizationResult, normalize_cyclical_financials
from .peer_discovery import discover_peer_candidates
from .peer_enrichment import enrich_peer_candidates
from .peer_selection import build_peer_selection_report
from .peer_universe import build_peer_universe
from .reports import save_report_artifacts
from .colab import prompt_for_ticker, run_colab_analysis

__all__ = [
    "analyze_ticker_from_inputs",
    "analyze_ticker_live",
    "analyze_from_notebook_globals",
    "run_calibration",
    "run_benchmark_calibration",
    "build_calibration_diagnostics",
    "DEFAULT_BENCHMARK_CASES",
    "benchmark_tickers",
    "evaluate_historical_outcomes",
    "SecEdgarClient",
    "YFinanceHistoricalPriceClient",
    "calculate_price_outcome",
    "HistoricalMacroClient",
    "collect_point_in_time_observation",
    "collect_benchmark_history",
    "build_scenarios",
    "build_comparable_report",
    "calculate_cost_of_capital",
    "reconcile_cash_flows",
    "CyclicalNormalizationResult",
    "normalize_cyclical_financials",
    "discover_peer_candidates",
    "enrich_peer_candidates",
    "build_peer_selection_report",
    "build_peer_universe",
    "save_report_artifacts",
    "prompt_for_ticker",
    "run_colab_analysis",
]
