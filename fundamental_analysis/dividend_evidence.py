"""Collect dividend date evidence; matching is not cash-flow certification."""
from collections import defaultdict
from datetime import date
import json
import os
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .historical_archive import ArchiveReader
from .market_supplement import _write_archive


class TiingoDividendClient:
    def __init__(self, token=None, getter=None):
        self.token = token or os.environ.get("TIINGO_API_KEY", "")
        self.getter = getter
        if getter is None and not self.token:
            raise ValueError("TIINGO_API_KEY ausente; configure-a como segredo no ambiente")

    def fetch(self, ticker, start, end):
        query = urlencode({"startExDate": start, "endExDate": end})
        url = f"https://api.tiingo.com/tiingo/corporate-actions/{quote(ticker, safe='')}/distributions?{query}"
        if self.getter:
            return url, self.getter(url)
        request = Request(url, headers={"Authorization": f"Token {self.token}", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                return url, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Tiingo HTTP {exc.code}; acesso nao confirmado") from None
        except URLError:
            raise RuntimeError("Tiingo indisponivel por falha de rede") from None


def _day(value):
    if not isinstance(value, str):
        raise ValueError("data ausente")
    return date.fromisoformat(value[:10])


def reconcile_dates(ticker, expected, response):
    if not isinstance(response, list):
        raise ValueError("resposta de dividendos nao e uma lista")
    index = defaultdict(list)
    for row in response:
        if not isinstance(row, dict):
            raise ValueError("linha de dividendo invalida")
        if str(row.get("ticker", "")).upper() != ticker:
            raise ValueError("ticker da resposta diverge da consulta")
        index[_day(row.get("exDate"))].append(row)
    results = []
    for item in expected:
        ex_date = _day(item["ex_date"])
        matches = index[ex_date]
        result = {"ticker": ticker, "ex_date": ex_date.isoformat(),
                  "yahoo_value": item["value"], "cash_flow_approved": False}
        if len(matches) != 1:
            result.update(status="missing" if not matches else "ambiguous")
        else:
            row = matches[0]
            result.update(provider_distribution=row.get("distribution"), perma_ticker=row.get("permaTicker"))
            try:
                payment, declaration = _day(row.get("paymentDate")), _day(row.get("declarationDate"))
                if payment < ex_date or declaration > ex_date:
                    raise ValueError("cronologia exige revisao")
                result.update(status="dates_matched", payment_date=payment.isoformat(),
                              declaration_date=declaration.isoformat(),
                              pending="confirmar identidade, moeda, base por acao e tipo de distribuicao")
            except ValueError:
                result.update(status="dates_missing_or_special_event")
        results.append(result)
    return results


def collect_dividend_evidence(source_archive, output, client=None):
    output = Path(output)
    if output.exists():
        raise ValueError("diretorio de saida ja existe")
    archive = ArchiveReader(source_archive)
    report = archive.load("market_evidence_report", "report")
    grouped, seen = defaultdict(list), set()
    for item in report["unresolved_dividends"]:
        ticker, day = item["ticker"].upper(), _day(item["ex_date"]).isoformat()
        if (ticker, day) in seen:
            raise ValueError("dividendo esperado duplicado")
        seen.add((ticker, day))
        grouped[ticker].append(item)
    client = client or TiingoDividendClient()
    entries, results, errors = [], [], []
    for ticker, expected in sorted(grouped.items()):
        days = sorted(item["ex_date"] for item in expected)
        try:
            url, response = client.fetch(ticker, days[0], days[-1])
            entries.append(("dividend_provider_response", ticker, {"url": url, "response": response}))
            results.extend(reconcile_dates(ticker, expected, response))
        except (RuntimeError, ValueError, TypeError, KeyError):
            errors.append({"ticker": ticker, "reason": "consulta ou resposta rejeitada; acesso/cobertura pendente"})
    summary = {"source_archive_sha256": archive.digest, "expected_dividends": len(seen),
               "dates_matched": sum(row["status"] == "dates_matched" for row in results),
               "errors": errors, "results": results, "benchmark_authorized": False,
               "corporate_event_coverage_written": False}
    entries.append(("dividend_evidence_report", "report", summary))
    _write_archive(output, entries, {key: value for key, value in summary.items() if key != "results"})
    return summary

