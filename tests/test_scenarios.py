import unittest

from fundamental_analysis.data_sources import metric_value
from fundamental_analysis.main import analyze_ticker_from_inputs
from fundamental_analysis.config import DCF
from fundamental_analysis.scenarios import aggregate_fair_value, aggregate_margin_of_safety, build_reverse_dcf
from fundamental_analysis.valuation import DCFInput, ValuationResult, dcf_fcff_no_sensitivity


class ScenarioTests(unittest.TestCase):
    def test_analysis_builds_ordered_scenario_outputs(self):
        result = analyze_ticker_from_inputs(
            "SCN",
            {"revenue": 1_000_000, "ebit": 180_000, "net_income": 120_000},
            {"total_assets": 1_400_000, "total_liabilities": 500_000, "equity": 900_000, "cash": 120_000, "total_debt": 200_000, "current_assets": 450_000, "current_liabilities": 220_000},
            {"cfo": 170_000, "capex": -45_000},
            {"shares": 10_000, "price": 55, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        labels = [scenario.label for scenario in result.scenarios]
        self.assertEqual(labels, ["Stress", "Pessimista", "Base", "Otimista"])
        self.assertEqual(len(result.report["scenario_table"]), 4)
        self.assertIn("reverse_dcf", result.report)
        self.assertIn("Cenarios hipoteticos", result.report["markdown"])
        self.assertIn("Reverse DCF", result.report["markdown"])

    def test_stress_scenario_is_more_conservative_than_optimistic(self):
        result = analyze_ticker_from_inputs(
            "SCN",
            {"revenue": 1_000_000, "ebit": 180_000, "net_income": 120_000},
            {"total_assets": 1_400_000, "total_liabilities": 500_000, "equity": 900_000, "cash": 120_000, "total_debt": 200_000, "current_assets": 450_000, "current_liabilities": 220_000},
            {"cfo": 170_000, "capex": -45_000},
            {"shares": 10_000, "price": 55, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        by_key = {scenario.key: scenario for scenario in result.scenarios}

        self.assertIsNotNone(by_key["stress"].fair_value_per_share)
        self.assertIsNotNone(by_key["bull"].fair_value_per_share)
        self.assertLess(by_key["stress"].fair_value_per_share, by_key["bull"].fair_value_per_share)
        self.assertLess(by_key["stress"].margin_of_safety, by_key["bull"].margin_of_safety)

    def test_base_scenario_uses_the_same_growth_as_primary_dcf(self):
        result = analyze_ticker_from_inputs(
            "BASE",
            {"revenue": 1_000_000, "ebit": 180_000, "net_income": 120_000},
            {"total_assets": 1_400_000, "total_liabilities": 500_000, "equity": 900_000, "cash": 120_000, "total_debt": 200_000, "current_assets": 450_000, "current_liabilities": 220_000},
            {"cfo": 170_000, "capex": -45_000, "depreciation_amortization": 20_000},
            {"shares": 10_000, "price": 55, "wacc": 0.10, "revenue_growth": 0.25, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        primary = next(item for item in result.valuations if item.method == "dcf_fcff")
        base = next(item for item in result.scenarios if item.key == "base")
        base_dcf = next(item for item in base.valuations if item.method == "dcf_fcff")

        self.assertAlmostEqual(primary.diagnostics["growth_years"], DCF.default_growth_years)
        self.assertAlmostEqual(base.assumptions["growth_years"], primary.diagnostics["growth_years"])
        self.assertAlmostEqual(base_dcf.fair_value_per_share, primary.fair_value_per_share)

    def test_scenario_aggregation_is_weighted_by_confidence(self):
        valuations = [
            ValuationResult("weak", 50.0, 0.20, margin_of_safety=-0.50),
            ValuationResult("strong", 100.0, 0.80, margin_of_safety=0.20),
        ]

        self.assertAlmostEqual(aggregate_fair_value(valuations), 90.0)
        self.assertAlmostEqual(aggregate_margin_of_safety(valuations), 0.06)

    def test_reverse_dcf_solves_growth_implied_by_current_price(self):
        values = {
            "fcff": metric_value("fcff", 100_000, "manual"),
            "shares": metric_value("shares", 10_000, "manual"),
            "total_debt": metric_value("total_debt", 0, "manual"),
            "cash": metric_value("cash", 0, "manual"),
            "price": metric_value("price", 128.0, "manual"),
        }

        result = build_reverse_dcf(values, {"wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02}, 0.10)

        self.assertIsNotNone(result.implied_growth_years)
        self.assertEqual(result.status, "plausivel")
        self.assertGreater(result.confidence, 0.0)

    def test_reverse_dcf_explains_negative_fcff(self):
        values = {
            "fcff": metric_value("fcff", -100_000, "manual"),
            "shares": metric_value("shares", 10_000, "manual"),
            "total_debt": metric_value("total_debt", 0, "manual"),
            "cash": metric_value("cash", 0, "manual"),
            "price": metric_value("price", 20.0, "manual"),
        }

        result = build_reverse_dcf(values, {"wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02}, 0.10)

        self.assertIsNone(result.implied_growth_years)
        self.assertEqual(result.status, "indisponivel")
        self.assertIn("FCFF atual e negativo", result.interpretation)

    def test_reverse_dcf_can_infer_explicit_growth_above_wacc(self):
        values = {
            "fcff": metric_value("fcff", 100_000, "manual"),
            "shares": metric_value("shares", 10_000, "manual"),
            "total_debt": metric_value("total_debt", 0, "manual"),
            "cash": metric_value("cash", 0, "manual"),
            "price": metric_value("price", 1.0, "manual"),
        }
        target_growth = 0.20
        target = dcf_fcff_no_sensitivity(
            DCFInput(
                values["fcff"],
                values["shares"],
                metric_value("wacc", 0.10, "manual"),
                metric_value("growth_years", target_growth, "manual"),
                metric_value("terminal_growth", 0.02, "manual"),
                values["total_debt"],
                values["cash"],
                values["price"],
            )
        ).fair_value_per_share
        values["price"] = metric_value("price", target, "manual")

        result = build_reverse_dcf(values, {"wacc": 0.10, "growth_years": 0.05, "terminal_growth": 0.02}, 0.10)

        self.assertAlmostEqual(result.implied_growth_years, target_growth, places=3)
        self.assertGreater(result.implied_growth_years, result.discount_rate)
        self.assertEqual(result.assumptions["max_growth"], DCF.max_growth_years)


if __name__ == "__main__":
    unittest.main()

