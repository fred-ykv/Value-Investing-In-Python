import unittest

from fundamental_analysis.main import _merge_cyclical_history, analyze_ticker_from_inputs
from tests.test_cyclical_normalization import annual_statement


BASE_INCOME = {"revenue": 10_000_000_000, "ebit": 1_500_000_000, "net_income": 900_000_000, "tax_provision": 250_000_000, "interest_expense": 100_000_000}
BASE_BALANCE = {"total_assets": 15_000_000_000, "total_liabilities": 7_000_000_000, "equity": 8_000_000_000, "cash": 1_000_000_000, "total_debt": 2_500_000_000, "current_assets": 4_000_000_000, "current_liabilities": 2_000_000_000}
BASE_CASH_FLOW = {"cfo": 1_200_000_000, "capex": -300_000_000, "depreciation_amortization": 250_000_000}
BASE_MARKET = {"shares": 100_000_000, "price": 75, "wacc": 0.10, "ke": 0.10, "growth_years": 0.04, "terminal_growth": 0.02}


class AcceptanceProfileTests(unittest.TestCase):
    def test_traditional_industrial_runs(self):
        result = analyze_ticker_from_inputs("INDU", BASE_INCOME, BASE_BALANCE, BASE_CASH_FLOW, BASE_MARKET, {"sector": "Industrials", "industry": "Industrial Products"})
        self.assertEqual(result.company_type, "tradicional")
        self.assertAlmostEqual(result.cost_of_capital.discount_rate, 0.10)
        self.assertTrue(result.valuations)

    def test_big_tech_runs(self):
        result = analyze_ticker_from_inputs("TECH", BASE_INCOME, BASE_BALANCE, BASE_CASH_FLOW, dict(BASE_MARKET, revenue_growth=0.18, target_fcf_margin=0.24), {"sector": "Technology", "industry": "Software"})
        self.assertEqual(result.company_type, "growth_tech")
        self.assertEqual(result.valuations[0].method, "growth_tech")
        self.assertAlmostEqual(result.valuations[0].diagnostics["discount_rate"], result.cost_of_capital.discount_rate)

    def test_bank_runs(self):
        result = analyze_ticker_from_inputs("BANK", BASE_INCOME, BASE_BALANCE, BASE_CASH_FLOW, dict(BASE_MARKET, dividend_per_share=2.0), {"sector": "Financial Services", "industry": "Banks - Regional"})
        self.assertEqual(result.company_type, "bancos_financeiras")
        self.assertEqual(result.valuations[0].method, "residual_income")

    def test_negative_fcf_company_runs(self):
        cash_flow = dict(BASE_CASH_FLOW, cfo=-200_000_000, capex=-2_000_000_000)
        result = analyze_ticker_from_inputs("NEG", BASE_INCOME, BASE_BALANCE, cash_flow, dict(BASE_MARKET, revenue_growth=0.30), {"sector": "Technology", "industry": "Software"})
        self.assertEqual(result.company_type, "growth_tech")
        self.assertTrue(any(v.diagnostics.get("negative_fcff") for v in result.valuations))

    def test_cyclical_company_uses_normalized_inputs_and_explains_them(self):
        history = [
            annual_statement(
                2017 + index,
                7_000_000_000 + index * 500_000_000,
                operating_margin,
                net_margin,
            )
            for index, (operating_margin, net_margin) in enumerate(
                zip(
                    [0.05, 0.08, 0.12, 0.16, 0.22, 0.19, 0.11, 0.07],
                    [0.02, 0.04, 0.07, 0.10, 0.14, 0.12, 0.06, 0.03],
                )
            )
        ]
        market = dict(
            BASE_MARKET,
            growth_years=0.15,
            is_cyclical=True,
            cyclical_history=history,
        )

        result = analyze_ticker_from_inputs(
            "CYC",
            BASE_INCOME,
            BASE_BALANCE,
            BASE_CASH_FLOW,
            market,
            {"sector": "Basic Materials", "industry": "Steel"},
        )

        self.assertTrue(result.cyclical_normalization.applied)
        self.assertEqual(result.cyclical_normalization.sample_years, 8)
        methods = {valuation.method: valuation for valuation in result.valuations}
        self.assertTrue(methods["dcf_fcff"].diagnostics["cyclical_normalization"])
        self.assertTrue(methods["graham"].diagnostics["cyclical_normalization"])
        self.assertTrue(methods["eva"].diagnostics["cyclical_normalization"])
        self.assertLessEqual(methods["dcf_fcff"].diagnostics["growth_years"], 0.08)
        self.assertIn("Normalizacao do ciclo", result.report["markdown"])
        self.assertIn("Atual", result.report["html"])
        self.assertTrue(result.report["cyclical_normalization"]["applied"])

    def test_live_history_merge_prefers_sec_and_preserves_unique_yahoo_year(self):
        yahoo_2023 = annual_statement(2023, 1_000, 0.10, 0.06)
        yahoo_2024 = annual_statement(2024, 1_100, 0.11, 0.07)
        sec_2023 = annual_statement(2023, 1_005, 0.10, 0.06)

        merged = _merge_cyclical_history(
            [yahoo_2023, yahoo_2024],
            [sec_2023],
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].income_statement["revenue"].value, 1_005)
        self.assertEqual(merged[1].income_statement["revenue"].value, 1_100)


if __name__ == "__main__":
    unittest.main()
