import unittest

import fundamental_analysis.main as main_module
from fundamental_analysis.main import analyze_ticker_from_inputs
from fundamental_analysis.peer_enrichment import enrich_peer_candidates
from fundamental_analysis.peer_selection import build_peer_selection_report
from fundamental_analysis.metrics import MetricPack


class PeerEnrichmentTests(unittest.TestCase):
    def test_enriches_missing_peer_fields_from_fetcher(self):
        enriched = enrich_peer_candidates(
            [{"ticker": "GM", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "business_model": "traditional_auto", "sic": "3711"}],
            fetch_info=lambda ticker: {
                "marketCap": 48_000_000_000,
                "trailingPE": 8.0,
                "enterpriseToRevenue": 1.2,
                "revenueGrowth": 0.04,
                "operatingMargins": 0.07,
                "debtToEquity": 120.0,
            },
        )

        peer = enriched[0]
        self.assertEqual(peer["market_cap"], 48_000_000_000)
        self.assertEqual(peer["price_to_earnings"], 8.0)
        self.assertAlmostEqual(peer["debt_to_equity"], 1.2)
        self.assertEqual(peer["_peer_metric_sources"]["price_to_earnings"], "yfinance")
        self.assertGreaterEqual(peer["peer_data_confidence"], 0.70)

    def test_manual_values_are_not_overwritten_by_yahoo(self):
        enriched = enrich_peer_candidates(
            [{"ticker": "GM", "price_to_earnings": 7.0, "candidate_source": "manual"}],
            fetch_info=lambda ticker: {"trailingPE": 9.0},
        )

        self.assertEqual(enriched[0]["price_to_earnings"], 7.0)
        self.assertEqual(enriched[0]["_peer_metric_sources"]["price_to_earnings"], "manual")

    def test_relative_median_requires_two_peers_with_usable_multiple_confidence(self):
        report = build_peer_selection_report(
            {
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "sic": "3711",
                "business_model": "traditional_auto",
                "market_cap": 400_000,
            },
            MetricPack({}),
            [
                {
                    "ticker": "GM",
                    "sector": "Consumer Cyclical",
                    "industry": "Auto Manufacturers",
                    "sic": "3711",
                    "business_model": "traditional_auto",
                    "market_cap": 380_000,
                    "price_to_earnings": 8.0,
                    "peer_data_confidence": 0.80,
                },
                {
                    "ticker": "STLA",
                    "sector": "Consumer Cyclical",
                    "industry": "Auto Manufacturers",
                    "sic": "3711",
                    "business_model": "traditional_auto",
                    "market_cap": 420_000,
                    "peer_data_confidence": 0.80,
                },
            ],
        )

        self.assertEqual(report.peer_medians, {})

    def test_analysis_uses_enriched_builtin_peers_for_comparable_medians(self):
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
                        "price_to_earnings": 8.0,
                    },
                    {
                        "ticker": "STLA",
                        "sector": "Consumer Cyclical",
                        "industry": "Auto Manufacturers",
                        "sic": "3711",
                        "business_model": "traditional_auto",
                        "market_cap": 420_000,
                        "price_to_earnings": 10.0,
                    },
                ],
            },
            {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "sic": "3711", "business_model": "traditional_auto", "market_cap": 400_000},
        )

        self.assertEqual(result.peer_selection.peer_medians["price_to_earnings"], 9.0)
        self.assertIn("Confianca dados", result.report["markdown"])

    def test_manual_analysis_uses_peer_yahoo_enrichment_by_default(self):
        original_enrich = main_module.enrich_peer_candidates
        calls = []

        def fake_enrich(candidates, *, use_yahoo=None, **kwargs):
            calls.append(use_yahoo)
            enriched = []
            for index, candidate in enumerate(candidates):
                row = dict(candidate)
                row["price_to_earnings"] = 8.0 + index
                row["_peer_metric_sources"] = {"price_to_earnings": "yfinance"}
                row["peer_data_confidence"] = 0.80
                enriched.append(row)
            return enriched

        main_module.enrich_peer_candidates = fake_enrich
        try:
            result = main_module.analyze_ticker_from_inputs(
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
                {"shares": 10_000, "price": 40},
                {
                    "ticker": "F",
                    "sector": "Consumer Cyclical",
                    "industry": "Auto Manufacturers",
                    "sic": "3711",
                    "business_model": "traditional_auto",
                    "market_cap": 400_000,
                },
            )
        finally:
            main_module.enrich_peer_candidates = original_enrich

        self.assertEqual(calls, [True])
        self.assertIn("price_to_earnings", result.peer_selection.peer_medians)


if __name__ == "__main__":
    unittest.main()
