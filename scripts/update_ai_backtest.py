from sources import *
from statistics import median


BACKTEST_PATH = ROOT / "data/ai_backtest.json"
MARKET_HISTORY_DIR = ROOT / "data/history/market"


def market_snapshots():
    out = []
    for p in sorted(MARKET_HISTORY_DIR.glob("*.json")):
        d = load_json(p, {})
        date = str(d.get("date") or p.stem or "").strip()
        stocks = d.get("stocks", {})
        if date and stocks:
            out.append({"date": date, "stocks": stocks})
    return out


def valid_price(v):
    try:
        x = float(v)
        return x if x > 0 else None
    except Exception:
        return None


def pct_return(entry, exit_price):
    if not entry or not exit_price:
        return None
    return round((float(exit_price) / float(entry) - 1) * 100, 4)


def evaluate_record(rec, snapshots, date_index):
    selection_date = rec.get("selection_date")
    ticker = str(rec.get("ticker") or "")
    idx = date_index.get(selection_date)
    if idx is None:
        return rec

    for days in (5, 10):
        key = f"return_{days}d"
        status_key = f"status_{days}d"
        end_date_key = f"end_date_{days}d"
        target_idx = idx + days

        if target_idx >= len(snapshots):
            rec[key] = None
            rec[status_key] = "pending"
            rec[end_date_key] = None
            continue

        target = snapshots[target_idx]
        q = target["stocks"].get(ticker, {})
        exit_price = valid_price(q.get("price"))

        if exit_price is None:
            rec[key] = None
            rec[status_key] = "unavailable"
            rec[end_date_key] = target["date"]
            continue

        rec[key] = pct_return(rec.get("entry_price"), exit_price)
        rec[status_key] = "complete"
        rec[end_date_key] = target["date"]

    return rec


def stats_for(records, days):
    key = f"return_{days}d"
    vals = [
        float(r[key])
        for r in records
        if r.get(f"status_{days}d") == "complete" and r.get(key) is not None
    ]

    if not vals:
        return {
            "avg_return": None,
            "median_return": None,
            "win_rate": None,
            "samples": 0,
        }

    return {
        "avg_return": round(sum(vals) / len(vals), 4),
        "median_return": round(median(vals), 4),
        "win_rate": round(sum(1 for x in vals if x > 0) / len(vals) * 100, 2),
        "samples": len(vals),
    }


def summary_block(records):
    return {
        "5d": stats_for(records, 5),
        "10d": stats_for(records, 10),
    }


def build_summary(records):
    out = {
        "all": summary_block(records),
        "twse": summary_block([r for r in records if r.get("market") == "twse"]),
        "tpex": summary_block([r for r in records if r.get("market") == "tpex"]),
        "rank_buckets": {},
    }

    for label, max_rank in (("top5", 5), ("top10", 10), ("top20", 20)):
        subset = [r for r in records if int(r.get("rank") or 999) <= max_rank]
        out["rank_buckets"][label] = summary_block(subset)

    return out


def current_records(ai, market_data):
    selection_date = str(market_data.get("date") or "").strip()
    stocks = market_data.get("stocks", {})

    if not selection_date:
        raise RuntimeError("market_latest.json has no date")

    rows = []
    for mk in ("twse", "tpex"):
        for rank, x in enumerate(ai.get(mk, []), start=1):
            ticker = str(x.get("ticker") or "")
            entry_price = valid_price(stocks.get(ticker, {}).get("price"))
            if not ticker or entry_price is None:
                continue

            rows.append({
                "selection_date": selection_date,
                "market": mk,
                "ticker": ticker,
                "name": x.get("name") or ticker,
                "rank": rank,
                "score": x.get("score"),
                "entry_price": entry_price,
                "return_5d": None,
                "return_10d": None,
                "status_5d": "pending",
                "status_10d": "pending",
                "end_date_5d": None,
                "end_date_10d": None,
            })

    return selection_date, rows


def main():
    ai = load_json(ROOT / "data/ai_picks.json", {})
    market_data = load_json(ROOT / "data/market_latest.json", {})
    old = load_json(BACKTEST_PATH, {})
    records = list(old.get("records", []) or [])

    selection_date, today_rows = current_records(ai, market_data)

    # 同一交易日若重跑，以最後一次 AI 名單為準
    records = [r for r in records if r.get("selection_date") != selection_date]
    records.extend(today_rows)

    snapshots = market_snapshots()
    date_index = {x["date"]: i for i, x in enumerate(snapshots)}

    records = [evaluate_record(r, snapshots, date_index) for r in records]
    records.sort(
        key=lambda r: (
            r.get("selection_date") or "",
            r.get("market") or "",
            int(r.get("rank") or 999),
        ),
        reverse=True,
    )

    dates = sorted({r.get("selection_date") for r in records if r.get("selection_date")})

    out = {
        "updated_at": now_tpe().isoformat(timespec="minutes"),
        "method": {
            "entry": "AI選股基準交易日收盤價",
            "return_5d": "基準日後第5個交易日收盤價相對基準日收盤價",
            "return_10d": "基準日後第10個交易日收盤價相對基準日收盤價",
            "calendar_basis": "交易日，不是日曆日",
            "notes": [
                "同一股票在不同選股日視為不同訊號樣本",
                "未滿5或10個交易日的訊號顯示進行中",
                "目前先做絕對報酬與勝率，不使用未驗證的大盤代理指標",
            ],
        },
        "start_date": dates[0] if dates else selection_date,
        "latest_selection_date": selection_date,
        "selection_days": len(dates),
        "record_count": len(records),
        "summary": build_summary(records),
        "records": records,
    }

    save_json(BACKTEST_PATH, out)

    print(
        "ai backtest",
        "selection_date", selection_date,
        "records", len(records),
        "5d samples", out["summary"]["all"]["5d"]["samples"],
        "10d samples", out["summary"]["all"]["10d"]["samples"],
    )


if __name__ == "__main__":
    main()
