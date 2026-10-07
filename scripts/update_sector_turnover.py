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
    for sec in sectors:
        name = str(sec.get("name") or "").strip()
        if not name:
            continue
        for row in sec.get("stocks", []) or []:
            t = str(row.get("ticker") or "").strip()
            if t:
                ticker_to_sectors.setdefault(t, []).append(name)
    return sectors, ticker_to_sectors


def latest_five_history():
    files = sorted(HISTORY_DIR.glob("*.json"))
    rows = []
    for p in files[-5:]:
        d = load_json(p, {})
        if d.get("date") and isinstance(d.get("stocks"), dict):
            rows.append(d)
    return rows


def official_today_if_available(today):
    p = HISTORY_DIR / f"{today}.json"
    d = load_json(p, {})
    if d.get("date") == today and isinstance(d.get("stocks"), dict):
        return d
    return None


def fetch_intraday_turnover(tickers, master):
    channels = []
    for t in tickers:
        market = str(master.get(t, {}).get("market") or "").lower()
        if market == "tpex":
            channels.append(f"otc_{t}.tw")
        else:
            channels.append(f"tse_{t}.tw")

    out = {}
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})

    for i in range(0, len(channels), 100):
        batch = channels[i:i + 100]
        try:
            r = s.get(
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

        for q in data.get("msgArray", []) or []:
            t = str(q.get("c") or "").strip()
            if t not in tickers:
                continue

            price = num(q.get("z"))
            if price <= 0:
                bid = num(str(q.get("b") or "").split("_")[0])
                ask = num(str(q.get("a") or "").split("_")[0])
                if bid > 0 and ask > 0:
                    price = (bid + ask) / 2
                else:
                    price = bid or ask or num(q.get("y"))

            # TWSE MIS 的 v 為累積成交張數，轉為股數後估算成交金額
            lots = num(q.get("v"))
            if price > 0 and lots >= 0:
                out[t] = price * lots * 1000.0

    return out


def aggregate_sector_turnover(sectors, stock_turnover):
    result = {}
    for sec in sectors:
        name = str(sec.get("name") or "").strip()
        total = 0.0
        used = 0
        for row in sec.get("stocks", []) or []:
            t = str(row.get("ticker") or "").strip()
            v = stock_turnover.get(t)
            if v is None:
                continue
            total += float(v)
            used += 1
        result[name] = {
            "turnover": total,
            "used_stocks": used,
            "total_stocks": len(sec.get("stocks", []) or []),
        }
    return result


def main():
    sectors, ticker_to_sectors = tracked()
    tickers = set(ticker_to_sectors)
    master = load_json(MASTER_PATH, {}).get("stocks", {}) or {}
    today = now_tpe().strftime("%Y-%m-%d")

    history = latest_five_history()

    # 近5個已完成交易日：官方成交金額
    history_sector = []
    for snap in history:
        stock_turnover = {
            str(t): num(row.get("turnover"))
            for t, row in (snap.get("stocks") or {}).items()
            if str(t) in tickers and row.get("turnover") is not None
        }
        history_sector.append(
            (snap.get("date"), aggregate_sector_turnover(sectors, stock_turnover))
        )

    official_today = official_today_if_available(today)
    if official_today:
        stock_turnover_today = {
            str(t): num(row.get("turnover"))
            for t, row in (official_today.get("stocks") or {}).items()
            if str(t) in tickers and row.get("turnover") is not None
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
        cur = today_sector.get(name, {})
        values = [
            float(x.get(name, {}).get("turnover") or 0)
            for _, x in history_sector
        ]
        valid = [x for x in values if x > 0]
        avg5 = sum(valid) / len(valid) if valid else None
        current = float(cur.get("turnover") or 0)

        ratio = None
        if avg5 and avg5 > 0:
            ratio = (current / avg5 - 1) * 100

        out_items.append({
            "name": name,
            "turnover": round(current),
            "avg5_turnover": round(avg5) if avg5 is not None else None,
            "vs_avg5_pct": round(ratio, 1) if ratio is not None else None,
            "used_stocks": cur.get("used_stocks", 0),
            "total_stocks": cur.get("total_stocks", 0),
        })

    out_items.sort(key=lambda x: x.get("turnover") or 0, reverse=True)

    save_json(OUT_PATH, {
        "updated_at": now_tpe().isoformat(timespec="minutes"),
        "date": today,
        "unit": "TWD",
        "display_unit": "億元",
        "estimated": estimated,
        "source": source,
        "avg5_dates": [d for d, _ in history_sector],
        "sectors": out_items,
    })

    print(
        "sector turnover saved",
        today,
        "sectors", len(out_items),
        "source", source,
        "history_days", len(history_sector),
    )


if __name__ == "__main__":
    main()
