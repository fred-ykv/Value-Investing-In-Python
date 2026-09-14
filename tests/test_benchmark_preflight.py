import json
import tempfile
import unittest
from pathlib import Path

from fundamental_analysis.benchmark_preflight import build_preflight


class BenchmarkPreflightTests(unittest.TestCase):
    def test_manifest_universe_is_enumerated_and_missing_inputs_block(self):
        result = build_preflight()
        self.assertEqual(result["expected_companies"], 50)
        self.assertEqual(result["observed_companies"], 50)
        self.assertEqual(result["eligible_companies"], 0)
        self.assertEqual(result["status"], "blocked")

    def test_lifecycle_price_coverage_does_not_override_economic_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({"capture_complete": True, "coverage_passed": True, "economic_reconciliation_passed": False, "coverage": [{"ticker": "MDLA", "is_ready": True}]}), encoding="utf-8")
            result = build_preflight(lifecycle_evidence=path)
        row = next(row for row in result["rows"] if row["ticker"] == "MDLA")
        self.assertFalse(row["elegivel"])
        self.assertIn("reconciliacao economica lifecycle pendente", row["motivos"])


if __name__ == "__main__":
    unittest.main()

