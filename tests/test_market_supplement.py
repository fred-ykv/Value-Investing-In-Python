from datetime import date
from pathlib import Path
import tempfile
import unittest

from fundamental_analysis.historical_archive import _price_key
from fundamental_analysis.historical_prices import PricePoint, PriceSeries
from fundamental_analysis.market_supplement import _write_archive, collect_market_supplement
from fundamental_analysis.portfolio_package import _load_archives


class Provider:
    def __init__(self, *, dividend=False, changed_close=False):
        self.dividend = dividend
        self.changed_close = changed_close

    def fetch(self, ticker, start, end):
        close = 12.0 if self.changed_close else 10.0
        series = PriceSeries(ticker, (PricePoint(date(2020, 1, 2), 9.5, close, 1234),), "fixture")
        actions = {"events": [], "unresolved_dividends": ([{"ticker": ticker, "ex_date": "2020-01-02",
                                                              "value": 0.2, "reason": "payment_date_missing"}]
                                                            if self.dividend else [])}
        return series, actions


class MarketSupplementTests(unittest.TestCase):
    def base_archive(self, root):
        payload = {"ticker": "AAA", "source": "base", "security_id": "", "issuer_cik": "",
                   "input_evidence_sha256": "", "points": [{"day": "2020-01-02", "adjusted_close": 9.5,
                                                               "raw_close": 10.0, "volume": None}]}
        _write_archive(root, [("price_series", _price_key("AAA", date(2020, 1, 2), date(2020, 1, 2)), payload)], {})

    def test_reconciled_volume_is_added_without_rewriting_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, supplement = Path(tmp) / "base", Path(tmp) / "supplement"
            self.base_archive(base)
            report = collect_market_supplement([base], supplement, provider=Provider())
            _, _, prices, _, coverage, issues = _load_archives([base, supplement])
        self.assertEqual(report["captured_volume_points"], 1)
        self.assertEqual(prices[("AAA", "2020-01-02")]["volume"], 1234)
        self.assertTrue(coverage)
        self.assertFalse(issues)

    def test_dividend_without_payment_date_prevents_event_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, supplement = Path(tmp) / "base", Path(tmp) / "supplement"
            self.base_archive(base)
            report = collect_market_supplement([base], supplement, provider=Provider(dividend=True))
        self.assertFalse(report["corporate_event_coverage_written"])
        self.assertEqual(report["unresolved_dividends"][0]["reason"], "payment_date_missing")

    def test_price_divergence_rejects_supplement(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, supplement = Path(tmp) / "base", Path(tmp) / "supplement"
            self.base_archive(base)
            report = collect_market_supplement([base], supplement, provider=Provider(changed_close=True))
        self.assertEqual(report["captured_volume_points"], 0)
        self.assertIn("raw_close diverge", report["issues"][0])


if __name__ == "__main__":
    unittest.main()

