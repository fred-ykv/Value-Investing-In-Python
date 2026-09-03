import unittest
from dataclasses import replace
from datetime import date

from fundamental_analysis.data_sources import metric_value
from fundamental_analysis.financial_statements import FinancialStatements
from fundamental_analysis.historical_signals import (
    derive_historical_signals,
    merge_historical_signals,
)


def annual_statements(
    period_end: date,
    *,
    revenue: float,
    gross_profit: float,
    ebit: float,
    tax: float,
    depreciation: float,
    capex: float,
    nwc_cash_effect: float,
) -> FinancialStatements:
    def value(name: str, amount: float):
        return metric_value(
            name,
            amount,
            "yfinance",
            source_url="https://finance.yahoo.com/quote/TEST",
            source_document="Yahoo Finance annual statement",
            period_end=period_end,
        )

    return FinancialStatements(
        "TEST",
        {
            "revenue": value("revenue", revenue),
            "gross_profit": value("gross_profit", gross_profit),
            "ebit": value("ebit", ebit),
            "tax_provision": value("tax_provision", tax),
            "interest_expense": value("interest_expense", 0.0),
        },
        {},
        {
            "depreciation_amortization": value(
                "depreciation_amortization", depreciation
            ),
            "capex": value("capex", capex),
            "change_in_nwc_cash_effect": value(
                "change_in_nwc_cash_effect", nwc_cash_effect
            ),
        },
        {},
        {},
        "yfinance",
    )


