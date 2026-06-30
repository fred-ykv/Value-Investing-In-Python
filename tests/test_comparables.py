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
            {"cfo": 140_000, "capex": -40_000, "depreciation_amortization": 50_000},
            {
                "shares": 10_000,
                "price": 50,
                "wacc": 0.10,
                "growth_years": 0.04,
                "terminal_growth": 0.02,
                "peer_medians": {"price_to_earnings": 8.0, "ev_to_ebitda": 4.0, "ev_to_ebit": 5.0, "ev_to_sales": 0.8, "price_to_book": 0.8},
            },
            {"sector": "Industrials"},
        )

        table = result.report["comparable_table"]
        names = [row["metric"] for row in table]
        self.assertTrue(table)
        self.assertIn("ev_to_ebitda", names)
        self.assertIn("Comparaveis de mercado", result.report["markdown"])
        self.assertIn("N pares", result.report["markdown"])
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

    def test_growth_tech_comparables_prioritize_sales_multiples(self):
        result = analyze_ticker_from_inputs(
            "SaaS",
            {"revenue": 1_000_000, "ebit": -50_000, "net_income": -80_000},
            {"total_assets": 1_500_000, "total_liabilities": 300_000, "equity": 1_200_000, "cash": 500_000, "total_debt": 100_000, "current_assets": 900_000, "current_liabilities": 200_000},
            {"cfo": 50_000, "capex": -20_000},
            {"shares": 100_000, "price": 20, "revenue_growth": 0.30, "peer_medians": {"ev_to_sales": 8.0, "price_to_sales": 7.0, "price_to_earnings": 40.0}},
            {"sector": "Technology", "industry": "Software"},
        )

        names = [row["metric"] for row in result.report["comparable_table"]]

        self.assertEqual(names, ["ev_to_sales", "price_to_sales", "price_to_earnings"])

    def test_low_peer_sample_penalizes_relative_confidence(self):
        result = analyze_ticker_from_inputs(
            "THIN",
            {"revenue": 1_000_000, "ebit": 200_000, "net_income": 100_000},
            {"total_assets": 1_500_000, "total_liabilities": 500_000, "equity": 1_000_000, "cash": 100_000, "total_debt": 200_000, "current_assets": 500_000, "current_liabilities": 250_000},
            {"cfo": 140_000, "capex": -40_000},
            {
                "shares": 10_000,
                "price": 50,
                "peer_medians": {"price_to_earnings": 8.0},
                "peer_median_counts": {"price_to_earnings": 1},
            },
            {"sector": "Industrials"},
        )

        self.assertLess(result.comparables.confidence, 0.50)
        self.assertIn("rebaixada por amostra limitada", result.comparables.summary)

    def test_comparable_report_handles_missing_peers(self):
        report = build_comparable_report(CompanyType.TRADITIONAL, {}, {}, {})

        self.assertEqual(report.confidence, 0.0)
        self.assertIn("Sem medianas", report.summary)

    def test_missing_peer_medians_fall_back_to_sector_benchmark(self):
        result = analyze_ticker_from_inputs(
            "MLI",
            {"revenue": 4_000_000, "ebit": 900_000, "net_income": 700_000},
            {"total_assets": 5_000_000, "total_liabilities": 900_000, "equity": 4_100_000, "cash": 1_000_000, "total_debt": 200_000, "current_assets": 2_000_000, "current_liabilities": 400_000},
            {"cfo": 800_000, "capex": -200_000, "depreciation_amortization": 120_000},
            {"shares": 100_000, "price": 120, "wacc": 0.10, "growth_years": 0.04, "terminal_growth": 0.02},
            {"sector": "Industrials", "industry": "Metal Fabrication", "business_model": "metal_fabrication"},
        )

        table = result.report["comparable_table"]
        self.assertTrue(table)
        self.assertIn("damodaran_sector_benchmark", {row["source"] for row in table})
        self.assertIn("benchmark setorial Damodaran", result.comparables.summary)
        self.assertGreater(result.comparables.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
