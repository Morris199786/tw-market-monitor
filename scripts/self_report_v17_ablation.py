#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Private TWSE V17 ablation; chronological training; never writes production files."""
import argparse,csv,collections,datetime as dt,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import self_report_predict as v17

VARIANTS=('V17_original','V17_exclude_clause_10_13','V17_exclude_30_days','V17_both','A_rule_reference')
def readcsv(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(p,rows):
 if not rows:return
 with open(p,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--scores',default='data/self_report_v17_archive/scores.csv')
 ap.add_argument('--events',default='data/self_report_v17_archive/events.csv')
 ap.add_argument('--rule-dir',default='private_rule_backtest_v2')
 ap.add_argument('--out',default='private_v17_ablation')
 a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 events=readcsv(a.events);truth=collections.defaultdict(set);prior=collections.defaultdict(list)
 for e in events:
  prior[e['ticker']].append(e)
  if e.get('kind')=='attention':truth[(e['date'],e['market'])].add(e['ticker'])
 for x in prior.values():x.sort(key=lambda e:e['date'])
 rule=readcsv(Path(a.rule_dir)/'daily.csv')
 rule_days={r['date']:r for r in rule if r['market']=='twse' and r['variant']=='listed_n1_otc_n5ge3' and r['exclusion']=='30_calendar_days'}
 excluded=readcsv(Path(a.rule_dir)/'excluded_clause_10_13.csv')
 excluded_days={(r['date'],r['ticker']) for r in excluded if r['market']=='twse'}
 rows_by_day=collections.defaultdict(list)
 for r in readcsv(a.scores):
  if not '2026-07-01'<=r['date']<='2026-10-20' or r['market']!='twse':continue
  for k in ('label','recent','gap','reason6','n1','n3','n5','n10','n20'):
   r[k]=int(r.get(k) or 0)
  r['reason6_flag']=int(r.get('reason6_flag') or (r['reason6']>0))
  r['days_since_report']=int(r['days_since_report']) if r.get('days_since_report') else None
  r['market_pattern']=v17.bucket(r)
  r['notice_intensity']='high' if r['n5']>=3 else 'mid' if r['n5']==2 else 'low'
  r['clause_data_available']=int(bool(str(r.get('clause_last_known') or '')))
  r['rule_eligible']=v17.eligible(r)
  r['label']=int(r['ticker'] in truth[(r['date'],'twse')])
  rows_by_day[r['date']].append(r)
 training=[];details=[];missing_clause=0
 for day,rows in sorted(rows_by_day.items()):
  ready=len({r['date'] for r in training})>=5 and sum(r['label'] for r in training)>=15
  rr=rule_days.get(day)
  if not ready or rr is None or str(rr['valid']).lower() not in ('true','1'):
   training.extend(rows);continue
  cutoff=rows[0].get('cutoff') or rr.get('cutoff') or (dt.date.fromisoformat(day)-dt.timedelta(days=1)).isoformat()
  # V17 fit remains exactly the same for all four variants. Only candidate gates change.
  scored=v17.score_v17(rows,training)
  base=[r for r in scored if r['market']=='twse' and r.get('rule_eligible') and r['probability']>=.10]
  cutoff_date=dt.date.fromisoformat(day)
  def recent30(ticker):
   return any(e['date']<=cutoff and 0<=(cutoff_date-dt.date.fromisoformat(e['date'])).days<=30 for e in prior[ticker])
  def clause_excluded(r):
   # Restrict to last-session TWSE notices. Full exclusion requires the complete notice universe;
   # archived scores cannot reliably reconstruct every older clause count.
   return (cutoff,r['ticker']) in excluded_days and r['n1']>=1
  for variant in VARIANTS[:-1]:
   chosen=base
   if variant in ('V17_exclude_clause_10_13','V17_both'):
    chosen=[r for r in chosen if not clause_excluded(r)]
   if variant in ('V17_exclude_30_days','V17_both'):
    chosen=[r for r in chosen if not recent30(r['ticker'])]
   chosen=sorted(chosen,key=lambda r:(-r['probability'],r['ticker']))[:10]
   picks={r['ticker'] for r in chosen};actual=truth[(day,'twse')]
   details.append(dict(date=day,month=day[:7],strategy=variant,market='twse',predictions=len(picks),hits=len(picks&actual),actuals=len(actual),picks=' '.join(sorted(picks)),hit_tickers=' '.join(sorted(picks&actual))))
  picks=set(rr['picks'].split());actual=truth[(day,'twse')]
  details.append(dict(date=day,month=day[:7],strategy='A_rule_reference',market='twse',predictions=len(picks),hits=len(picks&actual),actuals=len(actual),picks=' '.join(sorted(picks)),hit_tickers=' '.join(sorted(picks&actual))))
  training.extend(rows)
 summary=[]
 for variant in VARIANTS:
  for month in ('2026-07','2026-08','2026-09','2026-10','ALL'):
   sub=[r for r in details if r['strategy']==variant and (month=='ALL' or r['month']==month)]
   h=sum(r['hits'] for r in sub);p=sum(r['predictions'] for r in sub);actual=sum(r['actuals'] for r in sub)
   summary.append(dict(strategy=variant,month=month,days=len(sub),hits=h,predictions=p,actuals=actual,precision=round(h/p,6) if p else None,recall=round(h/actual,6) if actual else None))
 writecsv(out/'comparison.csv',summary);writecsv(out/'comparison_daily.csv',details)
 audit={'scope':'PRIVATE exploratory TWSE only; original V17 unchanged','valid_days':len([x for x in details if x['strategy']=='V17_original']),
 'clauses':'Excluded notices are from official source audit. This candidate-gate ablation removes a candidate if its previous-session notice was excluded; cannot fully rebuild V17 feature vectors after removing 10-13 clauses.',
 'limitations':['Historical V17 archived scores.csv is a partial candidate snapshot; NOT a full-universe or official A/B comparison.','V17 training uses archived features, and the four variants share the same fitted model; training features are NOT recomputed after removing notices.','Clause-only filtering depends on the rule script excluded_clause_10_13.csv; verify notice parser semantics for mixed clauses.','30-day prior event history must be complete; July is excluded when June events are unverified.','The 30-day filter uses all self-report events known strictly before prediction date.','Same 54 or fewer dates must be checked in comparison.csv; no modifications to production V17.']}
 (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 for x in summary:
  if x['month']=='ALL':print('ABLATION_RESULT',json.dumps(x,ensure_ascii=False))
if __name__=='__main__':main()
