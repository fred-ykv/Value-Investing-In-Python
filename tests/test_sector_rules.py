import unittest

from fundamental_analysis.config import CompanyType
from fundamental_analysis.sector_rules import classify_company


class SectorRuleTests(unittest.TestCase):
    def test_consumer_defensive_beverages_are_not_ev_growth(self):
        info = {"sector": "Consumer Defensive", "industry": "Beverages - Non-Alcoholic"}

        self.assertEqual(classify_company(info), CompanyType.TRADITIONAL)

    def test_ev_acronym_matches_as_standalone_token(self):
        info = {"sector": "Consumer Cyclical", "industry": "EV Automaker"}

        self.assertEqual(classify_company(info), CompanyType.GROWTH_TECH)


if __name__ == "__main__":
    unittest.main()
