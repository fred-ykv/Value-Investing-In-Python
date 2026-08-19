import unittest

from fundamental_analysis.main import analyze_ticker_from_inputs
from fundamental_analysis.visual_reporting import apply_visual_polish_to_html


class VisualReportingTests(unittest.TestCase):
    def test_visual_polish_adds_dashboard_shell_and_legend(self):
        html = apply_visual_polish_to_html("<html><head></head><body><main><header>ABC</header></main></body></html>", "Comprar")

        self.assertIn('body class="visual-polish recommend-buy"', html)
        self.assertIn("visual-polish-css", html)
        self.assertIn("Legenda visual", html)
        self.assertIn("legend-dot positive", html)
        self.assertIn("Favoravel", html)
        self.assertIn("Dado fraco", html)

    def test_analysis_report_uses_visual_polish_without_changing_payload_tables(self):
        result = analyze_ticker_from_inputs(
            "VIS",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000, "depreciation_amortization": 20_000},
            {"shares": 10_000, "price": 60, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        html = result.report["html"]

        self.assertIn("visual-polish", html)
        self.assertIn("Legenda visual", html)
        self.assertIn("Leitura rapida para iniciantes", html)
        self.assertIn("score-pill", html)
        self.assertRegex(html, r"score-(positive|neutral|negative)")
        self.assertRegex(html, r"Forte|Intermediario|Fraco")
        self.assertTrue(result.report["valuation_table"])
        self.assertTrue(result.report["score_table"])
        self.assertTrue(result.report["key_indicator_table"])


if __name__ == "__main__":
    unittest.main()
