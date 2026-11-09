#!/usr/bin/env python3
"""Refresh website actuals independently from the next forecast date."""
import argparse
import datetime as dt
import re
from zoneinfo import ZoneInfo
from self_report_forecast_export import load, save
from self_report_calendar import windows

TZ = ZoneInfo('Asia/Taipei')

def all_items(history):
    return history.get('items', []) + history.get('parse_failed', []) + history.get('diagnostics', {}).get('parse_failed', [])

def attention(item):
    if item.get('source') == 'news_backup':
        return False  # News is not an official attention-trading announcement.
    subject = str(item.get('subject') or '')
    return bool(re.search(r'注意交易|注意股|達公[布佈]注意|(?:多次)?達公[布佈]交易資訊標準|公[布佈]交易資訊標準', re.sub(r'\s+', '', subject)))

def confirmed_actual(item):
    """Require an actual attention-triggered financial disclosure, not merely a notice.

    Preserve already parsed EPS items; accept an unparsed official filing only
    when its downloaded detail includes a single-month financial table. Parsed
    diagnostics without source detail are not sufficient proof of publication.
    """
    if not attention(item):
        return False
    if item.get('monthly_eps') is not None:
        return True
    if item.get('source') != 'mops_ajax' or item.get('source_error'):
        return False
    detail = str(item.get('detail') or '')
    return bool(
        re.search(r'財務業務資訊|財務資訊', detail)
        and re.search(r'最近一月|最近一個月|單月|\(月\)', detail)
        and re.search(r'營業收入|營收', detail)
        and re.search(r'每股(?:稅後|基本)?(?:盈餘|損益)|EPS', detail, re.I)
    )

def settle(history, master, ledger, existing, now):
    stamp = dt.datetime.fromisoformat(history['updated_at'])
    if stamp.tzinfo is None:
        raise ValueError('History timestamp needs timezone')
    stamp = stamp.astimezone(TZ)
    days = existing.setdefault('days', {})
    grouped = windows(ledger.get('forecasts', {}))
    for target, forecast in sorted(grouped.items()):
        if target < '2026-10-21' or target > now.date().isoformat():
            continue
        day = dt.date.fromisoformat(target)
        if stamp.date() < day or (stamp.date() == day and stamp.hour < 20):
            continue
        if target < str(history.get('monitor_start_date', '')):
            continue
        codes = {'twse': set(), 'tpex': set()}
        first = {}
        for item in all_items(history):
            if not confirmed_actual(item):
                continue
            key = (item.get('ticker'), item.get('monthly_period') or item.get('publish_date'))
            if key not in first or item.get('publish_date', '') < first[key].get('publish_date', ''):
                first[key] = item
        for item in first.values():
            if not forecast['asof'] < item.get('publish_date', '') <= target:
                continue
            ticker = str(item.get('ticker') or '').strip()
            if not re.fullmatch(r'[1-9]\d{3}', ticker):
                continue
            market = master['stocks'].get(ticker, {}).get('market')
            if market not in codes:
                raise ValueError('Unknown market: '+ticker)
            codes[market].add(ticker)
        # Preserve manually confirmed additions across automated reruns.
        # Manual additions are explicitly recorded in the verified actuals JSON.
        old = days.get(target)
        if old:
            for market in ('twse', 'tpex'):
                codes[market].update(str(x) for x in old.get('manual_verified_' + market, []))
        rec = dict(complete=True, provisional=stamp.date() == day,
                   source='site_history_signal_window_v1', window_start=forecast['asof'], original_dates=forecast['original_dates'],
                   verified_at=stamp.isoformat(), **{k: sorted(v) for k,v in codes.items()})
        if old:
            for market in ('twse', 'tpex'):
                if old.get('manual_verified_' + market):
                    rec['manual_verified_' + market] = old['manual_verified_' + market]
            if old.get('manual_verification_note'):
                rec['manual_verification_note'] = old['manual_verification_note']
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


