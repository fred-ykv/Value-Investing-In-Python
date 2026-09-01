def annual_fact(value, start, end, filed, accession, form="10-K", unit="USD"):
    return {
        "val": value,
        "start": start,
        "end": end,
        "filed": filed,
        "accn": accession,
        "form": form,
        "fy": int(end[:4]),
        "fp": "FY",
        "unit": unit,
    }


def instant_fact(value, end, filed, accession, form="10-K"):
    return {
        "val": value,
        "end": end,
        "filed": filed,
        "accn": accession,
        "form": form,
        "fy": int(end[:4]),
        "fp": "FY",
    }


def concept(entries, unit="USD"):
    return {"label": "Fixture", "description": "Fixture", "units": {unit: entries}}


def company_facts_fixture():
    a1 = "0000001234-24-000001"
    a2 = "0000001234-25-000001"
    filed1 = "2024-02-15"
    filed2 = "2025-02-15"
    prior_revenue = annual_fact(900, "2022-01-01", "2022-12-31", filed1, a1)
    current_revenue = annual_fact(1_000, "2023-01-01", "2023-12-31", filed1, a1)
    comparative_revenue = annual_fact(1_000, "2023-01-01", "2023-12-31", filed2, a2)
    future_revenue = annual_fact(2_000, "2024-01-01", "2024-12-31", filed2, a2)

    def annual_pair(prior, current, future):
        return [
            annual_fact(prior, "2022-01-01", "2022-12-31", filed1, a1),
            annual_fact(current, "2023-01-01", "2023-12-31", filed1, a1),
            annual_fact(current, "2023-01-01", "2023-12-31", filed2, a2),
            annual_fact(future, "2024-01-01", "2024-12-31", filed2, a2),
        ]

    def instant_pair(current, future):
        return [
            instant_fact(current, "2023-12-31", filed1, a1),
            instant_fact(future, "2024-12-31", filed2, a2),
        ]

    return {
        "cik": 1234,
        "entityName": "Test Corporation",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": concept(
                    [
                        prior_revenue,
                        current_revenue,
                        comparative_revenue,
                        future_revenue,
                    ]
                ),
                "OperatingIncomeLoss": concept(annual_pair(120, 140, 280)),
                "NetIncomeLoss": concept(annual_pair(80, 100, 200)),
                "IncomeTaxExpenseBenefit": concept(annual_pair(20, 25, 50)),
                "InterestExpenseNonOperating": concept(annual_pair(8, 10, 20)),
                "Assets": concept(instant_pair(1_500, 2_500)),
                "StockholdersEquity": concept(instant_pair(900, 1_400)),
                "CashAndCashEquivalentsAtCarryingValue": concept(instant_pair(200, 300)),
                "LongTermDebt": concept(instant_pair(300, 500)),
                "ShortTermBorrowings": concept(instant_pair(50, 80)),
                "AssetsCurrent": concept(instant_pair(600, 900)),
                "LiabilitiesCurrent": concept(instant_pair(300, 450)),
                "NetCashProvidedByUsedInOperatingActivities": concept(
                    annual_pair(145, 170, 300)
                ),
                "PaymentsToAcquirePropertyPlantAndEquipment": concept(
                    annual_pair(45, 50, 80)
                ),
                "DepreciationDepletionAndAmortization": concept(
                    annual_pair(35, 40, 60)
                ),
                "IncreaseDecreaseInAccountsReceivable": concept(
                    annual_pair(5, 10, 20)
                ),
                "IncreaseDecreaseInInventories": concept(
                    annual_pair(10, 15, 25)
                ),
                "IncreaseDecreaseInAccountsPayable": concept(
                    annual_pair(3, 4, 8)
                ),
                "IncreaseDecreaseInDeferredRevenue": concept(
                    annual_pair(2, 1, 3)
                ),
                "DeferredRevenue": concept(
                    [
                        instant_fact(8, "2021-12-31", filed1, a1),
                        instant_fact(10, "2022-12-31", filed1, a1),
                        instant_fact(11, "2023-12-31", filed1, a1),
                        instant_fact(10, "2022-12-31", filed2, a2),
                        instant_fact(11, "2023-12-31", filed2, a2),
                        instant_fact(14, "2024-12-31", filed2, a2),
                    ]
                ),
                "CommonStockDividendsPerShareDeclared": concept(
                    [
                        annual_fact(1.0, "2023-01-01", "2023-12-31", filed1, a1),
                        annual_fact(1.2, "2024-01-01", "2024-12-31", filed2, a2),
                    ],
                    "USD/shares",
                ),
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": concept(
                    [
                        instant_fact(100, "2024-01-31", filed1, a1),
                        instant_fact(110, "2025-01-31", filed2, a2),
                    ],
                    "shares",
                )
            },
        },
    }


def ticker_map_fixture():
    return {"0": {"cik_str": 1234, "ticker": "TEST", "title": "Test Corporation"}}
