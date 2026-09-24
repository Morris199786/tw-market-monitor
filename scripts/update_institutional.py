from sources import *

def build_period(history, market, kind, days):
    use=history[-days:]
    sums={}
    for h in use:
        closes=h.get("closes",{})
        for t,r in h.get(market,{}).items():
            price=closes.get(t,{}).get("price",0)
            shares=r.get(kind,0)
            x=sums.setdefault(t,{"ticker":t,"name":r.get("name",""),"shares":0,"amount":0.0})
            x["shares"]+=shares
            x["amount"]+=shares*price
    arr=list(sums.values())
    for x in arr:x["amount_100m"]=x["amount"]/1e8
    buy=sorted([x for x in arr if x["amount"]>0],key=lambda x:x["amount"],reverse=True)[:20]
    sell=sorted([x for x in arr if x["amount"]<0],key=lambda x:x["amount"])[:20]
    latest=use[-1] if use else {}
    for x in buy+sell:
        q=latest.get("closes",{}).get(x["ticker"],{})
        x["change_pct"]=q.get("change_pct")
    return {"buy":buy,"sell":sell,"complete":len(use)>=days,"days_used":len(use)}

def main():
    latest=load_json(ROOT/"data/market_latest.json",{})
    closes=latest.get("stocks",{})
    today=latest.get("date") or now_tpe().date().isoformat()
    tw=fetch_twse_institutional(today)
    ot=fetch_tpex_institutional()
    snap={"date":today,"updated_at":now_tpe().isoformat(timespec="minutes"),
          "twse":tw,"tpex":ot,"closes":closes}
    save_json(ROOT/f"data/history/institutional/{today}.json",snap)

    files=sorted((ROOT/"data/history/institutional").glob("*.json"))[-7:]
    hist=[load_json(p,{}) for p in files]
    out={"date":today,"periods":{}}
    for period,days in [("1d",1),("3d",3),("5d",5)]:
        out["periods"][period]={}
        for market in ("twse","tpex"):
            out["periods"][period][market]={}
            for kind in ("foreign","trust","dealer","total"):
                out["periods"][period][market][kind]=build_period(hist,market,kind,days)
    save_json(ROOT/"data/institutional.json",out)
    print("institutional",len(tw),len(ot), "history",len(hist))

if __name__=="__main__": main()
