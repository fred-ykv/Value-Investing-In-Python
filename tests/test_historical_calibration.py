import unittest
from dataclasses import replace
from datetime import date, timedelta

from fundamental_analysis.config import CalibrationAssumptions
from fundamental_analysis.historical_calibration import (
    HistoricalCalibrationObservation,
    evaluate_historical_outcomes,
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


if __name__ == "__main__":
    unittest.main()

