import json
from pathlib import Path
import unittest


class ColabNotebookTests(unittest.TestCase):
    def test_colab_runner_notebook_has_required_cells(self):
        notebook_path = Path("COLAB_ANALYSIS_RUNNER.ipynb")

        payload = json.loads(notebook_path.read_text(encoding="utf-8"))
        sources = "\n".join("".join(cell.get("source", [])) for cell in payload["cells"])

        self.assertEqual(payload["nbformat"], 4)
        self.assertIn("!git clone https://github.com/fred-ykv/Value-Investing-In-Python.git", sources)
        self.assertIn("!pip install -r requirements.txt", sources)
        self.assertIn("run_colab_analysis", sources)
        self.assertIn("default_ticker=\"MLI\"", sources)
        self.assertIn("files.download(path)", sources)


if __name__ == "__main__":
    unittest.main()
