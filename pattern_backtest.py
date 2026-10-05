#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股底部型態策略歷史回測
直接沿用 pattern_scanner.py 的 score_stock()，不複製、不改動選股公式

回測方式：
- 使用目前網站共用科技股池
- 每個歷史訊號日只提供「當日以前」K線給 score_stock()
- 當日成交金額 >= 1,000 萬的條件由原 scanner 負責
- 每個訊號日取 Top 50
- 計算選股後 5 / 10 / 20 個交易日報酬
- 預設回測所有具有完整 20D 未來資料的歷史訊號日

注意：
股票池使用目前 repo 的 tech_universe 回看歷史，
尚未具備歷史 point-in-time 成分股資料，因此可能存在 survivorship bias
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pattern_scanner as scanner

ROOT = Path(__file__).resolve().parent

OUT_DETAIL_CSV = ROOT / "pattern_backtest.csv"
OUT_SUMMARY_CSV = ROOT / "pattern_backtest_summary.csv"
OUT_JSON = ROOT / "pattern_backtest.json"

FORWARD_DAYS = (5, 10, 20)


def mean(values):
    return sum(values) / len(values) if values else None


def median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def row_date(row):
    return datetime.fromtimestamp(
        row[0], timezone.utc
    ).date().isoformat()


def download_history(tickers, sleep_seconds=0.15):
    import time

    cache = {}
    failed = []

    for i, code in enumerate(tickers, 1):
        data = scanner.fetch_one(code)

        if not data:
            failed.append(code)
            print(
                f"[下載 {i:>3}/{len(tickers)}] "
                f"{code} 失敗"
            )
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


def get_calendar(cache):
    if "2330" in cache:
        rows = cache["2330"]["rows"]
    else:
        rows = max(
            (item["rows"] for item in cache.values()),
            key=len
        )

    return [row_date(row) for row in rows]


def forward_return(info, signal_date, days):
    idx = info["date_to_index"].get(signal_date)

    if idx is None:
        return None

    target_idx = idx + days

    if target_idx >= len(info["rows"]):
        return None

    entry = info["rows"][idx][4]
    exit_price = info["rows"][target_idx][4]

    if not entry or not exit_price:
        return None

    return (exit_price / entry - 1) * 100


def run_backtest(cache, top_n=50, backtest_days=0):
    calendar = get_calendar(cache)

    # score_stock 至少需要 160 根K
    # 並保留最後20個交易日作為 forward return
    if len(calendar) < 181:
        raise RuntimeError(
            "歷史資料不足，無法執行 20 個交易日回測"
        )

    signal_dates = calendar[159:-20]

    if backtest_days > 0:
        signal_dates = signal_dates[-backtest_days:]

    print("")
    print("===== 歷史滾動回測 =====")
    print(f"訊號日：{len(signal_dates)}")
    print(f"每次選股：Top {top_n}")
    print("Forward：5D / 10D / 20D")
    print("")

    details = []
    summaries = []

    for di, signal_date in enumerate(signal_dates, 1):
        candidates = []

        for code, info in cache.items():
            idx = info["date_to_index"].get(signal_date)

            if idx is None or idx < 159:
                continue

            # 關鍵：只給 score_stock 訊號日以前資料
            # 因此選股公式完全看不到未來
            history_until_signal = info["rows"][:idx + 1]

            result = scanner.score_stock(
                code,
                info["name"],
                history_until_signal
            )

            if not result:
                continue

            candidates.append(result)

        candidates.sort(
            key=lambda x: (
                -x["score"],
                scanner.priority(x["stage"])
            )
        )

        selected = candidates[:top_n]

        returns = {
            5: [],
            10: [],
            20: []
        }

        for rank, result in enumerate(selected, 1):
            info = cache[result["code"]]

            ret5 = forward_return(
                info, signal_date, 5
            )
            ret10 = forward_return(
                info, signal_date, 10
            )
            ret20 = forward_return(
                info, signal_date, 20
            )

            row = {
                "signal_date": signal_date,
                "rank": rank,
                "code": result["code"],
                "name": result["name"],
                "score": result["score"],
                "pattern": result["pattern"],
                "stage": result["stage"],
                "entry_close": result["close"],
                "turnover_million": result.get(
                    "turnover_million"
                ),
                "ret_5d_pct": (
                    round(ret5, 2)
                    if ret5 is not None
                    else None
                ),
                "ret_10d_pct": (
                    round(ret10, 2)
                    if ret10 is not None
                    else None
                ),
                "ret_20d_pct": (
                    round(ret20, 2)
                    if ret20 is not None
                    else None
                )
            }

            details.append(row)

            if ret5 is not None:
                returns[5].append(ret5)
            if ret10 is not None:
                returns[10].append(ret10)
            if ret20 is not None:
                returns[20].append(ret20)

        summary = {
            "signal_date": signal_date,
            "selected": len(selected)
        }

        for days in FORWARD_DAYS:
            values = returns[days]

            summary[f"avg_{days}d_pct"] = (
                round(mean(values), 2)
                if values else None
            )

            summary[f"median_{days}d_pct"] = (
                round(median(values), 2)
                if values else None
            )

            summary[f"win_rate_{days}d_pct"] = (
                round(
                    sum(x > 0 for x in values)
                    / len(values)
                    * 100,
                    1
                )
                if values else None
            )

        summaries.append(summary)

        print(
            f"[{di:>3}/{len(signal_dates)}] "
            f"{signal_date} "
            f"選出 {len(selected):>2} 檔"
            f"｜5D {summary['avg_5d_pct']}%"
            f"｜10D {summary['avg_10d_pct']}%"
            f"｜20D {summary['avg_20d_pct']}%"
        )

    return details, summaries, signal_dates


