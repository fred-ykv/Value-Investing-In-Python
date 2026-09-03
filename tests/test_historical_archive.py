import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from datetime import date, timedelta
from unittest.mock import patch

from build_historical_dataset import write_dataset_outputs
from fundamental_analysis.benchmark_universe import BenchmarkCase
from fundamental_analysis.historical_archive import (
    ArchiveError, ArchiveReader, ArchiveWriter, OUTPUT_FILES,
    RecordingMacroClient, RecordingPriceClient, RecordingSecClient,
    ReplayMacroClient, ReplayPriceClient, ReplaySecClient,
    canonical_json, sha256,
)
from fundamental_analysis.historical_prices import PricePoint, PriceSeries
from fundamental_analysis.point_in_time_collection import collect_benchmark_history
from tests.sec_fixtures import company_facts_fixture, ticker_map_fixture
from tests.test_historical_macro import erp_html


ROOT = Path(__file__).resolve().parents[1]


class Prices:
    def fetch_series(self, ticker, start, end):
        points = []
        day = start
        while day <= end:
            if day.weekday() < 5:
                elapsed = (day - date(2020, 1, 1)).days
                adjusted = 10 + elapsed * 0.01 + (elapsed % 7) * 0.005
                points.append(PricePoint(day, adjusted, adjusted * 2))
            day += timedelta(days=1)
        return PriceSeries(ticker, tuple(points), "fixture adjusted dividends and splits", "fixture-id", "0000001234")


class HistoricalArchiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def finish_dummy(self, writer):
        output = self.root / "expected"
        output.mkdir(exist_ok=True)
        for name in OUTPUT_FILES:
            (output / name).write_text("fixture\n", encoding="utf-8")
        writer.finish({}, output)
        return ArchiveReader(writer.directory)

    def test_prices_preserve_dates_adjustments_identity_and_source(self):
        writer = ArchiveWriter(self.root / "archive")
        provider = Prices()
        start, end = date(2024, 1, 1), date(2025, 3, 1)
        expected = provider.fetch_series("TEST", start, end)
        captured = RecordingPriceClient(writer, provider).fetch_series("TEST", start, end)
        reader = self.finish_dummy(writer)
        replay = ReplayPriceClient(reader).fetch_series("TEST", start, end)
        self.assertEqual(expected, captured)
        self.assertEqual(expected, replay)
        self.assertNotEqual(replay.points[0].raw_close, replay.points[0].adjusted_close)
        with self.assertRaises(ArchiveError):
            ReplayPriceClient(reader).fetch_series("TEST", start - timedelta(days=1), end)
        self.assertEqual(len(reader.failures), 1)

    def test_capture_freezes_first_response(self):
        writer = ArchiveWriter(self.root / "archive")
        self.assertEqual(writer.capture("sec_json", "url", lambda: {"v": 10}), {"v": 10})
        self.assertEqual(writer.capture("sec_json", "url", lambda: {"v": 99}), {"v": 10})

    def test_capture_preserves_provider_mapping_order(self):
        writer = ArchiveWriter(self.root / "archive")
        captured = writer.capture("sec_json", "url", lambda: {"z": 10, "a": 99})
        reader = self.finish_dummy(writer)
        self.assertEqual(list(captured), ["z", "a"])
        self.assertEqual(list(reader.load("sec_json", "url")), ["z", "a"])

    def test_existing_archive_is_not_overwritten(self):
        ArchiveWriter(self.root / "archive")
        with self.assertRaises(FileExistsError):
            ArchiveWriter(self.root / "archive")

    def test_nonfinite_prices_cannot_be_archived(self):
        writer = ArchiveWriter(self.root / "archive")
        with self.assertRaises(ValueError):
            writer.capture("price_series", "test", lambda: {"price": float("nan")})
        with self.assertRaises(ArchiveError):
            ArchiveReader(writer.directory)

    def test_missing_and_modified_objects_fail_before_replay(self):
        writer = ArchiveWriter(self.root / "archive")
        writer.capture("price_series", "test", lambda: {"price": 42})
        reader = self.finish_dummy(writer)
        entry = reader.manifest["entries"][0]
        path = writer.directory / "objects" / (entry["sha256"] + ".json")
        path.write_bytes(b'{"price":43}')
        with self.assertRaisesRegex(ArchiveError, "Integridade"):
            ArchiveReader(writer.directory)
        path.unlink()
        with self.assertRaisesRegex(ArchiveError, "ausente"):
            ArchiveReader(writer.directory)

    def test_manifest_corruption_and_path_injection_fail(self):
        writer = ArchiveWriter(self.root / "archive")
        reader = self.finish_dummy(writer)
        path = writer.directory / "manifest.json"
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ArchiveError, "Integridade"):
            ArchiveReader(writer.directory)
        payload = reader.manifest
        payload["entries"][0]["sha256"] = "../outside"
        changed = canonical_json(payload)
        path.write_bytes(changed)
        (writer.directory / "manifest.sha256").write_text(sha256(changed), encoding="ascii")
        with self.assertRaisesRegex(ArchiveError, "hash invalido"):
            ArchiveReader(writer.directory)

    def test_code_drift_and_partial_input_consumption_fail(self):
        writer = ArchiveWriter(self.root / "archive")
        writer.capture("sec_json", "unused", lambda: {"v": 1})
        reader = self.finish_dummy(writer)
        with patch("fundamental_analysis.historical_archive.code_fingerprints", return_value={}):
            with self.assertRaisesRegex(ArchiveError, "Codigo diferente"):
                reader.verify_code()
        with self.assertRaisesRegex(ArchiveError, "exatamente"):
            reader.compare_outputs(self.root / "expected")

    def test_changed_code_during_capture_prevents_finalization(self):
        writer = ArchiveWriter(self.root / "archive")
        with patch("fundamental_analysis.historical_archive.code_fingerprints", return_value={}):
            with self.assertRaisesRegex(ArchiveError, "mudou durante"):
                writer.finish({}, self.root)
        self.assertFalse((writer.directory / "manifest.json").exists())

    def test_output_difference_is_not_accepted(self):
        writer = ArchiveWriter(self.root / "archive")
        reader = self.finish_dummy(writer)
        (self.root / "expected" / "collection_manifest.json").write_text("changed", encoding="utf-8")
        self.assertFalse(all(reader.compare_outputs(self.root / "expected").values()))

    def test_replay_clients_never_read_live_caches_or_http(self):
        writer = ArchiveWriter(self.root / "archive")
        writer.capture("sec_json", "sec-url", lambda: {"frozen": True})
        writer.capture("macro_text", "macro-url", lambda: "frozen csv")
        reader = self.finish_dummy(writer)
        with patch("fundamental_analysis.sec_edgar.SecEdgarClient._request_json", side_effect=AssertionError("network")), patch("fundamental_analysis.historical_macro.HistoricalMacroClient._request_text", side_effect=AssertionError("network")):
            self.assertEqual(ReplaySecClient(reader)._load_json("sec-url", "any.json"), {"frozen": True})
            self.assertEqual(ReplayMacroClient(reader)._load_text("macro-url", "any.csv"), "frozen csv")
            with self.assertRaises(ArchiveError):
                ReplaySecClient(reader)._load_json("not-archived", "company_tickers.json")

    def make_collection(self):
        writer = ArchiveWriter(self.root / "archive")
        case = BenchmarkCase("TEST", "tradicionais_ciclicas", "industrial_machinery", "fixture")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else company_facts_fixture()

        def get_text(url):
            if "treasury" in url:
                return "Date,10 Yr\n02/15/2024,4.00\n"
            return erp_html()

        run = {
            "cases": [asdict(case)], "start_year": 2024, "end_year": 2024,
            "max_filings_per_company": 1, "outcomes_available_through": date(2026, 9, 3),
            "validation_start_year": 2022,
        }
        dataset = collect_benchmark_history(
            RecordingSecClient(writer, json_getter=get_json, cache_dir=self.root / "sec"),
            RecordingPriceClient(writer, Prices()),
            RecordingMacroClient(writer, text_getter=get_text, cache_dir=self.root / "macro"),
            cases=[case], start_year=2024, end_year=2024, max_filings_per_company=1,
            outcomes_available_through=run["outcomes_available_through"],
        )
        self.assertEqual(len(dataset.errors), 0)
        self.assertEqual(len(dataset.observations), 1)
        output = self.root / "capture"
        output.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            write_dataset_outputs(dataset, output, 2022)
        writer.finish(run, output)
        return writer.directory

    def run_replay(self, archive, outdir):
        env = {key: value for key, value in os.environ.items() if key not in {"SEC_USER_AGENT", "TIINGO_API_KEY", "PYTHONPATH"}}
        return subprocess.run(
            [sys.executable, "-I", "-S", str(ROOT / "replay_historical_dataset.py"), str(archive), "--outdir", str(outdir)],
            cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )

    def test_full_collection_replays_in_isolated_process_without_credentials(self):
        archive = self.make_collection()
        result = self.run_replay(archive, self.root / "replay")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        verification = json.loads((self.root / "replay" / "replay_verification.json").read_text(encoding="utf-8"))
        self.assertTrue(verification["passed"])
        self.assertEqual(verification["observations"], 1)
        self.assertEqual(verification["network_attempts"], [])
        self.assertTrue(all(verification["outputs_identical"].values()))
        before = json.loads((self.root / "capture" / "collection_manifest.json").read_text(encoding="utf-8"))
        after = json.loads((self.root / "replay" / "collection_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(before, after)

    def test_corrupted_archive_cli_fails_and_cannot_write_inside_archive(self):
        archive = self.make_collection()
        protected = self.run_replay(archive, archive / "overwrite")
        self.assertNotEqual(protected.returncode, 0)
        self.assertFalse((archive / "overwrite").exists())
        (archive / "manifest.sha256").write_text("0" * 64, encoding="ascii")
        result = self.run_replay(archive, self.root / "replay")
        self.assertNotEqual(result.returncode, 0)
        verification = json.loads((self.root / "replay" / "replay_verification.json").read_text(encoding="utf-8"))
        self.assertFalse(verification["passed"])

    def test_guard_counts_caught_network_and_native_escape_attempts(self):
        from replay_historical_dataset import OfflineGuard
        guard = OfflineGuard()
        for event in ("socket.connect", "subprocess.Popen", "ctypes.dlopen"):
            with self.assertRaises(RuntimeError):
                guard(event, ())
        self.assertEqual(len(guard.attempts), 3)
        code = "from replay_historical_dataset import OfflineGuard; import sys, socket; g=OfflineGuard(); sys.addaudithook(g)\ntry: socket.socket()\nexcept RuntimeError: pass\nassert g.attempts == ['socket.__new__']\n"
        result = subprocess.run([sys.executable, "-S", "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_caught_network_attempt_fails_even_with_identical_outputs(self):
        archive = self.make_collection()
        outdir = self.root / "replay"
        code = (
            "import build_historical_dataset as build, socket, sys; "
            "from replay_historical_dataset import main\n"
            "original = build.write_dataset_outputs\n"
            "def probe(*args):\n"
            "    try: socket.socket()\n"
            "    except RuntimeError: pass\n"
            "    return original(*args)\n"
            "build.write_dataset_outputs = probe\n"
            "raise SystemExit(main())\n"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", code, str(archive), "--outdir", str(outdir)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        verification = json.loads((outdir / "replay_verification.json").read_text(encoding="utf-8"))
        self.assertFalse(verification["passed"])
        self.assertEqual(verification["network_attempts"], ["socket.__new__"])
        self.assertTrue(all(verification["outputs_identical"].values()))


if __name__ == "__main__":
    unittest.main()
