import unittest

from fundamental_analysis.notebook_adapter import analyze_from_notebook_globals


class NotebookAdapterTests(unittest.TestCase):
    def test_adapts_common_names(self):
        namespace = {
            "symbol": "MLI",
            "Revenue_last": 4_000_000_000,
            "EBIT_last": 700_000_000,
            "NetIncome": 500_000_000,
            "TotalAssets_value": 5_000_000_000,
            "TotalLiabilities_value": 2_000_000_000,
            "CommonEquity": 3_000_000_000,
            "cash_total": 500_000_000,
            "total_debt": 800_000_000,
            "TotalCurrentAssets_value": 1_700_000_000,
            "TotalCurrentLiabilities_value": 900_000_000,
            "FCO": 650_000_000,
            "capex_cf_last": -150_000_000,
            "Shares_Outstanding": 100_000_000,
            "current_price": 45,
            "WACC_value": 0.10,
            "Ke": 0.11,
            "gLL_M_value": 0.05,
            "CP_value": 0.02,
            "info": {"sector": "Industrials"},
        }
        result = analyze_from_notebook_globals(namespace)
        self.assertEqual(result.ticker, "MLI")
        self.assertTrue(result.valuations)


if __name__ == "__main__":
    unittest.main()
