import unittest
from datetime import datetime

from fundamental_analysis.data_sources import (
    MetricValue,
    _latest_statement_metric,
    get_mapping_value,
    parse_finviz_snapshot,
)


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
