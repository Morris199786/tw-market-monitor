"""Independent all-TWSE/TPEx pattern screen. Never touches AI account or sends push."""
import argparse,json,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor,as_completed
import update_daily_k as candles
from minervini_patterns import VERSION,RULES,clean_bars,trend,analyze,rs_ranks,limit_companies
ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo('Asia/Taipei')


def scan(root,as_of):
    data=root/'data';master=candles.read(data/'master.json',{}).get('stocks',{})
    universe={t:m for t,m in master.items() if len(t)==4 and t.isdigit() and not t.startswith('0') and m.get('market') in ('twse','tpex')}
    histories={};excluded={};basis={}
    for t in universe:
        p=data/'pattern_history'/(t+'.json')
        if not p.exists():p=data/'daily_k'/(t+'.json')
        doc=candles.read(p,{})
        try:bars=clean_bars(doc.get('bars',[]),as_of)
        except (ValueError,TypeError):excluded[t]='invalid_history';continue
        if not bars:excluded[t]='missing_history';continue
        if bars[-1]['time']!=as_of:excluded[t]='stale_history';continue
        if len(bars)<253:excluded[t]='short_history';continue
        # Price discontinuities inside the most recent base can mimic patterns.
        # Raw-price source cannot certify corporate actions: quarantine large gaps.
        if any(abs(bars[i]['close']/bars[i-1]['close']-1)>.25 for i in range(max(1,len(bars)-130),len(bars))):
            excluded[t]='price_discontinuity';continue
        histories[t]=bars;basis[t]=doc.get('price_basis','未還原日K')
    ranks=rs_ranks(histories);items=[];tt=0
    for t,bars in histories.items():
        checks=trend(bars,ranks.get(t));tt+=int(bool(checks) and all(x['passed'] for x in checks))
        for s in analyze(bars,ranks.get(t)):
            s.update(ticker=t,name=universe[t].get('name',t),market=universe[t]['market'],as_of=as_of,
                price=bars[-1]['close'],price_basis=basis[t],id=t+'-'+s['pattern'],chart_path='data/pattern_charts/'+t+'.json')
            for seg in s['segments']+s['zones']:
                seg['start_date']=bars[seg['start']]['time'];seg['end_date']=bars[seg['end']]['time']
            s['start_date']=bars[s['start']]['time'];s['end_date']=bars[s['end']]['time']
            s['sessions']=s['end']-s['start']+1
            items.append(s)
        if any(x['ticker']==t for x in items):
            candles.write(data/'pattern_charts'/(t+'.json'),dict(ticker=t,as_of=as_of,price_basis=basis[t],bars=bars))
    order={'breakout':0,'near':1,'unconfirmed':2,'forming':3,'failed':4}
    items.sort(key=lambda s:(order[s['status']],-s['rs'],abs(s['distance_pct']),s['ticker']))
    matched_stocks=len({i['ticker'] for i in items})
    items=limit_companies(items,10)
    counts={reason:sum(v==reason for v in excluded.values()) for reason in sorted(set(excluded.values()))}
    result=dict(schema=1,version=VERSION,as_of=as_of,generated_at=datetime.now(TZ).isoformat(timespec='seconds'),
        scope='全上市／上櫃普通股；不含興櫃、ETF、權證及特別股',
        coverage=dict(registered=len(universe),eligible=len(histories),excluded=counts,trend_pass=tt,
            max_companies=10,matched_stocks=matched_stocks,rs_population=len(ranks),candidate_stocks=len({i['ticker'] for i in items}),patterns=len(items),
            complete_history=len(histories)+counts.get('short_history',0)==len(universe)),
        price_note='沿用未還原OHLC；除權息、減資及分割可能影響辨識。近130日單日價格跳動超過25%先排除；不等於完整公司行動校正。',
        rules=RULES,items=items)
    candles.write(data/'pattern_screen.json',result)
    candles.write(data/'pattern_snapshots'/(as_of+'.json'),result)
    candles.write(data/'pattern_coverage.json',dict(as_of=as_of,excluded=excluded))
    print(json.dumps(result['coverage'],ensure_ascii=False),flush=True)
    return result


def collect(root,as_of,budget):
    """Reuse validated collector but use an independent cache and full registry.
    Bounded bootstraps resume missing histories first, never just the tech pool.
    """
    candles.ROOT=root;candles.DEST=root/'data/pattern_history';candles.TARGET_DATE=as_of
    now=datetime.now(TZ);master=candles.read(root/'data/master.json',{}).get('stocks',{})
    universe={t:m for t,m in master.items() if len(t)==4 and t.isdigit() and not t.startswith('0') and m.get('market') in ('twse','tpex')}
    if len(universe)<1500:raise ValueError('All-market registry unexpectedly small; abort rather than claim full coverage')
    official,errors=candles.fetch_official(now)
    if candles.TARGET_DATE!=as_of:raise ValueError('Official source target date differs from requested completed date')
    tasks=[]
    # Seed independent cache with valid existing historical bars; do not mutate daily_k.
    for t,m in universe.items():
        dest=candles.DEST/(t+'.json');doc=candles.read(dest,{})
        if not doc:
            old=candles.read(root/'data/daily_k'/(t+'.json'),{})
            if old:doc=old;candles.write(dest,doc)
        if doc.get('date')!=as_of or not doc.get('bars'):tasks.append((t,m,not bool(doc.get('bars'))))
    tasks.sort(key=lambda x:(not x[2],x[0]))
    results={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        fs={pool.submit(candles.fetch_with_market_status,t,m,now,official,errors):t for t,m,_ in tasks[:budget]}
        for f in as_completed(fs):
            t=fs[f]
            try:
                value,status,_=f.result();results[t]=status
            except Exception as e:results[t]=str(e)[:180]
            if len(results)%25==0:print(f'pattern history {len(results)}/{len(fs)}',flush=True)
    candles.write(root/'data/pattern_history_status.json',dict(as_of=as_of,requested=len(tasks),attempted=len(results),
        budget=budget,official_errors=errors,results=results))
    if tasks and not any(v in ('updated','cached') for v in results.values()):
        print('WARNING: source refresh returned no success; stale histories are excluded from screening',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--as-of')
    p.add_argument('--refresh',action='store_true');p.add_argument('--budget',type=int,default=300);a=p.parse_args()
    day=a.as_of or candles.read(a.root/'data/market_latest.json',{}).get('date')
    if not day:sys.exit('No completed market date')
    if a.refresh:collect(a.root,day,a.budget)
    scan(a.root,day)
