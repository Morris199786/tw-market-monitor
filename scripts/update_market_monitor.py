"""2024 年起大盤監控：上市全市場官方金額，沿用使用者試算表日頻門檻。"""
import json, math, statistics, time, urllib.request, urllib.parse, urllib.error, os, sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/market_monitor.json'
BASE = 'https://www.twse.com.tw/rwd/zh/'
START_YEAR = 2024
WARMUP_START = '2023-11'

def number(v):
    x = float(str(v).replace(',', '').strip())
    if not math.isfinite(x): raise ValueError('nonfinite')
    return x

# All requests are serialized. Backfill must not burst hundreds of requests.
_LAST_REQUEST = 0.0
_CONSECUTIVE_FAILURES = 0
_DEADLINE = float('inf')
class SourceUnavailable(RuntimeError): pass

def fetch(path, **params):
    global _LAST_REQUEST, _CONSECUTIVE_FAILURES
    url = BASE + path + '?' + urllib.parse.urlencode(dict(params, response='json'))
    last = None
    for attempt in range(3):
        if time.monotonic() >= _DEADLINE: raise SourceUnavailable('本輪時間預算已到，已保存進度')
        time.sleep(max(0, 2.5 - (time.monotonic() - _LAST_REQUEST)))
        _LAST_REQUEST = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0', 'Accept':'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r: data=json.load(r)
            if not isinstance(data,dict): raise ValueError('官方回應不是 JSON 物件')
            if data.get('stat') and data['stat']!='OK': raise ValueError(str(data['stat'])[:160])
            _CONSECUTIVE_FAILURES=0
            return data
        except Exception as exc:
            last=exc
            delay=15 * (2 ** attempt)
            if isinstance(exc,urllib.error.HTTPError):
                retry_after=exc.headers.get('Retry-After','') if exc.headers else ''
                if retry_after.isdigit(): delay=max(delay,int(retry_after))
            print(f'來源重試 {attempt+1}/3：{path} {params} {type(exc).__name__}: {exc}',flush=True)
            if attempt<2:
                if time.monotonic()+delay>=_DEADLINE: raise SourceUnavailable('等待重試超過本輪時間預算')
                time.sleep(delay)
    _CONSECUTIVE_FAILURES+=1
    if _CONSECUTIVE_FAILURES>=3: raise SourceUnavailable(f'來源連續失敗，暫停請求：{last}')
    raise last

def date_iso(v):
    y,m,d=map(int,v.split('/'));y=y+1911 if y<1911 else y
    return f'{y:04}-{m:02}-{d:02}'

def indices(today, old=None):
    result={};errors=[]
    months=[f'{y}-{m:02}' for y in range(2023,int(today[:4])+1) for m in range(1,13) if WARMUP_START <= f'{y}-{m:02}' <= today[:7]]
    def month_index(ym):
        found={}
        try:
            data=fetch('afterTrading/FMTQIK',date=ym.replace('-','')+'01')
            if not data.get('data'): raise ValueError('empty trading calendar')
            fields=data['fields'];di=fields.index('日期');ci=fields.index('發行量加權股價指數')
            for row in data['data']:
                ds=date_iso(row[di])
                if not ds.startswith(ym): raise ValueError('month mismatch')
                if ds<=today:found[ds]=number(row[ci])
            if not found: raise ValueError('empty trading calendar')
            return found,None
        except SourceUnavailable: raise
        except Exception as e:return {},f'{ym} 指數來源失敗：{type(e).__name__}: {e}'
    cached={}
    if old and old.get('calendar_complete'):
        for row in old.get('raw',[]):
            if row.get('index') is not None:cached.setdefault(row['date'][:7],{})[row['date']]=row['index']
    for ym in months:
        if ym<today[:7] and cached.get(ym):
            found,error=cached[ym],None
        else:found,error=month_index(ym)
        result.update(found)
        if error:errors.append(error)
        print(f'交易日清單 {ym}：{error or str(len(found))+" 日"}',flush=True)
    return result,errors

def daily(ds, kinds=None):
    key=ds.replace('-','');out={'date':ds};errors=[]
    for kind in (kinds if kinds is not None else ['foreign','margin']):
        try:
            if kind=='foreign':
                d=fetch('fund/BFI82U',dayDate=key,type='day')
                if d.get('date')!=key: raise ValueError(f"date mismatch: expected {key}, got {d.get('date')}, stat={d.get('stat')}")
                f=d['fields'];r=next(r for r in d['data'] if r[0]=='外資及陸資(不含外資自營商)')
                buy=number(r[f.index('買進金額')]);sell=number(r[f.index('賣出金額')]);net=number(r[f.index('買賣差額')])
                if abs(buy-sell-net)>0.1: raise ValueError('net mismatch')
                out['foreign']=net/1e8
            else:
                d=fetch('marginTrading/MI_MARGN',date=key,selectType='MS')
                if d.get('date')!=key: raise ValueError(f"date mismatch: expected {key}, got {d.get('date')}, stat={d.get('stat')}")
                t=next(t for t in d['tables'] if '項目' in t.get('fields',[]))
                r=next(r for r in t['data'] if r[0]=='融資金額(仟元)')
                out['margin']=number(r[t['fields'].index('今日餘額')])*1000
                out['margin_previous']=number(r[t['fields'].index('前日餘額')])*1000
        except SourceUnavailable: raise
        except Exception as e: errors.append(f'{ds} {kind}：{type(e).__name__}: {e}')
    return out,errors

