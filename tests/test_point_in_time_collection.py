import tempfile
import unittest
from dataclasses import replace
from datetime import date

from fundamental_analysis.benchmark_universe import BenchmarkCase
from fundamental_analysis.config import POINT_IN_TIME
from fundamental_analysis.data_sources import metric_value
from fundamental_analysis.historical_macro import HistoricalMacroSnapshot
from fundamental_analysis.historical_prices import PricePoint, PriceSeries
from fundamental_analysis.point_in_time_collection import (
    collect_benchmark_history,
    collect_point_in_time_observation,
)
from fundamental_analysis.sec_edgar import SecEdgarClient
from tests.sec_fixtures import company_facts_fixture, ticker_map_fixture


class StaticPriceProvider:
    def __init__(self):
        dates = [
            "2024-02-12",
            "2024-02-13",
            "2024-02-14",
            "2024-02-19",
            "2024-03-01",
            "2024-03-18",
        ]
        self.series = {
            "TEST": PriceSeries(
                "TEST",
                tuple(PricePoint(date.fromisoformat(day), value) for day, value in zip(dates, [9, 9.5, 9.2, 10, 9, 12])),
                "fixture",
            ),
            "SPY": PriceSeries(
                "SPY",
                tuple(PricePoint(date.fromisoformat(day), value) for day, value in zip(dates, [99, 100, 99.5, 100, 102, 105])),
                "fixture",
            ),
        }

    def fetch_series(self, ticker, start, end):
        return self.series[ticker].between(start, end)


class StaticMacroProvider:
    def snapshot(self, as_of):
        available_from = date(as_of.year, 1, 15)
        return HistoricalMacroSnapshot(
            as_of=as_of,
            risk_free_rate=metric_value(
                "risk_free_rate",
                0.04,
                "us_treasury_historical",
                period_end=as_of,
            ),
            equity_risk_premium=metric_value(
                "equity_risk_premium",
                0.05,
                "damodaran_historical_erp",
                period_end=date(as_of.year - 1, 12, 31),
                filing_date=available_from,
            ),
            risk_free_observation_date=as_of,
            erp_reference_year=as_of.year - 1,
            erp_available_from=available_from,
            point_in_time_valid=True,
        )


class PointInTimeCollectionTests(unittest.TestCase):
    def test_builds_auditable_observation_without_current_peer_data(self):
        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else company_facts_fixture()

        assumptions = replace(
            POINT_IN_TIME,
            forward_horizon_months=1,
            beta_lookback_months=1,
            minimum_beta_return_observations=2,
            benchmark_by_group=(("tradicionais_ciclicas", "SPY"),),
        )
        case = BenchmarkCase(
            "TEST",
            "tradicionais_ciclicas",
            "industrial_machinery",
            "Fixture industrial",
            is_cyclical=True,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            sec_client = SecEdgarClient(
                "Test Research test@example.com",
                assumptions=assumptions,
                cache_dir=tempdir,
                json_getter=get_json,
            )
            anchor = sec_client.list_annual_filings("TEST", end_year=2024)[0]
            result = collect_point_in_time_observation(
                case,
                anchor,
                sec_client,
                StaticPriceProvider(),
                StaticMacroProvider(),
                assumptions=assumptions,
            )

        self.assertEqual(result.error, "")
        self.assertIsNotNone(result.observation)
        observation = result.observation
        self.assertEqual(observation.filing_accession, "0000001234-24-000001")
        self.assertEqual(observation.latest_filing_date, date(2024, 2, 15))
        self.assertEqual(observation.as_of, date(2024, 2, 16))
        self.assertEqual(observation.price_start_date, date(2024, 2, 19))
        self.assertEqual(observation.benchmark_ticker, "SPY")
        self.assertAlmostEqual(observation.forward_return, 0.20)
        self.assertAlmostEqual(observation.risk_free_rate, 0.04)
        self.assertAlmostEqual(observation.equity_risk_premium, 0.05)
        self.assertTrue(observation.macro_point_in_time_validated)
        self.assertIsNotNone(observation.discount_rate)
        self.assertIn(observation.discount_rate_label, {"WACC", "Custo do patrimonio (Ke)"})
        self.assertIsNotNone(observation.cost_of_equity)
        self.assertTrue(observation.cost_of_capital_method)
        self.assertIsNotNone(observation.cost_of_capital_confidence)
        self.assertTrue(observation.is_point_in_time_valid)
        self.assertTrue(observation.is_cyclical)
        self.assertFalse(observation.cyclical_normalization_applied)
        self.assertEqual(observation.cyclical_normalization_years, 1)
        self.assertIsNotNone(observation.current_fcff)
        self.assertIsNone(observation.normalized_fcff)

    def test_incomplete_forward_window_is_skipped_instead_of_reported_as_error(self):
        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else company_facts_fixture()

        assumptions = replace(
            POINT_IN_TIME,
            forward_horizon_months=1,
            benchmark_by_group=(("tradicionais_ciclicas", "SPY"),),
        )
        case = BenchmarkCase("TEST", "tradicionais_ciclicas", "industrial_machinery", "Fixture")
        with tempfile.TemporaryDirectory() as tempdir:
            sec_client = SecEdgarClient(
                "Test Research test@example.com",
                assumptions=assumptions,
                cache_dir=tempdir,
                json_getter=get_json,
            )
            dataset = collect_benchmark_history(
                sec_client,
                StaticPriceProvider(),
                StaticMacroProvider(),
                cases=[case],
                start_year=2024,
                end_year=2024,
                max_filings_per_company=1,
                assumptions=assumptions,
                outcomes_available_through=date(2024, 2, 20),
            )

        self.assertEqual(len(dataset.results), 1)
        self.assertEqual(len(dataset.skipped), 1)
        self.assertEqual(len(dataset.errors), 0)


if __name__ == "__main__":
    unittest.main()
