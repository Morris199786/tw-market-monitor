"""Daily OHLCV for heatmap and institutional stocks.

Reject malformed Yahoo candles, retain validated historical data, and expose
source discrepancies without silently marking a stale feed as refreshed.
"""
import json
import math
import time
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Taipei')
DEST = ROOT / 'data/daily_k'


def read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)


def valid_bar(row):
    try:
        o, h, l, c, v = (float(row[k]) for k in ('open','high','low','close','volume'))
        # Yahoo floats can differ by tiny roundoff, but genuine OHLC violations are rejected.
        eps = max(0.0001, abs(h) * 1e-6)
        return (all(math.isfinite(x) for x in (o,h,l,c,v)) and
                min(o,h,l,c) > 0 and v >= 0 and
                l-eps <= min(o,c) <= max(o,c) <= h+eps)
    except (KeyError, TypeError, ValueError, OverflowError): return False


def parse_chart(payload, symbol, now, gaps=None, rejected_dates=None, diagnostics=None):
    chart = payload.get('chart', {})
    if chart.get('error'): raise ValueError(str(chart['error'])[:160])
    results = chart.get('result') or []
    if len(results) != 1: raise ValueError('missing chart result')
    r = results[0]
    if r.get('meta', {}).get('symbol') != symbol: raise ValueError('ticker mismatch')
    quote = (r.get('indicators', {}).get('quote') or [{}])[0]
    rows = {}
    for i, ts in enumerate(r.get('timestamp') or []):
        day = datetime.fromtimestamp(ts, TZ).date()
        if day > now.date() or (day == now.date() and (now.hour,now.minute) < (14,0)):
            continue
        raw = {}
        for key in ('open','high','low','close','volume'):
            array = quote.get(key) or []
            v = array[i] if i < len(array) else None
            raw[key] = float(v) if isinstance(v,(int,float)) and math.isfinite(v) else None
        date = day.isoformat()
        if all(v is None for v in raw.values()):
            if gaps is not None: gaps.append(date)
            continue
        bar = {'time':date, **raw}
        if not valid_bar(bar):
            if rejected_dates is not None: rejected_dates.append(date)
            if diagnostics is not None:
                # Include raw values only for recent dates to keep manifest small.
                if (now.date() - day).days <= 10:
                    diagnostics[date] = raw
            continue
        rows[date] = {'time':date,'open':round(raw['open'],4),
                      'high':round(raw['high'],4),'low':round(raw['low'],4),
                      'close':round(raw['close'],4),'volume':int(raw['volume'])}
    bars = [rows[d] for d in sorted(rows)]
    if not bars: raise ValueError('no valid completed candles')
    return bars


def merge_bars(old, incoming, rejected_dates):
    existing = {r['time']:r for r in old.get('bars',[]) if isinstance(r,dict)
                and r.get('time') and valid_bar(r)}
    fresh = {r['time']:r for r in incoming}
    overlap = sorted(set(existing)&set(fresh))
    if len(overlap)>=10:
        ratios = [fresh[d]['close']/existing[d]['close'] for d in overlap[-30:]]
        if sum(x<.8 or x>1.25 for x in ratios)>len(ratios)//2:
            raise ValueError('historical price basis changed; existing data preserved')
    merged = dict(existing)
    merged.update(fresh)
    for day in rejected_dates:
        if day in existing: merged[day] = existing[day]
    return [merged[d] for d in sorted(merged)]


VERSION = '2026-10-13-official-retry'


