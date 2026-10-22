#!/usr/bin/env python3
"""Compare brokerage forecasts only with dated, verifiable actual EPS disclosures.
No network, AI, PDF reparse, or paid calls. Never infer release date from fiscal period.
"""
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Q = re.compile(r'^20\d{2}-Q[1-4]$')
M = re.compile(r'^20\d{2}-(0[1-9]|1[0-2])$')

def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def valid_date(value):
    try:
        s = str(value or '')[:10]
        date.fromisoformat(s)
        return s
    except (TypeError, ValueError):
        return ''

def actuals(data):
    # History retains self reports after the live cards have rolled off.
    # Deduplicate repeated announcements across current and historical feeds.
    seen = set()
    for filename in ('self_reports.json', 'self_reports_history.json'):
        for r in read(data / filename, {'items': []}).get('items', []):
            ticker = str(r.get('ticker') or '')
            month = str(r.get('monthly_period') or '')
            day = valid_date(r.get('publish_date'))
            value = r.get('monthly_eps')
            if not (re.fullmatch(r'\d{4}', ticker) and M.fullmatch(month) and day and value is not None):
                continue
            key = ('monthly', ticker, month, day)
            if key in seen:
                continue
            seen.add(key)
            yield r, f'{month[:4]}-Q{(int(month[5:])-1)//3+1}', 'monthly', month, value, day
    # Only quarterly disclosures with their own actual announcement date.
    # The quarterly_earnings_history cumulative financial statement has no
    # disclosure timestamp, so it must NOT be treated as a dated release.
    for r in read(data / 'quarterly_earnings.json', {'reports': []}).get('reports', []):
        ticker = str(r.get('ticker') or '')
        period = str(r.get('period') or '')
        day = valid_date(r.get('publish_date'))
        value = r.get('eps')
        if not (re.fullmatch(r'\d{4}', ticker) and Q.fullmatch(period) and day and value is not None):
            continue
        key = ('quarterly', ticker, period, day)
        if key in seen:
            continue
        seen.add(key)
        yield r, period, 'quarterly', period, value, day

def compare(root=ROOT):
    data = root / 'data'
    forecasts = read(data / 'broker_eps_forecasts.json', {'items': []}).get('items', [])
    by_key = {}
    for f in forecasts:
        ticker, period = str(f.get('ticker') or ''), str(f.get('period') or '')
        report_date = valid_date(f.get('report_date'))
        try:
            eps = float(f.get('eps'))
        except (TypeError, ValueError):
            continue
        if not (re.fullmatch(r'\d{4}', ticker) and Q.fullmatch(period) and report_date and eps != 0):
            continue
        by_key.setdefault((ticker, period), []).append((f, report_date, eps))
    matches = {}
    for a, period, kind, actual_period, value, published in actuals(data):
        ticker = str(a['ticker'])
        try:
            actual_eps = float(value)
        except (TypeError, ValueError):
            continue
        for f, report_date, forecast_eps in by_key.get((ticker, period), []):
            if report_date >= published:
                continue  # No same-day comparison without verified intraday order.
            rid = str(f.get('report_id') or '')
            if not rid:
                continue
            key = (kind, actual_period, ticker, published, rid)
            matches[key] = {
                'ticker': ticker, 'name': a.get('name') or '', 'period': period,
                'actual_kind': kind, 'actual_period': actual_period,
                'announcement_date': published, 'actual_eps': actual_eps,
                'broker': f.get('broker') or '', 'report_date': report_date,
                'report_id': rid, 'forecast_eps': forecast_eps,
                'ratio_pct': round(actual_eps / forecast_eps * 100, 1),
                'ratio_label': '單月／季預估比' if kind == 'monthly' else '季度達成率',
                'source_url': f.get('source_url') or ''
            }
    output = {'version': 2, 'items': sorted(matches.values(), key=lambda x: (x['ticker'], x['period'], x['actual_period'], x['report_date'], x['report_id']))}
    path = data / 'broker_eps_comparisons.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(output, ensure_ascii=False, indent=2) + '\n'
    if not path.exists() or path.read_text(encoding='utf-8') != content:
        path.write_text(content, encoding='utf-8')
    print(f'Offline compare: {len(output["items"])} matches; API calls=0; PDF parses=0')
    return output

if __name__ == '__main__':
    compare()
