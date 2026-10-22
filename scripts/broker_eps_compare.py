#!/usr/bin/env python3
"""Evidence-dated EPS comparison; offline, deterministic, no paid calls.

Only actual EPS with an explicit, verified announcement date may match a
broker report whose date is earlier than or equal to. Never derive a disclosure date
from a fiscal period, file mtime, or a scheduled board meeting.
"""
from __future__ import annotations
import json
import math
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARTER = re.compile(r'^20\d{2}-Q[1-4]$')
MONTH = re.compile(r'^20\d{2}-(?:0[1-9]|1[0-2])$')
TICKER = re.compile(r'^\d{4}$')

def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default

def valid_date(value):
    s = str(value or '')[:10]
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return ''

def number(value):
    if isinstance(value, bool) or value is None or str(value).strip() == '':
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None

def actuals(data):
    """All verifiably dated monthly/quarterly announcements, including history."""
    seen = set()
    sources = (
        ('self_reports.json', 'items'),
        ('self_reports_history.json', 'items'),
        ('quarterly_earnings.json', 'reports'),
        ('quarterly_earnings_announcements_history.json', 'items'),
    )
    for filename, key in sources:
        for r in load(data / filename, {}).get(key, []):
            ticker = str(r.get('ticker') or '')
            day = valid_date(r.get('publish_date'))
            if not TICKER.fullmatch(ticker) or not day:
                continue
            candidates = []
            if filename.startswith('self_reports'):
                month = str(r.get('monthly_period') or '')
                if MONTH.fullmatch(month):
                    period = f'{month[:4]}-Q{(int(month[5:])-1)//3+1}'
                    candidates.append(('monthly', month, period, number(r.get('monthly_eps'))))
                # A self-report may also explicitly disclose last quarter's EPS.
                # Its own publication date, not the financial period, is used.
                qp = str(r.get('quarter_period') or '')
                if QUARTER.fullmatch(qp):
                    candidates.append(('quarterly', qp, qp, number(r.get('quarter_eps'))))
            else:
                qp = str(r.get('period') or '')
                if QUARTER.fullmatch(qp):
                    candidates.append(('quarterly', qp, qp, number(r.get('eps'))))
            for kind, actual_period, period, eps in candidates:
                if eps is None:
                    continue
                ident = (ticker, kind, actual_period, day, eps)
                if ident in seen:
                    continue
                seen.add(ident)
                yield {'ticker': ticker, 'name': r.get('name') or '', 'kind': kind,
                       'actual_period': actual_period, 'period': period,
                       'announcement_date': day, 'actual_eps': eps,
                       'actual_source': filename}

def compare(root=ROOT):
    data = root / 'data'
    forecasts = load(data / 'broker_eps_forecasts.json', {'items': []}).get('items', [])
    by_key = {}
    for f in forecasts:
        ticker, period = str(f.get('ticker') or ''), str(f.get('period') or '')
        day, eps = valid_date(f.get('report_date')), number(f.get('eps'))
        if not TICKER.fullmatch(ticker) or not QUARTER.fullmatch(period) or not day or eps in (None, 0) or not f.get('report_id'):
            continue
        by_key.setdefault((ticker, period), []).append((f, day, eps))
    matches = {}
    audit = {'forecasts': len(forecasts), 'valid_forecasts': sum(map(len, by_key.values())),
             'dated_actuals': 0, 'potential_same_ticker_period': 0,
             'excluded_late': 0, 'matches': 0}
    for a in actuals(data):
        audit['dated_actuals'] += 1
        for f, report_day, estimate in by_key.get((a['ticker'], a['period']), []):
            audit['potential_same_ticker_period'] += 1
            if report_day > a['announcement_date']:
                audit['excluded_late'] += 1
                continue
            rid = str(f['report_id'])
            key = (a['ticker'], a['kind'], a['actual_period'], a['announcement_date'], a['actual_eps'], rid)
            matches[key] = {
                'ticker': a['ticker'], 'name': a['name'], 'period': a['period'],
                'actual_kind': a['kind'], 'actual_period': a['actual_period'],
                'announcement_date': a['announcement_date'], 'actual_eps': a['actual_eps'],
                'broker': f.get('broker') or '', 'report_date': report_day,
                'report_id': rid, 'forecast_eps': estimate,
                'ratio_pct': round(a['actual_eps'] / estimate * 100, 1),
                'ratio_label': '單月／季預估比' if a['kind'] == 'monthly' else '季度達成率',
                'source_url': f.get('source_url') or '',
                'actual_source': a['actual_source']}
    output = {'version': 3, 'items': sorted(matches.values(), key=lambda x:
              (x['ticker'], x['period'], x['actual_period'], x['announcement_date'], x['report_date'], x['report_id']))}
    audit['matches'] = len(output['items'])
    for filename, value in (('broker_eps_comparisons.json', output), ('broker_eps_compare_audit.json', audit)):
        p = data / filename
        content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if not p.exists() or p.read_text(encoding='utf-8') != content:
            p.write_text(content, encoding='utf-8')
    print('EPS compare audit:', json.dumps(audit, ensure_ascii=False))
    print('API calls=0; PDF parses=0')
    return output

if __name__ == '__main__':
    compare()
