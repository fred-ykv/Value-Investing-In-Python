"""Exercise the exact Colab cells with fake Git, Tiingo and download services."""

from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch
import zipfile

from collect_lifecycle_evidence import collect_lifecycle_evidence, evidence_code_fingerprints
from tests.test_lifecycle_evidence import response_fixture


ROOT = Path(__file__).resolve().parents[1]


class LifecycleNotebookTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.session = Path(temp.name) / "session"
        self.session.mkdir()
        notebook = json.loads((ROOT / "COLAB_LIFECYCLE_EVIDENCE.ipynb").read_text(encoding="utf-8"))
        self.cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
        self.assertEqual(len(self.cells), 4)
        for cell in self.cells:
            self.assertIsNone(cell["execution_count"])
            self.assertEqual(cell["outputs"], [])
        self.namespace = {}
        self.download = Mock()

    def execute(self, *, partial=False, corrupt_before_download=False):
        def getter(url):
            if partial and "/MDLA/prices?" in url:
                raise RuntimeError("test upstream error")
            return response_fixture(url)

        def run(command, **kwargs):
            if command[:2] == ["git", "clone"]:
                target = Path(command[-1])
                target.mkdir()
                shutil.copy2(ROOT / "collect_lifecycle_evidence.py", target)
            elif command[0] == "git" and command[3] == "archive":
                path = next(value.split("=", 1)[1] for value in command if value.startswith("--output="))
                with zipfile.ZipFile(path, "w") as archive:
                    for name in evidence_code_fingerprints():
                        archive.write(ROOT / name, name)
            else:
                self.assertEqual(command[0], sys.executable)
                self.assertEqual(command[2], "--outdir")
                self.assertNotIn("NOTEBOOK_TEST_TOKEN", " ".join(command))
                report = collect_lifecycle_evidence(command[3], api_token=kwargs["env"]["TIINGO_API_KEY"], json_getter=getter)
                return subprocess.CompletedProcess(command, 0 if report["capture_complete"] else 1, stdout="fixture", stderr="")
            return subprocess.CompletedProcess(command, 0)

        google = ModuleType("google")
        colab = ModuleType("google.colab")
        colab.userdata = Mock()
        colab.userdata.get.return_value = "NOTEBOOK_TEST_TOKEN"
        colab.files = Mock(download=self.download)
        google.colab = colab
        ipython = ModuleType("IPython")
        display = ModuleType("IPython.display")
        display.Markdown = lambda value: value
        display.display = Mock()
        ipython.display = display
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {
                "google": google, "google.colab": colab,
                "IPython": ipython, "IPython.display": display,
            }))
            stack.enter_context(patch("tempfile.mkdtemp", return_value=str(self.session)))
            stack.enter_context(patch("subprocess.run", side_effect=run))
            stack.enter_context(patch("subprocess.check_output", return_value="fixture_commit\n"))
            stack.enter_context(redirect_stdout(io.StringIO()))
            for index, cell in enumerate(self.cells):
                if index == 3 and corrupt_before_download:
                    (self.namespace["evidence"] / "normalized_prices.csv").write_text("changed", encoding="utf-8")
                exec(compile("".join(cell["source"]), f"colab_cell_{index + 1}", "exec"), self.namespace)

    def test_complete_notebook_exports_verified_private_bundle_without_token(self):
        self.execute()
        archive = self.namespace["archive"]
        self.download.assert_called_once_with(str(archive))
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            self.assertIn("lifecycle_evidence/source.zip", names)
            self.assertIn("lifecycle_evidence/evidence/normalized_prices.csv", names)
            metadata = json.loads(package.read("lifecycle_evidence/package.json"))
            self.assertTrue(metadata["capture_complete"])
            self.assertFalse(metadata["eligible_for_benchmark"])
            self.assertEqual(metadata["source_commit"], "fixture_commit")
            self.assertEqual(metadata["collection_exit_code"], 0)
            for name in names:
                self.assertNotIn(".git/", name)
                self.assertNotIn(b"NOTEBOOK_TEST_TOKEN", package.read(name))
        self.assertNotIn("token", self.namespace)
        self.assertNotIn("child_env", self.namespace)

    def test_partial_collection_can_be_downloaded_only_as_diagnostic_evidence(self):
        self.execute(partial=True)
        self.download.assert_called_once()
        self.assertEqual(self.namespace["collection_exit_code"], 1)
        self.assertFalse(self.namespace["report"]["capture_complete"])
        self.assertFalse(self.namespace["report"]["eligible_for_benchmark"])

    def test_changed_prices_block_download(self):
        with self.assertRaisesRegex(RuntimeError, "Arquivo alterado"):
            self.execute(corrupt_before_download=True)
        self.download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
