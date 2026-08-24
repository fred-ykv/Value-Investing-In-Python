import unittest
from datetime import date, timedelta

from fundamental_analysis.config import CalibrationAssumptions
from fundamental_analysis.historical_calibration import HistoricalCalibrationObservation
from fundamental_analysis.out_of_sample_validation import (
    evaluate_out_of_sample_validation,
    out_of_sample_payload,
    render_out_of_sample_markdown,
    split_temporal_observations,
)


ASSUMPTIONS = CalibrationAssumptions(
    minimum_total_sample=4,
    minimum_sample_per_group=2,
    maximum_recommendation_concentration=1.0,
    minimum_score_spread=0.0,
    minimum_data_confidence=0.0,
    maximum_error_rate=1.0,
    outcome_bucket_count=2,
    forward_horizon_months=12,
    minimum_historical_observations=8,
    minimum_outcome_coverage=1.0,
    minimum_point_in_time_ratio=1.0,
    minimum_spearman_correlation=0.5,
    minimum_monotonic_bucket_ratio=1.0,
    validation_start_year=2022,
    minimum_calibration_observations=4,
    minimum_validation_observations=4,
    minimum_observations_per_group_per_split=2,
    minimum_distinct_tickers_per_group_per_split=2,
)


def observation(
    ticker,
    as_of,
    price_end,
    score,
    excess_return,
    group,
):
    return HistoricalCalibrationObservation(
        ticker=ticker,
        as_of=as_of,
        company_type="tradicional",
        total_score=score,
        recommendation="Comprar" if score >= 0.7 else "Observar",
        data_confidence=0.8,
        forward_return=0.05 + excess_return,
        benchmark_return=0.05,
        max_drawdown=-0.30 + score * 0.10,
        point_in_time_validated=True,
        latest_filing_date=as_of - timedelta(days=1),
        price_start_date=as_of,
        price_end_date=price_end,
        risk_free_rate=0.04,
        risk_free_rate_date=as_of - timedelta(days=1),
        equity_risk_premium=0.05,
        erp_available_date=date(as_of.year, 1, 15),
        macro_point_in_time_validated=True,
        discount_rate=0.09,
        benchmark_group=group,
        sector_bucket="fixture",
    )


class OutOfSampleValidationTests(unittest.TestCase):
    def build_observations(self):
        calibration = [
            observation(
                f"C{index}",
                date(2019 + index % 2, 3, 1),
                date(2020 + index % 2, 3, 1),
                0.4 + index * 0.1,
                -0.04 + index * 0.03,
                "group_a" if index % 2 == 0 else "group_b",
            )
            for index in range(4)
        ]
        validation = [
            observation(
                f"V{index}",
                date(2022 + index % 2, 3, 1),
                date(2023 + index % 2, 3, 1),
                0.4 + index * 0.1,
                -0.03 + index * 0.03,
                "group_a" if index % 2 == 0 else "group_b",
            )
            for index in range(4)
        ]
        embargoed = observation(
            "E0",
            date(2021, 6, 1),
            date(2022, 6, 1),
            0.6,
            0.01,
            "group_a",
        )
        return [*calibration, embargoed, *validation]

    def test_temporal_split_embargoes_overlapping_forward_outcome(self):
        calibration, validation, embargoed = split_temporal_observations(
            self.build_observations(),
            date(2022, 1, 1),
        )

        self.assertEqual(len(calibration), 4)
        self.assertEqual(len(validation), 4)
        self.assertEqual([item.ticker for item in embargoed], ["E0"])
        self.assertTrue(all(item.price_end_date < date(2022, 1, 1) for item in calibration))
        self.assertTrue(all(item.as_of >= date(2022, 1, 1) for item in validation))

    def test_report_requires_both_splits_and_group_coverage(self):
        report = evaluate_out_of_sample_validation(
            self.build_observations(),
            ASSUMPTIONS,
        )

        self.assertTrue(report.is_ready_for_recalibration)
        self.assertEqual(report.calibration_summary.spearman_score_to_excess_return, 1.0)
        self.assertEqual(report.validation_summary.spearman_score_to_excess_return, 1.0)
        group_segments = [
            segment for segment in report.segments if segment.dimension == "benchmark_group"
        ]
        self.assertEqual(len(group_segments), 4)
        self.assertIn("Inicio do holdout: 2022-01-01", render_out_of_sample_markdown(report))
        self.assertTrue(out_of_sample_payload(report)["is_ready_for_recalibration"])

    def test_missing_group_in_calibration_blocks_readiness(self):
        observations = [
            item
            for item in self.build_observations()
            if not (item.as_of < date(2022, 1, 1) and item.benchmark_group == "group_b")
        ]

        report = evaluate_out_of_sample_validation(observations, ASSUMPTIONS)

        self.assertFalse(report.is_ready_for_recalibration)
        self.assertTrue(
            any("Calibracao/group_b" in warning for warning in report.warnings)
        )


if __name__ == "__main__":
    unittest.main()
