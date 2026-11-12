#!/usr/bin/env python3
"""Read-only Sheets importer. Build active-equity ETF data; publish manifest last.
Input: --xlsx workbook.xlsx, or Google Application Default Credentials (WIF),
with legacy GOOGLE_SERVICE_ACCOUNT_JSON support.
Optional --market-csv: date,code,adjusted_close,average_price (TWD only).
"""
import argparse, collections, datetime as dt, hashlib, json, math, os, re, shutil, tempfile
from pathlib import Path
SHEET_ID='1BzgyIoIo_Fq8GhLKU3smRaVv5XjD7BMskgsxckTPIl8'
TABS=['ETF清單','全部歷史','ETF每日還原股價','ETF每日NAV與單位','更新總覽']
def num(x):
    if x is None or str(x).strip() in ('','—','--'): return None
    try:
        v=float(str(x).replace(',','').replace('%',''));return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None
def date(x):
    if isinstance(x,(dt.datetime,dt.date)):
        return x.strftime('%Y-%m-%d')
    # Sheets API UNFORMATTED_VALUE returns date-formatted cells as numeric
    # serial days since 1899-12-30, while other tabs use YYYYMMDD strings.
    if isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x):
        if 30000 <= x <= 80000:
            return (dt.date(1899,12,30)+dt.timedelta(days=int(x))).isoformat()
    s=str(x or '').strip()
    m=re.fullmatch(r'(20\d\d)[/-]?(\d\d)[/-]?(\d\d)',s)
    if m:
        try:return dt.date(*map(int,m.groups())).isoformat()
        except ValueError:return None
    if re.fullmatch(r'\d{5}(?:\.0+)?',s):
        serial=float(s)
        if 30000 <= serial <= 80000:
            return (dt.date(1899,12,30)+dt.timedelta(days=int(serial))).isoformat()
    return None
def dictionaries(rows):
    it=iter(rows);head=[str(x or '').strip() for x in next(it)]
    for values in it:
        if any(x is not None and x!='' for x in values):yield dict(zip(head,values))
def read_xlsx(path):
    import openpyxl
    w=openpyxl.load_workbook(path,read_only=True,data_only=True)
    try:
        return {name:list(dictionaries(w[name].iter_rows(values_only=True))) for name in TABS}
    finally:w.close()
def read_sheets():
    import google.auth
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    raw=os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON') or os.environ.get('GOOGLE_SERVICE_ACCOUNT')
    if raw:
        # Keep backwards compatibility with a valid legacy JSON secret when explicitly supplied.
        cred=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=scopes)
    else:
        # google-github-actions/auth exports GOOGLE_APPLICATION_CREDENTIALS for keyless WIF.
        cred,_=google.auth.default(scopes=scopes)
    api=build('sheets','v4',credentials=cred,cache_discovery=False).spreadsheets()
    sid=os.environ.get('ETFFLOW_SHEET_ID',SHEET_ID)
    meta=api.get(spreadsheetId=sid,fields='sheets(properties(title,gridProperties(rowCount,columnCount)))').execute()
    tabs={x['properties']['title']:x['properties']['gridProperties'] for x in meta['sheets']}
    output={}
    for name in TABS:
        if name not in tabs:raise RuntimeError('Missing tab '+name)
        rows=[];limit=tabs[name]['rowCount']
        ranges=[f"'{name}'!A{first}:U{min(limit,first+2499)}" for first in range(1,limit+1,2500)]
        for i in range(0,len(ranges),4):
            response=api.values().batchGet(spreadsheetId=sid,ranges=ranges[i:i+4],valueRenderOption='UNFORMATTED_VALUE').execute()
            for part in response.get('valueRanges',[]):rows.extend(part.get('values',[]))
        output[name]=list(dictionaries(rows))
    return output
