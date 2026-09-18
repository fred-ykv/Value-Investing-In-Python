"""Validate the provenance contract for prepared portfolio inputs."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable, Mapping, Any


INPUT_KEYS = {"sessions", "signals", "bars", "events", "rules"}


def _is_hash(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def load_portfolio_attestation(
    path: str | Path,
    *,
    expected_experiment_id: str,
    expected_manifest_version: str,
    verified_archive_sha256: Iterable[str],
) -> Mapping[str, Any]:
    root = Path(path)
    document = root / "portfolio_attestation.json" if root.is_dir() else root
    sidecar = document.with_suffix(".sha256")
    raw = document.read_bytes()
    digest = sha256(raw).hexdigest()
    if sidecar.read_text(encoding="ascii").strip() != digest:
        raise ValueError("hash do atestado da carteira diverge do arquivo")
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("versao do atestado da carteira nao suportada")
    if payload.get("experiment_id") != expected_experiment_id:
        raise ValueError("experimento do atestado diverge do manifesto")
    if str(payload.get("manifest_version")) != str(expected_manifest_version):
        raise ValueError("versao do manifesto diverge do atestado")
    sources = payload.get("source_archive_sha256")
    expected_sources = sorted(set(verified_archive_sha256))
    if not isinstance(sources, list) or sources != sorted(set(sources)) or sources != expected_sources:
        raise ValueError("fontes do atestado divergem dos arquivos historicos verificados")
    hashes = payload.get("portfolio_input_hashes")
    if not isinstance(hashes, dict) or set(hashes) != INPUT_KEYS or not all(_is_hash(value) for value in hashes.values()):
        raise ValueError("hashes das entradas da carteira ausentes ou invalidos")
    if not _is_hash(payload.get("calendar_sessions_sha256")):
        raise ValueError("hash do calendario ausente ou invalido")
    return {**payload, "attestation_sha256": digest, "integrity_verified": True}

