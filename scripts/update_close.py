from sources import *
from datetime import timedelta

def tech(master,ticker):
    ind=str(master.get(ticker,{}).get("industry",""))
    cfg=load_json(ROOT/"config.json",{})
    return any(x in ind for x in cfg.get("tech_industries",[]))

def history_files():
    return sorted((ROOT/"data/history/market").glob("*.json"))

def main():
    master_data=load_json(ROOT/"data/master.json",{})
    master=master_data.get("stocks",{})
    if not master:
        master=fetch_master()
        save_json(ROOT/"data/master.json",{"updated_at":now_tpe().isoformat(timespec="minutes"),"stocks":master})

    twse=fetch_twse_latest_quotes()
    tpex=fetch_tpex_latest_quotes()
    quotes={**twse,**tpex}
    today=now_tpe().date().isoformat()

    # 保留普通股，公司主檔中必須存在
    filtered={t:q for t,q in quotes.items() if t in master and ordinary_ticker(t)}
    snap={"date":today,"updated_at":now_tpe().isoformat(timespec="minutes"),"stocks":filtered}
    save_json(ROOT/f"data/history/market/{today}.json",snap)
    save_json(ROOT/"data/market_latest.json",snap)

    topn=load_json(ROOT/"config.json",{}).get("top_n",{}).get("turnover",30)
    turnover={"date":today,"twse":[],"tpex":[]}
    for market in ("twse","tpex"):
        arr=[q for q in filtered.values() if q["market"]==market]
        arr.sort(key=lambda x:x.get("turnover",0),reverse=True)
        turnover[market]=arr[:topn]
    save_json(ROOT/"data/turnover.json",turnover)

    # 突然放量 + 進階篩選需要至少 21 個交易日收盤歷史
    hist=[]
    for p in history_files()[-25:]:
        d=load_json(p,{})
        if d.get("stocks"):hist.append(d)
    latest=hist[-1] if hist else snap

    volume_items=[]
    screen_items=[]
    if len(hist)>=6:
        for t,q in latest["stocks"].items():
            if not tech(master,t): continue
            prior=[h["stocks"].get(t) for h in hist[:-1] if h["stocks"].get(t)]
            last5=prior[-5:]
            if len(last5)<5 or any(x.get("volume",0)<=0 for x in last5): continue
            avg5=sum(x["volume"] for x in last5)/5
            ratio=q["volume"]/avg5 if avg5 else 0
            volume_items.append({**q,"volume_ratio_5d":ratio,"low_base":avg5<100000})

            if len(prior)>=20:
                avg20=sum(x["volume"] for x in prior[-20:])/20
                seq=(prior+[q])
                avg3=sum(x["volume"] for x in seq[-3:])/3
                avg5i=sum(x["volume"] for x in seq[-5:])/5
                avg10=sum(x["volume"] for x in seq[-10:])/10
                lots=q["volume"]/1000
                if (avg20>0 and
                    q["volume"]>=avg20*1.3 and q["volume"]<=avg20*2.0 and
                    avg3>avg5i>avg10 and lots>=1000):
                    screen_items.append({**q,"volume_ratio_20d":q["volume"]/avg20,
                                         "avg3":round(avg3/1000),"avg5":round(avg5i/1000),"avg10":round(avg10/1000)})
    volume_items.sort(key=lambda x:x["volume_ratio_5d"],reverse=True)
    screen_items.sort(key=lambda x:x["volume_ratio_5d"],reverse=True)
    save_json(ROOT/"data/volume.json",{
        "date":today,"complete":len(hist)>=6,"history_days":len(hist),"items":volume_items[:50]
    })
    save_json(ROOT/"data/screener.json",{
        "date":today,"complete":len(hist)>=21,"history_days":len(hist),"items":screen_items
    })
    print("close",len(filtered),"history",len(hist),"screen",len(screen_items))

if __name__=="__main__": main()
