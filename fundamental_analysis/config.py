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
    default_credit_spread: float = 0.020
    min_beta: float = 0.0
    max_beta: float = 3.0
    min_discount_rate: float = 0.01
    max_discount_rate: float = 0.50
    max_pre_tax_cost_of_debt: float = 0.30
    risk_free_rate_source: str = "Premissa configurada; atualizar com Treasury compativel com o horizonte"
    equity_risk_premium_source: str = "Premissa configurada; atualizar com ERP de mercado documentado"


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
    intrinsic_weight: float = 0.70
    relative_weight: float = 0.30
    minimum_relative_confidence: float = 0.25


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
class ReverseDCFAssumptions:
    min_growth: float = -0.20
    max_growth: float = 0.60
    tolerance: float = 0.0001
    max_iterations: int = 80
    plausible_growth: float = 0.08
    demanding_growth: float = 0.15


@dataclass(frozen=True)
class CashFlowReconciliationAssumptions:
    close_gap_ratio: float = 0.20
    moderate_gap_ratio: float = 0.50


@dataclass(frozen=True)
class CyclicalNormalizationAssumptions:
    minimum_years: int = 5
    target_years: int = 8
    maximum_years: int = 10
    winsor_tail_fraction: float = 0.10
    minimum_confidence: float = 0.58
    transition_years: int = 3
    maximum_normalized_growth: float = 0.08
    cycle_position_margin_gap: float = 0.02
    maximum_fcff_crosscheck_gap: float = 0.03
    nwc_fallback_confidence_penalty: float = 0.18
    operating_margin_bounds: Tuple[float, float] = (-0.25, 0.50)
    net_margin_bounds: Tuple[float, float] = (-0.30, 0.40)
    fcff_margin_bounds: Tuple[float, float] = (-0.40, 0.50)
    reinvestment_margin_bounds: Tuple[float, float] = (-0.30, 0.60)
    tax_rate_bounds: Tuple[float, float] = (0.00, 0.45)
    industry_keywords: Tuple[str, ...] = (
        "steel",
        "metal fabrication",
        "metals",
        "mining",
        "commodity",
        "chemicals",
        "farm machinery",
        "agricultural machinery",
        "heavy machinery",
        "construction machinery",
        "auto manufacturers",
        "automobile manufacturers",
    )


@dataclass(frozen=True)
class CalibrationAssumptions:
    minimum_total_sample: int = 40
    minimum_sample_per_group: int = 8
    maximum_recommendation_concentration: float = 0.75
    minimum_score_spread: float = 0.20
    minimum_data_confidence: float = 0.55
    maximum_error_rate: float = 0.15
    outcome_bucket_count: int = 5
    forward_horizon_months: int = 12
    minimum_historical_observations: int = 100
    minimum_outcome_coverage: float = 0.90
    minimum_point_in_time_ratio: float = 0.95
    minimum_spearman_correlation: float = 0.10
    minimum_monotonic_bucket_ratio: float = 0.60


@dataclass(frozen=True)
class PointInTimeAssumptions:
    sec_base_url: str = "https://data.sec.gov"
    sec_ticker_map_url: str = "https://www.sec.gov/files/company_tickers.json"
    sec_user_agent_env: str = "SEC_USER_AGENT"
    sec_max_requests_per_second: float = 8.0
    request_timeout_seconds: int = 30
    cache_directory: str = ".cache/sec_edgar"
    cache_max_age_hours: int = 24
    macro_cache_directory: str = ".cache/historical_macro"
    macro_cache_max_age_hours: int = 24
    macro_http_user_agent: str = "Value-Investing-In-Python/1.0 historical-research"
    treasury_csv_url_template: str = (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
        "daily-treasury-rates.csv/{year}/all?_format=csv&field_tdr_date_value={year}"
        "&page=&type=daily_treasury_yield_curve"
    )
    treasury_maturity_column: str = "10 Yr"
    risk_free_max_staleness_days: int = 7
    damodaran_historical_erp_url: str = (
        "https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/histimpl.html"
    )
    erp_publication_month: int = 1
    erp_publication_day: int = 15
    annual_forms: Tuple[str, ...] = ("10-K", "20-F", "40-F")
    minimum_filing_lag_days: int = 1
    minimum_fundamental_coverage: float = 0.70
    price_start_max_lag_days: int = 7
    price_end_max_lag_days: int = 7
    forward_horizon_months: int = 12
    beta_lookback_months: int = 24
    minimum_beta_return_observations: int = 126
    historical_start_year: int = 2015
    max_annual_filings_per_company: int = 5
    benchmark_by_group: Tuple[Tuple[str, str], ...] = (
        ("tradicionais_ciclicas", "SPY"),
        ("growth_tech", "QQQ"),
        ("bancos_financeiras", "KBE"),
        ("fcf_negativo_early_growth", "IWM"),
    )

    def benchmark_for_group(self, group: str) -> str:
        return dict(self.benchmark_by_group).get(group, "SPY")


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
    min_evidence_weight: float = 0.50


