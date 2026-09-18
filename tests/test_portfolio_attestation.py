import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from fundamental_analysis.portfolio_attestation import load_portfolio_attestation


class PortfolioAttestationTests(unittest.TestCase):
    def write_package(self, root, *, sources=None):
        payload = {
            "schema_version": 1,
            "experiment_id": "benchmark-pit",
            "manifest_version": "1.1",
            "source_archive_sha256": sorted(sources or ["a" * 64, "b" * 64]),
            "portfolio_input_hashes": {
                key: digit * 64 for key, digit in zip(
                    ("sessions", "signals", "bars", "events", "rules"), "12345"
                )
            },
            "calendar_sessions_sha256": "c" * 64,
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        document = Path(root) / "portfolio_attestation.json"
        document.write_bytes(raw)
        document.with_suffix(".sha256").write_text(sha256(raw).hexdigest(), encoding="ascii")
        return document

    def test_accepts_exact_verified_sources_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = self.write_package(tmp)
            result = load_portfolio_attestation(document, expected_experiment_id="benchmark-pit",
                                                 expected_manifest_version="1.1",
                                                 verified_archive_sha256=["b" * 64, "a" * 64])
        self.assertTrue(result["integrity_verified"])

    def test_rejects_source_omission(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = self.write_package(tmp, sources=["a" * 64])
            with self.assertRaisesRegex(ValueError, "fontes"):
                load_portfolio_attestation(document, expected_experiment_id="benchmark-pit",
                                           expected_manifest_version="1.1",
                                           verified_archive_sha256=["a" * 64, "b" * 64])

    def test_rejects_tampered_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = self.write_package(tmp)
            document.write_text(document.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash"):
                load_portfolio_attestation(document, expected_experiment_id="benchmark-pit",
                                           expected_manifest_version="1.1",
                                           verified_archive_sha256=["a" * 64, "b" * 64])


if __name__ == "__main__":
    unittest.main()

