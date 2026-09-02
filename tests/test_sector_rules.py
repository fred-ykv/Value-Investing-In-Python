import unittest

from fundamental_analysis.config import CompanyType
from fundamental_analysis.sector_rules import classify_company, classify_company_profile


class SectorRuleTests(unittest.TestCase):
    def test_consumer_defensive_beverages_are_not_ev_growth(self):
        info = {"sector": "Consumer Defensive", "industry": "Beverages - Non-Alcoholic"}

        self.assertEqual(classify_company(info), CompanyType.TRADITIONAL)

    def test_ev_acronym_matches_as_standalone_token(self):
        info = {"sector": "Consumer Cyclical", "industry": "EV Automaker"}

        self.assertEqual(classify_company(info), CompanyType.GROWTH_TECH)

    def test_traditional_auto_business_model_overrides_auto_manufacturer_label(self):
        info = {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "business_model": "traditional_auto"}

        self.assertEqual(classify_company(info), CompanyType.TRADITIONAL)

    def test_rivian_uses_audited_ev_pure_play_profile(self):
        profile = classify_company_profile(
            {
                "ticker": "RIVN",
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
            },
            has_negative_fcf=True,
        )

        self.assertEqual(profile.company_type, CompanyType.GROWTH_TECH)
        self.assertEqual(profile.business_model, "ev_pure_play")
        self.assertEqual(profile.rule_code, "audited_ticker_override")

    def test_traditional_automaker_is_not_promoted_by_negative_fcff_alone(self):
        profile = classify_company_profile(
            {
                "ticker": "GM",
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
            },
            has_negative_fcf=True,
        )

        self.assertEqual(profile.company_type, CompanyType.TRADITIONAL)
        self.assertEqual(profile.rule_code, "traditional_default")

    def test_credit_mentioned_in_industrial_description_does_not_make_it_a_bank(self):
        profile = classify_company_profile(
            {
                "ticker": "AUTO",
                "sector": "Consumer Cyclical",
                "industry": "Auto Manufacturers",
                "longBusinessSummary": "The group also provides customer credit.",
            }
        )

        self.assertEqual(profile.company_type, CompanyType.TRADITIONAL)


if __name__ == "__main__":
    unittest.main()
