import copy
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fundamental_analysis.benchmark_universe import HISTORICAL_LIFECYCLE_CASES
from fundamental_analysis.config import POINT_IN_TIME
from fundamental_analysis.historical_calibration import (
    read_historical_calibration_csv, write_historical_calibration_csv, evaluate_historical_outcomes,
)
from fundamental_analysis.historical_prices import (
    PricePoint, PriceSeries, calculate_price_outcome, CompositeHistoricalPriceClient,
)
from fundamental_analysis.institutional_prices import TiingoHistoricalPriceClient
from fundamental_analysis.price_eligibility import (
    TRADING_RULES, PriceEligibilityError, apply_price_eligibility, trading_identity,
    valid_price_eligibility_audit,
)
from tests.test_historical_prices import StaticPriceProvider
from tests.test_historical_calibration import observations


CASES = {case.ticker: case for case in HISTORICAL_LIFECYCLE_CASES}


def reviewed_series(ticker, points):
    identity = trading_identity(ticker)
    return PriceSeries(ticker, tuple(points), "synthetic fixture, not market evidence",
                       identity["security_id"], identity["issuer_cik"], "a" * 64)


class PriceEligibilityTests(unittest.TestCase):
    def test_all_reviewed_boundaries_exclude_on_and_after_not_before(self):
        for rule in TRADING_RULES:
            with self.subTest(ticker=rule.ticker):
                last = rule.first_ineligible_date - timedelta(days=1)
                points = (PricePoint(last, 10, 10, 0),
                          PricePoint(rule.first_ineligible_date, 10, 10, 0),
                          PricePoint(rule.first_ineligible_date + timedelta(days=1), 15, 15, 500))
                original = reviewed_series(rule.ticker, points)
                eligible, audit = apply_price_eligibility(original, rule.ticker, CASES[rule.ticker].lifecycle_event)
                self.assertEqual(eligible.points, points[:1])
                self.assertEqual(original.points, points)
                self.assertEqual(len(audit["quarantined_rows"]), 2)
                self.assertTrue(valid_price_eligibility_audit(audit, rule.ticker, original.issuer_cik, last))
                self.assertEqual(audit["quarantined_rows"][1]["volume"], 500)

    def test_zero_and_missing_volume_are_preserved_before_boundary(self):
        points = (PricePoint(date(2021, 10, 27), 10, 10, 0), PricePoint(date(2021, 10, 28), 10, 10))
        eligible, audit = apply_price_eligibility(reviewed_series("MDLA", points), "MDLA", CASES["MDLA"].lifecycle_event)
        self.assertEqual(eligible.points, points)
        self.assertEqual(audit["quarantined_rows"], [])
        self.assertIsNone(eligible.points[-1].volume)

    def test_mntv_event_day_is_retained(self):
        point = PricePoint(date(2023, 5, 31), 9.45, 9.45, 100)
        eligible, audit = apply_price_eligibility(reviewed_series("MNTV", [point]), "MNTV", CASES["MNTV"].lifecycle_event)
        self.assertEqual(eligible.points, (point,))
        self.assertEqual(audit["identity"]["first_ineligible_date"], "2023-06-01")

    def test_bbby_otc_history_is_retained_and_terminal_payoff_remains_zero(self):
        case = CASES["BBBY"]
        stock = reviewed_series("BBBY", [PricePoint(date(2023, 6, 15), 1, 1, 100),
                                         PricePoint(date(2023, 9, 29), 0.0789, 0.0789, 100)])
        spy = PriceSeries("SPY", tuple(PricePoint(day, 100, 100) for day in (
            date(2023, 6, 15), date(2023, 9, 29), date(2024, 6, 17))), "fixture")
        outcome = calculate_price_outcome("BBBY", "SPY", date(2023, 6, 15),
            StaticPriceProvider({"BBBY": stock, "SPY": spy}), lifecycle_event=case.lifecycle_event, expected_cik=case.cik)
        self.assertEqual(outcome.forward_return, -1)
        self.assertEqual(outcome.max_drawdown, -1)
        self.assertEqual(outcome.stock_terminal_date, date(2023, 9, 29))
        self.assertEqual(outcome.price_eligibility_audit["quarantined_rows"], [])

    def test_cash_payoff_uses_reviewed_last_price_and_unchanged_contract(self):
        case = CASES["MDLA"]
        stock = reviewed_series("MDLA", [PricePoint(date(2021, 9, 1), 30, 30),
            PricePoint(date(2021, 10, 28), 33.99, 33.99), PricePoint(date(2021, 10, 29), 33.99, 33.99, 0)])
        spy = PriceSeries("SPY", (PricePoint(date(2021, 9, 1), 100, 100),
            PricePoint(date(2021, 10, 29), 110, 110), PricePoint(date(2021, 11, 1), 121, 121)), "fixture")
        outcome = calculate_price_outcome("MDLA", "SPY", date(2021, 9, 1),
            StaticPriceProvider({"MDLA": stock, "SPY": spy}),
            replace(POINT_IN_TIME, forward_horizon_months=2), lifecycle_event=case.lifecycle_event)
        self.assertEqual(outcome.stock_terminal_date, date(2021, 10, 28))
        self.assertAlmostEqual(outcome.forward_return, 34 / 30 * 121 / 110 - 1)
        self.assertEqual(outcome.terminal_value_per_share, 34)
        self.assertEqual(len(outcome.price_eligibility_audit["quarantined_rows"]), 1)

    def test_missing_or_mismatched_identity_evidence_and_event_fail_closed(self):
        case = CASES["MDLA"]
        original = reviewed_series("MDLA", [PricePoint(date(2021, 10, 28), 10, 10)])
        for changed in (replace(original, issuer_cik=""), replace(original, security_id="other-class"),
                        replace(original, ticker="BBBYQ"), replace(original, input_evidence_sha256="")):
            with self.subTest(series=changed), self.assertRaises(PriceEligibilityError):
                apply_price_eligibility(changed, "MDLA", case.lifecycle_event)
        for event in (None, replace(case.lifecycle_event, effective_date=date(2021, 10, 30)),
                      replace(case.lifecycle_event, terminal_value_per_share=35)):
            with self.assertRaises(PriceEligibilityError):
                apply_price_eligibility(original, "MDLA", event)
        with self.assertRaises(PriceEligibilityError):
            apply_price_eligibility(replace(original, ticker="OTHER"), "OTHER", None)
        with patch("fundamental_analysis.price_eligibility.TRADING_RULES", TRADING_RULES[:-1]):
            with self.assertRaises(PriceEligibilityError):
                apply_price_eligibility(original, "MDLA", case.lifecycle_event)

    def test_invalid_or_duplicate_prices_are_not_silently_normalized(self):
        valid = PricePoint(date(2021, 10, 28), 10, 10)
        for points in ((valid, valid), (replace(valid, raw_close=None),),
                       (replace(valid, adjusted_close=float("nan")),), (replace(valid, volume=-1),)):
            with self.assertRaises(PriceEligibilityError):
                apply_price_eligibility(reviewed_series("MDLA", points), "MDLA", CASES["MDLA"].lifecycle_event)

    def test_no_eligible_entry_cannot_be_rescued_by_post_suspension_price(self):
        stock = reviewed_series("MDLA", [PricePoint(date(2021, 10, 29), 34, 34)])
        with self.assertRaisesRegex(PriceEligibilityError, "Nenhum preco elegivel"):
            calculate_price_outcome("MDLA", "SPY", date(2021, 10, 28),
                StaticPriceProvider({"MDLA": stock}), lifecycle_event=CASES["MDLA"].lifecycle_event)

    def test_provider_identity_failure_cannot_fall_back(self):
        fallback = unittest.mock.Mock()
        provider = CompositeHistoricalPriceClient(TiingoHistoricalPriceClient(json_getter=lambda url: {}), fallback)
        with self.assertRaises(PriceEligibilityError):
            provider.fetch_series("MDLA", date(2021, 1, 1), date(2021, 12, 1))
        fallback.fetch_series.assert_not_called()

    def test_provider_boolean_is_not_coerced_to_a_price_or_volume(self):
        from tests.test_institutional_prices import metadata, prices
        for key in ("close", "adjClose", "volume"):
            def getter(url):
                if "/prices?" not in url:
                    return metadata()
                payload = prices()
                payload[0][key] = True
                return payload
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Booleano"):
                TiingoHistoricalPriceClient(json_getter=getter).fetch_series("MDLA", date.min, date.max)

    def test_audit_roundtrip_and_legacy_csv_block_recalibration(self):
        case = CASES["MDLA"]
        _, audit = apply_price_eligibility(reviewed_series("MDLA", [PricePoint(date(2021, 10, 28), 10, 10),
            PricePoint(date(2021, 10, 29), 10, 10, 0)]), "MDLA", case.lifecycle_event)
        observation = replace(observations()[0], ticker="MDLA", security_cik=case.cik,
            lifecycle_event_type=case.lifecycle_event.event_type, lifecycle_event_date=case.lifecycle_event.effective_date,
            stock_terminal_date=date(2021, 10, 28), price_eligibility_audit=audit)
        self.assertTrue(observation.has_valid_price_eligibility)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "observations.csv"
            write_historical_calibration_csv([observation], path)
            loaded = read_historical_calibration_csv(path)[0]
        self.assertEqual(loaded.price_eligibility_audit, audit)
        self.assertTrue(loaded.has_valid_price_eligibility)
        legacy = replace(observation, price_eligibility_audit={})
        self.assertFalse(legacy.is_point_in_time_valid)
        self.assertTrue(any("Negociabilidade" in warning for warning in evaluate_historical_outcomes([legacy]).warnings))
        altered = copy.deepcopy(audit)
        altered["quarantined_rows"][0]["raw_close"] = 12
        self.assertFalse(replace(observation, price_eligibility_audit=altered).has_valid_price_eligibility)
        self.assertFalse(replace(observation, stock_terminal_date=date(2021, 10, 29)).has_valid_price_eligibility)


if __name__ == "__main__":
    unittest.main()
