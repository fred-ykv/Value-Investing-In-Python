import unittest

from fundamental_analysis.calibration import build_calibration_summary
from fundamental_analysis.main import analyze_ticker_from_inputs


def with_full_peer_counts(peer_medians):
    return {key: 6 for key in peer_medians}


class CalibrationBasketTests(unittest.TestCase):
    def test_benchmark_basket_distribution_is_financially_plausible(self):
        results = [
            analyze_ticker_from_inputs(
                "MEGA_TECH_PREMIUM",
                {"revenue": 380e9, "ebit": 115e9, "net_income": 100e9},
                {"total_assets": 350e9, "total_liabilities": 290e9, "equity": 60e9, "cash": 65e9, "total_debt": 110e9, "current_assets": 140e9, "current_liabilities": 130e9},
                {"cfo": 115e9, "capex": -11e9, "depreciation_amortization": 12e9},
                {
                    "shares": 15.5e9,
                    "price": 190,
                    "wacc": 0.09,
                    "ke": 0.09,
                    "growth_years": 0.05,
                    "terminal_growth": 0.025,
                    "revenue_growth": 0.06,
                    "fcff_growth": 0.05,
                    "peer_medians": {"price_to_earnings": 28, "ev_to_sales": 7, "price_to_sales": 7, "ev_to_ebitda": 20},
                    "peer_median_counts": with_full_peer_counts({"price_to_earnings": 28, "ev_to_sales": 7, "price_to_sales": 7, "ev_to_ebitda": 20}),
                },
                {"sector": "Technology", "industry": "Consumer Electronics"},
            ),
            analyze_ticker_from_inputs(
                "EXCEPTIONAL_GROWTH",
                {"revenue": 120e9, "ebit": 75e9, "net_income": 68e9},
                {"total_assets": 130e9, "total_liabilities": 35e9, "equity": 95e9, "cash": 35e9, "total_debt": 10e9, "current_assets": 70e9, "current_liabilities": 25e9},
                {"cfo": 70e9, "capex": -4e9, "depreciation_amortization": 2e9},
                {
                    "shares": 24.5e9,
                    "price": 130,
                    "wacc": 0.10,
                    "ke": 0.10,
                    "growth_years": 0.20,
                    "terminal_growth": 0.035,
                    "revenue_growth": 0.45,
                    "fcff_growth": 0.35,
                    "target_fcf_margin": 0.38,
                    "peer_medians": {"ev_to_sales": 25, "price_to_sales": 24, "price_to_earnings": 45},
                    "peer_median_counts": with_full_peer_counts({"ev_to_sales": 25, "price_to_sales": 24, "price_to_earnings": 45}),
                },
                {"sector": "Technology", "industry": "Semiconductors"},
            ),
            analyze_ticker_from_inputs(
                "QUALITY_BANK",
                {"revenue": 170e9, "ebit": 65e9, "net_income": 50e9},
                {"total_assets": 4000e9, "total_liabilities": 3700e9, "equity": 300e9, "cash": 900e9, "total_debt": 650e9, "current_assets": 1200e9, "current_liabilities": 1000e9},
                {"cfo": 65e9, "capex": -5e9},
                {
                    "shares": 2.9e9,
                    "price": 200,
                    "ke": 0.10,
                    "terminal_growth": 0.02,
                    "dividend_per_share": 4.6,
                    "peer_medians": {"price_to_book": 1.6, "price_to_earnings": 12},
                    "peer_median_counts": with_full_peer_counts({"price_to_book": 1.6, "price_to_earnings": 12}),
                },
                {"sector": "Financial Services", "industry": "Banks - Diversified"},
            ),
            analyze_ticker_from_inputs(
                "LEVERED_TRADITIONAL_AUTO",
                {"revenue": 176e9, "ebit": 9e9, "net_income": 4e9},
                {"total_assets": 280e9, "total_liabilities": 235e9, "equity": 45e9, "cash": 28e9, "total_debt": 150e9, "current_assets": 115e9, "current_liabilities": 105e9},
                {"cfo": 14e9, "capex": -8e9, "depreciation_amortization": 7e9},
                {
                    "shares": 4e9,
                    "price": 12,
                    "wacc": 0.11,
                    "ke": 0.11,
                    "growth_years": 0.02,
                    "terminal_growth": 0.01,
                    "revenue_growth": 0.03,
                    "fcff_growth": 0.02,
                    "peer_medians": {"price_to_earnings": 8, "ev_to_ebitda": 7, "ev_to_ebit": 9, "ev_to_sales": 0.7, "price_to_book": 1.0},
                    "peer_median_counts": with_full_peer_counts({"price_to_earnings": 8, "ev_to_ebitda": 7, "ev_to_ebit": 9, "ev_to_sales": 0.7, "price_to_book": 1.0}),
                },
                {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "business_model": "traditional_auto"},
            ),
            analyze_ticker_from_inputs(
                "NEGATIVE_FCF_GROWTH",
                {"revenue": 2e9, "ebit": -0.6e9, "net_income": -0.75e9},
                {"total_assets": 3e9, "total_liabilities": 1e9, "equity": 2e9, "cash": 0.8e9, "total_debt": 0.2e9, "current_assets": 1.1e9, "current_liabilities": 0.4e9},
                {"cfo": -0.45e9, "capex": -0.15e9},
                {
                    "shares": 250e6,
                    "price": 18,
                    "ke": 0.13,
                    "wacc": 0.13,
                    "growth_years": 0.25,
                    "terminal_growth": 0.03,
                    "revenue_growth": 0.35,
                    "target_fcf_margin": 0.18,
                    "cash_runway_years": 1.3,
                    "peer_medians": {"ev_to_sales": 5, "price_to_sales": 4.5},
                    "peer_median_counts": with_full_peer_counts({"ev_to_sales": 5, "price_to_sales": 4.5}),
                },
                {"sector": "Technology", "industry": "Software"},
            ),
        ]

        summary = build_calibration_summary(results)
        recommendations = {row.ticker: row.recommendation for row in summary.rows}
        company_types = {row.ticker: row.company_type for row in summary.rows}

        self.assertEqual(recommendations["MEGA_TECH_PREMIUM"], "Observar")
        self.assertEqual(recommendations["EXCEPTIONAL_GROWTH"], "Comprar")
        self.assertEqual(recommendations["QUALITY_BANK"], "Observar")
        self.assertEqual(recommendations["LEVERED_TRADITIONAL_AUTO"], "Evitar")
        self.assertEqual(recommendations["NEGATIVE_FCF_GROWTH"], "Observar")
        self.assertEqual(company_types["LEVERED_TRADITIONAL_AUTO"], "tradicional")
        self.assertEqual(summary.recommendation_counts["Observar"], 3)
        self.assertEqual(summary.recommendation_counts["Comprar"], 1)
        self.assertEqual(summary.recommendation_counts["Evitar"], 1)
        self.assertGreater(summary.max_score, summary.min_score)


if __name__ == "__main__":
    unittest.main()
