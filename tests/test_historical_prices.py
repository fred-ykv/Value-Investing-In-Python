import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from fundamental_analysis.benchmark_universe import HistoricalLifecycleEvent
from fundamental_analysis.config import POINT_IN_TIME
from fundamental_analysis.historical_prices import (
    CsvHistoricalPriceClient,
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

    def test_normalized_csv_requires_permanent_identity_and_source(self):
        content = (
            "security_id,issuer_cik,ticker,date,adjusted_close,raw_close,source\n"
            "PERMNO_12345,0000001234,OLD,2021-01-04,10.5,11.0,licensed_fixture\n"
            "PERMNO_12345,0000001234,OLD,2021-01-05,11.0,11.5,licensed_fixture\n"
        )
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "prices.csv"
            path.write_text(content, encoding="utf-8")
            client = CsvHistoricalPriceClient(path)
            loaded = client.fetch_series(
                "OLD",
                date(2021, 1, 1),
                date(2021, 1, 31),
            )

        self.assertEqual(len(loaded.points), 2)
        self.assertEqual(loaded.security_id, "PERMNO_12345")
        self.assertEqual(loaded.issuer_cik, "0000001234")
        self.assertIn("licensed_fixture", loaded.source)

    def test_expected_cik_rejects_reused_ticker_series(self):
        provider = StaticPriceProvider(
            {
                "OLD": PriceSeries(
                    "OLD",
                    (
                        PricePoint(date(2024, 1, 5), 100, 100),
                        PricePoint(date(2024, 2, 5), 110, 110),
                    ),
                    "licensed_fixture",
                    "PERMNO_12345",
                    "0000009999",
                ),
                "SPY": series(
                    "SPY",
                    [("2024-01-05", 100), ("2024-02-05", 105)],
                ),
            }
        )

        with self.assertRaisesRegex(LookupError, "esperado 0000001234"):
            calculate_price_outcome(
                "OLD",
                "SPY",
                date(2024, 1, 4),
                provider,
                replace(POINT_IN_TIME, forward_horizon_months=1),
                expected_cik="0000001234",
            )

    def test_cash_acquisition_is_reinvested_in_benchmark_to_full_horizon(self):
        provider = StaticPriceProvider(
            {
                "OLD": PriceSeries(
                    "OLD",
                    (
                        PricePoint(date(2024, 1, 2), 95, 95),
                        PricePoint(date(2024, 1, 3), 98, 98),
                        PricePoint(date(2024, 1, 5), 100, 100),
                        PricePoint(date(2024, 1, 20), 80, 80),
                        PricePoint(date(2024, 1, 31), 90, 90),
                    ),
                    "licensed_fixture",
                ),
                "SPY": PriceSeries(
                    "SPY",
                    (
                        PricePoint(date(2024, 1, 2), 96, 96),
                        PricePoint(date(2024, 1, 3), 98, 98),
                        PricePoint(date(2024, 1, 5), 100, 100),
                        PricePoint(date(2024, 1, 20), 105, 105),
                        PricePoint(date(2024, 1, 31), 110, 110),
                        PricePoint(date(2024, 3, 4), 121, 121),
                    ),
                    "licensed_fixture",
                ),
            }
        )
        assumptions = replace(
            POINT_IN_TIME,
            forward_horizon_months=2,
            beta_lookback_months=1,
            minimum_beta_return_observations=2,
        )
        event = HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2024, 1, 31),
            120.0,
            "https://www.sec.gov/Archives/edgar/data/1234/filing.htm",
            "0000001234-24-000001",
        )

        outcome = calculate_price_outcome(
            "OLD",
            "SPY",
            date(2024, 1, 4),
            provider,
            assumptions,
            lifecycle_event=event,
        )

        self.assertAlmostEqual(outcome.forward_return, 0.32)
        self.assertAlmostEqual(outcome.benchmark_return, 0.21)
        self.assertAlmostEqual(outcome.max_drawdown, -0.20)
        self.assertEqual(outcome.price_end_date, date(2024, 3, 4))
        self.assertEqual(outcome.stock_terminal_date, date(2024, 1, 31))
        self.assertEqual(
            outcome.outcome_method,
            "cash_acquisition_reinvested_in_benchmark",
        )

    def test_cancelled_equity_records_total_loss(self):
        provider = StaticPriceProvider(
            {
                "FAIL": PriceSeries(
                    "FAIL",
                    (
                        PricePoint(date(2024, 1, 2), 95, 95),
                        PricePoint(date(2024, 1, 3), 98, 98),
                        PricePoint(date(2024, 1, 5), 100, 100),
                        PricePoint(date(2024, 1, 30), 10, 10),
                    ),
                    "licensed_fixture",
                ),
                "SPY": PriceSeries(
                    "SPY",
                    (
                        PricePoint(date(2024, 1, 2), 96, 96),
                        PricePoint(date(2024, 1, 3), 98, 98),
                        PricePoint(date(2024, 1, 5), 100, 100),
                        PricePoint(date(2024, 1, 31), 105, 105),
                        PricePoint(date(2024, 3, 4), 110, 110),
                    ),
                    "licensed_fixture",
                ),
            }
        )
        assumptions = replace(
            POINT_IN_TIME,
            forward_horizon_months=2,
            beta_lookback_months=1,
            minimum_beta_return_observations=2,
        )
        event = HistoricalLifecycleEvent(
            "cancelled_zero",
            date(2024, 1, 31),
            0.0,
            "https://www.sec.gov/Archives/edgar/data/1234/plan.htm",
            "0000001234-24-000002",
        )

        outcome = calculate_price_outcome(
            "FAIL",
            "SPY",
            date(2024, 1, 4),
            provider,
            assumptions,
            lifecycle_event=event,
        )

        self.assertEqual(outcome.forward_return, -1.0)
        self.assertEqual(outcome.max_drawdown, -1.0)
        self.assertEqual(outcome.outcome_method, "cancelled_zero")
        self.assertEqual(outcome.terminal_value_per_share, 0.0)


if __name__ == "__main__":
    unittest.main()
