import unittest

from fundamental_analysis.metrics import MetricPack
from fundamental_analysis.peer_selection import (
    PeerCandidateResult,
    build_peer_selection_report,
    peer_selection_confidence_details,
)


class PeerConfidenceTests(unittest.TestCase):
    def test_two_approved_peers_are_not_labeled_as_certain(self):
        peers = [
            PeerCandidateResult("A", 0.90, "strong", data_confidence=0.80),
            PeerCandidateResult("B", 0.85, "strong", data_confidence=0.80),
        ]
        confidence, size, quality, label = peer_selection_confidence_details(peers, peers)
        self.assertAlmostEqual(size, 2 / 6)
        self.assertAlmostEqual(quality, 0.80)
        self.assertAlmostEqual(confidence, 2 / 6 * 0.80)
        self.assertEqual(label, "Amostra estreita")

    def test_low_quality_and_weak_reference_reduce_confidence(self):
        approved = [PeerCandidateResult("A", 0.70, "acceptable", data_confidence=0.55)]
        weak = [PeerCandidateResult("W", 0.52, "weak_reference", data_confidence=0.55)]
        confidence, size, quality, label = peer_selection_confidence_details(approved, approved + weak)
        self.assertLess(confidence, 0.20)
        self.assertEqual(label, "Amostra estreita")

    def test_empty_selection_is_explicitly_low_confidence(self):
        details = peer_selection_confidence_details([], [])
        self.assertEqual(details, (0.0, 0.0, 0.0, "Sem amostra"))

    def test_report_exposes_confidence_audit(self):
        report = build_peer_selection_report(
            {"sector": "Industrials", "industry": "Steel", "business_model": "metal_fabrication"},
            MetricPack({}),
            [{"ticker": "A", "sector": "Industrials", "industry": "Steel", "business_model": "metal_fabrication", "price_to_earnings": 10}],
        )
        self.assertIn("confianca da evidencia", report.summary.lower())
        self.assertGreaterEqual(report.confidence_sample_size, 0.0)


if __name__ == "__main__":
    unittest.main()

