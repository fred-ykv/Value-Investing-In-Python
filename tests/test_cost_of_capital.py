import unittest

from fundamental_analysis.config import CompanyType
from fundamental_analysis.cost_of_capital import calculate_cost_of_capital
from fundamental_analysis.data_sources import MetricValue, metric_value


def capital_values(**overrides):
    values = {
        "beta": metric_value("beta", 1.0, "manual"),
        "market_cap": metric_value("market_cap", 800.0, "manual"),
        "price": metric_value("price", 8.0, "manual"),
        "shares": metric_value("shares", 100.0, "manual"),
        "equity": metric_value("equity", 500.0, "manual"),
        "total_debt": metric_value("total_debt", 200.0, "manual"),
        "interest_expense": metric_value("interest_expense", 12.0, "manual"),
        "tax_rate": metric_value("tax_rate", 0.25, "derived"),
    }
    values.update(overrides)
    return values


class CostOfCapitalTests(unittest.TestCase):
    def test_wacc_uses_market_weights_and_after_tax_cost_of_debt(self):
        result = calculate_cost_of_capital(
            CompanyType.TRADITIONAL,
            capital_values(),
            {
                "risk_free_rate": metric_value(
                    "risk_free_rate",
                    0.045,
                    "us_treasury_historical",
                ),
                "equity_risk_premium": metric_value(
                    "equity_risk_premium",
                    0.055,
                    "damodaran_historical_erp",
                ),
                "beta": 1.0,
                "cost_of_debt": 0.06,
            },
        )

        self.assertAlmostEqual(result.cost_of_equity, 0.10)
        self.assertAlmostEqual(result.equity_weight, 0.80)
        self.assertAlmostEqual(result.debt_weight, 0.20)
        self.assertAlmostEqual(result.after_tax_cost_of_debt, 0.045)
        self.assertAlmostEqual(result.wacc, 0.089)
        self.assertEqual(result.discount_rate_label, "WACC")
        self.assertNotEqual(result.component_confidences["beta"], result.component_confidences["risk_free_rate"])
        self.assertFalse(result.is_fallback)
        self.assertFalse(result.component_fallbacks["risk_free_rate"])
        self.assertFalse(result.component_fallbacks["equity_risk_premium"])
        self.assertFalse(result.component_fallbacks["beta"])
        self.assertFalse(result.component_fallbacks["pre_tax_cost_of_debt"])
        self.assertFalse(result.component_fallbacks["capital_weights"])
        self.assertFalse(result.component_fallbacks["discount_rate"])

    def test_explicit_wacc_is_used_but_calculated_wacc_is_kept_for_comparison(self):
        result = calculate_cost_of_capital(
            CompanyType.TRADITIONAL,
            capital_values(),
            {"beta": 1.0, "cost_of_debt": 0.06, "wacc": 0.12},
        )

        self.assertAlmostEqual(result.discount_rate, 0.12)
        self.assertAlmostEqual(result.calculated_wacc, 0.089)
        self.assertEqual(result.method, "explicit_wacc_override")
        self.assertTrue(any("prevaleceu" in note for note in result.notes))
        self.assertFalse(result.component_fallbacks["discount_rate"])
        self.assertTrue(result.component_fallbacks["calculated_wacc"])

    def test_unused_debt_cost_fallback_does_not_taint_zero_debt_wacc(self):
        result = calculate_cost_of_capital(
            CompanyType.TRADITIONAL,
            capital_values(
                total_debt=metric_value("total_debt", 0.0, "manual"),
            ),
            {
                "risk_free_rate": metric_value(
                    "risk_free_rate",
                    0.045,
                    "us_treasury_historical",
                ),
                "equity_risk_premium": metric_value(
                    "equity_risk_premium",
                    0.055,
                    "damodaran_historical_erp",
                ),
                "beta": 1.0,
            },
        )

        self.assertAlmostEqual(result.wacc, result.cost_of_equity)
        self.assertTrue(result.component_fallbacks["pre_tax_cost_of_debt"])
        self.assertFalse(result.component_fallbacks["calculated_wacc"])
        self.assertFalse(result.component_fallbacks["discount_rate"])
        self.assertFalse(result.is_fallback)

    def test_financial_company_uses_ke_instead_of_wacc(self):
        result = calculate_cost_of_capital(
            CompanyType.FINANCIAL,
            capital_values(),
            {"ke": 0.11, "wacc": 0.08},
        )

        self.assertAlmostEqual(result.discount_rate, 0.11)
        self.assertIsNone(result.wacc)
        self.assertEqual(result.discount_rate_label, "Custo do patrimonio (Ke)")
        self.assertTrue(any("WACC nao e aplicado" in note for note in result.notes))
        self.assertFalse(result.component_fallbacks["cost_of_equity"])
        self.assertFalse(result.component_fallbacks["discount_rate"])

    def test_missing_debt_does_not_create_false_wacc(self):
        result = calculate_cost_of_capital(
            CompanyType.TRADITIONAL,
            capital_values(total_debt=MetricValue("total_debt", None, "missing", 0.0)),
            {"beta": 1.0},
        )

        self.assertIsNone(result.wacc)
        self.assertEqual(result.method, "ke_proxy_missing_capital_structure")
        self.assertTrue(result.is_fallback)
        self.assertFalse(result.component_fallbacks["debt_value"])
        self.assertEqual(result.sources["debt_value"], "Indisponivel")
        self.assertTrue(result.component_fallbacks["discount_rate"])
        self.assertTrue(any("WACC nao pode ser calculado" in note for note in result.notes))


if __name__ == "__main__":
    unittest.main()

