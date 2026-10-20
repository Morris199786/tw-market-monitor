#!/usr/bin/env python3
"""自結預測研究版：無未來資訊、逐日回測、0–10檔動態名單。
執行：python self_report_predict.py --backtest --asof 2026-10-19
依賴：pip install requests
資料：data/self_reports.json（網站既有真實公告）；注意股來自 TWSE/TPEx 官方 JSON。
注意：只使用已公開的注意交易資料，非法律觸發規則判定。
"""
import argparse, collections, csv, datetime as dt, json, math, re, sys
from pathlib import Path
import requests

def get(url):
    r=requests.get(url,timeout=35,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();return r.json()

def official_attention(start,end):
    a=start.replace('-','');b=end.replace('-','')
    urls=[('上市',f'https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={a}&endDate={b}'),('上櫃',f'https://www.tpex.org.tw/www/zh-tw/bulletin/attention?startDate={start.replace("-","%2F")}&endDate={end.replace("-","%2F")}&response=json')]
    out=[]
    for market,url in urls:
        z=get(url)
        records=z.get('data',[]) if market=='上市' else (z.get('tables') or [{}])[0].get('data',[])
        for x in records:
            if len(x)<6 or not re.fullmatch(r'\d{4}',str(x[1])):continue
            m=re.search(r'(\d{3})/(\d{2})/(\d{2})',str(x[5]))
            if not m:continue
            date=f'{int(m[1])+1911}-{m[2]}-{m[3]}'
            out.append(dict(date=date,ticker=str(x[1]),name=str(x[2]),market=market,reason=str(x[4])))
    return out

def month_from_detail(x):
    p=x.get('monthly_period')
    if p and re.fullmatch(r'20\d\d-\d\d',str(p)):return p
    d=x.get('detail') or ''
    m=re.search(r'(\d{3})年\s*(\d{1,2})月',d)
    return f'{int(m[1])+1911}-{int(m[2]):02}' if m else None

def self_reports(path):
    j=json.loads(Path(path).read_text(encoding='utf-8'))
    raw=j.get('items',[])+j.get('diagnostics',{}).get('parse_failed',[])
    out=[];seen=set()
    for x in raw:
        ticker=str(x.get('ticker',''))
        date=str(x.get('publish_date',''))
        subject=x.get('subject') or ''
        if not re.fullmatch(r'\d{4}',ticker) or not re.fullmatch(r'20\d\d-\d\d-\d\d',date):continue
        if not re.search(r'注意交易資訊|多次達公[布佈]注意|注意交易',subject):continue
        if re.search(r'可轉換公司|轉換公司債',subject):continue
        k=(date,ticker)
        if k in seen:continue
        seen.add(k)
        out.append(dict(date=date,ticker=ticker,month=month_from_detail(x),name=x.get('name','')))
    return out

def target_month(date):
    # 每月初通常公布上個月的自結；實際月份仍以已公告資料為準
    y,m=map(int,date[:7].split('-'));return f'{y-1}-12' if m==1 else f'{y}-{m-1:02}'

def features(ticker,cutoff,dates,history):
    prior=[d for d in dates if d<=cutoff]
    entries=[x for x in history.get(ticker,[]) if x['date']<=cutoff]
    def window(n):return [x for x in entries if x['date'] in set(prior[-n:])]
    x3,x5,x10,x20=(window(n) for n in (3,5,10,20))
    def kinds(xs,k):return sum(bool(re.search(r'第'+k+r'款',x['reason'])) for x in xs)
    last=entries[-1]['date'] if entries else None
    gap=prior.index(cutoff)-prior.index(last) if last in prior else 99
    return dict(n1=len(window(1)),n3=len(x3),n5=len(x5),n10=len(x10),n20=len(x20),r1=kinds(x10,'一'),r4=kinds(x10,'四'),r6=kinds(x10,'六'),gap=gap,market=entries[-1]['market'] if entries else '',name=entries[-1]['name'] if entries else '')

def rank(f,variant):
    if variant=='baseline':return 3*f['n3']-3*(f['n3']-sum(1 for _ in []))-f['n5'] # overwritten below
    if variant=='density':return 2*f['n3']+f['n10']
    if variant=='reason':return 2*f['n3']+f['n10']+f['r6']
    if variant=='balanced':return 2*f['n3']+f['n10']+f['r6']+0.5*f['r1']+0.5*f['r4']-min(f['gap'],5)
    raise ValueError(variant)

def score(f,variant):
    if variant=='baseline':return 3*f['n3']-3*f['n2']-f['n5']
    return rank(f,variant)

def make_candidates(cutoff,dates,history,reports,variant,threshold,cap=10):
    # cutoff 為已知資訊的最後交易日；當天盤後公告的自結，預測時已知
    future=dt.date.fromisoformat(cutoff)+dt.timedelta(days=1)
    while future.weekday()>=5:future+=dt.timedelta(days=1)
    prediction_day=future.isoformat()
    period=target_month(prediction_day)
    excluded={x['ticker'] for x in reports if x['date']<=cutoff and x['month']==period}
    candidates=[]
    for ticker in history:
        if ticker in excluded:continue
        f=features(ticker,cutoff,dates,history)
        f['n2']=sum(x['date'] in set([d for d in dates if d<=cutoff][-2:]) for x in history[ticker])
        if f['n10']==0:continue
        if variant=='baseline' and f['n1']==0:continue
        s=score(f,variant)
        if s<threshold:continue
        candidates.append(dict(ticker=ticker,score=round(s,3),**f))
    return sorted(candidates,key=lambda x:(-x['score'],x['ticker']))[:cap],period

def write_csv(path,rows):
    if not rows:return
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser();p.add_argument('--reports',default='data/self_reports.json');p.add_argument('--start',default='2026-09-01');p.add_argument('--asof',default=dt.date.today().isoformat());p.add_argument('--backtest',action='store_true');p.add_argument('--out',default='self_report_model');a=p.parse_args()
    at=official_attention(a.start,a.asof);reports=self_reports(a.reports)
    dates=sorted(set(x['date'] for x in at));history=collections.defaultdict(list)
    for x in at:history[x['ticker']].append(x)
    for xs in history.values():xs.sort(key=lambda x:x['date'])
    Path(a.out).mkdir(parents=True,exist_ok=True)
    variants=['baseline','density','reason','balanced'];thresholds={'baseline':[-10,-5,0], 'density':[2,4,6,8,10], 'reason':[3,5,7,9,12], 'balanced':[2,4,6,8,10]}
    if a.backtest:
        # 訓練期與驗證期完全分開；沒有足夠歷史則不宣稱可泛化
        day_rows=[];summ=[]
        for v in variants:
            for th in thresholds[v]:
                tp=pred=actual=0;v_tp=v_pred=v_actual=0
                for i in range(1,len(dates)):
                    day=dates[i];cutoff=dates[i-1]
                    if day<'2026-09-29':continue
                    picks,period=make_candidates(cutoff,dates,history,reports,v,th)
                    # 僅計網站已擷取、且公告屬目標月份的事件；未知月份另列不作陰性
                    truth={x['ticker'] for x in reports if x['date']==day and x['month']==period}
                    hits=sum(x['ticker'] in truth for x in picks)
                    tp+=hits;pred+=len(picks);actual+=len(truth)
                    if day>='2026-10-08':v_tp+=hits;v_pred+=len(picks);v_actual+=len(truth)
                    day_rows.append(dict(variant=v,threshold=th,date=day,predicted=len(picks),hits=hits,actual=len(truth),tickers=' '.join(x['ticker'] for x in picks)))
                summ.append(dict(variant=v,threshold=th,hits=tp,predictions=pred,actual=actual,precision=round(tp/pred,4) if pred else 0,recall=round(tp/actual,4) if actual else 0,validation_hits=v_tp,validation_predictions=v_pred,validation_actual=v_actual,validation_precision=round(v_tp/v_pred,4) if v_pred else 0,validation_recall=round(v_tp/v_actual,4) if v_actual else 0))
        write_csv(Path(a.out)/'backtest_daily.csv',day_rows);write_csv(Path(a.out)/'backtest_summary.csv',summ)
        # 固定採用事先定義的基準門檻，避免從同段資料挑最好的再報績效
        chosen='reason';th=7
    else:chosen='reason';th=7
    picks,period=make_candidates(a.asof,dates,history,reports,chosen,th)
    write_csv(Path(a.out)/'predictions.csv',[dict(period=period,**x) for x in picks])
    (Path(a.out)/'predictions.json').write_text(json.dumps(dict(asof=a.asof,model=chosen,threshold=th,target_month=period,count=len(picks),items=picks,warning='研究模型，尚未驗證法規觸發條件；公告缺漏可能影響回測'),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'資料：注意紀錄{len(at)}筆，網站自結{len(reports)}筆；預測{len(picks)}檔；結果：{a.out}/')
if __name__=='__main__':main()
