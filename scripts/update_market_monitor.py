"""2026 大盤監控：上市全市場官方金額，沿用使用者試算表日頻門檻。"""
import json, math, statistics, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/market_monitor.json'
BASE = 'https://www.twse.com.tw/rwd/zh/'

def number(v):
    x = float(str(v).replace(',', '').strip())
    if not math.isfinite(x): raise ValueError('nonfinite')
    return x

def fetch(path, **params):
    url = BASE + path + '?' + urllib.parse.urlencode(dict(params, response='json'))
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as r: return json.load(r)
        except Exception:
            if attempt: raise
            time.sleep(1)

def date_iso(v):
    y,m,d=map(int,v.split('/'));y=y+1911 if y<1911 else y
    return f'{y:04}-{m:02}-{d:02}'

def indices(today):
    result={};errors=[]
    months=['2025-12']+[f'2026-{m:02}' for m in range(1,13) if f'2026-{m:02}'<=today[:7]]
    for ym in months:
        try:
            data=fetch('afterTrading/FMTQIK',date=ym.replace('-','')+'01')
            fields=data['fields'];di=fields.index('日期');ci=fields.index('發行量加權股價指數')
            for row in data['data']:
                ds=date_iso(row[di])
                if ds<=today and ds.startswith(ym): result[ds]=number(row[ci])
        except Exception as e: errors.append(f'{ym} 指數來源失敗：{type(e).__name__}')
    return result,errors

def daily(ds):
    key=ds.replace('-','');out={'date':ds};errors=[]
    for kind in ['foreign','margin']:
        try:
            if kind=='foreign':
                d=fetch('fund/BFI82U',dayDate=key,type='day')
                if d.get('date')!=key: raise ValueError('date mismatch')
                f=d['fields'];r=next(r for r in d['data'] if r[0]=='外資及陸資(不含外資自營商)')
                buy=number(r[f.index('買進金額')]);sell=number(r[f.index('賣出金額')]);net=number(r[f.index('買賣差額')])
                if abs(buy-sell-net)>0.1: raise ValueError('net mismatch')
                out['foreign']=net/1e8
            else:
                d=fetch('marginTrading/MI_MARGN',date=key,selectType='MS')
                if d.get('date')!=key: raise ValueError('date mismatch')
                t=next(t for t in d['tables'] if '項目' in t.get('fields',[]))
                r=next(r for r in t['data'] if r[0]=='融資金額(仟元)')
                out['margin']=number(r[t['fields'].index('今日餘額')])*1000
                out['margin_previous']=number(r[t['fields'].index('前日餘額')])*1000
        except Exception as e: errors.append(f'{ds} {kind}：{type(e).__name__}')
    return out,errors

def calculate(raw):
    rows=[]
    for i,r in enumerate(raw):
        if not r['date'].startswith('2026-'): continue
        x=dict(r);x.update(relative=None,z=None,p10=None,relative5=None,relative20=None,foreign_light=None,margin_light=None,intersection=None)
        def window(key,n):
            w=raw[max(0,i-n+1):i+1]
            return [v[key] for v in w] if len(w)==n and all(v.get(key) is not None for v in w) else None
        f20=window('foreign',20);f10=window('foreign',10)
        if f20 is not None:
            sd=statistics.stdev(f20) # 檔案未指明母體/樣本；明示採 STDEV.S
            x['z']=(statistics.mean(f20[-5:])-statistics.mean(f20[:15]))/sd if sd else 0
        if f10 is not None:
            total=sum(abs(v) for v in f10)
            x['p10']=sum(abs(v) for v in f10 if v<0)/total if total else 0
        if f20 is not None and f10 is not None:
            avg=statistics.mean(f20[-5:]);z=x['z'];p=x['p10']
            x['foreign_light']='red' if (z<=-1.1 and avg<0) or p>=.8 else 'yellow' if (z<=-.8 and avg<0) or p>=.7 else 'normal'
        for n,key in [(1,'relative'),(5,'relative5'),(20,'relative20')]:
            ms=window('margin',n+1);ix=window('index',n+1)
            if ms and ix and ms[0]>0 and ix[0]>0:x[key]=((ms[-1]/ms[0]-1)-(ix[-1]/ix[0]-1))*100
        a,b=x['relative5'],x['relative20']
        if a is not None and b is not None:x['margin_light']='red' if a>=5 or b>=9 else 'yellow' if a>=3.5 or b>=7.5 else 'normal'
        f,m=x['foreign_light'],x['margin_light']
        if f is not None and m is not None:x['intersection']='red' if f!='normal' and m!='normal' and 'red' in (f,m) else 'yellow' if f!='normal' and m!='normal' else 'normal'
        rows.append(x)
    return rows

def main():
    today=datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat();old=json.loads(OUT.read_text()) if OUT.exists() else {}
    saved={r['date']:r for r in old.get('raw',[])};idx,errors=indices(today)
    if errors: raise RuntimeError('指數交易日清單不完整，保留原檔：'+'; '.join(errors))
    for ds,v in idx.items():saved.setdefault(ds,{'date':ds})['index']=v
    dates=sorted(idx);retry=set(dates[-3:])
    needed=[d for d in dates if d in retry or saved[d].get('foreign') is None or saved[d].get('margin') is None]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for k,(r,err) in enumerate(pool.map(daily,needed),1):
            saved[r['date']].update(r);errors.extend(err)
            if k%20==0: print(f'回補 {k}/{len(needed)}',flush=True)
    # Next day's previous balance is TWSE's final corrected balance.
    for j, ds in enumerate(dates[1:], 1):
        previous = saved[ds].get('margin_previous')
        if previous is not None:
            saved[dates[j-1]]['margin'] = previous
    raw=[saved[d] for d in sorted(saved) if d<=today]
    rows=calculate(raw)
    out={'year':2026,'updated_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='minutes'),'as_of_date':max((r['date'] for r in rows),default=None),'errors':errors,'raw':raw,'rows':rows,'scope':'上市全市場；外資及陸資不含外資自營商；融資金額餘額；加權指數','standard_deviation':'STDEV.S（樣本標準差）；原檔未明示母體或樣本','sources':[BASE+'fund/BFI82U',BASE+'marginTrading/MI_MARGN',BASE+'afterTrading/FMTQIK']}
    OUT.parent.mkdir(parents=True,exist_ok=True);tmp=OUT.with_suffix('.tmp');tmp.write_text(json.dumps(out,ensure_ascii=False,indent=2));tmp.replace(OUT)
    print(json.dumps({'rows':len(rows),'missing':sum(r.get('foreign') is None or r.get('margin') is None for r in rows),'errors':errors},ensure_ascii=False))
if __name__=='__main__':main()
