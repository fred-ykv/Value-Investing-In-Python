import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta

from fundamental_analysis.config import CompanyType
from fundamental_analysis.cyclical_normalization import build_cyclical_periods, normalize_cyclical_financials
from fundamental_analysis.cyclical_reporting import cyclical_normalization_payload
from fundamental_analysis.main import _merge_cyclical_history
from tests.test_cyclical_normalization import annual_statement, current_values


def statement(end, start=None, source="sec_edgar", revenue=1000, net_margin=0.1):
    item = deepcopy(annual_statement(end.year, revenue, 0.2, net_margin))
    item.source = source
    for mapping in (item.income_statement, item.cash_flow):
        for key, value in mapping.items():
            mapping[key] = replace(value, period_end=end, period_start=start, source=source, currency="USD")
    return item


class FiscalIdentityTests(unittest.TestCase):
    def test_mli_dates_count_seven_exercises_instead_of_ten_in_both_orders(self):
        ends = [date(2019, 12, 28), date(2020, 12, 26), date(2021, 12, 25), date(2022, 12, 31), date(2023, 12, 30), date(2024, 12, 28), date(2025, 12, 27)]
        sec = [statement(end, end - timedelta(days=363)) for end in ends]
        yahoo = [statement(date(y, 12, 31), source="yfinance") for y in (2023, 2024, 2025)]
        baseline, _ = build_cyclical_periods(sec)
        periods, warnings = build_cyclical_periods(_merge_cyclical_history(yahoo, sec))
        reversed_periods, reversed_warnings = build_cyclical_periods(list(reversed(sec + yahoo)))
        self.assertEqual(len(periods), 7)
        self.assertEqual(periods, reversed_periods)
        self.assertEqual(warnings, reversed_warnings)
        self.assertEqual([p.fcff_margin for p in periods], [p.fcff_margin for p in baseline])
        self.assertEqual(len(periods[-1].source_observations), 2)
        self.assertEqual(periods[-1].source, "sec_edgar")

    def test_duplicates_cannot_unlock_minimum_history(self):
        history = [statement(date(y, 12, 28), date(y, 1, 1)) for y in range(2020, 2024)]
        history += [statement(date(y, 12, 31), source="yfinance") for y in range(2020, 2024)]
        result = normalize_cyclical_financials(CompanyType.TRADITIONAL, current_values(), history, {}, {"is_cyclical": True})
        self.assertFalse(result.applied)
        self.assertEqual(result.sample_years, 4)
        self.assertEqual(result.status, "insufficient_history")

    def test_known_52_and_53_week_periods_are_distinct(self):
        a = statement(date(2022, 12, 31), date(2021, 12, 26))
        b = statement(date(2023, 12, 30), date(2023, 1, 1))
        self.assertEqual(len(build_cyclical_periods([a, b])[0]), 2)

    def test_two_full_exercises_can_end_in_same_calendar_year(self):
        a = statement(date(2022, 1, 1), date(2021, 1, 3))
        b = statement(date(2022, 12, 31), date(2022, 1, 2))
        self.assertEqual(len(build_cyclical_periods([a, b])[0]), 2)

    def test_transition_and_ttm_are_quarantined(self):
        transition = statement(date(2024, 6, 30), date(2024, 1, 1))
        ttm = statement(date(2024, 12, 31), date(2024, 1, 1))
        ttm.info["period_type"] = "ttm"
        periods, warnings = build_cyclical_periods([transition, ttm])
        self.assertEqual(periods, ())
        self.assertEqual(len(warnings), 2)

    def test_ambiguous_close_dates_do_not_select_an_arbitrary_source(self):
        a = statement(date(2024, 12, 28), date(2024, 1, 1))
        b = statement(date(2024, 12, 31), source="yfinance", revenue=2000)
        periods, warnings = build_cyclical_periods([a, b])
        self.assertEqual(periods, ())
        self.assertIn("ambigua", warnings[0])
        self.assertIn('"revenue": 2000', warnings[0])

    def test_exact_date_sources_survive_live_merge_for_audit(self):
        a = statement(date(2024, 12, 31), date(2024, 1, 1))
        b = statement(date(2024, 12, 31), source="yfinance")
        periods, _ = build_cyclical_periods(_merge_cyclical_history([b], [a]))
        self.assertEqual(len(periods[0].source_observations), 2)

    def test_window_applies_after_resolution(self):
        sec = [statement(date(y, 12, 28), date(y, 1, 1)) for y in range(2014, 2026)]
        yahoo = [statement(date(y, 12, 31), source="yfinance") for y in range(2020, 2026)]
        periods, _ = build_cyclical_periods(_merge_cyclical_history(yahoo, sec))
        self.assertEqual(len(periods), 10)
        self.assertEqual(periods[0].period_end.year, 2016)

    def test_duplicate_with_missing_profit_still_counts_once(self):
        item = statement(date(2024, 12, 31))
        del item.income_statement["net_income"]
        self.assertEqual(len(build_cyclical_periods([item, deepcopy(item)])[0]), 1)

    def test_summary_and_payload_show_unique_periods(self):
        history = [statement(date(y, 12, 31), date(y, 1, 1)) for y in range(2019, 2026)]
        result = normalize_cyclical_financials(CompanyType.TRADITIONAL, current_values(), history, {}, {"is_cyclical": True})
        payload = cyclical_normalization_payload(result, current_values())
        self.assertEqual(payload["unique_fiscal_periods"], 7)
        self.assertIn("7 exercicios unicos", payload["summary"])
        self.assertEqual(payload["history_start"], "2019-12-31")
        self.assertTrue(payload["history"][0]["source_observations"])

    def test_overlapping_full_length_periods_are_not_two_exercises(self):
        a = statement(date(2023, 12, 31), date(2023, 1, 1))
        b = statement(date(2024, 12, 15), date(2023, 12, 2))
        periods, warnings = build_cyclical_periods([a, b])
        self.assertEqual(periods, ())
        self.assertIn("quarentena", warnings[0])

    def test_different_currencies_are_not_reconciled(self):
        a = statement(date(2024, 12, 31), date(2024, 1, 1))
        b = deepcopy(a)
        b.income_statement["revenue"] = replace(b.income_statement["revenue"], currency="EUR")
        self.assertEqual(build_cyclical_periods([a, b])[0], ())

    def test_same_calendar_year_does_not_justify_overlapping_exercises(self):
        a = statement(date(2024, 6, 30), date(2023, 7, 1))
        b = statement(date(2024, 12, 31), date(2024, 1, 1))
        self.assertEqual(build_cyclical_periods([a, b])[0], ())

    def test_different_issuers_are_quarantined(self):
        a = statement(date(2023, 12, 31), date(2023, 1, 1))
        b = statement(date(2024, 12, 31), date(2024, 1, 1))
        b.ticker = "OTHER"
        self.assertEqual(build_cyclical_periods([a, b])[0], ())


if __name__ == "__main__":
    unittest.main()
