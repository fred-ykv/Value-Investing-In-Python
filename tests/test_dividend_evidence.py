from pathlib import Path
import tempfile
import unittest
from fundamental_analysis.dividend_evidence import TiingoDividendClient, collect_dividend_evidence, reconcile_dates
from fundamental_analysis.market_supplement import _write_archive
from fundamental_analysis.historical_archive import ArchiveReader


class DividendEvidenceTests(unittest.TestCase):
    expected = [{"ticker": "AAA", "ex_date": "2020-01-10", "value": 0.1}]

    def row(self, **kwargs):
        return dict({"ticker": "aaa", "exDate": "2020-01-10", "paymentDate": "2020-02-01",
                     "declarationDate": "2020-01-01", "distribution": 0.2}, **kwargs)

    def test_matched_dates_do_not_certify_amount(self):
        result = reconcile_dates("AAA", self.expected, [self.row()])[0]
        self.assertEqual(result["status"], "dates_matched")
        self.assertFalse(result["cash_flow_approved"])

    def test_missing_duplicate_and_special_dividends_block(self):
        for response, status in [([], "missing"), ([self.row(), self.row()], "ambiguous"),
                                 ([self.row(paymentDate=None)], "dates_missing_or_special_event"),
                                 ([self.row(paymentDate="2020-01-09")], "dates_missing_or_special_event")]:
            with self.subTest(status=status):
                self.assertEqual(reconcile_dates("AAA", self.expected, response)[0]["status"], status)

    def test_wrong_ticker_rejected(self):
        with self.assertRaises(ValueError):
            reconcile_dates("AAA", self.expected, [self.row(ticker="BBB")])

    def test_archives_raw_response_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "source", Path(tmp) / "output"
            _write_archive(source, [("market_evidence_report", "report", {"unresolved_dividends": self.expected})], {})
            client = TiingoDividendClient(getter=lambda url: [self.row()])
            result = collect_dividend_evidence(source, output, client)
            archive = ArchiveReader(output)
            self.assertEqual(result["dates_matched"], 1)
            self.assertEqual(archive.load("dividend_provider_response", "AAA")["response"], [self.row()])
            self.assertFalse(result["benchmark_authorized"])

