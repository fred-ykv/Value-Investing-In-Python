import unittest

from fundamental_analysis.config import CompanyType
from fundamental_analysis.comparables import ComparableReport
from fundamental_analysis.data_sources import metric_value
from fundamental_analysis.metrics import MetricPack
from fundamental_analysis.scoring import compute_score, liquidity_dimension, valuation_dimension
from fundamental_analysis.valuation import ValuationResult


def metric_pack(**values):
    return MetricPack({name: metric_value(name, value, "manual") for name, value in values.items()})


class ScoringCalibrationTests(unittest.TestCase):
    def test_moderate_negative_margin_is_not_scored_as_zero(self):
        metrics = metric_pack(
            revenue_growth=0.20,
            fcff_growth=0.10,
            fama_french_profitability=0.90,
            earnings_quality=0.90,
            piotroski_proxy=0.90,
            debt_to_equity=0.20,
            net_debt_to_ebit=1.00,
            current_ratio=2.00,
        )
        valuations = [ValuationResult("dcf_fcff", 75.0, 0.80, margin_of_safety=-0.25)]

        score = compute_score(CompanyType.TRADITIONAL, valuations, metrics, metric_value("price", 100.0, "manual"))

        self.assertGreater(score.dimensions["valuation"].score, 0.30)
        self.assertEqual(score.recommendation, "Observar")

    def test_low_valuation_and_low_quality_remain_avoid(self):
        metrics = metric_pack(
            revenue_growth=0.25,
            fama_french_profitability=0.10,
            earnings_quality=0.10,
            piotroski_proxy=0.10,
            debt_to_equity=0.00,
            net_debt_to_ebit=0.00,
            current_ratio=2.50,
        )
        valuations = [ValuationResult("dcf_fcff", -20.0, 0.50, margin_of_safety=-2.00)]

        score = compute_score(CompanyType.GROWTH_TECH, valuations, metrics, metric_value("price", 10.0, "manual"))

        self.assertLess(score.dimensions["valuation"].score, 0.20)
        self.assertLess(score.dimensions["quality"].score, 0.30)
        self.assertEqual(score.recommendation, "Evitar")

    def test_bank_valuation_uses_roe_adjusted_price_to_book(self):
        metrics = metric_pack(price_to_book=2.60, roe=0.17)
        valuations = [
            ValuationResult("residual_income", 230.0, 0.77, margin_of_safety=-0.30),
            ValuationResult("ddm", 75.0, 0.80, margin_of_safety=-0.77),
        ]

        dimension = valuation_dimension(valuations, metrics, CompanyType.FINANCIAL)

        self.assertGreater(dimension.score, 0.25)

    def test_growth_tech_liquidity_penalizes_short_cash_runway(self):
        metrics = metric_pack(current_ratio=3.0, cash_runway_years=0.75)

        dimension = liquidity_dimension(metrics, CompanyType.GROWTH_TECH)

        self.assertLess(dimension.score, 0.80)
        self.assertIn("cash runway", dimension.explanation)

    def test_relative_comparables_blend_into_valuation_without_overriding_intrinsic_value(self):
        metrics = metric_pack()
        valuations = [ValuationResult("dcf_fcff", 80.0, 0.80, margin_of_safety=-0.20)]
        comparables = ComparableReport([], overall_score=0.90, confidence=1.0, summary="discount to peers")

        dimension = valuation_dimension(valuations, metrics, CompanyType.TRADITIONAL, comparables)

        self.assertGreater(dimension.score, valuation_dimension(valuations, metrics, CompanyType.TRADITIONAL).score)
        self.assertLess(dimension.score, 0.90)
        self.assertIn("peer-relative", dimension.explanation)


if __name__ == "__main__":
    unittest.main()
