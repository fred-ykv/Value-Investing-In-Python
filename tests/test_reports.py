import unittest

from fundamental_analysis.main import analyze_ticker_from_inputs
from fundamental_analysis.reports import render_markdown_report
from fundamental_analysis.scoring import DimensionScore, ScoreReport
from fundamental_analysis.valuation import ValuationResult


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
        self.assertIn("Tese da recomendacao", markdown)
        self.assertIn("Valuation por metodo", markdown)
        self.assertIn("Score por dimensao", markdown)
        self.assertIn("Fontes e confianca das metricas", markdown)
        self.assertIn("Notas explicativas", markdown)
        self.assertIn("Margem de seguranca negativa", markdown)
        self.assertIn("| revenue |", markdown)
        self.assertIn("| manual |", markdown)
        self.assertTrue(result.report["metric_lineage_table"])
        self.assertIn("source", result.report["metric_lineage_table"][0])
        self.assertIn("confidence", result.report["metric_lineage_table"][0])
        self.assertIn("Recomendacao final", markdown)

    def test_report_explains_buy_gate_when_valuation_blocks_buy(self):
        score = ScoreReport(
            total_score=0.74,
            recommendation="Observar",
            dimensions={
                "valuation": DimensionScore("valuation", 0.20, 0.70, "valuation is weak"),
                "growth": DimensionScore("growth", 0.90, 0.70, "growth is strong"),
                "quality": DimensionScore("quality", 0.90, 0.70, "quality is strong"),
                "debt": DimensionScore("debt", 0.90, 0.70, "debt is low"),
                "liquidity": DimensionScore("liquidity", 0.90, 0.70, "liquidity is good"),
                "data_confidence": DimensionScore("data_confidence", 0.80, 0.80, "data is reliable"),
            },
        )
        valuations = [ValuationResult("dcf_fcff", 80.0, 0.80, margin_of_safety=-0.20)]

        markdown = render_markdown_report("GATE", score, valuations)

        self.assertIn("nao subiu para Comprar", markdown)
        self.assertIn("abaixo do minimo exigido", markdown)


if __name__ == "__main__":
    unittest.main()
