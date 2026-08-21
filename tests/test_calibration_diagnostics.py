import unittest

from fundamental_analysis.benchmark_universe import (
    DEFAULT_BENCHMARK_CASES,
    benchmark_group_counts,
    validate_benchmark_cases,
)
from fundamental_analysis.calibration import CalibrationRow, build_calibration_diagnostics
from fundamental_analysis.config import CalibrationAssumptions


def assumptions(**overrides):
    values = {
        "minimum_total_sample": 8,
        "minimum_sample_per_group": 4,
        "maximum_recommendation_concentration": 0.75,
        "minimum_score_spread": 0.20,
        "minimum_data_confidence": 0.55,
        "maximum_error_rate": 0.15,
        "outcome_bucket_count": 5,
        "forward_horizon_months": 12,
        "minimum_historical_observations": 10,
        "minimum_outcome_coverage": 0.90,
        "minimum_point_in_time_ratio": 0.95,
        "minimum_spearman_correlation": 0.10,
        "minimum_monotonic_bucket_ratio": 0.60,
    }
    values.update(overrides)
    return CalibrationAssumptions(**values)


def row(index, group, score, recommendation="Observar", confidence=0.80, error=""):
    return CalibrationRow(
        ticker=f"T{index}",
        company_type="tradicional",
        recommendation=recommendation,
        total_score=score,
        dimension_scores={
            "valuation": score,
            "quality": min(1.0, score + 0.10),
            "data_confidence": confidence,
        },
        dimension_confidence={"valuation": confidence},
        error=error,
        benchmark_group=group,
    )


class BenchmarkUniverseTests(unittest.TestCase):
    def test_default_universe_is_balanced_and_unique(self):
        validate_benchmark_cases(DEFAULT_BENCHMARK_CASES, minimum_per_group=10)

        self.assertEqual(len(DEFAULT_BENCHMARK_CASES), 40)
        self.assertEqual(set(benchmark_group_counts().values()), {10})


class CalibrationDiagnosticsTests(unittest.TestCase):
    def test_small_sample_is_not_ready_for_weight_changes(self):
        diagnostics = build_calibration_diagnostics(
            [row(1, "grupo_a", 0.40), row(2, "grupo_a", 0.50)],
            assumptions(),
        )

        self.assertFalse(diagnostics.is_ready_for_weight_changes)
        self.assertTrue(any("Amostra valida insuficiente" in item for item in diagnostics.warnings))

    def test_balanced_sample_can_pass_cross_sectional_controls(self):
        rows = [
            row(1, "grupo_a", 0.20, "Evitar"),
            row(2, "grupo_a", 0.30, "Evitar"),
            row(3, "grupo_a", 0.40, "Observar"),
            row(4, "grupo_a", 0.50, "Observar"),
            row(5, "grupo_b", 0.45, "Observar"),
            row(6, "grupo_b", 0.55, "Observar"),
            row(7, "grupo_b", 0.65, "Comprar"),
            row(8, "grupo_b", 0.75, "Comprar"),
        ]

        diagnostics = build_calibration_diagnostics(rows, assumptions())

        self.assertTrue(diagnostics.is_ready_for_weight_changes)
        self.assertEqual(diagnostics.warnings, ())
        self.assertAlmostEqual(diagnostics.score_spread, 0.55)

    def test_quartiles_use_linear_interpolation(self):
        rows = [row(index, "grupo_a", score) for index, score in enumerate([0.10, 0.20, 0.30, 0.40])]
        diagnostics = build_calibration_diagnostics(
            rows,
            assumptions(minimum_total_sample=4, minimum_sample_per_group=4),
        )
        group = diagnostics.group_summaries["grupo_a"]

        self.assertAlmostEqual(group.p25_score, 0.175)
        self.assertAlmostEqual(group.median_score, 0.25)
        self.assertAlmostEqual(group.p75_score, 0.325)

    def test_recommendation_concentration_is_explicit(self):
        rows = [row(index, "grupo_a" if index < 4 else "grupo_b", 0.20 + index * 0.08) for index in range(8)]
        diagnostics = build_calibration_diagnostics(rows, assumptions())

        self.assertFalse(diagnostics.is_ready_for_weight_changes)
        self.assertEqual(diagnostics.dominant_recommendation, "Observar")
        self.assertEqual(diagnostics.recommendation_concentration, 1.0)


if __name__ == "__main__":
    unittest.main()

