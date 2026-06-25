import unittest

from fundamental_analysis.metrics import MetricPack
from fundamental_analysis.peer_discovery import discover_peer_candidates
from fundamental_analysis.peer_universe import build_peer_universe


class PeerUniverseTests(unittest.TestCase):
    def test_builtin_universe_uses_business_model_and_excludes_target(self):
        result = build_peer_universe(
            {
                "ticker": "F",
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "sic": "3711",
                "business_model": "traditional_auto",
            },
            {},
        )

        tickers = [candidate["ticker"] for candidate in result.candidates]
        self.assertIn("GM", tickers)
        self.assertIn("STLA", tickers)
        self.assertNotIn("F", tickers)
        self.assertIn("builtin_seed:traditional_auto", result.sources)

    def test_configured_universe_accepts_mapping_keys_and_candidates(self):
        result = build_peer_universe(
            {"ticker": "ABC", "industry": "Custom Industry"},
            {
                "configured_peer_universe": {
                    "ABC": ["XYZ"],
                    "Custom Industry": [{"ticker": "DEF", "sector": "Industrials"}],
                    "Default": ["QQQ"],
                }
            },
        )

        tickers = [candidate["ticker"] for candidate in result.candidates]
        self.assertEqual(tickers[:3], ["XYZ", "DEF", "QQQ"])
        self.assertEqual(result.candidates[0]["candidate_source"], "configured_peer_universe")

    def test_discovery_can_use_builtin_universe_without_manual_peer_universe(self):
        candidates = discover_peer_candidates(
            {
                "ticker": "F",
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "sic": "3711",
                "business_model": "traditional_auto",
            },
            MetricPack({}),
            {},
        )

        tickers = [candidate["ticker"] for candidate in candidates]
        self.assertIn("GM", tickers)
        self.assertIn("STLA", tickers)
        self.assertTrue(all(candidate["candidate_source"].startswith("builtin_seed:") for candidate in candidates))


if __name__ == "__main__":
    unittest.main()
