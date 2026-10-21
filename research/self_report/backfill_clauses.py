#!/usr/bin/env python3
"""Fetch TWSE official notices, enrich historical snapshots with as-of clauses.
Requires network when running; no paid APIs. Never use target-day notices.
"""
import argparse,csv,datetime as dt,json,re,time,urllib.request
from collections import defaultdict
from pathlib import Path
from self_report_predict import parse_notices,notice_clauses

def fetch(a,b):
    url=f'https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={a:%Y%m%d}&endDate={b:%Y%m%d}'
    for attempt in range(4):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json','Accept-Encoding':'identity'})
            with urllib.request.urlopen(req,timeout=50) as r: raw=r.read()
            return json.loads(raw.decode('utf-8-sig'))
        except Exception:
            if attempt==3: raise
            time.sleep(2**attempt)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',default='2026-06-01');ap.add_argument('--end',default='2026-09-30');ap.add_argument('--scores',default='walk_forward_scores.csv');ap.add_argument('--output',default='clause_enriched_scores.csv');args=ap.parse_args()
    a=dt.date.fromisoformat(args.start);b=dt.date.fromisoformat(args.end);notice=[]
    while a<=b:
        z=min(a+dt.timedelta(days=13),b)
        payload=fetch(a,z)
        if payload.get('stat') not in (None, 'OK'):
            raise RuntimeError(f'TWSE API error {a}..{z}: {payload.get("stat")}')
        if payload.get('data') or any(t.get('data') for t in payload.get('tables', [])):
            notice+=parse_notices(payload,'twse',a.isoformat(),z.isoformat())
        a=z+dt.timedelta(days=1);time.sleep(.4)
    if not notice:
        raise RuntimeError("No TWSE attention notices fetched: refusing empty backfill")
    by_stock=defaultdict(list)
    for n in notice:by_stock[n['ticker']].append(n)
    for v in by_stock.values():v.sort(key=lambda x:x['date'])
    with open(args.scores,encoding='utf-8-sig',newline='') as f:source=list(csv.DictReader(f))
    fields=list(source[0]);features=['clause_data_available','clause_last_known','clause_last_count','clause_distinct_20d']+[f'clause_{i}_last' for i in range(1,13)]+[f'clause_{i}_20d' for i in range(1,13)]
    fields+= [x for x in features if x not in fields]
    cutoffs=sorted({x['cutoff'] for x in source if x.get('cutoff')})
    windows={day:set(cutoffs[max(0,i-19):i+1]) for i,day in enumerate(cutoffs)}
    for row in source:
        if row['market']!='twse':
            for k in features:row[k]='0'
            continue
        cutoff=row.get('cutoff')
        if not cutoff:raise ValueError('Missing cutoff: cannot avoid future leakage')
        cutoff_dt=dt.date.fromisoformat(cutoff)
        # Calendar-aligned 20 trading days, from archived score dates; not 20 calendar days.
        allowed=windows[cutoff];hist=[x for x in by_stock[row['ticker']] if x['date'] in allowed]
        last=set(notice_clauses(hist[-1]['reason'])) if hist else set()
        all_clauses=[notice_clauses(x['reason']) for x in hist]
        row.update(clause_data_available='1',clause_last_known=str(bool(last)*1),clause_last_count=str(len(last)),clause_distinct_20d=str(len(set().union(*all_clauses))))
        for i in range(1,13):
            row[f'clause_{i}_last']=str(int(i in last))
            row[f'clause_{i}_20d']=str(sum(i in s for s in all_clauses))
    with open(args.output,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(source)
    with open('twse_notice_clauses.json','w',encoding='utf-8') as f:json.dump(notice,f,ensure_ascii=False,indent=1)
    print('Official TWSE records:',len(notice),'Archived candidates:',len(source),'Output:',args.output)
if __name__=='__main__':main()
