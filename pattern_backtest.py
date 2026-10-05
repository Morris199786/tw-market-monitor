#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股底部型態策略歷史回測
直接沿用 pattern_scanner.py 的 score_stock()，不複製、不修改正式選股公式

輸出：
1. pattern_backtest.csv
   - 每個訊號日 Top 50 個股明細
   - 含 5D / 10D / 20D 報酬
2. pattern_backtest_summary.csv
   - 每個訊號日 Top 5 / Top 10 / Top 50 組合統計
3. pattern_backtest.json
   - 完整個股明細、每日組合統計、整體 Top5/Top10/Top50 統計

回測：
- 每個歷史訊號日只使用當日以前資料
- 直接呼叫正式 pattern_scanner.score_stock()
- 流動性條件沿用正式 scanner（目前 >= 1,000 萬）
- 排名沿用正式 score + stage priority
- 計算選股日收盤至未來第 5 / 10 / 20 個交易日收盤報酬

注意：
目前股票池使用「現在的 tech_universe」回看歷史，
不是歷史 point-in-time 股票池，因此仍可能有 survivorship bias
"""

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pattern_scanner as scanner

ROOT = Path(__file__).resolve().parent

DETAIL_CSV = ROOT / "pattern_backtest.csv"
SUMMARY_CSV = ROOT / "pattern_backtest_summary.csv"
OUT_JSON = ROOT / "pattern_backtest.json"

FORWARD_DAYS = (5, 10, 20)
GROUPS = (5, 10, 50)


def avg(values):
    return sum(values) / len(values) if values else None


def med(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def rounded(x, n=2):
    return round(x, n) if x is not None else None


def row_date(row):
    return datetime.fromtimestamp(row[0], timezone.utc).date().isoformat()


def download_history(tickers, sleep_seconds):
    cache = {}
    failed = []

    for i, code in enumerate(tickers, 1):
        data = scanner.fetch_one(code)

        if not data:
            failed.append(code)
            print(f"[下載 {i:>3}/{len(tickers)}] {code} 失敗")
            continue

        _, name, rows = data

        cache[code] = {
            "name": name,
            "rows": rows,
            "date_to_index": {
                row_date(row): idx
                for idx, row in enumerate(rows)
            }
        }

        if i % 25 == 0 or i == len(tickers):
            print(
                f"[下載 {i:>3}/{len(tickers)}] "
                f"成功 {len(cache)} 檔"
            )

        time.sleep(sleep_seconds)

    return cache, failed


def trading_calendar(cache):
    if "2330" in cache:
        rows = cache["2330"]["rows"]
    else:
        rows = max(
            (x["rows"] for x in cache.values()),
            key=len
        )

    return [row_date(r) for r in rows]


def forward_return(info, signal_date, days):
    idx = info["date_to_index"].get(signal_date)

    if idx is None:
        return None

    target = idx + days

    if target >= len(info["rows"]):
        return None

    entry = info["rows"][idx][4]
    exit_price = info["rows"][target][4]

    if not entry or not exit_price:
        return None

    return (exit_price / entry - 1) * 100


def stats(rows, days):
    key = f"ret_{days}d_pct"
    vals = [
        float(r[key])
        for r in rows
        if r.get(key) is not None
    ]

    if not vals:
        return {
            "avg": None,
            "median": None,
            "win_rate": None,
            "count": 0
        }

    return {
        "avg": rounded(avg(vals)),
        "median": rounded(med(vals)),
        "win_rate": rounded(
            sum(x > 0 for x in vals) / len(vals) * 100,
            1
        ),
        "count": len(vals)
    }


def run_backtest(cache, top_n=50, backtest_days=0):
    calendar = trading_calendar(cache)

    if len(calendar) < 181:
        raise RuntimeError("歷史資料不足，無法計算完整 20D 回測")

    signal_dates = calendar[159:-20]

    if backtest_days > 0:
        signal_dates = signal_dates[-backtest_days:]

    detail_rows = []
    summary_rows = []

    print("")
    print("===== ROLLING BACKTEST =====")
    print(f"訊號日：{len(signal_dates)}")
    print(f"每個訊號日先保留 Top {top_n}")
    print("統計：Top 5 / Top 10 / Top 50")
    print("Forward：5D / 10D / 20D")
    print("")

    for day_no, signal_date in enumerate(signal_dates, 1):
        candidates = []

        for code, info in cache.items():
            idx = info["date_to_index"].get(signal_date)

            if idx is None or idx < 159:
                continue

            # 嚴格只把訊號日以前資料交給正式 score_stock
            historical_rows = info["rows"][:idx + 1]

            result = scanner.score_stock(
                code,
                info["name"],
                historical_rows
            )

            if result:
                candidates.append(result)

        candidates.sort(
            key=lambda x: (
                -x["score"],
                scanner.priority(x["stage"])
            )
        )

        selected = candidates[:top_n]
        this_day = []

        for rank, result in enumerate(selected, 1):
            info = cache[result["code"]]

            r5 = forward_return(info, signal_date, 5)
            r10 = forward_return(info, signal_date, 10)
            r20 = forward_return(info, signal_date, 20)

            row = {
                "signal_date": signal_date,
                "rank": rank,
                "code": result["code"],
                "name": result["name"],
                "score": result["score"],
                "pattern": result["pattern"],
                "stage": result["stage"],
                "entry_close": result["close"],
                "turnover_million": result.get("turnover_million"),
                "ret_5d_pct": rounded(r5),
                "ret_10d_pct": rounded(r10),
                "ret_20d_pct": rounded(r20)
            }

            detail_rows.append(row)
            this_day.append(row)

        summary = {
            "signal_date": signal_date,
            "selected": len(this_day)
        }

        for group in GROUPS:
            group_rows = [
                r for r in this_day
                if r["rank"] <= group
            ]

            for days in FORWARD_DAYS:
                s = stats(group_rows, days)
                prefix = f"top{group}_{days}d"

                summary[f"{prefix}_avg_pct"] = s["avg"]
                summary[f"{prefix}_median_pct"] = s["median"]
                summary[f"{prefix}_win_rate_pct"] = s["win_rate"]

        summary_rows.append(summary)

        print(
            f"[{day_no:>3}/{len(signal_dates)}] {signal_date}"
            f" | Top5 20D {summary['top5_20d_avg_pct']}%"
            f" | Top10 20D {summary['top10_20d_avg_pct']}%"
            f" | Top50 20D {summary['top50_20d_avg_pct']}%"
        )

    return detail_rows, summary_rows, signal_dates


def overall_group_stats(detail_rows):
    result = {}

    for group in GROUPS:
        rows = [
            r for r in detail_rows
            if r["rank"] <= group
        ]

        block = {
            "selection_rows": len(rows)
        }

        for days in FORWARD_DAYS:
            s = stats(rows, days)
            block[f"avg_{days}d_pct"] = s["avg"]
            block[f"median_{days}d_pct"] = s["median"]
            block[f"win_rate_{days}d_pct"] = s["win_rate"]
            block[f"observations_{days}d"] = s["count"]

        result[f"top{group}"] = block

    return result


def positive_portfolio_day_rates(summary_rows):
    result = {}

    for group in GROUPS:
        block = {}

        for days in FORWARD_DAYS:
            key = f"top{group}_{days}d_avg_pct"
            vals = [
                r[key]
                for r in summary_rows
                if r.get(key) is not None
            ]

            block[f"positive_days_{days}d_pct"] = (
                rounded(
                    sum(x > 0 for x in vals)
                    / len(vals)
                    * 100,
                    1
                )
                if vals else None
            )

        result[f"top{group}"] = block

    return result


def write_outputs(
    detail_rows,
    summary_rows,
    signal_dates,
    failed,
    top_n
):
    detail_fields = [
        "signal_date",
        "rank",
        "code",
        "name",
        "score",
        "pattern",
        "stage",
        "entry_close",
        "turnover_million",
        "ret_5d_pct",
        "ret_10d_pct",
        "ret_20d_pct"
    ]

    with DETAIL_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=detail_fields
        )
        writer.writeheader()
        writer.writerows(detail_rows)

    summary_fields = [
        "signal_date",
        "selected"
    ]

    for group in GROUPS:
        for days in FORWARD_DAYS:
            summary_fields.extend([
                f"top{group}_{days}d_avg_pct",
                f"top{group}_{days}d_median_pct",
                f"top{group}_{days}d_win_rate_pct"
            ])

    with SUMMARY_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=summary_fields
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    overall = overall_group_stats(detail_rows)
    positive_days = positive_portfolio_day_rates(summary_rows)

    payload = {
        "version": "v2-top5-top10-top50-backtest",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "top_n_scanned": top_n,
        "groups": list(GROUPS),
        "forward_days": list(FORWARD_DAYS),
        "min_turnover": getattr(
            scanner,
            "MIN_TURNOVER",
            10_000_000
        ),
        "signal_days": len(signal_dates),
        "first_signal_date": (
            signal_dates[0] if signal_dates else None
        ),
        "last_signal_date": (
            signal_dates[-1] if signal_dates else None
        ),
        "failed_tickers": failed,
        "method": (
            "每個歷史訊號日只使用當日以前K線，"
            "直接呼叫正式pattern_scanner.score_stock；"
            "按正式分數與stage priority排序，"
            "保留Top50後分別統計Top5、Top10、Top50；"
            "計算選股日收盤至未來5/10/20交易日收盤報酬"
        ),
        "universe_note": (
            "股票池使用目前repo的tech_universe固定回看歷史，"
            "不是歷史point-in-time股票池，"
            "因此可能存在survivorship bias"
        ),
        "overall": overall,
        "positive_portfolio_days": positive_days,
        "daily_summary": summary_rows,
        "rows": detail_rows
    }

    OUT_JSON.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("")
    print("===== OVERALL =====")

    for group in GROUPS:
        x = overall[f"top{group}"]
        p = positive_days[f"top{group}"]

        print("")
        print(f"Top {group}")

        for days in FORWARD_DAYS:
            print(
                f"  {days:>2}D"
                f" 平均 {x[f'avg_{days}d_pct']}%"
                f" | 中位數 {x[f'median_{days}d_pct']}%"
                f" | 個股勝率 {x[f'win_rate_{days}d_pct']}%"
                f" | 組合正報酬日 "
                f"{p[f'positive_days_{days}d_pct']}%"
            )

    print("")
    print("輸出完成：")
    print(DETAIL_CSV.name)
    print(SUMMARY_CSV.name)
    print(OUT_JSON.name)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="每個歷史訊號日保留的最大排名，請維持>=50"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="0=全部；N=只回測最近N個完整訊號日"
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=0.15
    )

    parser.add_argument(
        "--tickers",
        default=""
    )

    args = parser.parse_args()

    if args.top < 50:
        raise ValueError(
            "--top 必須 >= 50，才能同時計算 Top5/Top10/Top50"
        )

    if args.tickers:
        tickers = [
            x.strip()
            for x in args.tickers.split(",")
            if x.strip()
        ]
    else:
        tickers = scanner.shared_tech_universe()

    print(
        f"回測股票池：{len(tickers)} 檔"
        f" | 保留 Top {args.top}"
        f" | 統計 Top5/Top10/Top50"
        f" | 5D/10D/20D"
    )

    cache, failed = download_history(
        tickers,
        args.sleep
    )

    detail_rows, summary_rows, signal_dates = run_backtest(
        cache,
        top_n=args.top,
        backtest_days=args.days
    )

    write_outputs(
        detail_rows,
        summary_rows,
        signal_dates,
        failed,
        args.top
    )


if __name__ == "__main__":
    main()
