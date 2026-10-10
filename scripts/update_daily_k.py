"""Daily OHLCV for heatmap constituents; isolated from institutional/heatmap data."""
import json, math, time, os
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo('Asia/Taipei')
DEST=ROOT/'data/daily_k'

def read(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError): return default

def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8');temp.replace(path)

def parse_chart(payload,symbol,now,gaps=None):
    chart=payload.get('chart',{})
    if chart.get('error'): raise ValueError(str(chart['error'])[:160])
    result=chart.get('result') or []
    if len(result)!=1: raise ValueError('missing chart result')
    r=result[0]
    if r.get('meta',{}).get('symbol')!=symbol: raise ValueError('ticker mismatch')
    timestamps=r.get('timestamp') or []
    quote=(r.get('indicators',{}).get('quote') or [{}])[0]
    rows={}; rejected=[]
    for i,ts in enumerate(timestamps):
        date=datetime.fromtimestamp(ts,TZ).date()
        if date>now.date() or (date==now.date() and (now.hour,now.minute)<(14,0)): continue
        values=[]
        for key in ['open','high','low','close','volume']:
            array=quote.get(key) or [];v=array[i] if i<len(array) else None
            values.append(float(v) if isinstance(v,(int,float)) and math.isfinite(v) else None)
        o,h,l,c,v=values
        if all(x is None for x in values):
            if gaps is not None: gaps.append(date.isoformat())
            continue
        if any(x is None for x in values) or min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:
            rejected.append(date.isoformat());continue
        rows[date.isoformat()]={'time':date.isoformat(),'open':round(o,4),'high':round(h,4),'low':round(l,4),'close':round(c,4),'volume':int(v)}
    bars=[rows[k] for k in sorted(rows)]
    if not bars: raise ValueError('no valid completed candles')
    # Reject partial broken history, retaining last valid file instead of bridging missing data
    if rejected: raise ValueError('incomplete OHLCV: '+','.join(rejected[-5:]))
    return bars

def fetch_one(ticker,meta,now):
    symbol=ticker+('.TW' if meta['market']=='twse' else '.TWO')
    path=DEST/(ticker+'.json');old=read(path,{})
    # One successful fetch per Taiwan calendar day; manual retries only retry failures
    if old.get('fetched_on')==now.date().isoformat() and old.get('bars'):
        fetched=datetime.fromisoformat(old['updated_at'])
        if fetched.hour>=14 or now.hour<14: return old,'cached'
    error=None
    for attempt in range(3):
        try:
            response=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/'+symbol,
                params={'range':'2y','interval':'1d','events':'splits,div','includeAdjustedClose':'false'},
                headers={'User-Agent':'Mozilla/5.0'},timeout=(10,35))
            response.raise_for_status();gaps=[];bars=parse_chart(response.json(),symbol,now,gaps)
            value={'ticker':ticker,'name':meta['name'],'market':meta['market'],'source':'Yahoo Finance',
                'price_basis':'Yahoo OHLC/Close（非 Adj Close；來源可能調整拆股）',
                'volume_unit':'shares','missing_dates':gaps,'updated_at':now.isoformat(timespec='seconds'),
                'fetched_on':now.date().isoformat(),'date':bars[-1]['time'],'bars':bars}
            if old.get('date','')>value['date']: raise ValueError('source date regressed')
            write(path,value);return value,'updated'
        except Exception as exc:
            error=f'{type(exc).__name__}: {exc}'[:180]
            if attempt<2: time.sleep(2*(attempt+1))
    return old,error

def main():
    now=datetime.now(TZ)
    sectors=read(ROOT/'data/sectors.json',{}).get('sectors',[])
    master=read(ROOT/'data/master.json',{}).get('stocks',{})
    tickers={str(x.get('ticker','')) for sector in sectors for x in sector.get('stocks',[])}
    if not tickers: raise RuntimeError('empty heatmap universe')
    universe={}; errors={}
    for ticker in sorted(tickers):
        meta=master.get(ticker,{})
        if not ticker.isdigit() or len(ticker)!=4 or meta.get('market') not in ('twse','tpex'):
            errors[ticker]='missing valid market identity';continue
        universe[ticker]=meta
    status={};success=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(fetch_one,t,m,now):t for t,m in universe.items()}
        for future in as_completed(tasks):
            ticker=tasks[future]
            try: value,result=future.result()
            except Exception as exc: value={};result=type(exc).__name__
            ok=result in ('updated','cached')
            if ok: success+=1
            else: errors[ticker]=result
            status[ticker]={'available':bool(value.get('bars')),'refresh_ok':ok,'date':value.get('date'),'bars':len(value.get('bars',[]))}
    write(DEST/'manifest.json',{'updated_at':now.isoformat(timespec='seconds'),'source':'Yahoo Finance','stocks':status,'errors':errors,'success':success,'requested':len(tickers)})
    print(f'daily K: {success}/{len(tickers)} refreshed; {len(errors)} errors')
    if errors: raise RuntimeError('Some daily K sources failed; valid existing data retained; see manifest.json')
if __name__=='__main__': main()
