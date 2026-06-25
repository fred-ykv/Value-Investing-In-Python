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
class ValuationScoreAssumptions:
    margin_score_curve: Tuple[Tuple[float, float], ...] = (
        (-1.00, 0.00),
        (-0.50, 0.15),
        (-0.25, 0.35),
        (0.00, 0.55),
        (0.25, 0.75),
        (0.50, 0.90),
        (1.00, 1.00),
    )
    bank_model_weight: float = 0.35
    bank_price_to_book_weight: float = 0.20
    bank_roe_weight: float = 0.25
    bank_justified_price_to_book_weight: float = 0.20
    bank_default_cost_of_equity: float = 0.10
    bank_terminal_growth: float = 0.02


@dataclass(frozen=True)
class ScenarioCase:
    key: str
    label: str
    growth_delta: float
    discount_rate_delta: float
    terminal_growth_delta: float
    fcff_adjustment: float
    target_fcf_margin_delta: float
    description: str


@dataclass(frozen=True)
class ScenarioAssumptions:
    cases: Tuple[ScenarioCase, ...] = (
        ScenarioCase(
            key="stress",
            label="Stress",
            growth_delta=-0.12,
            discount_rate_delta=0.03,
            terminal_growth_delta=-0.01,
            fcff_adjustment=-0.35,
            target_fcf_margin_delta=-0.06,
            description="Recessao, compressao de margem, custo de capital maior e menor crescimento terminal.",
        ),
        ScenarioCase(
            key="bear",
            label="Pessimista",
            growth_delta=-0.06,
            discount_rate_delta=0.015,
            terminal_growth_delta=-0.005,
            fcff_adjustment=-0.20,
            target_fcf_margin_delta=-0.03,
            description="Crescimento menor, margem pressionada e taxa de desconto mais alta.",
        ),
        ScenarioCase(
            key="base",
            label="Base",
            growth_delta=0.00,
            discount_rate_delta=0.00,
            terminal_growth_delta=0.00,
            fcff_adjustment=0.00,
            target_fcf_margin_delta=0.00,
            description="Premissas centrais usadas no valuation principal.",
        ),
        ScenarioCase(
            key="bull",
            label="Otimista",
            growth_delta=0.05,
            discount_rate_delta=-0.005,
            terminal_growth_delta=0.005,
            fcff_adjustment=0.15,
            target_fcf_margin_delta=0.03,
            description="Execucao melhor, margem mais alta e custo de capital ligeiramente menor.",
        ),
    )


@dataclass(frozen=True)
class ComparableAssumptions:
    discount_for_strong_score: float = -0.30
    premium_for_weak_score: float = 0.30
    minimum_peer_metrics: int = 2


@dataclass(frozen=True)
class PeerSelectionAssumptions:
    strong_threshold: float = 0.80
    acceptable_threshold: float = 0.65
    weak_threshold: float = 0.50
    min_approved_peers: int = 2
    sector_weight: float = 0.15
    industry_weight: float = 0.20
    sic_weight: float = 0.15
    business_model_weight: float = 0.20
    size_weight: float = 0.10
    growth_weight: float = 0.08
    margin_weight: float = 0.08
    leverage_weight: float = 0.04


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
                valuation=0.25,
                growth=0.15,
                quality=0.25,
                debt=0.15,
                liquidity=0.10,
                data_confidence=0.10,
            ),
            CompanyType.GROWTH_TECH: ScoreWeights(
                valuation=0.15,
                growth=0.25,
                quality=0.30,
                debt=0.05,
                liquidity=0.10,
                data_confidence=0.15,
            ),
            CompanyType.FINANCIAL: ScoreWeights(
                valuation=0.25,
                growth=0.10,
                quality=0.30,
                debt=0.05,
                liquidity=0.05,
                data_confidence=0.25,
            ),
        }
    )
    buy_threshold: float = 0.70
    watch_threshold: float = 0.45
    max_single_valuation_method_weight: float = 0.50
    min_valuation_score_for_buy: float = 0.45
    avoid_if_valuation_below: float = 0.20
    avoid_if_quality_below: float = 0.30


DCF = DCFAssumptions()
GROWTH_TECH = GrowthTechAssumptions()
MARKET = MarketAssumptions()
VALUATION_SCORE = ValuationScoreAssumptions()
SCORE = ScoreConfig()
SCENARIOS = ScenarioAssumptions()
COMPARABLES = ComparableAssumptions()
PEER_SELECTION = PeerSelectionAssumptions()

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
