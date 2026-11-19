#!/usr/bin/env python3
"""Official TWSE/TPEx daily AD and SMA breadth. Python 3.10+, stdlib only."""
import argparse, concurrent.futures, datetime as dt, html, json, math, os, re, time, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
VERSION = 1
TWSE = 'https://www.twse.com.tw/rwd/zh/'
TPEX = 'https://www.tpex.org.tw/www/zh-tw/'
def number(x):
    try:
        v = float(re.sub('<[^>]*>', '', str(x)).replace(',', '').replace('−', '-').strip())
        return v if math.isfinite(v) else None
    except (ValueError, TypeError): return None
def clean(x): return html.unescape(re.sub('<[^>]*>', '', str(x))).strip()
def ordinary(code): return bool(re.fullmatch(r'[1-9]\d{3}', code)) and not code.startswith('91')
def date_value(s):
    parts = re.findall(r'\d+', str(s))
    if len(parts) >= 3:
        y,m,d = map(int, parts[:3]); return dt.date(y+1911 if y<1911 else y,m,d).isoformat()
    raise ValueError('invalid official date: '+str(s))
def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); tmp.replace(path)
def request(base, params):
    url=base+'?'+urllib.parse.urlencode(dict(params,response='json'))
    error=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=25) as r: j=json.load(r)
            if str(j.get('stat','')).lower() not in ('ok','') : raise ValueError(str(j.get('stat'))[:160])
            return j
        except Exception as e:
            error=e
            if attempt<2: time.sleep(1+attempt*2)
    raise RuntimeError(str(error))
def read(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError): return None

def parse_quotes(j, market, date):
    if str(j.get('date')) != date.replace('-',''): raise ValueError('quote date mismatch')
    tables=j.get('tables',[])
    key='證券代號' if market=='twse' else '代號'
    table=next((t for t in tables if key in t.get('fields',[]) and ('成交股數' in t['fields']) and (market=='twse' or t.get('title')=='上櫃股票行情')),None)
    if not table: raise ValueError('missing official quotes table')
    fields=[clean(f).replace(' ','') for f in table['fields']]
    stocks={}
    for row in table.get('data',[]):
        r=dict(zip(fields,row)); code=clean(r[key])
        if not ordinary(code): continue
        c=number(r.get('收盤價' if market=='twse' else '收盤'))
        change=number(r.get('漲跌價差' if market=='twse' else '漲跌'))
        if market=='twse':
            sign=clean(r.get('漲跌(+/-)',''))
            if sign=='-': change=-abs(change) if change is not None else None
            elif sign not in ('','+'): change=None
        stocks[code]={'close':c,'change':change,'volume':number(r.get('成交股數')),'next_ref':number(r.get('次日參考價'))}
    if len(stocks)<100: raise ValueError('implausibly small stock universe')
    index=None
    if market=='twse':
        for t in tables:
            if '價格指數(臺灣證券交易所)' in t.get('title',''):
                index=next((number(r[1]) for r in t.get('data',[]) if clean(r[0])=='發行量加權股價指數'),None)
    return {'schema':VERSION,'date':date,'market':market,'stocks':stocks,'index':index}

