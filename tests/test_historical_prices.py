import unittest
from dataclasses import replace
from datetime import date

from fundamental_analysis.config import POINT_IN_TIME
from fundamental_analysis.historical_prices import (
    PricePoint,
    PriceSeries,
    calculate_price_outcome,
    yfinance_price_points,
)


class StaticPriceProvider:
    def __init__(self, series):
        self.series = series

    def fetch_series(self, ticker, start, end):
        return self.series[ticker].between(start, end)


def series(ticker, values):
    return PriceSeries(
        ticker,
        tuple(PricePoint(date.fromisoformat(day), value) for day, value in values),
        "fixture",
    )


class HistoricalPriceTests(unittest.TestCase):
    def test_forward_return_drawdown_and_beta_use_adjusted_history(self):
        provider = StaticPriceProvider(
            {
                "TEST": series(
                    "TEST",
                    [
                        ("2024-01-01", 100),
                        ("2024-01-02", 110),
                        ("2024-01-03", 99),
                        ("2024-01-05", 100),
                        ("2024-01-20", 80),
                        ("2024-02-05", 120),
                    ],
                ),
                "SPY": series(
                    "SPY",
                    [
                        ("2024-01-01", 100),
                        ("2024-01-02", 105),
                        ("2024-01-03", 100),
                        ("2024-01-05", 100),
                        ("2024-01-20", 105),
                        ("2024-02-05", 110),
                    ],
                ),
            }
        )
        assumptions = replace(
            POINT_IN_TIME,
            forward_horizon_months=1,
            beta_lookback_months=1,
            minimum_beta_return_observations=2,
        )

        outcome = calculate_price_outcome(
            "TEST",
            "SPY",
            date(2024, 1, 4),
            provider,
            assumptions,
        )

        self.assertEqual(outcome.price_start_date, date(2024, 1, 5))
        self.assertEqual(outcome.price_end_date, date(2024, 2, 5))
        self.assertAlmostEqual(outcome.forward_return, 0.20)
        self.assertAlmostEqual(outcome.benchmark_return, 0.10)
        self.assertAlmostEqual(outcome.max_drawdown, -0.20)
        self.assertEqual(outcome.beta_observations, 2)
        self.assertIsNotNone(outcome.trailing_beta)

    def test_price_too_far_from_target_date_is_rejected(self):
        provider = StaticPriceProvider(
            {
                "TEST": series("TEST", [("2024-01-20", 100), ("2024-02-20", 110)]),
                "SPY": series("SPY", [("2024-01-20", 100), ("2024-02-20", 105)]),
            }
        )
        assumptions = replace(POINT_IN_TIME, forward_horizon_months=1)

        with self.assertRaises(LookupError):
            calculate_price_outcome(
                "TEST",
                "SPY",
                date(2024, 1, 4),
                provider,
                assumptions,
            )

    def test_raw_close_drives_valuation_while_adjusted_close_drives_return(self):
        provider = StaticPriceProvider(
            {
                "TEST": PriceSeries(
                    "TEST",
                    (
                        PricePoint(date(2024, 1, 5), 50, 100),
                        PricePoint(date(2024, 1, 20), 40, 80),
                        PricePoint(date(2024, 2, 5), 60, 60),
                    ),
                    "fixture",
                ),
                "SPY": PriceSeries(
                    "SPY",
                    (
                        PricePoint(date(2024, 1, 5), 100, 100),
                        PricePoint(date(2024, 1, 20), 105, 105),
                        PricePoint(date(2024, 2, 5), 110, 110),
                    ),
                    "fixture",
                ),
            }
        )
        assumptions = replace(POINT_IN_TIME, forward_horizon_months=1)

        outcome = calculate_price_outcome(
            "TEST",
            "SPY",
            date(2024, 1, 4),
            provider,
            assumptions,
        )

        self.assertEqual(outcome.start_price, 100)
        self.assertEqual(outcome.start_adjusted_price, 50)
        self.assertAlmostEqual(outcome.forward_return, 0.20)
        self.assertAlmostEqual(outcome.max_drawdown, -0.20)

    def test_later_splits_are_reversed_only_for_valuation_price(self):
        import pandas as pd

        frame = pd.DataFrame(
            {
                "Close": [50.0, 50.0, 60.0],
                "Adj Close": [45.0, 46.0, 55.0],
                "Stock Splits": [0.0, 2.0, 0.0],
            },
            index=pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-08"]),
        )

        points = yfinance_price_points(frame)

        self.assertEqual(points[0].valuation_close, 100.0)
        self.assertEqual(points[1].valuation_close, 50.0)
        self.assertEqual(points[2].valuation_close, 60.0)
        self.assertEqual(points[0].adjusted_close, 45.0)


if __name__ == "__main__":
    unittest.main()
