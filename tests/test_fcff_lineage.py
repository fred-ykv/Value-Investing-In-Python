import unittest

from fundamental_analysis.data_sources import MetricValue, metric_value
from fundamental_analysis.financial_statements import FinancialStatements, build_statement_metrics, compute_fcff


def inputs(**overrides):
    values = {
        "ebit": metric_value("ebit", 1_000, "manual"),
        "tax_rate": metric_value("tax_rate", 0.25, "manual", basis="derived"),
        "depreciation_amortization": metric_value("depreciation_amortization", 100, "manual"),
        "capex": metric_value("capex", -200, "manual"),
        "change_in_nwc": metric_value("change_in_nwc", 50, "manual"),
        "interest_expense": metric_value("interest_expense", 0, "manual"),
    }
    values.update(overrides)
    return values


class FCFFLineageTests(unittest.TestCase):
    def test_fcff_uses_unlevered_formula(self):
        result = compute_fcff(inputs())
        self.assertEqual(result.value, 600)
        self.assertEqual(result.formula, "nopat_plus_da_minus_capex_minus_delta_nwc")
        self.assertEqual(result.basis, "derived")

    def test_interest_does_not_change_fcff_when_tax_rate_is_fixed(self):
        base = compute_fcff(inputs(interest_expense=metric_value("interest_expense", 0, "manual")))
        with_interest = compute_fcff(inputs(interest_expense=metric_value("interest_expense", 500, "manual")))
        self.assertEqual(base.value, with_interest.value)

    def test_capex_sign_is_normalized_once(self):
        negative_capex = compute_fcff(inputs(capex=metric_value("capex", -200, "manual")))
        positive_capex = compute_fcff(inputs(capex=metric_value("capex", 200, "manual")))
        self.assertEqual(negative_capex.value, positive_capex.value)

    def test_missing_capex_makes_fcff_unavailable(self):
        result = compute_fcff(inputs(capex=MetricValue("capex", None, "missing", 0.0)))
        self.assertIsNone(result.value)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("requires EBIT", result.note)

    def test_missing_nwc_is_explicit_low_confidence_approximation(self):
        result = compute_fcff(inputs(change_in_nwc=MetricValue("change_in_nwc", None, "missing", 0.0)))
        self.assertEqual(result.value, 650)
        self.assertTrue(result.is_fallback)
        self.assertLess(result.confidence, 0.70)
        self.assertIn("change_in_nwc unavailable", result.note)

    def test_statement_metrics_keep_fcf_proxy_separate_from_fcff(self):
        metrics = build_statement_metrics(
            FinancialStatements(
                "FCFF",
                {"revenue": 2_000, "ebit": 1_000, "net_income": 500, "tax_provision": 250, "interest_expense": 0},
                {"total_assets": 3_000, "total_liabilities": 1_000, "equity": 2_000},
                {"cfo": 900, "capex": -200, "depreciation_amortization": 100, "change_in_nwc": 50},
                {"shares": 100, "price": 10},
            )
        )
        self.assertEqual(metrics.values["free_cash_flow_after_capex"].value, 700)
        self.assertEqual(metrics.values["fcff"].formula, "nopat_plus_da_minus_capex_minus_delta_nwc")
        self.assertNotEqual(metrics.values["free_cash_flow_after_capex"].value, metrics.values["fcff"].value)


if __name__ == "__main__":
    unittest.main()
