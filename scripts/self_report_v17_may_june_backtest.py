#!/usr/bin/env python3
"""Private May/June V17 walk-forward backtest. Fail closed on missing actuals.

Uses the repository's exact V17 make_rows/evaluate/score_v17/choose functions.
No website data writes or production ledger changes.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import self_report_predict as model


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    ap=argparse.ArgumentParser()
    ap.add_argument('--notices',required=True,help='Verified daily attention notices JSON list: date,ticker,market,reason')
    ap.add_argument('--events',required=True,help='Verified historical monthly self-report events CSV: date,ticker,month,market,kind')
    ap.add_argument('--master',default='data/master.json')
    ap.add_argument('--calendar',required=True,help='Official full trading calendar JSON array of ISO dates')
    ap.add_argument('--out',default='private_backtest_may_june')
    ap.add_argument('--start',default='2026-01-01')
    args=ap.parse_args()
    notices=json.loads(Path(args.notices).read_text(encoding='utf-8-sig'))
    with open(args.events,encoding='utf-8-sig',newline='') as f:events=list(csv.DictReader(f))
    master=json.loads(Path(args.master).read_text(encoding='utf-8-sig'))['stocks']
    cal=json.loads(Path(args.calendar).read_text(encoding='utf-8-sig'))
    if not isinstance(cal,list) or not isinstance(notices,list):raise SystemExit('Invalid input format')
    if len(cal)!=len(set(cal)) or cal!=sorted(cal):raise SystemExit('Trading calendar must be sorted unique')
    if not all(x in cal for x in ('2026-04-30','2026-05-29','2026-06-30')):
        raise SystemExit('Historical trading calendar incomplete (April 30, May 29, June 30)')
    if min(cal)>'2026-01-01':raise SystemExit('Insufficient training warmup: calendar must start by 2026-01-01')
    if not any(e.get('date','')<'2026-05-01' and e.get('kind')=='attention' for e in events):
        raise SystemExit('Historical labels missing before May: cannot train V17 without leakage')
    if not any('2026-05-01'<=e.get('date','')<='2026-05-31' and e.get('kind')=='attention' for e in events):
        raise SystemExit('May attention-triggered self-report labels absent; cannot measure recall')
    if not any('2026-06-01'<=e.get('date','')<='2026-06-30' and e.get('kind')=='attention' for e in events):
        raise SystemExit('June attention-triggered self-report labels absent; cannot measure recall')
    if not any(n.get('date','')<'2026-05-01' for n in notices):raise SystemExit('Attention history before May missing')
    if not any('2026-06-01'<=n.get('date','')<='2026-06-30' for n in notices):raise SystemExit('June attention history missing')
    if not all(e.get('ticker') in master for e in events):raise SystemExit('Historical events include unknown tickers')
    # Input completeness is a responsibility of the historical collectors; nonempty data is not proof of completeness.
    rows={}
    for i,day in enumerate(cal):
        if day<args.start or day>'2026-06-30' or i==0:continue
        rows[day]=model.make_rows(cal[i-1],day,cal,notices,events,master)
    summary,daily,picks,_,_=model.evaluate(rows,events,evaluation_start='2026-05-01')
    filtered_daily=[r for r in daily if '2026-05-01'<=r['date']<='2026-06-30']
    if not filtered_daily:raise SystemExit('No evaluated days in May-June (insufficient warmup)')
    selected_days={x['date'] for x in filtered_daily}
    report={}
    for month in ('2026-05','2026-06'):
        report[month]={}
        for market in ('twse','tpex'):
            pp=[p for p in picks if p['date'][:7]==month and p['market']==market]
            dates={x['date'] for x in filtered_daily if x['date'][:7]==month}
            actual=sum(len({e['ticker'] for e in events if e['date']==d and e['market']==market and e['kind']=='attention'}) for d in dates)
            report[month][market]=model.metrics(pp,actual)
            report[month][market]['evaluated_days']=len(dates)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    payload={'kind':'private_retrospective_walk_forward','model_version':model.VERSION,'period':['2026-05','2026-06'],
             'input_hashes':{k:sha(v) for k,v in [('notices',args.notices),('events',args.events),('calendar',args.calendar),('master',args.master)]},
             'metrics':report,'warning':'Accuracy depends on verified complete historical MOPS self-report universe; do not publish as prospective metrics.'}
    model.write(out/'summary.json',payload)
    model.csvout(out/'daily.csv',filtered_daily)
    model.csvout(out/'picks.csv',[p for p in picks if p['date'] in selected_days])
    print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__':run()
