"""Temporal calibration/holdout protocol for historical score observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from statistics import mean
from typing import Iterable

from .config import CALIBRATION, CalibrationAssumptions
from .historical_calibration import (
    HistoricalCalibrationObservation,
    HistoricalCalibrationSummary,
    evaluate_historical_outcomes,
    spearman_correlation,
)


@dataclass(frozen=True)
class SegmentOutcomeSummary:
    split: str
    dimension: str
    segment: str
    observations: int
    usable_observations: int
    distinct_tickers: int
    average_score: float | None
    average_excess_return: float | None
    excess_return_hit_rate: float | None
    average_max_drawdown: float | None
    spearman_score_to_excess_return: float


@dataclass(frozen=True)
class OutOfSampleValidationReport:
    validation_start_date: date
    calibration_observations: tuple[HistoricalCalibrationObservation, ...]
    validation_observations: tuple[HistoricalCalibrationObservation, ...]
    embargoed_observations: tuple[HistoricalCalibrationObservation, ...]
    calibration_summary: HistoricalCalibrationSummary
    validation_summary: HistoricalCalibrationSummary
    segments: tuple[SegmentOutcomeSummary, ...]
    lifecycle_calibration_tickers: int
    adverse_lifecycle_calibration_tickers: int
    warnings: tuple[str, ...]
    is_ready_for_recalibration: bool


def evaluate_out_of_sample_validation(
    observations: Iterable[HistoricalCalibrationObservation],
    assumptions: CalibrationAssumptions = CALIBRATION,
) -> OutOfSampleValidationReport:
    all_observations = tuple(observations)
    cutoff = date(assumptions.validation_start_year, 1, 1)
    calibration, validation, embargoed = split_temporal_observations(
        all_observations,
        cutoff,
    )
    calibration_assumptions = replace(
        assumptions,
        minimum_historical_observations=assumptions.minimum_calibration_observations,
    )
    validation_assumptions = replace(
        assumptions,
        minimum_historical_observations=assumptions.minimum_validation_observations,
    )
    calibration_summary = evaluate_historical_outcomes(
        calibration,
        calibration_assumptions,
    )
    validation_summary = evaluate_historical_outcomes(
        validation,
        validation_assumptions,
    )
    segments = tuple(
        [
            *_segment_summaries("calibracao", calibration),
            *_segment_summaries("validacao", validation),
        ]
    )
    lifecycle_calibration_tickers = len(
        {item.ticker for item in calibration if item.lifecycle_event_type}
    )
    adverse_lifecycle_calibration_tickers = len(
        {
            item.ticker
            for item in calibration
            if item.lifecycle_event_type == "cancelled_zero"
        }
    )

    warnings: list[str] = []
    if len(all_observations) < assumptions.minimum_historical_observations:
        warnings.append(
            f"Amostra total insuficiente: {len(all_observations)} de "
            f"{assumptions.minimum_historical_observations} observacoes."
        )
    warnings.extend(
        f"Calibracao: {warning}" for warning in calibration_summary.warnings
    )
    warnings.extend(
        f"Validacao: {warning}" for warning in validation_summary.warnings
    )
    warnings.extend(
        _group_coverage_warnings(
            all_observations,
            calibration,
            validation,
            assumptions,
        )
    )
    if (
        lifecycle_calibration_tickers
        < assumptions.minimum_lifecycle_tickers_in_calibration
    ):
        warnings.append(
            "Calibracao sem cobertura suficiente de empresas retiradas da bolsa: "
            f"{lifecycle_calibration_tickers} tickers; minimo "
            f"{assumptions.minimum_lifecycle_tickers_in_calibration}."
        )
    if (
        adverse_lifecycle_calibration_tickers
        < assumptions.minimum_adverse_lifecycle_tickers_in_calibration
    ):
        warnings.append(
            "Calibracao sem casos adversos de cancelamento ou perda total: "
            f"{adverse_lifecycle_calibration_tickers} tickers; minimo "
            f"{assumptions.minimum_adverse_lifecycle_tickers_in_calibration}."
        )
    return OutOfSampleValidationReport(
        validation_start_date=cutoff,
        calibration_observations=calibration,
        validation_observations=validation,
        embargoed_observations=embargoed,
        calibration_summary=calibration_summary,
        validation_summary=validation_summary,
        segments=segments,
        lifecycle_calibration_tickers=lifecycle_calibration_tickers,
        adverse_lifecycle_calibration_tickers=(
            adverse_lifecycle_calibration_tickers
        ),
        warnings=tuple(dict.fromkeys(warnings)),
        is_ready_for_recalibration=not warnings,
    )


def split_temporal_observations(
    observations: Iterable[HistoricalCalibrationObservation],
    validation_start_date: date,
) -> tuple[
    tuple[HistoricalCalibrationObservation, ...],
    tuple[HistoricalCalibrationObservation, ...],
    tuple[HistoricalCalibrationObservation, ...],
]:
    calibration: list[HistoricalCalibrationObservation] = []
    validation: list[HistoricalCalibrationObservation] = []
    embargoed: list[HistoricalCalibrationObservation] = []
    for observation in observations:
        if (
            observation.price_end_date is not None
            and observation.price_end_date < validation_start_date
        ):
            calibration.append(observation)
        elif observation.as_of >= validation_start_date:
            validation.append(observation)
        else:
            embargoed.append(observation)
    key = lambda item: (item.as_of, item.ticker)
    return (
        tuple(sorted(calibration, key=key)),
        tuple(sorted(validation, key=key)),
        tuple(sorted(embargoed, key=key)),
    )


def out_of_sample_payload(report: OutOfSampleValidationReport) -> dict[str, object]:
    return {
        "validation_start_date": report.validation_start_date.isoformat(),
        "calibration_observations": len(report.calibration_observations),
        "validation_observations": len(report.validation_observations),
        "embargoed_observations": len(report.embargoed_observations),
        "calibration": _historical_summary_payload(report.calibration_summary),
        "validation": _historical_summary_payload(report.validation_summary),
        "segments": [asdict(segment) for segment in report.segments],
        "lifecycle_calibration_tickers": report.lifecycle_calibration_tickers,
        "adverse_lifecycle_calibration_tickers": (
            report.adverse_lifecycle_calibration_tickers
        ),
        "warnings": list(report.warnings),
        "is_ready_for_recalibration": report.is_ready_for_recalibration,
    }


def render_out_of_sample_markdown(report: OutOfSampleValidationReport) -> str:
    calibration = report.calibration_summary
    validation = report.validation_summary
    lines = [
        "# Validacao temporal fora da amostra",
        "",
        f"- Inicio do holdout: {report.validation_start_date}",
        f"- Calibracao: {len(report.calibration_observations)} observacoes",
        f"- Validacao: {len(report.validation_observations)} observacoes",
        f"- Embargo temporal: {len(report.embargoed_observations)} observacoes",
        f"- Tickers retirados da bolsa na calibracao: {report.lifecycle_calibration_tickers}",
        "- Casos de cancelamento/perda total na calibracao: "
        f"{report.adverse_lifecycle_calibration_tickers}",
        f"- Pronto para recalibrar: {'sim' if report.is_ready_for_recalibration else 'nao'}",
        "",
        "O holdout nao deve ser usado para escolher pesos, travas ou limites. "
        "Ele serve apenas para testar uma configuracao definida na calibracao.",
        "",
        "## Resultado geral",
        "| Amostra | Total | Utilizaveis | Cobertura | Point-in-time | Spearman | Monotonicidade |",
        "|---|---:|---:|---:|---:|---:|---:|",
        _summary_row("Calibracao", calibration),
        _summary_row("Validacao", validation),
        "",
        "## Resultado por grupo",
        "| Amostra | Grupo | N | Utilizaveis | Tickers | Score medio | Excesso medio | Acerto | Drawdown medio | Spearman |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(
        _segment_row(segment)
        for segment in report.segments
        if segment.dimension == "benchmark_group"
    )
    lines.extend(
        [
            "",
            "## Resultado por recomendacao",
            "| Amostra | Recomendacao | N | Utilizaveis | Tickers | Score medio | Excesso medio | Acerto | Drawdown medio |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    lines.extend(
        _recommendation_row(segment)
        for segment in report.segments
        if segment.dimension == "recommendation"
    )
    lines.extend(
        [
            "",
            "## Resultado por permanencia no mercado",
            "| Amostra | Status | N | Utilizaveis | Tickers | Score medio | Excesso medio | Acerto | Drawdown medio |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    lines.extend(
        _recommendation_row(segment)
        for segment in report.segments
        if segment.dimension == "universe_status"
    )
    lines.extend(["", "## Alertas"])
    if report.warnings:
        lines.extend(f"- {warning}" for warning in report.warnings)
    else:
        lines.append("- Todos os controles minimos foram atendidos.")
    return "\n".join(lines)


def _segment_summaries(
    split: str,
    observations: tuple[HistoricalCalibrationObservation, ...],
) -> list[SegmentOutcomeSummary]:
    summaries: list[SegmentOutcomeSummary] = []
    for dimension, selector in (
        ("benchmark_group", lambda item: item.benchmark_group or item.company_type),
        ("recommendation", lambda item: item.recommendation),
        ("universe_status", lambda item: item.universe_status or "active"),
    ):
        grouped: dict[str, list[HistoricalCalibrationObservation]] = {}
        for observation in observations:
            grouped.setdefault(str(selector(observation) or "nao_informado"), []).append(
                observation
            )
        for segment, items in sorted(grouped.items()):
            usable = [
                item
                for item in items
                if item.has_complete_outcome and item.is_point_in_time_valid
            ]
            excess = [float(item.excess_return) for item in usable]
            summaries.append(
                SegmentOutcomeSummary(
                    split=split,
                    dimension=dimension,
                    segment=segment,
                    observations=len(items),
                    usable_observations=len(usable),
                    distinct_tickers=len({item.ticker for item in usable}),
                    average_score=_mean_or_none([item.total_score for item in usable]),
                    average_excess_return=_mean_or_none(excess),
                    excess_return_hit_rate=(
                        sum(value > 0.0 for value in excess) / len(excess)
                        if excess
                        else None
                    ),
                    average_max_drawdown=_mean_or_none(
                        [float(item.max_drawdown) for item in usable]
                    ),
                    spearman_score_to_excess_return=spearman_correlation(
                        [item.total_score for item in usable],
                        excess,
                    ),
                )
            )
    return summaries


def _group_coverage_warnings(
    all_observations: tuple[HistoricalCalibrationObservation, ...],
    calibration: tuple[HistoricalCalibrationObservation, ...],
    validation: tuple[HistoricalCalibrationObservation, ...],
    assumptions: CalibrationAssumptions,
) -> list[str]:
    groups = sorted(
        {
            item.benchmark_group or item.company_type
            for item in all_observations
            if item.benchmark_group or item.company_type
        }
    )
    warnings: list[str] = []
    for split_name, split in (("Calibracao", calibration), ("Validacao", validation)):
        for group in groups:
            usable = [
                item
                for item in split
                if (item.benchmark_group or item.company_type) == group
                and item.has_complete_outcome
                and item.is_point_in_time_valid
            ]
            distinct_tickers = len({item.ticker for item in usable})
            if len(usable) < assumptions.minimum_observations_per_group_per_split:
                warnings.append(
                    f"{split_name}/{group}: {len(usable)} observacoes utilizaveis; "
                    f"minimo {assumptions.minimum_observations_per_group_per_split}."
                )
            if distinct_tickers < assumptions.minimum_distinct_tickers_per_group_per_split:
                warnings.append(
                    f"{split_name}/{group}: {distinct_tickers} tickers distintos; "
                    f"minimo {assumptions.minimum_distinct_tickers_per_group_per_split}."
                )
    return warnings


def _historical_summary_payload(summary: HistoricalCalibrationSummary) -> dict[str, object]:
    return {
        "observations": len(summary.observations),
        "usable_observations": summary.usable_observations,
        "outcome_coverage": summary.outcome_coverage,
        "point_in_time_ratio": summary.point_in_time_ratio,
        "spearman_score_to_excess_return": summary.spearman_score_to_excess_return,
        "monotonic_bucket_ratio": summary.monotonic_bucket_ratio,
        "warnings": list(summary.warnings),
        "is_ready": summary.is_ready_for_weight_changes,
    }


def _summary_row(label: str, summary: HistoricalCalibrationSummary) -> str:
    return (
        f"| {label} | {len(summary.observations)} | {summary.usable_observations} | "
        f"{summary.outcome_coverage:.1%} | {summary.point_in_time_ratio:.1%} | "
        f"{summary.spearman_score_to_excess_return:.3f} | "
        f"{summary.monotonic_bucket_ratio:.1%} |"
    )


def _segment_row(segment: SegmentOutcomeSummary) -> str:
    return (
        f"| {segment.split.title()} | {segment.segment} | {segment.observations} | "
        f"{segment.usable_observations} | {segment.distinct_tickers} | "
        f"{_number(segment.average_score)} | {_percent(segment.average_excess_return)} | "
        f"{_percent(segment.excess_return_hit_rate)} | "
        f"{_percent(segment.average_max_drawdown)} | "
        f"{segment.spearman_score_to_excess_return:.3f} |"
    )


def _recommendation_row(segment: SegmentOutcomeSummary) -> str:
    return (
        f"| {segment.split.title()} | {segment.segment} | {segment.observations} | "
        f"{segment.usable_observations} | {segment.distinct_tickers} | "
        f"{_number(segment.average_score)} | {_percent(segment.average_excess_return)} | "
        f"{_percent(segment.excess_return_hit_rate)} | "
        f"{_percent(segment.average_max_drawdown)} |"
    )


def _mean_or_none(values: list[float]) -> float | None:
    return mean(values) if values else None


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


__all__ = [
    "OutOfSampleValidationReport",
    "SegmentOutcomeSummary",
    "evaluate_out_of_sample_validation",
    "out_of_sample_payload",
    "render_out_of_sample_markdown",
    "split_temporal_observations",
]
