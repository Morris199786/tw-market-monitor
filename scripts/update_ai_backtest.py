from sources import *
from statistics import median
from datetime import datetime

BACKTEST_PATH = ROOT / "data/ai_backtest.json"
MARKET_HISTORY_DIR = ROOT / "data/history/market"
MA_DAYS = 10


def normalize_date(value):
    s = str(value or "").strip()
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 8:
        try:
            return datetime.strptime(digits, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def market_snapshots():
    by_date = {}
    for p in sorted(MARKET_HISTORY_DIR.glob("*.json")):
        d = load_json(p, {})
        date = normalize_date(d.get("date") or p.stem)
        stocks = d.get("stocks", {})
        if date and isinstance(stocks, dict) and stocks:
            by_date[date] = {"date": date, "stocks": stocks}
    return [by_date[k] for k in sorted(by_date)]


def valid_price(v):
    try:
        x = float(v)
        return x if x > 0 and x != float("inf") and x == x else None
    except (TypeError, ValueError, OverflowError):
        return None


def pct_return(entry, exit_price):
    if not entry or not exit_price:
        return None
    return round((float(exit_price) / float(entry) - 1) * 100, 4)


def price_at(snapshots, idx, ticker):
    if idx < 0 or idx >= len(snapshots):
        return None
    return valid_price(snapshots[idx]["stocks"].get(ticker, {}).get("price"))


def ma10_at(snapshots, idx, ticker):
    """最近10個有效交易收盤價；不把停牌缺價當作跌破訊號。"""
    values = []
    for j in range(idx, -1, -1):
        price = price_at(snapshots, j, ticker)
        if price is not None:
            values.append(price)
        if len(values) == MA_DAYS:
            return sum(values) / MA_DAYS
    return None


def latest_price_on_or_before(snapshots, idx, ticker):
    """到期日停牌時，使用此前最近有效收盤價，不使用未來價格。"""
    for j in range(idx, -1, -1):
        price = price_at(snapshots, j, ticker)
        if price is not None:
            return price, snapshots[j]["date"]
    return None, None


def evaluate_record(rec, snapshots, date_index):
    selection_date = normalize_date(rec.get("selection_date"))
    ticker = str(rec.get("ticker") or "")
    idx = date_index.get(selection_date)
    if idx is None:
        return rec

    entry = valid_price(rec.get("entry_price"))
    # 每次重新計算，避免舊結果與新規則混用
    exit_idx = None
    exit_price = None
    exit_ma10 = None
    for j in range(idx + 1, min(idx + 10, len(snapshots) - 1) + 1):
        close = price_at(snapshots, j, ticker)
        ma10 = ma10_at(snapshots, j, ticker)
        if close is not None and ma10 is not None and close < ma10:
            exit_idx, exit_price, exit_ma10 = j, close, ma10
            break

    rec["ma10_exit_date"] = snapshots[exit_idx]["date"] if exit_idx is not None else None
    rec["ma10_exit_price"] = exit_price
    rec["ma10_exit_value"] = round(exit_ma10, 4) if exit_ma10 is not None else None
    rec["ma10_exit_day"] = exit_idx - idx if exit_idx is not None else None

    for days in (5, 10):
        key = f"return_{days}d"
        status_key = f"status_{days}d"
        end_date_key = f"end_date_{days}d"
        baseline_key = f"baseline_return_{days}d"
        baseline_status_key = f"baseline_status_{days}d"
        target_idx = idx + days

        # 舊策略：固定持有N個交易日，用來與MA10策略比較
        if target_idx >= len(snapshots):
            rec[baseline_key] = None
            rec[baseline_status_key] = "pending"
        else:
            baseline_price, _ = latest_price_on_or_before(snapshots, target_idx, ticker)
            rec[baseline_key] = pct_return(entry, baseline_price)
            rec[baseline_status_key] = "complete" if rec[baseline_key] is not None else "unavailable"

        # 提前出場後即鎖定實現報酬，5/10日績效皆可提早完成
        if exit_idx is not None and exit_idx <= target_idx:
            rec[key] = pct_return(entry, exit_price)
            rec[status_key] = "complete" if rec[key] is not None else "unavailable"
            rec[end_date_key] = snapshots[exit_idx]["date"]
            continue

        if target_idx >= len(snapshots):
            rec[key] = None
            rec[status_key] = "pending"
            rec[end_date_key] = None
            continue

        price, effective_date = latest_price_on_or_before(snapshots, target_idx, ticker)
        rec[key] = pct_return(entry, price)
        rec[status_key] = "complete" if rec[key] is not None else "unavailable"
        rec[end_date_key] = effective_date or snapshots[target_idx]["date"]

    return rec


def stats_for(records, days, prefix=""):
    key = f"{prefix}return_{days}d"
    status_key = f"{prefix}status_{days}d"
    vals = [float(r[key]) for r in records if r.get(status_key) == "complete" and r.get(key) is not None]
    if not vals:
        return {"avg_return": None, "median_return": None, "win_rate": None, "samples": 0}
    return {
        "avg_return": round(sum(vals) / len(vals), 4),
        "median_return": round(median(vals), 4),
        "win_rate": round(sum(x > 0 for x in vals) / len(vals) * 100, 2),
        "samples": len(vals),
    }


def summary_block(records, prefix=""):
    return {"5d": stats_for(records, 5, prefix), "10d": stats_for(records, 10, prefix)}


def build_summary(records, prefix=""):
    out = {
        "all": summary_block(records, prefix),
        "twse": summary_block([r for r in records if r.get("market") == "twse"], prefix),
        "tpex": summary_block([r for r in records if r.get("market") == "tpex"], prefix),
        "rank_buckets": {},
    }
    for label, max_rank in (("top5", 5), ("top10", 10), ("top20", 20)):
        subset = [r for r in records if int(r.get("rank") or 999) <= max_rank]
        out["rank_buckets"][label] = summary_block(subset, prefix)
    return out


def current_records(ai, market_data):
    selection_date = normalize_date(market_data.get("date"))
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
                "selection_date": selection_date, "market": mk, "ticker": ticker,
                "name": x.get("name") or ticker, "rank": rank, "score": x.get("score"),
                "entry_price": entry_price, "return_5d": None, "return_10d": None,
                "status_5d": "pending", "status_10d": "pending",
                "end_date_5d": None, "end_date_10d": None,
            })
    return selection_date, rows


