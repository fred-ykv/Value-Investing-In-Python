import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fundamental_analysis.data_sources import MetricValue
from fundamental_analysis.executive_reporting import apply_executive_layer_to_html, apply_executive_layer_to_markdown
from fundamental_analysis.main import analyze_ticker_from_inputs
from fundamental_analysis.html_reports import render_html_report
from fundamental_analysis.reports import render_markdown_report, save_report_artifacts
from fundamental_analysis.scoring import DimensionScore, ScoreReport
from fundamental_analysis.valuation import ValuationResult


class ReportTests(unittest.TestCase):
    def test_markdown_report_contains_required_sections(self):
        result = analyze_ticker_from_inputs(
            "RPT",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000, "depreciation_amortization": 20_000},
            {"shares": 10_000, "price": 60, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02, "dividend_per_share": 0.60, "revenue_cagr_5y": 0.1175, "earnings_cagr_5y": 0.4055},
            {"sector": "Industrials"},
        )
        markdown = result.report["markdown"]
        self.assertIn("Resumo executivo", markdown)
        self.assertIn("Tese da recomendacao", markdown)
        self.assertIn("Conclusao executiva", markdown)
        self.assertIn("O que ajudou", markdown)
        self.assertIn("O que pesou contra", markdown)
        self.assertIn("Ponte para decisao", markdown)
        self.assertIn("Preco atual da acao", markdown)
        self.assertIn("Indicadores principais", markdown)
        self.assertIn("| Valuation | P/L |", markdown)
        self.assertIn("| Endividamento | Liq. corrente |", markdown)
        self.assertIn("CAGR Receitas 5 anos", markdown)
        self.assertIn("Escala do score", markdown)
        self.assertIn("Valuation por metodo", markdown)
        self.assertIn("Taxa de desconto utilizada", markdown)
        self.assertIn("WACC de 10.00%", markdown)
        self.assertIn("Custo do patrimonio (Ke)", markdown)
        self.assertIn("Fluxo de Caixa Descontado (DCF/FCFF)", markdown)
        self.assertIn("Matriz de sensibilidade DCF", markdown)
        self.assertIn("WACC \\ g terminal", markdown)
        self.assertIn("Reverse DCF", markdown)
        self.assertIn("Crescimento implicito", markdown)
        self.assertIn("taxa de desconto", markdown)
        self.assertIn("Score por dimensao", markdown)
        self.assertIn("Fontes e confianca das metricas", markdown)
        self.assertIn("Notas explicativas", markdown)
        self.assertIn("Margem de seguranca negativa", markdown)
        self.assertIn("| Receita |", markdown)
        self.assertIn("Fontes dos dados principais:", markdown)
        self.assertIn("Entrada manual", markdown)
        self.assertTrue(result.report["metric_lineage_table"])
        self.assertIn("source", result.report["metric_lineage_table"][0])
        self.assertIn("confidence", result.report["metric_lineage_table"][0])
        self.assertIn("Recomendacao final", markdown)
        self.assertTrue(result.report["executive_decision"])
        self.assertIn("supports", result.report["executive_decision"])
        self.assertIn("pressures", result.report["executive_decision"])

    def test_html_report_contains_visual_decision_sections(self):
        result = analyze_ticker_from_inputs(
            "HTML",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000, "depreciation_amortization": 20_000},
            {
                "shares": 10_000,
                "price": 60,
                "wacc": 0.10,
                "growth_years": 0.04,
                "terminal_growth": 0.02,
                "dividend_per_share": 0.60,
                "peer_medians": {"price_to_earnings": 8.0, "ev_to_ebitda": 5.0, "ev_to_ebit": 6.0, "ev_to_sales": 1.2, "price_to_book": 1.0},
                "peer_median_counts": {"price_to_earnings": 4, "ev_to_ebitda": 4, "ev_to_ebit": 4, "ev_to_sales": 4, "price_to_book": 4},
            },
            {"sector": "Industrials"},
        )

        html = result.report["html"]

        self.assertIn("<!doctype html>", html)
        self.assertIn("Recomendacao", html)
        self.assertIn("Score total", html)
        self.assertIn("Preco atual", html)
        self.assertIn("Conclusao executiva", html)
        self.assertIn("executive-decision", html)
        self.assertIn("executive-card", html)
        self.assertIn("O que ajudou", html)
        self.assertIn("O que pesou contra", html)
        self.assertIn("Ponte para decisao", html)
        self.assertIn("Indicadores principais", html)
        self.assertIn("indicator-table", html)
        self.assertIn("signal positive", html)
        self.assertIn("P/L", html)
        self.assertIn("Escala do score", html)
        self.assertIn("Score por dimensao", html)
        self.assertIn("Valuation por metodo", html)
        self.assertIn("Taxa de desconto utilizada", html)
        self.assertIn("WACC de 10.00%", html)
        self.assertIn("Custo do patrimonio (Ke)", html)
        self.assertIn("Fluxo de Caixa Descontado (DCF/FCFF)", html)
        self.assertIn("Matriz de sensibilidade DCF", html)
        self.assertIn("WACC \\ g terminal", html)
        self.assertIn("Cenarios", html)
        self.assertIn("Reverse DCF", html)
        self.assertIn("Crescimento implicito", html)
        self.assertIn("reverse-grid", html)
        self.assertIn("Comparaveis", html)
        self.assertIn("Fontes dos dados principais", html)
        self.assertIn("Riscos principais", html)
        self.assertIn("card", html)
        self.assertIn("bar", html)
        self.assertIn("cost_of_capital", result.report)
        self.assertAlmostEqual(result.report["cost_of_capital"]["discount_rate"], 0.10)

    def test_reports_show_readable_source_lineage(self):
        result = analyze_ticker_from_inputs(
            "SRC",
            {
                "revenue": MetricValue(
                    "revenue",
                    1_000_000,
                    "yfinance",
                    0.85,
                    source_document="Yahoo Finance income statement",
                    period_end="2025-12-31",
                    currency="USD",
                    scale="raw",
                    basis="reported",
                ),
                "ebit": 200_000,
                "net_income": 120_000,
            },
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000, "depreciation_amortization": 20_000},
            {"shares": 10_000, "price": 60, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        markdown = result.report["markdown"]
        html = result.report["html"]

        self.assertIn("| Metrica | Valor usado | Base | Periodo | Moeda | Confianca | Fonte |", markdown)
        self.assertIn("Yahoo Finance, Yahoo Finance income statement, periodo 2025-12-31, moeda USD", markdown)
        self.assertIn("Fontes dos dados principais", html)
        self.assertIn("Yahoo Finance income statement", html)

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
        executive_markdown = apply_executive_layer_to_markdown(markdown, score, valuations)

        self.assertIn("nao subiu para Comprar", markdown)
        self.assertIn("abaixo do minimo exigido", markdown)
        self.assertIn("Trava/condicao decisiva", executive_markdown)
        self.assertIn("Para virar Comprar", markdown)

        html = render_html_report("GATE", score, valuations)
        executive_html = apply_executive_layer_to_html(html, score, valuations)
        self.assertIn("nao subiu para Comprar", html)
        self.assertIn("Trava/condicao", executive_html)
        self.assertIn("executive-card negative", executive_html)
        self.assertIn("Para virar Comprar", html)

    def test_growth_report_explains_short_cash_runway(self):
        result = analyze_ticker_from_inputs(
            "BURN",
            {"revenue": 1_000_000, "ebit": -500_000, "net_income": -600_000},
            {"total_assets": 2_000_000, "total_liabilities": 500_000, "equity": 1_500_000, "cash": 300_000, "total_debt": 100_000, "current_assets": 900_000, "current_liabilities": 200_000},
            {"cfo": -250_000, "capex": -150_000},
            {"shares": 100_000, "price": 20, "revenue_growth": 0.30},
            {"sector": "Technology", "industry": "Software"},
        )

        markdown = result.report["markdown"]
        risk_text = "\n".join(result.report["risk_diagnostics"])

        self.assertIn("Runway de caixa", markdown)
        self.assertIn("Runway de caixa", risk_text)
        self.assertIn("current ratio parece forte", markdown)

    def test_report_artifacts_are_saved_for_review(self):
        result = analyze_ticker_from_inputs(
            "Save/Me",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 120_000},
            {"total_assets": 1_500_000, "total_liabilities": 600_000, "equity": 900_000, "cash": 100_000, "total_debt": 250_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 150_000, "capex": -40_000},
            {"shares": 10_000, "price": 60, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials"},
        )

        with TemporaryDirectory() as tmpdir:
            artifacts = save_report_artifacts(result.ticker, result.report, tmpdir)
            markdown_path = Path(artifacts["markdown"])
            html_path = Path(artifacts["html"])
            json_path = Path(artifacts["tables_json"])

            self.assertTrue(markdown_path.exists())
            self.assertTrue(html_path.exists())
            self.assertTrue(json_path.exists())
            self.assertEqual(markdown_path.name, "SAVE_ME_analysis.md")
            self.assertIn("Ponte para decisao", markdown_path.read_text(encoding="utf-8"))
            self.assertIn("<!doctype html>", html_path.read_text(encoding="utf-8"))

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["recommendation"], result.score.recommendation)
            self.assertIn("cost_of_capital", payload)
            self.assertAlmostEqual(payload["cost_of_capital"]["discount_rate"], 0.10)
            self.assertTrue(payload["valuation_table"])


if __name__ == "__main__":
    unittest.main()