def build(raw,market=None):
    funds={}
    for r in raw['ETF清單']:
        category=str(r.get('分類') or '')
        if category not in ['主動式國內股票型','主動式國外股票型']:continue
        code=str(r.get('ETF代號') or '').strip()
        if not re.fullmatch(r'\d{5}A',code):raise ValueError('Unexpected active ETF code: '+code)
        funds[code]={'code':code,'name':str(r.get('ETF名稱') or code),'category':category,'region':'TW' if category=='主動式國內股票型' else 'GLOBAL','listing':date(r.get('上市日期')),'sourceLatest':date(r.get('最新持股日期'))}
    if not funds:raise ValueError('No active equity ETFs')
    snapshots=collections.defaultdict(lambda:collections.defaultdict(dict));names={};seen={};invalid=0;read=0
    for r in raw['全部歷史']:
        read+=1;c=str(r.get('股票代號') or '');d=date(r.get('日期'))
        if c not in funds or not d:continue
        # A date exists even when all assets are cash/derivatives; never treat a missing date as zero holdings.
        snap=snapshots[c][d]
        if str(r.get('商品種類') or '').strip()!='股票':continue
        if str(r.get('單位') or '').strip()!='股':continue
        stock=str(r.get('標的代號') or '').strip();q=num(r.get('數值'));w=num(r.get('權重(%)'))
        if not stock or q is None or q<0:invalid+=1;continue
        name=str(r.get('標的名稱') or stock).strip();names[stock]=name
        key=(c,d,stock);value=(q,w)
        if key in seen and seen[key]!=value:raise ValueError('Conflicting holdings '+str(key))
        seen[key]=value;snap[stock]=[stock,name,q,w]
    if invalid:raise ValueError(f'{invalid} invalid share records; previous data preserved')
    prices=collections.defaultdict(dict);navs=collections.defaultdict(dict)
    for r in raw['ETF每日還原股價']:
        c=str(r.get('股票代號') or '');d=date(r.get('日期'));v=num(r.get('收盤價'))
        if c in funds and d and v is not None and v>0:prices[c][d]=v
    for r in raw['ETF每日NAV與單位']:
        c=str(r.get('股票代號') or '');d=date(r.get('日期'))
        if c in funds and d:navs[c][d]={'date':d,'nav':num(r.get('淨值')),'unitsK':num(r.get('已發行受益權單位總數(千)')),'deltaK':num(r.get('與前日已發行單位差異數(千)'))}
    # Optional source is explicitly different from ETF prices. Missing input remains null.
    market=market or {};stocks=collections.defaultdict(list);etfs={};ranking=[]
    for c,f in funds.items():
        days=sorted(snapshots[c]);events=[];series=[];prior=None;ledger={};missing=set()
        for i,d in enumerate(days):
            cur=snapshots[c][d]
            if prior is not None:
                for st in sorted(set(cur)|set(prior)):
                    now=cur.get(st,[st,names.get(st,st),0,0]);before=prior.get(st,[st,names.get(st,st),0,0]);delta=now[2]-before[2]
                    if not delta:continue
                    avg=(market.get(st,{}).get(d) or {}).get('average_price')
                    # No assumed opening price for first snapshot; cost is available only after a known flat position.
                    if st not in ledger:
                        ledger[st]=0
                        if before[2]>0:missing.add(st)
                    if avg is None:missing.add(st)
                    else:ledger[st]+=delta*avg
                    cost=ledger[st]/now[2] if now[2]>0 and st not in missing else None
                    event={'date':d,'code':st,'name':now[1],'delta':delta,'shares':now[2],'weight':now[3],'weightDelta':now[3]-before[3] if now[3] is not None and before[3] is not None else None,'cost':cost}
                    events.append(event)
                    history=[]
                    for n in [5,10,30]:
                        if i<n:history.append(None)
                        else:history.append(now[2]-snapshots[c][days[i-n]].get(st,[None,None,0])[2])
                    oldw=snapshots[c][days[i-5]].get(st,[None,None,0,0])[3] if i>=5 else None
                    stocks[st].append(dict(event,etf=c,flow5=history[0],flow10=history[1],flow30=history[2],weight5=now[3]-oldw if now[3] is not None and oldw is not None else None))
                    if now[2]==0:ledger.pop(st,None);missing.discard(st)
            series.append({'date':d,'baseline':prior is None});prior=cur
        holdings=list(snapshots[c][days[-1]].values()) if days else []
        f.update(latest=days[-1] if days else None,earliest=days[0] if days else None,holdingCount=len(holdings))
        if f['sourceLatest'] and (not days or days[-1]<f['sourceLatest']):raise ValueError('Truncated holdings for '+c)
        etfs[c]={'fund':f,'dates':days,'events':events,'holdings':sorted(holdings,key=lambda x:x[3] if x[3] is not None else -1,reverse=True),'nav':sorted(navs[c].values(),key=lambda x:x['date']),'prices':sorted(prices[c].items())}
        p=sorted(prices[c].items());returns={}
        for n in [5,21,63,126,250,750]:returns[str(n)]=(p[-1][1]/p[-n-1][1]-1)*100 if len(p)>n else None
        ranking.append({'code':c,'date':p[-1][0] if p else None,'returns':returns,'days':len(p)})
    flow=[];domestic=[f for f in funds.values() if f['region']=='TW'];calendar=sorted({d for f in domestic for d in navs[f['code']]})
    for d in calendar:
        contributions=[]
        for f in domestic:
            if not f['listing'] or f['listing']>d:continue
            v=navs[f['code']].get(d);amount=None
            if v and v['deltaK'] is not None and v['nav'] is not None:amount=v['deltaK']*1000*v['nav']
            contributions.append({'code':f['code'],'amount':amount,'deltaK':v['deltaK'] if v else None,'nav':v['nav'] if v else None})
        available=sum(x['amount'] for x in contributions if x['amount'] is not None);covered=sum(x['amount'] is not None for x in contributions)
        flow.append({'date':d,'amount':available if covered==len(contributions) else None,'available':available,'covered':covered,'expected':len(contributions),'funds':contributions})
    overview={r.get('項目'):r.get('內容') for r in raw['更新總覽']}
    expected=num(overview.get('雲端有效明細筆數'))
    if expected is not None and read!=int(expected):raise ValueError(f'Holdings count mismatch: {read} != {int(expected)}')
    meta={'schema':2,'source':'Google Sheets / CMoney','sourceUpdated':overview.get('最後成功更新時間'),'generated':dt.datetime.now(dt.timezone.utc).isoformat(),'funds':list(funds.values()),'stocks':[{'code':k,'name':names.get(k,k)} for k in sorted(stocks)],'missing':['個股還原股價與市場均價尚未提供'] if not market else [],'rawRows':read}
    return meta,etfs,stocks,ranking,flow

