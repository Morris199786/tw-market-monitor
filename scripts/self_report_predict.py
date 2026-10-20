#!/usr/bin/env python3
"""Self-report attention research backtest. No deployment, notifications or paid APIs."""
import argparse, collections, csv, datetime as dt, json, re, time
from pathlib import Path
import requests

SESSION=requests.Session();SESSION.headers.update({'User-Agent':'Mozilla/5.0 (compatible; research/1.0)'})
def fetch(url):
    for i in range(3):
        try:
            r=SESSION.get(url,timeout=40);r.raise_for_status();return r.json()
        except (requests.RequestException,ValueError):
            if i==2:raise
            time.sleep(i+1)
def attention(start,end):
    a=start.replace('-','');b=end.replace('-','')
    endpoints=[('上市',f'https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={a}&endDate={b}'),('上櫃',f'https://www.tpex.org.tw/www/zh-tw/bulletin/attention?startDate={start.replace("-","%2F")}&endDate={end.replace("-","%2F")}&response=json')]
    out=[]
    for market,url in endpoints:
        z=fetch(url);tables=z.get('tables') or []
        rows=z.get('data',[]) if market=='上市' else (tables[0].get('data',[]) if tables else [])
        for row in rows:
            if len(row)<6 or not re.fullmatch(r'\d{4}',str(row[1])):continue
            m=re.search(r'(\d{3})/(\d{1,2})/(\d{1,2})',str(row[5]))
            if not m:continue
            date=f'{int(m[1])+1911:04d}-{int(m[2]):02d}-{int(m[3]):02d}'
            if start<=date<=end:
                out.append(dict(date=date,ticker=str(row[1]),name=str(row[2]),market=market,reason=str(row[4])))
    if not out:raise RuntimeError('Official attention feeds returned no data; refusing empty backtest')
    return out

def month_of(x):
    p=str(x.get('monthly_period') or '')
    if re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])',p):return p
    detail=x.get('detail') or ''
    m=re.search(r'(\d{3})年\s*(\d{1,2})月',detail)
    return f'{int(m[1])+1911:04d}-{int(m[2]):02d}' if m and 1<=int(m[2])<=12 else None

def load_reports(path):
    j=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    raw=j.get('items',[])+j.get('diagnostics',{}).get('parse_failed',[])
    out=[];seen=set()
    for x in raw:
        c=str(x.get('ticker',''));date=str(x.get('publish_date',''));subject=x.get('subject') or ''
        if not re.fullmatch(r'\d{4}',c) or not re.fullmatch(r'20\d\d-\d\d-\d\d',date):continue
        if re.search(r'可轉換公司|轉換公司債|公司債近期',subject):continue
        # All website self-report records are events; do not discard genuine events on subject keywords.
        k=(date,c)
        if k in seen:continue
        seen.add(k)
        out.append(dict(date=date,ticker=c,month=month_of(x),name=x.get('name',''),subject=subject,parsed=x.get('monthly_eps') is not None))
    return sorted(out,key=lambda x:(x['date'],x['ticker']))

def target_month(day):
    y,m=map(int,day[:7].split('-'));return f'{y-1}-12' if m==1 else f'{y}-{m-1:02d}'

def is_trade_day(day):return day.weekday()<5

def next_day(cutoff,dates):
    for day in dates:
        if day>cutoff:return day
    d=dt.date.fromisoformat(cutoff)+dt.timedelta(days=1)
    while not is_trade_day(d):d+=dt.timedelta(days=1)
    return d.isoformat()

def feats(c,cutoff,dates,h):
    previous=[d for d in dates if d<=cutoff]
    entries=[x for x in h[c] if x['date']<=cutoff]
    def win(n):
        ds=set(previous[-n:]);return [x for x in entries if x['date'] in ds]
    x10=win(10)
    def kind(xs,k):return sum(bool(re.search(r'第'+k+r'款',x['reason'])) for x in xs)
    last=entries[-1]['date']
    return dict(n1=len(win(1)),n2=len(win(2)),n3=len(win(3)),n5=len(win(5)),n10=len(x10),n20=len(win(20)),r1=kind(x10,'一'),r4=kind(x10,'四'),r6=kind(x10,'六'),gap=len(previous)-1-previous.index(last),market=entries[-1]['market'],name=entries[-1]['name'])

def score(f,variant):
    if variant=='baseline':return 3*f['n3']-3*f['n2']-f['n5']
    if variant=='density':return 2*f['n3']+f['n10']
    if variant=='reason':return 2*f['n3']+f['n10']+f['r6']
    if variant=='balanced':return 2*f['n3']+f['n10']+f['r6']+.5*(f['r1']+f['r4'])-min(f['gap'],5)
    raise ValueError(variant)