class HistoricalSignalTests(unittest.TestCase):
    def positive_history(self, prior_end=date(2023, 12, 31)):
        return [
            annual_statements(
                end,
                revenue=revenue,
                gross_profit=revenue * 0.4,
                ebit=200,
                tax=40,
                depreciation=50,
                capex=-80,
                nwc_cash_effect=-20,
            )
            for end, revenue in ((prior_end, 1_000), (date(2024, 12, 31), 1_200))
        ]

    def test_rejects_missing_year_and_quarterly_gap(self):
        for prior_end in (date(2022, 12, 31), date(2024, 9, 30)):
            with self.subTest(prior_end=prior_end):
                signals = derive_historical_signals(self.positive_history(prior_end))
                for name in ("revenue_growth", "fcff_growth"):
                    self.assertIsNone(signals[name].value)
                    self.assertEqual(signals[name].confidence, 0.0)
                    self.assertIn("intervalo", signals[name].note)

    def test_accepts_52_and_53_week_annual_comparatives(self):
        for prior_end in (date(2024, 1, 2), date(2023, 12, 26)):
            with self.subTest(prior_end=prior_end):
                signals = derive_historical_signals(self.positive_history(prior_end))
                self.assertAlmostEqual(signals["revenue_growth"].value, 0.2)
                self.assertAlmostEqual(signals["fcff_growth"].value, 0.0)

    def test_rejects_known_partial_period_and_misaligned_gross_profit(self):
        history = self.positive_history()
        income = history[-1].income_statement
        income["revenue"] = replace(income["revenue"], period_start=date(2024, 10, 1))
        signals = derive_historical_signals(history)
        self.assertIsNone(signals["revenue_growth"].value)
        self.assertIsNone(signals["gross_margin"].value)
        history = self.positive_history()
        income = history[-1].income_statement
        income["gross_profit"] = replace(income["gross_profit"], period_end=date(2023, 12, 31))
        self.assertIsNone(derive_historical_signals(history)["gross_margin"].value)

    def test_fcff_rejects_asymmetric_working_capital_bases(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                history = self.positive_history()
                prior_cf = history[0].cash_flow
                cash_effect = prior_cf.pop("change_in_nwc_cash_effect")
                if not missing:
                    prior_cf["change_in_nwc"] = replace(
                        cash_effect, name="change_in_nwc", value=20
                    )
                signal = derive_historical_signals(history)["fcff_growth"]
                self.assertIsNone(signal.value)
                self.assertIn("capital de giro", signal.note)
                self.assertIn("current", dict(signal.input_observations))

    def test_fcff_allows_symmetric_zero_nwc_with_fallback_label(self):
        history = self.positive_history()
        for statements in history:
            statements.cash_flow.pop("change_in_nwc_cash_effect")
        signal = derive_historical_signals(history)["fcff_growth"]
        self.assertAlmostEqual(signal.value, 0.0)
        self.assertTrue(signal.is_fallback)

    def test_fcff_rejects_inputs_from_different_periods(self):
        history = self.positive_history()
        cf = history[-1].cash_flow
        cf["capex"] = replace(cf["capex"], period_end=date(2023, 12, 31))
        signal = derive_historical_signals(history)["fcff_growth"]
        self.assertIsNone(signal.value)
        self.assertIn("alinhamento", signal.note)

    def test_rejects_conflicting_currencies(self):
        history = self.positive_history()
        for statements, currency in zip(history, ("EUR", "USD")):
            income = statements.income_statement
            income["revenue"] = replace(income["revenue"], currency=currency)
        income = history[-1].income_statement
        income["gross_profit"] = replace(income["gross_profit"], currency="EUR")
        signals = derive_historical_signals(history)
        self.assertIsNone(signals["revenue_growth"].value)
        self.assertIsNone(signals["gross_margin"].value)

    def test_nonfinite_manual_inputs_do_not_block_dated_evidence(self):
        annual = derive_historical_signals(self.positive_history())["revenue_growth"]
        for value in (float("nan"), float("inf"), "NaN", "Infinity", "missing"):
            with self.subTest(value=value):
                merged = merge_historical_signals(
                    {"revenue_growth": value}, {"revenue_growth": annual}
                )
                self.assertEqual(merged["revenue_growth"], annual)

    def test_derives_dated_like_for_like_annual_signals(self):
        history = [
            annual_statements(
                date(2023, 12, 31),
                revenue=1_000,
                gross_profit=400,
                ebit=200,
                tax=40,
                depreciation=50,
                capex=-80,
                nwc_cash_effect=-20,
            ),
            annual_statements(
                date(2024, 12, 31),
                revenue=1_200,
                gross_profit=480,
                ebit=240,
                tax=48,
                depreciation=60,
                capex=-90,
                nwc_cash_effect=-20,
            ),
        ]

        signals = derive_historical_signals(history)

        self.assertAlmostEqual(signals["revenue_growth"].value, 0.20)
        self.assertAlmostEqual(signals["gross_margin"].value, 0.40)
        self.assertIsNone(signals["gross_margin"].period_start)
        self.assertAlmostEqual(signals["fcff_growth"].value, 142 / 110 - 1)
        self.assertEqual(signals["fcff_growth"].period_start, date(2023, 12, 31))
        self.assertEqual(signals["fcff_growth"].period_end, date(2024, 12, 31))
        self.assertEqual(signals["fcff_growth"].source, "yfinance_derived")
        self.assertEqual(
            signals["fcff_growth"].formula,
            "current_positive_annual_fcff_divided_by_prior_positive_annual_fcff_minus_one",
        )
        self.assertEqual(dict(signals["fcff_growth"].input_observations)["current"], 142)

    def test_fcff_growth_rejects_non_positive_comparative_base(self):
        history = [
            annual_statements(
                date(2023, 12, 31),
                revenue=1_000,
                gross_profit=400,
                ebit=-100,
                tax=0,
                depreciation=20,
                capex=-80,
                nwc_cash_effect=0,
            ),
            annual_statements(
                date(2024, 12, 31),
                revenue=1_200,
                gross_profit=500,
                ebit=100,
                tax=20,
                depreciation=30,
                capex=-50,
                nwc_cash_effect=0,
            ),
        ]

        signal = derive_historical_signals(history)["fcff_growth"]

        self.assertIsNone(signal.value)
        self.assertEqual(signal.confidence, 0.0)
        self.assertIn("mudanca de sinal", signal.note)

    def test_cross_source_margin_keeps_both_documents_and_filing_date(self):
        statements = annual_statements(
            date(2024, 12, 31),
            revenue=1_000,
            gross_profit=400,
            ebit=200,
            tax=40,
            depreciation=50,
            capex=-80,
            nwc_cash_effect=-20,
        )
        statements.income_statement["revenue"] = metric_value(
            "revenue",
            1_000,
            "sec_edgar",
            source_url="https://data.sec.gov/example",
            source_document="SEC EDGAR 10-K example",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            filing_date=date(2025, 2, 1),
        )

        margin = derive_historical_signals([statements])["gross_margin"]

        self.assertEqual(margin.source, "cross_source_derived")
        self.assertIn("Yahoo Finance", margin.source_document)
        self.assertIn("SEC EDGAR", margin.source_document)
        self.assertEqual(margin.filing_date, date(2025, 2, 1))

    def test_dated_annual_signal_replaces_only_undated_yahoo_profile_value(self):
        annual = metric_value(
            "revenue_growth",
            0.12,
            "yfinance_derived",
            period_start=date(2023, 12, 31),
            period_end=date(2024, 12, 31),
        )
        profile = metric_value(
            "revenue_growth",
            0.30,
            "yfinance",
            source_document="Yahoo Finance quote/profile info",
        )

        merged = merge_historical_signals(
            {"revenue_growth": profile}, {"revenue_growth": annual}
        )
        manual = merge_historical_signals(
            {"revenue_growth": 0.25}, {"revenue_growth": annual}
        )

        self.assertEqual(merged["revenue_growth"], annual)
        self.assertEqual(manual["revenue_growth"], 0.25)


if __name__ == "__main__":
    unittest.main()
