import tempfile
import unittest
from copy import deepcopy
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

    def test_explicit_cik_keeps_delisted_company_resolvable(self):
        def get_json(url):
            if "company_tickers" in url:
                return {}
            return company_facts_fixture()

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            filings = client.list_annual_filings(
                "OLD",
                cik_override="1234",
            )
            snapshot = client.build_snapshot(
                "OLD",
                date(2024, 2, 16),
                cik_override="1234",
            )

        self.assertEqual(len(filings), 2)
        self.assertEqual(snapshot.cik, "0000001234")
        self.assertEqual(snapshot.ticker, "OLD")

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
        current_fcff = 140 * (1 - 25 / (140 - 10)) + 40 - 50 - 20
        prior_fcff = 120 * (1 - 20 / (120 - 8)) + 35 - 45 - 10
        fcff_growth = snapshot.market_data["fcff_growth"]
        self.assertAlmostEqual(fcff_growth.value, current_fcff / prior_fcff - 1)
        self.assertEqual(fcff_growth.period_start, date(2022, 12, 31))
        self.assertEqual(fcff_growth.period_end, date(2023, 12, 31))
        self.assertEqual(fcff_growth.filing_date, date(2024, 2, 15))
        self.assertEqual(
            fcff_growth.formula,
            "current_positive_fcff_divided_by_prior_positive_fcff_minus_one",
        )
        observations = dict(fcff_growth.input_observations)
        self.assertAlmostEqual(observations["current_fcff"], current_fcff)
        self.assertAlmostEqual(observations["prior_fcff"], prior_fcff)
        self.assertEqual(observations["current_change_in_nwc"], 20)
        self.assertEqual(observations["prior_change_in_nwc"], 10)
        self.assertIn("nwc_reconstruido_nos_dois_periodos", fcff_growth.note)
        self.assertTrue(fcff_growth.is_fallback)
        self.assertGreater(fcff_growth.confidence, 0.0)
        self.assertTrue(snapshot.audit.point_in_time_valid)
        self.assertEqual(snapshot.audit.coverage_ratio, 1.0)

    def test_reconstructs_economic_nwc_with_asset_and_liability_signs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            client = self.build_client(tempdir)
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        nwc = snapshot.cash_flow["change_in_nwc"]
        observations = dict(nwc.input_observations)
        self.assertEqual(nwc.value, 20)
        self.assertEqual(observations["receivables_economic_delta"], 10)
        self.assertEqual(observations["inventories_economic_delta"], 15)
        self.assertEqual(observations["payables_accrued_economic_delta"], -4)
        self.assertEqual(observations["customer_liability_economic_delta"], -1)
        self.assertEqual(
            observations["customer_liability_customer_liability_opening"],
            10,
        )
        self.assertEqual(
            observations["customer_liability_customer_liability_closing"],
            11,
        )
        self.assertEqual(
            nwc.formula,
            "economic_delta_nwc_from_sec_operating_component_groups",
        )
        self.assertTrue(nwc.is_fallback)
        self.assertGreater(nwc.confidence, 0.0)

    def test_customer_liability_prefers_comparative_balance_delta(self):
        payload = deepcopy(company_facts_fixture())
        entries = payload["facts"]["us-gaap"][
            "IncreaseDecreaseInDeferredRevenue"
        ]["units"]["USD"]
        for fact in entries:
            if (
                fact["accn"] == "0000001234-24-000001"
                and fact["end"] == "2023-12-31"
            ):
                fact["val"] = 999

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        nwc = snapshot.cash_flow["change_in_nwc"]
        self.assertEqual(nwc.value, 20)
        self.assertIn("DeferredRevenue", nwc.note)

    def test_customer_liability_falls_back_without_comparative_balances(self):
        payload = deepcopy(company_facts_fixture())
        payload["facts"]["us-gaap"].pop("DeferredRevenue")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        nwc = snapshot.cash_flow["change_in_nwc"]
        self.assertEqual(nwc.value, 20)
        self.assertIn("IncreaseDecreaseInDeferredRevenue", nwc.note)

    def test_rejects_one_sided_nwc_component_coverage(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap.pop("IncreaseDecreaseInAccountsPayable")
        gaap.pop("IncreaseDecreaseInDeferredRevenue")
        gaap.pop("DeferredRevenue")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        nwc = snapshot.cash_flow["change_in_nwc"]
        self.assertFalse(nwc.is_available)
        self.assertIn("ativos operacionais e passivos", nwc.note)
        observations = dict(snapshot.market_data["fcff_growth"].input_observations)
        self.assertEqual(observations["current_change_in_nwc_fallback_zero"], 0.0)
        self.assertEqual(observations["prior_change_in_nwc_fallback_zero"], 0.0)

    def test_fcff_growth_uses_symmetric_zero_for_asymmetric_nwc_coverage(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        for concept in (
            "IncreaseDecreaseInAccountsPayable",
            "IncreaseDecreaseInDeferredRevenue",
        ):
            entries = gaap[concept]["units"]["USD"]
            gaap[concept]["units"]["USD"] = [
                fact
                for fact in entries
                if not (
                    fact["accn"] == "0000001234-24-000001"
                    and fact["end"] == "2022-12-31"
                )
            ]
        gaap["DeferredRevenue"]["units"]["USD"] = [
            fact
            for fact in gaap["DeferredRevenue"]["units"]["USD"]
            if not (
                fact["accn"] == "0000001234-24-000001"
                and fact["end"] == "2021-12-31"
            )
        ]

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        growth = snapshot.market_data["fcff_growth"]
        observations = dict(growth.input_observations)
        current_without_nwc = 140 * (1 - 25 / (140 - 10)) + 40 - 50
        prior_without_nwc = 120 * (1 - 20 / (120 - 8)) + 35 - 45
        self.assertAlmostEqual(
            growth.value,
            current_without_nwc / prior_without_nwc - 1,
        )
        self.assertEqual(observations["current_change_in_nwc_fallback_zero"], 0.0)
        self.assertEqual(observations["prior_change_in_nwc_fallback_zero"], 0.0)
        self.assertIn("cobertura_assimetrica", growth.note)

    def test_fcff_growth_rejects_sign_changes_instead_of_inventing_growth(self):
        payload = deepcopy(company_facts_fixture())
        entries = payload["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"]
        for fact in entries:
            if (
                fact["accn"] == "0000001234-24-000001"
                and fact["end"] == "2022-12-31"
            ):
                fact["val"] = -100

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        growth = snapshot.market_data["fcff_growth"]
        self.assertFalse(growth.is_available)
        self.assertEqual(growth.source, "sec_edgar_derived")
        self.assertIn("precisam ser positivos", growth.note)
        self.assertLess(dict(growth.input_observations)["prior_fcff"], 0.0)

    def test_fcff_growth_records_missing_comparative_sec_inputs(self):
        payload = deepcopy(company_facts_fixture())
        entries = payload["facts"]["us-gaap"][
            "DepreciationDepletionAndAmortization"
        ]["units"]["USD"]
        payload["facts"]["us-gaap"]["DepreciationDepletionAndAmortization"][
            "units"
        ]["USD"] = [
            fact
            for fact in entries
            if not (
                fact["accn"] == "0000001234-24-000001"
                and fact["end"] == "2022-12-31"
            )
        ]

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        growth = snapshot.market_data["fcff_growth"]
        self.assertFalse(growth.is_available)
        self.assertIn("comparativo indisponivel", growth.note)
        self.assertIn("requires EBIT, tax rate, D&A, and capex", growth.note)

    def test_uses_lower_confidence_sec_da_fallback_for_fcff_growth(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap["DepreciationAmortizationAndAccretionNet"] = gaap.pop(
            "DepreciationDepletionAndAmortization"
        )

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        depreciation = snapshot.cash_flow["depreciation_amortization"]
        self.assertTrue(depreciation.is_fallback)
        self.assertIn("AccretionNet", depreciation.formula)
        self.assertTrue(snapshot.market_data["fcff_growth"].is_available)
        self.assertTrue(snapshot.market_data["fcff_growth"].is_fallback)

    def test_marks_partial_other_ppe_capex_concept_as_fallback(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap["PaymentsToAcquireOtherPropertyPlantAndEquipment"] = gaap.pop(
            "PaymentsToAcquirePropertyPlantAndEquipment"
        )

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        capex = snapshot.cash_flow["capex"]
        self.assertTrue(capex.is_fallback)
        self.assertIn("pode nao representar", capex.note)
        self.assertIn("OtherPropertyPlantAndEquipment", capex.formula)
        self.assertTrue(snapshot.market_data["fcff_growth"].is_available)
        self.assertTrue(snapshot.market_data["fcff_growth"].is_fallback)

    def test_annual_history_preserves_point_in_time_cutoff(self):
        with tempfile.TemporaryDirectory() as tempdir:
            client = self.build_client(tempdir)
            history = client.build_annual_history("TEST", date(2025, 2, 16))

        self.assertEqual(len(history), 2)
        self.assertEqual(
            [item.audit.anchor.accession_number for item in history],
            ["0000001234-24-000001", "0000001234-25-000001"],
        )
        self.assertTrue(
            all(item.audit.latest_filing_date <= date(2025, 2, 16) for item in history)
        )
        self.assertTrue(all(item.audit.point_in_time_valid for item in history))

    def test_filing_is_not_available_before_configured_lag(self):
        with tempfile.TemporaryDirectory() as tempdir:
            client = self.build_client(tempdir)

            with self.assertRaises(LookupError):
                client.build_snapshot("TEST", date(2024, 2, 15))

    def test_production_access_requires_identifying_user_agent(self):
        with self.assertRaises(ValueError):
            SecEdgarClient(user_agent="anonymous")

    def test_accepts_observed_sec_fallback_concepts_for_capex_and_interest(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap["PaymentsToAcquireProductiveAssets"] = gaap.pop(
            "PaymentsToAcquirePropertyPlantAndEquipment"
        )
        gaap["InterestExpense"] = gaap.pop("InterestExpenseNonOperating")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        self.assertEqual(snapshot.cash_flow["capex"].value, 50)
        self.assertEqual(snapshot.income_statement["interest_expense"].value, 10)

    def test_accepts_including_tax_revenue_and_common_holder_income(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap["RevenueFromContractWithCustomerIncludingAssessedTax"] = gaap.pop(
            "RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        gaap["NetIncomeLossAvailableToCommonStockholdersBasic"] = gaap.pop(
            "NetIncomeLoss"
        )

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        self.assertEqual(snapshot.income_statement["revenue"].value, 1_000)
        self.assertEqual(snapshot.income_statement["net_income"].value, 100)
        self.assertFalse(snapshot.cash_flow["capex"].is_fallback)
        self.assertFalse(snapshot.income_statement["interest_expense"].is_fallback)

    def test_derives_lower_confidence_ebit_proxy_when_reported_ebit_is_missing(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap[
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
        ] = gaap.pop("OperatingIncomeLoss")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        ebit = snapshot.income_statement["ebit"]
        self.assertEqual(ebit.value, 150)
        self.assertTrue(ebit.is_fallback)
        self.assertEqual(ebit.formula, "pretax_income_plus_abs_interest_expense")
        self.assertLess(ebit.confidence, snapshot.income_statement["net_income"].confidence)
        self.assertIn(
            "Metricas derivadas por fallback: change_in_nwc, ebit, fcff_growth.",
            snapshot.audit.warnings,
        )

    def test_uses_us_gaap_fallback_for_shares_when_dei_concept_is_missing(self):
        payload = deepcopy(company_facts_fixture())
        dei_units = payload["facts"]["dei"].pop(
            "EntityCommonStockSharesOutstanding"
        )
        payload["facts"]["us-gaap"]["CommonStockSharesOutstanding"] = dei_units

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        shares = snapshot.market_data["shares"]
        self.assertEqual(shares.value, 100)
        self.assertTrue(shares.is_fallback)
        self.assertIn("us-gaap", shares.formula)

    def test_uses_weighted_average_diluted_shares_as_last_filing_fallback(self):
        payload = deepcopy(company_facts_fixture())
        payload["facts"]["dei"].pop("EntityCommonStockSharesOutstanding")
        payload["facts"]["us-gaap"]["WeightedAverageNumberOfDilutedSharesOutstanding"] = {
            "label": "Diluted shares",
            "description": "Diluted shares",
            "units": {
                "shares": [
                    {
                        "val": 125,
                        "start": "2023-01-01",
                        "end": "2023-12-31",
                        "filed": "2024-02-15",
                        "accn": "0000001234-24-000001",
                        "form": "10-K",
                    }
                ]
            },
        }

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        shares = snapshot.market_data["shares"]
        self.assertEqual(shares.value, 125)
        self.assertTrue(shares.is_fallback)
        self.assertEqual(
            shares.confidence,
            client.assumptions.weighted_average_shares_fallback_confidence,
        )
        self.assertIn("WeightedAverageNumberOfDilutedSharesOutstanding", shares.formula)

    def test_accepts_complete_debt_and_capital_lease_concept(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap["DebtAndCapitalLeaseObligations"] = gaap.pop("LongTermDebt")
        gaap.pop("ShortTermBorrowings")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        self.assertEqual(snapshot.balance_sheet["total_debt"].value, 300)

    def test_sums_debt_current_and_noncurrent_concepts(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap["LongTermDebtNoncurrent"] = gaap.pop("LongTermDebt")
        gaap["DebtCurrent"] = gaap.pop("ShortTermBorrowings")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        self.assertEqual(snapshot.balance_sheet["total_debt"].value, 350)

    def test_sums_notes_payable_current_and_noncurrent_concepts(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap["LongTermNotesPayable"] = gaap.pop("LongTermDebt")
        gaap["NotesPayableCurrent"] = gaap.pop("ShortTermBorrowings")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        self.assertEqual(snapshot.balance_sheet["total_debt"].value, 350)

    def test_ebit_proxy_accepts_net_nonoperating_interest_with_extra_penalty(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap[
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
        ] = gaap.pop("OperatingIncomeLoss")
        interest = gaap.pop("InterestExpenseNonOperating")
        for fact in interest["units"]["USD"]:
            fact["val"] = -abs(fact["val"])
        gaap["InterestIncomeExpenseNonoperatingNet"] = interest

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        ebit = snapshot.income_statement["ebit"]
        self.assertEqual(ebit.value, 150)
        self.assertTrue(ebit.is_fallback)
        self.assertIn("juros liquidos", ebit.note)
        self.assertLess(ebit.confidence, 0.80)

    def test_uses_auditable_zero_debt_fallback_without_financing_evidence(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap.pop("LongTermDebt")
        gaap.pop("ShortTermBorrowings")
        gaap.pop("InterestExpenseNonOperating")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        debt = snapshot.balance_sheet["total_debt"]
        self.assertEqual(debt.value, 0.0)
        self.assertTrue(debt.is_fallback)
        self.assertEqual(
            debt.formula,
            "zero_debt_absence_of_anchor_financing_evidence",
        )
        self.assertEqual(debt.confidence, client.assumptions.zero_debt_fallback_confidence)

    def test_does_not_assume_zero_debt_when_interest_evidence_exists(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap.pop("LongTermDebt")
        gaap.pop("ShortTermBorrowings")

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        self.assertNotIn("total_debt", snapshot.balance_sheet)

    def test_discloses_operating_lease_without_treating_it_as_financial_debt(self):
        payload = deepcopy(company_facts_fixture())
        gaap = payload["facts"]["us-gaap"]
        gaap.pop("LongTermDebt")
        gaap.pop("ShortTermBorrowings")
        gaap.pop("InterestExpenseNonOperating")
        gaap["OperatingLeaseLiability"] = gaap["Assets"].copy()

        def get_json(url):
            return ticker_map_fixture() if "company_tickers" in url else payload

        with tempfile.TemporaryDirectory() as tempdir:
            client = SecEdgarClient(
                "Test Research test@example.com",
                cache_dir=tempdir,
                json_getter=get_json,
            )
            snapshot = client.build_snapshot("TEST", date(2024, 2, 16))

        debt = snapshot.balance_sheet["total_debt"]
        self.assertEqual(debt.value, 0.0)
        self.assertIn("arrendamento operacional", debt.note)
        self.assertIn("ajuste simetrico de EBIT e FCFF", debt.note)


if __name__ == "__main__":
    unittest.main()
