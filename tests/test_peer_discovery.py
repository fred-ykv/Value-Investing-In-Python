import unittest

from fundamental_analysis.main import analyze_ticker_from_inputs
from fundamental_analysis.metrics import MetricPack
from fundamental_analysis.peer_discovery import discover_peer_candidates


class PeerDiscoveryTests(unittest.TestCase):
    def test_discovers_candidates_from_universe(self):
        candidates = discover_peer_candidates(
            {
                "ticker": "F",
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "sic": "3711",
                "business_model": "traditional_auto",
                "market_cap": 50_000_000_000,
                "revenue_growth": 0.03,
                "operating_margin": 0.08,
            },
            MetricPack({}),
            {
                "peer_universe": [
                    {
                        "ticker": "GM",
                        "sector": "Consumer Cyclical",
                        "industry": "Auto Manufacturers",
                        "sic": "3711",
                        "business_model": "traditional_auto",
                        "market_cap": 48_000_000_000,
                        "revenue_growth": 0.04,
                        "operating_margin": 0.07,
                    },
                    {
                        "ticker": "JPM",
                        "sector": "Financial Services",
                        "industry": "Banks - Diversified",
                        "sic": "6021",
                        "business_model": "bank",
                        "market_cap": 450_000_000_000,
                    },
                ]
            },
        )

        self.assertEqual([candidate["ticker"] for candidate in candidates], ["GM"])
        self.assertGreaterEqual(candidates[0]["discovery_score"], 0.55)

    def test_analysis_uses_discovered_universe_when_no_manual_candidates(self):
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
                "peer_universe": [
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
                    },
                    {
                        "ticker": "TSLA",
                        "sector": "Consumer Cyclical",
                        "industry": "Auto Manufacturers",
                        "sic": "3711",
                        "business_model": "ev_pure_play",
                        "market_cap": 9_000_000,
                        "revenue_growth": 0.20,
                        "operating_margin": 0.12,
                        "price_to_earnings": 60.0,
                    },
                ],
            },
            {
                "ticker": "F",
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "sic": "3711",
                "business_model": "traditional_auto",
                "market_cap": 400_000,
            },
        )

        self.assertEqual([peer.ticker for peer in result.peer_selection.approved], ["GM", "STLA"])
        self.assertEqual(result.peer_selection.peer_medians["price_to_earnings"], 9.0)
        rejected = {peer.ticker: peer for peer in result.peer_selection.rejected}
        self.assertEqual(rejected["TSLA"].status, "rejected_veto")


if __name__ == "__main__":
    unittest.main()
