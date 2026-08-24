import unittest
from datetime import date

from fundamental_analysis.config import CompanyType
from fundamental_analysis.cyclical_normalization import normalize_cyclical_financials
from fundamental_analysis.data_sources import metric_value
from fundamental_analysis.financial_statements import FinancialStatements, build_statement_metrics


def annual_statement(year, revenue, operating_margin, net_margin, reinvestment_margin=0.05):
    ebit = revenue * operating_margin
    tax = ebit * 0.25
    depreciation = revenue * 0.03
    capex = depreciation + revenue * reinvestment_margin
    return FinancialStatements(
        "CYC",
        {
            "revenue": metric_value("revenue", revenue, "manual", period_end=date(year, 12, 31)),
            "ebit": metric_value("ebit", ebit, "manual", period_end=date(year, 12, 31)),
            "net_income": metric_value("net_income", revenue * net_margin, "manual", period_end=date(year, 12, 31)),
            "tax_provision": metric_value("tax_provision", tax, "manual", period_end=date(year, 12, 31)),
            "interest_expense": metric_value("interest_expense", 0, "manual", period_end=date(year, 12, 31)),
        },
        {},
        {
            "depreciation_amortization": metric_value("depreciation_amortization", depreciation, "manual", period_end=date(year, 12, 31)),
            "capex": metric_value("capex", -capex, "manual", period_end=date(year, 12, 31)),
            "change_in_nwc_cash_effect": metric_value("change_in_nwc_cash_effect", 0, "manual", period_end=date(year, 12, 31)),
        },
        {},
        {"sector": "Industrials", "industry": "Steel"},
        "manual",
    )


def current_values():
    statements = FinancialStatements(
        "CYC",
        {
            "revenue": 2_000,
            "ebit": 500,
            "net_income": 240,
            "tax_provision": 125,
            "interest_expense": 0,
        },
        {"equity": 1_000, "cash": 100, "total_debt": 300},
        {
            "depreciation_amortization": 60,
            "capex": -160,
            "change_in_nwc_cash_effect": 0,
        },
        {"shares": 100, "price": 20},
        {},
        "manual",
    )
    return build_statement_metrics(statements).values


class CyclicalNormalizationTests(unittest.TestCase):
    def setUp(self):
        margins = [0.05, 0.10, 0.15, 0.20, 0.25]
        net_margins = [0.02, 0.05, 0.08, 0.10, 0.12]
        self.history = [
            annual_statement(2019 + index, 1_000 + index * 100, margin, net_margin)
            for index, (margin, net_margin) in enumerate(zip(margins, net_margins))
        ]

    def test_normalizes_scaled_margins_on_current_revenue(self):
        result = normalize_cyclical_financials(
            CompanyType.TRADITIONAL,
            current_values(),
            self.history,
            {"sector": "Industrials", "industry": "Steel"},
            {"is_cyclical": True},
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.sample_years, 5)
        self.assertAlmostEqual(result.normalized_operating_margin, 0.15)
        self.assertAlmostEqual(result.normalized_ebit.value, 300.0)
        self.assertAlmostEqual(result.normalized_nopat.value, 225.0)
        self.assertAlmostEqual(result.normalized_reinvestment.value, 100.0)
        self.assertAlmostEqual(result.normalized_fcff.value, 125.0)
        self.assertAlmostEqual(result.normalized_fcff_direct.value, 125.0)
        self.assertEqual(result.cycle_position, "acima_do_meio_do_ciclo")
        self.assertEqual(result.normalized_fcff.formula, "normalized_nopat_minus_normalized_reinvestment")

    def test_preserves_current_values_when_history_is_short(self):
        result = normalize_cyclical_financials(
            CompanyType.TRADITIONAL,
            current_values(),
            self.history[:4],
            {"sector": "Industrials", "industry": "Steel"},
            {"is_cyclical": True},
        )

        self.assertFalse(result.applied)
        self.assertEqual(result.status, "insufficient_history")
        self.assertFalse(result.normalized_fcff.is_available)
        self.assertTrue(any("Historico insuficiente" in warning for warning in result.warnings))

    def test_does_not_apply_to_non_cyclical_company(self):
        result = normalize_cyclical_financials(
            CompanyType.TRADITIONAL,
            current_values(),
            self.history,
            {"sector": "Consumer Defensive", "industry": "Beverages"},
            {},
        )

        self.assertFalse(result.is_cyclical)
        self.assertEqual(result.status, "not_applicable")

    def test_missing_working_capital_materially_reduces_confidence(self):
        clean_history = [
            annual_statement(2015 + index, 1_000 + index * 100, 0.12, 0.07)
            for index in range(8)
        ]
        fallback_history = [
            FinancialStatements(
                item.ticker,
                item.income_statement,
                item.balance_sheet,
                {
                    key: value
                    for key, value in item.cash_flow.items()
                    if key != "change_in_nwc_cash_effect"
                },
                item.market_data,
                item.info,
                item.source,
            )
            for item in clean_history
        ]
        clean = normalize_cyclical_financials(
            CompanyType.TRADITIONAL,
            current_values(),
            clean_history,
            {"sector": "Industrials", "industry": "Steel"},
            {"is_cyclical": True},
        )
        fallback = normalize_cyclical_financials(
            CompanyType.TRADITIONAL,
            current_values(),
            fallback_history,
            {"sector": "Industrials", "industry": "Steel"},
            {"is_cyclical": True},
        )

        self.assertLess(fallback.confidence, clean.confidence - 0.15)
        self.assertTrue(any("capital de giro" in warning for warning in fallback.warnings))


if __name__ == "__main__":
    unittest.main()
