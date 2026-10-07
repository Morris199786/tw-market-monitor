from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")
MIS = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"

SECTORS_PATH = ROOT / "data/sectors.json"
MASTER_PATH = ROOT / "data/master.json"
HISTORY_DIR = ROOT / "data/history/market"
OUT_PATH = ROOT / "data/sector_turnover.json"

MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(13, 30)
SESSION_MINUTES = 270


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return 0.0


def now_tpe():
    return datetime.now(TZ)


def tracked():
    cfg = load_json(SECTORS_PATH, {})
    sectors = cfg.get("sectors", []) or []
    ticker_to_sectors, ticker_names = {}, {}

    for sec in sectors:
        name = str(sec.get("name") or "").strip()
        if not name:
            continue
        for row in sec.get("stocks", []) or []:
            ticker = str(row.get("ticker") or "").strip()
            stock_name = str(row.get("name") or ticker).strip()
            if ticker:
                ticker_to_sectors.setdefault(ticker, []).append(name)
                ticker_names[ticker] = stock_name

    return sectors, ticker_to_sectors, ticker_names


def latest_five_history(today):
    rows = []
    for p in reversed(sorted(HISTORY_DIR.glob("*.json"))):
        d = load_json(p, {})
        date = str(d.get("date") or "")
        if not date or date >= today:
            continue
        if isinstance(d.get("stocks"), dict):
            rows.append(d)
        if len(rows) >= 5:
            break
    rows.reverse()
    return rows


def official_today_if_available(today):
    d = load_json(HISTORY_DIR / f"{today}.json", {})
    return d if d.get("date") == today and isinstance(d.get("stocks"), dict) else None


def session_progress(now):
    """目前交易時間占完整 270 分鐘的比例。盤中用於成交進度的暫行時間校正。"""
    if now.weekday() >= 5:
        return 1.0

    current = now.timetz().replace(tzinfo=None)
    if current <= MARKET_OPEN:
        return 0.0
    if current >= MARKET_CLOSE:
        return 1.0

    start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    elapsed = (now - start).total_seconds() / 60.0
    return max(0.0, min(1.0, elapsed / SESSION_MINUTES))


def progress_metric(turnover, avg5, progress):
    """
    盤中成交進度倍率：
    (目前累積成交額 / 已完成交易時間比例) / 前5日平均全天成交額

    progress_ratio=1.0 代表照目前速度推估，全天約等於5日均
    progress_pct=(progress_ratio-1)*100
    """
    if not avg5 or avg5 <= 0 or not progress or progress <= 0:
        return None, None

    ratio = (float(turnover) / float(progress)) / float(avg5)
    return ratio, (ratio - 1.0) * 100.0


