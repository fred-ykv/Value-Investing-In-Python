"""Batch calibration helpers for score diagnostics."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Callable, Iterable, Mapping

from .benchmark_universe import BenchmarkCase, DEFAULT_BENCHMARK_CASES, validate_benchmark_cases
from .config import CALIBRATION, SCORE, CalibrationAssumptions
from .main import AnalysisResult, analyze_ticker_live


@dataclass(frozen=True)
class CalibrationRow:
    ticker: str
    company_type: str
    recommendation: str
    total_score: float
    dimension_scores: Mapping[str, float]
    dimension_confidence: Mapping[str, float]
    error: str = ""
    benchmark_group: str = ""
    sector_bucket: str = ""

    @property
    def valuation_score(self) -> float:
        return self.dimension_scores.get("valuation", 0.0)

    @property
    def quality_score(self) -> float:
        return self.dimension_scores.get("quality", 0.0)

    @property
    def data_confidence(self) -> float:
        return self.dimension_scores.get("data_confidence", 0.0)

    @property
    def valuation_gate(self) -> bool:
        return (
            self.total_score >= SCORE.buy_threshold
            and self.recommendation == "Observar"
            and self.valuation_score < SCORE.min_valuation_score_for_buy
        )

    @property
    def group_key(self) -> str:
        return self.benchmark_group or self.company_type or "sem_grupo"


@dataclass(frozen=True)
class CalibrationSummary:
    rows: list[CalibrationRow]
    recommendation_counts: dict[str, int]
    average_score: float
    min_score: float
    max_score: float
    valuation_gate_count: int


@dataclass(frozen=True)
class CalibrationGroupSummary:
    group: str
    count: int
    average_score: float
    median_score: float
    p25_score: float
    p75_score: float
    min_score: float
    max_score: float
    score_spread: float
    recommendation_counts: dict[str, int]
    valuation_gate_count: int
    valuation_gate_rate: float
    average_data_confidence: float
    low_confidence_count: int
    dimension_averages: dict[str, float]


@dataclass(frozen=True)
class CalibrationDiagnostics:
    rows: list[CalibrationRow]
    total: int
    successful: int
    errors: int
    error_rate: float
    recommendation_counts: dict[str, int]
    dominant_recommendation: str
    recommendation_concentration: float
    average_score: float
    min_score: float
    max_score: float
    score_spread: float
    valuation_gate_count: int
    valuation_gate_rate: float
    average_data_confidence: float
    group_summaries: dict[str, CalibrationGroupSummary]
    warnings: tuple[str, ...]
    is_ready_for_historical_validation: bool


def run_calibration(
    tickers: Iterable[str],
    analyzer: Callable[[str], AnalysisResult] = analyze_ticker_live,
) -> list[CalibrationRow]:
    rows: list[CalibrationRow] = []
    for raw_ticker in tickers:
        ticker = raw_ticker.upper().strip()
        if not ticker:
            continue
        try:
            result = analyzer(ticker)
            rows.append(row_from_result(result))
        except Exception as exc:
            rows.append(
                CalibrationRow(
                    ticker=ticker,
                    company_type="erro",
                    recommendation="Erro",
                    total_score=0.0,
                    dimension_scores={},
                    dimension_confidence={},
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return rows


def run_benchmark_calibration(
    cases: Iterable[BenchmarkCase] = DEFAULT_BENCHMARK_CASES,
    analyzer: Callable[[str], AnalysisResult] = analyze_ticker_live,
    assumptions: CalibrationAssumptions = CALIBRATION,
) -> CalibrationDiagnostics:
    cases = tuple(cases)
    validate_benchmark_cases(cases)
    rows: list[CalibrationRow] = []
    for case in cases:
        ticker = case.ticker.upper().strip()
        try:
            result = analyzer(ticker)
            rows.append(
                row_from_result(
                    result,
                    benchmark_group=case.benchmark_group,
                    sector_bucket=case.sector_bucket,
                )
            )
        except Exception as exc:
            rows.append(
                CalibrationRow(
                    ticker=ticker,
                    company_type="erro",
                    recommendation="Erro",
                    total_score=0.0,
                    dimension_scores={},
                    dimension_confidence={},
                    error=f"{type(exc).__name__}: {exc}",
                    benchmark_group=case.benchmark_group,
                    sector_bucket=case.sector_bucket,
                )
            )
    return build_calibration_diagnostics(rows, assumptions)


def row_from_result(
    result: AnalysisResult,
    benchmark_group: str = "",
    sector_bucket: str = "",
) -> CalibrationRow:
    return CalibrationRow(
        ticker=result.ticker.upper(),
        company_type=result.company_type,
        recommendation=result.score.recommendation,
        total_score=result.score.total_score,
        dimension_scores={name: dim.score for name, dim in result.score.dimensions.items()},
        dimension_confidence={name: dim.confidence for name, dim in result.score.dimensions.items()},
        benchmark_group=benchmark_group,
        sector_bucket=sector_bucket,
    )


def build_calibration_summary(results: Iterable[AnalysisResult]) -> CalibrationSummary:
    return calibration_summary_from_rows(row_from_result(result) for result in results)


def calibration_summary_from_rows(rows: Iterable[CalibrationRow]) -> CalibrationSummary:
    rows = list(rows)
    successful = [row for row in rows if not row.error]
    scores = [row.total_score for row in successful]
    return CalibrationSummary(
        rows=rows,
        recommendation_counts=dict(Counter(row.recommendation for row in successful)),
        average_score=mean(scores) if scores else 0.0,
        min_score=min(scores) if scores else 0.0,
        max_score=max(scores) if scores else 0.0,
        valuation_gate_count=sum(1 for row in successful if row.valuation_gate),
    )


def build_calibration_diagnostics(
    rows: Iterable[CalibrationRow],
    assumptions: CalibrationAssumptions = CALIBRATION,
) -> CalibrationDiagnostics:
    rows = list(rows)
    successful = [row for row in rows if not row.error]
    errors = len(rows) - len(successful)
    scores = [row.total_score for row in successful]
    recommendation_counts = dict(Counter(row.recommendation for row in successful))
    dominant_recommendation = ""
    recommendation_concentration = 0.0
    if recommendation_counts:
        dominant_recommendation, dominant_count = max(
            recommendation_counts.items(), key=lambda item: (item[1], item[0])
        )
        recommendation_concentration = dominant_count / len(successful)

    group_rows: dict[str, list[CalibrationRow]] = defaultdict(list)
    for row in successful:
        group_rows[row.group_key].append(row)
    all_groups = sorted({row.group_key for row in rows})
    group_summaries = {
        group: _build_group_summary(group, group_rows.get(group, []), assumptions)
        for group in all_groups
    }

    error_rate = errors / len(rows) if rows else 0.0
    min_score = min(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0
    score_spread = max_score - min_score if scores else 0.0
    gate_count = sum(1 for row in successful if row.valuation_gate)
    average_confidence = mean(row.data_confidence for row in successful) if successful else 0.0

    warnings: list[str] = []
    if len(successful) < assumptions.minimum_total_sample:
        warnings.append(
            f"Amostra valida insuficiente: {len(successful)} de {assumptions.minimum_total_sample} casos minimos."
        )
    for group, group_summary in group_summaries.items():
        if group_summary.count < assumptions.minimum_sample_per_group:
            warnings.append(
                f"Grupo {group} tem {group_summary.count} casos validos; minimo exigido: "
                f"{assumptions.minimum_sample_per_group}."
            )
    if error_rate > assumptions.maximum_error_rate:
        warnings.append(
            f"Taxa de erro de {error_rate:.1%} supera o limite de {assumptions.maximum_error_rate:.1%}."
        )
    if recommendation_concentration > assumptions.maximum_recommendation_concentration:
        warnings.append(
            f"A recomendacao {dominant_recommendation} concentra {recommendation_concentration:.1%} dos casos; "
            f"limite: {assumptions.maximum_recommendation_concentration:.1%}."
        )
    if score_spread < assumptions.minimum_score_spread:
        warnings.append(
            f"Dispersao do score de {score_spread:.3f} e menor que o minimo de "
            f"{assumptions.minimum_score_spread:.3f}."
        )
    if average_confidence < assumptions.minimum_data_confidence:
        warnings.append(
            f"Confianca media dos dados de {average_confidence:.1%} e menor que o minimo de "
            f"{assumptions.minimum_data_confidence:.1%}."
        )

    return CalibrationDiagnostics(
        rows=rows,
        total=len(rows),
        successful=len(successful),
        errors=errors,
        error_rate=error_rate,
        recommendation_counts=recommendation_counts,
        dominant_recommendation=dominant_recommendation,
        recommendation_concentration=recommendation_concentration,
        average_score=mean(scores) if scores else 0.0,
        min_score=min_score,
        max_score=max_score,
        score_spread=score_spread,
        valuation_gate_count=gate_count,
        valuation_gate_rate=gate_count / len(successful) if successful else 0.0,
        average_data_confidence=average_confidence,
        group_summaries=group_summaries,
        warnings=tuple(warnings),
        is_ready_for_historical_validation=not warnings,
    )


def _build_group_summary(
    group: str,
    rows: list[CalibrationRow],
    assumptions: CalibrationAssumptions,
) -> CalibrationGroupSummary:
    scores = sorted(row.total_score for row in rows)
    dimensions = sorted({name for row in rows for name in row.dimension_scores})
    gate_count = sum(1 for row in rows if row.valuation_gate)
    return CalibrationGroupSummary(
        group=group,
        count=len(rows),
        average_score=mean(scores) if scores else 0.0,
        median_score=_quantile(scores, 0.50),
        p25_score=_quantile(scores, 0.25),
        p75_score=_quantile(scores, 0.75),
        min_score=min(scores) if scores else 0.0,
        max_score=max(scores) if scores else 0.0,
        score_spread=(max(scores) - min(scores)) if scores else 0.0,
        recommendation_counts=dict(Counter(row.recommendation for row in rows)),
        valuation_gate_count=gate_count,
        valuation_gate_rate=gate_count / len(rows) if rows else 0.0,
        average_data_confidence=mean(row.data_confidence for row in rows) if rows else 0.0,
        low_confidence_count=sum(
            1 for row in rows if row.data_confidence < assumptions.minimum_data_confidence
        ),
        dimension_averages={
            name: mean(row.dimension_scores.get(name, 0.0) for row in rows)
            for name in dimensions
        },
    )


def summarize_calibration(rows: Iterable[CalibrationRow]) -> dict[str, object]:
    rows = list(rows)
    successful = [row for row in rows if not row.error]
    by_type: dict[str, list[CalibrationRow]] = defaultdict(list)
    for row in successful:
        by_type[row.company_type].append(row)
    return {
        "total": len(rows),
        "successful": len(successful),
        "errors": len(rows) - len(successful),
        "recommendations": dict(Counter(row.recommendation for row in successful)),
        "average_score": mean([row.total_score for row in successful]) if successful else 0.0,
        "average_score_by_type": {
            company_type: mean([row.total_score for row in type_rows])
            for company_type, type_rows in by_type.items()
        },
        "weakest_dimensions": weakest_dimensions(successful),
        "valuation_gate_count": sum(1 for row in successful if row.valuation_gate),
    }


def weakest_dimensions(rows: Iterable[CalibrationRow]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        if not row.dimension_scores:
            continue
        result[row.ticker] = min(row.dimension_scores.items(), key=lambda item: item[1])[0]
    return result


def write_calibration_csv(rows: Iterable[CalibrationRow], path: str | Path) -> None:
    rows = list(rows)
    dimensions = sorted({name for row in rows for name in row.dimension_scores})
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ticker",
                "benchmark_group",
                "sector_bucket",
                "company_type",
                "recommendation",
                "total_score",
                "valuation_gate",
                "error",
                *[f"{name}_score" for name in dimensions],
                *[f"{name}_confidence" for name in dimensions],
            ],
        )
        writer.writeheader()
        for row in rows:
            payload = {
                "ticker": row.ticker,
                "benchmark_group": row.benchmark_group,
                "sector_bucket": row.sector_bucket,
                "company_type": row.company_type,
                "recommendation": row.recommendation,
                "total_score": f"{row.total_score:.4f}",
                "valuation_gate": "1" if row.valuation_gate else "0",
                "error": row.error,
            }
            for name in dimensions:
                payload[f"{name}_score"] = _fmt(row.dimension_scores.get(name))
                payload[f"{name}_confidence"] = _fmt(row.dimension_confidence.get(name))
            writer.writerow(payload)


def write_calibration_json(
    rows: Iterable[CalibrationRow],
    path: str | Path,
    assumptions: CalibrationAssumptions = CALIBRATION,
) -> None:
    diagnostics = build_calibration_diagnostics(rows, assumptions)
    payload = asdict(diagnostics)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_calibration_markdown(
    rows: Iterable[CalibrationRow],
    assumptions: CalibrationAssumptions = CALIBRATION,
) -> str:
    rows = list(rows)
    summary = summarize_calibration(rows)
    diagnostics = build_calibration_diagnostics(rows, assumptions)
    lines = [
        "# Calibracao do Score",
        "",
        f"- Total de tickers: {summary['total']}",
        f"- Sucessos: {summary['successful']}",
        f"- Erros: {summary['errors']}",
        f"- Score medio: {float(summary['average_score']):.3f}",
        f"- Recomendacoes: {summary['recommendations']}",
        f"- Casos bloqueados pela trava de valuation: {summary['valuation_gate_count']}",
        f"- Dispersao do score: {diagnostics.score_spread:.3f}",
        f"- Confianca media dos dados: {diagnostics.average_data_confidence:.1%}",
        f"- Concentracao da recomendacao dominante: {diagnostics.recommendation_concentration:.1%}",
        f"- Pronto para iniciar validacao historica: {'sim' if diagnostics.is_ready_for_historical_validation else 'nao'}",
        "",
        "## Alertas de validade",
    ]
    if diagnostics.warnings:
        lines.extend(f"- {warning}" for warning in diagnostics.warnings)
    else:
        lines.append("- Nenhum alerta de amostra, dispersao, concentracao ou cobertura.")
    lines.extend(
        [
            "",
            "## Distribuicao por grupo",
            "| Grupo | N | Media | P25 | Mediana | P75 | Dispersao | Confianca | Trava valuation | Recomendacoes |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for group, group_summary in diagnostics.group_summaries.items():
        lines.append(
            f"| {group} | {group_summary.count} | {group_summary.average_score:.3f} | "
            f"{group_summary.p25_score:.3f} | {group_summary.median_score:.3f} | "
            f"{group_summary.p75_score:.3f} | {group_summary.score_spread:.3f} | "
            f"{group_summary.average_data_confidence:.1%} | {group_summary.valuation_gate_rate:.1%} | "
            f"{group_summary.recommendation_counts} |"
        )
    lines.extend(
        [
            "",
            "## Tickers",
            "| Ticker | Grupo | Tipo inferido | Recomendacao | Score | Valuation | Qualidade | Confianca dados | Trava valuation | Dimensao mais fraca | Erro |",
            "|---|---|---|---|---:|---:|---:|---:|---|---|---|",
        ]
    )
    weakest = dict(summary["weakest_dimensions"])
    for row in rows:
        lines.append(
            f"| {row.ticker} | {row.group_key} | {row.company_type} | {row.recommendation} | "
            f"{row.total_score:.3f} | {row.valuation_score:.3f} | {row.quality_score:.3f} | "
            f"{row.data_confidence:.3f} | {'sim' if row.valuation_gate else 'nao'} | "
            f"{weakest.get(row.ticker, '-')} | {row.error} |"
        )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"


def _quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction

