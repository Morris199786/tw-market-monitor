"""AI-only full TWSE/TPEx quote cache; never changes other pages or sends messages."""
import argparse,html,json,re,time,urllib.request,urllib.parse
from datetime import datetime
from pathlib import Path
from ai_portfolio_engine import DEFAULTS,TZ,number
ROOT=Path(__file__).resolve().parents[1]
PASSIVE={'0050','006208','0056','00878','00919','00713'}
FIN_URLS={'twse':'https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci','tpex':'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci'}

def read(p,default=None):return json.loads(p.read_text()) if p.exists() else ({} if default is None else default)
def write(p,d):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,allow_nan=False));tmp.replace(p)
def fetch(url):
    error=None
    for i in range(2):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 AI paper research','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
        except Exception as e:error=e
    raise RuntimeError(str(error))
def val(x):
    if x is None:return None
    s=re.sub(r'<[^>]+>','',html.unescape(str(x))).replace(',','').strip()
    if s.startswith('(') and s.endswith(')'):s='-'+s[1:-1]
    return number(s)
def field(fs,*names):
    for i,s in enumerate(fs):
        text=re.sub(r'\s|<[^>]*>','',str(s))
        if any(text==n or text.startswith(n) for n in names):return i
    return None

def parse_quotes(obj,market,day,allowed):
    response_date=str(obj.get('date','')).replace('-','').replace('/','')
    if response_date!=day.replace('-',''):raise ValueError('Official quote response date mismatch: '+response_date+' vs '+day)
    out={}
    tables=obj.get('tables',[])
    if not tables and obj.get('fields') and obj.get('data'):tables=[obj]
    for tb in tables:
        fs=tb.get('fields',[]);rows=tb.get('data',[])
        ids=[field(fs,'證券代號','代號'),field(fs,'證券名稱','名稱'),field(fs,'開盤價','開盤'),field(fs,'最高價','最高'),
             field(fs,'最低價','最低'),field(fs,'收盤價','收盤'),field(fs,'成交股數'),field(fs,'成交金額')]
        if any(i is None for i in ids):continue
        for row in rows:
            t=str(row[ids[0]]).strip()
            if t not in allowed:continue
            ns=[val(row[i]) for i in ids[2:]]
            if any(n is None or n<=0 for n in ns[:4]):continue
            if not ns[2]<=min(ns[0],ns[3])<=max(ns[0],ns[3])<=ns[1]:continue
            out[t]=dict(ticker=t,name=re.sub(r'<[^>]+>','',str(row[ids[1]])).strip(),market=market,
                open=ns[0],high=ns[1],low=ns[2],close=ns[3],price=ns[3],volume=ns[4] or 0,turnover=ns[5] or 0,time=day)
    return out

def quote_url(day,market):
    if market=='twse':return 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?'+urllib.parse.urlencode({'response':'json','date':day.replace('-',''),'type':'ALLBUT0999'})
    dt=datetime.fromisoformat(day);roc=f'{dt.year-1911}/{dt:%m/%d}'
    return 'https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?'+urllib.parse.urlencode({'l':'zh-tw','d':roc,'se':'EW','o':'json'})

def finance_rows(rows,market,observed):
    out={}
    for x in rows:
        t=str(x.get('公司代號',x.get('SecuritiesCompanyCode',''))).strip()
        year=val(x.get('年度',x.get('Year')));quarter=val(x.get('季別',x.get('Season')))
        if not year or not quarter or len(t)!=4:continue
        if year<1911:year+=1911
        revenue=val(x.get('營業收入'));gross=val(x.get('營業毛利（毛損）淨額'));profit=val(x.get('營業利益（損失）'))
        period=f'{int(year)}-Q{int(quarter)}'
        if int(year)>int(observed[:4]) or (int(year)==int(observed[:4]) and int(quarter)*3>int(observed[5:7])):continue
        out[t]=dict(ticker=t,period=period,scope='year_to_date',observed_at=observed,
            export_date=x.get('出表日期',x.get('Date')),revenue=revenue,eps=val(x.get('基本每股盈餘（元）')),
            gross_margin=100*gross/revenue if gross is not None and revenue and revenue>0 else None,
            operating_margin=100*profit/revenue if profit is not None and revenue and revenue>0 else None,source_url=FIN_URLS[market])
    return out

def core_history(data,day):
    errors=[];dt=datetime.fromisoformat(day)
    for ticker in ('0050','006208'):
        path=data/'ai_etf_bars'/(ticker+'.json');old=read(path)
        if old.get('ticker')==ticker and old.get('as_of_date')==day and len(old.get('bars',[]))>=21:continue
        bars={b['time']:b for b in old.get('bars',[]) if b.get('time','9999')<=day}
        for offset in (0,1):
            month=dt.month-offset;year=dt.year
            if month<1:year-=1;month+=12
            md=f'{year:04d}{month:02d}01'
            url='https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?'+urllib.parse.urlencode({'date':md,'stockNo':ticker,'response':'json'})
            try:
                obj=fetch(url)
                if not re.search(r'(?<![0-9])'+ticker+r'(?![0-9])',str(obj.get('title',''))) and str(obj.get('stockNo',''))!=ticker:raise ValueError('ETF identity mismatch')
                for row in obj.get('data',[]):
                    yy,mm,dd=map(int,row[0].split('/'));yy=yy+1911 if yy<1911 else yy
                    d=f'{yy:04d}-{mm:02d}-{dd:02d}'
                    if d>day or yy!=year or mm!=month:continue
                    ns=[val(row[i]) for i in (3,4,5,6,1)]
                    if all(n is not None and n>0 for n in ns[:4]):bars[d]=dict(time=d,open=ns[0],high=ns[1],low=ns[2],close=ns[3],volume=ns[4] or 0)
            except Exception as e:errors.append(f'{ticker} core ETF history: {e}')
        if bars:write(path,dict(ticker=ticker,as_of_date=day,bars=[bars[d] for d in sorted(bars)],source='TWSE STOCK_DAY official monthly OHLC'))
    return errors

