from sources import *
from datetime import timedelta

def tracked_tickers():
    d=load_json(ROOT/"data/sectors.json",{})
    return {str(x.get("ticker")) for s in d.get("sectors",[]) for x in s.get("stocks",[]) if x.get("ticker")}

def history_files():
    return sorted((ROOT/"data/history/market").glob("*.json"))

def backfill_market(master, target=21):
    existing={p.stem for p in history_files()}
    have=sum(1 for p in history_files() if load_json(p,{}).get("stocks"))
    if have>=target:return
    d=now_tpe().date()-timedelta(days=1)
    tries=0
    while have<target and tries<50:
        ds=d.isoformat(); tries+=1
        if ds not in existing:
            try:
                tw=fetch_twse_quotes_by_date(ds); ot=fetch_tpex_quotes_by_date(ds)
                q={**tw,**ot}; q={t:x for t,x in q.items() if t in master and ordinary_ticker(t)}
                if len(q)>200:
                    save_json(ROOT/f"data/history/market/{ds}.json",{"date":ds,"updated_at":now_tpe().isoformat(timespec="minutes"),"stocks":q})
                    have+=1; existing.add(ds); print("backfill market",ds,len(q),have)
            except Exception as e:
                print("skip market",ds,e)
        d-=timedelta(days=1)

def main():
    master_data=load_json(ROOT/"data/master.json",{}); master=master_data.get("stocks",{})
    if not master:
        master=fetch_master(); save_json(ROOT/"data/master.json",{"updated_at":now_tpe().isoformat(timespec="minutes"),"stocks":master})

    twse=fetch_twse_latest_quotes(); tpex=fetch_tpex_latest_quotes(); quotes={**twse,**tpex}
    today=now_tpe().date().isoformat()
    filtered={t:q for t,q in quotes.items() if t in master and ordinary_ticker(t)}
    snap={"date":today,"updated_at":now_tpe().isoformat(timespec="minutes"),"stocks":filtered}
    save_json(ROOT/f"data/history/market/{today}.json",snap); save_json(ROOT/"data/market_latest.json",snap)

    backfill_market(master,21)

    topn=load_json(ROOT/"config.json",{}).get("top_n",{}).get("turnover",30)
    turnover={"date":today,"twse":[],"tpex":[]}
    for market in ("twse","tpex"):
        arr=[q for q in filtered.values() if q["market"]==market]; arr.sort(key=lambda x:x.get("turnover",0),reverse=True)
        turnover[market]=arr[:topn]
    save_json(ROOT/"data/turnover.json",turnover)

    hist=[]
    for p in history_files()[-30:]:
        d=load_json(p,{})
        if d.get("stocks"):hist.append(d)
    latest=hist[-1] if hist else snap
    tracked=tracked_tickers()
    volume_items=[]; screen_items=[]
    if len(hist)>=6:
        for t,q in latest["stocks"].items():
            if tracked and t not in tracked: continue
            prior=[h["stocks"].get(t) for h in hist[:-1] if h["stocks"].get(t)]
            last5=prior[-5:]
            if len(last5)<5 or any(x.get("volume",0)<=0 for x in last5): continue
            avg5=sum(x["volume"] for x in last5)/5; ratio=q["volume"]/avg5 if avg5 else 0
            volume_items.append({**q,"volume_ratio_5d":ratio,"low_base":avg5<100000})
            if len(prior)>=20:
                avg20=sum(x["volume"] for x in prior[-20:])/20; seq=prior+[q]
                avg3=sum(x["volume"] for x in seq[-3:])/3; avg5i=sum(x["volume"] for x in seq[-5:])/5; avg10=sum(x["volume"] for x in seq[-10:])/10
                lots=q["volume"]/1000
                if avg20>0 and q["volume"]>=avg20*1.3 and q["volume"]<=avg20*2.0 and avg3>avg5i>avg10 and lots>=1000:
                    screen_items.append({**q,"volume_ratio_5d":ratio,"volume_ratio_20d":q["volume"]/avg20,
                                         "avg3":round(avg3/1000),"avg5":round(avg5i/1000),"avg10":round(avg10/1000)})
    volume_items.sort(key=lambda x:x["volume_ratio_5d"],reverse=True); screen_items.sort(key=lambda x:x["volume_ratio_5d"],reverse=True)
    save_json(ROOT/"data/volume.json",{"date":today,"complete":len(hist)>=6,"history_days":len(hist),"items":volume_items[:50]})
    save_json(ROOT/"data/screener.json",{"date":today,"complete":len(hist)>=21,"history_days":len(hist),"items":screen_items})
    print("close",len(filtered),"history",len(hist),"volume",len(volume_items),"screen",len(screen_items))

if __name__=="__main__": main()