def build_overall(details):
    overall = {
        "selection_rows": len(details)
    }

    for days in FORWARD_DAYS:
        key = f"ret_{days}d_pct"

        values = [
            row[key]
            for row in details
            if row[key] is not None
        ]

        overall[f"avg_{days}d_pct"] = (
            round(mean(values), 2)
            if values else None
        )

        overall[f"median_{days}d_pct"] = (
            round(median(values), 2)
            if values else None
        )

        overall[f"win_rate_{days}d_pct"] = (
            round(
                sum(x > 0 for x in values)
                / len(values)
                * 100,
                1
            )
            if values else None
        )

    return overall


def write_outputs(
    details,
    summaries,
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

    with OUT_DETAIL_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=detail_fields
        )
        writer.writeheader()
        writer.writerows(details)

    summary_fields = [
        "signal_date",
        "selected",
        "avg_5d_pct",
        "median_5d_pct",
        "win_rate_5d_pct",
        "avg_10d_pct",
        "median_10d_pct",
        "win_rate_10d_pct",
        "avg_20d_pct",
        "median_20d_pct",
        "win_rate_20d_pct"
    ]

    with OUT_SUMMARY_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=summary_fields
        )
        writer.writeheader()
        writer.writerows(summaries)

    overall = build_overall(details)

    payload = {
        "version": "v1-pattern-rolling-backtest",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "top_n": top_n,
        "min_turnover": getattr(
            scanner,
            "MIN_TURNOVER",
            10_000_000
        ),
        "forward_days": [5, 10, 20],
        "signal_days": len(signal_dates),
        "first_signal_date": (
            signal_dates[0]
            if signal_dates else None
        ),
        "last_signal_date": (
            signal_dates[-1]
            if signal_dates else None
        ),
        "failed_tickers": failed,
        "method": (
            "每個歷史訊號日只使用當日以前K線，"
            "直接呼叫 pattern_scanner.py 的 score_stock()；"
            "依原策略分數排序取Top N，"
            "再計算往後5/10/20交易日收盤報酬"
        ),
        "universe_note": (
            "使用目前 repo 的 tech_universe 固定回看歷史；"
            "尚未使用歷史 point-in-time 成分股，"
            "因此可能存在 survivorship bias"
        ),
        "overall": overall,
        "daily_summary": summaries,
        "rows": details
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
    print("===== 整體回測結果 =====")
    print(f"訊號日：{len(signal_dates)}")
    print(f"選股筆數：{len(details)}")

    for days in FORWARD_DAYS:
        print(
            f"{days:>2}D"
            f"｜平均 {overall[f'avg_{days}d_pct']}%"
            f"｜中位數 {overall[f'median_{days}d_pct']}%"
            f"｜勝率 {overall[f'win_rate_{days}d_pct']}%"
        )

    print("")
    print("輸出：")
    print(OUT_DETAIL_CSV.name)
    print(OUT_SUMMARY_CSV.name)
    print(OUT_JSON.name)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--top",
        type=int,
        default=50
    )

    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help=(
            "只回測最近N個已有完整20D結果的訊號日；"
            "0代表目前2年K線可回測的全部日期"
        )
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
        f"｜Top {args.top}"
        f"｜5D/10D/20D"
    )

    cache, failed = download_history(
        tickers,
        sleep_seconds=args.sleep
    )

    details, summaries, signal_dates = run_backtest(
        cache,
        top_n=args.top,
        backtest_days=args.days
    )

    write_outputs(
        details,
        summaries,
        signal_dates,
        failed,
        args.top
    )


if __name__ == "__main__":
    main()
