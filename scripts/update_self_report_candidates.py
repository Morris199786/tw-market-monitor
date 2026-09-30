#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_self_report_candidates.py
目的：
1. 抓 TWSE / TPEx 官方注意股票歷史
2. 依上市 / 上櫃分開計算「可能被要求公布近期財務資訊」候選分數
3. 讀 data/self_reports_history.json，避免近期已公告者重複高分
4. 支援 --backtest，回測既有 attention-trading 自結公告
5. 產出 data/self_report_candidates.json

注意：
- 這是候選模型，不代表公司依法「一定」會公告
- 不把處置門檻直接當成自結門檻
- 第9~13款在 TWSE 處置規則中不納入處置，因此 primary(1~8) 與 secondary(9~13) 分開計分
"""
from __future__ import annotations
import argparse, json, re, time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "self_report_candidates.json"
HISTORY = DATA / "self_reports_history.json"

S = requests.Session()
S.headers.update({"User-Agent":"Mozilla/5.0 self-report-candidate/1.0"})

TWSE_NOTICE = "https://www.twse.com.tw/rwd/zh/announcement/notice"
# TPEx endpoint may change; parser accepts common field names and fails visibly in source_status
TPEX_NOTICE_CANDIDATES = [
    "https://www.tpex.org.tw/www/zh-tw/announcement/attention",
    "https://www.tpex.org.tw/web/stock/aftertrading/attention_information/attention_information_result.php",
]

CN_NUM = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,
          "十一":11,"十二":12,"十三":13}

def load(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def iso_date(v):
    s=str(v or "").strip().replace(".","/").replace("-","/")
    m=re.search(r"(\d{2,4})/(\d{1,2})/(\d{1,2})",s)
    if not m: return ""
    y=int(m.group(1)); y=y+1911 if y<1911 else y
    return f"{y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

def ordinary(t):
    return bool(re.fullmatch(r"\d{4}",str(t or "").strip()))

def clauses(text):
    out=set()
    for x in re.findall(r"第([一二三四五六七八九十]{1,3})款",str(text or "")):
        if x in CN_NUM: out.add(CN_NUM[x])
    return sorted(out)

def get_json(url, params=None):
    r=S.get(url,params=params,timeout=30); r.raise_for_status()
    return r.json()

def fetch_twse(start,end):
    js=get_json(TWSE_NOTICE, {
        "response":"json","startDate":start.replace("-",""),
        "endDate":end.replace("-",""),"stockNo":"","querytype":"1","selectType":"","sortKind":"DATE"
    })
    fields=js.get("fields") or []
    data=js.get("data") or []
    rows=[]
    for a in data:
        d=dict(zip(fields,a))
        ticker=str(d.get("證券代號","")).strip()
        if not ordinary(ticker): continue
        detail=str(d.get("注意交易資訊",""))
        dt=iso_date(d.get("日期",""))
        if not dt: continue
        cs=clauses(detail)
        rows.append({"market":"twse","ticker":ticker,"name":str(d.get("證券名稱","")).strip(),
                     "date":dt,"clauses":cs,"primary":any(1<=x<=8 for x in cs),
                     "detail":detail})
    return rows

def _walk_rows(obj):
    if isinstance(obj,list):
        for x in obj:
            if isinstance(x,dict): yield x
    elif isinstance(obj,dict):
        for k in ("data","aaData","rows","result"):
            if isinstance(obj.get(k),list):
                yield from _walk_rows(obj[k])

def fetch_tpex(start,end):
    errors=[]
    for url in TPEX_NOTICE_CANDIDATES:
        try:
            r=S.get(url,params={"startDate":start.replace("-","/"),"endDate":end.replace("-","/"),
                                "response":"json"},timeout=30)
            r.raise_for_status()
            try: js=r.json()
            except Exception: 
                errors.append(url+":not_json"); continue
            rows=[]
            for d in _walk_rows(js):
                ticker=str(d.get("SecuritiesCompanyCode") or d.get("證券代號") or d.get("股票代號") or d.get("code") or "").strip()
                if not ordinary(ticker): continue
                dt=iso_date(d.get("Date") or d.get("日期") or d.get("date") or "")
                if not dt: continue
                name=str(d.get("CompanyName") or d.get("證券名稱") or d.get("股票名稱") or d.get("name") or "").strip()
                detail=str(d.get("AttentionInformation") or d.get("注意交易資訊") or d.get("原因") or d)
                cs=clauses(detail)
                rows.append({"market":"tpex","ticker":ticker,"name":name,"date":dt,"clauses":cs,
                             "primary":any(1<=x<=8 for x in cs) if cs else True,"detail":detail})
            if rows: return rows, {"ok":True,"url":url,"error":""}
            errors.append(url+":empty")
        except Exception as e: errors.append(url+":"+type(e).__name__)
    return [], {"ok":False,"url":"","error":"; ".join(errors)}

def trading_dates(rows, asof):
    ds=sorted({r["date"] for r in rows if r["date"]<=asof})
    return ds

def features(events, asof, calendar):
    ev=sorted({x["date"] for x in events if x["date"]<=asof})
    primary=sorted({x["date"] for x in events if x["date"]<=asof and x["primary"]})
    pos={d:i for i,d in enumerate(calendar)}
    ai=pos.get(asof, len(calendar)-1)
    def n(win, arr=ev):
        allowed=set(calendar[max(0,ai-win+1):ai+1])
        return sum(d in allowed for d in arr)
    consecutive=0
    evset=set(ev)
    for d in reversed(calendar[:ai+1]):
        if d in evset: consecutive+=1
        else: break
    last=ev[-1] if ev else ""
    days_since=(date.fromisoformat(asof)-date.fromisoformat(last)).days if last else 999
    return {
        "today_attention": asof in evset,
        "attention_3d":n(3),"attention_5d":n(5),"attention_10d":n(10),"attention_30d":n(30),
        "primary_5d":n(5,primary),"primary_10d":n(10,primary),"primary_30d":n(30,primary),
        "consecutive":consecutive,"days_since_attention":days_since,
        "last_attention":last,
    }

def score_feature(f, market, days_since_self=999):
    # 第一版透明規則；回測後再校正，不假裝是官方機率
    s=0
    reasons=[]
    if f["today_attention"]: s+=24; reasons.append("今日達注意")
    if f["consecutive"]>=2: s+=min(20,7*f["consecutive"]); reasons.append(f'連續{f["consecutive"]}個交易日注意')
    if f["attention_5d"]>=2: s+=min(18,5*f["attention_5d"]); reasons.append(f'近5日注意{f["attention_5d"]}次')
    if f["attention_10d"]>=3: s+=min(14,3*f["attention_10d"]); reasons.append(f'近10日注意{f["attention_10d"]}次')
    if f["attention_30d"]>=5: s+=min(12,f["attention_30d"]); reasons.append(f'近30日注意{f["attention_30d"]}次')
    if f["primary_10d"]>=2: s+=10; reasons.append("近期多次屬第1~8款")
    if f["primary_30d"]==0 and f["attention_30d"]>0: s-=8; reasons.append("近期僅次要注意款次")
    if days_since_self<=5: s-=30; reasons.append("5日內已公布過注意交易自結")
    elif days_since_self<=15: s-=15; reasons.append("15日內已公布過注意交易自結")
    # 上櫃先略提高「多次注意」權重，之後由回測資料校正
    if market=="tpex" and f["attention_10d"]>=2: s+=5
    return max(0,min(100,s)),reasons

def self_reports():
    h=load(HISTORY,{"items":[]})
    out=[]
    for x in h.get("items",[]):
        subj=(x.get("subject") or "")+" "+(x.get("detail") or "")
        if x.get("monthly_eps") is None or x.get("quarter_eps") is None: continue
        if "注意交易" not in subj: continue
        out.append({"ticker":str(x.get("ticker","")),"name":x.get("name",""),
                    "date":x.get("publish_date",""),"market":x.get("market","")})
    return out

def last_self_before(reports,ticker,asof):
    ds=sorted(x["date"] for x in reports if x["ticker"]==ticker and x["date"]<asof)
    if not ds:return 999
    return (date.fromisoformat(asof)-date.fromisoformat(ds[-1])).days

def rank(asof, all_rows, reports):
    cal=trading_dates(all_rows,asof)
    grouped=defaultdict(list)
    meta={}
    for r in all_rows:
        if r["date"]<=asof:
            grouped[(r["market"],r["ticker"])].append(r)
            meta[(r["market"],r["ticker"])]=r
    ans=[]
    for key,ev in grouped.items():
        market,ticker=key
        f=features(ev,asof,cal)
        # 候選至少近期真的有注意，避免全市場噪音
        if f["attention_10d"]==0: continue
        dss=last_self_before(reports,ticker,asof)
        sc,reasons=score_feature(f,market,dss)
        if sc<25: continue
        m=meta[key]
        ans.append({"ticker":ticker,"name":m["name"],"market":market,"score":sc,
                    "level":"高" if sc>=70 else "中" if sc>=50 else "觀察",
                    **f,"days_since_last_self_report":None if dss==999 else dss,
                    "reasons":reasons})
    return sorted(ans,key=lambda x:(-x["score"],x["ticker"]))

def backtest(rows,reports):
    tests=[]
    hits={3:0,5:0,10:0}
    for target in reports:
        asof=target["date"]
        ranked=rank(asof,rows,[r for r in reports if r["date"]<asof])
        tickers=[x["ticker"] for x in ranked]
        rec=next((x for x in ranked if x["ticker"]==target["ticker"]),None)
        rankno=tickers.index(target["ticker"])+1 if target["ticker"] in tickers else None
        for k in hits:
            if rankno and rankno<=k:hits[k]+=1
        tests.append({"date":asof,"ticker":target["ticker"],"name":target["name"],
                      "rank":rankno,"score":rec["score"] if rec else 0,
                      "features":rec or {}})
    n=len(tests)
    return {"samples":n,"top3_recall":hits[3]/n if n else None,
            "top5_recall":hits[5]/n if n else None,"top10_recall":hits[10]/n if n else None,
            "cases":tests}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--days",type=int,default=60)
    ap.add_argument("--backtest",action="store_true")
    args=ap.parse_args()
    today=date.today().isoformat()
    start=(date.today()-timedelta(days=args.days+20)).isoformat()
    status={}
    try:
        tw=fetch_twse(start,today); status["twse"]={"ok":True,"rows":len(tw)}
    except Exception as e:
        tw=[]; status["twse"]={"ok":False,"rows":0,"error":repr(e)}
    tp,tpst=fetch_tpex(start,today); status["tpex"]={**tpst,"rows":len(tp)}
    rows=tw+tp
    reports=self_reports()
    candidates=rank(today,rows,reports)
    obj={"updated_at":datetime.now().astimezone().isoformat(timespec="minutes"),
         "asof":today,"model":"rule-v1","disclaimer":"候選分數，不是官方公告機率",
         "source_status":status,"candidates":candidates}
    if args.backtest: obj["backtest"]=backtest(rows,reports)
    save(OUT,obj)
    print(json.dumps({"sources":status,"candidates":len(candidates),
                      "top":candidates[:10],"backtest":obj.get("backtest")},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