def official_rows(rows, market, now):
    out = {}
    keys = (('Code','OpeningPrice','HighestPrice','LowestPrice','ClosingPrice','TradeVolume')
            if market == 'twse' else
            ('SecuritiesCompanyCode','Open','High','Low','Close','TradingShares'))
    for row in rows:
        try:
            date = str(row['Date']).replace('/','').replace('-','')
            if len(date)==7: date=str(int(date[:3])+1911)+date[3:]
            day=datetime.strptime(date,'%Y%m%d').date()
            if day>now.date() or (day==now.date() and now.hour<14): continue
            ticker=str(row[keys[0]]).strip()
            if len(ticker)!=4 or not ticker.isdigit(): continue
            bar={'time':day.isoformat()}
            for key,field in zip(('open','high','low','close','volume'),keys[1:]):
                bar[key]=float(str(row[field]).replace(',','').strip())
            if not valid_bar(bar): continue
            bar['volume']=int(bar['volume'])
            bar['source']='TWSE' if market=='twse' else 'TPEx'
            if ticker not in out or bar['time']>out[ticker]['time']: out[ticker]=bar
        except (KeyError,ValueError,TypeError): continue
    if not out: raise ValueError('official OHLCV schema/date unavailable')
    return out


def fetch_official(now):
    quotes,errors={},{}
    endpoints={'twse':'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
               'tpex':'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes'}
    def get(market,url):
        last_error=None
        for attempt in range(4):
            try:
                # Retry the entire response, including body download / JSON parsing.
                # The TPEx response is large; a successful HTTP status alone is insufficient.
                with requests.get(url,headers={'User-Agent':'Mozilla/5.0',
                    'Accept':'application/json','Accept-Encoding':'identity',
                    'Connection':'close'},timeout=(10,45)) as r:
                    r.raise_for_status()
                    rows=r.json()
                return official_rows(rows,market,now)
            except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
                last_error=exc
                print(f'official {market} attempt {attempt+1}/4: {type(exc).__name__}',flush=True)
                if attempt<3: time.sleep(min(2**attempt,4))
        raise RuntimeError(f'{market} download failed after 4 attempts: {last_error}')
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(get,m,u):m for m,u in endpoints.items()}
        for job in as_completed(jobs):
            market=jobs[job]
            try: quotes[market]=job.result()
            except Exception as exc: errors[market]=str(exc)[:180]
    return quotes,errors


def save_candles(ticker,meta,now,bars,gaps=None,rejected=None):
    value={'ticker':ticker,'name':meta['name'],'market':meta['market'],
           'source':'Yahoo Finance history + TWSE/TPEx official close',
           'price_basis':'OHLC/Close（非 Adj Close）','volume_unit':'shares',
           'missing_dates':gaps or [],'invalid_dates':rejected or [],
           'updated_at':now.isoformat(timespec='seconds'),
           'fetched_on':now.date().isoformat(),'date':bars[-1]['time'],
           'version':VERSION,'bars':bars}
    write(DEST/(ticker+'.json'),value)
    return value


def fetch_one(ticker, meta, now, official=None):
    symbol = ticker + ('.TW' if meta['market']=='twse' else '.TWO')
    path = DEST/(ticker+'.json')
    old = read(path,{})
    validated=[r for r in old.get('bars',[]) if isinstance(r,dict) and r.get('time') and valid_bar(r)]
    # Existing history only needs one official all-market quote per day, not 327 Yahoo calls.
    if official and len(validated)>=240:
        last=max(r['time'] for r in validated)
        gap=(datetime.fromisoformat(official['time'])-datetime.fromisoformat(last)).days
        if 0<=gap<=4 and not any((datetime.fromisoformat(last)+timedelta(days=i)).weekday()<5 for i in range(1,gap)):
            bars=merge_bars(old,[official],[])
            fixed=official['time']
            value=save_candles(ticker,meta,now,bars,
                [d for d in old.get('missing_dates',[]) if d!=fixed],
                [d for d in old.get('invalid_dates',[]) if d!=fixed])
            return value,'updated',{'host':official['source']}
    if old.get('version')==VERSION and old.get('fetched_on') == now.date().isoformat() and old.get('bars'):
        try:
            fetched = datetime.fromisoformat(old['updated_at'])
            if fetched.hour>=14 or now.hour<14: return old,'cached',{}
        except (KeyError,ValueError,TypeError): pass
    error = None
    diagnostic = {}
    # Yahoo's two chart endpoints may have different cache states.
    for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
        for attempt in range(2):
            try:
                response = requests.get('https://'+host+'/v8/finance/chart/'+symbol,
                    params={'range':'2y','interval':'1d','events':'splits,div',
                            'includeAdjustedClose':'false'},
                    headers={'User-Agent':'Mozilla/5.0'},timeout=(10,35))
                response.raise_for_status()
                gaps,rejected,raw = [],[],{}
                incoming = parse_chart(response.json(),symbol,now,gaps,rejected,raw)
                if official:
                    incoming=merge_bars({'bars':incoming},[official],[])
                    gaps=[d for d in gaps if d!=official['time']]
                    rejected=[d for d in rejected if d!=official['time']]
                    raw.pop(official['time'],None)
                bars = merge_bars(old,incoming,rejected)
                latest_source = incoming[-1]['time']
                latest_saved = old.get('date','')
                if latest_saved and latest_source < latest_saved:
                    error = f'stale source: latest {latest_source}, saved {latest_saved}; rejected={rejected[-5:]}'
                    diagnostic = {'host':host,'source_date':latest_source,
                                  'rejected_recent':raw,'rejected_dates':rejected[-10:]}
                    # Different endpoint might have a fresher valid candle.
                    break
                value=save_candles(ticker,meta,now,bars,gaps,rejected)
                return value,'updated',{'host':host,'rejected_recent':raw}
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'[:180]
                if attempt==0: time.sleep(2)
    return old,error or 'source unavailable',diagnostic