def publish(output,result,market=None):
    meta,etfs,stocks,ranking,flow=result
    fingerprint=(dict(meta,generated=None),etfs,stocks,ranking,flow)
    serial=json.dumps(fingerprint,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode();version=hashlib.sha256(serial).hexdigest()[:12]
    output.mkdir(parents=True,exist_ok=True);dest=output/'versions'/version
    temp=Path(tempfile.mkdtemp(prefix='.build-',dir=output))
    def write(path,obj):
        p=temp/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    try:
        write('meta.json',meta);write('ranking.json',ranking);write('flows.json',flow)
        for code,data in etfs.items():write('etfs/'+code+'.json',data)
        index={}
        for i,(code,data) in enumerate(sorted(stocks.items())):
            key=f's{i:05d}';index[code]=key;write('stocks/'+key+'.json',{'code':code,'events':sorted(data,key=lambda x:(x['date'],x['etf']),reverse=True),'prices':market.get(code,{}) if market else {},'calendars':{c:etfs[c]['dates'] for c in {v['etf'] for v in data}}})
        write('stock-index.json',index)
        dest.parent.mkdir(exist_ok=True)
        if dest.exists():shutil.rmtree(temp)
        else:temp.rename(dest)
        pointer=output/'manifest.next.json';pointer.write_text(json.dumps({'schema':2,'version':version,'path':'versions/'+version+'/'},separators=(',',':')));pointer.replace(output/'manifest.json')
        # Retain current and one previous generation for open tabs, without growing every day forever.
        older=sorted((p for p in dest.parent.iterdir() if p.is_dir() and p!=dest),key=lambda p:p.stat().st_mtime,reverse=True)
        for p in older[1:]:shutil.rmtree(p)
    finally:
        if temp.exists():shutil.rmtree(temp)
    print(json.dumps({'status':'ok','funds':len(etfs),'stocks':len(stocks),'rawRows':meta['rawRows'],'version':version},ensure_ascii=False))
def main():
    p=argparse.ArgumentParser();p.add_argument('--xlsx');p.add_argument('--output',default='data/etf-flow-v2');p.add_argument('--market-csv');a=p.parse_args();market={}
    if a.market_csv:
        import csv
        with open(a.market_csv,encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                d=date(r.get('date'));c=r.get('code');close=num(r.get('adjusted_close'));avg=num(r.get('average_price'))
                if not c or not d:raise ValueError('Invalid market date/code')
                if close is not None and close<=0:raise ValueError('Invalid adjusted close')
                if avg is not None and avg<=0:raise ValueError('Invalid market average')
                market.setdefault(c,{})[d]={'close':close,'average_price':avg}
    raw=read_xlsx(a.xlsx) if a.xlsx else read_sheets();publish(Path(a.output),build(raw,market),market)
if __name__=='__main__':main()
