#!/usr/bin/env python3
"""Settle V17 using the site's existing self-report history as the assumed complete universe.

The user explicitly accepts site coverage as complete. Only attention-triggered
announcements count; EPS parsing success is NOT required. Each eligible past
forecast date is frozen into verified_actuals once the history cache has advanced
beyond that date. Never overwrite previously frozen actuals.
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Taipei')
START = '2026-10-21'

def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default

def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def collect(history, master, target):
    result = {'twse': set(), 'tpex': set()}
    stocks = master['stocks']
    unknown = []
    for item in history.get('items', []):
        if item.get('publish_date') != target or item.get('match_reason') != 'attention_trading':
            continue
        subject = str(item.get('subject') or '')
        if not re.search(r'注意交易|注意股|達公[布佈]注意', subject):
            continue
        ticker = str(item.get('ticker') or '').strip()
        if not re.fullmatch(r'[1-9]\d{3}', ticker):
            continue
        market = (stocks.get(ticker) or {}).get('market')
        if market not in result:
            unknown.append(ticker)
        else:
            result[market].add(ticker)
    if unknown:
        raise SystemExit('Unclassified attention report tickers: ' + ','.join(sorted(set(unknown))))
    return {k: sorted(v) for k, v in result.items()}

def run(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', default='data/self_reports_history.json')
    ap.add_argument('--master', default='data/master.json')
    ap.add_argument('--ledger', default='data/self_report_v17_forecast_ledger.json')
    ap.add_argument('--output', default='data/self_report_v17_actuals_verified.json')
    args = ap.parse_args(argv)
    history, master, ledger = (read(args.history), read(args.master), read(args.ledger, {'forecasts': {}}))
    if not all(isinstance(v, dict) for v in (history, master, ledger)):
        raise SystemExit('Missing self-report history, stock master or forecast ledger')
    cache_time = dt.datetime.fromisoformat(history['updated_at'])
    if cache_time.tzinfo is None:
        raise SystemExit('History updated_at must include timezone')
    cache_day = cache_time.astimezone(TZ).date()
    today = dt.datetime.now(TZ).date()
    existing = read(args.output, {'schema': 1, 'days': {}})
    days = existing.setdefault('days', {})
    added = []
    for target in sorted(ledger.get('forecasts', {})):
        if target < START or target in days:
            continue
        target_day = dt.date.fromisoformat(target)
        # At least the next calendar day and a refreshed website cache.
        if target_day >= today or cache_day <= target_day:
            continue
        codes = collect(history, master, target)
        days[target] = {
            'complete': True, **codes,
            'source': 'site_self_reports_history_assumed_complete',
            'verified_at': cache_time.isoformat(),
        }
        added.append(target)
    existing['schema'] = 1
    write(args.output, existing)
    print('settled_new_dates=', added, 'settled_total=', len(days), 'cache_updated_at=', cache_time.isoformat())

if __name__ == '__main__':
    run()
