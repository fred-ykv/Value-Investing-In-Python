import unittest

from fundamental_analysis.main import analyze_ticker_from_inputs
from fundamental_analysis.metrics import MetricPack
from fundamental_analysis.peer_selection import build_peer_selection_report


class PeerSelectionTests(unittest.TestCase):
    def test_veto_rejects_incompatible_auto_peer(self):
        report = build_peer_selection_report(
            {
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "sic": "3711",
                "business_model": "traditional_auto",
                "market_cap": 50_000_000_000,
                "revenue_growth": 0.03,
                "operating_margin": 0.08,
                "debt_to_equity": 1.2,
            },
            MetricPack({}),
            [
                {
                    "ticker": "GM",
                    "sector": "Consumer Cyclical",
                    "industry": "Auto Manufacturers",
                    "sic": "3711",
                    "business_model": "traditional_auto",
                    "market_cap": 48_000_000_000,
                    "revenue_growth": 0.04,
                    "operating_margin": 0.07,
                    "debt_to_equity": 1.1,
                    "price_to_earnings": 7.0,
                },
                {
                    "ticker": "STLA",
                    "sector": "Consumer Cyclical",
                    "industry": "Auto Manufacturers",
                    "sic": "3711",
                    "business_model": "traditional_auto",
                    "market_cap": 55_000_000_000,
                    "revenue_growth": 0.02,
                    "operating_margin": 0.09,
                    "debt_to_equity": 1.3,
                    "price_to_earnings": 9.0,
                },
                {
                    "ticker": "TSLA",
                    "sector": "Consumer Cyclical",
                    "industry": "Auto Manufacturers",
                    "sic": "3711",
                    "business_model": "ev_pure_play",
                    "market_cap": 900_000_000_000,
                    "revenue_growth": 0.20,
                    "operating_margin": 0.12,
                    "debt_to_equity": 0.2,
                    "price_to_earnings": 60.0,
                },
            ],
        )

        self.assertEqual([peer.ticker for peer in report.approved], ["GM", "STLA"])
        rejected = {peer.ticker: peer for peer in report.rejected}
        self.assertEqual(rejected["TSLA"].status, "rejected_veto")
        self.assertTrue(rejected["TSLA"].vetoes)
        self.assertEqual(report.peer_medians["price_to_earnings"], 8.0)

    def test_approved_peers_feed_comparable_medians(self):
        result = analyze_ticker_from_inputs(
            "F",
            {"revenue": 1_000_000, "ebit": 80_000, "net_income": 60_000},
            {
                "total_assets": 2_000_000,
                "total_liabilities": 1_100_000,
                "equity": 900_000,
                "cash": 120_000,
                "total_debt": 400_000,
                "current_assets": 600_000,
                "current_liabilities": 300_000,
            },
            {"cfo": 100_000, "capex": -30_000},
            {
                "shares": 10_000,
                "price": 40,
                "peer_candidates": [
                    {
                        "ticker": "GM",
                        "sector": "Consumer Cyclical",
                        "industry": "Auto Manufacturers",
                        "sic": "3711",
                        "business_model": "traditional_auto",
                        "market_cap": 380_000,
                        "revenue_growth": 0.03,
                        "operating_margin": 0.08,
                        "debt_to_equity": 0.45,
                        "price_to_earnings": 8.0,
                        "ev_to_ebit": 7.0,
                    },
                    {
                        "ticker": "STLA",
                        "sector": "Consumer Cyclical",
                        "industry": "Auto Manufacturers",
                        "sic": "3711",
                        "business_model": "traditional_auto",
                        "market_cap": 420_000,
                        "revenue_growth": 0.02,
                        "operating_margin": 0.09,
                        "debt_to_equity": 0.50,
                        "price_to_earnings": 10.0,
                        "ev_to_ebit": 8.0,
                    }
                ],
            },
            {
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "sic": "3711",
                "business_model": "traditional_auto",
                "market_cap": 400_000,
            },
        )

        self.assertEqual([peer.ticker for peer in result.peer_selection.approved], ["GM", "STLA"])
        self.assertIn("Selecao assistida de pares", result.report["markdown"])
        self.assertTrue(result.report["comparable_table"])
        self.assertTrue(any(metric.source == "peer_medians" for metric in result.comparables.metrics))

    def test_single_approved_peer_does_not_feed_comparable_medians(self):
        report = build_peer_selection_report(
            {
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "sic": "3711",
                "business_model": "traditional_auto",
                "market_cap": 50_000_000_000,
            },
            MetricPack({}),
            [
                {
                    "ticker": "GM",
                    "sector": "Consumer Cyclical",
                    "industry": "Auto Manufacturers",
                    "sic": "3711",
                    "business_model": "traditional_auto",
                    "market_cap": 48_000_000_000,
                    "price_to_earnings": 7.0,
                }
            ],
        )

        self.assertEqual(report.confidence, 0.5)
        self.assertEqual(report.peer_medians, {})
        self.assertIn("abaixo do minimo", report.summary)

    def test_empty_candidate_list_is_low_confidence(self):
        report = build_peer_selection_report({}, MetricPack({}), [])

        self.assertEqual(report.confidence, 0.0)
        self.assertIn("Nenhum par aprovado", report.summary)


if __name__ == "__main__":
    unittest.main()
