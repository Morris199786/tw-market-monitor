#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent rule A/B/C vs V17 archived-feature walk-forward comparison.
No changes to production data, website, ledger, or Telegram.
"""
import argparse,csv,collections,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import self_report_predict as v17

def readcsv(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(p,rows):
 with open(p,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def metric(h,p,a):return dict(hits=h,predictions=p,actuals=a,precision=round(h/p,6) if p else None,recall=round(h/a,6) if a else None)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rule-dir',default='private_rule_backtest_v2');ap.add_argument('--scores',default='data/self_report_v17_archive/scores.csv');ap.add_argument('--events',default='data/self_report_v17_archive/events.csv');ap.add_argument('--out',default='private_rule_v17_compare');args=ap.parse_args()
 out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
 daily=readcsv(Path(args.rule_dir)/'daily.csv');aud=json.loads((Path(args.rule_dir)/'audit.json').read_text())
 events=readcsv(args.events)
 truths=collections.defaultdict(set)
 for e in events:
  if e.get('kind')=='attention':truths[(e['date'],e['market'])].add(e['ticker'])
 days=collections.defaultdict(list)
 for r in readcsv(args.scores):
  if not '2026-07-01'<=r['date']<='2026-10-20':continue
  for key in ('label','recent','gap','reason6','n1','n3','n5','n10','n20'):
   r[key]=int(r.get(key) or 0)
  r['reason6_flag']=int(r.get('reason6_flag') or (r['reason6']>0))
  r['days_since_report']=int(r['days_since_report']) if r.get('days_since_report') else None
  r['market_pattern']=v17.bucket(r)
  r['notice_intensity']='high' if r['n5']>=3 else 'mid' if r['n5']==2 else 'low'
  r['clause_data_available']=int('clause_last_known' in r and str(r.get('clause_last_known'))!='')
  r['rule_eligible']=v17.eligible(r)
  r['label']=int(r['ticker'] in truths[(r['date'],r['market'])])
  days[r['date']].append(r)
 # Historical snapshot replay uses the archived V17 features and earlier-day labels only.
 training=[];v17_daily={};ready_days=set()
 for day,rows in sorted(days.items()):
  enough=len({r['date'] for r in training})>=5 and sum(r['label'] for r in training)>=15
  if enough:
   picked=v17.choose(v17.score_v17(rows,training))
   for market in ('twse','tpex'):
    selected={r['ticker'] for r in picked if r['market']==market}
    truth=truths[(day,market)]
    v17_daily[(day,market)]=dict(date=day,market=market,predictions=len(selected),hits=len(selected&truth),actuals=len(truth),picks=' '.join(sorted(selected)))
   ready_days.add(day)
  training.extend(rows)
 # The same set of valid dates is required for fair comparisons.
 strategies={'A上市_注意1次_排除30日':('listed_n1_otc_n5ge3','twse'),
             'B上櫃_5日注意2次_排除30日':('listed_n1_otc_n5ge2','tpex'),
             'C上櫃_5日注意3次_排除30日':('listed_n1_otc_n5ge3','tpex')}
 result=[];detail=[]
 for title,(variant,market) in strategies.items():
  subset=[r for r in daily if r['variant']==variant and r['market']==market and r['exclusion']=='30_calendar_days']
  for month in ('2026-07','2026-08','2026-09','2026-10','ALL'):
   use=[r for r in subset if (month=='ALL' or r['month']==month) and r['valid'] in ('True','true','1') and (r['date'],market) in v17_daily]
   excluded=sum((month=='ALL' or r['month']==month) and r['valid'] not in ('True','true','1') for r in subset)
   for name in (title,'V17_同日期_封存特徵重跑'):
    if name==title:
     h=sum(int(r['hits']) for r in use);p=sum(int(r['predictions']) for r in use);a=sum(int(r['actuals']) for r in use)
    else:
     h=sum(v17_daily[(r['date'],market)]['hits'] for r in use);p=sum(v17_daily[(r['date'],market)]['predictions'] for r in use);a=sum(v17_daily[(r['date'],market)]['actuals'] for r in use)
    result.append(dict(strategy_group=title,strategy=name,market=market,month=month,days=len(use),excluded_incomplete_days=excluded,**metric(h,p,a)))
   for r in use:
    ref=v17_daily[(r['date'],market)]
    detail.append(dict(group=title,date=r['date'],market=market,actuals=r['actuals'],rule_picks=r['picks'],rule_hits=r['hits'],v17_picks=ref['picks'],v17_hits=ref['hits']))
 writecsv(out/'comparison.csv',result)
 if detail:writecsv(out/'comparison_daily.csv',detail)
 info=dict(rule_audit=aud,comparison='same date and archived MOPS attention labels',limitations=[
  'V17 comparison replays archived historical feature snapshots, not a fully rebuilt V17 candidate universe.',
  'V17 has a chronological training warmup: only dates where V17 is ready are compared.',
  'Rule July cooldown days are excluded if verified June self-report events were not provided.',
  'Rules and V17 have different candidate construction: comparisons are exploratory, not a prospective A/B test.',
  'Missing historical MOPS actual events can bias both precision and recall.',
  'Neither strategy modifies the official V17 or website.'])
 (out/'audit.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
 for r in result:
  if r['month']=='ALL':print('COMPARE_RESULT',json.dumps(r,ensure_ascii=False))
if __name__=='__main__':main()
