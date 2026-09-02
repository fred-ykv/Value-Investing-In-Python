import unittest

from fundamental_analysis.data_sources import MetricValue, metric_value
from fundamental_analysis.valuation import (
    DCFInput,
    dcf_fcff,
    ddm_bank,
    eva_value,
    graham_value,
    growth_tech_value,
    residual_income_bank,
)


class DCFValuationTests(unittest.TestCase):
    def test_dcf_returns_value_and_sensitivity(self):
        result = dcf_fcff(DCFInput(metric_value("fcff", 1_000_000_000, "manual"), metric_value("shares", 100_000_000, "manual"), metric_value("wacc", 0.10, "manual"), metric_value("growth_years", 0.04, "manual"), metric_value("terminal_growth", 0.02, "manual"), metric_value("debt", 2_000_000_000, "manual"), metric_value("cash", 500_000_000, "manual"), metric_value("price", 80, "manual")))
        self.assertIsNotNone(result.fair_value_per_share)
        self.assertIn("sensitivity", result.diagnostics)

    def test_dcf_audits_input_and_effective_assumptions(self):
        result = dcf_fcff(
            DCFInput(
                metric_value("fcff", 1_000, "sec_edgar", formula="nopat_plus_da_minus_capex_minus_delta_wc"),
                metric_value("shares", 100, "sec_edgar"),
                metric_value("wacc", 0.10, "historical_wacc"),
                metric_value("growth_years", 0.04, "fallback", is_fallback=True),
                metric_value("terminal_growth", 0.12, "manual"),
                metric_value("debt", 200, "sec_edgar"),
                metric_value("cash", 50, "sec_edgar"),
                metric_value("price", 10, "historical_market_price"),
            )
        )

        assumptions = {item.name: item for item in result.assumptions}
        self.assertEqual(assumptions["fcff"].source, "sec_edgar")
        self.assertTrue(assumptions["explicit_growth_rate"].is_fallback)
        self.assertAlmostEqual(
            assumptions["terminal_growth_rate"].input_value,
            0.12,
        )
        self.assertLess(
            assumptions["terminal_growth_rate"].effective_value,
            assumptions["discount_rate"].effective_value,
        )
        self.assertTrue(assumptions["terminal_growth_rate"].is_fallback)
        self.assertEqual(
            assumptions["projection_horizon_years"].source,
            "config.py",
        )

    def test_all_valuation_families_expose_reproducible_assumptions(self):
        methods = (
            graham_value(
                metric_value("eps", 2.0, "sec_edgar"),
                metric_value("bvps", 10.0, "sec_edgar"),
                metric_value("price", 12.0, "historical_market_price"),
            ),
            eva_value(
                metric_value("invested_capital", 1_000, "sec_edgar"),
                metric_value("roic", 0.15, "derived"),
                metric_value("wacc", 0.10, "historical_wacc"),
                metric_value("terminal_growth", 0.02, "fallback", is_fallback=True),
                metric_value("shares", 100, "sec_edgar"),
                metric_value("price", 10, "historical_market_price"),
                metric_value("net_debt", 200, "derived"),
            ),
            residual_income_bank(
                metric_value("bvps", 25.0, "sec_edgar"),
                metric_value("roe", 0.14, "derived"),
                metric_value("ke", 0.10, "historical_capm"),
                metric_value("terminal_growth", 0.02, "fallback", is_fallback=True),
                metric_value("price", 30.0, "historical_market_price"),
            ),
            ddm_bank(
                metric_value("dividend_per_share", 1.5, "sec_edgar"),
                metric_value("ke", 0.10, "historical_capm"),
                metric_value("terminal_growth", 0.02, "fallback", is_fallback=True),
                metric_value("price", 30.0, "historical_market_price"),
            ),
            growth_tech_value(
                metric_value("revenue", 1_000, "sec_edgar"),
                metric_value("revenue_growth", 0.20, "sec_edgar_derived"),
                metric_value("target_fcf_margin", None, "missing"),
                metric_value("net_cash", 100, "derived"),
                metric_value("shares", 100, "sec_edgar"),
                metric_value("price", 15, "historical_market_price"),
                metric_value("discount_rate", 0.11, "historical_wacc"),
            ),
        )

        for method in methods:
            with self.subTest(method=method.method):
                self.assertTrue(method.assumptions)
                self.assertTrue(all(item.name for item in method.assumptions))
                self.assertTrue(all(item.source for item in method.assumptions))
                self.assertTrue(
                    all(0.0 <= item.confidence <= 1.0 for item in method.assumptions)
                )
        growth_assumptions = {item.name: item for item in methods[-1].assumptions}
        self.assertTrue(growth_assumptions["target_fcf_margin"].is_fallback)
        self.assertIsNone(growth_assumptions["target_fcf_margin"].input_value)
        self.assertIsNotNone(
            growth_assumptions["target_fcf_margin"].effective_value
        )

    def test_negative_fcff_without_positive_normalization_blocks_dcf(self):
        result = dcf_fcff(DCFInput(metric_value("fcff", -100_000_000, "manual"), metric_value("shares", 10_000_000, "manual"), metric_value("wacc", 0.11, "manual"), metric_value("growth_years", 0.05, "manual"), metric_value("terminal_growth", 0.02, "manual"), metric_value("debt", 0, "manual"), metric_value("cash", 0, "manual"), metric_value("price", 10, "manual")))
        self.assertTrue(result.diagnostics["negative_fcff"])
        self.assertIsNone(result.fair_value_per_share)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(
            result.diagnostics["model_applicability"],
            "not_applicable_negative_fcff",
        )

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

    def test_cyclical_dcf_transitions_gradually_to_normalized_fcff(self):
        base = dict(
            shares=metric_value("shares", 1, "manual"),
            wacc=metric_value("wacc", 0.10, "manual"),
            growth_years=metric_value("growth_years", 0.0, "manual"),
            terminal_growth=metric_value("terminal_growth", 0.0, "manual"),
            debt=metric_value("debt", 0, "manual"),
            cash=metric_value("cash", 0, "manual"),
            current_price=metric_value("price", 100, "manual"),
        )
        current_only = dcf_fcff(DCFInput(fcff=metric_value("fcff", 100, "manual"), **base))
        normalized_only = dcf_fcff(DCFInput(fcff=metric_value("fcff", 50, "manual"), **base))
        transitioned = dcf_fcff(
            DCFInput(
                fcff=metric_value("fcff", 100, "manual"),
                normalized_fcff=metric_value(
                    "normalized_fcff",
                    50,
                    "cyclical_normalization",
                    formula="normalized_nopat_minus_normalized_reinvestment",
                ),
                normalization_years=3,
                **base,
            )
        )

        self.assertGreater(transitioned.fair_value_per_share, normalized_only.fair_value_per_share)
        self.assertLess(transitioned.fair_value_per_share, current_only.fair_value_per_share)
        self.assertTrue(transitioned.diagnostics["cyclical_normalization"])
        self.assertEqual(transitioned.diagnostics["normalization_years"], 3)

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
