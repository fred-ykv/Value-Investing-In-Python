import tempfile
import unittest
from dataclasses import replace
from datetime import date

from fundamental_analysis.config import POINT_IN_TIME
from fundamental_analysis.historical_macro import HistoricalMacroClient


def erp_html():
    rows = "".join(
        f"<tr><td>{year}</td><td>4.00%</td><td>{4.00 + (year - 2014) * 0.10:.2f}%</td></tr>"
        for year in range(2014, 2025)
    )
    return (
        "<html><table><tr><th>Year</th><th>T.Bond Rate</th>"
        f"<th>Implied ERP (FCFE)</th></tr>{rows}</table></html>"
    )


class HistoricalMacroTests(unittest.TestCase):
    def build_client(self, treasury_by_year, assumptions=POINT_IN_TIME):
        def get_text(url):
            if "treasury" in url:
                year = int(url.split("daily-treasury-rates.csv/")[1].split("/")[0])
                return treasury_by_year.get(year, "Date,10 Yr\n")
            return erp_html()

        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        return HistoricalMacroClient(
            assumptions=assumptions,
            cache_dir=tempdir.name,
            text_getter=get_text,
        )

    def test_selects_latest_treasury_on_or_before_date_and_available_erp(self):
        client = self.build_client(
            {
                2023: "Date,10 Yr\n12/29/2023,3.88\n",
                2024: (
                    "Date,10 Yr\n"
                    "02/27/2024,4.30\n"
                    "02/28/2024,4.25\n"
                    "03/01/2024,4.20\n"
                ),
            }
        )

        snapshot = client.snapshot(date(2024, 2, 29))

        self.assertAlmostEqual(snapshot.risk_free_rate.value, 0.0425)
        self.assertEqual(snapshot.risk_free_observation_date, date(2024, 2, 28))
        self.assertEqual(snapshot.erp_reference_year, 2023)
        self.assertAlmostEqual(snapshot.equity_risk_premium.value, 0.049)
        self.assertEqual(snapshot.erp_available_from, date(2024, 1, 15))
        self.assertTrue(snapshot.point_in_time_valid)

    def test_erp_is_not_used_before_configured_publication_date(self):
        client = self.build_client(
            {
                2023: "Date,10 Yr\n12/29/2023,3.88\n",
                2024: "Date,10 Yr\n01/09/2024,4.02\n",
            }
        )

        snapshot = client.snapshot(date(2024, 1, 10))

        self.assertEqual(snapshot.erp_reference_year, 2022)
        self.assertEqual(snapshot.erp_available_from, date(2023, 1, 15))

    def test_stale_risk_free_rate_is_rejected(self):
        assumptions = replace(POINT_IN_TIME, risk_free_max_staleness_days=3)
        client = self.build_client(
            {
                2023: "Date,10 Yr\n12/29/2023,3.88\n",
                2024: "Date,10 Yr\n01/01/2024,4.00\n",
            },
            assumptions,
        )

        with self.assertRaises(LookupError):
            client.snapshot(date(2024, 1, 10))

    def test_future_treasury_observation_cannot_fill_snapshot(self):
        client = self.build_client(
            {
                2023: "Date,10 Yr\n",
                2024: "Date,10 Yr\n03/01/2024,4.20\n",
            }
        )

        with self.assertRaises(LookupError):
            client.snapshot(date(2024, 2, 29))


if __name__ == "__main__":
    unittest.main()