def calculate(raw):
    rows=[]
    for i,r in enumerate(raw):
        if int(r['date'][:4]) < START_YEAR: continue
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

def save(saved, dates, today, errors):
    # Keep calendar placeholders: missing sessions must never disappear from windows.
    raw=[saved[d] for d in dates if d<=today]
    rows=calculate(raw)
    coverage={}
    for year in range(START_YEAR,int(today[:4])+1):
        yr=[r for r in rows if r['date'].startswith(str(year)+'-')]
        coverage[str(year)]={'sessions':len(yr),
            'missing_data':sum(any(r.get(k) is None for k in ('foreign','margin','index')) for r in yr),
            'missing_signals':sum(r.get('intersection') is None for r in yr)}
    out={'year':int(today[:4]),'years':list(range(START_YEAR,int(today[:4])+1)),
         'coverage':coverage,'calendar_complete':True,
         'complete':all(c['missing_data']==0 and c['missing_signals']==0 for c in coverage.values()),
         'pending': [{'date':r['date'],'fields':[k for k in ('foreign','margin','index') if r.get(k) is None]} for r in raw if any(r.get(k) is None for k in ('foreign','margin','index'))],
         'updated_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='minutes'),
         'as_of_date':max((r['date'] for r in rows),default=None),
         'errors':errors,'raw':raw,'rows':rows,
         'scope':'上市全市場；外資及陸資不含外資自營商；融資金額餘額；加權指數',
         'standard_deviation':'STDEV.S（樣本標準差）；原檔未明示母體或樣本',
         'sources':[BASE+'fund/BFI82U',BASE+'marginTrading/MI_MARGN',BASE+'afterTrading/FMTQIK']}
    # Retain historical source provenance during subsequent daily refreshes.
    if OUT.exists():
        prior=json.loads(OUT.read_text(encoding='utf-8'))
        if prior.get('backfill_audit'):
            out['backfill_audit']=prior['backfill_audit']
            out['sources']=list(dict.fromkeys(out['sources']+prior.get('sources',[])))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix('.tmp');tmp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(OUT)
    return out


def main():
    global _DEADLINE
    _DEADLINE=time.monotonic()+float(os.environ.get('MM_BUDGET_SECONDS','1200'))
    today=datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()
    old=json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    saved={r['date']:r for r in old.get('raw',[])}
    idx,errors=indices(today,old)
    if errors: raise RuntimeError('指數交易日清單不完整，保留原檔：'+'; '.join(errors))
    for ds,v in idx.items():saved.setdefault(ds,{'date':ds})['index']=v
    dates=sorted(idx)
    def corrected_balances():
        for j, ds in enumerate(dates[1:],1):
            previous=saved[ds].get('margin_previous')
            if previous is not None:saved[dates[j-1]]['margin']=previous
    corrected_balances()
    # Refresh newest sessions only on the first pass; subsequent passes resume missing fields.
    recent=set(dates[-3:]) if os.environ.get('MM_RESUME_ONLY')!='1' else set()
    needed={d:[k for k in ('foreign','margin') if saved[d].get(k) is None or d in recent] for d in dates}
    needed={d:k for d,k in needed.items() if k}
    order=sorted(needed,key=lambda d:(0 if d in recent else 1,d))
    print(f'本輪需補 {len(order)} 日 / {sum(map(len,needed.values()))} 個欄位',flush=True)
    try:
        for i,ds in enumerate(order,1):
            # Persist each field: interruption must not discard another field already fetched.
            for kind in needed[ds]:
                r,err=daily(ds,[kind]);saved[ds].update(r);errors.extend(err)
                save(saved,dates,today,errors)
            if i%10==0:print(f'處理 {i}/{len(order)} 日',flush=True)
    except SourceUnavailable as exc:
        errors.append(str(exc));print(str(exc),flush=True)
    finally:
        corrected_balances()
        out=save(saved,dates,today,errors)
    print(json.dumps({'complete':out['complete'],'pending_fields':sum(len(r['fields']) for r in out['pending']),'coverage':out['coverage'],'errors':errors[-10:]},ensure_ascii=False))
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as f:
            f.write('\n### 大盤監控完整性\n\n年份 | 交易日 | 缺原始資料 | 缺燈號\n---|---:|---:|---:\n')
            for y,c in out['coverage'].items():f.write(f"{y}|{c['sessions']}|{c['missing_data']}|{c['missing_signals']}\n")
            f.write('\n'+('全部完成' if out['complete'] else '尚未補齊，已保存進度，下輪只補缺漏')+'\n')
    return 0 if out['complete'] and not errors else 2

if __name__=='__main__':sys.exit(main())
