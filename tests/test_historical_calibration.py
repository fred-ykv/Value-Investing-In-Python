import unittest
from dataclasses import replace
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

from fundamental_analysis.config import CalibrationAssumptions
from fundamental_analysis.historical_calibration import (
    HistoricalCalibrationObservation,
    HistoricalScoreComponentAudit,
    HistoricalScoreDimensionContribution,
    HistoricalValuationAssumptionAudit,
    HistoricalValuationMethodAudit,
    evaluate_historical_outcomes,
    read_historical_calibration_csv,
    write_historical_calibration_csv,
)


ASSUMPTIONS = CalibrationAssumptions(
    minimum_total_sample=8,
    minimum_sample_per_group=4,
    maximum_recommendation_concentration=0.75,
    minimum_score_spread=0.20,
    minimum_data_confidence=0.55,
    maximum_error_rate=0.15,
    outcome_bucket_count=5,
    forward_horizon_months=12,
    minimum_historical_observations=10,
    minimum_outcome_coverage=0.90,
    minimum_point_in_time_ratio=0.95,
    minimum_spearman_correlation=0.10,
    minimum_monotonic_bucket_ratio=0.60,
)


def observations(inverse=False, invalid_point_in_time_index=None):
    result = []
    as_of = date(2020, 3, 31)
    for index in range(10):
        score = (index + 1) / 10.0
        excess_return = (1.10 - score if inverse else score) * 0.20
        valid = index != invalid_point_in_time_index
        result.append(
            HistoricalCalibrationObservation(
                ticker=f"T{index}",
                as_of=as_of,
                company_type="tradicional",
                total_score=score,
                recommendation="Observar",
                data_confidence=0.80,
                forward_return=0.05 + excess_return,
                benchmark_return=0.05,
                max_drawdown=-0.30 + score * 0.10,
                point_in_time_validated=valid,
                latest_filing_date=as_of - timedelta(days=15) if valid else as_of + timedelta(days=15),
                risk_free_rate=0.04,
                risk_free_rate_date=as_of - timedelta(days=1),
                equity_risk_premium=0.05,
                erp_reference_year=as_of.year - 1,
                erp_available_date=date(as_of.year, 1, 15),
                macro_point_in_time_validated=True,
                discount_rate=0.085,
                discount_rate_label="WACC",
                wacc=0.085,
                cost_of_equity=0.095,
                cost_of_capital_method="market_value_wacc",
                cost_of_capital_confidence=0.81,
                cost_of_capital_is_fallback=False,
            )
        )
    return result