def fetch_intraday_turnover(tickers, master):
    channels = []
    for ticker in tickers:
        market = str(master.get(ticker, {}).get("market") or "").lower()
        channels.append(f"otc_{ticker}.tw" if market == "tpex" else f"tse_{ticker}.tw")

    out = {}
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for i in range(0, len(channels), 100):
        batch = channels[i:i + 100]
        try:
            r = session.get(
                MIS,
                params={"ex_ch": "|".join(batch), "json": "1", "delay": "0"},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print("MIS turnover batch failed:", repr(exc))
            continue

        for quote in data.get("msgArray", []) or []:
            ticker = str(quote.get("c") or "").strip()
            if ticker not in tickers:
                continue

            price = num(quote.get("z"))
            if price <= 0:
                bid = num(str(quote.get("b") or "").split("_")[0])
                ask = num(str(quote.get("a") or "").split("_")[0])
                if bid > 0 and ask > 0:
                    price = (bid + ask) / 2
                else:
                    price = bid or ask or num(quote.get("y"))

            # MIS v = 盤中累積成交張數
            # 目前免費來源無可靠累積成交金額/VWAP欄位，因此盤中仍採：
            # 當下價格 × 累積成交張數 × 1000
            lots = num(quote.get("v"))
            if price > 0 and lots >= 0:
                out[ticker] = price * lots * 1000.0

    return out


def aggregate_sector_turnover(sectors, stock_turnover):
    result = {}
    for sec in sectors:
        name = str(sec.get("name") or "").strip()
        total, used = 0.0, 0
        for row in sec.get("stocks", []) or []:
            ticker = str(row.get("ticker") or "").strip()
            value = stock_turnover.get(ticker)
            if value is None:
                continue
            total += float(value)
            used += 1
        result[name] = {
            "turnover": total,
            "used_stocks": used,
            "total_stocks": len(sec.get("stocks", []) or []),
        }
    return result


def main():
    sectors, ticker_to_sectors, ticker_names = tracked()
    tickers = set(ticker_to_sectors)
    master = load_json(MASTER_PATH, {}).get("stocks", {}) or {}

    now = now_tpe()
    today = now.strftime("%Y-%m-%d")
    history = latest_five_history(today)

    history_sector = []
    for snap in history:
        stock_turnover = {
            str(ticker): num(row.get("turnover"))
            for ticker, row in (snap.get("stocks") or {}).items()
            if str(ticker) in tickers and row.get("turnover") is not None
        }
        history_sector.append((snap.get("date"), aggregate_sector_turnover(sectors, stock_turnover)))

    official_today = official_today_if_available(today)

    if official_today:
        stock_turnover_today = {
            str(ticker): num(row.get("turnover"))
            for ticker, row in (official_today.get("stocks") or {}).items()
            if str(ticker) in tickers and row.get("turnover") is not None
        }
        source = "official_close"
        estimated = False
        intraday = False
        progress = 1.0
    else:
        stock_turnover_today = fetch_intraday_turnover(tickers, master)
        source = "TWSE_MIS_price_x_accumulated_volume"
        estimated = True
        intraday = True
        progress = session_progress(now)

    today_sector = aggregate_sector_turnover(sectors, stock_turnover_today)

    out_items = []
    for sec in sectors:
        name = str(sec.get("name") or "").strip()
        current_row = today_sector.get(name, {})
        values = [
            float(snapshot.get(name, {}).get("turnover") or 0)
            for _, snapshot in history_sector
        ]
        valid = [value for value in values if value > 0]
        avg5 = sum(valid) / len(valid) if valid else None
        current = float(current_row.get("turnover") or 0)

        vs_avg5_pct = (current / avg5 - 1) * 100 if avg5 and avg5 > 0 else None
        progress_ratio, progress_pct = (
            progress_metric(current, avg5, progress) if intraday else (None, None)
        )

        out_items.append({
            "name": name,
            "turnover": round(current),
            "avg5_turnover": round(avg5) if avg5 is not None else None,
            "vs_avg5_pct": round(vs_avg5_pct, 1) if vs_avg5_pct is not None else None,
            "progress_ratio": round(progress_ratio, 4) if progress_ratio is not None else None,
            "progress_pct": round(progress_pct, 1) if progress_pct is not None else None,
            "used_stocks": current_row.get("used_stocks", 0),
            "total_stocks": current_row.get("total_stocks", 0),
        })

    out_items.sort(
        key=lambda x: (
            x.get("progress_ratio") if intraday else (
                (x.get("turnover") or 0) / x["avg5_turnover"]
                if x.get("avg5_turnover") else 0
            )
        ) or 0,
        reverse=True,
    )

    stock_history_values = {ticker: [] for ticker in tickers}
    for snap in history:
        snap_stocks = snap.get("stocks") or {}
        for ticker in tickers:
            row = snap_stocks.get(ticker)
            if not isinstance(row, dict) or row.get("turnover") is None:
                continue
            value = num(row.get("turnover"))
            if value > 0:
                stock_history_values[ticker].append(value)

    out_stocks = []
    for ticker in sorted(tickers):
        turnover = stock_turnover_today.get(ticker)
        if turnover is None:
            continue

        history_values = stock_history_values.get(ticker, [])
        avg5 = sum(history_values) / len(history_values) if history_values else None
        vs_avg5_pct = (
            (float(turnover) / avg5 - 1) * 100
            if avg5 and avg5 > 0 else None
        )
        progress_ratio, progress_pct = (
            progress_metric(turnover, avg5, progress) if intraday else (None, None)
        )

        out_stocks.append({
            "ticker": ticker,
            "name": ticker_names.get(ticker, ticker),
            "turnover": round(float(turnover)),
            "avg5_turnover": round(avg5) if avg5 is not None else None,
            "vs_avg5_pct": round(vs_avg5_pct, 1) if vs_avg5_pct is not None else None,
            "progress_ratio": round(progress_ratio, 4) if progress_ratio is not None else None,
            "progress_pct": round(progress_pct, 1) if progress_pct is not None else None,
            "sectors": ticker_to_sectors.get(ticker, []),
        })

    out_stocks.sort(
        key=lambda x: (
            x.get("progress_ratio") if intraday else (
                (x.get("turnover") or 0) / x["avg5_turnover"]
                if x.get("avg5_turnover") else 0
            )
        ) or 0,
        reverse=True,
    )

    save_json(
        OUT_PATH,
        {
            "updated_at": now.isoformat(timespec="minutes"),
            "date": today,
            "unit": "TWD",
            "display_unit": "億元",
            "estimated": estimated,
            "intraday": intraday,
            "source": source,
            "session_progress": round(progress, 4),
            "session_progress_pct": round(progress * 100, 1),
            "progress_method": "linear_time_adjusted_vs_prev5_full_day_avg" if intraday else None,
            "avg5_dates": [date for date, _ in history_sector],
            "sectors": out_items,
            "stocks": out_stocks,
        },
    )

    print(
        "sector turnover saved",
        today,
        "sectors", len(out_items),
        "stocks", len(out_stocks),
        "source", source,
        "intraday", intraday,
        "session_progress", round(progress, 4),
        "history_days", len(history_sector),
    )


if __name__ == "__main__":
    main()
