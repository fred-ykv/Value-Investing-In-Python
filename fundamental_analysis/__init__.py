"""Modular fundamental analysis toolkit.

This package is a refactor target for the original notebooks. It keeps the
financial thesis intact while moving assumptions, data lineage, validation,
valuation, scoring, and reporting into auditable Python modules.
"""

from .main import analyze_ticker_from_inputs, analyze_ticker_live
from .notebook_adapter import analyze_from_notebook_globals
from .calibration import run_calibration
from .scenarios import build_scenarios
from .comparables import build_comparable_report
from .peer_discovery import discover_peer_candidates
from .peer_enrichment import enrich_peer_candidates
from .peer_selection import build_peer_selection_report
from .peer_universe import build_peer_universe

__all__ = [
    "analyze_ticker_from_inputs",
    "analyze_ticker_live",
    "analyze_from_notebook_globals",
    "run_calibration",
    "build_scenarios",
    "build_comparable_report",
    "discover_peer_candidates",
    "enrich_peer_candidates",
    "build_peer_selection_report",
    "build_peer_universe",
]
