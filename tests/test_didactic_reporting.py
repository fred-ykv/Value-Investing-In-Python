import unittest

from fundamental_analysis.main import analyze_ticker_from_inputs


class DidacticReportingTests(unittest.TestCase):
    def test_report_adds_beginner_reading_and_human_labels(self):
        result = analyze_ticker_from_inputs(
            "EDU",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {
                "total_assets": 1_500_000,
                "total_liabilities": 600_000,
                "equity": 900_000,
                "cash": 100_000,
                "total_debt": 250_000,
                "current_assets": 500_000,
                "current_liabilities": 250_000,
            },
            {"cfo": 150_000, "capex": -40_000, "depreciation_amortization": 20_000},
            {"shares": 10_000, "price": 60, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        markdown = result.report["markdown"]
        html = result.report["html"]

        self.assertIn("Leitura rapida para iniciantes", markdown)
        self.assertIn("Leitura rapida para iniciantes", html)
        self.assertIn("Ativos Totais", markdown)
        self.assertIn("Lucro Liquido", markdown)
        self.assertIn("Confianca dos Dados", markdown)
        self.assertIn("US$ 60.00", markdown)
        self.assertIn("US$ 60.00", html)
        self.assertNotIn("total_assets", markdown)
        self.assertNotIn("net_income", markdown)
        self.assertTrue(result.report["didactic_summary"])

    def test_didactic_summary_keeps_raw_tables_auditable(self):
        result = analyze_ticker_from_inputs(
            "AUD",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000},
            {"cfo": 150_000, "capex": -40_000},
            {"shares": 10_000, "price": 60},
            {"sector": "Industrials"},
        )

        metric_names = {row["metric"] for row in result.report["metric_lineage_table"]}

        self.assertIn("total_assets", metric_names)
        self.assertIn("net_income", metric_names)
        self.assertIn("didactic_summary", result.report)


if __name__ == "__main__":
    unittest.main()
