"""Preflight checks for survivorship-aware historical price providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .historical_prices import HistoricalPriceProvider
from .institutional_prices import (
    TIINGO_LIFECYCLE_MAPPINGS,
    TiingoSecurityMapping,
)


@dataclass(frozen=True)
class HistoricalPriceCoverageRow:
    ticker: str
    provider_ticker: str
    issuer_cik: str
    expected_start: date
    expected_end: date
    observed_start: date | None
    observed_end: date | None
    observations: int
    maximum_gap_days: int | None
    is_ready: bool
    error: str = ""


@dataclass(frozen=True)
class HistoricalPriceReadinessReport:
    provider: str
    rows: tuple[HistoricalPriceCoverageRow, ...]

    @property
    def is_ready(self) -> bool:
        return bool(self.rows) and all(row.is_ready for row in self.rows)


def audit_historical_price_coverage(
    provider: HistoricalPriceProvider,
    *,
    provider_name: str,
    mappings: Iterable[TiingoSecurityMapping] = TIINGO_LIFECYCLE_MAPPINGS,
    maximum_gap_days: int = 10,
    minimum_calendar_coverage_ratio: float = 0.45,
) -> HistoricalPriceReadinessReport:
    rows: list[HistoricalPriceCoverageRow] = []
    for mapping in mappings:
        try:
            series = provider.fetch_series(
                mapping.canonical_ticker,
                mapping.expected_first_price_date,
                mapping.expected_last_price_date,
            )
            points = series.points
            observed_start = points[0].day if points else None
            observed_end = points[-1].day if points else None
            gaps = [
                (current.day - previous.day).days
                for previous, current in zip(points, points[1:])
            ]
            observed_maximum_gap = max(gaps) if gaps else None
            calendar_days = (
                mapping.expected_last_price_date
                - mapping.expected_first_price_date
            ).days + 1
            minimum_observations = max(
                2,
                int(calendar_days * minimum_calendar_coverage_ratio),
            )
            errors: list[str] = []
            if series.issuer_cik != mapping.issuer_cik:
                errors.append(
                    f"CIK observado {series.issuer_cik or 'ausente'}"
                )
            if observed_start != mapping.expected_first_price_date:
                errors.append(f"inicio observado {observed_start}")
            if observed_end != mapping.expected_last_price_date:
                errors.append(f"fim observado {observed_end}")
            if len(points) < minimum_observations:
                errors.append(
                    f"apenas {len(points)} precos; minimo {minimum_observations}"
                )
            if (
                observed_maximum_gap is not None
                and observed_maximum_gap > maximum_gap_days
            ):
                errors.append(
                    f"lacuna maxima de {observed_maximum_gap} dias"
                )
            rows.append(
                HistoricalPriceCoverageRow(
                    ticker=mapping.canonical_ticker,
                    provider_ticker=mapping.provider_ticker,
                    issuer_cik=mapping.issuer_cik,
                    expected_start=mapping.expected_first_price_date,
                    expected_end=mapping.expected_last_price_date,
                    observed_start=observed_start,
                    observed_end=observed_end,
                    observations=len(points),
                    maximum_gap_days=observed_maximum_gap,
                    is_ready=not errors,
                    error="; ".join(errors),
                )
            )
        except Exception as exc:
            rows.append(
                HistoricalPriceCoverageRow(
                    ticker=mapping.canonical_ticker,
                    provider_ticker=mapping.provider_ticker,
                    issuer_cik=mapping.issuer_cik,
                    expected_start=mapping.expected_first_price_date,
                    expected_end=mapping.expected_last_price_date,
                    observed_start=None,
                    observed_end=None,
                    observations=0,
                    maximum_gap_days=None,
                    is_ready=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return HistoricalPriceReadinessReport(provider_name, tuple(rows))


def render_historical_price_readiness_markdown(
    report: HistoricalPriceReadinessReport,
) -> str:
    lines = [
        "# Preflight de precos historicos",
        "",
        f"- Provedor: {report.provider}",
        f"- Series aprovadas: {sum(row.is_ready for row in report.rows)}/{len(report.rows)}",
        f"- Pronto para benchmark: {'sim' if report.is_ready else 'nao'}",
        "",
        "| Ticker | Simbolo no provedor | CIK | Inicio | Fim | Pregoes | Maior lacuna | Status |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for row in report.rows:
        status = "aprovado" if row.is_ready else f"rejeitado: {row.error}"
        lines.append(
            f"| {row.ticker} | {row.provider_ticker} | {row.issuer_cik} | "
            f"{row.observed_start or '-'} | {row.observed_end or '-'} | "
            f"{row.observations} | {row.maximum_gap_days or '-'} | {status} |"
        )
    lines.extend(
        [
            "",
            "O preflight valida cobertura e identidade, mas nao substitui a "
            "reconciliacao economica dos eventos terminais.",
        ]
    )
    return "\n".join(lines)
