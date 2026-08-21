import tempfile
import unittest
from datetime import date

from fundamental_analysis.sec_edgar import SecEdgarClient
from tests.sec_fixtures import company_facts_fixture, ticker_map_fixture


class SecEdgarClientTests(unittest.TestCase):
    def build_client(self, cache_dir):
        def get_json(url):
            if "company_tickers" in url:
                return ticker_map_fixture()
            return company_facts_fixture()

        return SecEdgarClient(
            "Test Research test@example.com",
            cache_dir=cache_dir,
            json_getter=get_json,
        )

    def test_resolves_cik_and_lists_original_annual_filings(self):
        with tempfile.TemporaryDirectory() as tempdir:
            client = self.build_client(tempdir)

            self.assertEqual(client.resolve_cik("test"), "0000001234")
            filings = client.list_annual_filings("TEST")

        self.assertEqual(len(filings), 2)
        self.assertEqual(filings[0].accession_number, "0000001234-24-000001")
        self.assertEqual(filings[0].report_end, date(2023, 12, 31))

    def test_snapshot_uses_only_facts_known_by_as_of_date(self):
        with tempfile.TemporaryDirectory() as tempdir:
            client = self.build_client(tempdir)
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        self.assertEqual(snapshot.audit.anchor.accession_number, "0000001234-24-000001")
        self.assertEqual(snapshot.income_statement["revenue"].value, 1_000)
        self.assertEqual(snapshot.income_statement["revenue"].filing_date, date(2024, 2, 15))
        self.assertAlmostEqual(snapshot.market_data["revenue_growth"].value, 1_000 / 900 - 1)
        self.assertEqual(snapshot.market_data["shares"].value, 100)
        self.assertEqual(snapshot.balance_sheet["total_liabilities"].value, 600)
        self.assertEqual(snapshot.balance_sheet["total_debt"].value, 350)
        self.assertTrue(snapshot.audit.point_in_time_valid)
        self.assertGreater(snapshot.audit.coverage_ratio, 0.80)

    def test_filing_is_not_available_before_configured_lag(self):
        with tempfile.TemporaryDirectory() as tempdir:
            client = self.build_client(tempdir)

            with self.assertRaises(LookupError):
                client.build_snapshot("TEST", date(2024, 2, 15))

    def test_production_access_requires_identifying_user_agent(self):
        with self.assertRaises(ValueError):
            SecEdgarClient(user_agent="anonymous")


if __name__ == "__main__":
    unittest.main()

