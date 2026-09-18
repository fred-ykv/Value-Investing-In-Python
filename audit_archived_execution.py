"""Audit archived price execution rules offline, without changing scores."""
import argparse
from dataclasses import asdict
from datetime import date, timedelta
import json
from pathlib import Path
import sys

from replay_historical_dataset import OfflineGuard


def audit(path):
    from fundamental_analysis.benchmark_universe import HistoricalLifecycleEvent
    from fundamental_analysis.config import POINT_IN_TIME
    from fundamental_analysis.historical_archive import ArchiveReader, ReplayPriceClient
    from fundamental_analysis.historical_prices import add_months, calculate_price_outcome
    reader = ArchiveReader(path)
    provider = ReplayPriceClient(reader)
    cases = {c['ticker']: c for c in reader.manifest['run']['cases']}
    records = json.loads(reader.load('expected_output', 'collection_manifest.json'))['results']
    rows = []
    for record in records:
        obs = record.get('observation')
        if not obs:
            rows.append({'ticker': record['ticker'], 'error': 'observacao ausente'})
            continue
        ticker, as_of = obs['ticker'], date.fromisoformat(obs['as_of'])
        case = cases[ticker]
        event = case.get('lifecycle_event')
        if event:
            event = dict(event)
            event['effective_date'] = date.fromisoformat(event['effective_date'])
            event = HistoricalLifecycleEvent(**event)
        row = {'ticker': ticker, 'as_of': str(as_of)}
        rows.append(row)
        try:
            benchmark = POINT_IN_TIME.benchmark_for_group(case['benchmark_group'])
            result = calculate_price_outcome(ticker, benchmark, as_of, provider,
                lifecycle_event=event, expected_cik=case.get('cik') or None)
            start = add_months(as_of, -POINT_IN_TIME.beta_lookback_months) - timedelta(days=10)
            end = add_months(as_of, 12) + timedelta(days=POINT_IN_TIME.price_end_max_lag_days + 2)
            stock = provider.fetch_series(ticker, start, end)
            reference = provider.fetch_series(benchmark, start, end)
            stop = result.stock_terminal_date or result.price_end_date
            stock_days = {p.day for p in stock.points if result.price_start_date <= p.day <= stop}
            reference_days = {p.day for p in reference.points if result.price_start_date <= p.day <= stop}
            row.update({'price_rules_passed': True,
                'missing_vs_benchmark_sessions': sorted(str(d) for d in reference_days - stock_days),
                'session_reference': 'benchmark series; not an independent exchange calendar',
                'volume_missing_sessions': sum(p.volume is None for p in stock.points if p.day in stock_days),
                'entry_on_signal_date': result.price_start_date == as_of,
                'outcome_method': result.outcome_method,
                'terminal_event': asdict(event) if event else None,
                'saved_return_matches': abs(result.forward_return - obs['forward_return']) < 1e-10,
                'price_eligibility_audit': result.price_eligibility_audit})
        except (ValueError, LookupError, KeyError, TypeError) as exc:
            row['error'] = str(exc)
    return {'archive_sha256': reader.digest, 'rows': rows, 'benchmark_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archives', nargs='+')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    guard = OfflineGuard()
    sys.addaudithook(guard)
    results = [audit(path) for path in args.archives]
    report = {'archives': results, 'network_attempts': guard.attempts, 'benchmark_authorized': False}
    with Path(args.output).open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
    for result in results:
        rows = result['rows']
        print(json.dumps({'observations': len(rows), 'price_rules_passed': sum(r.get('price_rules_passed', False) for r in rows),
            'rows_missing_sessions': sum(bool(r.get('missing_vs_benchmark_sessions')) for r in rows),
            'entry_on_signal_date': sum(r.get('entry_on_signal_date', False) for r in rows),
            'rows_without_full_volume': sum(bool(r.get('volume_missing_sessions')) for r in rows),
            'return_mismatches': sum(r.get('saved_return_matches') is False for r in rows),
            'errors': [r for r in rows if 'error' in r][:3]}))
    return 2 if guard.attempts or any('error' in row for result in results for row in result['rows']) else 0


if __name__ == '__main__':
    raise SystemExit(main())

