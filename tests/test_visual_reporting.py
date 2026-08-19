import unittest

from fundamental_analysis.html_reports import render_html_report
from fundamental_analysis.main import analyze_ticker_from_inputs
from fundamental_analysis.scoring import DimensionScore, ScoreReport
from fundamental_analysis.valuation import ValuationResult
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

    def test_visual_polish_adds_margin_signals_to_valuation_table(self):
        score = ScoreReport(
            0.65,
            "Observar",
            {"valuation": DimensionScore("valuation", 0.50, 0.30, "Valuation")},
        )
        valuations = [
            ValuationResult("dcf_fcff", 130.0, 0.80, margin_of_safety=0.30),
            ValuationResult("graham", 104.0, 0.70, margin_of_safety=0.04),
            ValuationResult("eva", 80.0, 0.60, margin_of_safety=-0.20),
        ]

        html = apply_visual_polish_to_html(render_html_report("VAL", score, valuations), "Observar")

        self.assertIn("Margem positiva", html)
        self.assertIn("Margem estreita", html)
        self.assertIn("Margem negativa", html)
        self.assertIn('margin-pill positive', html)
        self.assertIn('margin-pill neutral', html)
        self.assertIn('margin-pill negative', html)


if __name__ == "__main__":
    unittest.main()
