import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from collect_lifecycle_evidence import collect_lifecycle_evidence
from fundamental_analysis.historical_prices import CsvHistoricalPriceClient
from fundamental_analysis.institutional_prices import TIINGO_LIFECYCLE_MAPPINGS


def response_fixture(url):
    path = urlparse(url).path.split("/")
    ticker = path[-2] if path[-1] == "prices" else path[-1]
    mapping = next(m for m in TIINGO_LIFECYCLE_MAPPINGS if m.provider_ticker == ticker)
    if path[-1] != "prices":
        return {"ticker": ticker, "name": mapping.expected_name,
                "startDate": mapping.expected_first_price_date.isoformat(),
                "endDate": mapping.expected_last_price_date.isoformat()}
    rows = []
    day = mapping.expected_first_price_date
    while day <= mapping.expected_last_price_date:
        if day.weekday() < 5:
            rows.append({"date": day.isoformat(), "close": 9.25, "adjClose": 4.50,
                         "volume": 0 if day == mapping.expected_last_price_date else 100,
                         "divCash": 0.05, "splitFactor": 2.0})
        day += timedelta(days=1)
    return rows


class LifecycleEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_exports_full_responses_roundtrips_prices_and_never_approves_economics(self):
        output = self.root / "evidence"
        report = collect_lifecycle_evidence(output, api_token="TEST_PRIVATE_TOKEN", json_getter=response_fixture)
        self.assertTrue(report["capture_complete"])
        self.assertEqual(len(report["responses"]), 20)
        self.assertEqual(len(report["coverage"]), 10)
        self.assertFalse(report["eligible_for_benchmark"])
        self.assertFalse(report["economic_reconciliation_passed"])
        client = CsvHistoricalPriceClient(output / "normalized_prices.csv")
        for mapping in TIINGO_LIFECYCLE_MAPPINGS:
            series = client.fetch_series(mapping.canonical_ticker, mapping.expected_first_price_date, mapping.expected_last_price_date)
            self.assertEqual(series.issuer_cik, mapping.issuer_cik)
            self.assertEqual(series.points[-1].day, mapping.expected_last_price_date)
            self.assertEqual(series.points[-1].raw_close, 9.25)
            self.assertEqual(series.points[-1].adjusted_close, 4.50)
        for response in report["responses"]:
            content = (output / response["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), response["sha256"])
            if "/prices?" in response["url"]:
                last = json.loads(content)[-1]
                self.assertEqual(last["volume"], 0)
                self.assertEqual(last["divCash"], 0.05)
                self.assertEqual(last["splitFactor"], 2.0)
        for name, digest in report["files_sha256"].items():
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest(), (output / "manifest.sha256").read_text().strip())
        for file in output.rglob("*"):
            if file.is_file():
                self.assertNotIn(b"TEST_PRIVATE_TOKEN", file.read_bytes())

    def test_missing_fields_stay_missing_in_full_response(self):
        def getter(url):
            payload = response_fixture(url)
            if isinstance(payload, list):
                for row in payload:
                    row.pop("volume")
            return payload

        output = self.root / "missing_volume"
        report = collect_lifecycle_evidence(output, json_getter=getter)
        self.assertTrue(report["capture_complete"])
        self.assertFalse(report["eligible_for_benchmark"])
        response = next(r for r in report["responses"] if "/prices?" in r["url"])
        self.assertNotIn("volume", json.loads((output / response["path"]).read_bytes())[0])

    def test_failure_is_partial_redacted_and_preserves_other_issuers(self):
        def getter(url):
            if "/MDLA/prices?" in url:
                raise RuntimeError("Authorization: Token PRIVATE_VALUE")
            return response_fixture(url)

        output = self.root / "partial"
        report = collect_lifecycle_evidence(output, api_token="PRIVATE_VALUE", json_getter=getter)
        self.assertFalse(report["capture_complete"])
        self.assertEqual(report["state"], "incomplete")
        self.assertEqual(sum(row["is_ready"] for row in report["coverage"]), 9)
        self.assertEqual(sum(r["status"] == "failed" for r in report["responses"]), 1)
        with self.assertRaises(LookupError):
            mapping = TIINGO_LIFECYCLE_MAPPINGS[0]
            CsvHistoricalPriceClient(output / "normalized_prices.csv").fetch_series("MDLA", mapping.expected_first_price_date, mapping.expected_last_price_date)
        for file in output.rglob("*"):
            if file.is_file():
                self.assertNotIn(b"PRIVATE_VALUE", file.read_bytes())

    def test_invalid_identity_is_archived_but_not_exported_as_valid_prices(self):
        def getter(url):
            payload = response_fixture(url)
            if url.endswith("/MDLA"):
                payload["name"] = "Unrelated company"
            return payload

        report = collect_lifecycle_evidence(self.root / "identity", json_getter=getter)
        self.assertFalse(report["capture_complete"])
        self.assertFalse(report["coverage"][0]["is_ready"])
        self.assertTrue(any(r["url"].endswith("/MDLA") and r["status"] == "captured" for r in report["responses"]))

    def test_response_reflecting_credential_is_not_archived(self):
        def getter(url):
            payload = response_fixture(url)
            if url.endswith("/MDLA"):
                payload["debug"] = "PRIVATE_VALUE"
            return payload

        output = self.root / "reflected_credential"
        report = collect_lifecycle_evidence(output, api_token="PRIVATE_VALUE", json_getter=getter)
        self.assertFalse(report["capture_complete"])
        self.assertEqual(sum(row["is_ready"] for row in report["coverage"]), 9)
        for file in output.rglob("*"):
            if file.is_file():
                self.assertNotIn(b"PRIVATE_VALUE", file.read_bytes())

    def test_existing_directory_is_never_overwritten(self):
        output = self.root / "existing"
        output.mkdir()
        protected = output / "manifest.json"
        protected.write_text("original", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            collect_lifecycle_evidence(output, json_getter=response_fixture)
        self.assertEqual(protected.read_text(), "original")

    def test_missing_token_fails_before_creating_package(self):
        with patch.dict(os.environ, {"TIINGO_API_KEY": ""}):
            with self.assertRaises(ValueError):
                collect_lifecycle_evidence(self.root / "no_token")
        self.assertFalse((self.root / "no_token").exists())

    def test_code_drift_prevents_complete_status(self):
        with patch("collect_lifecycle_evidence.evidence_code_fingerprints", side_effect=[{"code": "before"}, {"code": "after"}]):
            report = collect_lifecycle_evidence(self.root / "drift", json_getter=response_fixture)
        self.assertTrue(report["coverage_passed"])
        self.assertFalse(report["capture_complete"])
        self.assertFalse(report["code_unchanged_during_capture"])


if __name__ == "__main__":
    unittest.main()
