#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Isolated historical MOPS backfill with cross-query reconciliation and coverage audit.
No changes to live reports or Telegram delivery.
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_self_reports as src

# Known 2026 exchange holidays in the requested historical window. This is a
# diagnostic calendar, NOT a reason to skip MOPS announcements on holidays.
KNOWN_CLOSED = {
    '2026-09-25': '中秋節',
    '2026-09-28': '教師節補假',
}


def row_signature(row):
    """Stable within-day row signature across MOPS query layouts and mirrors."""
    raw = src.compact_text(row.get('text', ''))
    attrs = ' '.join(str(a) for a in row.get('attrs', []))
    # Use announcement id where possible; never collapse two distinct filings
    # solely because they share a company and publication date.
    match = re.search(r'(?:seq_no|SEQ_NO)[^\d]{0,20}(\d+)', attrs)
    ticker = re.search(r'(?<!\d)\d{4}(?!\d)', raw)
    if match and ticker:
        return ('seq', ticker.group(0), match.group(1), raw[:100])
    return ('text', raw)


def event_key(item):
    return (str(item.get('publish_date', '')), str(item.get('ticker', '')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2026-07-01')
    ap.add_argument('--end', default='2026-09-28')
    ap.add_argument('--out', default='self_report_historical')
    args = ap.parse_args()
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    if end < start or (end - start).days > 120:
        ap.error('invalid date range (maximum 120 days)')
    src.MONITOR_START_DATE = args.start
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    existing = json.loads((ROOT / 'data/self_reports_history.json').read_text(encoding='utf-8-sig'))
    merged = {src.identity(x): x for x in existing.get('items', [])}
    coverage, duplicates, parse_failures = [], [], []
    day = start
    while day <= end:
        iso = day.isoformat()
        closed_reason = '週末' if day.weekday() >= 5 else KNOWN_CLOSED.get(iso, '')
        # Query closed days too: exchange holidays do not guarantee MOPS silence.
        # Each query form and host is inspected; no early stop at first nonempty response.
        queries = src.query_payloads(iso, '')
        rows_by_signature = {}
        diagnostics, successful_queries, query_counts = [], 0, []
        for base in reversed(src.MOPS_BASES):
            for idx, payload in enumerate(queries):
                try:
                    rows = src.parse_rows(src.fetch_mops(base, payload))
                    successful_queries += 1
                    query_counts.append(len(rows))
                    diagnostics.append({'host': base, 'layout': idx + 1, 'rows': len(rows), 'ok': True})
                    for row in rows:
                        rows_by_signature.setdefault(row_signature(row), row)
                except Exception as exc:
                    diagnostics.append({'host': base, 'layout': idx + 1, 'ok': False, 'error': repr(exc)})
        candidates = [r for r in rows_by_signature.values() if src.subject_is_candidate(r.get('text', ''))]
        new = 0
        parsed = 0
        for row in candidates:
            try:
                item = src.parse_candidate_row(row, 'daily_broad')
            except Exception as exc:
                parse_failures.append({'date': iso, 'subject': row.get('text', '')[:250], 'error': repr(exc)})
                continue
            if not item or item.get('publish_date') != iso:
                continue
            parsed += 1
            key = src.identity(item)
            if key not in merged:
                merged[key] = item
                new += 1
        coverage.append({
            'date': iso, 'closed_reason': closed_reason, 'query_ok': successful_queries > 0,
            'query_attempts': len(diagnostics), 'successful_queries': successful_queries,
            'query_row_counts': query_counts, 'raw_unique_rows': len(rows_by_signature),
            'candidate_rows': len(candidates), 'parsed_candidates': parsed,
            'new_records': new, 'diagnostics': diagnostics,
        })
        print(iso, 'CLOSED' if closed_reason else 'OPEN', 'queries', successful_queries,
              'unique_rows', len(rows_by_signature), 'candidates', len(candidates),
              'parsed', parsed, 'new', new, flush=True)
        day += dt.timedelta(days=1)

    items = sorted(merged.values(), key=lambda x: (x.get('publish_date', ''), x.get('ticker', ''), x.get('publish_time', '')))
    grouped = defaultdict(list)
    for item in items:
        if args.start <= str(item.get('publish_date', '')) <= args.end:
            grouped[event_key(item)].append(item)
    for (date, ticker), records in sorted(grouped.items()):
        if len(records) > 1:
            duplicates.append({'date': date, 'ticker': ticker, 'filing_count': len(records),
                               'filings': [{'time': x.get('publish_time'), 'subject': x.get('subject'),
                                           'source': x.get('source')} for x in records]})

    failed = [x['date'] for x in coverage if not x['query_ok']]
    # Low counts on CLOSED days are normal. Open-day low counts need review.
    suspicious = [x['date'] for x in coverage if x['query_ok'] and not x['closed_reason'] and x['raw_unique_rows'] < 30]
    disagreements = [x['date'] for x in coverage if len(x['query_row_counts']) >= 2
                     and max(x['query_row_counts']) >= 30 and min(x['query_row_counts']) < max(x['query_row_counts']) * .5]
    # Unparsed candidates should be audited, not silently treated as negatives.
    unparsed = [x['date'] for x in coverage if x['candidate_rows'] > x['parsed_candidates']]
    (out / 'self_reports_history.json').write_text(json.dumps({
        'items': items, 'monitor_start_date': args.start, 'source': 'isolated_historical_backfill',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'duplicate_filing_audit.json').write_text(json.dumps(duplicates, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'parse_failures.json').write_text(json.dumps(parse_failures, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'coverage_warnings.json').write_text(json.dumps({
        'failed_days': failed, 'low_row_open_days': suspicious,
        'cross_query_count_disagreements': disagreements,
        'unparsed_candidate_days': unparsed,
        'closed_days': [{'date': x['date'], 'reason': x['closed_reason']} for x in coverage if x['closed_reason']],
        'duplicate_ticker_date_events': len(duplicates),
        'note': 'Raw filings retained; prediction labels must count unique ticker/date. Closed days queried but excluded from low-volume warnings. Query success does not prove completeness.',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SUMMARY', json.dumps({'total_records': len(items), 'unique_ticker_date_events': len(grouped),
                                  'duplicate_groups': len(duplicates), 'failed_days': failed,
                                  'suspicious_open_days': suspicious, 'parse_failures': len(parse_failures)}, ensure_ascii=False), flush=True)
    if failed:
        print('ERROR: historical query failed on', failed, flush=True)
        sys.exit(2)


if __name__ == '__main__':
    main()