def select(cutoff,day,dates,h,reports,variant,threshold,cap=10):
    period=target_month(day)
    # Month-known reports are excluded; unknown-month reports cannot be safely used as exclusions.
    excluded={x['ticker'] for x in reports if x['date']<=cutoff and x['month']==period}
    pool=[]
    for c in h:
        if c in excluded:continue
        f=feats(c,cutoff,dates,h)
        if f['n10']==0 or (variant=='baseline' and not f['n1']):continue
        s=score(f,variant)
        if s>=threshold:pool.append(dict(ticker=c,score=round(s,3),**f))
    return sorted(pool,key=lambda x:(-x['score'],x['ticker']))[:cap]

def write_csv(path,rows,fields):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--reports',default='data/self_reports.json');p.add_argument('--start',default='2026-09-01');p.add_argument('--asof',default=dt.date.today().isoformat());p.add_argument('--backtest',action='store_true');p.add_argument('--out',default='self_report_model');p.add_argument('--backtest-start',default='2026-09-29')
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    at=attention(a.start,a.asof);reports=load_reports(a.reports)
    dates=sorted({x['date'] for x in at});h=collections.defaultdict(list)
    for x in at:h[x['ticker']].append(x)
    for xs in h.values():xs.sort(key=lambda x:x['date'])
    variants={'baseline':[-10,-5,0],'density':[2,4,6,8,10],'reason':[3,5,7,9,12],'balanced':[2,4,6,8,10]}
    # Fixed research configuration, not retrospectively selected by validation results.
    chosen,th='reason',7
    summary=[];daily=[];audit=[]
    if a.backtest:
        for i in range(1,len(dates)):
            day=dates[i];cutoff=dates[i-1]
            if day<a.backtest_start:continue
            period=target_month(day)
            day_events=[x for x in reports if x['date']==day]
            # All website events count as real; report-month unknown are flagged, not silently dropped.
            known={x['ticker'] for x in day_events if x['month']==period}
            unknown={x['ticker'] for x in day_events if x['month'] is None}
            other={x['ticker'] for x in day_events if x['month'] not in (None,period)}
            audit.append(dict(date=day,target_month=period,all_site_events=len(day_events),target_month_events=len(known),unknown_month_events=len(unknown),other_month_events=len(other),unknown_tickers=' '.join(sorted(unknown)),other_tickers=' '.join(sorted(other))))
            for v,ths in variants.items():
                for threshold in ths:
                    picks=select(cutoff,day,dates,h,reports,v,threshold)
                    pred={x['ticker'] for x in picks};hits=len(pred&known)
                    daily.append(dict(variant=v,threshold=threshold,date=day,cutoff=cutoff,target_month=period,predicted=len(pred),hits=hits,actual=len(known),unknown_actual=len(unknown),all_site_events=len(day_events),tickers=' '.join(x['ticker'] for x in picks),hit_tickers=' '.join(sorted(pred&known)),missed_tickers=' '.join(sorted(known-pred))))
        for v,ths in variants.items():
            for threshold in ths:
                rs=[x for x in daily if x['variant']==v and x['threshold']==threshold]
                val=[x for x in rs if x['date']>='2026-10-08']
                def metrics(rr):
                    hits=sum(x['hits'] for x in rr);pred=sum(x['predicted'] for x in rr);actual=sum(x['actual'] for x in rr)
                    return dict(hits=hits,predictions=pred,actual=actual,precision=round(hits/pred,4) if pred else 0,recall=round(hits/actual,4) if actual else 0)
                m=metrics(rs);vm=metrics(val)
                summary.append(dict(variant=v,threshold=threshold,**m,validation_hits=vm['hits'],validation_predictions=vm['predictions'],validation_actual=vm['actual'],validation_precision=vm['precision'],validation_recall=vm['recall']))
        write_csv(out/'backtest_summary.csv',summary,list(summary[0]))
        write_csv(out/'backtest_daily.csv',daily,list(daily[0]))
        write_csv(out/'event_audit.csv',audit,list(audit[0]))
    prediction_day=next_day(a.asof,dates)
    picks=select(a.asof,prediction_day,dates,h,reports,chosen,th)
    write_csv(out/'predictions.csv',[dict(period=target_month(prediction_day),**x) for x in picks],['period','ticker','score','n1','n2','n3','n5','n10','n20','r1','r4','r6','gap','market','name'])
    (out/'predictions.json').write_text(json.dumps(dict(asof=a.asof,prediction_day=prediction_day,model=chosen,threshold=th,target_month=target_month(prediction_day),count=len(picks),items=picks,warning='Research only: no validated legal trigger rules; missing site announcements and unknown report months may bias evaluation'),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Attention records={len(at)}, site events={len(reports)}, month_known={sum(bool(x["month"]) for x in reports)}, month_unknown={sum(not x["month"] for x in reports)}')
    if audit:print(f'Backtest: days={len(audit)}, all site events={sum(x["all_site_events"] for x in audit)}, target-month={sum(x["target_month_events"] for x in audit)}, unknown-month={sum(x["unknown_month_events"] for x in audit)}, other-month={sum(x["other_month_events"] for x in audit)}')
    print(f'Prediction for {prediction_day}: {len(picks)} candidates, tickers={" ".join(x["ticker"] for x in picks)}')
if __name__=='__main__':main()
