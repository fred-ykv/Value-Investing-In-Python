"""Run the controlled-data regression suite without live financial services."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import sys
import unittest


class NetworkGuard:
    """Record and reject Python socket activity, even if a client catches it."""

    EVENTS = frozenset({
        "socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
        "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg",
    })

    def __init__(self):
        self.attempts: list[str] = []

    def __call__(self, event: str, args: tuple) -> None:
        if event in self.EVENTS:
            self.attempts.append(event)
            raise RuntimeError("Rede bloqueada nos testes: use dados controlados ou mocks.")


def run_tests(suite: unittest.TestSuite | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    guard = NetworkGuard()
    # Audit hooks are process-wide; this runner is intended for a fresh process.
    sys.addaudithook(guard)
    if suite is None:
        suite = unittest.defaultTestLoader.discover(
            start_dir=str(root / "tests"), top_level_dir=str(root)
        )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = (
        result.wasSuccessful()
        and result.testsRun > 0
        and not result.skipped
        and not result.expectedFailures
        and not guard.attempts
    )
    summary = (
        "## Testes de regressao offline\n\n"
        f"- Python: {platform.python_version()}\n"
        f"- Resultado: {'APROVADO' if passed else 'REPROVADO'}\n"
        f"- Testes executados: {result.testsRun}\n"
        f"- Falhas: {len(result.failures)}\n"
        f"- Erros: {len(result.errors)}\n"
        f"- Ignorados: {len(result.skipped)}\n"
        f"- Falhas esperadas: {len(result.expectedFailures)}\n"
        f"- Sucessos inesperados: {len(result.unexpectedSuccesses)}\n"
        f"- Tentativas de rede bloqueadas: {len(guard.attempts)}\n\n"
        "Esta verificacao testa o software com dados controlados. Nao valida "
        "cotacoes atuais, disponibilidade dos provedores ou desempenho financeiro.\n"
    )
    print(summary, flush=True)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as output:
            output.write(summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run_tests())
