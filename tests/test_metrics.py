import unittest

from fundamental_analysis.financial_statements import FinancialStatements, build_statement_metrics
from fundamental_analysis.metrics import build_metrics
from fundamental_analysis.data_sources import MetricValue


class MetricDefinitionTests(unittest.TestCase):
    def test_roic_uses_nopat_and_invested_capital_net_of_cash(self):
        statements = build_statement_metrics(
            FinancialStatements(
                "ROIC",
                {"ebit": 100, "tax_provision": 25, "interest_expense": 0, "net_income": 60, "revenue": 500},
                {
                    "total_assets": 1_000,
                    "total_liabilities": 500,
                    "equity": 500,
                    "total_debt": 200,
                    "cash": 100,
                    "current_assets": 300,
                    "current_liabilities": 150,
                },
                {"cfo": 90, "capex": -20, "depreciation_amortization": 10, "change_in_nwc": 5},
                {"shares": 100, "price": 10},
            )
        )
        metrics = build_metrics(statements.values)

        self.assertEqual(statements.values["nopat"].value, 75)
        self.assertEqual(statements.values["net_debt"].value, 100)
        self.assertEqual(statements.values["invested_capital"].value, 600)
        self.assertAlmostEqual(metrics.get("roic_proxy"), 0.125)

    def test_negative_denominators_do_not_create_false_positive_ratios(self):
        statements = build_statement_metrics(
            FinancialStatements(
                "LOSS",
                {"ebit": -100, "net_income": -120, "revenue": 500},
                {
                    "total_assets": 1_000,
                    "total_liabilities": 1_200,
                    "equity": -200,
                    "total_debt": 300,
                    "cash": 100,
                    "current_assets": 200,
                    "current_liabilities": 250,
                },
                {"cfo": -80, "capex": -20, "depreciation_amortization": 10},
                {"shares": 100, "price": 10},
            )
        )

        metrics = build_metrics(statements.values)

        self.assertIsNone(metrics.get("roe"))
        self.assertIsNone(metrics.get("debt_to_equity"))
        self.assertIsNone(metrics.get("price_to_book"))
        self.assertIsNone(metrics.get("cfo_to_net_income"))
        self.assertIsNone(metrics.get("net_debt_to_ebit"))

    def test_missing_debt_does_not_create_artificial_net_cash_ratio(self):
        statements = build_statement_metrics(
            FinancialStatements(
                "MISSING_DEBT",
                {"ebit": 100, "net_income": 60, "revenue": 500},
                {
                    "total_assets": 1_000,
                    "total_liabilities": 500,
                    "equity": 500,
                    "cash": 200,
                    "current_assets": 300,
                    "current_liabilities": 150,
                },
                {"cfo": 90, "capex": -20, "depreciation_amortization": 10},
                {"shares": 100, "price": 10},
            )
        )
        self.assertIsInstance(statements.values["total_debt"], MetricValue)

        metrics = build_metrics(statements.values)

        self.assertIsNone(metrics.get("net_debt_to_ebit"))


if __name__ == "__main__":
    unittest.main()

