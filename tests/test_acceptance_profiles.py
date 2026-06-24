import unittest

from fundamental_analysis.main import analyze_ticker_from_inputs


BASE_INCOME = {"revenue": 10_000_000_000, "ebit": 1_500_000_000, "net_income": 900_000_000, "tax_provision": 250_000_000, "interest_expense": 100_000_000}
BASE_BALANCE = {"total_assets": 15_000_000_000, "total_liabilities": 7_000_000_000, "equity": 8_000_000_000, "cash": 1_000_000_000, "total_debt": 2_500_000_000, "current_assets": 4_000_000_000, "current_liabilities": 2_000_000_000}
BASE_CASH_FLOW = {"cfo": 1_200_000_000, "capex": -300_000_000, "depreciation_amortization": 250_000_000}
BASE_MARKET = {"shares": 100_000_000, "price": 75, "wacc": 0.10, "ke": 0.10, "growth_years": 0.04, "terminal_growth": 0.02}


class AcceptanceProfileTests(unittest.TestCase):
    def test_traditional_industrial_runs(self):
        result = analyze_ticker_from_inputs("INDU", BASE_INCOME, BASE_BALANCE, BASE_CASH_FLOW, BASE_MARKET, {"sector": "Industrials", "industry": "Industrial Products"})
        self.assertEqual(result.company_type, "tradicional")
        self.assertTrue(result.valuations)

    def test_big_tech_runs(self):
        result = analyze_ticker_from_inputs("TECH", BASE_INCOME, BASE_BALANCE, BASE_CASH_FLOW, dict(BASE_MARKET, revenue_growth=0.18, target_fcf_margin=0.24), {"sector": "Technology", "industry": "Software"})
        self.assertEqual(result.company_type, "growth_tech")
        self.assertEqual(result.valuations[0].method, "growth_tech")

    def test_bank_runs(self):
        result = analyze_ticker_from_inputs("BANK", BASE_INCOME, BASE_BALANCE, BASE_CASH_FLOW, dict(BASE_MARKET, dividend_per_share=2.0), {"sector": "Financial Services", "industry": "Banks - Regional"})
        self.assertEqual(result.company_type, "bancos_financeiras")
        self.assertEqual(result.valuations[0].method, "residual_income")

    def test_negative_fcf_company_runs(self):
        cash_flow = dict(BASE_CASH_FLOW, cfo=-200_000_000, capex=-300_000_000)
        result = analyze_ticker_from_inputs("NEG", BASE_INCOME, BASE_BALANCE, cash_flow, dict(BASE_MARKET, revenue_growth=0.30), {"sector": "Technology", "industry": "Software"})
        self.assertEqual(result.company_type, "growth_tech")
        self.assertTrue(any(v.diagnostics.get("negative_fcff") for v in result.valuations))


if __name__ == "__main__":
    unittest.main()