class HistoricalCalibrationTests(unittest.TestCase):
    def test_monotonic_forward_outcomes_pass_controls(self):
        summary = evaluate_historical_outcomes(observations(), ASSUMPTIONS)

        self.assertTrue(summary.is_ready_for_weight_changes)
        self.assertAlmostEqual(summary.spearman_score_to_excess_return, 1.0)
        self.assertEqual(len(summary.buckets), 5)
        self.assertAlmostEqual(summary.monotonic_bucket_ratio, 1.0)

    def test_invalid_point_in_time_coverage_blocks_calibration(self):
        summary = evaluate_historical_outcomes(
            observations(invalid_point_in_time_index=0),
            ASSUMPTIONS,
        )

        self.assertFalse(summary.is_ready_for_weight_changes)
        self.assertAlmostEqual(summary.point_in_time_ratio, 0.90)
        self.assertTrue(any("point-in-time" in item for item in summary.warnings))

    def test_missing_macro_rate_or_applied_discount_rate_invalidates_observation(self):
        original = observations()[0]

        self.assertFalse(replace(original, risk_free_rate=None).is_point_in_time_valid)
        self.assertFalse(replace(original, equity_risk_premium=None).is_point_in_time_valid)
        self.assertFalse(replace(original, discount_rate=None).is_point_in_time_valid)

    def test_inverse_score_relationship_blocks_calibration(self):
        summary = evaluate_historical_outcomes(observations(inverse=True), ASSUMPTIONS)

        self.assertFalse(summary.is_ready_for_weight_changes)
        self.assertAlmostEqual(summary.spearman_score_to_excess_return, -1.0)
        self.assertEqual(summary.monotonic_bucket_ratio, 0.0)

    def test_equal_scores_are_not_split_between_buckets(self):
        tied = [
            replace(observation, total_score=(index // 2 + 1) / 5.0)
            for index, observation in enumerate(observations())
        ]
        summary = evaluate_historical_outcomes(tied, ASSUMPTIONS)

        self.assertEqual(len(summary.buckets), 5)
        self.assertTrue(all(bucket.min_score == bucket.max_score for bucket in summary.buckets))

    def test_csv_preserves_point_in_time_audit_fields(self):
        original = replace(
            observations()[0],
            total_score=0.585,
            benchmark_ticker="SPY",
            price_start_date=date(2020, 4, 1),
            price_end_date=date(2021, 4, 1),
            price_source="tiingo_eod:TEST;yfinance_historical",
            filing_accession="0000000000-20-000001",
            fundamental_coverage=0.85,
            is_cyclical=True,
            cyclical_normalization_applied=True,
            cyclical_normalization_years=8,
            cyclical_normalization_confidence=0.79,
            cycle_position="acima_do_meio_do_ciclo",
            current_fcff=125.0,
            normalized_fcff=95.0,
            normalized_operating_margin=0.14,
            normalized_reinvestment_margin=0.06,
            benchmark_group="tradicionais_ciclicas",
            sector_bucket="industrial_machinery",
            critical_metric_coverage=1.0,
            missing_critical_metrics="",
            analysis_input_validated=True,
            security_cik="0000001234",
            universe_status="acquired",
            outcome_method="cash_acquisition_reinvested_in_benchmark",
            lifecycle_event_type="cash_acquisition",
            lifecycle_event_date=date(2020, 8, 1),
            stock_terminal_date=date(2020, 7, 31),
            terminal_value_per_share=34.0,
            lifecycle_source_url="https://www.sec.gov/Archives/edgar/data/1234/filing.htm",
            dimension_valuation_score=0.31,
            dimension_valuation_confidence=0.71,
            dimension_growth_score=0.62,
            dimension_growth_confidence=0.72,
            dimension_quality_score=0.53,
            dimension_quality_confidence=0.73,
            dimension_debt_score=0.74,
            dimension_debt_confidence=0.74,
            dimension_liquidity_score=0.85,
            dimension_liquidity_confidence=0.75,
            dimension_data_confidence_score=0.80,
            dimension_data_confidence_confidence=0.80,
            calculated_wacc=0.0845,
            beta=0.95,
            pre_tax_cost_of_debt=0.06,
            after_tax_cost_of_debt=0.045,
            tax_rate=0.25,
            market_value_equity=800.0,
            debt_value=200.0,
            equity_weight=0.80,
            debt_weight=0.20,
            cost_of_capital_sources=(
                ("beta", "Beta historico point-in-time"),
                ("discount_rate", "WACC calculado pelo modelo"),
            ),
            cost_of_capital_component_confidences=(
                ("beta", 0.82),
                ("discount_rate", 0.81),
            ),
            cost_of_capital_component_fallbacks=(
                ("beta", False),
                ("discount_rate", False),
            ),
            cost_of_capital_notes=("WACC auditado.",),
            valuation_price=100.0,
            recommendation_before_gates="Comprar",
            recommendation_gate_code="buy_blocked_low_valuation",
            recommendation_gate_triggered=True,
            recommendation_gate_explanation="Compra bloqueada por valuation.",
            recommendation_buy_threshold=0.70,
            recommendation_watch_threshold=0.45,
            recommendation_min_valuation_score_for_buy=0.45,
            recommendation_avoid_if_valuation_below=0.20,
            recommendation_avoid_if_quality_below=0.30,
            score_model_version="multifactor_score_v1",
            score_config_fingerprint="a" * 64,
            score_configured_weights=(
                ("valuation", 0.25),
                ("growth", 0.15),
                ("quality", 0.25),
                ("debt", 0.15),
                ("liquidity", 0.10),
                ("data_confidence", 0.10),
            ),
            score_normalized_weights=(
                ("valuation", 0.25),
                ("growth", 0.15),
                ("quality", 0.25),
                ("debt", 0.15),
                ("liquidity", 0.10),
                ("data_confidence", 0.10),
            ),
            score_weighted_total=0.585,
            score_reconciliation_difference=0.0,
            score_dimension_contributions=(
                HistoricalScoreDimensionContribution(
                    "valuation", 0.40, 0.80, 0.25, 0.25, 0.10
                ),
                HistoricalScoreDimensionContribution(
                    "growth", 0.60, 0.80, 0.15, 0.15, 0.09
                ),
                HistoricalScoreDimensionContribution(
                    "quality", 0.80, 0.80, 0.25, 0.25, 0.20
                ),
                HistoricalScoreDimensionContribution(
                    "debt", 0.50, 0.80, 0.15, 0.15, 0.075
                ),
                HistoricalScoreDimensionContribution(
                    "liquidity", 0.50, 0.80, 0.10, 0.10, 0.05
                ),
                HistoricalScoreDimensionContribution(
                    "data_confidence", 0.70, 0.80, 0.10, 0.10, 0.07
                ),
            ),
            score_component_audit=(
                HistoricalScoreComponentAudit(
                    "growth",
                    "dimension",
                    "revenue_growth",
                    0.10,
                    0.50,
                    1.0,
                    1.0,
                    0.50,
                    0.80,
                    "sec_edgar",
                    True,
                ),
                HistoricalScoreComponentAudit(
                    "growth",
                    "dimension",
                    "fcff_growth",
                    None,
                    None,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    "missing",
                    False,
                    "Metrica indisponivel.",
                ),
            ),
            valuation_method_audit=(
                HistoricalValuationMethodAudit(
                    method="dcf_fcff",
                    used_in_score=True,
                    fair_value_per_share=120.0,
                    margin_of_safety=0.20,
                    confidence=0.82,
                    source="derived",
                    enterprise_value=12_500.0,
                    equity_value=12_000.0,
                    model_outputs=(
                        ("pv_explicit_stage", 4_000.0),
                        ("pv_terminal_value", 8_500.0),
                        ("terminal_value_share", 0.68),
                    ),
                    assumptions=(
                        HistoricalValuationAssumptionAudit(
                            name="discount_rate",
                            input_value=0.085,
                            effective_value=0.085,
                            source="historical_wacc",
                            confidence=0.81,
                            is_fallback=False,
                            note="WACC point-in-time",
                            formula="market_value_wacc",
                        ),
                        HistoricalValuationAssumptionAudit(
                            name="terminal_growth_rate",
                            input_value=None,
                            effective_value=0.025,
                            source="fallback",
                            confidence=0.45,
                            is_fallback=True,
                            note="Premissa padrao de config.py",
                        ),
                    ),
                ),
                HistoricalValuationMethodAudit(
                    method="graham",
                    used_in_score=False,
                    fair_value_per_share=None,
                    margin_of_safety=None,
                    confidence=0.0,
                    source="derived",
                    exclusion_reason="missing EPS",
                ),
            ),
        )
        with TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "history.csv"
            write_historical_calibration_csv([original], path)
            restored = read_historical_calibration_csv(path)[0]

        self.assertEqual(restored.benchmark_ticker, "SPY")
        self.assertEqual(restored.score_model_version, "multifactor_score_v1")
        self.assertEqual(restored.score_config_fingerprint, "a" * 64)
        self.assertAlmostEqual(
            sum(dict(restored.score_normalized_weights).values()),
            1.0,
        )
        self.assertAlmostEqual(restored.score_weighted_total, 0.585)
        self.assertAlmostEqual(restored.score_reconciliation_difference, 0.0)
        self.assertEqual(len(restored.score_dimension_contributions), 6)
        self.assertEqual(len(restored.score_component_audit), 2)
        self.assertEqual(restored.score_component_audit[0].source, "sec_edgar")
        self.assertTrue(restored.score_component_audit[0].used)
        self.assertIsNone(restored.score_component_audit[1].raw_value)
        self.assertFalse(restored.score_component_audit[1].used)
        self.assertAlmostEqual(
            sum(
                item.weighted_contribution
                for item in restored.score_dimension_contributions
            ),
            restored.total_score,
        )
        self.assertEqual(restored.price_start_date, date(2020, 4, 1))
        self.assertEqual(restored.price_end_date, date(2021, 4, 1))
        self.assertEqual(
            restored.price_source,
            "tiingo_eod:TEST;yfinance_historical",
        )
        self.assertEqual(restored.filing_accession, "0000000000-20-000001")
        self.assertAlmostEqual(restored.fundamental_coverage, 0.85)
        self.assertAlmostEqual(restored.risk_free_rate, 0.04)
        self.assertEqual(restored.risk_free_rate_date, date(2020, 3, 30))
        self.assertAlmostEqual(restored.equity_risk_premium, 0.05)
        self.assertEqual(restored.erp_reference_year, 2019)
        self.assertEqual(restored.erp_available_date, date(2020, 1, 15))
        self.assertTrue(restored.macro_point_in_time_validated)
        self.assertAlmostEqual(restored.discount_rate, 0.085)
        self.assertEqual(restored.discount_rate_label, "WACC")
        self.assertAlmostEqual(restored.wacc, 0.085)
        self.assertAlmostEqual(restored.cost_of_equity, 0.095)
        self.assertEqual(restored.cost_of_capital_method, "market_value_wacc")
        self.assertAlmostEqual(restored.cost_of_capital_confidence, 0.81)
        self.assertFalse(restored.cost_of_capital_is_fallback)
        self.assertTrue(restored.is_cyclical)
        self.assertTrue(restored.cyclical_normalization_applied)
        self.assertEqual(restored.cyclical_normalization_years, 8)
        self.assertAlmostEqual(restored.cyclical_normalization_confidence, 0.79)
        self.assertEqual(restored.cycle_position, "acima_do_meio_do_ciclo")
        self.assertAlmostEqual(restored.current_fcff, 125.0)
        self.assertAlmostEqual(restored.normalized_fcff, 95.0)
        self.assertAlmostEqual(restored.normalized_operating_margin, 0.14)
        self.assertAlmostEqual(restored.normalized_reinvestment_margin, 0.06)
        self.assertEqual(restored.benchmark_group, "tradicionais_ciclicas")
        self.assertEqual(restored.sector_bucket, "industrial_machinery")
        self.assertEqual(restored.critical_metric_coverage, 1.0)
        self.assertEqual(restored.missing_critical_metrics, "")
        self.assertTrue(restored.analysis_input_validated)
        self.assertEqual(restored.security_cik, "0000001234")
        self.assertEqual(restored.universe_status, "acquired")
        self.assertEqual(
            restored.outcome_method,
            "cash_acquisition_reinvested_in_benchmark",
        )
        self.assertEqual(restored.lifecycle_event_type, "cash_acquisition")
        self.assertEqual(restored.lifecycle_event_date, date(2020, 8, 1))
        self.assertEqual(restored.stock_terminal_date, date(2020, 7, 31))
        self.assertEqual(restored.terminal_value_per_share, 34.0)
        self.assertIn("sec.gov", restored.lifecycle_source_url)
        self.assertAlmostEqual(restored.dimension_valuation_score, 0.31)
        self.assertAlmostEqual(restored.dimension_valuation_confidence, 0.71)
        self.assertAlmostEqual(restored.dimension_growth_score, 0.62)
        self.assertAlmostEqual(restored.dimension_growth_confidence, 0.72)
        self.assertAlmostEqual(restored.dimension_quality_score, 0.53)
        self.assertAlmostEqual(restored.dimension_quality_confidence, 0.73)
        self.assertAlmostEqual(restored.dimension_debt_score, 0.74)
        self.assertAlmostEqual(restored.dimension_debt_confidence, 0.74)
        self.assertAlmostEqual(restored.dimension_liquidity_score, 0.85)
        self.assertAlmostEqual(restored.dimension_liquidity_confidence, 0.75)
        self.assertAlmostEqual(restored.dimension_data_confidence_score, 0.80)
        self.assertAlmostEqual(
            restored.dimension_data_confidence_confidence,
            0.80,
        )
        self.assertAlmostEqual(restored.calculated_wacc, 0.0845)
        self.assertAlmostEqual(restored.beta, 0.95)
        self.assertAlmostEqual(restored.pre_tax_cost_of_debt, 0.06)
        self.assertAlmostEqual(restored.after_tax_cost_of_debt, 0.045)
        self.assertAlmostEqual(restored.tax_rate, 0.25)
        self.assertAlmostEqual(restored.market_value_equity, 800.0)
        self.assertAlmostEqual(restored.debt_value, 200.0)
        self.assertAlmostEqual(restored.equity_weight, 0.80)
        self.assertAlmostEqual(restored.debt_weight, 0.20)
        self.assertEqual(
            dict(restored.cost_of_capital_sources)["discount_rate"],
            "WACC calculado pelo modelo",
        )
        self.assertAlmostEqual(
            dict(restored.cost_of_capital_component_confidences)["beta"],
            0.82,
        )
        self.assertFalse(
            dict(restored.cost_of_capital_component_fallbacks)["discount_rate"]
        )
        self.assertEqual(restored.cost_of_capital_notes, ("WACC auditado.",))
        self.assertAlmostEqual(restored.valuation_price, 100.0)
        self.assertEqual(restored.recommendation_before_gates, "Comprar")
        self.assertEqual(
            restored.recommendation_gate_code,
            "buy_blocked_low_valuation",
        )
        self.assertTrue(restored.recommendation_gate_triggered)
        self.assertEqual(
            restored.recommendation_gate_explanation,
            "Compra bloqueada por valuation.",
        )
        self.assertAlmostEqual(restored.recommendation_buy_threshold, 0.70)
        self.assertAlmostEqual(restored.recommendation_watch_threshold, 0.45)
        self.assertAlmostEqual(
            restored.recommendation_min_valuation_score_for_buy,
            0.45,
        )
        self.assertAlmostEqual(
            restored.recommendation_avoid_if_valuation_below,
            0.20,
        )
        self.assertAlmostEqual(
            restored.recommendation_avoid_if_quality_below,
            0.30,
        )
        self.assertEqual(len(restored.valuation_method_audit), 2)
        self.assertTrue(restored.valuation_method_audit[0].used_in_score)
        self.assertAlmostEqual(
            restored.valuation_method_audit[0].margin_of_safety,
            0.20,
        )
        dcf_audit = restored.valuation_method_audit[0]
        self.assertAlmostEqual(dcf_audit.enterprise_value, 12_500.0)
        self.assertAlmostEqual(dcf_audit.equity_value, 12_000.0)
        self.assertAlmostEqual(
            dict(dcf_audit.model_outputs)["terminal_value_share"],
            0.68,
        )
        self.assertEqual(len(dcf_audit.assumptions), 2)
        self.assertEqual(dcf_audit.assumptions[0].source, "historical_wacc")
        self.assertFalse(dcf_audit.assumptions[0].is_fallback)
        self.assertIsNone(dcf_audit.assumptions[1].input_value)
        self.assertAlmostEqual(dcf_audit.assumptions[1].effective_value, 0.025)
        self.assertTrue(dcf_audit.assumptions[1].is_fallback)
        self.assertEqual(
            restored.valuation_method_audit[1].exclusion_reason,
            "missing EPS",
        )

    def test_legacy_csv_infers_only_the_existing_data_confidence_dimension(self):
        legacy_csv = (
            "ticker,as_of,company_type,total_score,recommendation,data_confidence,"
            "forward_return,benchmark_return,max_drawdown,point_in_time_validated\n"
            "OLD,2020-03-31,tradicional,0.61,Observar,0.77,0.10,0.04,-0.20,1\n"
        )
        with TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "legacy.csv"
            path.write_text(legacy_csv, encoding="utf-8")
            restored = read_historical_calibration_csv(path)[0]

        self.assertIsNone(restored.dimension_valuation_score)
        self.assertIsNone(restored.dimension_growth_score)
        self.assertIsNone(restored.dimension_quality_score)
        self.assertIsNone(restored.dimension_debt_score)
        self.assertIsNone(restored.dimension_liquidity_score)
        self.assertAlmostEqual(restored.dimension_data_confidence_score, 0.77)
        self.assertAlmostEqual(
            restored.dimension_data_confidence_confidence,
            0.77,
        )
        self.assertIsNone(restored.calculated_wacc)
        self.assertIsNone(restored.beta)
        self.assertIsNone(restored.pre_tax_cost_of_debt)
        self.assertEqual(restored.cost_of_capital_sources, ())
        self.assertEqual(restored.cost_of_capital_component_confidences, ())
        self.assertEqual(restored.cost_of_capital_component_fallbacks, ())
        self.assertEqual(restored.cost_of_capital_notes, ())
        self.assertIsNone(restored.valuation_price)
        self.assertEqual(restored.recommendation_before_gates, "")
        self.assertEqual(restored.recommendation_gate_code, "")
        self.assertFalse(restored.recommendation_gate_triggered)
        self.assertIsNone(restored.recommendation_buy_threshold)
        self.assertEqual(restored.valuation_method_audit, ())
        self.assertEqual(restored.score_model_version, "")
        self.assertEqual(restored.score_config_fingerprint, "")
        self.assertEqual(restored.score_configured_weights, ())
        self.assertEqual(restored.score_normalized_weights, ())
        self.assertIsNone(restored.score_weighted_total)
        self.assertIsNone(restored.score_reconciliation_difference)
        self.assertEqual(restored.score_dimension_contributions, ())
        self.assertEqual(restored.score_component_audit, ())

    def test_previous_method_audit_schema_remains_readable(self):
        legacy_csv = (
            "ticker,as_of,company_type,total_score,recommendation,data_confidence,"
            "forward_return,benchmark_return,max_drawdown,point_in_time_validated,"
            "valuation_method_audit\n"
            'OLD,2020-03-31,tradicional,0.61,Observar,0.77,0.10,0.04,-0.20,1,'
            '"[{""method"":""dcf_fcff"",""used_in_score"":true,'
            '""fair_value_per_share"":120.0,""margin_of_safety"":0.20,'
            '""confidence"":0.82,""source"":""derived""}]"\n'
        )
        with TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "legacy_method_audit.csv"
            path.write_text(legacy_csv, encoding="utf-8")
            restored = read_historical_calibration_csv(path)[0]

        self.assertEqual(len(restored.valuation_method_audit), 1)
        method = restored.valuation_method_audit[0]
        self.assertEqual(method.method, "dcf_fcff")
        self.assertTrue(method.used_in_score)
        self.assertIsNone(method.enterprise_value)
        self.assertIsNone(method.equity_value)
        self.assertEqual(method.model_outputs, ())
        self.assertEqual(method.assumptions, ())


if __name__ == "__main__":
    unittest.main()
