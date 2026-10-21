#!/usr/bin/env python3
"""Private, offline rule sweep using existing 2026-07..10 archived daily features.
No writes to production data; labels are attention-triggered announcements only.
"""
import csv,json,argparse,collections,datetime as dt
from pathlib import Path

def load(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def metric(h,p,a):return {'hits':h,'predictions':p,'actuals':a,'precision':round(h/p,4) if p else None,'recall':round(h/a,4) if a else None}
def main():
 p=argparse.ArgumentParser();p.add_argument('--scores',default='data/self_report_v17_archive/scores.csv');p.add_argument('--events',default='data/self_report_v17_archive/events.csv');p.add_argument('--out',default='private_rule_backtest');args=p.parse_args()
 rows=load(args.scores); events=load(args.events)
 if not rows or not events:raise SystemExit('Missing historical snapshots or event labels')
 dates=sorted({r['date'] for r in rows if '2026-07-01'<=r['date']<='2026-10-20'})
 actual=collections.defaultdict(set); prior=collections.defaultdict(list)
 for e in events:
  if e.get('kind')=='attention':actual[(e['date'],e['market'])].add(e['ticker'])
  prior[e['ticker']].append(e)
 for ticker in prior:prior[ticker].sort(key=lambda e:e['date'])
 groups=collections.defaultdict(list)
 for r in rows:
  if r['date'] in dates and r.get('market') in ('twse','tpex'):groups[(r['date'],r['market'])].append(r)
 variants={'twse_n1_tpex_n5ge3':lambda r:r['market']=='twse' and int(r.get('n1') or 0)>=1 or r['market']=='tpex' and int(r.get('n5') or 0)>=3,
 'twse_n1_tpex_n5ge2':lambda r:r['market']=='twse' and int(r.get('n1') or 0)>=1 or r['market']=='tpex' and int(r.get('n5') or 0)>=2,
 'twse_n1_tpex_n3ge2_or_n5ge3':lambda r:r['market']=='twse' and int(r.get('n1') or 0)>=1 or r['market']=='tpex' and (int(r.get('n3') or 0)>=2 or int(r.get('n5') or 0)>=3),
 'twse_n1_tpex_n3ge3_or_n5ge2':lambda r:r['market']=='twse' and int(r.get('n1') or 0)>=1 or r['market']=='tpex' and (int(r.get('n3') or 0)>=3 or int(r.get('n5') or 0)>=2)}
 output=[]; details=[]
 for v,rule in variants.items():
  for exclusion in ('none','30_calendar_days','same_target_month','both'):
   for month in ('2026-07','2026-08','2026-09','2026-10','ALL'):
    for market in ('twse','tpex'):
     hit=pred=act=0; days=0
     for day in dates:
      if month!='ALL' and day[:7]!=month:continue
      # Archived rows are snapshots of an older candidate universe. Do not infer unarchived candidates.
      pool=[]
      for r in groups[(day,market)]:
       if not rule(r):continue
       cutoff=r.get('cutoff') or (dt.date.fromisoformat(day)-dt.timedelta(days=1)).isoformat()
       earlier=[e for e in prior[r['ticker']] if e['date']<=cutoff]
       within30=any((dt.date.fromisoformat(day)-dt.date.fromisoformat(e['date'])).days<=30 for e in earlier)
       target=(dt.date.fromisoformat(day).replace(day=1)-dt.timedelta(days=1)).strftime('%Y-%m')
       same_month=any(e.get('month')==target for e in earlier)
       if exclusion in ('30_calendar_days','both') and within30:continue
       if exclusion in ('same_target_month','both') and same_month:continue
       pool.append(r)
      # Rule-only; deterministic tie-break by recent notice frequency then ticker.
      pool.sort(key=lambda r:(-int(r.get('n5') or 0),-int(r.get('n3') or 0),r['ticker']))
      pool=pool[:10]
      truth=actual[(day,market)]; found={r['ticker'] for r in pool}
      hit+=len(found&truth);pred+=len(found);act+=len(truth);days+=1
      if month=='ALL':details.append(dict(variant=v,exclusion=exclusion,date=day,market=market,picks=' '.join(sorted(found)),hits=' '.join(sorted(found&truth)),misses=' '.join(sorted(truth-found)),actual=len(truth)))
     output.append(dict(variant=v,exclusion=exclusion,month=month,market=market,days=days,**metric(hit,pred,act)))
 out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
 for name,items in [('summary.csv',output),('daily.csv',details)]:
  with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=items[0].keys());w.writeheader();w.writerows(items)
 (out/'README.txt').write_text('OFFLINE EXPLORATORY RULE SWEEP. Historical scores.csv contains prior archived candidate snapshots, not guaranteed full universe. Rules are applied to snapshots only. Oct 2026 partial through Oct 20. One-month exclusions compare publication date (30 calendar days) or same target monthly EPS period. Max 10 picks per market per day. Actuals count only attention filings. Do NOT merge with prospective metrics.\n',encoding='utf-8')
 print(json.dumps({'days':len(dates),'feature_rows':len(rows),'actual_events':len(events),'summary_rows':len(output),'out':str(out)},ensure_ascii=False))
if __name__=='__main__':main()
