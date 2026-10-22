#!/usr/bin/env python3
"""Offline-only EPS matching; no OpenAI, PDF downloads, or Telegram.
Only forecasts published strictly BEFORE the actual EPS announcement qualify.
"""
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERIOD = re.compile(r'^20\d{2}-Q[1-4]$')

def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def valid_date(value):
    try:
        s = str(value or '')[:10]
        date.fromisoformat(s)
        return s
    except ValueError:
        return ''

def actuals(data):
    for r in read(data/'self_reports.json', {'items':[]}).get('items',[]):
        month = str(r.get('monthly_period') or '')
        if re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', month) and r.get('monthly_eps') is not None:
            yield r, f'{month[:4]}-Q{(int(month[5:])-1)//3+1}', 'monthly', month, r['monthly_eps']
    for r in read(data/'quarterly_earnings.json', {'reports':[]}).get('reports',[]):
        period = str(r.get('period') or '')
        if PERIOD.fullmatch(period) and r.get('eps') is not None:
            yield r, period, 'quarterly', period, r['eps']

def compare(root=ROOT):
    data = root/'data'
    forecasts = read(data/'broker_eps_forecasts.json', {'items':[]}).get('items',[])
    by_key = {}
    for f in forecasts:
        ticker, period = str(f.get('ticker') or ''), str(f.get('period') or '')
        report_date = valid_date(f.get('report_date'))
        try: eps = float(f.get('eps'))
        except (ValueError,TypeError): continue
        if not (re.fullmatch(r'\d{4}',ticker) and PERIOD.fullmatch(period) and report_date and eps != 0): continue
        by_key.setdefault((ticker,period), []).append((f,report_date,eps))
    matches = {}
    for a,period,kind,actual_period,value in actuals(data):
        ticker = str(a.get('ticker') or '')
        published = valid_date(a.get('publish_date'))
        if not published: continue  # Fail closed: missing date is NOT proof of pre-announcement forecast.
        try: actual_eps = float(value)
        except (ValueError,TypeError): continue
        for f,report_date,forecast_eps in by_key.get((ticker,period),[]):
            if report_date >= published: continue  # Same-day is excluded: intraday order unknown.
            rid = str(f.get('report_id') or '')
            if not rid: continue
            key = (kind,actual_period,ticker,rid)
            matches[key] = {
                'ticker':ticker, 'name':a.get('name') or '', 'period':period,
                'actual_kind':kind, 'actual_period':actual_period,
                'announcement_date':published, 'actual_eps':actual_eps,
                'broker':f.get('broker') or '', 'report_date':report_date,
                'report_id':rid, 'forecast_eps':forecast_eps,
                'ratio_pct':round(actual_eps/forecast_eps*100,1),
                'ratio_label':'單月／季預估比' if kind=='monthly' else '季度達成率',
                'source_url':f.get('source_url') or ''
            }
    output = {'version':1, 'items':sorted(matches.values(),key=lambda r:(r['ticker'],r['period'],r['actual_period'],r['report_date'],r['report_id']))}
    path=data/'broker_eps_comparisons.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(output,ensure_ascii=False,indent=2)+'\n'
    if not path.exists() or path.read_text(encoding='utf-8')!=content:
        path.write_text(content,encoding='utf-8')
    print(f'Offline compare: {len(output["items"])} matches; API calls=0; PDF parses=0')
    return output

if __name__=='__main__': compare()
