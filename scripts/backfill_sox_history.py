#!/usr/bin/env python3
"""SOX price index archive. Run from repository root; no API keys required."""
import argparse, csv, io, json, math, os, statistics, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

START=date(2008,1,1)
NY=ZoneInfo('America/New_York')
TW=ZoneInfo('Asia/Taipei')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/history/sox-history.json'
FRED='https://fred.stlouisfed.org/graph/fredgraph.csv'

def retry(fn):
    for attempt in range(3):
        try: return fn()
        except Exception:
            if attempt==2: raise
            time.sleep(3*(attempt+1))

def positive(x):
    try:
        v=float(x)
        return round(v,6) if math.isfinite(v) and v>0 else None
    except (TypeError, ValueError): return None

def fetch_yahoo(start,end):
    import yfinance as yf
    df=yf.Ticker('^SOX').history(start=start.isoformat(),end=(end+timedelta(days=1)).isoformat(),interval='1d',auto_adjust=False,actions=False,raise_errors=True,timeout=30)
    if df.empty: raise RuntimeError('Yahoo returned no rows')
    out={}
    for ts,row in df.iterrows():
        d=ts.date().isoformat()
        vals={k:positive(row.get(k.title())) for k in ('open','high','low','close')}
        if vals['close'] is not None: out[d]=vals
    return out

def fetch_fred(start,end):
    import requests
    r=requests.get(FRED,params={'id':'NASDAQSOX','cosd':start.isoformat(),'coed':end.isoformat()},timeout=60)
    r.raise_for_status()
    rd=csv.DictReader(io.StringIO(r.text.lstrip('\ufeff')))
    if not rd.fieldnames or 'NASDAQSOX' not in rd.fieldnames: raise ValueError('Invalid FRED CSV')
    out={}
    for row in rd:
        d=row.get('observation_date') or row.get('DATE')
        v=positive(row['NASDAQSOX'])
        if d and v is not None: out[date.fromisoformat(d).isoformat()]=v
    if not out: raise ValueError('Empty FRED series')
    return out

def calendar(start,end):
    import pandas_market_calendars as mcal
    sched=mcal.get_calendar('NASDAQ').schedule(start_date=start,end_date=end)
    now=datetime.now(timezone.utc)
    return {d.date().isoformat(): row['market_close'].to_pydatetime() for d,row in sched.iterrows() if row['market_close'].to_pydatetime()<=now}

def merge(expected,yahoo,fred,old):
    rows=[]; missing=[]; conflicts=[]; incomplete=[]
    for d,closed in sorted(expected.items()):
        y=yahoo.get(d,{}); f=fred.get(d); o=old.get(d,{})
        yc=y.get('close')
        if f is not None and yc is not None and abs(yc/f-1)>.001:
            conflicts.append({'date':d,'yahoo':yc,'fred':f})
        close=yc if yc is not None else f if f is not None else positive(o.get('close'))
        if close is None: missing.append(d); continue
        source='yahoo' if yc is not None else 'fred' if f is not None else o.get('close_source','archive')
        # Do not fabricate OHLC or mix bars whose closing prices disagree.
        bar=y if yc is not None else o if positive(o.get('close')) is not None and abs(o['close']/close-1)<=.001 else {}
        prices={k:positive(bar.get(k)) for k in ('open','high','low')}
        if all(v is not None for v in prices.values()):
            if prices['high']<max(prices['open'],close)-.02 or prices['low']>min(prices['open'],close)+.02 or prices['low']>prices['high']:
                prices=dict(open=None,high=None,low=None)
        if any(v is None for v in prices.values()): incomplete.append(d)
        rows.append(dict(date=d,available_at=closed.astimezone(TW).isoformat(),**prices,close=close,close_source=source,fred_close=f,close_verified=(f is not None and abs(close/f-1)<=.001)))
    return rows,missing,conflicts,incomplete

def indicators(rows,expected):
    lookup={r['date']:r for r in rows}; days=sorted(expected)
    def rnd(x): return round(x,6)
    for i,d in enumerate(days):
        r=lookup.get(d)
        if r is None: continue
        c=r['close']
        for n in (1,3,5,10,20):
            w=days[i-n:i+1] if i>=n else []
            r[f'return{n}']=rnd(100*(c/lookup[w[0]]['close']-1)) if w and all(k in lookup for k in w) else None
        for n in (20,60):
            w=days[i-n+1:i+1] if i>=n-1 else []
            vals=[lookup[k]['close'] for k in w if k in lookup]
            ma=statistics.mean(vals) if len(vals)==n else None
            r[f'ma{n}']=rnd(ma) if ma else None
            r[f'bias{n}']=rnd(100*(c/ma-1)) if ma else None
            r[f'drawdown{n}']=rnd(100*(c/max(vals)-1)) if ma else None
        w=days[i-20:i+1] if i>=20 else []
        vals=[lookup[k]['close'] for k in w if k in lookup]
        r['volatility20']=rnd(100*math.sqrt(252)*statistics.stdev([math.log(b/a) for a,b in zip(vals,vals[1:])])) if len(vals)==21 else None

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,default=OUT); p.add_argument('--end',type=date.fromisoformat,default=datetime.now(NY).date()); p.add_argument('--strict-ohlc',action='store_true'); a=p.parse_args()
    if a.end<START or a.end>datetime.now(NY).date(): p.error('Invalid end date')
    expected=calendar(START,a.end)
    if not expected: raise RuntimeError('Empty trading calendar')
    old={}
    if a.output.exists():
        payload=json.loads(a.output.read_text(encoding='utf-8'))
        old={r['date']:r for r in payload['rows']}
        if max(old,default='')>max(expected): raise RuntimeError('Refusing to truncate existing archive')
    errors={}; sources={}
    for name,fn in [('yahoo',fetch_yahoo),('fred',fetch_fred)]:
        try: sources[name]=retry(lambda:fn(START,a.end))
        except Exception as e: errors[name]=str(e); sources[name]={}
    if not any(sources.values()): raise RuntimeError(f'Both sources failed: {errors}')
    rows,missing,conflicts,incomplete=merge(expected,sources['yahoo'],sources['fred'],old)
    indicators(rows,expected)
    quality=dict(expected_sessions=len(expected),actual_sessions=len(rows),missing_dates=missing,close_conflicts=conflicts,incomplete_ohlc_dates=incomplete,source_errors=errors,fred_verified=sum(r['close_verified'] for r in rows),source_counts={k:len(v) for k,v in sources.items()})
    print(json.dumps(quality,ensure_ascii=False))
    if missing or conflicts or (a.strict_ohlc and incomplete): raise RuntimeError('Coverage/price validation failed; existing archive preserved')
    payload=dict(schema=1,symbol='^SOX',name='PHLX Semiconductor price index',timezone='America/New_York',available_at_basis='scheduled US session close converted to Asia/Taipei; not vendor publication timestamp',units='returns, bias, drawdown, volatility in percent',start_date=min(expected),as_of_date=max(expected),quality=quality,rows=rows)
    # Avoid rewriting an unchanged dataset.
    a.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.output.with_suffix('.json.tmp'); tmp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n',encoding='utf-8'); os.replace(tmp,a.output)
    print(f'Saved {len(rows)} sessions: {a.output}')

if __name__=='__main__': main()
