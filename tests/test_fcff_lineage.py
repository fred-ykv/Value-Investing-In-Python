import unittest
from datetime import date

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

    def test_cash_flow_statement_effect_uses_the_opposite_sign_of_economic_delta(self):
        economic = compute_fcff(inputs(change_in_nwc=metric_value("change_in_nwc", 50, "manual")))
        cash_effect = compute_fcff(
            inputs(
                change_in_nwc=MetricValue("change_in_nwc", None, "missing", 0.0),
                change_in_nwc_cash_effect=metric_value("change_in_nwc_cash_effect", -50, "yfinance"),
            )
        )

        self.assertEqual(economic.value, 600)
        self.assertEqual(cash_effect.value, economic.value)
        self.assertEqual(cash_effect.formula, "nopat_plus_da_minus_capex_plus_nwc_cash_effect")
        self.assertIn("cash-flow statement", cash_effect.note)

    def test_nue_2025_cash_effect_is_not_added_back_with_inverted_sign(self):
        metrics = build_statement_metrics(
            FinancialStatements(
                "NUE",
                {"ebit": 2_738_000_000, "tax_provision": 530_000_000, "interest_expense": 170_000_000},
                {"equity": 20_938_000_000, "total_debt": 7_121_000_000, "cash": 2_260_000_000},
                {
                    "cfo": 3_234_000_000,
                    "capex": -3_422_000_000,
                    "depreciation_amortization": 1_480_000_000,
                    "change_in_nwc_cash_effect": -636_000_000,
                },
                {"shares": 226_875_676, "price": 240.48},
                source="yfinance",
            )
        )

        expected = 2_738_000_000 * (1.0 - (530_000_000 / (2_738_000_000 - 170_000_000))) + 1_480_000_000 - 3_422_000_000 - 636_000_000
        self.assertAlmostEqual(metrics.values["fcff"].value, expected)
        self.assertLess(metrics.values["fcff"].value, 0)
        self.assertEqual(metrics.values["free_cash_flow_after_capex"].value, -188_000_000)

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

    def test_fcff_propagates_fallback_from_required_sec_inputs(self):
        result = compute_fcff(
            inputs(
                capex=metric_value(
                    "capex",
                    -200,
                    "sec_edgar",
                    is_fallback=True,
                )
            )
        )

        self.assertTrue(result.is_fallback)
        self.assertIn("fallback inputs: capex", result.note)

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

    def test_derived_cash_flows_preserve_currency_period_and_source_documents(self):
        period_end = date(2025, 12, 31)

        def sourced(name, value, document):
            return MetricValue(
                name,
                value,
                "yfinance",
                0.85,
                source_url="https://finance.yahoo.com/quote/NUE",
                source_document=document,
                period_end=period_end,
                currency="USD",
                scale="raw",
            )

        values = inputs(
            ebit=sourced("ebit", 2_659_000_000, "Yahoo Finance income statement"),
            depreciation_amortization=sourced("depreciation_amortization", 1_000_000_000, "Yahoo Finance cash flow statement"),
            capex=sourced("capex", -3_422_000_000, "Yahoo Finance cash flow statement"),
            change_in_nwc=MetricValue("change_in_nwc", None, "missing", 0.0),
            change_in_nwc_cash_effect=sourced("change_in_nwc_cash_effect", -1_000_000_000, "Yahoo Finance cash flow statement"),
        )
        values["cfo"] = sourced("cfo", 3_234_000_000, "Yahoo Finance cash flow statement")

        fcff = compute_fcff(values)
        statement_metrics = build_statement_metrics(
            FinancialStatements(
                "NUE",
                {"ebit": values["ebit"]},
                {},
                {"cfo": values["cfo"], "capex": values["capex"]},
                {},
                source="yfinance",
            )
        )
        fcf = statement_metrics.values["free_cash_flow_after_capex"]

        for metric in (fcff, fcf):
            self.assertEqual(metric.currency, "USD")
            self.assertEqual(metric.period_end, period_end)
            self.assertEqual(metric.source_url, "https://finance.yahoo.com/quote/NUE")
            self.assertIn("Yahoo Finance", metric.source_document)


if __name__ == "__main__":
    unittest.main()
