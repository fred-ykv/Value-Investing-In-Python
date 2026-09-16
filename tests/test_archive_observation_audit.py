import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fundamental_analysis.archive_observation_audit import audit_observations


class ObservationAuditTests(unittest.TestCase):
    def test_missing_benchmark_window_is_not_hidden_by_other_inputs(self):
        archive = MagicMock()
        archive.digest = "fixture"
        archive.manifest = {"run": {"cases": [{"ticker": "MLI", "benchmark_group": "tradicionais_ciclicas"}]}}
        archive.load.return_value = json.dumps({"results": [{"ticker": "MLI", "observation": {
            "ticker": "MLI", "as_of": "2020-03-01", "filing_accession": "fixture"}}]})
        module = "fundamental_analysis.archive_observation_audit."
        with patch(module + "ArchiveReader", return_value=archive), patch(module + "ReplaySecClient") as sec, patch(module + "ReplayMacroClient") as macro, patch(module + "ReplayPriceClient") as prices:
            sec.return_value.build_snapshot.return_value.audit.point_in_time_valid = True
            macro.return_value.snapshot.return_value.point_in_time_valid = True
            prices.return_value.fetch_series.side_effect = [SimpleNamespace(points=[1], ticker="MLI"), ValueError("benchmark ausente")]
            result = audit_observations("fixture")
        self.assertEqual(result["inputs_available"], 0)
        self.assertFalse(result["benchmark_authorized"])
        self.assertFalse(result["rows"][0]["checks"]["benchmark_window"])
        self.assertIn("benchmark ausente", result["rows"][0]["issues"][0])

