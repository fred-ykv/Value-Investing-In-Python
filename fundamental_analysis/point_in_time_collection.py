"""Build auditable historical score observations from SEC facts and prices."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from .benchmark_universe import BenchmarkCase, DEFAULT_BENCHMARK_CASES
from .config import POINT_IN_TIME, PointInTimeAssumptions
from .data_sources import metric_value
from .historical_calibration import HistoricalCalibrationObservation
from .historical_macro import HistoricalMacroProvider, HistoricalMacroSnapshot
from .historical_prices import (
    HistoricalPriceProvider,
    PriceOutcome,
    add_months,
    calculate_price_outcome,
)
from .main import AnalysisResult, analyze_ticker_from_inputs
from .sec_edgar import PointInTimeFundamentals, SecEdgarClient, SecFilingAnchor


@dataclass(frozen=True)
class PointInTimeCollectionResult:
    ticker: str
    as_of: date | None
    filing_accession: str
    observation: HistoricalCalibrationObservation | None
    error: str = ""
    warnings: tuple[str, ...] = ()
    skipped: bool = False


@dataclass(frozen=True)
class PointInTimeDataset:
    results: list[PointInTimeCollectionResult]

    @property
    def observations(self) -> list[HistoricalCalibrationObservation]:
        return [result.observation for result in self.results if result.observation is not None]

    @property
    def errors(self) -> list[PointInTimeCollectionResult]:
        return [result for result in self.results if result.error]

    @property
    def skipped(self) -> list[PointInTimeCollectionResult]:
        return [result for result in self.results if result.skipped]

    @property
    def success_rate(self) -> float:
        attempted = len(self.results) - len(self.skipped)
        return len(self.observations) / attempted if attempted else 0.0


AnalysisFunction = Callable[..., AnalysisResult]


def collect_point_in_time_observation(
    case: BenchmarkCase,
    anchor: SecFilingAnchor,
    sec_client: SecEdgarClient,
    price_provider: HistoricalPriceProvider,
    macro_provider: HistoricalMacroProvider,
    *,
    analyzer: AnalysisFunction = analyze_ticker_from_inputs,
    assumptions: PointInTimeAssumptions = POINT_IN_TIME,
) -> PointInTimeCollectionResult:
    as_of = anchor.filed + timedelta(days=assumptions.minimum_filing_lag_days)
    benchmark_ticker = assumptions.benchmark_for_group(case.benchmark_group)
    try:
        snapshot = sec_client.build_snapshot(
            case.ticker,
            as_of,
            anchor_accession=anchor.accession_number,
        )
        outcome = calculate_price_outcome(
            case.ticker,
            benchmark_ticker,
            as_of,
            price_provider,
            assumptions,
        )
        macro = macro_provider.snapshot(as_of)
        result = _analyze_snapshot(case, snapshot, outcome, macro, analyzer)
        data_dimension = result.score.dimensions.get("data_confidence")
        data_confidence = data_dimension.score if data_dimension is not None else 0.0
        coverage_ok = snapshot.audit.coverage_ratio >= assumptions.minimum_fundamental_coverage
        point_in_time_validated = (
            snapshot.audit.point_in_time_valid
            and coverage_ok
            and outcome.price_start_date >= as_of
            and snapshot.audit.latest_filing_date <= as_of
            and macro.point_in_time_valid
        )
        warnings = [*snapshot.audit.warnings, *macro.warnings]
        if outcome.trailing_beta is None:
            warnings.append(
                f"Beta historico indisponivel: {outcome.beta_observations} retornos comuns; "
                f"minimo {assumptions.minimum_beta_return_observations}."
            )
        observation = HistoricalCalibrationObservation(
            ticker=case.ticker.upper(),
            as_of=as_of,
            company_type=result.company_type,
            total_score=result.score.total_score,
            recommendation=result.score.recommendation,
            data_confidence=data_confidence,
            forward_return=outcome.forward_return,
            benchmark_return=outcome.benchmark_return,
            max_drawdown=outcome.max_drawdown,
            point_in_time_validated=point_in_time_validated,
            latest_filing_date=snapshot.audit.latest_filing_date,
            benchmark_ticker=benchmark_ticker,
            price_start_date=outcome.price_start_date,
            price_end_date=outcome.price_end_date,
            filing_accession=anchor.accession_number,
            fundamental_coverage=snapshot.audit.coverage_ratio,
            risk_free_rate=float(macro.risk_free_rate.value),
            risk_free_rate_date=macro.risk_free_observation_date,
            equity_risk_premium=float(macro.equity_risk_premium.value),
            erp_reference_year=macro.erp_reference_year,
            erp_available_date=macro.erp_available_from,
            macro_point_in_time_validated=macro.point_in_time_valid,
            discount_rate=result.cost_of_capital.discount_rate,
            discount_rate_label=result.cost_of_capital.discount_rate_label,
            wacc=result.cost_of_capital.wacc,
            cost_of_equity=result.cost_of_capital.cost_of_equity,
            cost_of_capital_method=result.cost_of_capital.method,
            cost_of_capital_confidence=result.cost_of_capital.confidence,
            cost_of_capital_is_fallback=result.cost_of_capital.is_fallback,
        )
        return PointInTimeCollectionResult(
            ticker=case.ticker.upper(),
            as_of=as_of,
            filing_accession=anchor.accession_number,
            observation=observation,
            warnings=tuple(warnings),
        )
    except Exception as exc:
        return PointInTimeCollectionResult(
            ticker=case.ticker.upper(),
            as_of=as_of,
            filing_accession=anchor.accession_number,
            observation=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def collect_benchmark_history(
    sec_client: SecEdgarClient,
    price_provider: HistoricalPriceProvider,
    macro_provider: HistoricalMacroProvider,
    *,
    cases: Iterable[BenchmarkCase] = DEFAULT_BENCHMARK_CASES,
    start_year: int | None = None,
    end_year: int | None = None,
    max_filings_per_company: int | None = None,
    analyzer: AnalysisFunction = analyze_ticker_from_inputs,
    assumptions: PointInTimeAssumptions = POINT_IN_TIME,
    outcomes_available_through: date | None = None,
) -> PointInTimeDataset:
    start_year = start_year if start_year is not None else assumptions.historical_start_year
    max_filings = (
        max_filings_per_company
        if max_filings_per_company is not None
        else assumptions.max_annual_filings_per_company
    )
    results: list[PointInTimeCollectionResult] = []
    outcomes_available_through = outcomes_available_through or date.today()
    for case in cases:
        try:
            anchors = sec_client.list_annual_filings(
                case.ticker,
                start_year=start_year,
                end_year=end_year,
                max_filings=None,
            )
        except Exception as exc:
            results.append(
                PointInTimeCollectionResult(
                    ticker=case.ticker.upper(),
                    as_of=None,
                    filing_accession="",
                    observation=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        if not anchors:
            results.append(
                PointInTimeCollectionResult(
                    ticker=case.ticker.upper(),
                    as_of=None,
                    filing_accession="",
                    observation=None,
                    error="Nenhum formulario anual no periodo solicitado",
                )
            )
            continue
        anchors = [
            anchor
            for anchor in anchors
            if add_months(
                anchor.filed + timedelta(days=assumptions.minimum_filing_lag_days),
                assumptions.forward_horizon_months,
            )
            <= outcomes_available_through
        ]
        if max_filings == 0:
            anchors = []
        elif max_filings is not None and max_filings > 0:
            anchors = anchors[-max_filings:]
        if not anchors:
            results.append(
                PointInTimeCollectionResult(
                    ticker=case.ticker.upper(),
                    as_of=None,
                    filing_accession="",
                    observation=None,
                    warnings=("Sem filing com janela futura completa no periodo solicitado.",),
                    skipped=True,
                )
            )
            continue
        for anchor in anchors:
            results.append(
                collect_point_in_time_observation(
                    case,
                    anchor,
                    sec_client,
                    price_provider,
                    macro_provider,
                    analyzer=analyzer,
                    assumptions=assumptions,
                )
            )
    return PointInTimeDataset(results)


def write_collection_manifest(dataset: PointInTimeDataset, path: str | Path) -> None:
    payload = {
        "total_attempts": len(dataset.results),
        "successful_observations": len(dataset.observations),
        "errors": len(dataset.errors),
        "skipped": len(dataset.skipped),
        "success_rate": dataset.success_rate,
        "results": [asdict(result) for result in dataset.results],
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def render_collection_markdown(dataset: PointInTimeDataset) -> str:
    lines = [
        "# Coleta Historica Point-in-Time",
        "",
        f"- Tentativas: {len(dataset.results)}",
        f"- Observacoes validas: {len(dataset.observations)}",
        f"- Erros: {len(dataset.errors)}",
        f"- Ignorados sem janela futura completa: {len(dataset.skipped)}",
        f"- Taxa de sucesso: {dataset.success_rate:.1%}",
        "",
        "## Resultado por observacao",
        "| Ticker | Data-base | Filing | Status | Cobertura | Rf / ERP / taxa aplicada | Benchmark | Avisos/erro |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for result in dataset.results:
        observation = result.observation
        coverage = f"{observation.fundamental_coverage:.1%}" if observation else "-"
        status = "ignorado" if result.skipped else "ok" if observation else "erro"
        capital = (
            f"{observation.risk_free_rate:.2%} / {observation.equity_risk_premium:.2%} / "
            f"{observation.discount_rate:.2%} ({observation.discount_rate_label})"
            if observation
            and observation.risk_free_rate is not None
            and observation.equity_risk_premium is not None
            and observation.discount_rate is not None
            else "-"
        )
        lines.append(
            f"| {result.ticker} | {result.as_of or '-'} | {result.filing_accession or '-'} | "
            f"{status} | "
            f"{coverage} | "
            f"{capital} | "
            f"{observation.benchmark_ticker if observation else '-'} | "
            f"{result.error or '; '.join(result.warnings) or '-'} |"
        )
    return "\n".join(lines)


def _analyze_snapshot(
    case: BenchmarkCase,
    snapshot: PointInTimeFundamentals,
    outcome: PriceOutcome,
    macro: HistoricalMacroSnapshot,
    analyzer: AnalysisFunction,
) -> AnalysisResult:
    shares = snapshot.market_data.get("shares")
    market_overrides: dict[str, object] = {
        "price": metric_value(
            "price",
            outcome.start_price,
            "yfinance_historical",
            "Unadjusted close for valuation on first trading day on or after the analysis date",
            source_url=f"https://finance.yahoo.com/quote/{case.ticker}/history",
            source_document="Yahoo Finance historical close",
            period_end=outcome.price_start_date,
            as_of=datetime.combine(outcome.price_start_date, datetime.min.time()),
            currency="USD",
            scale="raw",
        ),
        "enable_peer_yahoo_enrichment": False,
        "disable_sector_benchmark_fallback": True,
        "benchmark_group": case.benchmark_group,
        "sector_bucket": case.sector_bucket,
        "ticker": case.ticker,
        **macro.market_overrides(),
    }
    if outcome.trailing_beta is not None:
        market_overrides["beta"] = metric_value(
            "beta",
            outcome.trailing_beta,
            "yfinance_historical",
            f"Trailing beta from {outcome.beta_observations} daily return pairs known before analysis",
            source_document="Yahoo Finance adjusted historical prices",
            period_end=outcome.price_start_date - timedelta(days=1),
            as_of=datetime.combine(outcome.price_start_date, datetime.min.time()),
            formula="covariance_stock_benchmark_divided_by_benchmark_variance",
        )
    if shares is not None and shares.is_available:
        market_overrides["market_cap"] = metric_value(
            "market_cap",
            outcome.start_price * float(shares.value),
            "sec_edgar_derived",
            "Historical unadjusted close multiplied by SEC shares outstanding",
            source_document=(shares.source_document or "SEC EDGAR") + "; Yahoo Finance historical price",
            period_end=outcome.price_start_date,
            filing_date=shares.filing_date,
            currency="USD",
            formula="historical_price_times_filed_shares",
            confidence=min(shares.confidence, 0.75),
        )
    statements = snapshot.as_financial_statements(
        market_overrides=market_overrides,
        info_overrides=_classification_info(case),
    )
    return analyzer(
        statements.ticker,
        statements.income_statement,
        statements.balance_sheet,
        statements.cash_flow,
        statements.market_data,
        statements.info,
        statements.source,
    )


def _classification_info(case: BenchmarkCase) -> dict[str, object]:
    bucket = case.sector_bucket
    if case.benchmark_group == "bancos_financeiras":
        sector = "Financial Services"
        business_model = "bank"
    elif case.benchmark_group == "growth_tech":
        sector = "Technology"
        business_model = (
            "fabless_semiconductor" if "semiconductor" in bucket else "saas" if "software" in bucket else "technology"
        )
    elif case.benchmark_group == "fcf_negativo_early_growth":
        sector = "Healthcare" if "bio" in bucket else "Consumer Cyclical" if "vehicle" in bucket or "mobility" in bucket else "Technology"
        business_model = "ev_pure_play" if "vehicle" in bucket or "mobility" in bucket else "early_growth"
    else:
        sector = "Consumer Cyclical" if "auto" in bucket else "Basic Materials" if "steel" in bucket or "metal" in bucket else "Industrials"
        business_model = "traditional_auto" if "auto" in bucket else "industrial"
    return {
        "ticker": case.ticker,
        "sector": sector,
        "industry": bucket.replace("_", " ").title(),
        "business_model": business_model,
        "sic_description": bucket.replace("_", " "),
        "classification_source": "curated_benchmark_universe",
        "classification_rationale": case.rationale,
    }
