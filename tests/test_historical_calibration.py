import unittest
from dataclasses import replace
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

from fundamental_analysis.config import CalibrationAssumptions
from fundamental_analysis.historical_calibration import (
    HistoricalCalibrationObservation,
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
            benchmark_ticker="SPY",
            price_start_date=date(2020, 4, 1),
            price_end_date=date(2021, 4, 1),
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
        )
        with TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "history.csv"
            write_historical_calibration_csv([original], path)
            restored = read_historical_calibration_csv(path)[0]

        self.assertEqual(restored.benchmark_ticker, "SPY")
        self.assertEqual(restored.price_start_date, date(2020, 4, 1))
        self.assertEqual(restored.price_end_date, date(2021, 4, 1))
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


if __name__ == "__main__":
    unittest.main()
