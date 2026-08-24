import unittest
from datetime import date

from fundamental_analysis.institutional_prices import (
    TIINGO_LIFECYCLE_MAPPINGS,
    TiingoHistoricalPriceClient,
    TiingoSecurityMapping,
    validate_tiingo_mappings,
)
from fundamental_analysis.historical_price_readiness import (
    audit_historical_price_coverage,
    render_historical_price_readiness_markdown,
)
from fundamental_analysis.historical_prices import PricePoint, PriceSeries


def metadata(name="Medallia Inc."):
    return {
        "ticker": "MDLA",
        "name": name,
        "exchangeCode": "NYSE",
        "startDate": "2019-07-19",
        "endDate": "2021-10-29",
    }


def prices():
    return [
        {
            "date": "2019-07-19T00:00:00.000Z",
            "close": 37.20,
            "adjClose": 37.20,
        },
        {
            "date": "2020-03-20T00:00:00.000Z",
            "close": 18.10,
            "adjClose": 18.10,
        },
        {
            "date": "2021-10-29T00:00:00.000Z",
            "close": 33.99,
            "adjClose": 33.99,
        },
    ]


class TiingoHistoricalPriceTests(unittest.TestCase):
    def test_registry_covers_all_lifecycle_cases_and_bed_bath_alias(self):
        validate_tiingo_mappings()

        self.assertEqual(len(TIINGO_LIFECYCLE_MAPPINGS), 10)
        bed_bath = next(
            item
            for item in TIINGO_LIFECYCLE_MAPPINGS
            if item.canonical_ticker == "BBBY"
        )
        self.assertEqual(bed_bath.provider_ticker, "BBBYQ")
        self.assertEqual(bed_bath.issuer_cik, "0000886158")

    def test_fetches_adjusted_and_raw_prices_with_audited_identity(self):
        calls = []

        def get_json(url):
            calls.append(url)
            return prices() if "/prices?" in url else metadata()

        client = TiingoHistoricalPriceClient(json_getter=get_json)
        loaded = client.fetch_series(
            "MDLA",
            date(2019, 1, 1),
            date(2022, 1, 1),
        )
        cached = client.fetch_series(
            "MDLA",
            date(2020, 1, 1),
            date(2020, 12, 31),
        )

        self.assertEqual(len(loaded.points), 3)
        self.assertEqual(len(cached.points), 1)
        self.assertEqual(loaded.issuer_cik, "0001540184")
        self.assertIn("TIINGO:MDLA", loaded.security_id)
        self.assertEqual(loaded.points[1].raw_close, 18.10)
        self.assertEqual(loaded.points[1].adjusted_close, 18.10)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("token", loaded.source.casefold())

    def test_rejects_metadata_for_another_company(self):
        def get_json(url):
            return (
                prices()
                if "/prices?" in url
                else metadata("Unrelated Recycled Ticker Inc.")
            )

        client = TiingoHistoricalPriceClient(json_getter=get_json)

        with self.assertRaisesRegex(LookupError, "Emissor Tiingo"):
            client.fetch_series(
                "MDLA",
                date(2019, 1, 1),
                date(2022, 1, 1),
            )

    def test_live_access_requires_environment_token(self):
        with self.assertRaisesRegex(ValueError, "TIINGO_API_KEY"):
            TiingoHistoricalPriceClient(api_token="")

    def test_preflight_reports_complete_identity_and_price_coverage(self):
        mapping = TiingoSecurityMapping(
            "TEST",
            "TEST",
            "0000001234",
            "Test Company",
            date(2024, 1, 1),
            date(2024, 1, 5),
        )

        class Provider:
            def fetch_series(self, ticker, start, end):
                return PriceSeries(
                    ticker,
                    tuple(
                        PricePoint(date(2024, 1, day), 100.0 + day, 100.0 + day)
                        for day in range(1, 6)
                    ),
                    "fixture",
                    "FIXTURE:TEST",
                    "0000001234",
                )

        report = audit_historical_price_coverage(
            Provider(),
            provider_name="Fixture",
            mappings=(mapping,),
        )
        markdown = render_historical_price_readiness_markdown(report)

        self.assertTrue(report.is_ready)
        self.assertIn("Series aprovadas: 1/1", markdown)
        self.assertIn("| TEST | TEST | 0000001234 |", markdown)

    def test_preflight_rejects_sparse_series(self):
        mapping = TiingoSecurityMapping(
            "TEST",
            "TEST",
            "0000001234",
            "Test Company",
            date(2024, 1, 1),
            date(2024, 1, 20),
        )

        class Provider:
            def fetch_series(self, ticker, start, end):
                return PriceSeries(
                    ticker,
                    (
                        PricePoint(date(2024, 1, 1), 100.0, 100.0),
                        PricePoint(date(2024, 1, 20), 90.0, 90.0),
                    ),
                    "fixture",
                    "FIXTURE:TEST",
                    "0000001234",
                )

        report = audit_historical_price_coverage(
            Provider(),
            provider_name="Fixture",
            mappings=(mapping,),
        )

        self.assertFalse(report.is_ready)
        self.assertIn("lacuna maxima", report.rows[0].error)


if __name__ == "__main__":
    unittest.main()
