from sources import *

def main():
    cfg=load_json(ROOT/"data/sectors.json",{})
    master=load_json(ROOT/"data/master.json",{}).get("stocks",{})
    if not master:
        master=fetch_master()
        save_json(ROOT/"data/master.json",{"updated_at":now_tpe().isoformat(timespec="minutes"),"stocks":master})
    tickers=sorted({s["ticker"] for sec in cfg.get("sectors",[]) for s in sec["stocks"]})
    quotes=fetch_mis_quotes(tickers)

    sectors=[]
    for sec in cfg.get("sectors",[]):
        members=[]
        weighted=0.0; capsum=0.0; missing=[]
        for s in sec["stocks"]:
            t=s["ticker"]; q=quotes.get(t); m=master.get(t,{})
            shares=int(m.get("shares_issued") or 0)
            if not q or shares<=0:
                missing.append(t)
                members.append({"ticker":t,"name":s["name"],"price":q.get("price") if q else None,
                                "change_pct":q.get("change_pct") if q else None,"market_cap":None,"weight":None})
                continue
            cap=q["price"]*shares
            capsum+=cap; weighted+=q["change_pct"]*cap
            members.append({"ticker":t,"name":s["name"],"price":q["price"],
                            "change_pct":round(q["change_pct"],2),"market_cap":cap,"weight":None})
        pct=weighted/capsum if capsum else None
        for x in members:
            if x["market_cap"] is not None and capsum:
                x["weight"]=x["market_cap"]/capsum
        sectors.append({"name":sec["name"],"change_pct":round(pct,2) if pct is not None else None,
                        "complete":len(missing)==0,"missing":missing,"stocks":members})
    save_json(ROOT/"data/heatmap.json",{
        "updated_at":now_tpe().strftime("%Y/%m/%d %H:%M"),
        "method":"market_cap_weighted",
        "source":"TWSE MIS + TWSE/TPEx company master",
        "sectors":sectors
    })
    print("heatmap",len(sectors),"quotes",len(quotes))

if __name__=="__main__": main()
