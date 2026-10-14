#!/usr/bin/env python3
"""Isolated OHLCV backfill for AI research. Never touches data/daily_k."""
import json, math, os, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'data/ai_backtest_k'
TZ=ZoneInfo('Asia/Taipei')

def load(p):
    try: return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}

def valid(b):
    try:
        o,h,l,c,v=(float(b[k]) for k in ('open','high','low','close','volume'))
        eps=max(.0001,h*1e-6)
        return all(math.isfinite(x) for x in (o,h,l,c,v)) and l>0 and v>=0 and l-eps<=min(o,c)<=max(o,c)<=h+eps
    except (KeyError,TypeError,ValueError): return False

def fetch(ticker,market):
    symbol=ticker+('.TW' if market=='twse' else '.TWO')
    path=DEST/(ticker+'.json')
    old=load(path)
    previous={str(b['time']):b for b in old.get('bars',[]) if isinstance(b,dict) and b.get('time') and valid(b)}
    err='no source'
    for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
        for attempt in range(2):
            try:
                r=requests.get(f'https://{host}/v8/finance/chart/{symbol}',params={'range':'2y','interval':'1d','includeAdjustedClose':'false'},headers={'User-Agent':'Mozilla/5.0'},timeout=(8,25))
                r.raise_for_status()
                obj=r.json()['chart']['result'][0]
                if obj['meta']['symbol']!=symbol: raise ValueError('symbol mismatch')
                q=obj['indicators']['quote'][0]
                new={}
                for i,ts in enumerate(obj.get('timestamp') or []):
                    d=datetime.fromtimestamp(ts,TZ).date().isoformat()
                    try: b={'time':d,**{k:q[k][i] for k in ('open','high','low','close','volume')}}
                    except (IndexError,KeyError): continue
                    if valid(b): new[d]=b
                if not new: raise ValueError('no valid bars')
                previous.update(new)
                bars=[previous[k] for k in sorted(previous)]
                data={'ticker':ticker,'market':market,'source':'Yahoo Finance unadjusted daily OHLCV','updated_at':datetime.now(TZ).isoformat(timespec='seconds'),'bars':bars}
                path.parent.mkdir(parents=True,exist_ok=True)
                tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8');tmp.replace(path)
                return ticker,len(bars),None
            except Exception as e:
                err=f'{type(e).__name__}: {str(e)[:100]}'
                if attempt==0: time.sleep(.3)
    return ticker,len(previous),err

def main():
    master=load(ROOT/'data/master.json').get('stocks',{})
    # All technology ordinary stocks in historical shadow-universe; no website data overwritten.
    import sys
    sys.path.insert(0,str(ROOT))
    from ai_shadow_backtest import tech_universe
    wanted=sorted(t for t in tech_universe(master) if t in master and master[t].get('market') in ('twse','tpex'))
    if not wanted: raise RuntimeError('AI universe empty')
    workers=min(6,max(1,int(os.getenv('AI_K_WORKERS','4'))))
    outcomes=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks=[pool.submit(fetch,t,master[t]['market']) for t in wanted]
        for f in as_completed(tasks): outcomes.append(f.result())
    failed={t:err for t,n,err in outcomes if err}
    manifest={'updated_at':datetime.now(TZ).isoformat(timespec='seconds'),'requested':len(wanted),'with_bars':sum(n>0 for _,n,_ in outcomes),'fetched_ok':sum(err is None for _,_,err in outcomes),'failed':failed}
    DEST.mkdir(parents=True,exist_ok=True)
    (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('AI K backfill:',manifest['fetched_ok'],'/',len(wanted),'success; with historical bars:',manifest['with_bars'])
    if manifest['with_bars']==0: raise RuntimeError('No historical AI candles available')

if __name__=='__main__':main()
