"""Recompute a captured historical collection with network and native escapes blocked."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
import sys


class OfflineGuard:
    """Process-wide Python audit guard; not an operating-system sandbox."""

    EVENTS = frozenset({
        "socket.__new__", "socket.connect", "socket.getaddrinfo",
        "socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto",
        "socket.sendmsg", "subprocess.Popen", "os.system", "os.posix_spawn",
        "os.exec", "os.spawn", "ctypes.dlopen",
    })

    def __init__(self):
        self.attempts: list[str] = []

    def __call__(self, event: str, args: tuple) -> None:
        if event in self.EVENTS:
            self.attempts.append(event)
            raise RuntimeError("Rede, processos externos e bibliotecas nativas bloqueados no replay.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproduzir uma coleta historica sem acesso a provedores.")
    parser.add_argument("archive", help="Pacote criado por --archive-dir na coleta original.")
    parser.add_argument("--outdir", required=True, help="Diretorio NOVO para a reproducao.")
    args = parser.parse_args()
    guard = OfflineGuard()
    sys.addaudithook(guard)
    # Allow python -I -S: only this checkout is added, never site-packages.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_historical_dataset import write_dataset_outputs
    from fundamental_analysis.benchmark_universe import BenchmarkCase, HistoricalLifecycleEvent
    from fundamental_analysis.historical_archive import (
        ArchiveReader, ReplayMacroClient, ReplayPriceClient, ReplaySecClient,
    )
    from fundamental_analysis.point_in_time_collection import collect_benchmark_history

    outdir = Path(args.outdir)
    # Refuse to write inside the input archive, including through symlinks.
    if outdir.resolve().is_relative_to(Path(args.archive).resolve()):
        raise SystemExit("O diretorio de replay deve ficar fora do arquivo de entrada.")
    outdir.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "network_attempts": [], "financial_parameters_changed": False}
    try:
        archive = ArchiveReader(args.archive)
        archive.verify_code()
        run = archive.manifest["run"]
        cases = []
        for saved in run["cases"]:
            saved = dict(saved)
            if saved["lifecycle_event"] is not None:
                event = dict(saved["lifecycle_event"])
                event["effective_date"] = date.fromisoformat(event["effective_date"])
                saved["lifecycle_event"] = HistoricalLifecycleEvent(**event)
            cases.append(BenchmarkCase(**saved))
        dataset = collect_benchmark_history(
            ReplaySecClient(archive), ReplayPriceClient(archive), ReplayMacroClient(archive),
            cases=cases, start_year=run["start_year"], end_year=run["end_year"],
            max_filings_per_company=run["max_filings_per_company"],
            outcomes_available_through=date.fromisoformat(run["outcomes_available_through"]),
        )
        write_dataset_outputs(dataset, outdir, run["validation_start_year"])
        matches = archive.compare_outputs(outdir)
        archive.verify_code()
        report.update({
            "archive_manifest_sha256": archive.digest,
            "observations": len(dataset.observations), "errors": len(dataset.errors),
            "outputs_identical": matches, "input_objects": len(archive.accessed),
            "python_capture": archive.manifest["python"], "python_replay": sys.version,
            "passed": bool(dataset.observations) and not dataset.errors and all(matches.values()) and not guard.attempts,
        })
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["network_attempts"] = guard.attempts
    if guard.attempts:
        report["passed"] = False
    (outdir / "replay_verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8",
    )
    print("\nReplay offline: " + ("APROVADO" if report["passed"] else "REPROVADO"))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
