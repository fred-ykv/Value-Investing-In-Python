import unittest

from fundamental_analysis.comparables import build_comparable_report, score_premium_discount
from fundamental_analysis.config import CompanyType
from fundamental_analysis.main import analyze_ticker_from_inputs


class ComparableTests(unittest.TestCase):
    def test_relative_discount_scores_better_than_premium(self):
        self.assertGreater(score_premium_discount(-0.25), score_premium_discount(0.25))

    def test_traditional_company_uses_peer_medians(self):
        result = analyze_ticker_from_inputs(
            "CMP",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 100_000},
            {"total_assets": 1_500_000, "total_liabilities": 500_000, "equity": 1_000_000, "cash": 100_000, "total_debt": 200_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 140_000, "capex": -40_000},
            {
                "shares": 10_000,
                "price": 50,
                "wacc": 0.10,
                "growth_years": 0.04,
                "terminal_growth": 0.02,
                "peer_medians": {"price_to_earnings": 8.0, "ev_to_ebit": 5.0, "ev_to_sales": 0.8, "price_to_book": 0.8},
            },
            {"sector": "Industrials"},
        )

        table = result.report["comparable_table"]
        self.assertTrue(table)
        self.assertIn("Comparaveis de mercado", result.report["markdown"])
        self.assertGreater(result.comparables.confidence, 0.0)
        self.assertGreater(result.comparables.overall_score, 0.50)

    def test_financial_comparables_focus_on_price_to_book_and_earnings(self):
        result = analyze_ticker_from_inputs(
            "BNK",
            {"revenue": 1_000_000, "ebit": 250_000, "net_income": 120_000},
            {"total_assets": 10_000_000, "total_liabilities": 9_000_000, "equity": 1_000_000, "cash": 500_000, "total_debt": 2_000_000, "current_assets": 0, "current_liabilities": 0},
            {"cfo": 150_000, "capex": -10_000},
            {"shares": 100_000, "price": 12, "peer_pb": 1.5, "peer_pe": 12.0},
            {"sector": "Financial Services", "industry": "Banks"},
        )

        names = [row["metric"] for row in result.report["comparable_table"]]

        self.assertEqual(names, ["price_to_book", "price_to_earnings"])

    def test_comparable_report_handles_missing_peers(self):
        report = build_comparable_report(CompanyType.TRADITIONAL, {}, {}, {})

        self.assertEqual(report.confidence, 0.0)
        self.assertIn("Sem medianas", report.summary)


if __name__ == "__main__":
    unittest.main()
