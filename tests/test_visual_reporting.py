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

    def test_visual_polish_adds_margin_signals_to_scenario_table(self):
        result = analyze_ticker_from_inputs(
            "SCN",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000, "depreciation_amortization": 20_000},
            {"shares": 10_000, "price": 60, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        html = result.report["html"]
        scenario_section = html.split("<h2>Cenarios</h2>", 1)[1].split("</section>", 1)[0]

        self.assertIn("margin-pill", scenario_section)
        self.assertRegex(scenario_section, r"Margem positiva|Margem estreita|Margem negativa")

    def test_visual_polish_summarizes_scenarios_as_decision_block(self):
        result = analyze_ticker_from_inputs(
            "BLK",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000, "depreciation_amortization": 20_000},
            {"shares": 10_000, "price": 60, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        html = result.report["html"]
        scenario_section = html.split("<h2>Cenarios</h2>", 1)[1].split("</section>", 1)[0]

        self.assertIn("scenario-dashboard", scenario_section)
        self.assertIn("scenario-card-grid", scenario_section)
        self.assertIn("Cenario conservador", scenario_section)
        self.assertIn("Cenario base", scenario_section)
        self.assertIn("Cenario otimista", scenario_section)
        self.assertRegex(scenario_section, r"Sustenta a tese|Fragiliza a tese|Quebra ou pressiona")
        self.assertIn("use esta secao para ver se a tese sobrevive fora do caso otimista", scenario_section)

    def test_visual_polish_summarizes_comparables_as_decision_block(self):
        result = analyze_ticker_from_inputs(
            "CMP",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000, "depreciation_amortization": 20_000},
            {
                "shares": 10_000,
                "price": 60,
                "wacc": 0.10,
                "growth_years": 0.04,
                "terminal_growth": 0.02,
                "peer_medians": {"price_to_earnings": 8.0, "ev_to_ebitda": 12.0, "ev_to_sales": 4.0},
                "peer_median_counts": {"price_to_earnings": 4, "ev_to_ebitda": 4, "ev_to_sales": 4},
            },
            {"sector": "Industrials"},
        )

        html = result.report["html"]
        comparable_section = html.split("<h2>Comparaveis</h2>", 1)[1].split("</section>", 1)[0]

        self.assertIn("comparable-dashboard", comparable_section)
        self.assertIn("Multiplo que mais ajuda", comparable_section)
        self.assertIn("Multiplo que mais pressiona", comparable_section)
        self.assertIn("Forca da amostra", comparable_section)
        self.assertRegex(comparable_section, r"desconto relevante|proxima da faixa dos pares|premio contra os pares")


if __name__ == "__main__":
    unittest.main()
