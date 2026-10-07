#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股底部型態掃描器 v4｜圓弧落底 / 階梯式築底版

目標：
1. 優先找「下跌斜率逐步鈍化 → 圓弧落底 → 右側回升」
2. 接受階梯式下跌中反覆出現小 U，最後形成較大的 U / W
3. 排除「跳空/近垂直急殺 → 低檔長時間橫盤」的假底部
4. 60MA 尚未翻揚不直接淘汰，避免錯過早期築底
5. 本版只做選股，不做績效回測

股票池：
沿用 scripts/tech_universe.py 的網站科技股池

流動性：
當日成交金額 >= NT$10,000,000

輸出：
pattern_scan_top30.csv
pattern_scan_top30.json
預設 Top 50
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
sys.path.insert(0, str(ROOT / "scripts"))

from sources import fetch_master
from tech_universe import tech_tickers

UA = "Mozilla/5.0"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"
OUT_CSV = "pattern_scan_top30.csv"
OUT_JSON = "pattern_scan_top30.json"
MIN_TURNOVER = 10_000_000

DEFAULT_TICKERS = [
    "2330","2454","2308","2382","3231","6669","3661","3443","3035","3529",
    "6533","6643","8227","6695","3228","3037","8046","3189","2368","2383",
    "6274","6213","5347","2313","4958","2367","2408","2344","8299","6488",
    "3260","3017","3324","3653","4979","6223","3131","6510","6220","6187",
    "3211","3533","3583","4977","6515","6640","6789","6196","2467","5434",
    "8028","8086","6239","3665","6279","2059","2395","6414","5269"
]


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def mean(x):
    return sum(x) / len(x) if x else 0.0


