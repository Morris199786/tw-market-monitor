#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股底部型態掃描器 v1
- W / 多重底
- U / 碗型底
- 破底洗盤後收回
- VCP / 底部收斂
- 目標：找「右側剛轉折、尚未離底太遠」的候選股
- 純測試版：不更新網站、不發 Telegram

使用：
  python pattern_scanner.py
  python pattern_scanner.py --top 30
  python pattern_scanner.py --tickers 8046,3211,3037
  python pattern_scanner.py --universe stocks.txt

stocks.txt 格式：每行一個股票代號，或「代號,名稱」
"""

import argparse
import csv
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

UA = "Mozilla/5.0"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"
OUT_CSV = "pattern_scan_top30.csv"
OUT_JSON = "pattern_scan_top30.json"

# 先放一批測試股票；正式接網站時改吃你的完整科技股池
DEFAULT_TICKERS = [
    "2330","2454","2308","2382","3231","6669","3661","3443","3035","3529",
    "6533","6643","8227","6695","3228","3037","8046","3189","2368","2383",
    "6274","6213","5347","2313","4958","2367","2408","2344","8299","6488",
    "3260","3017","3324","3653","4979","6223","3131","6510","6220","6187",
    "3211","3533","3583","4977","6515","6640","6789","6196","2467","5434",
    "6643","8028","8086","6239","3665","6279","2059","2395","6414","5269",
]

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0

def pct(a, b):
    return (a / b - 1.0) if b else 0.0

def sma(xs, n):
    if len(xs) < n: return None
    return mean(xs[-n:])

def true_ranges(h, l, c):
    out = []
    for i in range(len(c)):
        pc = c[i-1] if i else c[i]
        out.append(max(h[i]-l[i], abs(h[i]-pc), abs(l[i]-pc)))
    return out

def lin_slope(values):
    n = len(values)
    if n < 2: return 0.0
    xm = (n-1)/2
    ym = mean(values)
    den = sum((i-xm)**2 for i in range(n))
    return sum((i-xm)*(v-ym) for i,v in enumerate(values))/den if den else 0.0

def local_minima(c, radius=3):
    pts=[]
    for i in range(radius, len(c)-radius):
        w=c[i-radius:i+radius+1]
        if c[i] == min(w):
            pts.append((i,c[i]))
    return pts

def local_maxima(c, radius=3):
    pts=[]
    for i in range(radius, len(c)-radius):
        w=c[i-radius:i+radius+1]
        if c[i] == max(w):
            pts.append((i,c[i]))
    return pts

def yahoo_symbol(code, suffix):
    return f"{code}.{suffix}"

def fetch_one(code):
    # 上市 .TW / 上櫃 .TWO 自動嘗試
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})
    for suffix in ("TW","TWO"):
        sym = yahoo_symbol(code, suffix)
        url = YAHOO + quote(sym)
        params={"range":"2y","interval":"1d","events":"div,splits","includeAdjustedClose":"true"}
        try:
            r=sess.get(url, params=params, timeout=15)
            if r.status_code != 200: continue
            obj=r.json()["chart"]["result"]
            if not obj: continue
            x=obj[0]
            q=x["indicators"]["quote"][0]
            ts=x["timestamp"]
            name=x.get("meta",{}).get("longName") or x.get("meta",{}).get("shortName") or code
            rows=[]
            for i,t in enumerate(ts):
                vals=[q.get(k,[None]*len(ts))[i] for k in ("open","high","low","close","volume")]
                if any(v is None for v in vals[:4]): continue
                rows.append((t,*vals))
            if len(rows) >= 140:
                return sym,name,rows
        except Exception:
            pass
    return None

def score_stock(code, name, rows):
    rows=rows[-260:]
    O=[r[1] for r in rows]; H=[r[2] for r in rows]; L=[r[3] for r in rows]
    C=[r[4] for r in rows]; V=[float(r[5] or 0) for r in rows]
    n=len(C)
    if n < 140 or C[-1] <= 0: return None

    # 聚焦最近約 120 日底部，但用更長資料確認先前下降趨勢
    w=min(120,n)
    c=C[-w:]; h=H[-w:]; l=L[-w:]; v=V[-w:]
    mins=local_minima(c,3)
    maxs=local_maxima(c,3)

    score_structure=0
    labels=[]

    # ---- U / 碗型：左降、中平、右升 ----
    thirds=max(15,w//3)
    left=c[:thirds]
    mid=c[thirds:2*thirds]
    right=c[2*thirds:]
    scale=max(mean(c),1e-9)
    sl=lin_slope(left)/scale
    sm=lin_slope(mid)/scale
    sr=lin_slope(right)/scale
    u_shape = clamp((-sl)/0.004)*0.35 + clamp(sr/0.003)*0.35 + clamp((0.0025-abs(sm))/0.0025)*0.30
    if u_shape >= .58:
        labels.append("U/碗型")
        score_structure=max(score_structure, 25*u_shape)

    # ---- W / 多重底：近 100 日找相近的兩個低點，中間有反彈 ----
    wscore=0
    recent_mins=[p for p in mins if p[0] >= max(0,w-100)]
    for a in range(len(recent_mins)):
        for b in range(a+1,len(recent_mins)):
            i1,p1=recent_mins[a]; i2,p2=recent_mins[b]
            gap=i2-i1
            if not 8 <= gap <= 65: continue
            similarity=1-clamp(abs(p2/p1-1)/0.10)
            bounce=max(c[i1:i2+1])/min(p1,p2)-1
            bounce_score=clamp((bounce-.04)/.16)
            rightness=clamp((i2-(w-75))/55)
            s=.45*similarity+.35*bounce_score+.20*rightness
            wscore=max(wscore,s)
    if wscore >= .55:
        labels.append("W/多重底")
        score_structure=max(score_structure,25*wscore)

    # ---- 破底洗盤後快速收回：新低後 1~5 日站回前低，且收回日有量 ----
    wash_score=0
    wash_count=0
    for j in range(max(25,w-90), w-5):
        prev_low=min(c[max(0,j-25):j])
        if c[j] < prev_low*0.995:
            depth=(prev_low-c[j])/prev_low
            for k in range(j+1,min(w,j+6)):
                if c[k] >= prev_low:
                    volbase=mean(v[max(0,k-20):k]) or 1
                    volratio=v[k]/volbase
                    fast=1-(k-j-1)/5
                    s=.40*clamp(depth/.07)+.35*clamp(volratio/1.5)+.25*fast
                    wash_score=max(wash_score,s)
                    wash_count+=1
                    break
    score_wash=15*wash_score
    if wash_score >= .45: labels.append("破底收回")

    # ---- 低點改善：Lower Low -> Equal/Higher Low ----
    lows=[p for p in recent_mins[-5:]]
    improve=0
    if len(lows)>=3:
        vals=[x[1] for x in lows]
        changes=[pct(vals[i],vals[i-1]) for i in range(1,len(vals))]
        recent=changes[-2:]
        # 最近低點不再大幅破底；higher low 最佳
        improve=mean([clamp((x+.035)/.07) for x in recent])
        # 最後一底高於前底再加強
        if vals[-1] >= vals[-2]*.995: improve=min(1,improve+.15)
    score_lows=15*improve

    # ---- 波動收斂：ATR% 近期 < 前期 ----
    tr=true_ranges(h,l,c)
    atr_old=mean(tr[-60:-30])/(mean(c[-60:-30]) or 1)
    atr_new=mean(tr[-20:])/(mean(c[-20:]) or 1)
    atr_ratio=atr_new/(atr_old or 1e-9)
    range_old=(max(c[-60:-30])/min(c[-60:-30])-1) if min(c[-60:-30]) else 1
    range_new=(max(c[-20:])/min(c[-20:])-1) if min(c[-20:]) else 1
    contraction=.55*clamp((1.15-atr_ratio)/.55)+.45*clamp((1.10-(range_new/(range_old or 1e-9)))/.70)
    score_contract=15*contraction
    if contraction>=.62: labels.append("VCP/收斂")

    # ---- 成交量：整理末端量縮 + 上漲/收回日量較佳 ----
    vol20=mean(v[-20:]); vol_prev=mean(v[-60:-20]) or 1
    dry=clamp((1.15-vol20/vol_prev)/.55)
    upvol=[v[i] for i in range(w-20,w) if c[i]>=c[i-1]]
    dnvol=[v[i] for i in range(w-20,w) if c[i]<c[i-1]]
    uv=mean(upvol); dv=mean(dnvol) or 1
    demand=clamp((uv/dv-.85)/.65)
    score_volume=15*(.55*dry+.45*demand)

    # ---- 右側轉折：MA5/10 翻揚、Higher Low、價格站回 MA20 ----
    ma5=sma(c,5); ma10=sma(c,10); ma20=sma(c,20); ma60=sma(c,60)
    ma5_prev=mean(c[-10:-5]); ma10_prev=mean(c[-20:-10])
    turn=0
    turn += .25*clamp((ma5/ma5_prev-1+.01)/.035)
    turn += .25*clamp((ma10/ma10_prev-1+.01)/.035)
    turn += .25*(1 if c[-1]>=ma20 else clamp(c[-1]/ma20-.96,.0,.04)/.04)
    turn += .25*improve
    score_turn=10*turn

    # ---- 位置：右側剛起漲最好，離 60 日低點約 5~22%，太遠扣分 ----
    low60=min(c[-60:])
    dist=c[-1]/low60-1
    if .05 <= dist <= .22:
        pos=1.0
    elif dist < .05:
        pos=clamp(dist/.05)
    else:
        pos=clamp(1-(dist-.22)/.25)
    score_pos=5*pos

    total=score_structure+score_wash+score_lows+score_contract+score_volume+score_turn+score_pos

    # 沒有任何底型訊號者限制分數，避免純強勢股混進來
    if not labels:
        total=min(total,49)

    # 階段
    high60=max(c[-60:])
    near_high=c[-1]/high60
    if turn>=.62 and contraction>=.45 and dist<=.22:
        stage="🟠 右側轉折/準備區"
    elif contraction>=.60 and dist<=.18:
        stage="🟡 築底末端"
    elif near_high>=.985 and c[-1]>ma20:
        stage="🔴 接近/嘗試突破"
    elif dist>.32:
        stage="⚪ 已離底較遠"
    else:
        stage="⚪ 築底中"

    # 參考支撐 / 突破
    support=min(c[-20:])
    resistance=max(c[-40:-5]) if len(c)>=45 else max(c[:-5])
    vol_ratio=v[-1]/(mean(v[-20:-1]) or 1)

    reasons=[]
    if u_shape>=.58: reasons.append("左降→底部走平→右側斜率翻正")
    if wscore>=.55: reasons.append("近端存在相近雙底/多重底")
    if wash_score>=.45: reasons.append(f"破底後快速收回訊號 {wash_count} 次")
    if improve>=.60: reasons.append("最近低點由破底轉為等低/墊高")
    if contraction>=.62: reasons.append("ATR/區間振幅明顯收斂")
    if dry>=.55: reasons.append("底部整理量縮")
    if turn>=.62: reasons.append("短均線與價格開始右側轉強")
    if not reasons: reasons.append("綜合底部條件接近門檻")

    return {
        "code":code, "name":name, "score":round(total,1),
        "pattern":" + ".join(dict.fromkeys(labels)) if labels else "底部候選",
        "stage":stage,
        "close":round(c[-1],2),
        "support":round(support,2),
        "breakout":round(resistance,2),
        "vol_ratio":round(vol_ratio,2),
        "dist_from_60d_low_pct":round(dist*100,1),
        "structure":round(score_structure,1),
        "washout":round(score_wash,1),
        "low_improve":round(score_lows,1),
        "contraction":round(score_contract,1),
        "volume":round(score_volume,1),
        "right_turn":round(score_turn,1),
        "position":round(score_pos,1),
        "reason":"；".join(reasons)
    }

def read_universe(path):
    out=[]
    with open(path,"r",encoding="utf-8-sig") as f:
        for line in f:
            s=line.strip()
            if not s or s.startswith("#"): continue
            code=s.split(",")[0].strip()
            if code.isdigit() and len(code)==4:
                out.append(code)
    return list(dict.fromkeys(out))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--top",type=int,default=30)
    ap.add_argument("--tickers",default="")
    ap.add_argument("--universe",default="")
    ap.add_argument("--sleep",type=float,default=.15)
    args=ap.parse_args()

    if args.tickers:
        tickers=[x.strip() for x in args.tickers.split(",") if x.strip()]
    elif args.universe:
        tickers=read_universe(args.universe)
    else:
        tickers=DEFAULT_TICKERS

    print(f"掃描 {len(tickers)} 檔；只輸出測試結果，不更新網站、不推播")
    results=[]
    failed=[]
    for idx,code in enumerate(tickers,1):
        data=fetch_one(code)
        if not data:
            failed.append(code)
            print(f"[{idx:>3}/{len(tickers)}] {code} 下載失敗")
            continue
        sym,name,rows=data
        r=score_stock(code,name,rows)
        if r:
            results.append(r)
            print(f"[{idx:>3}/{len(tickers)}] {code} {r['score']:>5.1f} {r['pattern']} {r['stage']}")
        time.sleep(args.sleep)

    results.sort(key=lambda x:x["score"], reverse=True)
    top=results[:args.top]

    fields=["rank","code","name","score","pattern","stage","close","support","breakout",
            "vol_ratio","dist_from_60d_low_pct","structure","washout","low_improve",
            "contraction","volume","right_turn","position","reason"]
    with open(OUT_CSV,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        for i,r in enumerate(top,1):
            w.writerow({"rank":i,**r})

    payload={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "scanned":len(tickers),"success":len(results),"failed":failed,
        "top":top
    }
    Path(OUT_JSON).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print("\n===== TOP =====")
    for i,r in enumerate(top,1):
        print(f"{i:>2}. {r['code']} {r['name'][:12]:<12} {r['score']:>5.1f} "
              f"{r['pattern']:<24} {r['stage']}")
        print(f"    支撐 {r['support']}｜突破參考 {r['breakout']}｜量比 {r['vol_ratio']}｜{r['reason']}")
    print(f"\n輸出：{OUT_CSV} / {OUT_JSON}")
    if failed: print("下載失敗：",",".join(failed))

if __name__=="__main__":
    main()
