from sources import *
import csv, io
from datetime import datetime, timedelta

def field(r,names): return pick(r,names,None)

def normalize_rows(rows):
    out=[]
    for r in rows:
        t=str(field(r,["證券代號","stockCode","SecurityCode"]) or "").strip()
        if not ordinary_ticker(t):continue
        date=str(field(r,["資料日期","date","DataDate"]) or "").strip()
        level=iv(field(r,["持股分級","level","HoldingLevel"])); shares=iv(field(r,["股數","shares","Shares"]))
        pct=n(field(r,["占集保庫存數比例%","佔集保庫存數比例%","占集保庫存數比例 (%)","percentage","Percentage"]))
        if not date or not level: continue
        out.append((date,t,level,shares,pct))
    return out

def aggregate(rows):
    by={}
    for date,t,level,shares,pct in rows:
        d=by.setdefault(t,{"date":date,"total":0,"400":0,"1000":0})
        if level==17:d["total"]=shares
        if level in (13,14,15):d["400"]+=shares
        if level==15:d["1000"]+=shares
    for t,d in by.items():
        total=d["total"]; d["400_ratio"]=d["400"]/total*100 if total else 0; d["1000_ratio"]=d["1000"]/total*100 if total else 0
    return by

def fetch_archive_before(date):
    dt=datetime.strptime(date,"%Y%m%d").date()
    for back in range(1,22):
        d=dt-timedelta(days=back)
        if d.weekday()!=4: continue
        url=f"https://raw.githubusercontent.com/wirelessr/tdcc-opendata-archive/main/snapshots/{d.year}/{d.isoformat()}.csv"
        try:
            r=S.get(url,timeout=30)
            if r.status_code!=200: continue
            rows=list(csv.DictReader(io.StringIO(r.text.lstrip("\ufeff"))))
            nr=normalize_rows(rows)
            if nr:
                dd=max(x[0] for x in nr); return {"date":dd,"stocks":aggregate([x for x in nr if x[0]==dd])}
        except Exception as e: print("archive fail",d,e)
    return None

def tracked_tickers():
    d=load_json(ROOT/"data/sectors.json",{})
    return {str(x.get("ticker")) for s in d.get("sectors",[]) for x in s.get("stocks",[]) if x.get("ticker")}

def main():
    rows=normalize_rows(fetch_tdcc_distribution())
    if not rows: raise RuntimeError("TDCC 1-5 returned no usable rows")
    date=max(x[0] for x in rows); rows=[x for x in rows if x[0]==date]; latest=aggregate(rows)
    save_json(ROOT/f"data/history/holders/{date}.json",{"date":date,"stocks":latest})

    files=sorted((ROOT/"data/history/holders").glob("*.json")); prev=None
    if len(files)>=2: prev=load_json(files[-2],{})
    if not prev:
        prev=fetch_archive_before(date)
        if prev: save_json(ROOT/f"data/history/holders/{prev['date']}.json",prev)

    market=load_json(ROOT/"data/market_latest.json",{}).get("stocks",{}); master=load_json(ROOT/"data/master.json",{}).get("stocks",{}); tracked=tracked_tickers()
    out={"date":date,"previous_date":prev.get("date") if prev else None,"complete":bool(prev),"twse":{"400":[],"1000":[]},"tpex":{"400":[],"1000":[]}}
    if prev:
        pstocks=prev.get("stocks",{})
        for t,d in latest.items():
            if t not in pstocks or t not in master:continue
            if tracked and t not in tracked:continue
            mk=master[t]["market"]; q=market.get(t,{})
            for kind in ("400","1000"):
                cur=d[f"{kind}_ratio"]; old=pstocks[t].get(f"{kind}_ratio",0); delta=cur-old
                if delta<=0:continue
                out[mk][kind].append({"ticker":t,"name":master[t].get("name",""),"ratio":cur,"delta":delta,"week_change_pct":q.get("change_pct"),"score":0})
        for mk in ("twse","tpex"):
            for kind in ("400","1000"):
                arr=sorted(out[mk][kind],key=lambda x:x["delta"],reverse=True)[:30]
                for i,x in enumerate(arr):x["score"]=round(100*(len(arr)-i)/max(1,len(arr)),1)
                out[mk][kind]=arr
    save_json(ROOT/"data/holders.json",out); print("holders",date,"previous",out["previous_date"])

if __name__=="__main__": main()
