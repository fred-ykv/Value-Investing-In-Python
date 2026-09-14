"""Load and validate the frozen historical experiment contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


MANIFEST_PATH = Path(__file__).with_name("EXPERIMENT_MANIFEST.json")


def load_experiment_manifest(path: str | Path = MANIFEST_PATH) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    errors = validate_experiment_manifest(manifest)
    if errors:
        raise ValueError("Manifesto experimental invalido: " + "; ".join(errors))
    return manifest


def validate_experiment_manifest(manifest: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ("manifest_version", "experiment_id", "universe", "data_and_time", "benchmarks", "costs", "metrics_and_gates")
    errors.extend(f"campo ausente: {key}" for key in required if key not in manifest)
    if manifest.get("model_policy", {}).get("weights_and_formulas_frozen") is not True:
        errors.append("pesos e formulas precisam estar congelados")
    if manifest.get("status") != "frozen_before_new_benchmark":
        errors.append("status precisa indicar congelamento anterior ao benchmark")
    universe = manifest.get("universe", {})
    if universe.get("expected_default_companies") != 40 or universe.get("expected_lifecycle_cases") != 10:
        errors.append("composicao esperada do universo deve ser 40 + 10 lifecycle")
    if manifest.get("costs", {}).get("primary_transaction_cost_bps_per_side") != 10:
        errors.append("custo primario deve ser 10 bps por lado")
    if manifest.get("model_policy", {}).get("primary_horizon_months") != 12:
        errors.append("horizonte primario deve ser 12 meses")
    if manifest.get("reproducibility", {}).get("offline_replay_required") is not True:
        errors.append("replay offline deve ser obrigatorio")
    return errors

