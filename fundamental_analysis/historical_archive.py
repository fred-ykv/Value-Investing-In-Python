"""Content-addressed inputs for historical collection and fail-closed replay."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from .historical_macro import HistoricalMacroClient
from .historical_prices import PricePoint, PriceSeries
from .sec_edgar import SecEdgarClient


OUTPUT_FILES = (
    "historical_observations.csv", "collection_manifest.json",
    "collection_report.md", "historical_calibration.md",
    "out_of_sample_validation.md", "out_of_sample_validation.json",
)


class ArchiveError(ValueError):
    """An archive is incomplete, incompatible, or failed its integrity check."""


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Tipo nao serializavel no arquivo historico: {type(value).__name__}")


def canonical_json(value, *, sort_keys: bool = True) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=sort_keys, separators=(",", ":"),
        allow_nan=False, default=_json_default,
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_fingerprints() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    files = list((root / "fundamental_analysis").rglob("*.py"))
    files.extend(root / name for name in (
        "build_historical_dataset.py", "replay_historical_dataset.py",
    ))
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes().replace(b"\r\n", b"\n"))
        for path in sorted(files)
    }


class ArchiveWriter:
    """Create a new archive; an existing directory is never overwritten."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        (self.directory / "objects").mkdir()
        self._entries: dict[tuple[str, str], dict] = {}
        self._payloads: dict[tuple[str, str], object] = {}
        self._finished = False
        self._code = code_fingerprints()

    def capture(self, kind: str, key: str, loader: Callable[[], object]):
        if self._finished:
            raise ArchiveError("Arquivo historico ja foi finalizado.")
        identity = (kind, key)
        if identity not in self._entries:
            # Preserve provider mapping order: parsers may use it to break ties.
            data = canonical_json(loader(), sort_keys=False)
            digest = sha256(data)
            path = self.directory / "objects" / f"{digest}.json"
            if not path.exists():
                path.write_bytes(data)
            self._entries[identity] = {
                "kind": kind, "key": key, "sha256": digest,
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            self._payloads[identity] = json.loads(data)
        # Clients get only the frozen value, even if an upstream cache changes.
        return self._payloads[identity]

    def finish(self, run: dict, output_directory: str | Path) -> str:
        if self._code != code_fingerprints():
            raise ArchiveError("Codigo mudou durante a coleta; arquivo nao finalizado.")
        for name in OUTPUT_FILES:
            path = Path(output_directory) / name
            self.capture("expected_output", name, lambda path=path: path.read_text(encoding="utf-8"))
        payload = {
            "schema_version": 1, "state": "complete",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version, "code_sha256": self._code,
            "run": run, "entries": list(self._entries.values()),
            "limitations": [
                "Hashes detectam alteracoes acidentais; nao sao assinatura digital.",
                "Precos ajustados sao a versao entregue pelo provedor na coleta; nao uma vintage certificada do provedor.",
                "Reproducibilidade nao certifica a tese financeira nem autoriza recalibrar pesos.",
            ],
        }
        data = canonical_json(payload)
        digest = sha256(data)
        (self.directory / "manifest.json").write_bytes(data)
        (self.directory / "manifest.sha256").write_text(digest + "\n", encoding="ascii")
        self._finished = True
        return digest


class ArchiveReader:
    """Load verified objects only; never consult a cache or network provider."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory).resolve()
        self.failures: list[str] = []
        self.accessed: set[tuple[str, str]] = set()
        self._payloads: dict[tuple[str, str], object] = {}
        data = self._read_file("manifest.json")
        digest = self._read_file("manifest.sha256").decode("ascii").strip()
        if sha256(data) != digest:
            raise ArchiveError("Integridade do manifesto historico reprovada.")
        self.digest = digest
        self.manifest = json.loads(data)
        if self.manifest.get("schema_version") != 1 or self.manifest.get("state") != "complete":
            raise ArchiveError("Arquivo historico incompleto ou versao nao suportada.")
        self._entries = {}
        for entry in self.manifest["entries"]:
            identity = (entry["kind"], entry["key"])
            digest = entry["sha256"]
            if identity in self._entries or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ArchiveError("Entrada duplicada ou hash invalido no manifesto.")
            self._entries[identity] = entry
            content = self._read_file(f"objects/{digest}.json")
            if sha256(content) != digest:
                raise ArchiveError(f"Integridade reprovada: {identity[0]} {identity[1]}")
            self._payloads[identity] = json.loads(content)
        if not self._entries:
            raise ArchiveError("Arquivo historico sem entradas.")

    def _read_file(self, name: str) -> bytes:
        path = (self.directory / name).resolve()
        if not path.is_relative_to(self.directory):
            raise ArchiveError("Caminho fora do arquivo historico.")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ArchiveError(f"Arquivo historico ausente ou ilegivel: {name}") from exc

    def load(self, kind: str, key: str):
        identity = (kind, key)
        if identity not in self._payloads:
            message = f"Entrada historica nao arquivada: {kind} {key}"
            self.failures.append(message)
            raise ArchiveError(message)
        self.accessed.add(identity)
        return self._payloads[identity]

    def verify_code(self) -> None:
        if self.manifest["code_sha256"] != code_fingerprints():
            raise ArchiveError("Codigo diferente do usado na coleta. Use a mesma versao para replay.")

    def compare_outputs(self, directory: str | Path) -> dict[str, bool]:
        matches = {
            name: (Path(directory) / name).read_text(encoding="utf-8")
            == self.load("expected_output", name)
            for name in OUTPUT_FILES
        }
        if self.failures or self.accessed != set(self._entries):
            raise ArchiveError("Replay nao consumiu exatamente as entradas arquivadas.")
        return matches


class RecordingSecClient(SecEdgarClient):
    def __init__(self, archive: ArchiveWriter, **kwargs):
        self.archive = archive
        super().__init__(**kwargs)

    def _load_json(self, url: str, cache_name: str):
        return self.archive.capture(
            "sec_json", url, lambda: super(RecordingSecClient, self)._load_json(url, cache_name),
        )


class ReplaySecClient(SecEdgarClient):
    def __init__(self, archive: ArchiveReader, **kwargs):
        self.archive = archive
        super().__init__(json_getter=lambda url: archive.load("sec_json", url), **kwargs)

    def _load_json(self, url: str, cache_name: str):
        return self.archive.load("sec_json", url)


class RecordingMacroClient(HistoricalMacroClient):
    def __init__(self, archive: ArchiveWriter, **kwargs):
        self.archive = archive
        super().__init__(**kwargs)

    def _load_text(self, url: str, cache_name: str) -> str:
        return self.archive.capture(
            "macro_text", url, lambda: super(RecordingMacroClient, self)._load_text(url, cache_name),
        )


class ReplayMacroClient(HistoricalMacroClient):
    def __init__(self, archive: ArchiveReader, **kwargs):
        self.archive = archive
        super().__init__(**kwargs)

    def _load_text(self, url: str, cache_name: str) -> str:
        return self.archive.load("macro_text", url)


def _price_key(ticker: str, start: date, end: date) -> str:
    return canonical_json([ticker.upper().strip(), start, end]).decode("utf-8")


def _price_series(payload: dict) -> PriceSeries:
    return PriceSeries(
        ticker=payload["ticker"], source=payload["source"],
        security_id=payload["security_id"], issuer_cik=payload["issuer_cik"],
        points=tuple(PricePoint(date.fromisoformat(p["day"]), p["adjusted_close"], p["raw_close"]) for p in payload["points"]),
    )


class RecordingPriceClient:
    def __init__(self, archive: ArchiveWriter, provider):
        self.archive = archive
        self.provider = provider

    def fetch_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        payload = self.archive.capture(
            "price_series", _price_key(ticker, start, end),
            lambda: asdict(self.provider.fetch_series(ticker, start, end)),
        )
        return _price_series(payload)


class ReplayPriceClient:
    def __init__(self, archive: ArchiveReader):
        self.archive = archive

    def fetch_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        return _price_series(self.archive.load("price_series", _price_key(ticker, start, end)))
