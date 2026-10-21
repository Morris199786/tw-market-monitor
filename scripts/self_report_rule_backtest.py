#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent July-Oct rule backtest from OFFICIAL complete attention universe.
Never modifies V17 or production data. Historic MOPS event labels from verified archive.
July lookback exclusions require June MOPS events; unavailable variants are marked NA.
"""
import argparse, collections, csv, datetime as dt, hashlib, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import self_report_predict as prod

START, END = '2026-07-01', '2026-10-20'
WARMUP = '2026-06-01'
MARKETS = ('twse', 'tpex')

# Recognize Arabic, Chinese, full-width clause numbers; exclude only clauses 10-13.
CN = {'十':10, '十一':11, '十二':12, '十三':13, '一〇':10, '一一':11, '一二':12, '一三':13}
CLAUSE = re.compile(r'(?:第\s*)?([0-9０-９]{1,2}|十[一二三]?|一[〇一二三])\s*(?:款|條)', re.I)

def valid_notice(n):
    reason = str(n.get('reason') or '').translate(str.maketrans('０１２３４５６７８９','0123456789'))
    numbers = []
    for m in CLAUSE.finditer(reason):
        v = m.group(1)
        num = int(v) if v.isdigit() else CN.get(v)
        if num is not None: numbers.append(num)
    # Conservative: if the only explicit clauses are 10-13, exclude.
    # If a notice mixes 1-9 with 10-13, retain the qualifying clause.
    if numbers and all(10 <= x <= 13 for x in numbers):
        return False
    # Ambiguous 10-13 phrasing without a parseable clause must be audited.
    if re.search(r'第\s*(?:十[一二三]?|1[0-3])\s*款', reason) and not numbers:
        raise ValueError(f'Unparseable attention clause: {n}')
    return True

def read_csv(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write_csv(p, rows, fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def count_metrics(h,p,a):
    return dict(hits=h,predictions=p,actuals=a,precision=round(h/p,6) if p else None,recall=round(h/a,6) if a else None)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='private_rule_backtest_v2')
    ap.add_argument('--events',default='data/self_report_v17_archive/events.csv')
    ap.add_argument('--june-events',default='',help='Verified June 2026 MOPS event CSV, optional. Needed for valid July cooldown comparisons.')
    ap.add_argument('--attention-cache',default='private_rule_attention_cache')
    args=ap.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    events=read_csv(args.events)
    if args.june_events:events+=read_csv(args.june_events)
    events=[e for e in events if WARMUP <= e.get('date','') <= END and e.get('market') in MARKETS]
    if not events:raise SystemExit('No historical MOPS event labels')
    june_verified=bool(args.june_events) and any(e['date'].startswith('2026-06') for e in events)
    master=prod.read(ROOT/'data/master.json')['stocks']
    monitor=prod.read(ROOT/'data/market_monitor.json')
    calendar=sorted({x['date'] for x in monitor.get('raw',[]) if x.get('index') is not None and WARMUP<=x['date']<=END})
    if not calendar or calendar[0]>'2026-06-03' or calendar[-1]<END:
        raise SystemExit('Market trading calendar missing June warmup or Oct20')
    notices=[];query_audit=[]
    for market in MARKETS:
        a=dt.date.fromisoformat(WARMUP);finish=dt.date.fromisoformat(END)
        while a<=finish:
            b=min(a+dt.timedelta(days=13),finish)
            rows,status=prod.attention(a.isoformat(),b.isoformat(),cache=args.attention_cache,markets=(market,))
            notices.extend(rows)
            query_audit.append(dict(market=market,start=a.isoformat(),end=b.isoformat(),count=len(rows)))
            a=b+dt.timedelta(days=1)
    # Only remove disqualified attention notices, before computing all lookback windows.
    dedup={}
    for n in notices:
        key=(n['date'],n['market'],n['ticker'])
        if key in dedup:dedup[key]['reason']+=' '+n.get('reason','')
        else:dedup[key]=dict(n)
    notices=list(dedup.values())
    qualified=[n for n in notices if valid_notice(n)]
    excluded=[n for n in notices if not valid_notice(n)]
    if not qualified or not excluded:
        raise SystemExit('Attention clause filtering looks suspicious: zero qualifying or zero 10-13 notices; audit required')
    event_objects=[]
    for e in events:
        event_objects.append(dict(date=e['date'],ticker=e['ticker'],month=e.get('month'),market=e['market'],kind=e.get('kind'),name=e.get('name','')))
    # Rebuild EVERY day's candidate pool from the official notice history, not old scores.csv.
    dates=[d for d in calendar if START<=d<=END]
    truth=collections.defaultdict(set);prior=collections.defaultdict(list)
    for e in event_objects:
        prior[e['ticker']].append(e)
        if e['kind']=='attention':truth[(e['date'],e['market'])].add(e['ticker'])
    for arr in prior.values():arr.sort(key=lambda x:x['date'])
    daily=[];summaries=[];candidate_audit=[]
    variants={
        'listed_n1_otc_n5ge3':lambda r: r['n1']>=1 if r['market']=='twse' else r['n5']>=3,
        'listed_n1_otc_n5ge2':lambda r: r['n1']>=1 if r['market']=='twse' else r['n5']>=2,
        'listed_n1_otc_n3ge2_or_n5ge3':lambda r: r['n1']>=1 if r['market']=='twse' else r['n3']>=2 or r['n5']>=3,
        'listed_n1_otc_n3ge3_or_n5ge2':lambda r: r['n1']>=1 if r['market']=='twse' else r['n3']>=3 or r['n5']>=2,
    }
    for i,day in enumerate(dates):
        idx=calendar.index(day)
        if idx<20:raise SystemExit('Insufficient June warmup for '+day)
        cutoff=calendar[idx-1]
        windows={n:set(calendar[max(0,idx-n):idx]) for n in (1,3,5,10,20)}
        grouped=collections.defaultdict(list)
        for n in qualified:
            if n['date']<=cutoff and n['ticker'] in master and master[n['ticker']].get('market')==n['market']:
                grouped[(n['market'],n['ticker'])].append(n['date'])
        rows=[]
        for (market,ticker),hist in grouped.items():
            counts={f'n{n}':sum(d in windows[n] for d in hist) for n in windows}
            if counts['n20']==0:continue
            rows.append(dict(date=day,cutoff=cutoff,market=market,ticker=ticker,**counts))
        candidate_audit.append(dict(date=day,all_attention_candidates=len(rows),twse=sum(r['market']=='twse' for r in rows),tpex=sum(r['market']=='tpex' for r in rows)))
        for v,rule in variants.items():
            for excl in ('none','30_calendar_days','same_target_month','both'):
                # Without June reports, July lookback-based exclusions cannot be trusted.
                valid=not(day<'2026-08-01' and excl!='none' and not june_verified)
                for market in MARKETS:
                    pool=[]
                    for r in rows:
                        if r['market']!=market or not rule(r):continue
                        earlier=[e for e in prior[r['ticker']] if e['date']<=cutoff]
                        within30=any(0<=(dt.date.fromisoformat(day)-dt.date.fromisoformat(e['date'])).days<=30 for e in earlier)
                        target=(dt.date.fromisoformat(day).replace(day=1)-dt.timedelta(days=1)).strftime('%Y-%m')
                        same_month=any(e.get('month')==target for e in earlier)
                        if excl in ('30_calendar_days','both') and within30:continue
                        if excl in ('same_target_month','both') and same_month:continue
                        pool.append(r)
                    pool.sort(key=lambda r:(-r['n5'],-r['n3'],r['ticker']))
                    pool=pool[:10]
                    picked={r['ticker'] for r in pool};actual=truth[(day,market)]
                    daily.append(dict(date=day,month=day[:7],market=market,variant=v,exclusion=excl,valid=valid,
                                      predictions=len(picked) if valid else '',hits=len(picked&actual) if valid else '',actuals=len(actual) if valid else '',
                                      picks=' '.join(sorted(picked)) if valid else '',hit_tickers=' '.join(sorted(picked&actual)) if valid else '',
                                      missed_tickers=' '.join(sorted(actual-picked)) if valid else '',
                                      warning='' if valid else 'June MOPS events missing: July lookback exclusion cannot be evaluated'))
    for v in variants:
        for excl in ('none','30_calendar_days','same_target_month','both'):
            for market in MARKETS:
                for month in ('2026-07','2026-08','2026-09','2026-10','ALL'):
                    subset=[r for r in daily if r['variant']==v and r['exclusion']==excl and r['market']==market and (month=='ALL' or r['month']==month)]
                    valid=[r for r in subset if r['valid']]
                    m=count_metrics(sum(r['hits'] for r in valid),sum(r['predictions'] for r in valid),sum(r['actuals'] for r in valid))
                    summaries.append(dict(variant=v,exclusion=excl,market=market,month=month,days=len(valid),skipped_days=len(subset)-len(valid),**m))
    write_csv(out/'summary.csv',summaries,list(summaries[0]))
    write_csv(out/'daily.csv',daily,list(daily[0]))
    write_csv(out/'candidate_audit.csv',candidate_audit,list(candidate_audit[0]))
    write_csv(out/'excluded_clause_10_13.csv',excluded,['date','market','ticker','name','reason'])
    audit=dict(start=START,end=END,trading_days=len(dates),raw_notices=len(notices),qualifying_notices=len(qualified),excluded_10_to_13=len(excluded),
               source='TWSE and TPEx official attention APIs; full attention-derived candidate pool, not archived scores.csv',
               labels='data/self_report_v17_archive/events.csv (attention-triggered only)',june_mops_verified=june_verified,
               july_lookback_metrics_available=june_verified,attention_queries=query_audit,
               limitations=['No future announcements used in prediction filters',
                            'MOPS historical event archive must be complete for recall to be definitive',
                            'V17 comparison must use same dates and verified label universe',
                            'If June MOPS history absent, July cooldown variants are NA rather than falsely calculated'])
    (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'README.txt').open('w',encoding='utf-8') as f:f.write('PRIVATE RULE STRATEGY ONLY. Does not modify V17. See audit.json for limitations.\n')
    print(json.dumps({k:audit[k] for k in ('trading_days','raw_notices','qualifying_notices','excluded_10_to_13','june_mops_verified')},ensure_ascii=False))
    for x in summaries:
        if x['month']=='ALL' and x['exclusion']=='none':print('RULE_RESULT',json.dumps(x,ensure_ascii=False))

if __name__=='__main__':main()
