from sources import *

def field(r,names): return pick(r,names,None)

def normalize_rows(rows):
    out=[]
    for r in rows:
        t=str(field(r,["證券代號","stockCode","SecurityCode"]) or "").strip()
        if not ordinary_ticker(t):continue
        date=str(field(r,["資料日期","date","DataDate"]) or "").strip()
        level=iv(field(r,["持股分級","level","HoldingLevel"]))
        shares=iv(field(r,["股數","shares","Shares"]))
        pct=n(field(r,["占集保庫存數比例%","占集保庫存數比例 (%)","percentage","Percentage"]))
        if not date or not level: continue
        out.append((date,t,level,shares,pct))
    return out

def aggregate(rows):
    by={}
    for date,t,level,shares,pct in rows:
        d=by.setdefault(t,{"date":date,"total":0,"400":0,"1000":0})
        # TDCC level 17 is total; 13=400,001~600,000, 14=600,001~1,000,000, 15=>1,000,001
        if level==17:d["total"]=shares
        if level in (13,14,15):d["400"]+=shares
        if level==15:d["1000"]+=shares
    for t,d in by.items():
        total=d["total"]
        d["400_ratio"]=d["400"]/total*100 if total else 0
        d["1000_ratio"]=d["1000"]/total*100 if total else 0
    return by

def main():
    rows=normalize_rows(fetch_tdcc_distribution())
    if not rows:
        raise RuntimeError("TDCC 1-5 returned no usable rows")
    date=max(x[0] for x in rows)
    rows=[x for x in rows if x[0]==date]
    latest=aggregate(rows)
    snap_path=ROOT/f"data/history/holders/{date}.json"
    save_json(snap_path,{"date":date,"stocks":latest})

    files=sorted((ROOT/"data/history/holders").glob("*.json"))
    prev=None
    if len(files)>=2:
        prev=load_json(files[-2],{})
    market=load_json(ROOT/"data/market_latest.json",{}).get("stocks",{})
    master=load_json(ROOT/"data/master.json",{}).get("stocks",{})
    tech_inds=load_json(ROOT/"config.json",{}).get("tech_industries",[])

    out={"date":date,"previous_date":prev.get("date") if prev else None,
         "complete":bool(prev),"twse":{"400":[],"1000":[]},"tpex":{"400":[],"1000":[]}}
    if prev:
        pstocks=prev.get("stocks",{})
        for t,d in latest.items():
            if t not in pstocks or t not in master:continue
            if not any(x in str(master[t].get("industry","")) for x in tech_inds):continue
            mk=master[t]["market"]
            q=market.get(t,{})
            for kind in ("400","1000"):
                cur=d[f"{kind}_ratio"]; old=pstocks[t].get(f"{kind}_ratio",0)
                delta=cur-old
                if delta<=0:continue
                out[mk][kind].append({
                    "ticker":t,"name":master[t].get("name",""),"ratio":cur,"delta":delta,
                    "week_change_pct":q.get("change_pct"),"score":0
                })
        for mk in ("twse","tpex"):
            for kind in ("400","1000"):
                arr=sorted(out[mk][kind],key=lambda x:x["delta"],reverse=True)[:30]
                for i,x in enumerate(arr):x["score"]=round(100*(len(arr)-i)/max(1,len(arr)),1)
                out[mk][kind]=arr
    save_json(ROOT/"data/holders.json",out)
    print("holders",date,"previous",out["previous_date"])

if __name__=="__main__": main()
