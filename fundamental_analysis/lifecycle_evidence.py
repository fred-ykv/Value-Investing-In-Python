"""Read a complete PR58 evidence package without executing its bundled code."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import stat
import zipfile
from dataclasses import replace
from pathlib import Path, PurePosixPath

from .institutional_prices import TIINGO_LIFECYCLE_MAPPINGS, TiingoHistoricalPriceClient
from .price_eligibility import PriceEligibilityError


def _require(condition, message):
    if not condition:
        raise PriceEligibilityError(message)


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Chave JSON duplicada no pacote")
            result[key] = value
        return result

    def invalid_constant(value):
        raise PriceEligibilityError(f"Constante JSON invalida: {value}")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _safe_name(name):
    _require(isinstance(name, str) and bool(name) and not PurePosixPath(name).is_absolute()
             and ".." not in PurePosixPath(name).parts and ":" not in name and "\\" not in name,
             "Caminho inseguro no pacote de precos")


class LifecycleEvidencePriceClient:
    """Hash-checked CSV/JSON reconciliation; this does not certify a benchmark."""

    def __init__(self, path):
        path = Path(path)
        try:
            if path.is_dir():
                root = path.resolve()

                def read(name):
                    _safe_name(name)
                    target = (root / name).resolve(strict=True)
                    _require(target.is_relative_to(root) and target.stat().st_size < 50_000_000,
                             "Arquivo de evidencia fora da pasta ou muito grande")
                    return target.read_bytes()

                self._load(read)
            else:
                with zipfile.ZipFile(path) as bundle:
                    entries = bundle.infolist()
                    _require(sum(e.file_size for e in entries) < 100_000_000, "ZIP de evidencia muito grande")
                    _require(len({e.filename.casefold() for e in entries}) == len(entries), "Caminhos duplicados no ZIP")
                    for entry in entries:
                        _safe_name(entry.filename)
                        _require(not stat.S_ISLNK(entry.external_attr >> 16) and not entry.flag_bits & 1,
                                 "ZIP com link simbolico ou criptografia")
                    manifests = [e.filename for e in entries if e.filename.endswith("/evidence/manifest.json")
                                 or e.filename in {"manifest.json", "evidence/manifest.json"}]
                    _require(len(manifests) == 1, "Manifesto de evidencia ausente ou ambiguo no ZIP")
                    prefix = manifests[0][:-len("manifest.json")]

                    def read(name):
                        _safe_name(name)
                        return bundle.read(prefix + name)

                    self._load(read)
        except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as exc:
            if isinstance(exc, PriceEligibilityError):
                raise
            raise PriceEligibilityError(f"Pacote de precos invalido ({type(exc).__name__})") from exc

    def _load(self, read):
        manifest_bytes = read("manifest.json")
        self.manifest_sha256 = _digest(manifest_bytes)
        _require(read("manifest.sha256").decode("ascii").strip() == self.manifest_sha256,
                 "Hash do manifesto de precos diverge")
        manifest = _json(manifest_bytes)
        _require(manifest["schema_version"] == 1 and manifest["state"] == "complete"
                 and all(manifest[key] is True for key in (
                     "capture_complete", "coverage_passed", "code_unchanged_during_capture")),
                 "Manifesto de precos incompleto; nao usar fallback")
        _require(manifest["provider"] == "Tiingo EOD", "Provedor do pacote nao suportado")
        _require(set(manifest["files_sha256"]) == {"normalized_prices.csv", "coverage_report.md"},
                 "Manifesto sem os arquivos de evidencia esperados")
        files = {}
        for name, digest in manifest["files_sha256"].items():
            files[name] = read(name)
            _require(_digest(files[name]) == digest, f"Hash divergente: {name}")
        responses = {}
        _require(len(manifest["responses"]) == 2 * len(TIINGO_LIFECYCLE_MAPPINGS), "Respostas Tiingo incompletas")
        for record in manifest["responses"]:
            data = read(record["path"])
            _require(record["status"] == "captured" and _digest(data) == record["sha256"]
                     and len(data) == record["bytes"], "Resposta Tiingo adulterada ou incompleta")
            _require(record["url"] not in responses, "URL Tiingo duplicada")
            responses[record["url"]] = _json(data)
        accessed = set()

        def getter(url):
            _require(url in responses, "Resposta Tiingo exigida ausente")
            accessed.add(url)
            return responses[url]

        client = TiingoHistoricalPriceClient(json_getter=getter)
        self._series = {}
        for mapping in TIINGO_LIFECYCLE_MAPPINGS:
            series = client.fetch_series(mapping.canonical_ticker, mapping.expected_first_price_date,
                                         mapping.expected_last_price_date)
            self._series[series.ticker] = replace(series, input_evidence_sha256=self.manifest_sha256)
        _require(accessed == set(responses), "Resposta Tiingo inesperada no manifesto")
        coverage = manifest["coverage"]
        _require(len(coverage) == len(self._series)
                 and {row["ticker"] for row in coverage} == set(self._series), "Cobertura do manifesto incompleta")
        for row in coverage:
            series = self._series[row["ticker"]]
            _require(row["is_ready"] is True and row["issuer_cik"] == series.issuer_cik
                     and row["observations"] == len(series.points), "Cobertura diverge das respostas")
        expected = {(s.ticker, p.day.isoformat()): (s, p) for s in self._series.values() for p in s.points}
        seen = set()
        for row in csv.DictReader(io.StringIO(files["normalized_prices.csv"].decode("utf-8"))):
            key = row["ticker"], row["date"]
            _require(key in expected and key not in seen, "Data/ticker CSV inesperado ou duplicado")
            seen.add(key)
            series, point = expected[key]
            _require(row["security_id"] == series.security_id and row["issuer_cik"] == series.issuer_cik
                     and row["source"] == series.source
                     and float(row["raw_close"]) == point.raw_close
                     and float(row["adjusted_close"]) == point.adjusted_close,
                     "CSV nao reconcilia com os precos/identidades originais")
        _require(seen == set(expected) and len(seen) == manifest["rows_written"], "CSV de evidencia incompleto")

    def fetch_series(self, ticker, start, end):
        ticker = ticker.upper().strip()
        if ticker not in self._series:
            raise LookupError(f"Ticker {ticker} nao pertence ao pacote lifecycle")
        return self._series[ticker].between(start, end)


def reconcile_csv_evidence(path, series):
    _require(path.name == "normalized_prices.csv", "CSV lifecycle exige normalized_prices.csv e manifesto do pacote completo")
    client = LifecycleEvidencePriceClient(path.parent)
    _require(set(series) == set(client._series), "CSV lifecycle fora do pacote completo")
    return {ticker: replace(client._series[ticker], source=loaded.source) for ticker, loaded in series.items()}
