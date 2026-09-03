import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CIRunnerTests(unittest.TestCase):
    def run_sample(self, sample, *, summary_path=""):
        code = (
            "import unittest\n"
            "from scripts.run_ci_tests import run_tests\n"
            + textwrap.dedent(sample)
            + "\nraise SystemExit(run_tests(suite))\n"
        )
        return subprocess.run(
            [sys.executable, "-S", "-c", code],
            cwd=ROOT,
            env={**os.environ, "GITHUB_STEP_SUMMARY": summary_path, "PYTHONUTF8": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )

    def test_success_writes_job_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            summary_path = Path(directory) / "summary.md"
            result = self.run_sample("""
                suite = unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
            """, summary_path=str(summary_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("Resultado: APROVADO", summary)
            self.assertIn("Testes executados: 1", summary)

    def test_empty_suite_fails_closed(self):
        result = self.run_sample("suite = unittest.TestSuite()")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Testes executados: 0", result.stdout)

    def test_failed_and_errored_tests_return_failure(self):
        for exception in ("AssertionError", "ValueError"):
            with self.subTest(exception=exception):
                result = self.run_sample(f"""
                    def broken():
                        raise {exception}('deliberate failure')
                    suite = unittest.TestSuite([unittest.FunctionTestCase(broken)])
                """)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Resultado: REPROVADO", result.stdout)

    def test_skip_and_expected_failure_cannot_produce_green_check(self):
        for decorator, body in (
            ("unittest.skip('deliberate skip')", "pass"),
            ("unittest.expectedFailure", "self.fail('deliberate failure')"),
        ):
            with self.subTest(decorator=decorator):
                result = self.run_sample(f"""
                    class Sample(unittest.TestCase):
                        @{decorator}
                        def test_case(self):
                            {body}
                    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Sample)
                """)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Resultado: REPROVADO", result.stdout)

    def test_caught_network_errors_still_fail_job(self):
        for operation in (
            "socket.getaddrinfo('example.invalid', 443)",
            "socket.socket().connect(('127.0.0.1', 1))",
        ):
            with self.subTest(operation=operation):
                result = self.run_sample(f"""
                    import socket
                    def catches_network_error():
                        try:
                            {operation}
                        except RuntimeError:
                            pass
                    suite = unittest.TestSuite([
                        unittest.FunctionTestCase(catches_network_error)
                    ])
                """)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Tentativas de rede bloqueadas: 1", result.stdout)


if __name__ == "__main__":
    unittest.main()
