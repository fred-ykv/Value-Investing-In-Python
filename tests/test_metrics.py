import unittest

from fundamental_analysis.financial_statements import FinancialStatements, build_statement_metrics
from fundamental_analysis.metrics import build_metrics


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


if __name__ == "__main__":
    unittest.main()

