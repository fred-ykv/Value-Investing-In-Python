"""Point-in-time risk-free rates and implied equity risk premiums."""

from __future__ import annotations

import csv
import io
import math
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Protocol

from .config import POINT_IN_TIME, PointInTimeAssumptions
from .data_sources import MetricValue, metric_value


@dataclass(frozen=True)
class RiskFreeObservation:
    day: date
    rate: float
    source_url: str


@dataclass(frozen=True)
class EquityRiskPremiumObservation:
    reference_year: int
    available_from: date
    premium: float
    source_url: str


@dataclass(frozen=True)
class HistoricalMacroSnapshot:
    as_of: date
    risk_free_rate: MetricValue
    equity_risk_premium: MetricValue
    risk_free_observation_date: date
    erp_reference_year: int
    erp_available_from: date
    point_in_time_valid: bool
    warnings: tuple[str, ...] = ()

    def market_overrides(self) -> dict[str, MetricValue]:
        return {
            "risk_free_rate": self.risk_free_rate,
            "equity_risk_premium": self.equity_risk_premium,
        }


class HistoricalMacroProvider(Protocol):
    def snapshot(self, as_of: date) -> HistoricalMacroSnapshot:
        ...


TextGetter = Callable[[str], str]


class HistoricalMacroClient:
    def __init__(
        self,
        *,
        assumptions: PointInTimeAssumptions = POINT_IN_TIME,
        cache_dir: str | Path | None = None,
        text_getter: TextGetter | None = None,
    ):
        self.assumptions = assumptions
        self.cache_dir = Path(cache_dir or assumptions.macro_cache_directory)
        self.text_getter = text_getter

    def snapshot(self, as_of: date) -> HistoricalMacroSnapshot:
        risk_free = self.risk_free_observation(as_of)
        erp = self.equity_risk_premium_observation(as_of)
        risk_free_lag = (as_of - risk_free.day).days
        valid = (
            risk_free.day <= as_of
            and risk_free_lag <= self.assumptions.risk_free_max_staleness_days
            and erp.available_from <= as_of
        )
        warnings: list[str] = []
        if risk_free_lag > 3:
            warnings.append(
                f"Taxa livre de risco usa observacao de {risk_free.day}, "
                f"{risk_free_lag} dias antes da data-base."
            )
        if not valid:
            warnings.append("Snapshot macro rejeitado pelo controle point-in-time.")
        risk_free_metric = metric_value(
            "risk_free_rate",
            risk_free.rate,
            "us_treasury_historical",
            f"Treasury nominal de 10 anos em {risk_free.day}",
            source_url=risk_free.source_url,
            source_document="U.S. Treasury Daily Par Yield Curve Rates",
            period_end=risk_free.day,
            as_of=datetime.combine(as_of, datetime.min.time()),
            basis="reported",
            formula="treasury_10_year_rate_divided_by_100",
        )
        erp_metric = metric_value(
            "equity_risk_premium",
            erp.premium,
            "damodaran_historical_erp",
            (
                f"ERP implicito FCFE do ano {erp.reference_year}; considerado disponivel "
                f"em {erp.available_from}"
            ),
            source_url=erp.source_url,
            source_document="Damodaran Historical Implied Equity Risk Premiums",
            period_end=date(erp.reference_year, 12, 31),
            filing_date=erp.available_from,
            as_of=datetime.combine(as_of, datetime.min.time()),
            basis="reported",
            formula="damodaran_implied_erp_fcfe",
        )
        return HistoricalMacroSnapshot(
            as_of=as_of,
            risk_free_rate=risk_free_metric,
            equity_risk_premium=erp_metric,
            risk_free_observation_date=risk_free.day,
            erp_reference_year=erp.reference_year,
            erp_available_from=erp.available_from,
            point_in_time_valid=valid,
            warnings=tuple(warnings),
        )

    def risk_free_observation(self, as_of: date) -> RiskFreeObservation:
        observations: list[RiskFreeObservation] = []
        parse_errors: list[str] = []
        for year in (as_of.year - 1, as_of.year):
            url = self.assumptions.treasury_csv_url_template.format(year=year)
            text = self._load_text(url, f"treasury_yield_curve_{year}.csv")
            try:
                observations.extend(parse_treasury_csv(text, url, self.assumptions))
            except ValueError as exc:
                parse_errors.append(f"{year}: {exc}")
        if not observations:
            raise LookupError(
                "Taxa livre de risco indisponivel: " + "; ".join(parse_errors)
            )
        candidates = [item for item in observations if item.day <= as_of]
        if not candidates:
            raise LookupError(f"Taxa livre de risco indisponivel ate {as_of}")
        selected = max(candidates, key=lambda item: item.day)
        lag = (as_of - selected.day).days
        if lag > self.assumptions.risk_free_max_staleness_days:
            raise LookupError(
                f"Taxa livre de risco esta {lag} dias antes de {as_of}; "
                f"maximo {self.assumptions.risk_free_max_staleness_days}"
            )
        return selected

    def equity_risk_premium_observation(
        self,
        as_of: date,
    ) -> EquityRiskPremiumObservation:
        url = self.assumptions.damodaran_historical_erp_url
        text = self._load_text(url, "damodaran_historical_erp.html")
        observations = parse_damodaran_erp_html(text, url, self.assumptions)
        candidates = [item for item in observations if item.available_from <= as_of]
        if not candidates:
            raise LookupError(f"ERP historico indisponivel em {as_of}")
        return max(candidates, key=lambda item: item.reference_year)

    def _load_text(self, url: str, cache_name: str) -> str:
        cache_path = self.cache_dir / cache_name
        fresh = (
            cache_path.exists()
            and time.time() - cache_path.stat().st_mtime
            <= self.assumptions.macro_cache_max_age_hours * 3600
        )
        if fresh:
            try:
                text = cache_path.read_text(encoding="utf-8")
                if text.strip():
                    return text
            except OSError:
                pass
        if self.text_getter is not None:
            text = self.text_getter(url)
        else:
            text = self._request_text(url)
        if not isinstance(text, str) or not text.strip():
            raise TypeError(f"Resposta textual invalida para {url}")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(cache_path)
        return text

    def _request_text(self, url: str) -> str:
        import requests

        response = requests.get(
            url,
            headers={"User-Agent": self.assumptions.macro_http_user_agent},
            timeout=self.assumptions.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.text


def parse_treasury_csv(
    text: str,
    source_url: str,
    assumptions: PointInTimeAssumptions = POINT_IN_TIME,
) -> list[RiskFreeObservation]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("CSV do Treasury sem cabecalho")
    normalized_headers = {_normalize_header(name): name for name in reader.fieldnames}
    date_column = normalized_headers.get("date")
    maturity_column = normalized_headers.get(
        _normalize_header(assumptions.treasury_maturity_column)
    )
    if date_column is None or maturity_column is None:
        raise ValueError("CSV do Treasury sem colunas Date e 10 Yr")
    observations: list[RiskFreeObservation] = []
    for row in reader:
        raw_date = (row.get(date_column) or "").strip()
        raw_rate = (row.get(maturity_column) or "").strip()
        try:
            day = datetime.strptime(raw_date, "%m/%d/%Y").date()
            percentage = float(raw_rate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(percentage) and 0.0 <= percentage <= 30.0:
            observations.append(RiskFreeObservation(day, percentage / 100.0, source_url))
    if not observations:
        raise ValueError("CSV do Treasury sem observacoes validas de 10 anos")
    return observations


def parse_damodaran_erp_html(
    text: str,
    source_url: str,
    assumptions: PointInTimeAssumptions = POINT_IN_TIME,
) -> list[EquityRiskPremiumObservation]:
    parser = _TableRowParser()
    parser.feed(text)
    observations: list[EquityRiskPremiumObservation] = []
    for row in parser.rows:
        if not row or not re.fullmatch(r"\d{4}", row[0]):
            continue
        year = int(row[0])
        if len(row) < 2:
            continue
        premium = _parse_percentage(row[-1])
        if premium is None or not 0.0 < premium < 0.20:
            continue
        available_from = date(
            year + 1,
            assumptions.erp_publication_month,
            assumptions.erp_publication_day,
        )
        observations.append(
            EquityRiskPremiumObservation(year, available_from, premium, source_url)
        )
    if len(observations) < 10:
        raise ValueError("Tabela Damodaran sem historico ERP suficiente")
    return observations


class _TableRowParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            self._row.append(" ".join("".join(self._cell_parts).split()))
            self._cell_parts = None
        elif lowered == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell_parts = None


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _parse_percentage(value: str) -> float | None:
    cleaned = value.replace("%", "").replace(",", ".").strip()
    try:
        percentage = float(cleaned)
    except ValueError:
        return None
    return percentage / 100.0 if math.isfinite(percentage) else None
