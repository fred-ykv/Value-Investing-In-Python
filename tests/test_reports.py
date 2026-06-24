import unittest

from fundamental_analysis.main import analyze_ticker_from_inputs


class ReportTests(unittest.TestCase):
    def test_markdown_report_contains_required_sections(self):
        result = analyze_ticker_from_inputs(
            "RPT",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000},
            {"shares": 10_000, "price": 60, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )
        markdown = result.report["markdown"]
        self.assertIn("Resumo executivo", markdown)
        self.assertIn("Valuation por metodo", markdown)
        self.assertIn("Score por dimensao", markdown)
        self.assertIn("Fontes e confianca das metricas", markdown)
        self.assertIn("| revenue |", markdown)
        self.assertIn("| manual |", markdown)
        self.assertTrue(result.report["metric_lineage_table"])
        self.assertIn("source", result.report["metric_lineage_table"][0])
        self.assertIn("confidence", result.report["metric_lineage_table"][0])
        self.assertIn("Recomendacao final", markdown)


if __name__ == "__main__":
    unittest.main()
