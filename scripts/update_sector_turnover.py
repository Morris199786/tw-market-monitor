from __future__ import annotations

import json
from datetime import datetime
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


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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

    ticker_to_sectors = {}
    ticker_names = {}

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
    files = sorted(HISTORY_DIR.glob("*.json"))
    rows = []

    # 排除今天，確保5日均一定是「前5個完整交易日」
    for p in reversed(files):
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
    p = HISTORY_DIR / f"{today}.json"
    d = load_json(p, {})

    if d.get("date") == today and isinstance(d.get("stocks"), dict):
        return d

    return None


def fetch_intraday_turnover(tickers, master):
    channels = []

    for ticker in tickers:
        market = str(master.get(ticker, {}).get("market") or "").lower()

        if market == "tpex":
            channels.append(f"otc_{ticker}.tw")
        else:
            channels.append(f"tse_{ticker}.tw")

    out = {}
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for i in range(0, len(channels), 100):
        batch = channels[i:i + 100]

        try:
            r = session.get(
                MIS,
                params={
                    "ex_ch": "|".join(batch),
                    "json": "1",
                    "delay": "0",
                },
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
            # 盤中成交金額為估算值：目前價格 × 累積成交張數 × 1000
            lots = num(quote.get("v"))

            if price > 0 and lots >= 0:
                out[ticker] = price * lots * 1000.0

    return out


def aggregate_sector_turnover(sectors, stock_turnover):
    result = {}

    for sec in sectors:
        name = str(sec.get("name") or "").strip()
        total = 0.0
        used = 0

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

    # 前5個完整交易日：官方成交金額
    history_sector = []

    for snap in history:
        stock_turnover = {
            str(ticker): num(row.get("turnover"))
            for ticker, row in (snap.get("stocks") or {}).items()
            if str(ticker) in tickers and row.get("turnover") is not None
        }

        history_sector.append(
            (
                snap.get("date"),
                aggregate_sector_turnover(sectors, stock_turnover),
            )
        )

    official_today = official_today_if_available(today)

    if official_today:
        stock_turnover_today = {
            str(ticker): num(row.get("turnover"))
            for ticker, row in (official_today.get("stocks") or {}).items()
            if str(ticker) in tickers and row.get("turnover") is not None
        }

        source = "official_close"
        estimated = False
    else:
        stock_turnover_today = fetch_intraday_turnover(tickers, master)
        source = "TWSE_MIS_price_x_accumulated_volume"
        estimated = True

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

        ratio = None

        if avg5 and avg5 > 0:
            ratio = (current / avg5 - 1) * 100

        out_items.append({
            "name": name,
            "turnover": round(current),
            "avg5_turnover": round(avg5) if avg5 is not None else None,
            "vs_avg5_pct": round(ratio, 1) if ratio is not None else None,
            "used_stocks": current_row.get("used_stocks", 0),
            "total_stocks": current_row.get("total_stocks", 0),
        })

    out_items.sort(key=lambda x: x.get("turnover") or 0, reverse=True)

    # 個股近5日平均成交金額：用前5個完整交易日官方成交金額
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

    # 個股成交金額 + 5日均 + 成交增幅，供量熱力圖點開族群後排序與金標
    out_stocks = []

    for ticker in sorted(tickers):
        turnover = stock_turnover_today.get(ticker)

        if turnover is None:
            continue

        history_values = stock_history_values.get(ticker, [])
        avg5_turnover = (
            sum(history_values) / len(history_values)
            if history_values
            else None
        )

        vs_avg5_pct = None
        if avg5_turnover and avg5_turnover > 0:
            vs_avg5_pct = (float(turnover) / avg5_turnover - 1) * 100

        out_stocks.append({
            "ticker": ticker,
            "name": ticker_names.get(ticker, ticker),
            "turnover": round(float(turnover)),
            "avg5_turnover": (
                round(avg5_turnover)
                if avg5_turnover is not None
                else None
            ),
            "vs_avg5_pct": (
                round(vs_avg5_pct, 1)
                if vs_avg5_pct is not None
                else None
            ),
            "sectors": ticker_to_sectors.get(ticker, []),
        })

    out_stocks.sort(key=lambda x: x.get("turnover") or 0, reverse=True)

    save_json(
        OUT_PATH,
        {
            "updated_at": now.isoformat(timespec="minutes"),
            "date": today,
            "unit": "TWD",
            "display_unit": "億元",
            "estimated": estimated,
            "source": source,
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
        "history_days", len(history_sector),
    )


if __name__ == "__main__":
    main()
