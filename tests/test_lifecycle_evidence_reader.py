import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from collect_lifecycle_evidence import collect_lifecycle_evidence
from fundamental_analysis.historical_prices import CsvHistoricalPriceClient
from fundamental_analysis.lifecycle_evidence import LifecycleEvidencePriceClient
from fundamental_analysis.price_eligibility import PriceEligibilityError
from tests.test_lifecycle_evidence import response_fixture


class LifecycleEvidenceReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.original = Path(cls.shared.name) / "evidence"
        collect_lifecycle_evidence(cls.original, json_getter=response_fixture)

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evidence = self.root / "evidence"
        shutil.copytree(self.original, self.evidence)

    def change_manifest(self, change):
        path = self.evidence / "manifest.json"
        manifest = json.loads(path.read_bytes())
        change(manifest)
        raw = json.dumps(manifest).encode()
        path.write_bytes(raw)
        (self.evidence / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest())

    def test_zip_and_directory_preserve_raw_prices_and_volume_without_network(self):
        path = self.root / "package.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            for file in self.evidence.rglob("*"):
                if file.is_file():
                    bundle.write(file, "lifecycle_evidence/evidence/" + file.relative_to(self.evidence).as_posix())
            bundle.writestr("lifecycle_evidence/source.zip", b"not executed")
        with patch("socket.socket", side_effect=AssertionError("network")):
            zipped = LifecycleEvidencePriceClient(path).fetch_series("MDLA", date.min, date.max)
            direct = LifecycleEvidencePriceClient(self.evidence).fetch_series("MDLA", date.min, date.max)
            csv = CsvHistoricalPriceClient(self.evidence / "normalized_prices.csv").fetch_series("MDLA", date.min, date.max)
        self.assertEqual(zipped, direct)
        self.assertEqual(csv.points, direct.points)
        self.assertEqual(zipped.points[-1].day, date(2021, 10, 29))
        self.assertEqual(zipped.points[-1].volume, 0)
        self.assertEqual(len(zipped.input_evidence_sha256), 64)

    def test_missing_or_incomplete_manifest_rejects_csv(self):
        self.change_manifest(lambda m: m.update(state="incomplete", capture_complete=False))
        with self.assertRaisesRegex(PriceEligibilityError, "incompleto"):
            CsvHistoricalPriceClient(self.evidence / "normalized_prices.csv")
        (self.evidence / "manifest.json").unlink()
        with self.assertRaises(PriceEligibilityError):
            CsvHistoricalPriceClient(self.evidence / "normalized_prices.csv")

    def test_manifest_hash_tampering_is_rejected(self):
        path = self.evidence / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(PriceEligibilityError, "Hash do manifesto"):
            LifecycleEvidencePriceClient(self.evidence)

    def test_raw_response_tampering_is_rejected(self):
        manifest = json.loads((self.evidence / "manifest.json").read_bytes())
        path = self.evidence / manifest["responses"][0]["path"]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(PriceEligibilityError, "adulterada"):
            LifecycleEvidencePriceClient(self.evidence)

    def test_csv_rehashed_but_not_matching_originals_is_rejected(self):
        path = self.evidence / "normalized_prices.csv"
        path.write_bytes(path.read_bytes().replace(b"9.25", b"9.35", 1))
        self.change_manifest(lambda m: m["files_sha256"].update({path.name: hashlib.sha256(path.read_bytes()).hexdigest()}))
        with self.assertRaisesRegex(PriceEligibilityError, "nao reconcilia"):
            LifecycleEvidencePriceClient(self.evidence)

    def test_identity_changed_even_with_updated_hash_is_rejected(self):
        def change(manifest):
            record = manifest["responses"][0]
            path = self.evidence / record["path"]
            payload = json.loads(path.read_bytes())
            payload["name"] = "Reused ticker, unrelated issuer"
            raw = json.dumps(payload).encode()
            path.write_bytes(raw)
            record.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        self.change_manifest(change)
        with self.assertRaisesRegex(PriceEligibilityError, "Emissor"):
            LifecycleEvidencePriceClient(self.evidence)

    def test_unsafe_and_duplicate_zip_paths_are_rejected(self):
        for name in ("../manifest.json", "C:/outside", "evidence/../outside"):
            path = self.root / "unsafe.zip"
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr(name, "{}")
            with self.assertRaisesRegex(PriceEligibilityError, "Caminho inseguro"):
                LifecycleEvidencePriceClient(path)
        path = self.root / "duplicates.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("evidence/manifest.json", "{}")
            bundle.writestr("evidence/MANIFEST.json", "{}")
        with self.assertRaisesRegex(PriceEligibilityError, "duplicados"):
            LifecycleEvidencePriceClient(path)

    def test_missing_and_duplicate_response_records_are_rejected(self):
        self.change_manifest(lambda m: m["responses"].__setitem__(1, m["responses"][0]))
        with self.assertRaisesRegex(PriceEligibilityError, "duplicada"):
            LifecycleEvidencePriceClient(self.evidence)
        self.change_manifest(lambda m: m["responses"].pop())
        with self.assertRaisesRegex(PriceEligibilityError, "incompletas"):
            LifecycleEvidencePriceClient(self.evidence)

    def test_cli_uses_evidence_and_reports_partial_collection_as_failure(self):
        import build_historical_dataset as build
        from types import SimpleNamespace
        with patch("sys.argv", ["build_historical_dataset.py", "--universe", "lifecycle",
                                "--lifecycle-evidence", str(self.evidence), "--outdir", str(self.root / "output")]), \
                patch.object(build, "SecEdgarClient"), patch.object(build, "HistoricalMacroClient"), \
                patch.object(build, "write_dataset_outputs"), \
                patch.object(build, "collect_benchmark_history", return_value=SimpleNamespace(observations=[object()], errors=[object()])) as collect:
            self.assertEqual(build.main(), 1)
            provider = collect.call_args.args[1].providers[0]
            self.assertIsInstance(provider, LifecycleEvidencePriceClient)


if __name__ == "__main__":
    unittest.main()
