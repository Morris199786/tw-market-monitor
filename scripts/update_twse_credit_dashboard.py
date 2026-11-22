#!/usr/bin/env python3
"""TWSE official credit dashboard, date-scoped JSON ingestion.

Historical source verified on 2026-11-22:
  https://www.twse.com.tw/rwd/zh/marginTrading/BFIJ3U?response=json&date=YYYYMMDD

Always verify response date equals requested date. Never synthesize missing history.
Money values are raw TWD in BFIJ3U and stored as TWD 100 million (億元).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API = 'https://www.twse.com.tw/rwd/zh/marginTrading/BFIJ3U'
DASHBOARD = 'https://www.twse.com.tw/dashboard/zh/credit/margin.html'
DEST = Path(__file__).resolve().parents[1] / 'data/twse_credit_dashboard.json'
MARKET = DEST.parent / 'market_monitor.json'
START = dt.date(2026, 9, 23)
TZ = ZoneInfo('Asia/Taipei')
FIELDS = ('maintenance_ratio', 'call_accounts', 'call_amount',
          'disposal_accounts', 'disposal_amount', 'credit_accounts',
          'credit_account_ratio')
COUNT_KEYS = ('call_accounts', 'disposal_accounts', 'credit_accounts')


def parse_number(value, key):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{key}: missing or invalid numeric value {value!r}')
    return value


def validate(row):
    if not isinstance(row, dict) or not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', str(row.get('date', ''))):
        raise ValueError('invalid row date')
    for key in FIELDS:
        parse_number(row.get(key), key)
    if not 100 <= row['maintenance_ratio'] <= 500:
        raise ValueError('implausible maintenance ratio')
    if not 0 <= row['credit_account_ratio'] <= 100:
        raise ValueError('invalid credit account ratio')
    for key in COUNT_KEYS:
        if type(row[key]) is not int:
            raise ValueError(f'{key}: account count must be an integer')
    return row


def from_official(payload, requested):
    if not isinstance(payload, dict) or str(payload.get('stat', '')).upper() != 'OK':
        raise ValueError('official API did not return an OK record')
    date = str(payload.get('date', ''))
    if date != requested.strftime('%Y%m%d'):
        raise ValueError(f'official API date mismatch: wanted {requested:%Y%m%d}, got {date!r}')

    def val(field):
        return parse_number(payload.get(field), field)

    # TWSE definitions: belowAccNum = accounts with maintenance below 130%,
    # callAccNum = accounts issued a margin-call notice (DIFFERENT statistic).
    # The dashboard's below-130% metric is displayed in call_accounts.
    # Both metrics are kept distinctly to avoid silently equating them.
    for extra in ('callAccNum', 'crdAmt'):
        val(extra)
    row = {
        'date': requested.isoformat(),
        'maintenance_ratio': float(val('keepRate')),
        'call_accounts': int(val('belowAccNum')),
        'call_amount': round(val('callAmt') / 100_000_000, 6),
        'disposal_accounts': int(val('exeAccNum')),
        'disposal_amount': round(val('exeAmt') / 100_000_000, 6),
        'credit_accounts': int(val('marginAccNum')),
        'credit_account_ratio': float(val('marginAccRate')),
        'notified_call_accounts': int(val('callAccNum')),
    }
    for official_key, normalized_key in (
        ('belowAccNum','call_accounts'), ('exeAccNum','disposal_accounts'),
        ('marginAccNum','credit_accounts'), ('callAccNum','notified_call_accounts')
    ):
        if not float(payload[official_key]).is_integer():
            raise ValueError(f'{official_key} must be an integer')
    return validate(row)


def fetch(day, retries=3, opener=urlopen, sleep=time.sleep):
    url = API + '?' + urlencode({'response': 'json', 'date': day.strftime('%Y%m%d')})
    headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 (compatible; tw-market-monitor/1.0)',
               'Referer': DASHBOARD, 'Cache-Control': 'no-cache'}
    for attempt in range(retries):
        try:
            request = Request(url, headers=headers)
            with opener(request, timeout=25) as response:
                payload = json.load(response)
            return from_official(payload, day)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f'official API transport failure: {exc}') from exc
            sleep(2 ** attempt)
    raise RuntimeError('unexpected retry exit')


def read_old():
    if not DEST.exists():
        return {'schema': 1, 'first_date': str(START), 'rows': [], 'calendar': []}
    obj = json.loads(DEST.read_text(encoding='utf-8'))
    if not isinstance(obj, dict) or not isinstance(obj.get('rows'), list):
        raise ValueError('existing JSON rows malformed')
    for row in obj['rows']:
        validate(row)
    return obj


def trading_calendar(start, end):
    if not MARKET.exists():
        raise RuntimeError('market_monitor.json is required for the official trading-day calendar')
    market = json.loads(MARKET.read_text(encoding='utf-8'))
    rows = market.get('rows', [])
    if not isinstance(rows, list) or not rows:
        raise RuntimeError('market_monitor.json has no rows')
    days = set()
    for row in rows:
        value = row.get('date') if isinstance(row, dict) else None
        if isinstance(value, str) and re.fullmatch(r'20\d{2}-\d{2}-\d{2}', value) and start.isoformat() <= value <= end.isoformat():
            days.add(value)
    if not days:
        raise RuntimeError('no trading days in the requested range')
    return sorted(days)


def persist(new_rows, calendar):
    obj = read_old()
    by_date = {row['date']: row for row in obj['rows']}
    by_date.update({row['date']: validate(row) for row in new_rows})
    merged_cal = sorted(set(obj.get('calendar', []) or []) | set(calendar))
    merged_rows = [by_date[k] for k in sorted(by_date)]
    if merged_rows == obj['rows'] and merged_cal == obj.get('calendar', []):
        print('TWSE_CREDIT_UNCHANGED', len(merged_rows), flush=True)
        return
    obj.update({'schema': 1, 'source': API, 'first_date': str(START),
                'calendar': merged_cal, 'rows': merged_rows})
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(DEST)
    print('TWSE_CREDIT_PUBLISHED_LOCALLY', len(merged_rows), flush=True)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--backfill', action='store_true')
    mode.add_argument('--daily', action='store_true')
    mode.add_argument('--probe', action='store_true')
    parser.add_argument('--start', default=str(START))
    parser.add_argument('--end')
    parser.add_argument('--max-consecutive-failures', type=int, default=5,
                        help='Abort after consecutive missing records, preserving prior verified rows')
    args = parser.parse_args()
    today = dt.datetime.now(TZ).date()
    if args.daily or args.probe:
        # Find the most recently published trading date; do not assume today has data.
        days = [today - dt.timedelta(days=i) for i in range(6)]
        if args.probe:
            days = [dt.date.fromisoformat(args.start)]
        last_error = None
        for day in days:
            try:
                row = fetch(day)
                print('TWSE_CREDIT_VERIFIED', json.dumps(row, ensure_ascii=False), flush=True)
                if not args.probe:
                    persist([row], [str(day)])
                return
            except (ValueError, RuntimeError) as exc:
                last_error = exc
                print('TWSE_CREDIT_UNAVAILABLE', str(day), str(exc), flush=True)
        raise SystemExit(f'No verified recent official row: {last_error}')

    start = max(START, dt.date.fromisoformat(args.start))
    end = min(today, dt.date.fromisoformat(args.end) if args.end else today)
    if end < start:
        raise SystemExit('end_date precedes start_date')
    calendar = trading_calendar(start, end)
    known = {row['date'] for row in read_old()['rows']}
    pending = [day for day in calendar if day not in known]
    print('TWSE_CREDIT_BACKFILL_START', len(pending), str(start), str(end), flush=True)
    batch = []
    missing = []
    failures_in_a_row = 0
    for value in pending:
        try:
            row = fetch(dt.date.fromisoformat(value))
            batch.append(row)
            failures_in_a_row = 0
            print('TWSE_CREDIT_VERIFIED', value, row['maintenance_ratio'], row['call_accounts'], flush=True)
        except (ValueError, RuntimeError) as exc:
            failures_in_a_row += 1
            missing.append({'date': value, 'reason': str(exc)[:220]})
            print('TWSE_CREDIT_MISSING', value, str(exc), flush=True)
        if len(batch) >= 10:
            persist(batch, calendar)
            batch.clear()
        if failures_in_a_row >= max(1, args.max_consecutive_failures):
            print('TWSE_CREDIT_EARLY_STOP', failures_in_a_row, flush=True)
            break
        time.sleep(0.25)
    if batch or calendar:
        persist(batch, calendar)
    all_rows = read_old()['rows']
    covered = {row['date'] for row in all_rows}
    gaps = [day for day in calendar if day not in covered]
    summary = {'expected': len(calendar), 'verified': len(calendar) - len(gaps),
               'missing': len(gaps), 'missing_dates': gaps[:50], 'sample_errors': missing[:8]}
    print('TWSE_CREDIT_SUMMARY', json.dumps(summary, ensure_ascii=False), flush=True)
    if gaps:
        raise SystemExit(3)


if __name__ == '__main__':
    main()
