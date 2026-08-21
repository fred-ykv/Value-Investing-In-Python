import unittest

from fundamental_analysis.data_sources import MetricValue, metric_value
from fundamental_analysis.valuation import DCFInput, dcf_fcff, ddm_bank, eva_value, growth_tech_value


class DCFValuationTests(unittest.TestCase):
    def test_dcf_returns_value_and_sensitivity(self):
        result = dcf_fcff(DCFInput(metric_value("fcff", 1_000_000_000, "manual"), metric_value("shares", 100_000_000, "manual"), metric_value("wacc", 0.10, "manual"), metric_value("growth_years", 0.04, "manual"), metric_value("terminal_growth", 0.02, "manual"), metric_value("debt", 2_000_000_000, "manual"), metric_value("cash", 500_000_000, "manual"), metric_value("price", 80, "manual")))
        self.assertIsNotNone(result.fair_value_per_share)
        self.assertIn("sensitivity", result.diagnostics)

    def test_negative_fcff_reduces_confidence(self):
        result = dcf_fcff(DCFInput(metric_value("fcff", -100_000_000, "manual"), metric_value("shares", 10_000_000, "manual"), metric_value("wacc", 0.11, "manual"), metric_value("growth_years", 0.05, "manual"), metric_value("terminal_growth", 0.02, "manual"), metric_value("debt", 0, "manual"), metric_value("cash", 0, "manual"), metric_value("price", 10, "manual")))
        self.assertTrue(result.diagnostics["negative_fcff"])
        self.assertLess(result.confidence, 0.70)

    def test_dcf_does_not_assume_missing_cash_is_zero(self):
        result = dcf_fcff(
            DCFInput(
                metric_value("fcff", 1_000, "manual"),
                metric_value("shares", 100, "manual"),
                metric_value("wacc", 0.10, "manual"),
                metric_value("growth_years", 0.0, "manual"),
                metric_value("terminal_growth", 0.0, "manual"),
                metric_value("debt", 200, "manual"),
                MetricValue("cash", None, "missing", 0.0),
                metric_value("price", 10, "manual"),
            )
        )

        self.assertIsNone(result.fair_value_per_share)
        self.assertIsNotNone(result.enterprise_value)
        self.assertIn("enterprise-to-equity", result.diagnostics["error"])

    def test_eva_bridges_enterprise_value_to_equity_with_net_debt(self):
        result = eva_value(
            metric_value("invested_capital", 1_000, "manual"),
            metric_value("roic", 0.15, "manual"),
            metric_value("wacc", 0.10, "manual"),
            metric_value("terminal_growth", 0.02, "manual"),
            metric_value("shares", 100, "manual"),
            metric_value("price", 10, "manual"),
            metric_value("net_debt", 200, "manual"),
        )

        self.assertAlmostEqual(result.enterprise_value, 1_637.5)
        self.assertAlmostEqual(result.equity_value, 1_437.5)
        self.assertAlmostEqual(result.fair_value_per_share, 14.375)
        self.assertEqual(result.diagnostics["net_debt_adjustment"], 200)

    def test_eva_does_not_assume_missing_net_debt_is_zero(self):
        result = eva_value(
            metric_value("invested_capital", 1_000, "manual"),
            metric_value("roic", 0.15, "manual"),
            metric_value("wacc", 0.10, "manual"),
            metric_value("terminal_growth", 0.02, "manual"),
            metric_value("shares", 100, "manual"),
            metric_value("price", 10, "manual"),
        )

        self.assertIsNone(result.fair_value_per_share)
        self.assertIn("net debt", result.diagnostics["error"])

    def test_zero_growth_is_not_replaced_by_default(self):
        result = dcf_fcff(DCFInput(metric_value("fcff", 1_000, "manual"), metric_value("shares", 100, "manual"), metric_value("wacc", 0.10, "manual"), metric_value("growth_years", 0.0, "manual"), metric_value("terminal_growth", 0.0, "manual"), metric_value("debt", 0, "manual"), metric_value("cash", 0, "manual"), metric_value("price", 100, "manual")))
        self.assertAlmostEqual(result.fair_value_per_share, 100.0, places=6)
        self.assertAlmostEqual(result.diagnostics["sensitivity"]["10.0%"]["0.0%"], 100.0, places=6)

    def test_zero_growth_bank_ddm_is_not_replaced_by_default(self):
        result = ddm_bank(metric_value("dividend_per_share", 1.0, "manual"), metric_value("ke", 0.10, "manual"), metric_value("terminal_growth", 0.0, "manual"), metric_value("price", 10.0, "manual"))
        self.assertAlmostEqual(result.fair_value_per_share, 10.0, places=6)

    def test_zero_growth_tech_revenue_growth_is_not_replaced_by_default(self):
        result = growth_tech_value(metric_value("revenue", 1_000, "manual"), metric_value("revenue_growth", 0.0, "manual"), metric_value("target_fcf_margin", 0.10, "manual"), metric_value("net_cash", 0, "manual"), metric_value("shares", 100, "manual"), metric_value("price", 10, "manual"), metric_value("discount_rate", 0.10, "manual"))
        self.assertEqual(result.diagnostics["growth"], 0.0)

    def test_growth_tech_does_not_assume_missing_net_cash_is_zero(self):
        result = growth_tech_value(
            metric_value("revenue", 1_000, "manual"),
            metric_value("revenue_growth", 0.10, "manual"),
            metric_value("target_fcf_margin", 0.10, "manual"),
            MetricValue("net_cash", None, "missing", 0.0),
            metric_value("shares", 100, "manual"),
            metric_value("price", 10, "manual"),
            metric_value("discount_rate", 0.10, "manual"),
        )

        self.assertIsNone(result.fair_value_per_share)
        self.assertIn("net cash", result.diagnostics["error"])


if __name__ == "__main__":
    unittest.main()