def main():
    now = datetime.now(TZ)
    sectors = read(ROOT/'data/sectors.json',{}).get('sectors',[])
    master = read(ROOT/'data/master.json',{}).get('stocks',{})
    tickers = {str(x.get('ticker','')) for s in sectors for x in s.get('stocks',[])}
    rankings = read(ROOT/'data/institutional.json',{}).get('periods',{})
    for period in rankings.values():
        for market in period.values():
            for group in market.values():
                for side in ('buy','sell'):
                    tickers.update(str(row.get('ticker','')) for row in group.get(side,[]))
    if not tickers: raise RuntimeError('empty heatmap universe')
    universe,errors = {},{}
    for ticker in sorted(tickers):
        meta = master.get(ticker,{})
        if not ticker.isdigit() or len(ticker)!=4 or meta.get('market') not in ('twse','tpex'):
            errors[ticker] = 'missing valid market identity'
            continue
        universe[ticker] = meta
    official,official_errors=fetch_official(now)
    status,success,diagnostics = {},0,{}
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = {pool.submit(fetch_one,t,m,now,official.get(m['market'],{}).get(t)):t for t,m in universe.items()}
        for future in as_completed(tasks):
            ticker = tasks[future]
            try: value,result,detail = future.result()
            except Exception as exc:
                value,result,detail = {},f'{type(exc).__name__}: {exc}'[:180],{}
            ok = result in ('updated','cached')
            if ok: success+=1
            else: errors[ticker]=result
            if detail.get('rejected_recent'):
                diagnostics[ticker]=detail
            status[ticker]={'available':bool(value.get('bars')),'refresh_ok':ok,
                            'date':value.get('date'),'bars':len(value.get('bars',[])),
                            'invalid_dates':value.get('invalid_dates',[])}
    write(DEST/'manifest.json',{'updated_at':now.isoformat(timespec='seconds'),
        'source':'Yahoo Finance + TWSE/TPEx','version':VERSION,'official_errors':official_errors,'stocks':status,'errors':errors,
        'diagnostics':diagnostics,'success':success,'requested':len(tickers)})
    print(f'daily K: {success}/{len(tickers)} refreshed; {len(errors)} errors')
    if errors: print('WARNING: source errors recorded in manifest.json; existing data preserved')
    if errors:
        raise RuntimeError(f'{len(errors)} stocks failed refresh; valid candles saved; inspect manifest.json')
    if not any(s['available'] for s in status.values()):
        raise RuntimeError('No daily K data available for any stock')

if __name__=='__main__': main()


