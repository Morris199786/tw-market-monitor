#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Historical MOPS self-report discovery. No Telegram, no changes to live data."""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_self_reports as src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2026-09-01')
    ap.add_argument('--end', default='2026-09-28')
    ap.add_argument('--out', default='self_report_historical')
    args = ap.parse_args()
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    if end < start or (end - start).days > 90:
        ap.error('invalid date range (maximum 90 days)')
    src.MONITOR_START_DATE = args.start
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    existing = json.loads((ROOT / 'data/self_reports_history.json').read_text(encoding='utf-8-sig'))
    merged = {src.identity(x): x for x in existing.get('items', [])}
    coverage = []
    day = start
    while day <= end:
        iso = day.isoformat()
        if day.weekday() >= 5:
            coverage.append({'date': iso, 'query_ok': True, 'skipped': 'weekend', 'raw_rows': 0, 'new_events': 0})
            day += dt.timedelta(days=1)
            continue
        # Daily broad query, with two alternative MOPS form layouts.
        payloads = src.query_payloads(iso, '')[:2]
        raw, diagnostics, success = [], [], False
        for base in reversed(src.MOPS_BASES):
            for payload in payloads:
                try:
                    rows = src.parse_rows(src.fetch_mops(base, payload))
                    diagnostics.append({'base': base, 'rows': len(rows)})
                    if rows:
                        raw = rows
                        success = True
                        break
                except Exception as exc:
                    diagnostics.append({'base': base, 'error': repr(exc)})
            if success:
                break
        found = 0
        for row in raw:
            if not src.subject_is_candidate(row.get('text', '')):
                continue
            try:
                item = src.parse_candidate_row(row, 'daily_broad')
            except Exception as exc:
                diagnostics.append({'parse_error': repr(exc)})
                continue
            if not item or item.get('publish_date') != iso:
                continue
            key = src.identity(item)
            if key not in merged:
                merged[key] = item
                found += 1
        coverage.append({'date': iso, 'query_ok': success, 'raw_rows': len(raw), 'new_events': found, 'diagnostics': diagnostics})
        print(iso, 'OK' if success else 'FAILED', 'rows', len(raw), 'new', found, flush=True)
        day += dt.timedelta(days=1)
    items = sorted(merged.values(), key=lambda x: (x.get('publish_date',''), x.get('ticker',''), x.get('publish_time','')))
    (out / 'self_reports_history.json').write_text(json.dumps({'items': items, 'monitor_start_date': args.start, 'source': 'isolated_historical_backfill'}, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding='utf-8')
    failed = [x['date'] for x in coverage if not x['query_ok']]
    if failed:
        print('INCOMPLETE historical coverage:', failed)
        sys.exit(2)
    print('Historical MOPS days queried:', len(coverage), 'total records:', len(items))


if __name__ == '__main__':
    main()