@dataclass(frozen=True)
class PeerDiscoveryAssumptions:
    max_candidates: int = 12
    min_candidate_score: float = 0.55
    min_evidence_weight: float = 0.55
    sector_weight: float = 0.20
    industry_weight: float = 0.25
    sic_weight: float = 0.15
    business_model_weight: float = 0.20
    size_weight: float = 0.10
    growth_weight: float = 0.05
    margin_weight: float = 0.05


@dataclass(frozen=True)
class PeerUniverseAssumptions:
    use_builtin_seed_universe: bool = True
    max_seed_candidates: int = 20


@dataclass(frozen=True)
class PeerEnrichmentAssumptions:
    use_yahoo_info: bool = True
    minimum_confidence_for_relative_valuation: float = 0.45


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
REVERSE_DCF = ReverseDCFAssumptions()
CASH_FLOW_RECONCILIATION = CashFlowReconciliationAssumptions()
CYCLICAL = CyclicalNormalizationAssumptions()
CALIBRATION = CalibrationAssumptions()
POINT_IN_TIME = PointInTimeAssumptions()
COMPARABLES = ComparableAssumptions()
PEER_SELECTION = PeerSelectionAssumptions()
PEER_DISCOVERY = PeerDiscoveryAssumptions()
PEER_UNIVERSE = PeerUniverseAssumptions()
PEER_ENRICHMENT = PeerEnrichmentAssumptions()

# Fallback de segunda linha para comparaveis quando a cesta de pares aprovada
# nao tiver medianas suficientes. Deve ser tratado como benchmark setorial,
# nao como pares empresa-a-empresa.
DAMODARAN_SECTOR_BENCHMARKS = {
    "bank": {
        "price_to_book": 1.25,
        "price_to_earnings": 11.0,
    },
    "metal_fabrication": {
        "price_to_earnings": 18.0,
        "ev_to_ebitda": 10.0,
        "ev_to_ebit": 13.0,
        "ev_to_sales": 1.6,
        "price_to_book": 2.2,
    },
    "software": {
        "price_to_earnings": 35.0,
        "ev_to_sales": 7.0,
        "price_to_sales": 6.5,
    },
    "semiconductor": {
        "price_to_earnings": 28.0,
        "ev_to_ebitda": 16.0,
        "ev_to_ebit": 20.0,
        "ev_to_sales": 5.5,
        "price_to_book": 5.0,
    },
    "auto_manufacturers": {
        "price_to_earnings": 12.0,
        "ev_to_ebitda": 8.0,
        "ev_to_ebit": 11.0,
        "ev_to_sales": 0.9,
        "price_to_book": 1.5,
    },
    "retail": {
        "price_to_earnings": 22.0,
        "ev_to_ebitda": 12.0,
        "ev_to_ebit": 16.0,
        "ev_to_sales": 1.2,
        "price_to_book": 3.0,
    },
    "pharma": {
        "price_to_earnings": 24.0,
        "ev_to_ebitda": 14.0,
        "ev_to_ebit": 18.0,
        "ev_to_sales": 4.5,
        "price_to_book": 4.0,
    },
}

DATA_SOURCE_CONFIDENCE = {
    "sec_edgar": 0.90,
    "sec_edgar_derived": 0.82,
    "yfinance_historical": 0.75,
    "us_treasury_historical": 0.95,
    "damodaran_historical_erp": 0.78,
    "yfinance": 0.80,
    "yfinance_derived": 0.75,
    "finviz": 0.65,
    "zacks": 0.45,
    "fundamentus": 0.55,
    "manual": 0.70,
    "notebook": 0.70,
    "derived": 0.75,
    "cyclical_normalization": 0.75,
    "fallback": 0.50,
    "missing": 0.00,
}
