"""Export full Tiingo evidence for review before admitting delisted outcomes."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from fundamental_analysis.historical_archive import canonical_json, code_fingerprints, sha256
from fundamental_analysis.historical_price_readiness import (
    audit_historical_price_coverage,
    render_historical_price_readiness_markdown,
)
from fundamental_analysis.institutional_prices import TiingoHistoricalPriceClient


class EvidenceTiingoClient(TiingoHistoricalPriceClient):
    """Record decoded responses, including fields unused by the price adapter."""

    def __init__(self, directory, *, api_token=None, json_getter=None):
        super().__init__(api_token=api_token, json_getter=json_getter)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        (self.directory / "responses").mkdir()
        self.responses: list[dict] = []

    def _get_json(self, url):
        record = {"url": url, "captured_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            payload = super()._get_json(url)
            data = canonical_json(payload, sort_keys=False)
            if self.api_token and self.api_token.encode("utf-8") in data:
                raise ValueError("Resposta contem credencial; conteudo nao arquivado.")
            digest = sha256(data)
            relative = f"responses/{digest}.json"
            (self.directory / relative).write_bytes(data)
            record.update(path=relative, sha256=digest, bytes=len(data), status="captured")
        except Exception as exc:
            record.update(status="failed", error_type=type(exc).__name__)
            # Upstream errors can contain request details; never export them.
            raise RuntimeError(f"Falha ao coletar resposta Tiingo ({type(exc).__name__}).") from None
        finally:
            self.responses.append(record)
        return payload


def evidence_code_fingerprints():
    return {
        **code_fingerprints(),
        "collect_lifecycle_evidence.py": sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
    }


def collect_lifecycle_evidence(directory, *, api_token=None, json_getter=None):
    code_before = evidence_code_fingerprints()
    client = EvidenceTiingoClient(directory, api_token=api_token, json_getter=json_getter)
    directory = client.directory
    coverage = audit_historical_price_coverage(client, provider_name="Tiingo EOD")
    # Metadata validation errors may quote provider text. Redact the configured
    # token before writing diagnostics, even though no request header is saved.
    if client.api_token:
        coverage = replace(coverage, rows=tuple(
            replace(row, error=row.error.replace(client.api_token, "[redacted]"))
            for row in coverage.rows
        ))
    rows_written = 0
    with (directory / "normalized_prices.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("security_id", "issuer_cik", "ticker", "date", "adjusted_close", "raw_close", "source"))
        for row in coverage.rows:
            if not row.is_ready:
                continue
            series = client.fetch_series(row.ticker, row.expected_start, row.expected_end)
            for point in series.points:
                writer.writerow((series.security_id, series.issuer_cik, series.ticker,
                                 point.day.isoformat(), point.adjusted_close, point.raw_close, series.source))
                rows_written += 1
    code_unchanged = evidence_code_fingerprints() == code_before
    complete = coverage.is_ready and code_unchanged
    markdown = render_historical_price_readiness_markdown(coverage).replace(
        "- Pronto para benchmark:", "- Cobertura tecnica aprovada:"
    ).replace("| Pregoes |", "| Registros do provedor |")
    markdown += (
        "\n\n## Reconciliacao economica pendente\n\n"
        "Cobertura de datas e identidade nao confirma que cada linha seja um negocio executavel.\n"
        "Conferir volume, ajustes, splits, dividendos e suspensao de negociacao nas respostas completas.\n"
        "Os campos sao preservados quando fornecidos pelo Tiingo; ausencia nao e preenchida com zero.\n"
        "Datas e valores terminais permanecem sujeitos a revisao SEC.\n"
        "Este pacote nao autoriza integrar a amostra ao benchmark nem recalibrar pesos.\n"
    )
    (directory / "coverage_report.md").write_text(markdown, encoding="utf-8")
    report = {
        "schema_version": 1,
        "state": "complete" if complete else "incomplete",
        "capture_complete": complete,
        "coverage_passed": coverage.is_ready,
        "code_unchanged_during_capture": code_unchanged,
        "code_sha256": code_before,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Tiingo EOD",
        "representation": "decoded_json_responses_and_normalized_csv",
        "economic_reconciliation_passed": False,
        "eligible_for_benchmark": False,
        "financial_parameters_changed": False,
        "rows_written": rows_written,
        "coverage": [asdict(row) for row in coverage.rows],
        "responses": client.responses,
        "files_sha256": {name: sha256((directory / name).read_bytes()) for name in (
            "normalized_prices.csv", "coverage_report.md",
        )},
        "limitations": [
            "Pacote de evidencia para revisao; nao e um resultado de benchmark nem um arquivo de replay.",
            "JSON decodificado preserva os campos retornados, mas nao representa os bytes HTTP originais.",
            "A cobertura esperada reproduz o cadastro atual e nao certifica a data do ultimo negocio.",
            "Hashes nao sao assinatura do fornecedor. Respeitar licenciamento e manter os dados privados.",
        ],
    }
    data = canonical_json(report)
    (directory / "manifest.json").write_bytes(data)
    (directory / "manifest.sha256").write_text(sha256(data) + "\n", encoding="ascii")
    return report


def main():
    parser = argparse.ArgumentParser(description="Exportar evidencia completa de precos para revisao de eventos terminais.")
    parser.add_argument("--outdir", required=True, help="Pasta nova; pacotes existentes nunca sao sobrescritos.")
    args = parser.parse_args()
    try:
        report = collect_lifecycle_evidence(args.outdir)
    except FileExistsError:
        raise SystemExit("A pasta ja existe. Escolha outra pasta para preservar a coleta anterior.") from None
    except ValueError:
        raise SystemExit("Verifique a configuracao TIINGO_API_KEY e o cadastro do provedor.") from None
    print("Coleta de evidencia: " + ("COMPLETA" if report["capture_complete"] else "INCOMPLETA"))
    print(f"Series com cobertura aprovada: {sum(row['is_ready'] for row in report['coverage'])}/{len(report['coverage'])}")
    print(f"Registros exportados: {report['rows_written']}")
    print("Reconciliacao economica: PENDENTE. Este pacote ainda nao libera o benchmark.")
    return 0 if report["capture_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
