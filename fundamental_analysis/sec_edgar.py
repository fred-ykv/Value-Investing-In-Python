"""SEC EDGAR company-facts adapter with point-in-time filing controls."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .config import POINT_IN_TIME, PointInTimeAssumptions
from .data_sources import MetricValue, metric_value, safe_float
from .financial_statements import FinancialStatements, build_statement_metrics


@dataclass(frozen=True)
class SecFilingAnchor:
    ticker: str
    cik: str
    accession_number: str
    form: str
    filed: date
    report_end: date


@dataclass(frozen=True)
class SnapshotAudit:
    as_of: date
    anchor: SecFilingAnchor
    selected_metrics: tuple[str, ...]
    missing_metrics: tuple[str, ...]
    coverage_ratio: float
    latest_filing_date: date
    point_in_time_valid: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PointInTimeFundamentals:
    ticker: str
    cik: str
    as_of: date
    income_statement: Mapping[str, MetricValue]
    balance_sheet: Mapping[str, MetricValue]
    cash_flow: Mapping[str, MetricValue]
    market_data: Mapping[str, MetricValue]
    info: Mapping[str, object]
    audit: SnapshotAudit

    def as_financial_statements(
        self,
        *,
        market_overrides: Mapping[str, object] | None = None,
        info_overrides: Mapping[str, object] | None = None,
    ) -> FinancialStatements:
        return FinancialStatements(
            self.ticker,
            self.income_statement,
            self.balance_sheet,
            self.cash_flow,
            {**self.market_data, **(market_overrides or {})},
            {**self.info, **(info_overrides or {})},
            "sec_edgar",
        )


@dataclass(frozen=True)
class _FactSpec:
    concepts: tuple[str, ...]
    units: tuple[str, ...]
    duration: bool
    taxonomy: str = "us-gaap"
    instant_window_days: int = 0


SEC_FACT_SPECS: dict[str, dict[str, _FactSpec]] = {
    "income_statement": {
        "revenue": _FactSpec(
            (
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "Revenues",
                "SalesRevenueNet",
                "SalesRevenueGoodsNet",
                "SalesRevenueServicesNet",
                "LicenseAndServicesRevenue",
            ),
            ("USD",),
            True,
        ),
        "ebit": _FactSpec(("OperatingIncomeLoss",), ("USD",), True),
        "net_income": _FactSpec(
            (
                "NetIncomeLoss",
                "ProfitLoss",
                "NetIncomeLossAvailableToCommonStockholdersBasic",
            ),
            ("USD",),
            True,
        ),
        "tax_provision": _FactSpec(("IncomeTaxExpenseBenefit",), ("USD",), True),
        "interest_expense": _FactSpec(
            (
                "InterestExpenseNonOperating",
                "InterestExpenseNonoperating",
                "InterestAndDebtExpense",
                "InterestExpense",
                "InterestExpenseDebt",
                "InterestExpenseOperating",
            ),
            ("USD",),
            True,
        ),
    },
    "balance_sheet": {
        "total_assets": _FactSpec(("Assets",), ("USD",), False),
        "total_liabilities": _FactSpec(("Liabilities",), ("USD",), False),
        "equity": _FactSpec(
            (
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ),
            ("USD",),
            False,
        ),
        "cash": _FactSpec(
            (
                "CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            ),
            ("USD",),
            False,
        ),
        "total_debt": _FactSpec(
            (
                "LongTermDebtAndFinanceLeaseObligations",
                "LongTermDebtAndCapitalLeaseObligationsCurrentAndNoncurrent",
                "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                "LongTermDebtAndCapitalLeaseObligations",
                "DebtAndCapitalLeaseObligations",
                "FinanceLeaseLiability",
                "LongTermDebt",
                "DebtCurrentAndNoncurrent",
            ),
            ("USD",),
            False,
        ),
        "current_assets": _FactSpec(("AssetsCurrent",), ("USD",), False),
        "current_liabilities": _FactSpec(("LiabilitiesCurrent",), ("USD",), False),
    },
    "cash_flow": {
        "cfo": _FactSpec(
            ("NetCashProvidedByUsedInOperatingActivities",),
            ("USD",),
            True,
        ),
        "capex": _FactSpec(
            (
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "PaymentsForAdditionsToPropertyPlantAndEquipment",
                "PaymentsToAcquireProductiveAssets",
            ),
            ("USD",),
            True,
        ),
        "depreciation_amortization": _FactSpec(
            (
                "DepreciationDepletionAndAmortization",
                "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
                "DepreciationAndAmortization",
                "Depreciation",
            ),
            ("USD",),
            True,
        ),
    },
    "market_data": {
        "shares": _FactSpec(
            ("EntityCommonStockSharesOutstanding",),
            ("shares",),
            False,
            taxonomy="dei",
            instant_window_days=120,
        ),
        "dividend_per_share": _FactSpec(
            ("CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"),
            ("USD/shares", "USD / shares"),
            True,
        ),
    },
}

# Optional because banks and some issuers do not present gross profit as a
# separate line. Its absence must not reduce the core filing coverage gate.
GROSS_PROFIT_SPEC = _FactSpec(("GrossProfit",), ("USD",), True)


JsonGetter = Callable[[str], Mapping[str, Any]]


class SecEdgarClient:
    def __init__(
        self,
        user_agent: str | None = None,
        *,
        assumptions: PointInTimeAssumptions = POINT_IN_TIME,
        cache_dir: str | Path | None = None,
        json_getter: JsonGetter | None = None,
    ):
        self.assumptions = assumptions
        self.user_agent = user_agent or os.environ.get(assumptions.sec_user_agent_env, "")
        self.json_getter = json_getter
        if json_getter is None and ("@" not in self.user_agent or len(self.user_agent) < 8):
            raise ValueError(
                f"Defina {assumptions.sec_user_agent_env} com nome/aplicacao e e-mail de contato "
                "antes de acessar a SEC EDGAR."
            )
        self.cache_dir = Path(cache_dir or assumptions.cache_directory)
        self._last_request_at = 0.0

    def resolve_cik(self, ticker: str, cik_override: str | None = None) -> str:
        normalized = ticker.upper().strip()
        if cik_override is not None:
            candidate = str(cik_override).strip()
            if not candidate.isdigit() or len(candidate) > 10:
                raise ValueError(f"CIK explicito invalido para {normalized}: {candidate}")
            return candidate.zfill(10)
        payload = self._load_json(self.assumptions.sec_ticker_map_url, "company_tickers.json")
        records: Iterable[object]
        if isinstance(payload, Mapping):
            records = payload.values()
        else:
            records = ()
        for raw_record in records:
            if not isinstance(raw_record, Mapping):
                continue
            if str(raw_record.get("ticker", "")).upper().strip() == normalized:
                cik = str(raw_record.get("cik_str", "")).strip()
                if cik:
                    return cik.zfill(10)
        raise KeyError(f"Ticker {normalized} nao encontrado no mapa oficial de CIKs da SEC")

    def fetch_company_facts(self, cik: str) -> Mapping[str, Any]:
        normalized_cik = str(cik).zfill(10)
        url = f"{self.assumptions.sec_base_url}/api/xbrl/companyfacts/CIK{normalized_cik}.json"
        return self._load_json(url, f"companyfacts_CIK{normalized_cik}.json")

    def list_annual_filings(
        self,
        ticker: str,
        *,
        cik_override: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        max_filings: int | None = None,
    ) -> list[SecFilingAnchor]:
        cik = self.resolve_cik(ticker, cik_override)
        payload = self.fetch_company_facts(cik)
        anchors = _annual_anchors(ticker.upper().strip(), cik, payload, self.assumptions)
        if start_year is not None:
            anchors = [anchor for anchor in anchors if anchor.filed.year >= start_year]
        if end_year is not None:
            anchors = [anchor for anchor in anchors if anchor.filed.year <= end_year]
        if max_filings == 0:
            return []
        if max_filings is not None and max_filings > 0:
            anchors = anchors[-max_filings:]
        return anchors

    def build_snapshot(
        self,
        ticker: str,
        as_of: date,
        *,
        anchor_accession: str | None = None,
        cik_override: str | None = None,
    ) -> PointInTimeFundamentals:
        normalized_ticker = ticker.upper().strip()
        cik = self.resolve_cik(normalized_ticker, cik_override)
        payload = self.fetch_company_facts(cik)
        anchors = _annual_anchors(normalized_ticker, cik, payload, self.assumptions)
        available = [
            anchor
            for anchor in anchors
            if (as_of - anchor.filed).days >= self.assumptions.minimum_filing_lag_days
        ]
        if anchor_accession:
            available = [anchor for anchor in available if anchor.accession_number == anchor_accession]
        if not available:
            suffix = f" para o accession {anchor_accession}" if anchor_accession else ""
            raise LookupError(f"Nenhum formulario anual estava disponivel em {as_of}{suffix}")
        anchor = max(available, key=lambda item: (item.filed, item.report_end))
        source_url = (
            f"{self.assumptions.sec_base_url}/api/xbrl/companyfacts/CIK{cik}.json"
        )

        sections: dict[str, dict[str, MetricValue]] = {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "market_data": {},
        }
        for section, specs in SEC_FACT_SPECS.items():
            for name, spec in specs.items():
                selected = _select_metric(payload, name, spec, anchor, source_url)
                if selected.is_available:
                    sections[section][name] = selected

        gross_profit = _select_metric(
            payload,
            "gross_profit",
            GROSS_PROFIT_SPEC,
            anchor,
            source_url,
        )
        if gross_profit.is_available:
            sections["income_statement"]["gross_profit"] = gross_profit

        _complete_ebit(sections["income_statement"], payload, anchor, source_url)
        _complete_depreciation_amortization(
            sections["cash_flow"],
            payload,
            anchor,
            source_url,
        )
        _complete_capex(
            sections["cash_flow"],
            payload,
            anchor,
            source_url,
        )
        sections["cash_flow"]["change_in_nwc"] = _derive_change_in_nwc(
            payload,
            anchor,
            source_url,
            self.assumptions,
        )
        _complete_balance_sheet(sections["balance_sheet"], payload, anchor, source_url)
        _complete_total_debt(
            sections["balance_sheet"],
            payload,
            anchor,
            source_url,
            self.assumptions,
        )
        _complete_shares(
            sections["market_data"],
            payload,
            anchor,
            source_url,
            self.assumptions,
        )
        revenue = sections["income_statement"].get("revenue")
        if revenue is not None and gross_profit.is_available:
            sections["market_data"]["gross_margin"] = _derive_gross_margin(
                gross_profit,
                revenue,
            )
        if revenue is not None:
            growth = _derive_revenue_growth(
                payload,
                revenue,
                anchor,
                source_url,
                self.assumptions,
            )
            if growth.is_available:
                sections["market_data"]["revenue_growth"] = growth
        sections["market_data"]["fcff_growth"] = _derive_fcff_growth(
            payload,
            sections["income_statement"],
            sections["cash_flow"],
            anchor,
            source_url,
            self.assumptions,
        )

        expected = tuple(
            name for specs in SEC_FACT_SPECS.values() for name in specs
        )
        selected_names = tuple(
            sorted(
                name
                for section in sections.values()
                for name, metric in section.items()
                if metric.is_available
            )
        )
        expected_names = set(expected)
        selected_expected_names = expected_names.intersection(selected_names)
        missing = tuple(sorted(expected_names - selected_expected_names))
        coverage = len(selected_expected_names) / len(expected) if expected else 0.0
        metric_dates = [
            metric.filing_date
            for section in sections.values()
            for metric in section.values()
            if metric.filing_date is not None
        ]
        latest_filing = max(metric_dates, default=anchor.filed)
        valid = latest_filing <= as_of and (as_of - anchor.filed).days >= self.assumptions.minimum_filing_lag_days
        warnings: list[str] = []
        if coverage < self.assumptions.minimum_fundamental_coverage:
            warnings.append(
                f"Cobertura fundamental de {coverage:.1%} abaixo do minimo de "
                f"{self.assumptions.minimum_fundamental_coverage:.1%}."
            )
        if missing:
            warnings.append("Metricas SEC ausentes: " + ", ".join(missing) + ".")
        fallback_metrics = sorted(
            metric.name
            for section in sections.values()
            for metric in section.values()
            if metric.is_available and metric.is_fallback
        )
        if fallback_metrics:
            warnings.append(
                "Metricas derivadas por fallback: " + ", ".join(fallback_metrics) + "."
            )
        if not valid:
            warnings.append("Snapshot rejeitado pelo controle point-in-time.")

        audit = SnapshotAudit(
            as_of=as_of,
            anchor=anchor,
            selected_metrics=selected_names,
            missing_metrics=missing,
            coverage_ratio=coverage,
            latest_filing_date=latest_filing,
            point_in_time_valid=valid,
            warnings=tuple(warnings),
        )
        info = {
            "ticker": normalized_ticker,
            "cik": cik,
            "entity_name": payload.get("entityName", ""),
            "filing_accession": anchor.accession_number,
            "filing_form": anchor.form,
            "filing_date": anchor.filed.isoformat(),
            "report_end": anchor.report_end.isoformat(),
        }
        return PointInTimeFundamentals(
            normalized_ticker,
            cik,
            as_of,
            sections["income_statement"],
            sections["balance_sheet"],
            sections["cash_flow"],
            sections["market_data"],
            info,
            audit,
        )

    def build_annual_history(
        self,
        ticker: str,
        as_of: date,
        *,
        max_filings: int = 10,
        cik_override: str | None = None,
    ) -> list[PointInTimeFundamentals]:
        anchors = [
            anchor
            for anchor in self.list_annual_filings(
                ticker,
                cik_override=cik_override,
            )
            if (as_of - anchor.filed).days >= self.assumptions.minimum_filing_lag_days
        ]
        if max_filings <= 0:
            return []
        return [
            self.build_snapshot(
                ticker,
                as_of,
                anchor_accession=anchor.accession_number,
                cik_override=cik_override,
            )
            for anchor in anchors[-max_filings:]
        ]

    def _load_json(self, url: str, cache_name: str) -> Mapping[str, Any]:
        cache_path = self.cache_dir / cache_name
        cache_is_fresh = (
            cache_path.exists()
            and time.time() - cache_path.stat().st_mtime
            <= self.assumptions.cache_max_age_hours * 3600
        )
        if cache_is_fresh:
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(payload, Mapping):
                    return payload
            except (OSError, json.JSONDecodeError):
                pass
        if self.json_getter is not None:
            payload = self.json_getter(url)
        else:
            payload = self._request_json(url)
        if not isinstance(payload, Mapping):
            raise TypeError(f"Resposta JSON invalida da SEC para {url}")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cache_path)
        return payload

    def _request_json(self, url: str) -> Mapping[str, Any]:
        import requests

        minimum_interval = 1.0 / max(0.1, self.assumptions.sec_max_requests_per_second)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < minimum_interval:
            time.sleep(minimum_interval - elapsed)
        response = requests.get(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            },
            timeout=self.assumptions.request_timeout_seconds,
        )
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise TypeError(f"Resposta JSON invalida da SEC para {url}")
        return payload


def _annual_anchors(
    ticker: str,
    cik: str,
    payload: Mapping[str, Any],
    assumptions: PointInTimeAssumptions,
) -> list[SecFilingAnchor]:
    by_accession: dict[str, SecFilingAnchor] = {}
    allowed_forms = set(assumptions.annual_forms)
    for _, _, _, fact in _iter_facts(payload):
        form = str(fact.get("form", ""))
        accession = str(fact.get("accn", ""))
        filed = _parse_date(fact.get("filed"))
        period_start = _parse_date(fact.get("start"))
        report_end = _parse_date(fact.get("end"))
        if (
            form not in allowed_forms
            or not accession
            or filed is None
            or period_start is None
            or report_end is None
            or not 250 <= (report_end - period_start).days <= 450
        ):
            continue
        candidate = SecFilingAnchor(ticker, cik, accession, form, filed, report_end)
        current = by_accession.get(accession)
        if current is None or candidate.report_end > current.report_end:
            by_accession[accession] = candidate

    by_report_end: dict[date, SecFilingAnchor] = {}
    for anchor in by_accession.values():
        current = by_report_end.get(anchor.report_end)
        if current is None or anchor.filed < current.filed:
            by_report_end[anchor.report_end] = anchor
    return sorted(by_report_end.values(), key=lambda item: (item.filed, item.report_end))


def _select_metric(
    payload: Mapping[str, Any],
    name: str,
    spec: _FactSpec,
    anchor: SecFilingAnchor,
    source_url: str,
) -> MetricValue:
    for concept in spec.concepts:
        candidates = _matching_facts(payload, spec, concept, anchor)
        if not candidates:
            continue
        fact = max(candidates, key=lambda item: (_parse_date(item.get("filed")) or date.min, str(item.get("start", ""))))
        value = safe_float(fact.get("val"))
        if value is None:
            continue
        return metric_value(
            name,
            value,
            "sec_edgar",
            f"{anchor.form} {anchor.accession_number}; {spec.taxonomy}:{concept}",
            source_url=source_url,
            source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
            period_start=_parse_date(fact.get("start")),
            period_end=_parse_date(fact.get("end")),
            filing_date=_parse_date(fact.get("filed")),
            as_of=datetime.combine(anchor.filed, datetime.min.time()),
            currency="USD" if any("USD" in unit for unit in spec.units) else None,
            scale="raw",
            basis="reported",
            formula=f"sec_xbrl:{spec.taxonomy}:{concept}",
        )
    return MetricValue(name, None, "missing", 0.0, "not found in anchor filing")


def _matching_facts(
    payload: Mapping[str, Any],
    spec: _FactSpec,
    concept: str,
    anchor: SecFilingAnchor,
) -> list[Mapping[str, Any]]:
    facts = payload.get("facts", {})
    taxonomy = facts.get(spec.taxonomy, {}) if isinstance(facts, Mapping) else {}
    concept_payload = taxonomy.get(concept, {}) if isinstance(taxonomy, Mapping) else {}
    units = concept_payload.get("units", {}) if isinstance(concept_payload, Mapping) else {}
    candidates: list[Mapping[str, Any]] = []
    for unit in spec.units:
        entries = units.get(unit, []) if isinstance(units, Mapping) else []
        for fact in entries if isinstance(entries, list) else []:
            if not isinstance(fact, Mapping):
                continue
            if str(fact.get("accn", "")) != anchor.accession_number:
                continue
            if str(fact.get("form", "")) != anchor.form:
                continue
            fact_end = _parse_date(fact.get("end"))
            if spec.duration or spec.instant_window_days == 0:
                if fact_end != anchor.report_end:
                    continue
            elif (
                fact_end is None
                or fact_end < anchor.report_end
                or fact_end > anchor.filed
                or (fact_end - anchor.report_end).days > spec.instant_window_days
            ):
                continue
            start = _parse_date(fact.get("start"))
            if spec.duration:
                if start is None:
                    continue
                days = (anchor.report_end - start).days
                if not 250 <= days <= 450:
                    continue
            elif start is not None:
                continue
            candidates.append(fact)
    return candidates


def _complete_depreciation_amortization(
    cash_flow: dict[str, MetricValue],
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
) -> None:
    if "depreciation_amortization" in cash_flow:
        return
    fallback = _select_metric(
        payload,
        "depreciation_amortization",
        _FactSpec(
            (
                "DepreciationAmortizationAndAccretionNet",
                "OtherDepreciationAndAmortization",
            ),
            ("USD",),
            True,
        ),
        anchor,
        source_url,
    )
    if fallback.is_available:
        cash_flow["depreciation_amortization"] = replace(
            fallback,
            confidence=max(0.0, fallback.confidence - 0.10),
            note=(
                "Fallback SEC para depreciacao e amortizacao; o conceito pode "
                "incluir accretion ou outros componentes e recebe penalidade de "
                "confianca."
            ),
            basis="derived",
            is_fallback=True,
        )


def _complete_capex(
    cash_flow: dict[str, MetricValue],
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
) -> None:
    if "capex" in cash_flow:
        return
    fallback = _select_metric(
        payload,
        "capex",
        _FactSpec(
            ("PaymentsToAcquireOtherPropertyPlantAndEquipment",),
            ("USD",),
            True,
        ),
        anchor,
        source_url,
    )
    if fallback.is_available:
        cash_flow["capex"] = replace(
            fallback,
            confidence=max(0.0, fallback.confidence - 0.15),
            note=(
                "Fallback SEC parcial para CAPEX: o conceito cobre outras "
                "aquisicoes de imobilizado e pode nao representar o investimento "
                "total."
            ),
            basis="derived",
            is_fallback=True,
        )


def _derive_change_in_nwc(
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
    assumptions: PointInTimeAssumptions,
) -> MetricValue:
    groups: list[tuple[str, float, tuple[MetricValue, ...], str]] = []

    def select(name: str, concepts: tuple[str, ...]) -> MetricValue:
        return _select_metric(
            payload,
            name,
            _FactSpec(concepts, ("USD",), True),
            anchor,
            source_url,
        )

    receivables = select(
        "nwc_receivables",
        (
            "IncreaseDecreaseInAccountsReceivable",
            "IncreaseDecreaseInReceivables",
        ),
    )
    if receivables.is_available:
        groups.append(
            ("receivables", float(receivables.value), (receivables,), "asset")
        )

    inventories = select(
        "nwc_inventories",
        ("IncreaseDecreaseInInventories",),
    )
    if inventories.is_available:
        groups.append(
            ("inventories", float(inventories.value), (inventories,), "asset")
        )

    contract_asset = select(
        "nwc_contract_asset",
        ("IncreaseDecreaseInContractWithCustomerAsset",),
    )
    if contract_asset.is_available:
        groups.append(
            (
                "contract_asset",
                float(contract_asset.value),
                (contract_asset,),
                "asset",
            )
        )

    payables = select(
        "nwc_payables_accrued",
        ("IncreaseDecreaseInAccountsPayableAndAccruedLiabilities",),
    )
    payable_metrics: tuple[MetricValue, ...] = ()
    payable_value: float | None = None
    if payables.is_available:
        payable_metrics = (payables,)
        payable_value = float(payables.value)
    else:
        accounts_payable = select(
            "nwc_accounts_payable",
            ("IncreaseDecreaseInAccountsPayable",),
        )
        accrued = select(
            "nwc_accrued_liabilities",
            (
                "IncreaseDecreaseInAccruedLiabilitiesAndOtherOperatingLiabilities",
                "IncreaseDecreaseInAccruedLiabilities",
            ),
        )
        payable_metrics = tuple(
            metric
            for metric in (accounts_payable, accrued)
            if metric.is_available
        )
        if payable_metrics:
            payable_value = sum(float(metric.value) for metric in payable_metrics)
    if payable_value is not None:
        groups.append(
            ("payables_accrued", -payable_value, payable_metrics, "liability")
        )

    reported_customer_liability = select(
        "nwc_customer_liability",
        (
            "IncreaseDecreaseInContractWithCustomerLiability",
            "IncreaseDecreaseInDeferredRevenue",
        ),
    )
    candidate_period_starts = {
        metric.period_start
        for _, _, group_metrics, _ in groups
        for metric in group_metrics
        if metric.period_start is not None
    }
    customer_liability = _derive_customer_liability_delta(
        payload,
        anchor,
        source_url,
        reported_customer_liability,
        assumptions,
        (
            reported_customer_liability.period_start
            if reported_customer_liability.period_start is not None
            else next(iter(candidate_period_starts))
            if len(candidate_period_starts) == 1
            else None
        ),
    )
    if customer_liability.is_available:
        groups.append(
            (
                "customer_liability",
                -float(customer_liability.value),
                (customer_liability,),
                "liability",
            )
        )

    other_net = select(
        "nwc_other_operating_capital_net",
        ("IncreaseDecreaseInOtherOperatingCapitalNet",),
    )
    if other_net.is_available:
        groups.append(
            (
                "other_operating_capital",
                float(other_net.value),
                (other_net,),
                "net",
            )
        )
    else:
        other_asset = select(
            "nwc_other_operating_assets",
            (
                "IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets",
                "IncreaseDecreaseInPrepaidExpense",
                "IncreaseDecreaseInOtherCurrentAssets",
            ),
        )
        other_liability = select(
            "nwc_other_operating_liabilities",
            (
                "IncreaseDecreaseInOtherOperatingLiabilities",
                "IncreaseDecreaseInOtherCurrentLiabilities",
            ),
        )
        other_metrics = tuple(
            metric
            for metric in (other_asset, other_liability)
            if metric.is_available
        )
        if other_metrics:
            value = (
                float(other_asset.value) if other_asset.is_available else 0.0
            ) - (
                float(other_liability.value)
                if other_liability.is_available
                else 0.0
            )
            side = (
                "net"
                if other_asset.is_available and other_liability.is_available
                else "asset"
                if other_asset.is_available
                else "liability"
            )
            groups.append(
                ("other_operating_capital", value, other_metrics, side)
            )

    sides = {side for _, _, _, side in groups}
    has_asset_side = "asset" in sides
    has_funding_side = bool({"liability", "net"}.intersection(sides))
    if (
        len(groups) < assumptions.minimum_nwc_component_groups
        or not has_asset_side
        or not has_funding_side
    ):
        return _unavailable_change_in_nwc(
            anchor,
            source_url,
            "Reconstrucao de NWC recusada: exige ao menos "
            f"{assumptions.minimum_nwc_component_groups} grupos, incluindo "
            "ativos operacionais e passivos ou capital operacional liquido; "
            f"grupos encontrados: {', '.join(name for name, *_ in groups) or 'nenhum'}.",
        )

    metrics = tuple(
        metric
        for _, _, group_metrics, _ in groups
        for metric in group_metrics
    )
    period_starts = {
        metric.period_start for metric in metrics if metric.period_start is not None
    }
    if len(period_starts) != 1:
        return _unavailable_change_in_nwc(
            anchor,
            source_url,
            "Reconstrucao de NWC recusada: componentes SEC usam janelas anuais "
            "inconsistentes.",
        )

    confidence_penalty = assumptions.nwc_component_reconstruction_confidence_penalty
    if len(groups) == assumptions.minimum_nwc_component_groups:
        confidence_penalty += assumptions.nwc_sparse_reconstruction_confidence_penalty
    confidence = max(
        0.0,
        min(metric.confidence for metric in metrics) - confidence_penalty,
    )
    value = sum(group_value for _, group_value, _, _ in groups)
    concepts = tuple(
        (metric.formula or "").rsplit(":", 1)[-1]
        for metric in metrics
    )
    uses_partial_customer_liability = any(
        group_name == "customer_liability"
        and (metric.formula or "").endswith("Current")
        for group_name, _, group_metrics, _ in groups
        for metric in group_metrics
    )
    coverage_note = (
        " Obrigacoes com clientes usam apenas o saldo corrente e recebem "
        "penalidade adicional de confianca."
        if uses_partial_customer_liability
        else ""
    )
    group_names = tuple(name for name, *_ in groups)
    observations = tuple(
        (f"{name}_economic_delta", group_value)
        for name, group_value, _, _ in groups
    ) + tuple(
        (f"{group_name}_{input_name}", input_value)
        for group_name, _, group_metrics, _ in groups
        for metric in group_metrics
        for input_name, input_value in metric.input_observations
    ) + (("change_in_nwc", value),)
    return metric_value(
        "change_in_nwc",
        value,
        "sec_edgar_derived",
        "Aumento economico do capital de giro operacional reconstruido por "
        "grupos operacionais SEC. Aumentos de ativos sao positivos; "
        "aumentos de passivos sao subtraidos. A reconstrucao permanece fallback "
        "porque conceitos customizados podem nao aparecer no Company Facts. "
        f"Grupos: {', '.join(group_names)}. Conceitos: {', '.join(concepts)}."
        f"{coverage_note}",
        source_url=source_url,
        source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
        period_start=next(iter(period_starts)),
        period_end=anchor.report_end,
        filing_date=anchor.filed,
        as_of=datetime.combine(anchor.filed, datetime.min.time()),
        currency="USD",
        scale="raw",
        basis="derived",
        is_fallback=True,
        formula="economic_delta_nwc_from_sec_operating_component_groups",
        confidence=confidence,
        input_observations=observations,
    )


def _derive_customer_liability_delta(
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
    reported_change: MetricValue,
    assumptions: PointInTimeAssumptions,
    period_start: date | None,
) -> MetricValue:
    if period_start is None:
        return reported_change

    opening_end = period_start - timedelta(days=1)
    concept_groups = (
        ("ContractWithCustomerLiability",),
        ("DeferredRevenue",),
        (
            "ContractWithCustomerLiabilityCurrent",
            "ContractWithCustomerLiabilityNoncurrent",
        ),
        ("DeferredRevenueCurrent", "DeferredRevenueNoncurrent"),
        ("ContractWithCustomerLiabilityCurrent",),
        ("DeferredRevenueCurrent",),
    )
    for concepts in concept_groups:
        closing = _select_instant_group(
            payload,
            "nwc_customer_liability_closing",
            concepts,
            anchor,
            anchor.report_end,
            source_url,
        )
        opening = _select_instant_group(
            payload,
            "nwc_customer_liability_opening",
            concepts,
            anchor,
            opening_end,
            source_url,
        )
        if not closing or not opening:
            continue
        closing_value = sum(float(metric.value) for metric in closing)
        opening_value = sum(float(metric.value) for metric in opening)
        concept_list = ", ".join(concepts)
        is_partial = len(concepts) == 1 and concepts[0].endswith("Current")
        confidence_penalty = (
            assumptions.nwc_partial_balance_confidence_penalty
            if is_partial
            else 0.0
        )
        coverage_note = (
            " O conceito cobre apenas o saldo corrente e recebe penalidade "
            "adicional de confianca."
            if is_partial
            else ""
        )
        return metric_value(
            "nwc_customer_liability",
            closing_value - opening_value,
            "sec_edgar_derived",
            "Variacao da obrigacao com clientes calculada pelos saldos "
            "comparativos do mesmo filing SEC. Esse saldo economico prevalece "
            "sobre a tag de fluxo, que pode representar movimentacao bruta. "
            f"Conceitos: {concept_list}.{coverage_note}",
            source_url=source_url,
            source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
            period_start=period_start,
            period_end=anchor.report_end,
            filing_date=anchor.filed,
            as_of=datetime.combine(anchor.filed, datetime.min.time()),
            currency="USD",
            scale="raw",
            basis="derived",
            is_fallback=True,
            formula=f"sec_balance_sheet_delta:{concept_list}",
            confidence=max(
                0.0,
                min(metric.confidence for metric in (*closing, *opening))
                - confidence_penalty,
            ),
            input_observations=(
                ("customer_liability_opening", opening_value),
                ("customer_liability_closing", closing_value),
            ),
        )
    return reported_change


def _select_instant_group(
    payload: Mapping[str, Any],
    name: str,
    concepts: tuple[str, ...],
    anchor: SecFilingAnchor,
    period_end: date,
    source_url: str,
) -> tuple[MetricValue, ...]:
    comparative_anchor = replace(anchor, report_end=period_end)
    selected = tuple(
        _select_metric(
            payload,
            f"{name}_{concept}",
            _FactSpec((concept,), ("USD",), False),
            comparative_anchor,
            source_url,
        )
        for concept in concepts
    )
    return selected if all(metric.is_available for metric in selected) else ()


def _unavailable_change_in_nwc(
    anchor: SecFilingAnchor,
    source_url: str,
    reason: str,
) -> MetricValue:
    return MetricValue(
        "change_in_nwc",
        None,
        "sec_edgar_derived",
        0.0,
        reason,
        source_url=source_url,
        source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
        period_end=anchor.report_end,
        filing_date=anchor.filed,
        as_of=datetime.combine(anchor.filed, datetime.min.time()),
        currency="USD",
        scale="raw",
        basis="derived",
        is_fallback=True,
        formula="economic_delta_nwc_from_sec_operating_component_groups",
    )


def _complete_balance_sheet(
    balance: dict[str, MetricValue],
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
) -> None:
    if "total_liabilities" in balance:
        return
    assets = balance.get("total_assets")
    equity = balance.get("equity")
    if assets is None or equity is None or not assets.is_available or not equity.is_available:
        return
    balance["total_liabilities"] = metric_value(
        "total_liabilities",
        float(assets.value) - float(equity.value),
        "sec_edgar_derived",
        "Total liabilities = total assets - stockholders equity",
        source_url=source_url,
        source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
        period_end=anchor.report_end,
        filing_date=anchor.filed,
        currency="USD",
        scale="raw",
        basis="derived",
        formula="assets_minus_equity",
    )


def _complete_shares(
    market_data: dict[str, MetricValue],
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
    assumptions: PointInTimeAssumptions,
) -> None:
    if "shares" in market_data:
        return
    fallback = _select_metric(
        payload,
        "shares",
        _FactSpec(
            ("CommonStockSharesOutstanding",),
            ("shares",),
            False,
            taxonomy="us-gaap",
            instant_window_days=120,
        ),
        anchor,
        source_url,
    )
    if fallback.is_available:
        market_data["shares"] = replace(
            fallback,
            confidence=max(0.0, fallback.confidence - 0.05),
            note="Fallback us-gaap para quantidade de acoes em circulacao.",
            is_fallback=True,
        )
        return
    weighted_average = _select_metric(
        payload,
        "shares",
        _FactSpec(
            (
                "WeightedAverageNumberOfDilutedSharesOutstanding",
                "WeightedAverageNumberOfSharesOutstandingBasic",
            ),
            ("shares",),
            True,
        ),
        anchor,
        source_url,
    )
    if weighted_average.is_available:
        market_data["shares"] = replace(
            weighted_average,
            confidence=assumptions.weighted_average_shares_fallback_confidence,
            note=(
                "Fallback para a media anual diluida de acoes porque o filing nao "
                "publicou uma quantidade instantanea consolidada."
            ),
            basis="derived",
            is_fallback=True,
        )


def _complete_ebit(
    income: dict[str, MetricValue],
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
) -> None:
    if "ebit" in income:
        return
    pretax_income = _select_metric(
        payload,
        "pretax_income",
        _FactSpec(
            (
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            ),
            ("USD",),
            True,
        ),
        anchor,
        source_url,
    )
    interest_expense = income.get("interest_expense")
    net_interest_proxy = False
    if interest_expense is None or not interest_expense.is_available:
        interest_expense = _select_metric(
            payload,
            "interest_expense",
            _FactSpec(
                (
                    "InterestIncomeExpenseNonoperatingNet",
                    "InterestIncomeExpenseNet",
                ),
                ("USD",),
                True,
            ),
            anchor,
            source_url,
        )
        net_interest_proxy = interest_expense.is_available
    if (
        not pretax_income.is_available
        or interest_expense is None
        or not interest_expense.is_available
    ):
        return
    income["ebit"] = metric_value(
        "ebit",
        float(pretax_income.value) + abs(float(interest_expense.value)),
        "sec_edgar_derived",
        "EBIT proxy = lucro antes dos impostos + despesa de juros; usado somente "
        "quando o EBIT reportado esta ausente"
        + (
            "; juros liquidos nao operacionais usados como aproximacao adicional"
            if net_interest_proxy
            else ""
        ),
        source_url=source_url,
        source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
        period_start=pretax_income.period_start,
        period_end=anchor.report_end,
        filing_date=anchor.filed,
        as_of=datetime.combine(anchor.filed, datetime.min.time()),
        currency="USD",
        scale="raw",
        basis="derived",
        is_fallback=True,
        formula="pretax_income_plus_abs_interest_expense",
        confidence=max(
            0.0,
            min(pretax_income.confidence, interest_expense.confidence)
            - (0.20 if net_interest_proxy else 0.10),
        ),
    )


def _complete_total_debt(
    balance: dict[str, MetricValue],
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
    assumptions: PointInTimeAssumptions,
) -> None:
    existing = balance.get("total_debt")
    complete_concepts = (
        "DebtCurrentAndNoncurrent",
        "LongTermDebtAndFinanceLeaseObligations",
        "LongTermDebtAndCapitalLeaseObligationsCurrentAndNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        "LongTermDebtAndCapitalLeaseObligations",
        "DebtAndCapitalLeaseObligations",
        "FinanceLeaseLiability",
    )
    if existing is not None and any(
        (existing.formula or "").endswith(concept) for concept in complete_concepts
    ):
        return
    short_term = _select_metric(
        payload,
        "short_term_borrowings",
        _FactSpec(("ShortTermBorrowings",), ("USD",), False),
        anchor,
        source_url,
    )
    if existing is not None and existing.is_available:
        components = [existing]
        if short_term.is_available:
            components.append(short_term)
    else:
        current = _select_metric(
            payload,
            "debt_current",
            _FactSpec(
                (
                    "LongTermDebtCurrent",
                    "DebtCurrent",
                    "ShortTermDebtCurrent",
                    "ConvertibleDebtCurrent",
                    "ConvertibleNotesPayableCurrent",
                    "CapitalLeaseObligationsCurrent",
                    "NotesPayableCurrent",
                    "FinanceLeaseLiabilityCurrent",
                ),
                ("USD",),
                False,
            ),
            anchor,
            source_url,
        )
        noncurrent = _select_metric(
            payload,
            "debt_noncurrent",
            _FactSpec(
                (
                    "LongTermDebtNoncurrent",
                    "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
                    "ConvertibleDebtNoncurrent",
                    "ConvertibleNotesPayableNoncurrent",
                    "ConvertibleLongTermNotesPayable",
                    "CapitalLeaseObligationsNoncurrent",
                    "LongTermNotesPayable",
                    "NotesPayableNoncurrent",
                    "FinanceLeaseLiabilityNoncurrent",
                ),
                ("USD",),
                False,
            ),
            anchor,
            source_url,
        )
        components = [
            metric for metric in (current, noncurrent, short_term) if metric.is_available
        ]
    if not components:
        financing_evidence = _anchor_financing_evidence(
            payload,
            anchor,
            source_url,
        )
        if financing_evidence:
            return
        operating_lease = _select_metric(
            payload,
            "operating_lease_liability",
            _FactSpec(
                ("OperatingLeaseLiability",),
                ("USD",),
                False,
            ),
            anchor,
            source_url,
        )
        lease_note = (
            " O filing reporta passivo de arrendamento operacional, que permanece "
            "fora da divida financeira porque o modelo ainda nao faz o ajuste "
            "simetrico de EBIT e FCFF exigido pela capitalizacao de leases."
            if operating_lease.is_available
            and abs(float(operating_lease.value)) > 0.0
            else ""
        )
        balance["total_debt"] = metric_value(
            "total_debt",
            0.0,
            "sec_edgar_derived",
            "Aproximacao conservadora de divida zero: o filing ancora nao apresenta "
            "conceito padronizado de divida nem despesa financeira positiva. Revisar "
            "manualmente notas de divida e arrendamentos antes de uma decisao."
            + lease_note,
            source_url=source_url,
            source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
            period_end=anchor.report_end,
            filing_date=anchor.filed,
            as_of=datetime.combine(anchor.filed, datetime.min.time()),
            currency="USD",
            scale="raw",
            basis="derived",
            is_fallback=True,
            formula="zero_debt_absence_of_anchor_financing_evidence",
            confidence=assumptions.zero_debt_fallback_confidence,
        )
        return
    balance["total_debt"] = metric_value(
        "total_debt",
        sum(float(metric.value) for metric in components),
        "sec_edgar_derived",
        "Soma auditavel dos componentes de divida encontrados no XBRL",
        source_url=source_url,
        source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
        period_end=anchor.report_end,
        filing_date=anchor.filed,
        currency="USD",
        scale="raw",
        basis="derived",
        formula="sum_available_debt_components",
        confidence=min(metric.confidence for metric in components),
    )


def _anchor_financing_evidence(
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
) -> tuple[str, ...]:
    debt = _select_metric(
        payload,
        "debt_evidence",
        _FactSpec(
            (
                "DebtInstrumentCarryingAmount",
                "NotesPayableCurrent",
                "NotesPayableNoncurrent",
                "ConvertibleNotesPayableCurrent",
                "ConvertibleNotesPayableNoncurrent",
            ),
            ("USD",),
            False,
        ),
        anchor,
        source_url,
    )
    interest = _select_metric(
        payload,
        "interest_evidence",
        _FactSpec(
            (
                "InterestExpenseNonOperating",
                "InterestExpenseNonoperating",
                "InterestAndDebtExpense",
                "InterestExpense",
                "InterestExpenseDebt",
                "InterestExpenseDebtExcludingAmortization",
            ),
            ("USD",),
            True,
        ),
        anchor,
        source_url,
    )
    evidence: list[str] = []
    if debt.is_available and abs(float(debt.value)) > 0.0:
        evidence.append(debt.formula or "debt_evidence")
    if interest.is_available and abs(float(interest.value)) > 0.0:
        evidence.append(interest.formula or "interest_evidence")
    return tuple(evidence)


def _derive_revenue_growth(
    payload: Mapping[str, Any],
    revenue: MetricValue,
    anchor: SecFilingAnchor,
    source_url: str,
    assumptions: PointInTimeAssumptions,
) -> MetricValue:
    formula = revenue.formula or ""
    concept = formula.rsplit(":", 1)[-1] if formula.startswith("sec_xbrl:") else ""
    if not concept:
        return MetricValue("revenue_growth", None, "missing", 0.0)
    facts = payload.get("facts", {})
    taxonomy = facts.get("us-gaap", {}) if isinstance(facts, Mapping) else {}
    concept_payload = taxonomy.get(concept, {}) if isinstance(taxonomy, Mapping) else {}
    units = concept_payload.get("units", {}) if isinstance(concept_payload, Mapping) else {}
    prior_candidates: list[Mapping[str, Any]] = []
    for fact in units.get("USD", []) if isinstance(units, Mapping) else []:
        if not isinstance(fact, Mapping):
            continue
        if str(fact.get("accn", "")) != anchor.accession_number:
            continue
        if str(fact.get("form", "")) != anchor.form:
            continue
        start = _parse_date(fact.get("start"))
        end = _parse_date(fact.get("end"))
        if start is None or end is None or end >= anchor.report_end:
            continue
        gap_days = (anchor.report_end - end).days
        if (
            250 <= (end - start).days <= 450
            and assumptions.minimum_annual_comparative_gap_days
            <= gap_days
            <= assumptions.maximum_annual_comparative_gap_days
        ):
            prior_candidates.append(fact)
    if not prior_candidates or revenue.value in (None, 0):
        return MetricValue("revenue_growth", None, "missing", 0.0, "prior annual revenue unavailable")
    prior = max(prior_candidates, key=lambda item: _parse_date(item.get("end")) or date.min)
    prior_value = safe_float(prior.get("val"))
    if prior_value in (None, 0):
        return MetricValue("revenue_growth", None, "missing", 0.0, "prior annual revenue unavailable")
    return metric_value(
        "revenue_growth",
        float(revenue.value) / float(prior_value) - 1.0,
        "sec_edgar_derived",
        "Receita anual do filing dividida pela receita comparativa no mesmo filing menos um",
        source_url=source_url,
        source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
        period_start=_parse_date(prior.get("end")),
        period_end=anchor.report_end,
        filing_date=anchor.filed,
        basis="derived",
        formula="annual_revenue_divided_by_comparative_revenue_minus_one",
        confidence=max(0.0, revenue.confidence - 0.05),
        input_observations=(
            ("current_revenue", float(revenue.value)),
            ("prior_revenue", float(prior_value)),
        ),
    )


def _derive_gross_margin(
    gross_profit: MetricValue,
    revenue: MetricValue,
) -> MetricValue:
    if not gross_profit.is_available or not revenue.is_available or revenue.value <= 0:
        return MetricValue(
            "gross_margin",
            None,
            "sec_edgar_derived",
            0.0,
            "Lucro bruto e receita positiva precisam estar no mesmo filing SEC.",
            period_end=revenue.period_end,
            filing_date=revenue.filing_date,
            scale="ratio",
            basis="derived",
            formula="annual_gross_profit_divided_by_annual_revenue",
        )
    return metric_value(
        "gross_margin",
        float(gross_profit.value) / float(revenue.value),
        "sec_edgar_derived",
        "Lucro bruto anual / receita anual do mesmo filing SEC.",
        source_url=revenue.source_url,
        source_document=revenue.source_document,
        period_start=revenue.period_start,
        period_end=revenue.period_end,
        filing_date=revenue.filing_date,
        as_of=revenue.as_of,
        scale="ratio",
        basis="derived",
        formula="annual_gross_profit_divided_by_annual_revenue",
        confidence=max(0.0, min(gross_profit.confidence, revenue.confidence) - 0.05),
        input_observations=(
            ("gross_profit", float(gross_profit.value)),
            ("revenue", float(revenue.value)),
        ),
    )


def _derive_fcff_growth(
    payload: Mapping[str, Any],
    current_income: Mapping[str, MetricValue],
    current_cash_flow: Mapping[str, MetricValue],
    anchor: SecFilingAnchor,
    source_url: str,
    assumptions: PointInTimeAssumptions,
) -> MetricValue:
    raw_current_fcff = _fcff_for_sections(
        anchor,
        current_income,
        current_cash_flow,
    )
    if not raw_current_fcff.is_available:
        return _unavailable_fcff_growth(
            anchor,
            source_url,
            "FCFF corrente indisponivel: "
            + (raw_current_fcff.note or "insumos ausentes"),
            current_fcff=raw_current_fcff,
        )

    current_fcff: MetricValue | None = None
    prior_fcff: MetricValue | None = None
    prior_end: date | None = None
    selected_current_cash_flow: Mapping[str, MetricValue] | None = None
    selected_prior_cash_flow: Mapping[str, MetricValue] | None = None
    nwc_pair_mode = ""
    prior_failure_notes: list[str] = []
    for candidate_end in _annual_comparative_period_ends(
        payload,
        anchor,
        assumptions,
    ):
        comparative_anchor = replace(anchor, report_end=candidate_end)
        prior_income, prior_cash_flow = _statement_sections_for_period(
            payload,
            comparative_anchor,
            source_url,
            assumptions,
        )
        aligned_current_cash_flow, aligned_prior_cash_flow, candidate_nwc_mode = (
            _align_nwc_pair(current_cash_flow, prior_cash_flow)
        )
        candidate_current_fcff = _fcff_for_sections(
            anchor,
            current_income,
            aligned_current_cash_flow,
        )
        candidate_fcff = _fcff_for_sections(
            comparative_anchor,
            prior_income,
            aligned_prior_cash_flow,
        )
        if candidate_current_fcff.is_available and candidate_fcff.is_available:
            current_fcff = candidate_current_fcff
            prior_fcff = candidate_fcff
            prior_end = candidate_end
            selected_current_cash_flow = aligned_current_cash_flow
            selected_prior_cash_flow = aligned_prior_cash_flow
            nwc_pair_mode = candidate_nwc_mode
            break
        prior_failure_notes.append(
            f"{candidate_end.isoformat()}: corrente="
            f"{candidate_current_fcff.note or 'insumos ausentes'}; comparativo="
            f"{candidate_fcff.note or 'insumos ausentes'}"
        )

    if current_fcff is None or prior_fcff is None or prior_end is None:
        detail = "; ".join(prior_failure_notes[:3])
        reason = "FCFF anual comparativo indisponivel no mesmo filing SEC."
        if detail:
            reason += " Tentativas: " + detail + "."
        return _unavailable_fcff_growth(
            anchor,
            source_url,
            reason,
            current_fcff=raw_current_fcff,
        )

    current_value = float(current_fcff.value)
    prior_value = float(prior_fcff.value)
    observations = (
        ("current_fcff", current_value),
        ("prior_fcff", prior_value),
    ) + _nwc_pair_observations(
        selected_current_cash_flow or {},
        selected_prior_cash_flow or {},
    )
    used_fallback = current_fcff.is_fallback or prior_fcff.is_fallback
    if current_value <= 0.0 or prior_value <= 0.0:
        reason = (
            "Crescimento percentual de FCFF recusado porque FCFF corrente e "
            "comparativo precisam ser positivos; uma mudanca de sinal nao e uma "
            "taxa de crescimento economicamente interpretavel. Tratamento NWC: "
            f"{nwc_pair_mode}."
        )
        return _unavailable_fcff_growth(
            anchor,
            source_url,
            reason,
            current_fcff=current_fcff,
            prior_fcff=prior_fcff,
            period_start=prior_end,
            input_observations=observations,
            is_fallback=used_fallback,
        )

    confidence = max(
        0.0,
        min(current_fcff.confidence, prior_fcff.confidence)
        - assumptions.fcff_growth_derivation_confidence_penalty,
    )
    note = (
        "FCFF corrente dividido pelo FCFF anual comparativo do mesmo filing SEC "
        "menos um. Ambos os FCFF usam a formula vigente do modelo. Tratamento "
        f"simetrico do capital de giro: {nwc_pair_mode}."
    )
    if used_fallback:
        note += " Pelo menos um FCFF usa fallback explicitamente identificado."
    return metric_value(
        "fcff_growth",
        current_value / prior_value - 1.0,
        "sec_edgar_derived",
        note,
        source_url=source_url,
        source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
        period_start=prior_end,
        period_end=anchor.report_end,
        filing_date=anchor.filed,
        as_of=datetime.combine(anchor.filed, datetime.min.time()),
        scale="ratio",
        basis="derived",
        is_fallback=used_fallback,
        formula="current_positive_fcff_divided_by_prior_positive_fcff_minus_one",
        confidence=confidence,
        input_observations=observations,
    )


def _statement_sections_for_period(
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    source_url: str,
    assumptions: PointInTimeAssumptions,
) -> tuple[dict[str, MetricValue], dict[str, MetricValue]]:
    income: dict[str, MetricValue] = {}
    cash_flow: dict[str, MetricValue] = {}
    for name, spec in SEC_FACT_SPECS["income_statement"].items():
        selected = _select_metric(payload, name, spec, anchor, source_url)
        if selected.is_available:
            income[name] = selected
    for name, spec in SEC_FACT_SPECS["cash_flow"].items():
        selected = _select_metric(payload, name, spec, anchor, source_url)
        if selected.is_available:
            cash_flow[name] = selected
    _complete_ebit(income, payload, anchor, source_url)
    _complete_depreciation_amortization(cash_flow, payload, anchor, source_url)
    _complete_capex(cash_flow, payload, anchor, source_url)
    cash_flow["change_in_nwc"] = _derive_change_in_nwc(
        payload,
        anchor,
        source_url,
        assumptions,
    )
    return income, cash_flow


def _align_nwc_pair(
    current_cash_flow: Mapping[str, MetricValue],
    prior_cash_flow: Mapping[str, MetricValue],
) -> tuple[dict[str, MetricValue], dict[str, MetricValue], str]:
    current = dict(current_cash_flow)
    prior = dict(prior_cash_flow)
    current_nwc = current.get("change_in_nwc")
    prior_nwc = prior.get("change_in_nwc")
    current_available = bool(current_nwc and current_nwc.is_available)
    prior_available = bool(prior_nwc and prior_nwc.is_available)
    if current_available and prior_available:
        return current, prior, "nwc_reconstruido_nos_dois_periodos"
    if not current_available and not prior_available:
        return current, prior, "fallback_zero_nos_dois_periodos"

    reason = (
        "Cobertura assimetrica de NWC entre os periodos; a aproximacao zero foi "
        "aplicada aos dois FCFF para preservar comparabilidade temporal."
    )
    current["change_in_nwc"] = MetricValue(
        "change_in_nwc",
        None,
        "sec_edgar_derived",
        0.0,
        reason,
        basis="derived",
        is_fallback=True,
        formula="symmetric_zero_nwc_for_fcff_growth",
    )
    prior["change_in_nwc"] = replace(
        current["change_in_nwc"],
        period_end=(prior_nwc.period_end if prior_nwc else None),
        filing_date=(prior_nwc.filing_date if prior_nwc else None),
    )
    return current, prior, "fallback_zero_simetrico_por_cobertura_assimetrica"


def _nwc_pair_observations(
    current_cash_flow: Mapping[str, MetricValue],
    prior_cash_flow: Mapping[str, MetricValue],
) -> tuple[tuple[str, float], ...]:
    observations: list[tuple[str, float]] = []
    for prefix, cash_flow in (
        ("current", current_cash_flow),
        ("prior", prior_cash_flow),
    ):
        nwc = cash_flow.get("change_in_nwc")
        if nwc is None or not nwc.is_available:
            observations.append((f"{prefix}_change_in_nwc_fallback_zero", 0.0))
            continue
        observations.append((f"{prefix}_change_in_nwc", float(nwc.value)))
        observations.extend(
            (f"{prefix}_nwc_{name}", value)
            for name, value in nwc.input_observations
            if name != "change_in_nwc"
        )
    return tuple(observations)


def _fcff_for_sections(
    anchor: SecFilingAnchor,
    income: Mapping[str, MetricValue],
    cash_flow: Mapping[str, MetricValue],
) -> MetricValue:
    statements = FinancialStatements(
        ticker=anchor.ticker,
        income_statement=income,
        cash_flow=cash_flow,
        source="sec_edgar",
    )
    return build_statement_metrics(statements).get("fcff")


def _annual_comparative_period_ends(
    payload: Mapping[str, Any],
    anchor: SecFilingAnchor,
    assumptions: PointInTimeAssumptions,
) -> tuple[date, ...]:
    eligible_facts = {
        (spec.taxonomy, concept, unit)
        for section in ("income_statement", "cash_flow")
        for spec in SEC_FACT_SPECS[section].values()
        for concept in spec.concepts
        for unit in spec.units
        if spec.duration
    }
    period_ends: set[date] = set()
    for taxonomy, concept, unit, fact in _iter_facts(payload):
        if (taxonomy, concept, unit) not in eligible_facts:
            continue
        if str(fact.get("accn", "")) != anchor.accession_number:
            continue
        if str(fact.get("form", "")) != anchor.form:
            continue
        start = _parse_date(fact.get("start"))
        end = _parse_date(fact.get("end"))
        if start is None or end is None or end >= anchor.report_end:
            continue
        gap_days = (anchor.report_end - end).days
        if (
            250 <= (end - start).days <= 450
            and assumptions.minimum_annual_comparative_gap_days
            <= gap_days
            <= assumptions.maximum_annual_comparative_gap_days
        ):
            period_ends.add(end)
    return tuple(sorted(period_ends, reverse=True))


def _unavailable_fcff_growth(
    anchor: SecFilingAnchor,
    source_url: str,
    reason: str,
    *,
    current_fcff: MetricValue | None = None,
    prior_fcff: MetricValue | None = None,
    period_start: date | None = None,
    input_observations: tuple[tuple[str, float], ...] = (),
    is_fallback: bool | None = None,
) -> MetricValue:
    fallback = (
        bool(is_fallback)
        if is_fallback is not None
        else bool(
            (current_fcff and current_fcff.is_fallback)
            or (prior_fcff and prior_fcff.is_fallback)
        )
    )
    return MetricValue(
        "fcff_growth",
        None,
        "sec_edgar_derived",
        0.0,
        reason,
        source_url=source_url,
        source_document=f"SEC EDGAR {anchor.form} {anchor.accession_number}",
        period_start=period_start,
        period_end=anchor.report_end,
        filing_date=anchor.filed,
        as_of=datetime.combine(anchor.filed, datetime.min.time()),
        scale="ratio",
        basis="derived",
        is_fallback=fallback,
        formula="current_positive_fcff_divided_by_prior_positive_fcff_minus_one",
        input_observations=input_observations,
    )


def _iter_facts(
    payload: Mapping[str, Any],
) -> Iterable[tuple[str, str, str, Mapping[str, Any]]]:
    facts = payload.get("facts", {})
    if not isinstance(facts, Mapping):
        return
    for taxonomy_name, taxonomy_payload in facts.items():
        if not isinstance(taxonomy_payload, Mapping):
            continue
        for concept_name, concept_payload in taxonomy_payload.items():
            if not isinstance(concept_payload, Mapping):
                continue
            units = concept_payload.get("units", {})
            if not isinstance(units, Mapping):
                continue
            for unit_name, entries in units.items():
                if not isinstance(entries, list):
                    continue
                for fact in entries:
                    if isinstance(fact, Mapping):
                        yield str(taxonomy_name), str(concept_name), str(unit_name), fact


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
