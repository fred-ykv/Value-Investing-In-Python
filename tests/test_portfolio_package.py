from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fundamental_analysis.portfolio_attestation import load_portfolio_attestation
from fundamental_analysis.portfolio_package import prepare_portfolio_package


class Reader:
    digest = "a" * 64


def observation(ticker, as_of, score):
    return {
        "ticker": ticker, "as_of": as_of, "total_score": score,
        "sector_bucket": "industrial", "point_in_time_validated": True,
        "analysis_input_validated": True,
    }


class PortfolioPackageTests(unittest.TestCase):
    def test_missing_volume_and_longitudinal_history_block_without_attestation(self):
        loaded = ([Reader()], [observation("AAA", "2020-01-02", 0.7)],
                  {("AAA", "2020-01-02"): {"raw_close": 10.0, "adjusted_close": 10.0, "volume": None}},
                  [], [(date(2020, 1, 1), date(2020, 1, 31))], [])
        with tempfile.TemporaryDirectory() as tmp, patch("fundamental_analysis.portfolio_package._load_archives", return_value=loaded):
            output = Path(tmp) / "package"
            result = prepare_portfolio_package(["archive"], output, sessions=(date(2020, 1, 2),))
            self.assertEqual(result["status"], "blocked")
            self.assertFalse((output / "portfolio_attestation.json").exists())
            self.assertTrue(any("volume ausente" in issue for issue in result["issues"]))
            self.assertTrue(any("longitudinal" in issue for issue in result["issues"]))

    def test_ready_package_is_accepted_by_preflight_contract(self):
        sessions = (date(2020, 1, 30), date(2020, 1, 31), date(2020, 2, 3))
        observations = [observation("AAA", "2020-01-02", 0.7), observation("AAA", "2020-01-30", 0.8)]
        prices = {("AAA", day.isoformat()): {"raw_close": 10.0, "adjusted_close": 10.0, "volume": 1000}
                  for day in sessions}
        loaded = ([Reader()], observations, prices, [], [(sessions[0], sessions[-1])], [])
        with tempfile.TemporaryDirectory() as tmp, patch("fundamental_analysis.portfolio_package._load_archives", return_value=loaded):
            output = Path(tmp) / "package"
            result = prepare_portfolio_package(["archive"], output, sessions=sessions,
                                               experiment_id="benchmark-pit", manifest_version="1.1")
            accepted = load_portfolio_attestation(output, expected_experiment_id="benchmark-pit",
                                                   expected_manifest_version="1.1",
                                                   verified_archive_sha256=["a" * 64])
            inputs = json.loads((output / "portfolio_inputs.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["package_written"])
        self.assertEqual(accepted["portfolio_input_hashes"], result["portfolio_input_hashes"])
        self.assertEqual(inputs["signals"][0]["day"], "2020-01-31")


if __name__ == "__main__":
    unittest.main()

