"""Central assumptions and scoring configuration.

All arbitrary financial assumptions should live here instead of being spread
across notebooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple


class CompanyType(str, Enum):
    TRADITIONAL = "tradicional"
    GROWTH_TECH = "growth_tech"
    FINANCIAL = "bancos_financeiras"


@dataclass(frozen=True)
class DCFAssumptions:
    horizon_years: int = 10
    default_wacc: float = 0.11
    default_growth_years: float = 0.05
    default_terminal_growth: float = 0.02
    min_growth_years: float = -0.10
    max_growth_years: float = 0.30
    min_terminal_growth: float = -0.01
    max_terminal_growth: float = 0.04
    min_spread_wacc_terminal: float = 0.01
    safety_margin_required: float = 0.25
    negative_fcff_confidence_penalty: float = 0.30
    sensitivity_wacc_range: Tuple[float, ...] = (0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14)
    sensitivity_terminal_growth_range: Tuple[float, ...] = (0.00, 0.01, 0.02, 0.03, 0.04)


@dataclass(frozen=True)
class GrowthTechAssumptions:
    default_discount_rate: float = 0.11
    terminal_growth: float = 0.03
    target_fcf_margin: float = 0.18
    rule_of_40_strong: float = 0.40
    rule_of_40_weak: float = 0.20
    min_cash_runway_years: float = 2.0


@dataclass(frozen=True)
class MarketAssumptions:
    risk_free_rate: float = 0.045
    equity_risk_premium: float = 0.055
    default_beta: float = 1.0


@dataclass(frozen=True)
class ScoreWeights:
    valuation: float
    growth: float
    quality: float
    debt: float
    liquidity: float
    data_confidence: float

    def normalized(self) -> "ScoreWeights":
        total = (
            self.valuation
            + self.growth
            + self.quality
            + self.debt
            + self.liquidity
            + self.data_confidence
        )
        if total == 0:
            raise ValueError("Score weight total cannot be zero")
        return ScoreWeights(
            valuation=self.valuation / total,
            growth=self.growth / total,
            quality=self.quality / total,
            debt=self.debt / total,
            liquidity=self.liquidity / total,
            data_confidence=self.data_confidence / total,
        )


@dataclass(frozen=True)
class ScoreConfig:
    weights_by_type: Dict[CompanyType, ScoreWeights] = field(
        default_factory=lambda: {
            CompanyType.TRADITIONAL: ScoreWeights(
                valuation=0.30,
                growth=0.15,
                quality=0.25,
                debt=0.15,
                liquidity=0.05,
                data_confidence=0.10,
            ),
            CompanyType.GROWTH_TECH: ScoreWeights(
                valuation=0.20,
                growth=0.30,
                quality=0.20,
                debt=0.05,
                liquidity=0.10,
                data_confidence=0.15,
            ),
            CompanyType.FINANCIAL: ScoreWeights(
                valuation=0.30,
                growth=0.10,
                quality=0.30,
                debt=0.05,
                liquidity=0.05,
                data_confidence=0.20,
            ),
        }
    )
    buy_threshold: float = 0.70
    watch_threshold: float = 0.45
    max_single_valuation_method_weight: float = 0.50


DCF = DCFAssumptions()
GROWTH_TECH = GrowthTechAssumptions()
MARKET = MarketAssumptions()
SCORE = ScoreConfig()

DATA_SOURCE_CONFIDENCE = {
    "yfinance": 0.80,
    "finviz": 0.65,
    "zacks": 0.45,
    "fundamentus": 0.55,
    "manual": 0.70,
    "notebook": 0.70,
    "derived": 0.75,
    "fallback": 0.50,
    "missing": 0.00,
}
