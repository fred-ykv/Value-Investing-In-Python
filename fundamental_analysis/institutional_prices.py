"""Auditable adapters for historical prices that include delisted securities."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .benchmark_universe import HISTORICAL_LIFECYCLE_CASES
from .config import POINT_IN_TIME, PointInTimeAssumptions
from .historical_prices import PricePoint, PriceSeries, normalize_price_series


JsonGetter = Callable[[str], object]


@dataclass(frozen=True)
class TiingoSecurityMapping:
    canonical_ticker: str
    provider_ticker: str
    issuer_cik: str
    expected_name: str
    expected_first_price_date: date
    expected_last_price_date: date

    @property
    def security_id(self) -> str:
        return (
            f"TIINGO:{self.provider_ticker}:"
            f"{self.expected_first_price_date.isoformat()}:CIK{self.issuer_cik}"
        )


TIINGO_LIFECYCLE_MAPPINGS: tuple[TiingoSecurityMapping, ...] = (
    TiingoSecurityMapping(
        "MDLA", "MDLA", "0001540184", "Medallia",
        date(2019, 7, 19), date(2021, 10, 29),
    ),
    TiingoSecurityMapping(
        "CLDR", "CLDR", "0001535379", "Cloudera",
        date(2017, 4, 28), date(2021, 10, 11),
    ),
    TiingoSecurityMapping(
        "CSPR", "CSPR", "0001598674", "Casper Sleep",
        date(2020, 2, 6), date(2022, 1, 24),
    ),
    TiingoSecurityMapping(
        "PLAN", "PLAN", "0001540755", "Anaplan",
        date(2018, 10, 12), date(2022, 6, 22),
    ),
    TiingoSecurityMapping(
        "ZEN", "ZEN", "0001463172", "Zendesk",
        date(2014, 5, 15), date(2022, 11, 21),
    ),
    TiingoSecurityMapping(
        "COUP", "COUP", "0001385867", "Coupa Software",
        date(2016, 10, 6), date(2023, 2, 28),
    ),
    TiingoSecurityMapping(
        "MNTV", "MNTV", "0001739936", "Momentive Global",
        date(2018, 9, 26), date(2023, 5, 31),
    ),
    TiingoSecurityMapping(
        "XM", "XM", "0001747748", "Qualtrics",
        date(2021, 1, 28), date(2023, 6, 28),
    ),
    TiingoSecurityMapping(
        "BBBY", "BBBYQ", "0000886158", "Bed Bath",
        date(1992, 6, 5), date(2023, 9, 29),
    ),
    TiingoSecurityMapping(
        "NEWR", "NEWR", "0001448056", "New Relic",
        date(2014, 12, 12), date(2023, 11, 7),
    ),
)


def validate_tiingo_mappings(
    mappings: Sequence[TiingoSecurityMapping] = TIINGO_LIFECYCLE_MAPPINGS,
) -> None:
    by_ticker = {item.canonical_ticker: item for item in mappings}
    expected = {case.ticker: case for case in HISTORICAL_LIFECYCLE_CASES}
    if set(by_ticker) != set(expected):
        missing = sorted(set(expected) - set(by_ticker))
        extra = sorted(set(by_ticker) - set(expected))
        raise ValueError(
            f"Mapa Tiingo incompleto; ausentes={missing}; excedentes={extra}"
        )
    if len(by_ticker) != len(mappings):
        raise ValueError("Mapa Tiingo contem ticker canonico duplicado")
    for ticker, mapping in by_ticker.items():
        case = expected[ticker]
        if mapping.issuer_cik != case.cik:
            raise ValueError(f"CIK Tiingo diverge do registro SEC para {ticker}")
        if not mapping.provider_ticker or not mapping.expected_name:
            raise ValueError(f"Identidade Tiingo incompleta para {ticker}")
        if mapping.expected_first_price_date >= mapping.expected_last_price_date:
            raise ValueError(f"Janela Tiingo invalida para {ticker}")


class TiingoHistoricalPriceClient:
    """Fetch raw and total-return-adjusted EOD prices with identity controls."""

    def __init__(
        self,
        api_token: str | None = None,
        *,
        mappings: Sequence[TiingoSecurityMapping] = TIINGO_LIFECYCLE_MAPPINGS,
        assumptions: PointInTimeAssumptions = POINT_IN_TIME,
        json_getter: JsonGetter | None = None,
    ):
        validate_tiingo_mappings(mappings)
        self.assumptions = assumptions
        self.api_token = (
            api_token
            or os.environ.get(assumptions.tiingo_api_key_env, "")
        ).strip()
        if json_getter is None and not self.api_token:
            raise ValueError(
                f"Defina {assumptions.tiingo_api_key_env} para acessar o Tiingo"
            )
        self.json_getter = json_getter
        self.mappings = {
            item.canonical_ticker.upper(): item for item in mappings
        }
        self._cache: dict[str, PriceSeries] = {}

    def fetch_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        canonical = ticker.upper().strip()
        mapping = self.mappings.get(canonical)
        if mapping is None:
            raise LookupError(f"Ticker {canonical} nao pertence ao mapa Tiingo auditado")
        if canonical not in self._cache:
            self._cache[canonical] = self._fetch_complete_series(mapping)
        return self._cache[canonical].between(start, end)

    def _fetch_complete_series(
        self,
        mapping: TiingoSecurityMapping,
    ) -> PriceSeries:
        provider_ticker = quote(mapping.provider_ticker, safe="-")
        metadata_url = (
            f"{self.assumptions.tiingo_base_url}/{provider_ticker}"
        )
        metadata = self._get_json(metadata_url)
        if not isinstance(metadata, Mapping):
            raise LookupError(
                f"Metadados Tiingo invalidos para {mapping.canonical_ticker}"
            )
        self._validate_metadata(mapping, metadata)

        query = urlencode(
            {
                "startDate": mapping.expected_first_price_date.isoformat(),
                "endDate": mapping.expected_last_price_date.isoformat(),
            }
        )
        prices_url = f"{metadata_url}/prices?{query}"
        payload = self._get_json(prices_url)
        if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
            raise LookupError(
                f"Precos Tiingo invalidos para {mapping.canonical_ticker}"
            )
        points: list[PricePoint] = []
        seen_days: set[date] = set()
        for row_number, raw_row in enumerate(payload, start=1):
            if not isinstance(raw_row, Mapping):
                raise ValueError(
                    f"Linha Tiingo {row_number} invalida para "
                    f"{mapping.canonical_ticker}"
                )
            try:
                day = date.fromisoformat(str(raw_row["date"])[:10])
                adjusted_close = float(raw_row["adjClose"])
                raw_close = float(raw_row["close"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Preco Tiingo invalido para {mapping.canonical_ticker} "
                    f"na linha {row_number}: {exc}"
                ) from exc
            if (
                not math.isfinite(adjusted_close)
                or adjusted_close <= 0
                or not math.isfinite(raw_close)
                or raw_close <= 0
            ):
                raise ValueError(
                    f"Preco Tiingo nao positivo para {mapping.canonical_ticker} "
                    f"em {day}"
                )
            if day in seen_days:
                raise ValueError(
                    f"Preco Tiingo duplicado para {mapping.canonical_ticker} "
                    f"em {day}"
                )
            seen_days.add(day)
            points.append(PricePoint(day, adjusted_close, raw_close))
        if not points:
            raise LookupError(f"Serie Tiingo vazia para {mapping.canonical_ticker}")
        series = normalize_price_series(
            PriceSeries(
                mapping.canonical_ticker,
                tuple(points),
                (
                    f"tiingo_eod:{mapping.provider_ticker};"
                    f"metadata={metadata_url}"
                ),
                mapping.security_id,
                mapping.issuer_cik,
            )
        )
        first_day = series.points[0].day
        last_day = series.points[-1].day
        if first_day != mapping.expected_first_price_date:
            raise LookupError(
                f"Primeiro preco Tiingo de {mapping.canonical_ticker} e "
                f"{first_day}; esperado {mapping.expected_first_price_date}"
            )
        if last_day != mapping.expected_last_price_date:
            raise LookupError(
                f"Ultimo preco Tiingo de {mapping.canonical_ticker} e "
                f"{last_day}; esperado {mapping.expected_last_price_date}"
            )
        return series

    def _validate_metadata(
        self,
        mapping: TiingoSecurityMapping,
        metadata: Mapping[str, Any],
    ) -> None:
        provider_ticker = str(metadata.get("ticker") or "").upper().strip()
        name = str(metadata.get("name") or "").strip()
        try:
            start_date = date.fromisoformat(str(metadata["startDate"])[:10])
            end_date = date.fromisoformat(str(metadata["endDate"])[:10])
        except (KeyError, TypeError, ValueError) as exc:
            raise LookupError(
                f"Datas de cobertura Tiingo invalidas para "
                f"{mapping.canonical_ticker}"
            ) from exc
        if provider_ticker != mapping.provider_ticker:
            raise LookupError(
                f"Ticker Tiingo {provider_ticker or 'ausente'} diverge de "
                f"{mapping.provider_ticker}"
            )
        if mapping.expected_name.casefold() not in name.casefold():
            raise LookupError(
                f"Emissor Tiingo '{name or 'ausente'}' diverge do esperado "
                f"para {mapping.canonical_ticker}"
            )
        if start_date != mapping.expected_first_price_date:
            raise LookupError(
                f"Inicio Tiingo de {mapping.canonical_ticker} e {start_date}; "
                f"esperado {mapping.expected_first_price_date}"
            )
        if end_date != mapping.expected_last_price_date:
            raise LookupError(
                f"Fim Tiingo de {mapping.canonical_ticker} e {end_date}; "
                f"esperado {mapping.expected_last_price_date}"
            )

    def _get_json(self, url: str) -> object:
        if self.json_getter is not None:
            return self.json_getter(url)
        request = Request(
            url,
            headers={
                "Authorization": f"Token {self.api_token}",
                "User-Agent": self.assumptions.macro_http_user_agent,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(
                request,
                timeout=self.assumptions.request_timeout_seconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(
                f"Tiingo respondeu HTTP {exc.code}; verifique chave e plano"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Falha de rede ao acessar Tiingo: {exc.reason}") from exc


validate_tiingo_mappings()