def main():
    ai = load_json(ROOT / "data/ai_picks.json", {})
    market_data = load_json(ROOT / "data/market_latest.json", {})
    old = load_json(BACKTEST_PATH, {})
    records = list(old.get("records", []) or [])
    selection_date, today_rows = current_records(ai, market_data)
    records = [r for r in records if normalize_date(r.get("selection_date")) != selection_date]
    records.extend(today_rows)
    snapshots = market_snapshots()
    date_index = {x["date"]: i for i, x in enumerate(snapshots)}
    records = [evaluate_record(r, snapshots, date_index) for r in records]
    records.sort(key=lambda r: (r.get("selection_date") or "", r.get("market") or "", int(r.get("rank") or 999)), reverse=True)
    dates = sorted({r.get("selection_date") for r in records if r.get("selection_date")})
    out = {
        "updated_at": now_tpe().isoformat(timespec="minutes"),
        "method": {
            "entry": "AI選股基準交易日收盤價",
            "return_5d": "推薦後第1日起，收盤跌破MA10即按當日收盤價出場；否則第5個交易日收盤結算",
            "return_10d": "推薦後第1日起，收盤跌破MA10即按當日收盤價出場；否則第10個交易日收盤結算",
            "calendar_basis": "交易日，不是日曆日",
            "baseline": "baseline_return_5d/10d 保留原固定持有策略作比較",
            "notes": [
                "推薦日即使低於MA10也保留樣本，從次一交易日才開始檢查",
                "提前出場後立即鎖定5日與10日已實現績效，不必等原期限屆滿",
                "收盤確認跌破並以同日收盤價成交屬理想化假設，實盤可能有執行落差",
                "停牌缺價不視為跌破，均線採最近10筆有效收盤價",
                "同一股票在不同選股日視為不同訊號樣本",
            ],
        },
        "start_date": dates[0] if dates else selection_date,
        "latest_selection_date": selection_date,
        "selection_days": len(dates),
        "record_count": len(records),
        "summary": build_summary(records),
        "baseline_summary": build_summary(records, "baseline_"),
        "records": records,
    }
    save_json(BACKTEST_PATH, out)
    print("ai backtest", "selection_date", selection_date, "records", len(records),
          "5d samples", out["summary"]["all"]["5d"]["samples"],
          "10d samples", out["summary"]["all"]["10d"]["samples"])


if __name__ == "__main__":
    main()