def calculate(days, cache, indices, actions, year):
    """Every denominator uses valid observations; gaps reset rolling history."""
    histories={}; prior={}; cumulative=0; ad_contiguous=True; rows=[]; prev_pct={}
    for date in days:
        data=cache.get(date)
        if not data:
            histories.clear(); prior={}
            if date[:4]>=str(year): ad_contiguous=False; rows.append({'date':date,'complete':False})
            prev_pct={}; continue
        stocks=data['stocks']; current={}; adv=dec=flat=excluded=0
        counts={20:[0,0],60:[0,0]}; priced=0
        for code,q in stocks.items():
            close=q['close']; volume=q['volume']; change=q['change']; old=prior.get(code)
            if close is None or close<=0 or volume is None or volume<=0:
                histories.pop(code,None); excluded+=1; continue
            priced+=1
            if change is None: excluded+=1
            elif change>0: adv+=1
            elif change<0: dec+=1
            else: flat+=1
            hist=histories.get(code,[])
            ref=None
            event=actions.get(date,{}).get(code)
            # TWSE official opening reference handles ex-dividend days flagged X.
            if event: ref=event
            elif old and old.get('next_ref') and old['next_ref']>0: ref=old['next_ref']
            elif change is not None: ref=close-change
            if old and hist:
                if ref is None or ref<=0 or abs(close/ref-1)>0.45:
                    hist=[]
                else:
                    # Back-adjust historical observations to today's reference price.
                    factor=ref/old['close']
                    if abs(ref-old['close'])>max(0.011,old['close']*0.00001): hist=[p*factor for p in hist]
            else: hist=[]
            hist=(hist+[close])[-60:]; histories[code]=hist; current[code]=q
            for n in (20,60):
                if len(hist)>=n:
                    counts[n][1]+=1
                    if close>sum(hist[-n:])/n+1e-9: counts[n][0]+=1
        # Remove suspended/missing stocks so observations must be consecutive sessions.
        histories={c:h for c,h in histories.items() if c in current}; prior=current
        if date[:4]<str(year): continue
        net=adv-dec
        if ad_contiguous: cumulative+=net
        r={'date':date,'complete':True,'universe':len(stocks),'priced':priced,'advances':adv,'declines':dec,'unchanged':flat,'ad_excluded':excluded,'net':net,'ad':cumulative if ad_contiguous else None,'index':data.get('index') or indices.get(date)}
        for n,(above,total) in counts.items():
            pct=round(100*above/total,4) if total else None
            r.update({f'above{n}':above,f'eligible{n}':total,f'pct{n}':pct,f'delta{n}':round(pct-prev_pct[n],4) if pct is not None and prev_pct.get(n) is not None else None})
            prev_pct[n]=pct
        rows.append(r)
    return rows

