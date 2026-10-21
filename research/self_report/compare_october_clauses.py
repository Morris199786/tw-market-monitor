#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fair historical replay: frozen V12 baseline versus clause reranker.
No internet, no API credits, no production file changes.
Each challenger day retains exactly the baseline's TWSE slots and OTC names.
Training uses strictly earlier dates; historical filing labels are rebuilt.
"""
import argparse, csv, importlib.util, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

BASE=['n1','n3','n5','n10','n20','gap','days_since_report','reason6']
CLAUSE=[f'clause_{i}_last' for i in range(1,13)]+['clause_last_count','clause_distinct_20d']

def load_module(path):
    spec=importlib.util.spec_from_file_location('frozen_baseline',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def get_metrics(picks, actual):
    n=len(picks);h=sum(int(x['hit']) for x in picks)
    return dict(picks=n,hits=h,precision=round(h/n,6) if n else None,
                recall=round(h/actual,6) if actual else None,actual=actual,
                f1=round(2*h/(n+actual),6) if n+actual else None)

def run(a):
    baseline=load_module(a.baseline_script)
    version=getattr(baseline,'VERSION','unknown')
    if not a.allow_other_version and 'v12' not in version.lower():
        raise RuntimeError(f'Refusing invalid V12 baseline: {version}')
    df=pd.read_csv(a.scores,dtype={'ticker':str},encoding='utf-8-sig',low_memory=False)
    ev=pd.read_csv(a.events,dtype={'ticker':str},encoding='utf-8-sig')
    required={'date','cutoff','ticker','market','n1','n3','n5','n10','n20','gap','reason6','days_since_report'}|set(CLAUSE)
    missing=required-set(df.columns)
    if missing:raise ValueError('Missing historical columns: '+','.join(sorted(missing)))
    if df.duplicated(['date','market','ticker']).any():raise ValueError('Duplicated candidates')
    keys=set(zip(ev.loc[ev.kind=='attention','date'],ev.loc[ev.kind=='attention','market'],ev.loc[ev.kind=='attention','ticker']))
    df=df.sort_values(['date','market','ticker']).reset_index(drop=True)
    df['label']=[int((d,m,t) in keys) for d,m,t in zip(df.date,df.market,df.ticker)]
    # Reject missing historical clause data on candidate TWSE rows rather than invent zeroes.
    listed=df[df.market=='twse']
    if listed['clause_last_known'].isna().any():raise ValueError('TWSE clause data missing')
    if int(pd.to_numeric(listed.clause_last_known,errors='coerce').fillna(0).sum())==0:
        raise ValueError('No actual historical clause matches: refusing backtest')
    # Ensure no future cutoff: prediction day must be after the snapshot date.
    if not (df.cutoff<df.date).all():raise ValueError('Future leakage: cutoff >= target date')
    for c in BASE+CLAUSE:
        df[c]=pd.to_numeric(df[c],errors='coerce')
    x=df[BASE+CLAUSE].fillna({'days_since_report':999}).fillna(0).clip(-1,999)
    all_days=sorted(df.date.unique());out=[];day_rows=[]
    for day in all_days:
        if day<a.start or day>a.end:continue
        prior=df[df.date<min(day,a.train_end)] if a.train_end else df[df.date<day];today=df[df.date==day]
        if len(set(prior.date))<5 or int(prior.label.sum())<15:continue
        # Exactly replay the frozen production scoring/selection code, as of the day.
        history=[]
        for r in prior.to_dict('records'):
            r['n1']=int(r['n1']);r['n3']=int(r['n3']);r['n5']=int(r['n5']);r['n20']=int(r['n20'])
            r['rule_eligible']=bool(baseline.eligible(r))
            r['market_pattern']=baseline.bucket(r)
            r['notice_intensity']='high' if r['n5']>=3 else 'mid' if r['n5']==2 else 'low'
            r['reason6_flag']=int(r.get('reason6') or 0)>0
            r['cooldown']=str(r.get('cooldown') or 'never')
            r['clause_data_available']=0  # Frozen baseline must never see future research clauses.
            history.append(r)
        model=baseline.Model(history)
        scored=[]
        for r in today.to_dict('records'):
            for c in ['n1','n3','n5','n20']:r[c]=int(r[c])
            r['rule_eligible']=bool(baseline.eligible(r))
            r['market_pattern']=baseline.bucket(r)
            r['notice_intensity']='high' if r['n5']>=3 else 'mid' if r['n5']==2 else 'low'
            r['reason6_flag']=int(r.get('reason6') or 0)>0
            r['cooldown']=str(r.get('cooldown') or 'never')
            r['clause_data_available']=0
            p,s=model.predict(r);r['probability']=p;r['cell_samples']=s
            scored.append(r)
        selected=baseline.choose(scored)
        base_twse=[r for r in selected if r['market']=='twse']
        otc=[r for r in selected if r['market']=='tpex']
        n=len(base_twse)
        if n:
            train=df[(df.date<min(day,a.train_end))&(df.market=='twse')] if a.train_end else df[(df.date<day)&(df.market=='twse')]
            test=df[(df.date==day)&(df.market=='twse')]
            # New clause model: fit only prior days, same fixed TWSE slot count.
            if len(train)>30 and train.label.nunique()==2:
                clf=make_pipeline(StandardScaler(),LogisticRegression(C=0.03,max_iter=600,random_state=0))
                clf.fit(x.loc[train.index,BASE+CLAUSE],train.label)
                eligible_idx=[i for i in test.index if baseline.eligible(scored[list(today.index).index(i)])]
                if len(eligible_idx)<n:raise ValueError(f'{day}: insufficient common eligible TWSE candidates')
                prob=clf.predict_proba(x.loc[eligible_idx,BASE+CLAUSE])[:,1]
                challenger=df.loc[eligible_idx].copy();challenger['new_probability']=prob
                chosen=challenger.sort_values(['new_probability','ticker'],ascending=[False,True]).head(n)
                new_twse=chosen.to_dict('records')
            else:new_twse=base_twse
        else:new_twse=[]
        for arm,rs in [('v12',selected),('v12_plus_clauses',new_twse+otc)]:
            for r in rs:
                out.append(dict(model=arm,date=day,market=r['market'],ticker=r['ticker'],name=r.get('name',''),
                                hit=int(r['label']),clause_3=int(r.get('clause_3_last') or 0),
                                clause_8=int(r.get('clause_8_last') or 0),clause_11=int(r.get('clause_11_last') or 0)))
        day_rows.append(dict(date=day,baseline_twse=n,challenger_twse=len(new_twse),otc=len(otc)))
    if not day_rows:raise ValueError('No evaluated dates; check --start, --end and warmup')
    if a.start >= '2026-10-01' and len(day_rows) < 10:
        raise ValueError(f'Incomplete October coverage: only {len(day_rows)} trading days; refusing partial score')
    picks=pd.DataFrame(out)
    # Official recall denominator: all attention-triggered reports on evaluated days, even outside candidates.
    evaluated={x['date'] for x in day_rows}
    report= {'baseline_version':version,'date_range':[min(evaluated),max(evaluated)],'evaluated_days':len(evaluated),
             'source':'historical candidate snapshots + actual attention-only event audit',
             'fairness':'identical dates, total slots, TWSE slots and OTC names; challenger changes TWSE ranking only',
             'markets':{},'warnings':['Historical candidate reconstruction; verify coverage and source completeness before trusting Oct result',
                'Prior candidate snapshots cannot recover candidates never archived',
                'Model hyperparameters must not be tuned on the independent holdout period']}
    for market in ['twse','tpex','all']:
        actual=len({(d,m,t) for d,m,t in keys if d in evaluated and (market=='all' or m==market)})
        report['markets'][market]={}
        for arm in ['v12','v12_plus_clauses']:
            sub=picks[(picks.model==arm)&((picks.market==market) if market!='all' else True)]
            report['markets'][market][arm]=get_metrics(sub.to_dict('records'),actual)
    for day,g in picks.groupby('date'):
        assert g[g.model=='v12'].shape[0]==g[g.model=='v12_plus_clauses'].shape[0]
        for market in ['twse','tpex']:
            a1=g[(g.model=='v12')&(g.market==market)]
            a2=g[(g.model=='v12_plus_clauses')&(g.market==market)]
            assert len(a1)==len(a2),f'{day} {market} unequal slots'
            if market=='tpex':assert set(a1.ticker)==set(a2.ticker),f'{day} OTC changed'
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    picks.to_csv(dest/'v12_vs_clauses_picks.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(day_rows).to_csv(dest/'daily_slots.csv',index=False,encoding='utf-8-sig')
    (dest/'v12_vs_clauses_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--scores',required=True);p.add_argument('--events',required=True)
    p.add_argument('--baseline-script',required=True);p.add_argument('--out',default='comparison_output')
    p.add_argument('--start',default='2026-10-02');p.add_argument('--end',default='2026-10-20')
    p.add_argument('--train-end',default='2026-10-01',help='Freeze both model training sets before this date')
    p.add_argument('--allow-other-version',action='store_true',help='Smoke test only; output is NOT V12')
    run(p.parse_args())
