from datetime import date
from pathlib import Path
import tempfile
import unittest

from fundamental_analysis.historical_archive import _price_key
from fundamental_analysis.historical_prices import PricePoint, PriceSeries
from fundamental_analysis.market_supplement import (_write_archive, collect_market_supplement,
                                                     create_market_supplement_request)
from fundamental_analysis.portfolio_package import _load_archives


class Provider:
    def __init__(self, *, dividend=False, changed_close=False, changed_adjusted=False):
        self.dividend = dividend
        self.changed_close = changed_close
        self.changed_adjusted = changed_adjusted

    def fetch(self, ticker, start, end):
        close = 12.0 if self.changed_close else 10.0
        adjusted = 8.0 if self.changed_adjusted else 9.5
        series = PriceSeries(ticker, (PricePoint(date(2020, 1, 2), adjusted, close, 1234),), "fixture")
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

    def test_supplement_preserves_base_price_within_reconciliation_tolerance(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, supplement = Path(tmp) / "base", Path(tmp) / "supplement"
            self.base_archive(base)
            payload = {"ticker": "AAA", "source": "yfinance_supplement_reconciled", "security_id": "",
                       "issuer_cik": "", "input_evidence_sha256": "",
                       "points": [{"day": "2020-01-02", "adjusted_close": 9.51,
                                   "raw_close": 10.01, "volume": 1234}]}
            _write_archive(supplement, [("price_series", "supplement", payload)], {})
            _, _, prices, _, _, issues = _load_archives([base, supplement])
        self.assertFalse(issues)
        self.assertEqual(prices[("AAA", "2020-01-02")]["raw_close"], 10.0)
        self.assertEqual(prices[("AAA", "2020-01-02")]["volume"], 1234)

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

    def test_adjusted_price_revision_warns_but_preserves_base_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, supplement = Path(tmp) / "base", Path(tmp) / "supplement"
            self.base_archive(base)
            report = collect_market_supplement([base], supplement, provider=Provider(changed_adjusted=True))
            _, _, prices, _, _, issues = _load_archives([base, supplement])
        self.assertEqual(report["captured_volume_points"], 1)
        self.assertTrue(report["warnings"])
        self.assertFalse(issues)
        self.assertEqual(prices[("AAA", "2020-01-02")]["adjusted_close"], 9.5)

    def test_compact_request_preserves_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            request = Path(tmp) / "request.json"
            supplement = Path(tmp) / "supplement"
            self.base_archive(base)
            created = create_market_supplement_request([base], request)
            report = collect_market_supplement([], supplement, provider=Provider(), request_path=request)
        self.assertEqual(created["required_volume_points"], 1)
        self.assertEqual(report["source_archive_sha256"], created["source_archive_sha256"])
        self.assertEqual(report["captured_volume_points"], 1)

    def test_yahoo_provider_limits_actions_to_requested_window(self):
        import pandas as pd
        from unittest.mock import patch
        from fundamental_analysis.market_supplement import YFinanceSupplementProvider

        frame = pd.DataFrame({"Close": [9.0, 10.0], "Adj Close": [8.5, 9.5],
                              "Volume": [100, 200], "Stock Splits": [2.0, 0.0],
                              "Dividends": [0.1, 0.2]},
                             index=pd.to_datetime(["2019-01-02", "2020-01-02"]))
        ticker = unittest.mock.Mock()
        ticker.history.return_value = frame
        module = unittest.mock.Mock()
        module.Ticker.return_value = ticker
        with patch.dict("sys.modules", {"yfinance": module}):
            _, actions = YFinanceSupplementProvider().fetch("AAA", date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(actions["events"], [])
        self.assertEqual([item["ex_date"] for item in actions["unresolved_dividends"]], ["2020-01-02"])


if __name__ == "__main__":
    unittest.main()

