from sources import *

def tracked_candidates(master):
    d=load_json(ROOT/"data/sectors.json",{})
    tickers={str(x.get("ticker")) for s in d.get("sectors",[]) for x in s.get("stocks",[]) if x.get("ticker")}
    return {t:m for t,m in master.items() if t in tickers}

def hist_inst_last5():
    files=sorted((ROOT/"data/history/institutional").glob("*.json"))[-5:]
    return [load_json(p,{}) for p in files if load_json(p,{})]

def main():
    cfg=load_json(ROOT/"config.json",{}); master=load_json(ROOT/"data/master.json",{}).get("stocks",{}); candidates=tracked_candidates(master)
    market=load_json(ROOT/"data/market_latest.json",{}).get("stocks",{}); holders=load_json(ROOT/"data/holders.json",{})
    volume=load_json(ROOT/"data/volume.json",{}).get("items",[]); volmap={x["ticker"]:x for x in volume}; hist=hist_inst_last5()
    metrics={mk:{k:{} for k in ("foreign","trust","dealer")} for mk in ("twse","tpex")}; turn5={mk:{} for mk in ("twse","tpex")}
    for t,m in candidates.items():
        mk=m["market"]; inst_amt={k:0.0 for k in metrics[mk]}; trn=0.0
        for h in hist:
            q=h.get("closes",{}).get(t,{}); trn+=q.get("turnover",0) or 0; r=h.get(mk,{}).get(t,{}); price=q.get("price",0) or 0
            for k in inst_amt: inst_amt[k]+=r.get(k,0)*price
        denom=trn if trn>0 else 1
        for k in inst_amt: metrics[mk][k][t]=inst_amt[k]/denom
        turn5[mk][t]=trn
    holder_metric={mk:{} for mk in ("twse","tpex")}
    for mk in ("twse","tpex"):
        by={}
        for kind in ("400","1000"):
            for x in holders.get(mk,{}).get(kind,[]): by.setdefault(x["ticker"],[]).append(x["delta"])
        holder_metric[mk]={t:safe_mean(v) or 0 for t,v in by.items()}
    is_sunday=now_tpe().weekday()==6; weights=cfg["ai_weights_sunday"] if is_sunday else cfg["ai_weights_trade_day"]
    out={"updated_at":now_tpe().isoformat(timespec="minutes"),"mode":"sunday" if is_sunday else "trade_day","complete":len(hist)>=5,"twse":[],"tpex":[]}
    for mk in ("twse","tpex"):
        pf={k:percentile_map(metrics[mk][k]) for k in ("foreign","trust","dealer")}; ph=percentile_map(holder_metric[mk]); pt=percentile_map(turn5[mk])
        daily_turn={t2:(market.get(t2,{}).get("turnover",0) or 0) for t2,m2 in candidates.items() if m2["market"]==mk}; pd=percentile_map(daily_turn)
        scores=[]
        for t,m in candidates.items():
            if m["market"]!=mk:continue
            score=weights.get("foreign",0)*pf["foreign"].get(t,0)+weights.get("trust",0)*pf["trust"].get(t,0)+weights.get("dealer",0)*pf["dealer"].get(t,0)+weights.get("holders",0)*ph.get(t,0)
            if is_sunday: score+=weights.get("turnover_5d",0)*pt.get(t,0)
            else:
                q=market.get(t,{}); score+=weights.get("turnover",0)*pd.get(t,0); vr=volmap.get(t,{}).get("volume_ratio_5d",0); vp=min(100,max(0,(vr-1)*100)) if q.get("change_pct",0)>0 else 0; score+=weights.get("volume_price",0)*vp
            tags=[]
            if pf["trust"].get(t,0)>=75:tags.append("投信偏多")
            if pf["foreign"].get(t,0)>=75:tags.append("外資偏多")
            if ph.get(t,0)>=75 and holder_metric[mk].get(t,0)>0:tags.append("大戶增加")
            if pt.get(t,0)>=75:tags.append("成交活躍")
            if market.get(t,{}).get("change_pct",0)<0:tags.append("當日下跌")
            reason="、".join(tags[:4]) or "相對分數來自法人、大戶與成交熱度"
            scores.append({"ticker":t,"name":m.get("name",""),"score":round(score,1),"change_pct":market.get(t,{}).get("change_pct"),"tags":tags,"reason":reason})
        scores.sort(key=lambda x:x["score"],reverse=True); out[mk]=scores[:cfg.get("top_n",{}).get("ai",20)]
    save_json(ROOT/"data/ai_picks.json",out); print("ai",out["mode"],len(out["twse"]),len(out["tpex"]),"hist",len(hist))

if __name__=="__main__": main()
