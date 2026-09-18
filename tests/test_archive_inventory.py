import tempfile
import unittest
from pathlib import Path
from fundamental_analysis.archive_inventory import inspect_archive
from fundamental_analysis.historical_archive import ArchiveWriter, OUTPUT_FILES


class ArchiveInventoryTests(unittest.TestCase):
    def make_archive(self, root, points):
        writer = ArchiveWriter(root / "archive")
        writer.capture("price_series", '["MLI","2020-01-01","2020-01-03"]', lambda: {
            "ticker": "MLI", "points": points})
        output = root / "output"
        output.mkdir()
        for name in OUTPUT_FILES:
            (output / name).write_text("fixture", encoding="utf-8")
        writer.finish({"cases": []}, output)
        return writer.directory

    def test_valid_inventory_is_not_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_archive(self.make_archive(Path(tmp), [
                {"day": "2020-01-02", "raw_close": 10, "adjusted_close": 9}]))
        self.assertEqual(len(result["price_windows"]), 1)
        self.assertFalse(result["benchmark_authorized"])

    def test_duplicate_dates_block_window(self):
        point = {"day": "2020-01-02", "raw_close": 10, "adjusted_close": 9}
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_archive(self.make_archive(Path(tmp), [point, point]))
        self.assertTrue(result["issues"])
        self.assertEqual(result["price_windows"], [])

    def test_tampered_object_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_archive(Path(tmp), [])
            next((path / "objects").glob("*.json")).write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                inspect_archive(path)

