import unittest

from fundamental_analysis.data_sources import metric_value
from fundamental_analysis.valuation import DCFInput, dcf_fcff


class DCFValuationTests(unittest.TestCase):
    def test_dcf_returns_value_and_sensitivity(self):
        result = dcf_fcff(DCFInput(metric_value("fcff", 1_000_000_000, "manual"), metric_value("shares", 100_000_000, "manual"), metric_value("wacc", 0.10, "manual"), metric_value("growth_years", 0.04, "manual"), metric_value("terminal_growth", 0.02, "manual"), metric_value("debt", 2_000_000_000, "manual"), metric_value("cash", 500_000_000, "manual"), metric_value("price", 80, "manual")))
        self.assertIsNotNone(result.fair_value_per_share)
        self.assertIn("sensitivity", result.diagnostics)

    def test_negative_fcff_reduces_confidence(self):
        result = dcf_fcff(DCFInput(metric_value("fcff", -100_000_000, "manual"), metric_value("shares", 10_000_000, "manual"), metric_value("wacc", 0.11, "manual"), metric_value("growth_years", 0.05, "manual"), metric_value("terminal_growth", 0.02, "manual"), metric_value("debt", 0, "manual"), metric_value("cash", 0, "manual"), metric_value("price", 10, "manual")))
        self.assertTrue(result.diagnostics["negative_fcff"])
        self.assertLess(result.confidence, 0.70)


if __name__ == "__main__":
    unittest.main()
