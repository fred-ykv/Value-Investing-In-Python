import unittest
from datetime import datetime

from fundamental_analysis.data_sources import (
    MetricValue,
    _latest_statement_metric,
    get_mapping_value,
    parse_finviz_snapshot,
    safe_float,
)
from fundamental_analysis.main import analyze_ticker_from_inputs


class FakeRow:
    def __init__(self, name, values):
        self.name = name
        self._values = values

    def dropna(self):
        return self

    def items(self):
        return self._values.items()


class FakeStatement:
    empty = False

    def __init__(self):
        self.index = ["Total Revenue"]
        self.loc = {
            "Total Revenue": FakeRow(
                "Total Revenue",
                {
                    "2025-12-31": 1000,
                    "2024-12-31": 900,
                },
            )
        }


class DataLineageTests(unittest.TestCase):
    def test_get_mapping_value_preserves_metric_value_lineage(self):
        original = MetricValue(
            "Total Revenue",
            1000,
            "yfinance",
            0.85,
            source_url="https://finance.yahoo.com/quote/ABC",
            source_document="Yahoo Finance income statement",
            currency="USD",
            scale="raw",
            basis="reported",
        )

        result = get_mapping_value({"revenue": original}, "revenue", source="manual")

        self.assertEqual(result.name, "revenue")
        self.assertEqual(result.source, "yfinance")
        self.assertEqual(result.source_url, "https://finance.yahoo.com/quote/ABC")
        self.assertEqual(result.currency, "USD")
        self.assertEqual(result.scale, "raw")

    def test_safe_float_accepts_metric_value(self):
        original = MetricValue("beta", 1.2, "yfinance", 0.85)

        self.assertEqual(safe_float(original), 1.2)

    def test_analysis_accepts_yfinance_metric_value_market_inputs(self):
        result = analyze_ticker_from_inputs(
            "MLI",
            {"revenue": 4_000_000_000, "ebit": 700_000_000, "net_income": 500_000_000},
            {
                "total_assets": 5_000_000_000,
                "total_liabilities": 2_000_000_000,
                "equity": 3_000_000_000,
                "cash": 500_000_000,
                "total_debt": 800_000_000,
                "current_assets": 1_700_000_000,
                "current_liabilities": 900_000_000,
            },
            {"cfo": 650_000_000, "capex": -150_000_000, "depreciation_amortization": 100_000_000},
            {
                "shares": MetricValue("shares", 100_000_000, "yfinance", 0.85),
                "price": MetricValue("price", 45, "yfinance", 0.85),
                "beta": MetricValue("beta", 1.2, "yfinance", 0.85),
            },
            {"sector": "Industrials"},
            source="yfinance",
        )

        self.assertEqual(result.ticker, "MLI")
        self.assertTrue(result.report["html"])

    def test_finviz_snapshot_adds_source_context(self):
        as_of = datetime(2026, 1, 2, 3, 4, 5)
        metrics = parse_finviz_snapshot(
            "<td>P/E</td><td>15.2</td>",
            source_url="https://finviz.com/quote.ashx?t=ABC",
            as_of=as_of,
        )

        self.assertEqual(metrics["P/E"].source, "finviz")
        self.assertEqual(metrics["P/E"].source_url, "https://finviz.com/quote.ashx?t=ABC")
        self.assertEqual(metrics["P/E"].source_document, "finviz snapshot")
        self.assertEqual(metrics["P/E"].as_of, as_of)

    def test_latest_statement_metric_preserves_period_and_currency(self):
        result = _latest_statement_metric(
            FakeStatement(),
            ("Total Revenue",),
            source_url="https://finance.yahoo.com/quote/ABC",
            source_document="Yahoo Finance income statement",
            currency="USD",
        )

        self.assertEqual(result.value, 1000)
        self.assertEqual(result.source, "yfinance")
        self.assertEqual(str(result.period_end), "2025-12-31")
        self.assertEqual(result.currency, "USD")
        self.assertEqual(result.source_document, "Yahoo Finance income statement")


if __name__ == "__main__":
    unittest.main()