def collect(root,max_days=None):
    data=root/'data';now=datetime.now(TZ).isoformat(timespec='seconds');cfg={**DEFAULTS,**read(root/'config/ai_portfolio.json')}
    master=read(data/'master.json').get('stocks',{});latest=read(data/'market_latest.json');day=latest.get('date')
    if not day:raise ValueError('No completed market date')
    ordinary={t:v for t,v in master.items() if len(t)==4 and t.isdigit() and not t.startswith('0') and v.get('market') in ('twse','tpex')}
    if len(ordinary)<1500:raise ValueError('Official full-market company register has insufficient coverage')
    manifest=read(data/'etf-flow-v2/manifest.json');base=data/'etf-flow-v2'/manifest.get('path','missing');meta=read(base/'meta.json')
    active={f['code']:f for f in meta.get('funds',[]) if f.get('region')=='TW' and f.get('listing','9999')<=day}
    allowed=set(ordinary)|set(active)|PASSIVE
    monitor=read(data/'market_monitor.json');dates=sorted({r['date'] for r in monitor.get('raw',[]) if r.get('date','9999')<=day})[-24:]
    if day not in dates:dates.append(day)
    errors=[];completed=0
    # Latest first: old existing market snapshots provide close history for the rest.
    for date in reversed(dates):
        path=data/'ai_universe_days'/(date+'.json');cached=read(path)
        if cached.get('complete'):continue
        if completed>=(cfg['bootstrap_days_per_run'] if max_days is None else max_days):break
        combined={};counts={}
        for m in ('twse','tpex'):
            try:
                quotes=parse_quotes(fetch(quote_url(date,m)),m,date,allowed)
                actual=sum(t in ordinary and ordinary[t]['market']==m for t in quotes)
                expected=sum(v['market']==m for v in ordinary.values());counts[m]={'actual':actual,'expected':expected}
                if actual<expected*.80:raise ValueError(f'{m} quote coverage {actual}/{expected}')
                combined.update(quotes)
            except Exception as e:errors.append(f'{date} {m}: {e}')
        complete=len(counts)==2 and all(c['actual']>=c['expected']*.80 for c in counts.values())
        write(path,dict(date=date,observed_at=now,complete=complete,stocks=combined,coverage=counts))
        completed+=1
        if errors:break
    current=read(data/'ai_universe_days'/(day+'.json'));quotes=current.get('stocks',{})
    instruments={}
    for t,q in quotes.items():
        if t in ordinary:instruments[t]={**q,'asset_type':'stock','industry':ordinary[t].get('industry','unknown')}
        elif t in active or t in PASSIVE:
            f=read(base/'etfs'/(t+'.json'))
            instruments[t]={**q,'asset_type':'etf','industry':'ETF','region':'TW','leveraged':False,'holdings':f.get('holdings',[]),
                'classification_source':'existing Taiwan equity fund metadata' if t in active else 'configured domestic broad/dividend equity ETF'}
    write(data/'ai_universe.json',dict(schema=2,date=day,updated_at=now,complete=current.get('complete',False),
        register_count=len(ordinary),stock_quote_count=sum(x['asset_type']=='stock' for x in instruments.values()),
        etf_count=sum(x['asset_type']=='etf' for x in instruments.values()),stocks=instruments,errors=errors,
        scope='TWSE/TPEx ordinary shares from official master; domestic unleveraged equity ETFs; excludes emerging stocks, warrants, preferred shares'))
    errors.extend(core_history(data,day))
    fin=read(data/'ai_fundamentals.json');metrics=fin.get('stocks',{});fin_errors=[]
    for m,url in FIN_URLS.items():
        try:metrics.update(finance_rows(fetch(url),m,now))
        except Exception as e:fin_errors.append(m+': '+str(e))
    write(data/'ai_fundamentals.json',dict(updated_at=now,stocks=metrics,errors=fin_errors,
        note='Official cumulative financial data, not single-quarter results; observed date is not announcement date'))
    print(json.dumps({'date':day,'register':len(ordinary),'stock_quotes':sum(x['asset_type']=='stock' for x in instruments.values()),
        'etfs':sum(x['asset_type']=='etf' for x in instruments.values()),'fundamentals':len(metrics),'errors':errors+fin_errors},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--max-days',type=int);a=p.parse_args();collect(a.root,a.max_days)
