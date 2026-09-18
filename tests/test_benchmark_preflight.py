import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fundamental_analysis.benchmark_preflight import _observation_index

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
        self.assertFalse(row["preco_disponivel"])

    def test_preserves_every_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.csv"
            path.write_text("ticker,point_in_time_validated\nMLI,False\nMLI,True\n", encoding="utf-8")
            rows = _observation_index(path)
        self.assertEqual(len(rows["MLI"]), 2)

    def test_expanded_executor_blocks_before_clients_or_calculation(self):
        import build_historical_dataset as runner
        with tempfile.TemporaryDirectory() as tmp:
            with patch("sys.argv", ["runner", "--universe", "expanded", "--outdir", tmp]), patch.object(runner, "SecEdgarClient") as sec, patch.object(runner, "collect_benchmark_history") as collect:
                self.assertEqual(runner.main(), 2)
                sec.assert_not_called()
                collect.assert_not_called()
            result = json.loads((Path(tmp) / "benchmark_preflight.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(len(result["rows"]), 50)


if __name__ == "__main__":
    unittest.main()

