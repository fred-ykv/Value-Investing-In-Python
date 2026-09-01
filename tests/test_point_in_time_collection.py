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
    _critical_metric_audit,
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
        self.assertIn("fixture", observation.price_source)
        self.assertEqual(observation.benchmark_ticker, "SPY")
        self.assertAlmostEqual(observation.forward_return, 0.20)
        self.assertAlmostEqual(observation.risk_free_rate, 0.04)
        self.assertAlmostEqual(observation.equity_risk_premium, 0.05)
        self.assertTrue(observation.macro_point_in_time_validated)
        self.assertIsNotNone(observation.discount_rate)
        self.assertIn(observation.discount_rate_label, {"WACC", "Custo do patrimonio (Ke)"})
        self.assertIsNotNone(observation.cost_of_equity)
        self.assertIsNotNone(observation.beta)
        self.assertIsNotNone(observation.calculated_wacc)
        self.assertIsNotNone(observation.pre_tax_cost_of_debt)
        self.assertIsNotNone(observation.after_tax_cost_of_debt)
        self.assertIsNotNone(observation.tax_rate)
        self.assertIsNotNone(observation.market_value_equity)
        self.assertIsNotNone(observation.debt_value)
        self.assertIsNotNone(observation.equity_weight)
        self.assertIsNotNone(observation.debt_weight)
        self.assertTrue(observation.cost_of_capital_method)
        self.assertIsNotNone(observation.cost_of_capital_confidence)
        self.assertIn("discount_rate", dict(observation.cost_of_capital_sources))
        self.assertIn(
            "discount_rate",
            dict(observation.cost_of_capital_component_confidences),
        )
        self.assertIn(
            "discount_rate",
            dict(observation.cost_of_capital_component_fallbacks),
        )
        self.assertTrue(observation.is_point_in_time_valid)
        self.assertTrue(observation.is_cyclical)
        self.assertFalse(observation.cyclical_normalization_applied)
        self.assertEqual(observation.cyclical_normalization_years, 1)
        self.assertIsNotNone(observation.current_fcff)
        self.assertIsNone(observation.normalized_fcff)
        self.assertEqual(observation.benchmark_group, "tradicionais_ciclicas")
        self.assertEqual(observation.sector_bucket, "industrial_machinery")
        self.assertEqual(observation.critical_metric_coverage, 1.0)
        self.assertTrue(observation.analysis_input_validated)
        self.assertEqual(observation.security_cik, "0000001234")
        self.assertEqual(observation.universe_status, "active")
        self.assertEqual(observation.outcome_method, "market_price_12m")
        dimension_pairs = (
            (
                observation.dimension_valuation_score,
                observation.dimension_valuation_confidence,
            ),
            (
                observation.dimension_growth_score,
                observation.dimension_growth_confidence,
            ),
            (
                observation.dimension_quality_score,
                observation.dimension_quality_confidence,
            ),
            (
                observation.dimension_debt_score,
                observation.dimension_debt_confidence,
            ),
            (
                observation.dimension_liquidity_score,
                observation.dimension_liquidity_confidence,
            ),
            (
                observation.dimension_data_confidence_score,
                observation.dimension_data_confidence_confidence,
            ),
        )
        self.assertTrue(
            all(
                score is not None
                and confidence is not None
                and 0.0 <= score <= 1.0
                and 0.0 <= confidence <= 1.0
                for score, confidence in dimension_pairs
            )
        )
        self.assertAlmostEqual(
            observation.dimension_data_confidence_score,
            observation.data_confidence,
        )
        self.assertAlmostEqual(observation.valuation_price, 10.0)
        self.assertTrue(observation.recommendation_before_gates)
        self.assertIn(
            observation.recommendation_gate_code,
            {"none", "buy_blocked_low_valuation", "avoid_low_valuation_and_quality"},
        )
        self.assertIsNotNone(observation.recommendation_buy_threshold)
        self.assertIsNotNone(observation.recommendation_watch_threshold)
        self.assertTrue(observation.recommendation_gate_explanation)
        self.assertTrue(observation.valuation_method_audit)
        for method in observation.valuation_method_audit:
            self.assertEqual(
                method.used_in_score,
                method.margin_of_safety is not None and method.confidence > 0.0,
            )
            if not method.used_in_score:
                self.assertTrue(method.exclusion_reason)
            self.assertTrue(method.assumptions)
            self.assertTrue(
                all(
                    assumption.name
                    and assumption.source
                    and 0.0 <= assumption.confidence <= 1.0
                    for assumption in method.assumptions
                )
            )
        dcf_audit = next(
            method
            for method in observation.valuation_method_audit
            if method.method == "dcf_fcff"
        )
        dcf_assumptions = {
            assumption.name: assumption for assumption in dcf_audit.assumptions
        }
        self.assertAlmostEqual(
            dcf_assumptions["discount_rate"].effective_value,
            observation.discount_rate,
        )
        self.assertEqual(
            dcf_assumptions["current_price"].effective_value,
            observation.valuation_price,
        )
        self.assertIn("pv_terminal_value", dict(dcf_audit.model_outputs))
        self.assertEqual(observation.score_model_version, "multifactor_score_v1")
        self.assertEqual(len(observation.score_config_fingerprint), 64)
        self.assertEqual(len(observation.score_dimension_contributions), 6)
        self.assertAlmostEqual(
            sum(dict(observation.score_normalized_weights).values()),
            1.0,
        )
        self.assertAlmostEqual(
            observation.score_weighted_total,
            observation.total_score,
        )
        self.assertAlmostEqual(observation.score_reconciliation_difference, 0.0)
        for contribution in observation.score_dimension_contributions:
            self.assertAlmostEqual(
                contribution.score * contribution.normalized_weight,
                contribution.weighted_contribution,
            )
        self.assertTrue(observation.score_component_audit)
        for dimension_score, dimension_name in (
            (observation.dimension_valuation_score, "valuation"),
            (observation.dimension_growth_score, "growth"),
            (observation.dimension_quality_score, "quality"),
            (observation.dimension_debt_score, "debt"),
            (observation.dimension_liquidity_score, "liquidity"),
            (observation.dimension_data_confidence_score, "data_confidence"),
        ):
            reconciled = sum(
                component.weighted_contribution
                for component in observation.score_component_audit
                if component.dimension == dimension_name
                and component.stage == "dimension"
                and component.used
            )
            self.assertAlmostEqual(reconciled, dimension_score)
        self.assertTrue(
            all(component.source for component in observation.score_component_audit)
        )
        fcff_growth = next(
            component
            for component in observation.score_component_audit
            if component.dimension == "growth"
            and component.component == "fcff_growth"
        )
        self.assertTrue(fcff_growth.used)
        self.assertEqual(fcff_growth.source, "sec_edgar_derived")
        self.assertEqual(fcff_growth.period_start, "2022-12-31")
        self.assertEqual(fcff_growth.period_end, "2023-12-31")
        self.assertEqual(fcff_growth.filing_date, "2024-02-15")
        self.assertIn("0000001234-24-000001", fcff_growth.source_document)
        self.assertEqual(
            fcff_growth.formula,
            "current_positive_fcff_divided_by_prior_positive_fcff_minus_one",
        )
        self.assertTrue(fcff_growth.is_fallback)
        observation_names = {
            name for name, _ in fcff_growth.input_observations
        }
        self.assertTrue(
            {
                "current_fcff",
                "prior_fcff",
                "current_change_in_nwc",
                "prior_change_in_nwc",
            }.issubset(observation_names)
        )

    def test_bank_critical_coverage_ignores_industrial_only_metrics(self):
        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else company_facts_fixture()

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))
        sparse_snapshot = replace(
            snapshot,
            income_statement={
                "net_income": snapshot.income_statement["net_income"],
            },
            balance_sheet={
                "equity": snapshot.balance_sheet["equity"],
            },
            cash_flow={},
            market_data={
                "shares": snapshot.market_data["shares"],
            },
        )

        bank_case = BenchmarkCase(
            "TEST",
            "bancos_financeiras",
            "diversified_bank",
            "Fixture bank",
        )
        traditional_case = BenchmarkCase(
            "TEST",
            "tradicionais_ciclicas",
            "industrial_machinery",
            "Fixture industrial",
        )
        bank_coverage, bank_missing = _critical_metric_audit(bank_case, sparse_snapshot)
        traditional_coverage, traditional_missing = _critical_metric_audit(
            traditional_case,
            sparse_snapshot,
        )

        self.assertEqual(bank_coverage, 1.0)
        self.assertEqual(bank_missing, ())
        self.assertLess(traditional_coverage, 1.0)
        self.assertIn("income_statement.revenue", traditional_missing)
        self.assertIn("cash_flow.capex", traditional_missing)

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
