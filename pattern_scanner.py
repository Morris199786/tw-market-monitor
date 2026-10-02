#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股底部型態掃描器 v3｜底部結構 + 壓力逐層消化版
預設股票池：共用 scripts/tech_universe.py 的「全台股科技普通股」
評分公式維持原 V3。
"""
import argparse,csv,json,time,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
import requests

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"scripts"))
from sources import fetch_master
from tech_universe import tech_tickers

UA="Mozilla/5.0"; YAHOO="https://query1.finance.yahoo.com/v8/finance/chart/"
OUT_CSV="pattern_scan_top30.csv"; OUT_JSON="pattern_scan_top30.json"
DEFAULT_TICKERS=["2330","2454","2308","2382","3231","6669","3661","3443","3035","3529","6533","6643","8227","6695","3228","3037","8046","3189","2368","2383","6274","6213","5347","2313","4958","2367","2408","2344","8299","6488","3260","3017","3324","3653","4979","6223","3131","6510","6220","6187","3211","3533","3583","4977","6515","6640","6789","6196","2467","5434","8028","8086","6239","3665","6279","2059","2395","6414","5269"]

def clamp(x,lo=0.,hi=1.): return max(lo,min(hi,x))
def mean(x): return sum(x)/len(x) if x else 0.
def pct(a,b): return a/b-1 if b else 0.
def sma(x,n): return mean(x[-n:]) if len(x)>=n else None
def slope(x):
    n=len(x)
    if n<2:return 0.
    xm=(n-1)/2; ym=mean(x); d=sum((i-xm)**2 for i in range(n))
    return sum((i-xm)*(v-ym) for i,v in enumerate(x))/d if d else 0.
def extrema(c,r=3,mode="min"):
    out=[]
    for i in range(r,len(c)-r):
        w=c[i-r:i+r+1]
        if c[i]==(min(w) if mode=="min" else max(w)): out.append((i,c[i]))
    return out
def trange(h,l,c):
    return [max(h[i]-l[i],abs(h[i]-(c[i-1] if i else c[i])),abs(l[i]-(c[i-1] if i else c[i]))) for i in range(len(c))]

def fetch_one(code):
    s=requests.Session(); s.headers.update({"User-Agent":UA})
    for suffix in ("TW","TWO"):
        sym=f"{code}.{suffix}"
        try:
            r=s.get(YAHOO+quote(sym),params={"range":"2y","interval":"1d","events":"div,splits","includeAdjustedClose":"true"},timeout=15)
            if r.status_code!=200: continue
            obj=r.json()["chart"]["result"]
            if not obj: continue
            x=obj[0]; q=x["indicators"]["quote"][0]; ts=x["timestamp"]
            name=x.get("meta",{}).get("longName") or x.get("meta",{}).get("shortName") or code
            rows=[]
            for i,t in enumerate(ts):
                vals=[q.get(k,[None]*len(ts))[i] for k in ("open","high","low","close","volume")]
                if any(v is None for v in vals[:4]): continue
                rows.append((t,*vals))
            if len(rows)>=160:return sym,name,rows
        except Exception: pass
    return None

def score_stock(code,name,rows):
    rows=rows[-300:]; H=[r[2] for r in rows]; L=[r[3] for r in rows]; C=[r[4] for r in rows]; V=[float(r[5] or 0) for r in rows]
    if len(C)<160 or C[-1]<=0:return None
    w=min(140,len(C)); c=C[-w:]; h=H[-w:]; l=L[-w:]; v=V[-w:]
    mins=extrema(c,3,"min"); maxs=extrema(c,3,"max")
    rmins=[p for p in mins if p[0]>=w-110]; rmaxs=[p for p in maxs if p[0]>=w-110]
    labels=[]; reasons=[]

    pre=c[:max(35,w-90)]; pre_sl=slope(pre)/(mean(pre) or 1); depth=max(c)/min(c)-1
    base_valid=.55*clamp((-pre_sl+.0003)/.0035)+.45*clamp((depth-.10)/.28)
    if rmins: base_valid=clamp(base_valid+.12*clamp((rmins[-1][0]-(w-80))/50))
    s_base=15*base_valid

    ws=0.
    for a in range(len(rmins)):
        for b in range(a+1,len(rmins)):
            i1,p1=rmins[a]; i2,p2=rmins[b]; gap=i2-i1
            if not 8<=gap<=70: continue
            sim=1-clamp(abs(p2/p1-1)/.11); bounce=max(c[i1:i2+1])/min(p1,p2)-1
            ws=max(ws,.42*sim+.36*clamp((bounce-.035)/.16)+.22*clamp((i2-(w-85))/60))
    thirds=max(18,w//3); left=c[:thirds]; mid=c[thirds:2*thirds]; right=c[2*thirds:]; scale=mean(c) or 1
    us=.34*clamp((-slope(left)/scale)/.004)+.30*clamp((.0027-abs(slope(mid)/scale))/.0027)+.36*clamp((slope(right)/scale)/.003)
    if ws>=.55: labels.append("W/多重底"); reasons.append("存在相近雙底/多重底")
    if us>=.58: labels.append("U/碗型"); reasons.append("左降→底部鈍化→右側翻正")
    s_shape=10*max(ws,us)

    lowq=0.; hlratio=0.
    if len(rmins)>=3:
        vals=[x[1] for x in rmins[-5:]]; ch=[pct(vals[i],vals[i-1]) for i in range(1,len(vals))][-3:]
        nobreak=mean([clamp((x+.035)/.055) for x in ch]); hlratio=sum(x>=-.005 for x in ch)/len(ch)
        lowq=.45*nobreak+.35*hlratio+.20*clamp((vals[-1]/vals[-2]-.97)/.07)
    s_low=15*lowq
    if lowq>=.62: reasons.append("右側低點不再破底並逐步墊高")

    wash=0.; wash_n=0
    for j in range(max(25,w-100),w-5):
        pl=min(c[max(0,j-25):j])
        if c[j]<pl*.995:
            dep=(pl-c[j])/pl
            for k in range(j+1,min(w,j+6)):
                if c[k]>=pl:
                    vr=v[k]/(mean(v[max(0,k-20):k]) or 1)
                    wash=max(wash,.38*clamp(dep/.07)+.34*clamp(vr/1.5)+.28*(1-(k-j-1)/5)); wash_n+=1; break
    s_wash=8*wash
    if wash>=.48: labels.append("破底收回"); reasons.append("破底後快速收回")

    pressure=0.; touches=0; reclaims=0; hs=rmaxs[-5:]
    if len(hs)>=3:
        ps=[]
        for i in range(1,len(hs)):
            ratio=hs[i][1]/hs[i-1][1]; ps.append(clamp((ratio-.94)/.06))
            if ratio>=.97: touches+=1
            if ratio>=1.: reclaims+=1
        cur=clamp((c[-1]/hs[-1][1]-.94)/.06); pressure=clamp(.72*mean(ps[-3:])+.28*cur)
    zones=[]
    for lb in (80,60,40,25):
        if len(c)>lb+5:
            seg=c[-lb:-5]; zones.append(min(seg[-max(8,lb//4):]))
    zones=sorted(set(zones)); zscore=sum(c[-1]>=z for z in zones)/len(zones) if zones else 0
    pressure=max(pressure,.75*zscore); s_pressure=20*pressure
    if pressure>=.65: reasons.append(f"上攻逐層測試/收復前壓力（觸碰{touches}、收復{reclaims}）")

    tr=trange(h,l,c)
    ao=mean(tr[-70:-35])/(mean(c[-70:-35]) or 1); am=mean(tr[-35:-15])/(mean(c[-35:-15]) or 1); an=mean(tr[-15:])/(mean(c[-15:]) or 1)
    ac=.45*clamp((1.12-am/(ao or 1e-9))/.55)+.55*clamp((1.10-an/(am or 1e-9))/.50)
    rr=[]
    for n in (60,35,20):
        seg=c[-n:]; rr.append(max(seg)/min(seg)-1)
    rc=.5*clamp((1.08-rr[1]/(rr[0] or 1e-9))/.60)+.5*clamp((1.08-rr[2]/(rr[1] or 1e-9))/.60)
    contract=.58*ac+.42*rc; s_contract=12*contract
    if contract>=.60: labels.append("VCP/收斂"); reasons.append("波動與回檔幅度逐步收斂")

    vol20=mean(v[-20:]); vp=mean(v[-60:-20]) or 1; dry=clamp((1.15-vol20/vp)/.55)
    uv=[]; dv=[]
    for i in range(w-20,w): (uv if c[i]>=c[i-1] else dv).append(v[i])
    demand=clamp(((mean(uv)/(mean(dv) or 1))-.85)/.70)
    ar=[]
    for i in range(w-25,w):
        if c[i]/c[i-1]-1>=.02: ar.append(v[i]/(mean(v[max(0,i-20):i]) or 1))
    attack=clamp(((max(ar) if ar else .8)-.9)/.9); vq=.35*dry+.35*demand+.30*attack; s_vol=10*vq
    if vq>=.62: reasons.append("整理量縮、攻擊波量能較佳")

    m5=sma(c,5); m10=sma(c,10); m20=sma(c,20); m60=sma(c,60)
    turn=.22*clamp((m5/mean(c[-10:-5])-1+.008)/.030)+.22*clamp((m10/mean(c[-20:-10])-1+.008)/.030)+.22*clamp((m20/mean(c[-40:-20])-1+.012)/.040)+.18*(1 if c[-1]>=m20 else clamp((c[-1]/m20-.96)/.04))+.16*lowq
    s_turn=10*turn
    if turn>=.62: reasons.append("5/10/20MA 與價格開始右側轉強")

    low60=min(c[-60:]); dist=c[-1]/low60-1; resistance=max(c[-45:-5])
    bp=c[-1]/resistance-1; below=(resistance-c[-1])/resistance; ext=c[-1]/m20-1; r5=c[-1]/c[-6]-1; r10=c[-1]/c[-11]-1
    neck=1. if 0<=below<=.08 else clamp(1-(below-.08)/.07) if .08<below<=.15 else .88 if -.035<=below<0 else .45 if -.07<=below<-.035 else 0.
    basepos=1. if .05<=dist<=.24 else .75*clamp(1-(dist-.24)/.10) if .24<dist<=.34 else clamp(dist/.05) if dist<.05 else 0.
    m60gap=c[-1]/m60-1; m60setup=1. if -.05<=m60gap<=.04 else clamp(1-abs(m60gap)/.14)
    raw=.26*turn+.23*neck+.18*basepos+.18*pressure+.10*contract+.05*m60setup
    heat=(.32*clamp((ext-.12)/.12) if ext>.12 else 0)+(.28*clamp((r5-.14)/.12) if r5>.14 else 0)+(.40*clamp((r10-.24)/.18) if r10>.24 else 0)
    timing=clamp(raw-heat); s_time=15*timing
    penalty=(7*clamp((bp-.05)/.10) if bp>.05 else 0)+(10*clamp((dist-.34)/.22) if dist>.34 else 0)+(7*clamp((ext-.12)/.12) if ext>.12 else 0)+(4*clamp((r5-.14)/.12) if r5>.14 else 0)+(5*clamp((r10-.24)/.18) if r10>.24 else 0)
    missed=bp>.11 or dist>.42 or ext>.20 or r10>.35

    total=s_base+s_shape+s_low+s_wash+s_pressure+s_contract+s_vol+s_turn+s_time-penalty
    if base_valid<.35: total=min(total,59.)
    if lowq<.25 and len(rmins)>=3: total=min(total,62.)
    if not labels and pressure<.50: total=min(total,54.)
    if missed: total=min(total,64.9)

    if missed: stage="⚪ 已錯過/已漲一段"
    elif 0<=below<=.10 and turn>=.56 and pressure>=.55 and lowq>=.45: stage="🟠 紅點準備區"
    elif -.04<=bp<=.04 and turn>=.58 and pressure>=.58: stage="🔴 突破初期"
    elif contract>=.55 and lowq>=.45 and bp<0: stage="🟡 築底末端"
    else: stage="⚪ 築底中"

    if not reasons: reasons=["底部結構接近門檻"]
    return {"code":code,"name":name,"score":round(max(0,total),1),"pattern":" + ".join(dict.fromkeys(labels)) if labels else "底部候選","stage":stage,"close":round(c[-1],2),"support":round(min(c[-20:]),2),"breakout":round(resistance,2),"vol_ratio":round(v[-1]/(mean(v[-20:-1]) or 1),2),"dist_from_60d_low_pct":round(dist*100,1),"breakout_pct":round(bp*100,1),"ma20_ext_pct":round(ext*100,1),"ret5_pct":round(r5*100,1),"ret10_pct":round(r10*100,1),"timing":round(s_time,1),"extension_penalty":round(penalty,1),"structure":round(s_shape,1),"washout":round(s_wash,1),"low_improve":round(s_low,1),"contraction":round(s_contract,1),"volume":round(s_vol,1),"right_turn":round(s_turn,1),"position":round(s_time,1),"base_validity":round(s_base,1),"pressure_reclaim":round(s_pressure,1),"higher_low_ratio":round(hlratio,2),"ma60_gap_pct":round(m60gap*100,1),"reason":"；".join(reasons)}

def read_universe(path):
    out=[]
    with open(path,encoding="utf-8-sig") as f:
        for line in f:
            s=line.strip()
            if not s or s.startswith("#"):continue
            code=s.split(",")[0].strip()
            if code.isdigit() and len(code)==4:out.append(code)
    return list(dict.fromkeys(out))

def shared_tech_universe():
    """
    完全沿用網站既有科技股標準：
      1. 官方科技產業股
      2. data/sectors.json 自訂科技族群
      3. config.json 跨產業科技供應鏈白名單
      4. 扣除 tech_exclude_tickers（若有）

    優先讀 repo 已產生的 data/master.json，避免 scanner
    自己重新抓 master 後因來源欄位差異造成股票池不一致。
    """
    try:
        master_path = ROOT / "data" / "master.json"
        if master_path.exists():
            obj = json.loads(master_path.read_text(encoding="utf-8"))
            master = obj.get("stocks", obj)
        else:
            master = fetch_master()

        tickers = sorted(tech_tickers(master))
        if tickers:
            print(f"網站共用科技股池：{len(tickers)} 檔")
            return tickers
    except Exception as e:
        print(f"網站共用科技股池取得失敗：{e}")

    print(f"改用 fallback DEFAULT_TICKERS：{len(DEFAULT_TICKERS)} 檔")
    return DEFAULT_TICKERS

def priority(stage):
    return 0 if stage.startswith("🟠") else 1 if stage.startswith("🔴") else 2 if stage.startswith("🟡") else 4 if "錯過" in stage else 3

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--top",type=int,default=30); ap.add_argument("--tickers",default=""); ap.add_argument("--universe",default=""); ap.add_argument("--sleep",type=float,default=.15); a=ap.parse_args()
    tickers=[x.strip() for x in a.tickers.split(",") if x.strip()] if a.tickers else read_universe(a.universe) if a.universe else shared_tech_universe()
    print(f"V3 掃描 {len(tickers)} 檔｜底部結構 + 壓力逐層消化")
    results=[]; failed=[]
    for i,code in enumerate(tickers,1):
        d=fetch_one(code)
        if not d: failed.append(code); print(f"[{i:>3}/{len(tickers)}] {code} 下載失敗"); continue
        _,name,rows=d; r=score_stock(code,name,rows)
        if r: results.append(r); print(f"[{i:>3}/{len(tickers)}] {code} {r['score']:>5.1f} 壓力:{r['pressure_reclaim']:>4.1f} {r['stage']}")
        time.sleep(a.sleep)
    results.sort(key=lambda x:(-x["score"],priority(x["stage"]))); top=results[:a.top]
    fields=["rank","code","name","score","pattern","stage","close","support","breakout","vol_ratio","dist_from_60d_low_pct","breakout_pct","ma20_ext_pct","ret5_pct","ret10_pct","timing","extension_penalty","structure","washout","low_improve","contraction","volume","right_turn","position","base_validity","pressure_reclaim","higher_low_ratio","ma60_gap_pct","reason"]
    with open(OUT_CSV,"w",newline="",encoding="utf-8-sig") as f:
        wr=csv.DictWriter(f,fieldnames=fields); wr.writeheader()
        for i,r in enumerate(top,1):wr.writerow({"rank":i,**r})
    Path(OUT_JSON).write_text(json.dumps({"version":"v3-tech-universe","generated_at":datetime.now(timezone.utc).isoformat(),"scanned":len(tickers),"success":len(results),"failed":failed,"top":top},ensure_ascii=False,indent=2),encoding="utf-8")
    print("\n===== V3 TOP =====")
    for i,r in enumerate(top,1):
        print(f"{i:>2}. {r['code']} {r['name'][:12]:<12} {r['score']:>5.1f} {r['pattern']:<22} {r['stage']}")
        print(f"    支撐 {r['support']}｜突破 {r['breakout']}｜底部有效 {r['base_validity']}｜壓力消化 {r['pressure_reclaim']}｜{r['reason']}")
    print(f"\n輸出：{OUT_CSV} / {OUT_JSON}")
    if failed:print("下載失敗：",",".join(failed))

if __name__=="__main__":main()
