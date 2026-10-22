#!/usr/bin/env python3
"""Refresh website actuals independently from the next forecast date."""
import argparse
import datetime as dt
import re
from zoneinfo import ZoneInfo
from self_report_forecast_export import load, save

TZ = ZoneInfo('Asia/Taipei')

def all_items(history):
    return history.get('items', []) + history.get('parse_failed', []) + history.get('diagnostics', {}).get('parse_failed', [])

def attention(item):
    if item.get('source') == 'news_backup':
        return False  # News is not an official attention-trading announcement.
    subject = str(item.get('subject') or '')
    return bool(re.search(r'注意交易|注意股|達公[布佈]注意', subject))

def settle(history, master, ledger, existing, now):
    stamp = dt.datetime.fromisoformat(history['updated_at'])
    if stamp.tzinfo is None:
        raise ValueError('History timestamp needs timezone')
    stamp = stamp.astimezone(TZ)
    days = existing.setdefault('days', {})
    for target in sorted(ledger.get('forecasts', {})):
        if target < '2026-10-21' or target > now.date().isoformat():
            continue
        day = dt.date.fromisoformat(target)
        if stamp.date() < day or (stamp.date() == day and stamp.hour < 20):
            continue
        if target < str(history.get('monitor_start_date', '')):
            continue
        codes = {'twse': set(), 'tpex': set()}
        for item in all_items(history):
            if item.get('publish_date') != target or not attention(item) or item.get('monthly_eps') is None:
                continue
            ticker = str(item.get('ticker') or '').strip()
            if not re.fullmatch(r'[1-9]\d{3}', ticker):
                continue
            market = master['stocks'].get(ticker, {}).get('market')
            if market not in codes:
                raise ValueError('Unknown market: '+ticker)
            codes[market].add(ticker)
        rec = dict(complete=True, provisional=stamp.date() == day,
                   source='site_self_reports_history_assumed_complete',
                   verified_at=stamp.isoformat(), **{k: sorted(v) for k,v in codes.items()})
        old = days.get(target)
        if old and old != rec:
            existing.setdefault('revisions', {}).setdefault(target, []).append(old)
        days[target] = rec
    existing['schema'] = 2
    return existing

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--history', default='data/self_reports_history.json')
    p.add_argument('--master', default='data/master.json')
    p.add_argument('--ledger', default='data/self_report_v17_forecast_ledger.json')
    p.add_argument('--output', default='data/self_report_v17_actuals_verified.json')
    a = p.parse_args()
    save(a.output, settle(load(a.history), load(a.master), load(a.ledger),
                         load(a.output, {'days': {}}), dt.datetime.now(TZ)))

if __name__ == '__main__':
    main()


