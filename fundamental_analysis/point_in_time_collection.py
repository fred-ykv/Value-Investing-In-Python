"""Build auditable historical score observations from SEC facts and prices."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from .benchmark_universe import BenchmarkCase, DEFAULT_BENCHMARK_CASES
from .config import CYCLICAL, POINT_IN_TIME, PointInTimeAssumptions
from .data_sources import metric_value
from .historical_calibration import (
    HistoricalCalibrationObservation,
    HistoricalScoreComponentAudit,
    HistoricalScoreDimensionContribution,
    HistoricalValuationAssumptionAudit,
    HistoricalValuationMethodAudit,
)
from .historical_macro import HistoricalMacroProvider, HistoricalMacroSnapshot
from .historical_prices import (
    HistoricalPriceProvider,
    PriceOutcome,
    add_months,
    calculate_price_outcome,
)
from .main import AnalysisResult, analyze_ticker_from_inputs
from .scoring import recommendation_decision_from_score
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
            cik_override=case.cik or None,
        )
        cyclical_history = (
            [
                item.as_financial_statements()
                for item in sec_client.build_annual_history(
                    case.ticker,
                    as_of,
                    max_filings=CYCLICAL.maximum_years,
                    cik_override=case.cik or None,
                )
            ]
            if case.is_cyclical
            else []
        )
        outcome = calculate_price_outcome(
            case.ticker,
            benchmark_ticker,
            as_of,
            price_provider,
            assumptions,
            lifecycle_event=case.lifecycle_event,
            expected_cik=case.cik or None,
        )
        macro = macro_provider.snapshot(as_of)
        result = _analyze_snapshot(
            case,
            snapshot,
            outcome,
            macro,
            analyzer,
            cyclical_history,
        )
        dimension_audit = {
            name: _score_dimension_audit(result, name)
            for name in (
                "valuation",
                "growth",
                "quality",
                "debt",
                "liquidity",
                "data_confidence",
            )
        }
        data_confidence = dimension_audit["data_confidence"][0] or 0.0
        decision = result.score.recommendation_decision or (
            recommendation_decision_from_score(
                result.score.total_score,
                result.score.dimensions,
            )
        )
        score_contributions = tuple(
            HistoricalScoreDimensionContribution(
                name=contribution.name,
                score=contribution.score,
                confidence=contribution.confidence,
                configured_weight=contribution.configured_weight,
                normalized_weight=contribution.normalized_weight,
                weighted_contribution=contribution.weighted_contribution,
            )
            for contribution in result.score.dimension_contributions
        )
        score_weighted_total = (
            sum(item.weighted_contribution for item in score_contributions)
            if score_contributions
            else None
        )
        score_reconciliation_difference = (
            result.score.total_score - score_weighted_total
            if score_weighted_total is not None
            else None
        )
        if (
            score_reconciliation_difference is not None
            and abs(score_reconciliation_difference) > 1e-12
        ):
            raise ValueError(
                "Contribuicoes dimensionais nao reconciliam com o score total"
            )
        score_configuration = result.score.configuration_audit
        score_component_audit = tuple(
            HistoricalScoreComponentAudit(
                dimension=component.dimension,
                stage=component.stage,
                component=component.component,
                raw_value=component.raw_value,
                transformed_score=component.transformed_score,
                configured_weight=component.configured_weight,
                effective_weight=component.effective_weight,
                weighted_contribution=component.weighted_contribution,
                confidence=component.confidence,
                source=component.source,
                used=component.used,
                reason=component.reason,
            )
            for component in result.score.component_audit
        )
        for dimension_name, (dimension_score, _) in dimension_audit.items():
            reconciled = sum(
                component.weighted_contribution
                for component in score_component_audit
                if component.dimension == dimension_name
                and component.stage == "dimension"
                and component.used
            )
            if dimension_score is not None and abs(reconciled - dimension_score) > 1e-12:
                raise ValueError(
                    f"Componentes historicos de {dimension_name} nao reconciliam com a dimensao"
                )
        critical_coverage, missing_critical = _critical_metric_audit(
            case,
            snapshot,
            assumptions,
        )
        analysis_input_validated = not missing_critical
        point_in_time_validated = (
            snapshot.audit.point_in_time_valid
            and analysis_input_validated
            and outcome.price_start_date >= as_of
            and snapshot.audit.latest_filing_date <= as_of
            and macro.point_in_time_valid
        )
        warnings = [
            *snapshot.audit.warnings,
            *macro.warnings,
            *result.cyclical_normalization.warnings,
        ]
        if missing_critical:
            warnings.append(
                "Entradas criticas ausentes para o modelo: "
                + ", ".join(missing_critical)
                + "."
            )
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
            score_model_version=(
                score_configuration.model_version if score_configuration else ""
            ),
            score_config_fingerprint=(
                score_configuration.fingerprint if score_configuration else ""
            ),
            score_configured_weights=(
                score_configuration.configured_weights
                if score_configuration
                else ()
            ),
            score_normalized_weights=(
                score_configuration.normalized_weights
                if score_configuration
                else ()
            ),
            score_weighted_total=score_weighted_total,
            score_reconciliation_difference=score_reconciliation_difference,
            score_dimension_contributions=score_contributions,
            score_component_audit=score_component_audit,
            recommendation=result.score.recommendation,
            recommendation_before_gates=decision.recommendation_before_gates,
            recommendation_gate_code=decision.gate_code,
            recommendation_gate_triggered=decision.gate_triggered,
            recommendation_gate_explanation=decision.explanation,
            recommendation_buy_threshold=decision.buy_threshold,
            recommendation_watch_threshold=decision.watch_threshold,
            recommendation_min_valuation_score_for_buy=(
                decision.min_valuation_score_for_buy
            ),
            recommendation_avoid_if_valuation_below=(
                decision.avoid_if_valuation_below
            ),
            recommendation_avoid_if_quality_below=(
                decision.avoid_if_quality_below
            ),
            data_confidence=data_confidence,
            forward_return=outcome.forward_return,
            benchmark_return=outcome.benchmark_return,
            max_drawdown=outcome.max_drawdown,
            point_in_time_validated=point_in_time_validated,
            latest_filing_date=snapshot.audit.latest_filing_date,
            benchmark_ticker=benchmark_ticker,
            price_start_date=outcome.price_start_date,
            price_end_date=outcome.price_end_date,
            valuation_price=outcome.start_price,
            price_source=outcome.source,
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
            calculated_wacc=result.cost_of_capital.calculated_wacc,
            cost_of_equity=result.cost_of_capital.cost_of_equity,
            beta=result.cost_of_capital.beta,
            pre_tax_cost_of_debt=result.cost_of_capital.pre_tax_cost_of_debt,
            after_tax_cost_of_debt=result.cost_of_capital.after_tax_cost_of_debt,
            tax_rate=result.cost_of_capital.tax_rate,
            market_value_equity=result.cost_of_capital.market_value_equity,
            debt_value=result.cost_of_capital.debt_value,
            equity_weight=result.cost_of_capital.equity_weight,
            debt_weight=result.cost_of_capital.debt_weight,
            cost_of_capital_method=result.cost_of_capital.method,
            cost_of_capital_confidence=result.cost_of_capital.confidence,
            cost_of_capital_is_fallback=result.cost_of_capital.is_fallback,
            cost_of_capital_sources=tuple(
                sorted(result.cost_of_capital.sources.items())
            ),
            cost_of_capital_component_confidences=tuple(
                sorted(result.cost_of_capital.component_confidences.items())
            ),
            cost_of_capital_component_fallbacks=tuple(
                sorted(result.cost_of_capital.component_fallbacks.items())
            ),
            cost_of_capital_notes=result.cost_of_capital.notes,
            valuation_method_audit=tuple(
                _valuation_method_audit(valuation)
                for valuation in result.valuations
            ),
            is_cyclical=result.cyclical_normalization.is_cyclical,
            cyclical_normalization_applied=result.cyclical_normalization.applied,
            cyclical_normalization_years=result.cyclical_normalization.sample_years,
            cyclical_normalization_confidence=result.cyclical_normalization.confidence,
            cycle_position=result.cyclical_normalization.cycle_position,
            current_fcff=_valuation_diagnostic_number(
                result,
                "dcf_fcff",
                "current_fcff",
            ),
            normalized_fcff=_metric_number(
                result.cyclical_normalization.normalized_fcff
            ),
            normalized_operating_margin=(
                result.cyclical_normalization.normalized_operating_margin
            ),
            normalized_reinvestment_margin=(
                result.cyclical_normalization.normalized_reinvestment_margin
            ),
            benchmark_group=case.benchmark_group,
            sector_bucket=case.sector_bucket,
            critical_metric_coverage=critical_coverage,
            missing_critical_metrics=", ".join(missing_critical),
            analysis_input_validated=analysis_input_validated,
            security_cik=snapshot.cik,
            universe_status=case.universe_status,
            outcome_method=outcome.outcome_method,
            lifecycle_event_type=(
                case.lifecycle_event.event_type if case.lifecycle_event else ""
            ),
            lifecycle_event_date=(
                case.lifecycle_event.effective_date if case.lifecycle_event else None
            ),
            stock_terminal_date=outcome.stock_terminal_date,
            terminal_value_per_share=outcome.terminal_value_per_share,
            lifecycle_source_url=(
                case.lifecycle_event.source_url if case.lifecycle_event else ""
            ),
            dimension_valuation_score=dimension_audit["valuation"][0],
            dimension_valuation_confidence=dimension_audit["valuation"][1],
            dimension_growth_score=dimension_audit["growth"][0],
            dimension_growth_confidence=dimension_audit["growth"][1],
            dimension_quality_score=dimension_audit["quality"][0],
            dimension_quality_confidence=dimension_audit["quality"][1],
            dimension_debt_score=dimension_audit["debt"][0],
            dimension_debt_confidence=dimension_audit["debt"][1],
            dimension_liquidity_score=dimension_audit["liquidity"][0],
            dimension_liquidity_confidence=dimension_audit["liquidity"][1],
            dimension_data_confidence_score=dimension_audit["data_confidence"][0],
            dimension_data_confidence_confidence=dimension_audit[
                "data_confidence"
            ][1],
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
                cik_override=case.cik or None,
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
        "| Ticker | Universo/resultado | Data-base | Filing | Status | Cobertura geral/critica | Ciclo | Rf / ERP / taxa aplicada | Benchmark | Avisos/erro |",
        "|---|---|---|---|---|---:|---|---:|---|---|",
    ]
    for result in dataset.results:
        observation = result.observation
        coverage = (
            f"{observation.fundamental_coverage:.1%} / "
            f"{observation.critical_metric_coverage:.1%}"
            if observation
            else "-"
        )
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
            f"| {result.ticker} | {_lifecycle_audit_label(observation)} | "
            f"{result.as_of or '-'} | {result.filing_accession or '-'} | "
            f"{status} | "
            f"{coverage} | "
            f"{_cycle_audit_label(observation)} | "
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
    cyclical_history: list[object],
) -> AnalysisResult:
    shares = snapshot.market_data.get("shares")
    price_source_url = (
        f"https://finance.yahoo.com/quote/{case.ticker}/history"
        if "yfinance" in outcome.source
        else ""
    )
    market_overrides: dict[str, object] = {
        "price": metric_value(
            "price",
            outcome.start_price,
            "historical_market_price",
            "Unadjusted close for valuation on first trading day on or after the analysis date",
            source_url=price_source_url,
            source_document=outcome.source,
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
        "is_cyclical": case.is_cyclical,
        "cyclical_history": cyclical_history,
        **macro.market_overrides(),
    }
    if outcome.trailing_beta is not None:
        market_overrides["beta"] = metric_value(
            "beta",
            outcome.trailing_beta,
            "historical_market_price",
            f"Trailing beta from {outcome.beta_observations} daily return pairs known before analysis",
            source_document=outcome.source,
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
            source_document=(shares.source_document or "SEC EDGAR") + "; " + outcome.source,
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


def _valuation_diagnostic_number(
    result: AnalysisResult,
    method: str,
    key: str,
) -> float | None:
    valuation = next(
        (item for item in result.valuations if item.method == method),
        None,
    )
    if valuation is None:
        return None
    value = valuation.diagnostics.get(key)
    return float(value) if value is not None else None


def _valuation_method_audit(valuation: object) -> HistoricalValuationMethodAudit:
    margin = getattr(valuation, "margin_of_safety", None)
    confidence = float(getattr(valuation, "confidence", 0.0) or 0.0)
    diagnostics = getattr(valuation, "diagnostics", {}) or {}
    used_in_score = margin is not None and confidence > 0.0
    exclusion_reason = ""
    if not used_in_score:
        if margin is None:
            exclusion_reason = str(
                diagnostics.get("error") or "Margem de seguranca indisponivel"
            )
        else:
            exclusion_reason = "Confianca igual a zero"
    fair_value = getattr(valuation, "fair_value_per_share", None)
    enterprise_value = getattr(valuation, "enterprise_value", None)
    equity_value = getattr(valuation, "equity_value", None)
    output_keys = (
        "pv_explicit_stage",
        "pv_terminal_value",
        "terminal_value_share",
        "explicit_stage_share",
        "economic_profit",
        "pv_economic_profit",
        "net_debt_adjustment",
    )
    model_outputs = tuple(
        (key, float(diagnostics[key]))
        for key in output_keys
        if diagnostics.get(key) is not None
    )
    assumptions = tuple(
        HistoricalValuationAssumptionAudit(
            name=str(getattr(assumption, "name", "")),
            input_value=_optional_float(
                getattr(assumption, "input_value", None)
            ),
            effective_value=_optional_float(
                getattr(assumption, "effective_value", None)
            ),
            source=str(getattr(assumption, "source", "")),
            confidence=float(getattr(assumption, "confidence", 0.0) or 0.0),
            is_fallback=bool(getattr(assumption, "is_fallback", False)),
            note=str(getattr(assumption, "note", "")),
            formula=str(getattr(assumption, "formula", "")),
        )
        for assumption in (getattr(valuation, "assumptions", ()) or ())
    )
    return HistoricalValuationMethodAudit(
        method=str(getattr(valuation, "method", "")),
        used_in_score=used_in_score,
        fair_value_per_share=(
            float(fair_value) if fair_value is not None else None
        ),
        margin_of_safety=float(margin) if margin is not None else None,
        confidence=confidence,
        source=str(getattr(valuation, "source", "")),
        exclusion_reason=exclusion_reason,
        enterprise_value=_optional_float(enterprise_value),
        equity_value=_optional_float(equity_value),
        model_outputs=model_outputs,
        assumptions=assumptions,
    )


def _metric_number(metric: object) -> float | None:
    value = getattr(metric, "value", None)
    return float(value) if value is not None else None


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _score_dimension_audit(
    result: AnalysisResult,
    name: str,
) -> tuple[float | None, float | None]:
    dimension = result.score.dimensions.get(name)
    if dimension is None:
        return None, None
    return float(dimension.score), float(dimension.confidence)


def _cycle_audit_label(
    observation: HistoricalCalibrationObservation | None,
) -> str:
    if observation is None or not observation.is_cyclical:
        return "nao aplicavel"
    status = "aplicada" if observation.cyclical_normalization_applied else "nao aplicada"
    return f"{status}; {observation.cyclical_normalization_years} anos"


def _lifecycle_audit_label(
    observation: HistoricalCalibrationObservation | None,
) -> str:
    if observation is None:
        return "-"
    if not observation.lifecycle_event_type:
        return f"{observation.universe_status}; {observation.outcome_method}"
    return (
        f"{observation.universe_status}; {observation.lifecycle_event_type}; "
        f"{observation.outcome_method}"
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


def _critical_metric_audit(
    case: BenchmarkCase,
    snapshot: PointInTimeFundamentals,
    assumptions: PointInTimeAssumptions = POINT_IN_TIME,
) -> tuple[float, tuple[str, ...]]:
    if case.benchmark_group == "bancos_financeiras":
        required = (
            ("income_statement", "net_income"),
            ("balance_sheet", "equity"),
            ("market_data", "shares"),
        )
    elif case.benchmark_group in {"growth_tech", "fcf_negativo_early_growth"}:
        required = (
            ("income_statement", "revenue"),
            ("balance_sheet", "cash"),
            ("balance_sheet", "total_debt"),
            ("market_data", "shares"),
        )
    else:
        required = (
            ("income_statement", "revenue"),
            ("income_statement", "ebit"),
            ("income_statement", "net_income"),
            ("balance_sheet", "equity"),
            ("balance_sheet", "cash"),
            ("balance_sheet", "total_debt"),
            ("cash_flow", "depreciation_amortization"),
            ("cash_flow", "capex"),
            ("market_data", "shares"),
        )
    sections = {
        "income_statement": snapshot.income_statement,
        "balance_sheet": snapshot.balance_sheet,
        "cash_flow": snapshot.cash_flow,
        "market_data": snapshot.market_data,
    }
    missing = tuple(
        f"{section}.{metric}"
        for section, metric in required
        if metric not in sections[section]
        or not sections[section][metric].is_available
        or sections[section][metric].confidence
        < assumptions.minimum_critical_metric_confidence
    )
    return (len(required) - len(missing)) / len(required), missing
