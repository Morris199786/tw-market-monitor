#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台股 W / 圓弧底早期右側掃描器

保留原有命令列參數、科技股池、成交金額門檻、CSV/JSON 檔名與欄位
核心修改：右側剛止跌、低點墊高、短均線初步轉正優先；避免等大漲才入選
不執行回測，不更動 GitHub Actions
"""
import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from sources import fetch_master
from tech_universe import tech_tickers

UA = 'Mozilla/5.0'
YAHOO = 'https://query1.finance.yahoo.com/v8/finance/chart/'
OUT_CSV = 'pattern_scan_top30.csv'
OUT_JSON = 'pattern_scan_top30.json'
MIN_TURNOVER = 10_000_000
DEFAULT_TICKERS = [
    '2330','2454','2308','2382','3231','6669','3661','3443','3035','3529',
    '6533','6643','8227','6695','3228','3037','8046','3189','2368','2383',
    '6274','6213','5347','2313','4958','2367','2408','2344','8299','6488',
    '3260','3017','3324','3653','4979','6223','3131','6510','6220','6187',
    '3211','3533','3583','4977','6515','6640','6789','6196','2467','5434',
    '8028','8086','6239','3665','6279','2059','2395','6414','5269',
]


def clamp(x, lo=0., hi=1.):
    return max(lo, min(hi, x))


def mean(x):
    return sum(x) / len(x) if x else 0.


def median(x):
    y = sorted(x)
    n = len(y)
    return (y[n//2] if n % 2 else (y[n//2-1]+y[n//2])/2) if n else 0.


def pct(a, b):
    return a/b-1 if b else 0.


def slope(x):
    n = len(x)
    if n < 2:
        return 0.
    xm = (n-1)/2
    ym = mean(x)
    den = sum((i-xm)**2 for i in range(n))
    return sum((i-xm)*(v-ym) for i, v in enumerate(x))/den if den else 0.


def norm_slope(x):
    return slope(x)/(mean(x) or 1.)


def sma(x, n):
    return mean(x[-n:]) if len(x) >= n else None


def extrema(c, r=3, mode='min'):
    out = []
    for i in range(r, len(c)-r):
        w = c[i-r:i+r+1]
        target = min(w) if mode == 'min' else max(w)
        if c[i] == target:
            out.append((i, c[i]))
    return out


def fetch_one(code):
    s = requests.Session()
    s.headers.update({'User-Agent': UA})
    for suffix in ('TW', 'TWO'):
        sym = f'{code}.{suffix}'
        try:
            r = s.get(YAHOO + quote(sym), params={
                'range': '2y', 'interval': '1d', 'events': 'div,splits',
                'includeAdjustedClose': 'true',
            }, timeout=15)
            if r.status_code != 200:
                continue
            result = r.json().get('chart', {}).get('result')
            if not result:
                continue
            x = result[0]
            q = x['indicators']['quote'][0]
            ts = x['timestamp']
            meta = x.get('meta', {})
            name = meta.get('longName') or meta.get('shortName') or code
            rows = []
            for i, t in enumerate(ts):
                vals = [q.get(k, [None]*len(ts))[i]
                        for k in ('open','high','low','close','volume')]
                if any(v is None for v in vals[:4]):
                    continue
                rows.append((t, *vals))
            if len(rows) >= 160:
                return sym, name, rows
        except Exception:
            pass
    return None


def rounded_turn_score(seg):
    """容許右側僅微幅轉強；不要求右側已經急漲。"""
    n = len(seg)
    if n < 18:
        return 0., 0., 0., 0.
    k = max(5, n//4)
    left, center, right = seg[:k], seg[k:-k], seg[-k:]
    ls, cs, rs = norm_slope(left), norm_slope(center), norm_slope(right)
    left_down = clamp((-ls-0.0002)/0.004)
    center_flat = clamp((0.0035-abs(cs))/0.0035)
    # 在右側斜率接近 0 時即開始給分，超過約 0.25%/日不再額外獎勵
    right_up = clamp((rs+0.0010)/0.0035)
    low, high = min(seg), max(seg)
    bottom_band = low + max(high-low, low*0.01)*0.18
    bottom_days = sum(v <= bottom_band for v in seg)
    bottom_width = clamp((bottom_days-2)/7)
    score = (0.32*left_down + 0.27*center_flat +
             0.27*right_up + 0.14*bottom_width)
    return score, ls, cs, rs


def best_rounded_base(c):
    best = (0., None, None, None, None, None)
    n = len(c)
    for length in (24,30,36,45,55,70,85):
        if n < length:
            continue
        for end_back in (0,2,3,6,10,15):
            end = n-end_back
            start = end-length
            if start < 0:
                continue
            sc, ls, cs, rs = rounded_turn_score(c[start:end])
            if sc > best[0]:
                best = (sc,start,end,ls,cs,rs)
    return best


def stair_step_score(c):
    look = c[-95:]
    mins = extrema(look, 2)
    if len(mins) < 3:
        return 0., 0
    good, strengths = 0, []
    for idx, price in mins[:-1]:
        future = look[idx+1:min(len(look),idx+9)]
        if not future:
            continue
        rb = max(future)/price-1
        strengths.append(rb)
        if rb >= 0.025:
            good += 1
    return (0.62*clamp((good-1)/4) +
            0.38*clamp((mean(strengths)-0.015)/0.07)), good


def cliff_and_deadbase(c, o):
    n = len(c)
    start = max(1,n-120)
    worst, worst_i = 0., None
    for i in range(start,n):
        d1 = pct(c[i],c[i-1])
        gap = pct(o[i],c[i-1])
        sc = max(clamp((-d1-0.055)/0.075),clamp((-gap-0.035)/0.065))
        if sc > worst:
            worst,worst_i = sc,i
    for span,threshold,scale in ((3,0.10,0.12),(5,0.14,0.15)):
        for i in range(max(span,start),n):
            sc = clamp((-pct(c[i],c[i-span])-threshold)/scale)
            if sc > worst:
                worst,worst_i = sc,i
    if worst_i is None:
        return 0.,0.,0.
    after = c[worst_i:min(n,worst_i+45)]
    if len(after) < 12:
        return worst,0.,worst*0.35
    anchor = mean(c[max(0,worst_i-8):worst_i]) or c[worst_i]
    stayed_low = clamp((0.94-median(after)/anchor)/0.12)
    rebound = max(after)/min(after)-1
    narrow = clamp((0.18-rebound)/0.13)
    weak_rebound = clamp((0.12-rebound)/0.09)
    dead = 0.48*stayed_low+0.32*narrow+0.20*weak_rebound
    return worst,dead,worst*dead


def recent_path_quality(c):
    seg = c[-60:]
    a,b,d = seg[:20],seg[20:40],seg[40:]
    sa,sb,sd = norm_slope(a),norm_slope(b),norm_slope(d)
    soften = clamp((sb-sa+0.001)/0.005)
    # 不再要求最後 20 日斜率已顯著上升
    right = clamp((sd+0.002)/0.004)
    not_vertical = clamp((0.010-abs(sa))/0.008)
    return 0.44*soften+0.41*right+0.15*not_vertical,sa,sb,sd


def multi_bottom_score(c):
    look = c[-100:]
    mins = extrema(look,3)
    best = 0.
    for a in range(len(mins)):
        for b in range(a+1,len(mins)):
            i1,p1 = mins[a]
            i2,p2 = mins[b]
            gap = i2-i1
            if not 8 <= gap <= 65:
                continue
            sim = 1-clamp(abs(p2/p1-1)/0.14)
            bounce = max(look[i1:i2+1])/min(p1,p2)-1
            sc = 0.40*sim+0.45*clamp((bounce-0.025)/0.16)+0.15*clamp(gap/35)
            best = max(best,sc)
    return best


def early_right_score(c, h, l):
    """抓右側第一段轉折，而非右側已噴出：低點墊高、短均線微翻、近期突破。"""
    low10_now = min(l[-5:])
    low10_prev = min(l[-12:-5])
    higher_low = clamp((low10_now/low10_prev-0.985)/0.055)
    m5_now = mean(c[-5:])
    m5_prev = mean(c[-10:-5])
    turn5 = clamp((pct(m5_now,m5_prev)+0.005)/0.025)
    m10_now = mean(c[-10:])
    m10_prev = mean(c[-20:-10])
    turn10 = clamp((pct(m10_now,m10_prev)+0.01)/0.035)
    # 近期高點突破的「初始」幅度：超過 8% 不再加分
    pivot = max(h[-12:-2])
    breakout = clamp((c[-1]/pivot-0.965)/0.065)
    # 最新收盤在 20MA 附近即為理想，毋須等到大幅站上
    m20 = mean(c[-20:])
    ma_contact = clamp(1-abs(c[-1]/m20-1.025)/0.10)
    return (0.26*higher_low+0.27*turn5+0.17*turn10+
            0.16*breakout+0.14*ma_contact)


def score_stock(code,name,rows):
    rows = rows[-320:]
    O = [float(r[1]) for r in rows]
    H = [float(r[2]) for r in rows]
    L = [float(r[3]) for r in rows]
    C = [float(r[4]) for r in rows]
    V = [float(r[5] or 0) for r in rows]
    if len(C) < 160 or C[-1] <= 0:
        return None
    today_turnover = C[-1]*V[-1]
    if today_turnover < MIN_TURNOVER:
        return None
    w = min(140,len(C))
    c,o,h,l,v = C[-w:],O[-w:],H[-w:],L[-w:],V[-w:]
    rounded,rb_start,rb_end,left_sl,center_sl,right_sl = best_rounded_base(c)
    stair,rebound_count = stair_step_score(c)
    path,path1,path2,path3 = recent_path_quality(c)
    multi = multi_bottom_score(c)
    cliff,dead,cliff_dead = cliff_and_deadbase(c,o)
    early = early_right_score(c,h,l)
    m5,m10,m20,m60 = (sma(c,n) for n in (5,10,20,60))
    ma_turn = (0.35*clamp((pct(m5,mean(c[-10:-5]))+0.006)/0.025)
               +0.30*clamp((pct(m10,mean(c[-20:-10]))+0.008)/0.032)
               +0.20*clamp((pct(m20,mean(c[-40:-20]))+0.012)/0.045)
               +0.15*clamp((c[-1]/m20-0.96)/0.065))
    vol20 = mean(v[-20:])
    vol_prev = mean(v[-60:-20]) or 1.
    dry = clamp((1.18-vol20/vol_prev)/0.60)
    upv,dnv = [],[]
    for i in range(max(1,len(c)-20),len(c)):
        (upv if c[i]>=c[i-1] else dnv).append(v[i])
    demand = clamp((mean(upv)/(mean(dnv) or 1)-0.80)/0.80)
    volume_quality = 0.52*dry+0.48*demand
    low60 = min(c[-60:])
    dist_low = c[-1]/low60-1
    # 右側初期最理想：離 60 日低點 2%~14%；超過 22% 快速降分
    base_position = (clamp(dist_low/0.025) if dist_low<0.025 else
                     1. if dist_low<=0.14 else clamp(1-(dist_low-0.14)/0.20))
    r5 = pct(c[-1],c[-6]); r10 = pct(c[-1],c[-11]); ext20 = pct(c[-1],m20)
    # 扣分提前，但不因單日正常突破就直接淘汰
    extension_penalty = (12*clamp((ext20-0.075)/0.13)
                         +10*clamp((r5-0.085)/0.11)
                         +10*clamp((r10-0.15)/0.16)
                         +8*clamp((dist_low-0.20)/0.22))
    positive = (25*rounded+15*path+12*stair+9*multi+
                9*ma_turn+6*volume_quality+10*base_position+14*early)
    cliff_penalty = 34*cliff_dead
    current_vertical = clamp((-path3-0.006)/0.008)
    vertical_penalty = 12*current_vertical
    total = positive-cliff_penalty-vertical_penalty-extension_penalty
    if rounded<0.42 and path<0.48:
        total = min(total,54.9)
    if cliff_dead>=0.55:
        total = min(total,44.9)
    # 已離底過遠或短期急漲，明確壓低排名；不能靠其他指標抵銷
    if ext20>=0.24 or r5>=0.24 or dist_low>=0.48:
        total = min(total,55.)
    labels,reasons = [],[]
    if rounded>=0.62:
        labels.append('圓弧/U底');reasons.append('下跌斜率鈍化，底部形成圓弧')
    elif rounded>=0.48:
        labels.append('圓弧候選');reasons.append('底部已有鈍化與曲率')
    if stair>=0.55:
        labels.append('階梯式築底');reasons.append(f'下跌途中出現{rebound_count}次有效反拉')
    if multi>=0.58:
        labels.append('W/多重底');reasons.append('存在多次低點與中間反彈')
    if early>=0.62:
        reasons.append('右側初期：低點墊高、短均線初步轉強')
    if path>=0.60:
        reasons.append('近期下跌斜率逐步變緩')
    if ma_turn>=0.60:
        reasons.append('短期均線開始右轉')
    if extension_penalty>=12:
        reasons.append('扣分：右側漲幅已偏大')
    if cliff_dead>=0.35:
        reasons.append('扣分：急殺後低檔橫盤')
    if current_vertical>=0.45:
        reasons.append('扣分：近期仍有近垂直下殺')
    if not reasons:
        reasons.append('底部結構接近門檻')
    if total>=70 and early>=0.60 and rounded>=0.48 and extension_penalty<10:
        stage = '🟠 右側起漲初期'
    elif total>=62 and (rounded>=0.48 or stair>=0.55):
        stage = '🟡 築底末端'
    elif cliff_dead>=0.55:
        stage = '⚪ 急殺後盤整'
    else:
        stage = '⚪ 築底觀察'
    return {
        'code':code,'name':name,'score':round(max(0,total),1),
        'pattern':' + '.join(labels) if labels else '底部候選',
        'stage':stage,'close':round(c[-1],2),
        'turnover_million':round(today_turnover/1_000_000,1),
        'rounded_base':round(rounded*100,1),'path_quality':round(path*100,1),
        'stair_step':round(stair*100,1),'multi_bottom':round(multi*100,1),
        'right_turn':round(ma_turn*100,1),'volume_quality':round(volume_quality*100,1),
        'cliff_risk':round(cliff*100,1),'dead_base_risk':round(dead*100,1),
        'cliff_dead_penalty':round(cliff_penalty,1),'vertical_penalty':round(vertical_penalty,1),
        'extension_penalty':round(extension_penalty,1),
        'dist_from_60d_low_pct':round(dist_low*100,1),
        'ma60_gap_pct':round((c[-1]/m60-1)*100,1),
        'ret5_pct':round(r5*100,1),'ret10_pct':round(r10*100,1),
        'left_slope':round((left_sl or 0)*100,3),
        'center_slope':round((center_sl or 0)*100,3),
        'right_slope':round((right_sl or 0)*100,3),
        'reason':'；'.join(reasons),
    }


def read_universe(path):
    out = []
    with open(path,encoding='utf-8-sig') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            code = s.split(',')[0].strip()
            if code.isdigit() and len(code)==4:
                out.append(code)
    return list(dict.fromkeys(out))


def shared_tech_universe():
    try:
        master_path = ROOT/'data'/'master.json'
        if master_path.exists():
            obj = json.loads(master_path.read_text(encoding='utf-8'))
            master = obj.get('stocks',obj)
        else:
            master = fetch_master()
        tickers = sorted(tech_tickers(master))
        if tickers:
            print(f'網站共用科技股池：{len(tickers)} 檔')
            return tickers
    except Exception as e:
        print(f'網站共用科技股池取得失敗：{e}')
    print(f'改用 fallback DEFAULT_TICKERS：{len(DEFAULT_TICKERS)} 檔')
    return DEFAULT_TICKERS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top',type=int,default=50)
    ap.add_argument('--tickers',default='')
    ap.add_argument('--universe',default='')
    ap.add_argument('--sleep',type=float,default=0.15)
    a = ap.parse_args()
    tickers = ([x.strip() for x in a.tickers.split(',') if x.strip()]
               if a.tickers else read_universe(a.universe) if a.universe
               else shared_tech_universe())
    print(f'早期右側掃描 {len(tickers)} 檔｜圓弧/W底｜避免追高｜成交金額 >= 1,000萬｜Top {a.top}')
    results,failed = [],[]
    liquidity_filtered = 0
    for i,code in enumerate(tickers,1):
        d = fetch_one(code)
        if not d:
            failed.append(code)
            print(f'[{i:>3}/{len(tickers)}] {code} 下載失敗')
            continue
        _,name,rows = d
        if rows:
            close,volume = float(rows[-1][4]),float(rows[-1][5] or 0)
            if close>0 and close*volume<MIN_TURNOVER:
                liquidity_filtered += 1
                print(f'[{i:>3}/{len(tickers)}] {code} 成交金額不足｜排除')
                time.sleep(a.sleep)
                continue
        r = score_stock(code,name,rows)
        if r:
            results.append(r)
            print(f"[{i:>3}/{len(tickers)}] {code} {r['score']:>5.1f} "
                  f"圓弧:{r['rounded_base']:>5.1f} 早期右側:{r['stage']} "
                  f"追高罰:{r['extension_penalty']:>4.1f}")
        time.sleep(a.sleep)
    results.sort(key=lambda x:(-x['score'],-x['rounded_base'],-x['path_quality']))
    top = results[:a.top]
    fields = ['rank','code','name','score','pattern','stage','close','turnover_million',
              'rounded_base','path_quality','stair_step','multi_bottom','right_turn',
              'volume_quality','cliff_risk','dead_base_risk','cliff_dead_penalty',
              'vertical_penalty','extension_penalty','dist_from_60d_low_pct',
              'ma60_gap_pct','ret5_pct','ret10_pct','left_slope','center_slope',
              'right_slope','reason']
    with open(OUT_CSV,'w',newline='',encoding='utf-8-sig') as f:
        wr = csv.DictWriter(f,fieldnames=fields)
        wr.writeheader()
        for i,r in enumerate(top,1):
            wr.writerow({'rank':i,**r})
    Path(OUT_JSON).write_text(json.dumps({
        'version':'early-right-entry','generated_at':datetime.now(timezone.utc).isoformat(),
        'min_turnover':MIN_TURNOVER,'requested_top':a.top,'scanned':len(tickers),
        'success':len(results),'liquidity_filtered':liquidity_filtered,
        'failed':failed,'top':top,
    },ensure_ascii=False,indent=2),encoding='utf-8')
    print('\n===== TOP =====')
    for i,r in enumerate(top,1):
        print(f"{i:>2}. {r['code']} {r['name'][:12]:<12} {r['score']:>5.1f} {r['pattern']:<24} {r['stage']}")
        print(f"    圓弧 {r['rounded_base']}｜路徑 {r['path_quality']}｜追高罰 {r['extension_penalty']}｜{r['reason']}")
    print(f'\n流動性排除：{liquidity_filtered} 檔')
    print(f'完成評分：{len(results)} 檔')
    print(f'最終輸出：{len(top)} 檔')
    print(f'輸出：{OUT_CSV} / {OUT_JSON}')
    if failed:
        print('下載失敗：',','.join(failed))


if __name__=='__main__':
    main()
