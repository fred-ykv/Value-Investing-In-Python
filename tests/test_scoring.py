import unittest

from fundamental_analysis.config import CompanyType, SCORE
from fundamental_analysis.comparables import ComparableReport
from fundamental_analysis.data_sources import metric_value
from fundamental_analysis.metrics import MetricPack
from fundamental_analysis.scoring import (
    DimensionScore,
    compute_score,
    liquidity_dimension,
    recommendation_decision_from_score,
    recommendation_from_score,
    valuation_dimension,
)
from fundamental_analysis.valuation import ValuationResult


def metric_pack(**values):
    return MetricPack({name: metric_value(name, value, "manual") for name, value in values.items()})


class ScoringCalibrationTests(unittest.TestCase):
    def test_structured_decision_records_buy_gate_without_changing_result(self):
        dimensions = {
            "valuation": DimensionScore("valuation", 0.44, 0.80, ""),
            "quality": DimensionScore("quality", 0.90, 0.80, ""),
        }

        decision = recommendation_decision_from_score(0.75, dimensions)

        self.assertEqual(decision.recommendation_before_gates, "Comprar")
        self.assertEqual(decision.final_recommendation, "Observar")
        self.assertEqual(decision.gate_code, "buy_blocked_low_valuation")
        self.assertTrue(decision.gate_triggered)

    def test_structured_decision_records_joint_valuation_quality_gate(self):
        dimensions = {
            "valuation": DimensionScore("valuation", 0.19, 0.80, ""),
            "quality": DimensionScore("quality", 0.29, 0.80, ""),
        }

        decision = recommendation_decision_from_score(0.60, dimensions)

        self.assertEqual(decision.recommendation_before_gates, "Observar")
        self.assertEqual(decision.final_recommendation, "Evitar")
        self.assertEqual(decision.gate_code, "avoid_low_valuation_and_quality")
        self.assertTrue(decision.gate_triggered)

    def test_structured_decision_is_equivalent_to_previous_gate_logic_at_boundaries(self):
        epsilon = 1e-9

        def previous_logic(total, valuation, quality):
            if total >= SCORE.buy_threshold and valuation < SCORE.min_valuation_score_for_buy:
                return "Observar"
            if (
                total >= SCORE.watch_threshold
                and valuation < SCORE.avoid_if_valuation_below
                and quality < SCORE.avoid_if_quality_below
            ):
                return "Evitar"
            return (
                "Comprar"
                if total >= SCORE.buy_threshold
                else "Observar"
                if total >= SCORE.watch_threshold
                else "Evitar"
            )

        totals = (
            SCORE.watch_threshold - epsilon,
            SCORE.watch_threshold,
            SCORE.buy_threshold - epsilon,
            SCORE.buy_threshold,
        )
        valuations = (
            SCORE.avoid_if_valuation_below - epsilon,
            SCORE.avoid_if_valuation_below,
            SCORE.min_valuation_score_for_buy - epsilon,
            SCORE.min_valuation_score_for_buy,
        )
        qualities = (
            SCORE.avoid_if_quality_below - epsilon,
            SCORE.avoid_if_quality_below,
            0.90,
        )
        for total in totals:
            for valuation in valuations:
                for quality in qualities:
                    dimensions = {
                        "valuation": DimensionScore("valuation", valuation, 1.0, ""),
                        "quality": DimensionScore("quality", quality, 1.0, ""),
                    }
                    expected = previous_logic(total, valuation, quality)
                    with self.subTest(total=total, valuation=valuation, quality=quality):
                        self.assertEqual(
                            recommendation_from_score(total, dimensions),
                            expected,
                        )
                        self.assertEqual(
                            recommendation_decision_from_score(
                                total,
                                dimensions,
                            ).final_recommendation,
                            expected,
                        )

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
        self.assertIsNotNone(score.recommendation_decision)
        self.assertEqual(
            score.recommendation,
            score.recommendation_decision.final_recommendation,
        )
        self.assertEqual(len(score.dimension_contributions), 6)
        self.assertAlmostEqual(
            sum(
                contribution.normalized_weight
                for contribution in score.dimension_contributions
            ),
            1.0,
        )
        self.assertAlmostEqual(
            sum(
                contribution.weighted_contribution
                for contribution in score.dimension_contributions
            ),
            score.total_score,
        )
        for contribution in score.dimension_contributions:
            self.assertAlmostEqual(
                contribution.score * contribution.normalized_weight,
                contribution.weighted_contribution,
            )
            self.assertAlmostEqual(
                contribution.score,
                score.dimensions[contribution.name].score,
            )
        self.assertIsNotNone(score.configuration_audit)
        self.assertEqual(len(score.configuration_audit.fingerprint), 64)
        for name, dimension in score.dimensions.items():
            components = [
                component
                for component in score.component_audit
                if component.dimension == name
                and component.stage == "dimension"
                and component.used
            ]
            self.assertTrue(components)
            self.assertAlmostEqual(
                sum(component.weighted_contribution for component in components),
                dimension.score,
            )
        revenue = next(
            component
            for component in score.component_audit
            if component.dimension == "growth"
            and component.component == "revenue_growth"
        )
        self.assertEqual(revenue.source, "manual")
        self.assertAlmostEqual(revenue.raw_value, 0.20)
        self.assertTrue(revenue.used)

    def test_score_configuration_fingerprint_is_deterministic_and_profile_specific(self):
        metrics = metric_pack(
            revenue_growth=0.10,
            fama_french_profitability=0.70,
            earnings_quality=0.70,
            piotroski_proxy=0.70,
            current_ratio=1.50,
        )
        valuations = [
            ValuationResult(
                "dcf_fcff",
                110.0,
                0.80,
                margin_of_safety=0.10,
            )
        ]

        traditional_a = compute_score(
            CompanyType.TRADITIONAL,
            valuations,
            metrics,
            metric_value("price", 100.0, "manual"),
        )
        traditional_b = compute_score(
            CompanyType.TRADITIONAL,
            valuations,
            metrics,
            metric_value("price", 100.0, "manual"),
        )
        growth = compute_score(
            CompanyType.GROWTH_TECH,
            valuations,
            metrics,
            metric_value("price", 100.0, "manual"),
        )

        self.assertEqual(
            traditional_a.configuration_audit.fingerprint,
            traditional_b.configuration_audit.fingerprint,
        )
        self.assertNotEqual(
            traditional_a.configuration_audit.fingerprint,
            growth.configuration_audit.fingerprint,
        )
        self.assertEqual(
            traditional_a.configuration_audit.model_version,
            "multifactor_score_v2_semantic_controls",
        )

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
        self.assertIn("runway de caixa", dimension.explanation)

    def test_growth_tech_missing_runway_does_not_transfer_its_weight(self):
        metrics = metric_pack(current_ratio=3.0)

        report = compute_score(
            CompanyType.GROWTH_TECH,
            [],
            metrics,
            metric_value("price", 10.0, "manual"),
        )

        dimension = report.dimensions["liquidity"]
        self.assertAlmostEqual(dimension.score, 0.70)
        components = {
            component.component: component
            for component in report.component_audit
            if component.dimension == "liquidity"
            and component.stage == "dimension"
        }
        self.assertAlmostEqual(components["current_ratio"].effective_weight, 0.40)
        self.assertAlmostEqual(components["cash_runway_years"].effective_weight, 0.60)
        self.assertTrue(components["cash_runway_years"].is_fallback)

    def test_relative_comparables_blend_into_valuation_without_overriding_intrinsic_value(self):
        metrics = metric_pack()
        valuations = [ValuationResult("dcf_fcff", 80.0, 0.80, margin_of_safety=-0.20)]
        comparables = ComparableReport([], overall_score=0.90, confidence=1.0, summary="discount to peers")

        dimension = valuation_dimension(valuations, metrics, CompanyType.TRADITIONAL, comparables)

        self.assertGreater(dimension.score, valuation_dimension(valuations, metrics, CompanyType.TRADITIONAL).score)
        self.assertLess(dimension.score, 0.90)
        self.assertIn("multiplos relativos de pares", dimension.explanation)

    def test_component_audit_records_relative_comparables_when_used(self):
        metrics = metric_pack(current_ratio=1.5)
        valuations = [
            ValuationResult(
                "dcf_fcff",
                80.0,
                0.80,
                source="derived",
                margin_of_safety=-0.20,
            )
        ]
        comparables = ComparableReport(
            [],
            overall_score=0.90,
            confidence=1.0,
            summary="discount to peers",
            basis="approved_peer_medians",
        )

        report = compute_score(
            CompanyType.TRADITIONAL,
            valuations,
            metrics,
            metric_value("price", 100.0, "manual"),
            comparables,
        )

        final_components = [
            component
            for component in report.component_audit
            if component.dimension == "valuation"
            and component.stage == "dimension"
            and component.used
        ]
        self.assertEqual(
            {component.component for component in final_components},
            {"intrinsic_or_bank_valuation", "relative_comparables"},
        )
        self.assertAlmostEqual(
            sum(component.effective_weight for component in final_components),
            1.0,
        )
        self.assertAlmostEqual(
            sum(component.weighted_contribution for component in final_components),
            report.dimensions["valuation"].score,
        )

    def test_component_audit_preserves_missing_metric_weight_with_fallback(self):
        report = compute_score(
            CompanyType.TRADITIONAL,
            [],
            metric_pack(revenue_growth=0.10),
            metric_value("price", 100.0, "manual"),
        )

        growth = {
            component.component: component
            for component in report.component_audit
            if component.dimension == "growth"
        }
        self.assertTrue(growth["revenue_growth"].used)
        self.assertAlmostEqual(growth["revenue_growth"].effective_weight, 0.5)
        self.assertTrue(growth["fcff_growth"].used)
        self.assertAlmostEqual(growth["fcff_growth"].effective_weight, 0.5)
        self.assertAlmostEqual(growth["fcff_growth"].transformed_score, 0.5)
        self.assertTrue(growth["fcff_growth"].reason)

    def test_component_audit_keeps_missing_growth_signals_with_neutral_default(self):
        report = compute_score(
            CompanyType.TRADITIONAL,
            [],
            metric_pack(),
            metric_value("price", 100.0, "manual"),
        )

        growth = {
            component.component: component
            for component in report.component_audit
            if component.dimension == "growth"
        }
        self.assertAlmostEqual(
            sum(item.weighted_contribution for item in growth.values()),
            report.dimensions["growth"].score,
        )
        self.assertTrue(growth["revenue_growth"].used)
        self.assertTrue(growth["fcff_growth"].used)
        self.assertEqual(growth["fcff_growth"].effective_weight, 0.5)
        self.assertEqual(report.dimensions["growth"].confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
