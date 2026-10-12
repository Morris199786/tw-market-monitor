#!/usr/bin/env python3
"""Read-only AI selection shadow test. Run from repository root.
python ai_shadow_backtest.py
Writes data/ai_shadow_test.json and data/ai_shadow_test.csv; does NOT alter live picks.
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path.cwd()
BACKTEST = ROOT / 'data/ai_backtest.json'
HISTORY = ROOT / 'data/history/market'
OUT_JSON = ROOT / 'data/ai_shadow_test.json'
OUT_CSV = ROOT / 'data/ai_shadow_test.csv'


def num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def pct(now, old):
    return (now / old - 1) * 100 if now and old and old > 0 else None


def load():
    if not BACKTEST.exists():
        raise SystemExit('Missing data/ai_backtest.json; run from repository root')
    d = json.loads(BACKTEST.read_text(encoding='utf-8'))
    snaps = {}
    for f in sorted(HISTORY.glob('*.json')):
        obj = json.loads(f.read_text(encoding='utf-8'))
        if isinstance(obj.get('stocks'), dict):
            snaps[obj.get('date', f.stem)] = obj['stocks']
    return d, snaps


def features(ticker, date, dates, snaps, index):
    i = index[date]
    def row(j):
        return snaps[dates[j]].get(ticker, {}) if j >= 0 else {}
    today = row(i)
    close = num(today.get('price'))
    if close is None:
        return None
    def back(k):
        return num(row(i-k).get('price')) if i >= k else None
    r5, r10, r20 = pct(close, back(5)), pct(close, back(10)), pct(close, back(20))
    prices = [num(row(j).get('price')) for j in range(max(0, i-19), i+1)]
    ma20 = mean(prices) if len(prices) == 20 and all(p is not None for p in prices) else None
    vol = num(today.get('volume'))
    prevvol = [num(row(j).get('volume')) for j in range(max(0, i-5), i)]
    vr = vol / mean(prevvol) if vol is not None and len(prevvol) == 5 and all(v is not None for v in prevvol) and mean(prevvol) > 0 else None
    market = today.get('market')
    # Same-market, equal-weight return of all stocks with valid data; no future data.
    def market_return(k):
        if i < k: return None
        old = snaps[dates[i-k]]
        vals = []
        for t, cur in snaps[date].items():
            if cur.get('market') != market: continue
            a = num(cur.get('price'))
            b = num(old.get(t, {}).get('price'))
            v = pct(a, b)
            if v is not None: vals.append(v)
        return mean(vals) if vals else None
    mr5 = market_return(5) if r5 is not None else None
    return {'r5':r5,'r10':r10,'r20':r20,'rs5':r5-mr5 if mr5 is not None else None,
            'ma20_gap':pct(close,ma20),'volume_ratio':vr}


def percentile(v, values):
    a = sorted(x for x in values if x is not None)
    if v is None or not a: return 50.0
    return 100 * (sum(x <= v for x in a) - 0.5) / len(a)


def summarize(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return {'samples':len(vals),'avg_pct':round(mean(vals),4) if vals else None,
            'median_pct':round(median(vals),4) if vals else None,
            'win_rate_pct':round(100*sum(v>0 for v in vals)/len(vals),2) if vals else None}


def main():
    data, snaps = load()
    dates = sorted(snaps)
    index = {d:i for i,d in enumerate(dates)}
    records = [r for r in data.get('records',[]) if r.get('selection_date') in index]
    groups = defaultdict(list)
    for r in records:
        groups[(r['selection_date'],r['market'])].append(r)
    output=[]
    for (date,market), picks in sorted(groups.items()):
        candidates=[]
        for r in picks:
            f = features(str(r['ticker']),date,dates,snaps,index)
            if f is None: continue
            candidates.append({**r,'features':f})
        if len(candidates)<5: continue
        # Relative ranks are computed ONLY among the original 20 candidates,
        # not the entire market. This tests re-ranking, not new-stock discovery.
        for r in candidates:
            f=r['features']
            rs=percentile(f['rs5'],[c['features']['rs5'] for c in candidates])
            trend=percentile(f['r10'],[c['features']['r10'] for c in candidates])
            vol=percentile(f['volume_ratio'],[c['features']['volume_ratio'] for c in candidates])
            base=percentile(num(r.get('score')),[num(c.get('score')) for c in candidates])
            gap=f['ma20_gap']
            penalty=(max(0,f['r5']-20)*2 if f['r5'] is not None else 0) + (max(0,gap-20)*2 if gap is not None else 0)
            r['shadow_score']=round(0.40*base+0.30*rs+0.20*trend+0.10*vol-penalty,4)
        original=sorted(candidates,key=lambda r:int(r.get('rank') or 999))[:5]
        shadow=sorted(candidates,key=lambda r:(-r['shadow_score'],str(r['ticker'])))[:5]
        for variant,selected in [('original_top5',original),('shadow_top5',shadow)]:
            for r in selected:
                output.append({'selection_date':date,'market':market,'variant':variant,
                    'ticker':r['ticker'],'name':r.get('name',''),'original_rank':r.get('rank'),
                    'original_score':r.get('score'),'shadow_score':r['shadow_score'],
                    'rs5':r['features']['rs5'],'r10':r['features']['r10'],
                    'volume_ratio':r['features']['volume_ratio'],
                    'baseline_5d':num(r.get('baseline_return_5d')) if r.get('baseline_status_5d')=='complete' else None,
                    'baseline_10d':num(r.get('baseline_return_10d')) if r.get('baseline_status_10d')=='complete' else None})
    summary={}
    for market in ('twse','tpex','all'):
        summary[market]={}
        for variant in ('original_top5','shadow_top5'):
            rows=[r for r in output if r['variant']==variant and (market=='all' or r['market']==market)]
            summary[market][variant]={'5d':summarize(rows,'baseline_5d'),'10d':summarize(rows,'baseline_10d')}
    # Paired comparison: only selection-date/market groups where both portfolios have
    # all 5 mature returns, avoiding bias from missing prices.
    paired=[]
    for (date,market) in sorted(groups):
        x=[r for r in output if r['selection_date']==date and r['market']==market]
        a=[r['baseline_5d'] for r in x if r['variant']=='original_top5']
        b=[r['baseline_5d'] for r in x if r['variant']=='shadow_top5']
        if len(a)==len(b)==5 and all(v is not None for v in a+b):
            paired.append({'date':date,'market':market,'original_avg_5d':round(mean(a),4),
                           'shadow_avg_5d':round(mean(b),4),'difference_pct_points':round(mean(b)-mean(a),4)})
    report={'note':'Research-only; no future data in features; candidate universe limited to original Top 20; not an out-of-sample test. Market-relative RS uses equal-weight stock universe proxy, not official index. Missing feature gets neutral rank. No transaction costs.',
            'source_updated_at':data.get('updated_at'),'config':{'base_score':0.40,'rs5':0.30,'return10':0.20,'volume_ratio':0.10,'overheat_penalty':'2 points per 1% above 20% 5d return or MA20 gap'},
            'summary':summary,'paired_5d':paired,'paired_mean_diff_pct_points':round(mean(x['difference_pct_points'] for x in paired),4) if paired else None,
            'rows':output}
    OUT_JSON.parent.mkdir(parents=True,exist_ok=True)
    OUT_JSON.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with OUT_CSV.open('w',newline='',encoding='utf-8-sig') as f:
        cols=['selection_date','market','variant','ticker','name','original_rank','original_score','shadow_score','rs5','r10','volume_ratio','baseline_5d','baseline_10d']
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(output)
    print(json.dumps({'summary':summary,'paired_mean_diff_pct_points':report['paired_mean_diff_pct_points'],'paired_groups':len(paired)},ensure_ascii=False,indent=2))
    print('Saved:',OUT_JSON,OUT_CSV)

if __name__=='__main__': main()
