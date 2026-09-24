from sources import *

def build_period(history, market, kind, days):
    use=history[-days:]; sums={}
    for h in use:
        closes=h.get("closes",{})
        for t,r in h.get(market,{}).items():
            price=closes.get(t,{}).get("price",0); shares=r.get(kind,0)
            x=sums.setdefault(t,{"ticker":t,"name":r.get("name",""),"shares":0,"amount":0.0})
            x["shares"]+=shares; x["amount"]+=shares*price
    arr=list(sums.values())
    for x in arr:x["amount_100m"]=x["amount"]/1e8
    buy=sorted([x for x in arr if x["amount"]>0],key=lambda x:x["amount"],reverse=True)[:20]
    sell=sorted([x for x in arr if x["amount"]<0],key=lambda x:x["amount"])[:20]
    latest=use[-1] if use else {}
    for x in buy+sell:
        q=latest.get("closes",{}).get(x["ticker"],{}); x["change_pct"]=q.get("change_pct")
    return {"buy":buy,"sell":sell,"complete":len(use)>=days,"days_used":len(use)}

def main():
    mfiles=sorted((ROOT/"data/history/market").glob("*.json"))
    markets=[load_json(p,{}) for p in mfiles if load_json(p,{}).get("stocks")][-5:]
    if not markets:
        raise RuntimeError("market history missing")

    hist=[]
    for m in markets:
        date=m.get("date"); closes=m.get("stocks",{}); p=ROOT/f"data/history/institutional/{date}.json"
        old=load_json(p,{})
        need=not old.get("twse") or not old.get("tpex")
        if need:
            try: tw=fetch_twse_institutional(date)
            except Exception as e: print("twse inst fail",date,e); tw={}
            try: ot=fetch_tpex_institutional(date)
            except Exception as e: print("tpex inst fail",date,e); ot={}
            old={"date":date,"updated_at":now_tpe().isoformat(timespec="minutes"),"twse":tw,"tpex":ot,"closes":closes}
            save_json(p,old); print("backfill inst",date,len(tw),len(ot))
        else:
            old["closes"]=closes
        if old.get("twse") or old.get("tpex"): hist.append(old)

    today=markets[-1].get("date")
    out={"date":today,"periods":{}}
    for period,days in [("1d",1),("3d",3),("5d",5)]:
        out["periods"][period]={}
        for market in ("twse","tpex"):
            out["periods"][period][market]={}
            for kind in ("foreign","trust","dealer","total"):
                out["periods"][period][market][kind]=build_period(hist,market,kind,days)
    save_json(ROOT/"data/institutional.json",out)
    print("institutional history",len(hist),"latest",today)

if __name__=="__main__": main()