def combine(a,b):
    rows=[]; previous={}
    for x,y in zip(a,b):
        assert x['date']==y['date']
        if not x.get('complete') or not y.get('complete'):
            rows.append({'date':x['date'],'complete':False}); previous={}; continue
        r={'date':x['date'],'complete':True,'index_twse':x.get('index'),'index_tpex':y.get('index')}
        for k in ('universe','priced','advances','declines','unchanged','ad_excluded','net'): r[k]=x[k]+y[k]
        r['ad']=x['ad']+y['ad'] if x['ad'] is not None and y['ad'] is not None else None
        for n in (20,60):
            for k in (f'above{n}',f'eligible{n}'): r[k]=x[k]+y[k]
            p=100*r[f'above{n}']/r[f'eligible{n}'] if r[f'eligible{n}'] else None
            r[f'pct{n}']=round(p,4) if p is not None else None
            r[f'delta{n}']=round(p-previous[n],4) if p is not None and previous.get(n) is not None else None
            previous[n]=p
        rows.append(r)
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--start-year','--year',dest='year',type=int,default=2024); p.add_argument('--as-of'); p.add_argument('--budget-seconds',type=int,default=int(os.getenv('MB_BUDGET_SECONDS','2400'))); p.add_argument('--cache-dir',default=str(ROOT/'.cache/market-breadth-v1')); p.add_argument('--output',default=str(ROOT/'data/market_breadth.json')); args=p.parse_args()
    now=dt.datetime.now(ZoneInfo('Asia/Taipei'))
    cutoff=dt.date.fromisoformat(args.as_of) if args.as_of else now.date()-dt.timedelta(days=now.hour<16)
    start=dt.date(args.year-1,9,1); cache_dir=Path(args.cache_dir); deadline=time.monotonic()+args.budget_seconds; errors=[]; dates=[]; otc={}; actions={}
    months=[]; m=start.replace(day=1)
    while m<=cutoff:
        months.append(m); m=(m.replace(day=28)+dt.timedelta(days=4)).replace(day=1)
    for m in months:
        tag=m.strftime('%Y%m'); mutable=tag>=cutoff.strftime('%Y%m')
        for kind in ('calendar','otc','actions'):
            path=cache_dir/kind/(tag+'.json'); j=read(path)
            try:
                if not j or mutable:
                    if kind=='calendar': j=request(TWSE+'afterTrading/FMTQIK',{'date':tag+'01'})
                    elif kind=='otc': j=request(TPEX+'afterTrading/tradingIndex',{'date':m.strftime('%Y/%m/%d')})
                    else: j=request(TWSE+'exRight/TWT49U',{'startDate':tag+'01','endDate':min(cutoff,(m.replace(day=28)+dt.timedelta(days=4)).replace(day=1)-dt.timedelta(days=1)).strftime('%Y%m%d')})
                    save(path,j)
            except Exception as e:
                errors.append(f'{kind} {tag}: {e}'); print(errors[-1],flush=True)
            if not j and kind=='calendar': raise RuntimeError(f'Missing trading calendar {tag}; previous publication preserved')
            if not j: continue
            if kind=='calendar' and not j.get('data'): raise RuntimeError(f'Empty calendar {tag}; previous publication preserved')
            if kind=='calendar': dates.extend(date_value(r[0]) for r in j.get('data',[]) if start.isoformat()<=date_value(r[0])<=cutoff.isoformat())
            elif kind=='otc':
                for t in j.get('tables',[]):
                    for r in t.get('data',[]): otc[date_value(r[0])]=number(r[4])
            else:
                for r in j.get('data',[]):
                    code=clean(r[1])
                    if ordinary(code): actions.setdefault(date_value(r[0]),{})[code]=number(r[9]) or number(r[4])
    dates=sorted(set(dates))
    if not any(d[:4]==str(args.year) for d in dates): raise RuntimeError('No verified trading calendar; preserved existing output')
    def collect(market):
        result={}; failures=[]; total=len(dates)
        for i,date in enumerate(dates):
            path=cache_dir/market/(date+'.json'); j=read(path)
            if j and j.get('schema')==VERSION and j.get('date')==date and j.get('market')==market and len(j.get('stocks',{}))>=100: result[date]=j; continue
            if time.monotonic()>=deadline: continue
            try:
                if market=='twse': raw=request(TWSE+'afterTrading/MI_INDEX',{'date':date.replace('-',''),'type':'ALLBUT0999'})
                else: raw=request(TPEX+'afterTrading/dailyQuotes',{'date':date.replace('-','/')})
                j=parse_quotes(raw,market,date); save(path,j); result[date]=j
                if i%10==0 or i==total-1: print(f'{market}: {i+1}/{total} {date}',flush=True)
            except Exception as e: failures.append(f'{market} {date}: {e}'); print(failures[-1],flush=True)
            time.sleep(0.25)
        return result,failures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fs={m:pool.submit(collect,m) for m in ('twse','tpex')}; results={m:f.result() for m,f in fs.items()}
    series={m:calculate(dates,results[m][0],otc if m=='tpex' else {},actions if m=='twse' else {},args.year) for m in results}
    series['all']=combine(series['twse'],series['tpex'])
    missing={m:[d for d in dates if d not in results[m][0]] for m in results}
    out={'schema':VERSION,'year':args.year,'updated_at':now.isoformat(timespec='seconds'),'as_of_date':dates[-1],'baseline':f'{args.year}-01-01 前一交易日設為 0','warmup_start':start.isoformat(),'complete':not any(missing.values()),'missing_dates':missing,'errors':errors+sum((r[1] for r in results.values()),[]),'sources':{'twse_quotes':TWSE+'afterTrading/MI_INDEX','tpex_quotes':TPEX+'afterTrading/dailyQuotes','tpex_index':TPEX+'afterTrading/tradingIndex','corporate_actions':TWSE+'exRight/TWT49U'},'series':series}
    # Never overwrite a more complete publication with an incomplete collection.
    old=read(Path(args.output))
    if old:
        old_good=sum(r.get('complete',False) for r in old.get('series',{}).get('all',[])); new_good=sum(r.get('complete',False) for r in series['all'])
        old_dates={r['date'] for r in old.get('series',{}).get('all',[]) if r.get('complete')}
        new_dates={r['date'] for r in series['all'] if r.get('complete')}
        if old_dates-new_dates:
            print('Historical backfill still in progress. Quotes cached; previous publication preserved.',flush=True)
            if os.getenv('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f: f.write(f'歷史回補中，行情待補 {sum(map(len,missing.values()))} 日，保留上次公布資料。')
            return
    save(Path(args.output),out)
    print(f"Saved {args.output}; complete={out['complete']}; sessions={len(series['all'])}; missing quotes={sum(map(len,missing.values()))}",flush=True)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f: f.write(f"### 騰落線與市場寬度\n截至 {dates[-1]}；自 {args.year} 年起 {len(series['all'])} 個交易日；行情待補 {sum(map(len,missing.values()))} 日。\n")
if __name__=='__main__': main()
