import unittest

from fundamental_analysis.main import analyze_ticker_from_inputs


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
        self.assertIn("Cenarios hipoteticos", result.report["markdown"])

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


if __name__ == "__main__":
    unittest.main()
