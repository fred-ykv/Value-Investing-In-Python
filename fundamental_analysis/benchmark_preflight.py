"""Unified, fail-closed coverage preflight for the historical benchmark."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .benchmark_universe import HISTORICAL_BENCHMARK_CASES, BenchmarkCase
from .experiment_manifest import load_experiment_manifest


@dataclass(frozen=True)
class CoverageRow:
    ticker: str
    cik: str
    grupo: str
    setor: str
    benchmark: str
    status_universo: str
    preco_disponivel: bool
    fundamentos_disponiveis: bool
    macro_disponivel: bool
    reconciliacao_economica: bool
    elegivel: bool
    motivos: tuple[str, ...]


def _read_json(path: str | Path) -> Mapping[str, Any]:
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as bundle:
            names = [name for name in bundle.namelist() if name.endswith("manifest.json")]
            if len(names) != 1:
                raise ValueError(f"Manifesto ausente ou ambiguo em {path}")
            return json.loads(bundle.read(names[0]).decode("utf-8"))
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _observation_index(path: str | Path | None) -> dict[str, Mapping[str, str]]:
    if not path:
        return {}
    source = Path(path)
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as bundle:
            names = [name for name in bundle.namelist() if name.endswith("historical_observations.csv")]
            if len(names) != 1:
                raise ValueError(f"historical_observations.csv ausente ou ambiguo em {source}")
            raw = bundle.read(names[0]).decode("utf-8")
    else:
        raw = source.read_text(encoding="utf-8")
    result: dict[str, Mapping[str, str]] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        ticker = (row.get("ticker") or "").strip().upper()
        if ticker:
            result[ticker] = row
    return result


def build_preflight(
    manifest_path: str | Path | None = None,
    lifecycle_evidence: str | Path | None = None,
    historical_observations: str | Path | None = None,
    cases: Iterable[BenchmarkCase] = HISTORICAL_BENCHMARK_CASES,
) -> dict[str, Any]:
    manifest = load_experiment_manifest(manifest_path) if manifest_path else load_experiment_manifest()
    lifecycle_manifest = _read_json(lifecycle_evidence) if lifecycle_evidence else {}
    lifecycle = {str(row["ticker"]).upper(): row for row in lifecycle_manifest.get("coverage", [])}
    observations = _observation_index(historical_observations)
    price_capture_ok = bool(lifecycle_manifest.get("capture_complete") and lifecycle_manifest.get("coverage_passed"))
    economic_ok = bool(lifecycle_manifest.get("economic_reconciliation_passed"))
    rows: list[CoverageRow] = []
    mapping = manifest["benchmarks"]["group_mapping"]
    for case in cases:
        ticker = case.ticker.upper()
        historical = observations.get(ticker, {})
        life = lifecycle.get(ticker, {})
        is_lifecycle = case.universe_status != "active"
        price = bool(life.get("is_ready") and price_capture_ok) if is_lifecycle else bool(historical.get("price_start_date") and historical.get("price_end_date") and historical.get("price_source"))
        fundamentals = historical.get("point_in_time_validated") == "True" and historical.get("analysis_input_validated") == "True"
        macro = historical.get("macro_point_in_time_validated") == "True"
        reconciliation = economic_ok if is_lifecycle else historical.get("analysis_input_validated") == "True"
        reasons: list[str] = []
        if not price: reasons.append("precos historicos ausentes ou nao aprovados")
        if not fundamentals: reasons.append("fundamentos point-in-time ausentes")
        if not macro: reasons.append("macro point-in-time ausente")
        if is_lifecycle and not reconciliation: reasons.append("reconciliacao economica lifecycle pendente")
        rows.append(CoverageRow(ticker, case.cik, case.benchmark_group, case.sector_bucket, mapping.get(case.benchmark_group, "SPY"), case.universe_status, price, fundamentals, macro, reconciliation, not reasons, tuple(reasons)))
    expected = int(manifest["universe"]["expected_total_companies"])
    group_counts = {group: sum(row.grupo == group for row in rows) for group in manifest["universe"]["groups"]}
    group_ok = all(group_counts.get(group) == spec["expected_count"] for group, spec in manifest["universe"]["groups"].items())
    eligible = sum(row.elegivel for row in rows)
    blocking = []
    if len(rows) != expected: blocking.append(f"universo esperado: {expected}; observado: {len(rows)}")
    if not group_ok: blocking.append("cobertura de grupos diverge do manifesto")
    if eligible != expected: blocking.append(f"empresas elegiveis: {eligible}/{expected}")
    return {"manifest_version": manifest["manifest_version"], "experiment_id": manifest["experiment_id"], "status": "blocked" if blocking else "ready", "expected_companies": expected, "observed_companies": len(rows), "eligible_companies": eligible, "group_counts": group_counts, "group_counts_match_manifest": group_ok, "rows": [asdict(row) for row in rows], "blocking_reasons": blocking}


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = ["# Preflight unificado do benchmark", "", f"**Status:** `{result['status']}`", f"**Empresas elegiveis:** {result['eligible_companies']}/{result['expected_companies']}", "", "| Ticker | Grupo | Benchmark | Preco | Fundamentos | Macro | Lifecycle | Status | Motivo |", "|---|---|---|---:|---:|---:|---:|---|---|"]
    for row in result["rows"]:
        checks = ["sim" if row[key] else "nao" for key in ("preco_disponivel", "fundamentos_disponiveis", "macro_disponivel", "reconciliacao_economica")]
        lines.append(f"| {row['ticker']} | {row['grupo']} | {row['benchmark']} | {checks[0]} | {checks[1]} | {checks[2]} | {checks[3]} | {'aprovado' if row['elegivel'] else 'bloqueado'} | {'; '.join(row['motivos']) or '-'} |")
    if result["blocking_reasons"]:
        lines += ["", "## Bloqueios", ""] + [f"- {reason}" for reason in result["blocking_reasons"]]
    return "\n".join(lines) + "\n"