def median(x):
    if not x:
        return 0.0
    y = sorted(x)
    n = len(y)
    return y[n // 2] if n % 2 else (y[n // 2 - 1] + y[n // 2]) / 2


def pct(a, b):
    return a / b - 1 if b else 0.0


def slope(x):
    n = len(x)
    if n < 2:
        return 0.0
    xm = (n - 1) / 2
    ym = mean(x)
    den = sum((i - xm) ** 2 for i in range(n))
    return sum((i - xm) * (v - ym) for i, v in enumerate(x)) / den if den else 0.0


def norm_slope(x):
    m = mean(x) or 1.0
    return slope(x) / m


def sma(x, n):
    return mean(x[-n:]) if len(x) >= n else None


def extrema(c, r=3, mode="min"):
    out = []
    for i in range(r, len(c) - r):
        w = c[i-r:i+r+1]
        target = min(w) if mode == "min" else max(w)
        if c[i] == target:
            out.append((i, c[i]))
    return out


def fetch_one(code):
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    for suffix in ("TW", "TWO"):
        sym = f"{code}.{suffix}"
        try:
            r = s.get(
                YAHOO + quote(sym),
                params={
                    "range": "2y",
                    "interval": "1d",
                    "events": "div,splits",
                    "includeAdjustedClose": "true",
                },
                timeout=15,
            )
            if r.status_code != 200:
                continue
            result = r.json().get("chart", {}).get("result")
            if not result:
                continue
            x = result[0]
            q = x["indicators"]["quote"][0]
            ts = x["timestamp"]
            meta = x.get("meta", {})
            name = meta.get("longName") or meta.get("shortName") or code
            rows = []
            for i, t in enumerate(ts):
                vals = [
                    q.get(k, [None] * len(ts))[i]
                    for k in ("open", "high", "low", "close", "volume")
                ]
                if any(v is None for v in vals[:4]):
                    continue
                rows.append((t, *vals))
            if len(rows) >= 160:
                return sym, name, rows
        except Exception:
            pass
    return None


def rounded_turn_score(seg):
    """
    評估一段價格是否具有「左側下降 -> 底部鈍化 -> 右側上升」的圓弧轉折
    不要求完美對稱 U。
    """
    n = len(seg)
    if n < 18:
        return 0.0, 0.0, 0.0, 0.0

    k = max(5, n // 4)
    left = seg[:k]
    center = seg[k:-k]
    right = seg[-k:]

    ls = norm_slope(left)
    cs = norm_slope(center)
    rs = norm_slope(right)

    left_down = clamp((-ls - 0.0002) / 0.0040)
    center_flat = clamp((0.0030 - abs(cs)) / 0.0030)
    right_up = clamp((rs + 0.0002) / 0.0040)

    # 底部不能只是一根尖針：最低點附近至少要有數日停留在底部區
    low = min(seg)
    high = max(seg)
    rng = max(high - low, low * 0.01)
    bottom_band = low + rng * 0.18
    bottom_days = sum(v <= bottom_band for v in seg)
    bottom_width = clamp((bottom_days - 2) / 7)

    score = (
        0.31 * left_down
        + 0.25 * center_flat
        + 0.31 * right_up
        + 0.13 * bottom_width
    )
    return score, ls, cs, rs


def best_rounded_base(c):
    """
    在最近 100 日內尋找不同長度的 U / 圓弧底。
    允許大 U 中包含小 U。
    """
    best = (0.0, None, None, None, None, None)
    n = len(c)

    for length in (24, 30, 36, 45, 55, 70, 85):
        if n < length:
            continue
        # 底部不一定剛好在今天，容許右側已經反彈後又回檔
        for end_back in (0, 3, 6, 10, 15):
            end = n - end_back
            start = end - length
            if start < 0 or end <= start:
                continue
            seg = c[start:end]
            sc, ls, cs, rs = rounded_turn_score(seg)
            if sc > best[0]:
                best = (sc, start, end, ls, cs, rs)

    return best


def stair_step_score(c):
    """
    找「邊殺邊拉」：下降過程中反覆出現局部低點後反彈，
    而不是單一路徑近垂直下殺。
    """
    look = c[-95:]
    mins = extrema(look, 2, "min")
    if len(mins) < 3:
        return 0.0, 0

    good_rebounds = 0
    rebound_strength = []
    for idx, price in mins[:-1]:
        future = look[idx+1:min(len(look), idx+9)]
        if not future:
            continue
        rb = max(future) / price - 1
        rebound_strength.append(rb)
        if rb >= 0.025:
            good_rebounds += 1

    count_score = clamp((good_rebounds - 1) / 4)
    strength_score = clamp((mean(rebound_strength) - 0.015) / 0.07)
    return 0.62 * count_score + 0.38 * strength_score, good_rebounds


def cliff_and_deadbase(c, o):
    """
    負面樣本：
    跳空/近垂直急殺後，長時間留在低檔窄幅橫盤。

    回傳：
    cliff_score 0~1
    dead_score  0~1
    combined    0~1
    """
    n = len(c)
    start = max(1, n - 120)
    worst = 0.0
    worst_i = None

    # 單日實體/收盤急殺 + 向下跳空
    for i in range(start, n):
        d1 = c[i] / c[i-1] - 1
        gap = o[i] / c[i-1] - 1 if c[i-1] else 0
        sc = max(
            clamp((-d1 - 0.055) / 0.075),
            clamp((-gap - 0.035) / 0.065),
        )
        if sc > worst:
            worst = sc
            worst_i = i

    # 3日/5日近垂直下殺
    for span, threshold, scale in ((3, 0.10, 0.12), (5, 0.14, 0.15)):
        for i in range(max(span, start), n):
            drop = c[i] / c[i-span] - 1
            sc = clamp((-drop - threshold) / scale)
            if sc > worst:
                worst = sc
                worst_i = i

    if worst_i is None:
        return 0.0, 0.0, 0.0

    after = c[worst_i:min(n, worst_i + 45)]
    if len(after) < 12:
        return worst, 0.0, worst * 0.35

    pre_anchor = mean(c[max(0, worst_i-8):worst_i]) or c[worst_i]
    after_mid = median(after)
    stayed_low = clamp((0.94 - after_mid / pre_anchor) / 0.12)

    arange = max(after) / min(after) - 1
    narrow = clamp((0.18 - arange) / 0.13)

    # 急殺後若沒有有效反拉，更像「死人盤」
    rebound = max(after) / min(after) - 1
    weak_rebound = clamp((0.12 - rebound) / 0.09)

    dead = 0.48 * stayed_low + 0.32 * narrow + 0.20 * weak_rebound
    combined = worst * dead
    return worst, dead, combined


def recent_path_quality(c):
    """
    最近 60 日切成三段：
    理想為下降斜率絕對值逐步變小，最後轉正。
    """
    seg = c[-60:]
    a, b, d = seg[:20], seg[20:40], seg[40:]
    sa, sb, sd = norm_slope(a), norm_slope(b), norm_slope(d)

    # 前段允許下降；中段比前段鈍；後段接近平或轉正
    soften = clamp((sb - sa + 0.001) / 0.005)
    right = clamp((sd + 0.0015) / 0.005)
    not_vertical = clamp((0.010 - abs(sa)) / 0.008)

    return 0.42 * soften + 0.43 * right + 0.15 * not_vertical, sa, sb, sd


def multi_bottom_score(c):
    look = c[-100:]
    mins = extrema(look, 3, "min")
    best = 0.0
    for a in range(len(mins)):
        for b in range(a+1, len(mins)):
            i1, p1 = mins[a]
            i2, p2 = mins[b]
            gap = i2 - i1
            if not 8 <= gap <= 65:
                continue
            sim = 1 - clamp(abs(p2 / p1 - 1) / 0.14)
            bounce = max(look[i1:i2+1]) / min(p1, p2) - 1
            # 不要求完全同底；反彈與時間結構更重要
            score = 0.40 * sim + 0.45 * clamp((bounce - 0.025) / 0.16) + 0.15 * clamp(gap / 35)
            best = max(best, score)
    return best


def score_stock(code, name, rows):
    rows = rows[-320:]
    O = [float(r[1]) for r in rows]
    H = [float(r[2]) for r in rows]
    L = [float(r[3]) for r in rows]
    C = [float(r[4]) for r in rows]
    V = [float(r[5] or 0) for r in rows]

    if len(C) < 160 or C[-1] <= 0:
        return None

    today_turnover = C[-1] * V[-1]
    if today_turnover < MIN_TURNOVER:
        return None

    w = min(140, len(C))
    c = C[-w:]
    o = O[-w:]
    v = V[-w:]

    rounded, rb_start, rb_end, left_sl, center_sl, right_sl = best_rounded_base(c)
    stair, rebound_count = stair_step_score(c)
    path, path1, path2, path3 = recent_path_quality(c)
    multi = multi_bottom_score(c)
    cliff, dead, cliff_dead = cliff_and_deadbase(c, o)

    # 右側轉強：不要求站上 60MA
    m5 = sma(c, 5)
    m10 = sma(c, 10)
    m20 = sma(c, 20)
    m60 = sma(c, 60)

    ma_turn = (
        0.30 * clamp((m5 / (mean(c[-10:-5]) or m5) - 1 + 0.008) / 0.035)
        + 0.30 * clamp((m10 / (mean(c[-20:-10]) or m10) - 1 + 0.010) / 0.040)
        + 0.25 * clamp((m20 / (mean(c[-40:-20]) or m20) - 1 + 0.014) / 0.050)
        + 0.15 * clamp((c[-1] / m20 - 0.96) / 0.07)
    )

    # 量縮整理 + 反彈日量能
    vol20 = mean(v[-20:])
    vol_prev = mean(v[-60:-20]) or 1
    dry = clamp((1.18 - vol20 / vol_prev) / 0.60)

    upv, dnv = [], []
    for i in range(max(1, len(c)-20), len(c)):
        (upv if c[i] >= c[i-1] else dnv).append(v[i])
    demand = clamp(((mean(upv) / (mean(dnv) or 1)) - 0.80) / 0.80)
    volume_quality = 0.52 * dry + 0.48 * demand

    # 底部位置：仍希望離近期低點不要太遠，但不把已反彈一小段全部殺掉
    low60 = min(c[-60:])
    dist_low = c[-1] / low60 - 1
    base_position = (
        1.0 if 0.03 <= dist_low <= 0.22
        else clamp(dist_low / 0.03) if dist_low < 0.03
        else clamp(1 - (dist_low - 0.22) / 0.22)
    )

    # 避免已經噴太遠
    r5 = c[-1] / c[-6] - 1
    r10 = c[-1] / c[-11] - 1
    ext20 = c[-1] / m20 - 1

    extension_penalty = (
        8 * clamp((ext20 - 0.15) / 0.14)
        + 5 * clamp((r5 - 0.15) / 0.12)
        + 7 * clamp((r10 - 0.27) / 0.18)
    )

    # 最重要：圓弧落底與路徑品質
    positive = (
        32 * rounded
        + 17 * path
        + 14 * stair
        + 10 * multi
        + 11 * ma_turn
        + 7 * volume_quality
        + 9 * base_position
    )

    # 急殺本身不是一律淘汰；只有「急殺 + 後續死人盤」重罰
    cliff_penalty = 34 * cliff_dead

    # 若最近仍是近垂直下殺，額外扣分
    current_vertical = clamp((-path3 - 0.006) / 0.008)
    vertical_penalty = 12 * current_vertical

    total = positive - cliff_penalty - vertical_penalty - extension_penalty

    # 硬性品質閘門：沒有圓弧/路徑轉折者，不讓單靠其他項目衝高
    if rounded < 0.42 and path < 0.48:
        total = min(total, 54.9)

    # 典型「跳空死人盤」直接壓低
    if cliff_dead >= 0.55:
        total = min(total, 44.9)

    labels = []
    reasons = []

    if rounded >= 0.62:
        labels.append("圓弧/U底")
        reasons.append("下跌斜率鈍化後形成圓弧並向右回升")
    elif rounded >= 0.48:
        labels.append("圓弧候選")
        reasons.append("底部已有鈍化與曲率")

    if stair >= 0.55:
        labels.append("階梯式築底")
        reasons.append(f"下跌途中出現{rebound_count}次有效反拉")

    if multi >= 0.58:
        labels.append("W/多重底")
        reasons.append("存在多次低點與中間反彈")

    if path >= 0.60:
        reasons.append("近期下跌斜率逐步變緩，右側改善")

    if ma_turn >= 0.60:
        reasons.append("短中期均線/價格開始右轉")

    if cliff_dead >= 0.35:
        reasons.append("扣分：曾急殺且後續偏低檔橫盤")

    if current_vertical >= 0.45:
        reasons.append("扣分：近期仍有近垂直下殺")

    if not reasons:
        reasons.append("底部結構接近門檻")

    if total >= 72 and rounded >= 0.60 and path >= 0.55:
        stage = "🟠 圓弧右側成形"
    elif total >= 64 and (rounded >= 0.55 or stair >= 0.58):
        stage = "🟡 築底末端"
    elif cliff_dead >= 0.55:
        stage = "⚪ 急殺後盤整"
    else:
        stage = "⚪ 築底觀察"

    return {
        "code": code,
        "name": name,
        "score": round(max(0, total), 1),
        "pattern": " + ".join(labels) if labels else "底部候選",
        "stage": stage,
        "close": round(c[-1], 2),
        "turnover_million": round(today_turnover / 1_000_000, 1),
        "rounded_base": round(rounded * 100, 1),
        "path_quality": round(path * 100, 1),
        "stair_step": round(stair * 100, 1),
        "multi_bottom": round(multi * 100, 1),
        "right_turn": round(ma_turn * 100, 1),
        "volume_quality": round(volume_quality * 100, 1),
        "cliff_risk": round(cliff * 100, 1),
        "dead_base_risk": round(dead * 100, 1),
        "cliff_dead_penalty": round(cliff_penalty, 1),
        "vertical_penalty": round(vertical_penalty, 1),
        "extension_penalty": round(extension_penalty, 1),
        "dist_from_60d_low_pct": round(dist_low * 100, 1),
        "ma60_gap_pct": round((c[-1] / m60 - 1) * 100, 1),
        "ret5_pct": round(r5 * 100, 1),
        "ret10_pct": round(r10 * 100, 1),
        "left_slope": round((left_sl or 0) * 100, 3),
        "center_slope": round((center_sl or 0) * 100, 3),
        "right_slope": round((right_sl or 0) * 100, 3),
        "reason": "；".join(reasons),
    }


def read_universe(path):
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            code = s.split(",")[0].strip()
            if code.isdigit() and len(code) == 4:
                out.append(code)
    return list(dict.fromkeys(out))


def shared_tech_universe():
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--tickers", default="")
    ap.add_argument("--universe", default="")
    ap.add_argument("--sleep", type=float, default=0.15)
    a = ap.parse_args()

    tickers = (
        [x.strip() for x in a.tickers.split(",") if x.strip()]
        if a.tickers
        else read_universe(a.universe)
        if a.universe
        else shared_tech_universe()
    )

    print(
        f"V4 掃描 {len(tickers)} 檔｜圓弧落底 + 階梯式築底"
        f"｜排除急殺死人盤｜成交金額 >= 1,000萬｜Top {a.top}"
    )

    results = []
    failed = []
    liquidity_filtered = 0

    for i, code in enumerate(tickers, 1):
        d = fetch_one(code)
        if not d:
            failed.append(code)
            print(f"[{i:>3}/{len(tickers)}] {code} 下載失敗")
            continue

        _, name, rows = d
        if rows:
            last_close = float(rows[-1][4])
            last_volume = float(rows[-1][5] or 0)
            turnover = last_close * last_volume
            if last_close > 0 and turnover < MIN_TURNOVER:
                liquidity_filtered += 1
                print(
                    f"[{i:>3}/{len(tickers)}] {code} "
                    f"成交金額 {turnover / 1_000_000:.1f}M ＜ 10M｜排除"
                )
                time.sleep(a.sleep)
                continue

        r = score_stock(code, name, rows)
        if r:
            results.append(r)
            print(
                f"[{i:>3}/{len(tickers)}] {code} {r['score']:>5.1f} "
                f"圓弧:{r['rounded_base']:>5.1f} "
                f"路徑:{r['path_quality']:>5.1f} "
                f"階梯:{r['stair_step']:>5.1f} "
                f"急殺盤整罰:{r['cliff_dead_penalty']:>4.1f} "
                f"{r['stage']}"
            )
        time.sleep(a.sleep)

    results.sort(key=lambda x: (-x["score"], -x["rounded_base"], -x["path_quality"]))
    top = results[:a.top]

    fields = [
        "rank","code","name","score","pattern","stage","close","turnover_million",
        "rounded_base","path_quality","stair_step","multi_bottom","right_turn",
        "volume_quality","cliff_risk","dead_base_risk","cliff_dead_penalty",
        "vertical_penalty","extension_penalty","dist_from_60d_low_pct",
        "ma60_gap_pct","ret5_pct","ret10_pct","left_slope","center_slope",
        "right_slope","reason",
    ]

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        for i, r in enumerate(top, 1):
            wr.writerow({"rank": i, **r})

    Path(OUT_JSON).write_text(
        json.dumps(
            {
                "version": "v4-rounded-bottom-path-quality",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "min_turnover": MIN_TURNOVER,
                "requested_top": a.top,
                "scanned": len(tickers),
                "success": len(results),
                "liquidity_filtered": liquidity_filtered,
                "failed": failed,
                "top": top,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n===== V4 TOP =====")
    for i, r in enumerate(top, 1):
        print(
            f"{i:>2}. {r['code']} {r['name'][:12]:<12} "
            f"{r['score']:>5.1f} {r['pattern']:<24} {r['stage']}"
        )
        print(
            f"    圓弧 {r['rounded_base']}｜路徑 {r['path_quality']}"
            f"｜階梯 {r['stair_step']}｜急殺盤整罰 {r['cliff_dead_penalty']}"
            f"｜{r['reason']}"
        )

    print(f"\n流動性排除：{liquidity_filtered} 檔")
    print(f"完成評分：{len(results)} 檔")
    print(f"最終輸出：{len(top)} 檔")
    print(f"輸出：{OUT_CSV} / {OUT_JSON}")

    if failed:
        print("下載失敗：", ",".join(failed))


if __name__ == "__main__":
    main()
