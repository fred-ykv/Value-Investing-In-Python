"""Batch calibration helpers for score diagnostics."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Callable, Iterable, Mapping

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


def row_from_result(result: AnalysisResult) -> CalibrationRow:
    return CalibrationRow(
        ticker=result.ticker.upper(),
        company_type=result.company_type,
        recommendation=result.score.recommendation,
        total_score=result.score.total_score,
        dimension_scores={name: dim.score for name, dim in result.score.dimensions.items()},
        dimension_confidence={name: dim.confidence for name, dim in result.score.dimensions.items()},
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
                "company_type",
                "recommendation",
                "total_score",
                "error",
                *[f"{name}_score" for name in dimensions],
                *[f"{name}_confidence" for name in dimensions],
            ],
        )
        writer.writeheader()
        for row in rows:
            payload = {
                "ticker": row.ticker,
                "company_type": row.company_type,
                "recommendation": row.recommendation,
                "total_score": f"{row.total_score:.4f}",
                "error": row.error,
            }
            for name in dimensions:
                payload[f"{name}_score"] = _fmt(row.dimension_scores.get(name))
                payload[f"{name}_confidence"] = _fmt(row.dimension_confidence.get(name))
            writer.writerow(payload)


def render_calibration_markdown(rows: Iterable[CalibrationRow]) -> str:
    rows = list(rows)
    summary = summarize_calibration(rows)
    lines = [
        "# Calibracao do Score",
        "",
        f"- Total de tickers: {summary['total']}",
        f"- Sucessos: {summary['successful']}",
        f"- Erros: {summary['errors']}",
        f"- Score medio: {float(summary['average_score']):.3f}",
        f"- Recomendacoes: {summary['recommendations']}",
        "",
        "## Score medio por tipo",
    ]
    for company_type, score in dict(summary["average_score_by_type"]).items():
        lines.append(f"- {company_type}: {float(score):.3f}")
    lines.extend(
        [
            "",
            "## Tickers",
            "| Ticker | Tipo | Recomendacao | Score | Dimensao mais fraca | Erro |",
            "|---|---|---|---:|---|---|",
        ]
    )
    weakest = dict(summary["weakest_dimensions"])
    for row in rows:
        lines.append(
            f"| {row.ticker} | {row.company_type} | {row.recommendation} | "
            f"{row.total_score:.3f} | {weakest.get(row.ticker, '-')} | {row.error} |"
        )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"
