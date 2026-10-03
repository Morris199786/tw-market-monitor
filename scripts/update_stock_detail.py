from sources import *
from sources import _idx

TREND_DAYS = 60
FLOW_DAYS = 5
NEEDED_MARKET_DAYS = TREND_DAYS + 1


def _pick_number(obj, keys):
    for key in keys:
        if key in obj and obj.get(key) is not None:
            try:
                return float(obj.get(key))
            except Exception:
                pass
    for key in keys:
        value = obj.get(key)
        if isinstance(value, dict):
            for subkey in ("total", "net", "net_buy_sell", "net_shares", "buy_sell", "shares", "lots", "value"):
                if value.get(subkey) is not None:
                    try:
                        return float(value.get(subkey))
                    except Exception:
                        pass
    return 0.0


def _extract_inst_lots(row, kind):
    share_keys = {
        "foreign": ["foreign", "foreign_total", "foreign_net", "foreign_shares", "foreign_buy_sell", "qfii", "foreign_investor"],
        "trust": ["trust", "investment_trust", "investmentTrust", "trust_total", "trust_net", "trust_shares", "trust_buy_sell"],
        "dealer": ["dealer", "dealer_total", "dealer_net", "dealer_shares", "dealer_buy_sell", "proprietary", "proprietary_dealer"],
    }
    lot_keys = {
        "foreign": ["foreign_lots", "foreign_net_lots"],
        "trust": ["trust_lots", "trust_net_lots", "investment_trust_lots"],
        "dealer": ["dealer_lots", "dealer_net_lots", "proprietary_lots"],
    }
    lot_value = _pick_number(row, lot_keys.get(kind, []))
    if lot_value:
        return round(lot_value, 1)
    return round(_pick_number(row, share_keys.get(kind, [])) / 1000, 1)


def market_history():
    rows = []
    for p in sorted((ROOT / "data/history/market").glob("*.json")):
        d = load_json(p, {})
        if d.get("date") and d.get("stocks"):
            rows.append(d)
    return rows[-NEEDED_MARKET_DAYS:]


def institutional_history():
    rows = []
    for p in sorted((ROOT / "data/history/institutional").glob("*.json")):
        d = load_json(p, {})
        if d.get("date"):
            rows.append(d)
    return rows[-FLOW_DAYS:]


def display_names_and_shares():
    master = load_json(ROOT / "data/master.json", {}).get("stocks", {})
    names, shares, markets = {}, {}, {}
    for ticker, row in master.items():
        t = str(ticker)
        names[t] = str(row.get("name") or t).strip()
        shares[t] = int(row.get("shares_issued") or 0)
        markets[t] = str(row.get("market") or "").lower()

    cfg = load_json(ROOT / "data/sectors.json", {})
    for sec in cfg.get("sectors", []):
        for row in sec.get("stocks", []):
            t = str(row.get("ticker") or "").strip()
            name = str(row.get("name") or "").strip()
            if t and name:
                names[t] = name

    heat = load_json(ROOT / "data/heatmap.json", {})
    for sec in heat.get("sectors", []):
        for row in sec.get("stocks", []):
            t = str(row.get("ticker") or "").strip()
            price = float(row.get("price") or 0)
            cap = float(row.get("market_cap") or 0)
            if t and shares.get(t, 0) <= 0 and price > 0 and cap > 0:
                shares[t] = int(round(cap / price))
    return names, shares, markets


def parse_twse_date(raw):
    s = str(raw or "").strip()
    if not s:
        return None
    parts = s.split("/")
    if len(parts) != 3:
        return None
    try:
        y, m, d = map(int, parts)
        if y < 1911:
            y += 1911
        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return None


def fetch_taiex(dates):
    wanted, values = set(dates), {}
    months = sorted({d[:7] for d in dates})
    for ym in months:
        y, m = ym.split("-")
        try:
            data = get_json(f"{TWSE_WEB}/rwd/zh/afterTrading/FMTQIK", params={"date": f"{y}{m}01", "response": "json"}, timeout=45)
        except Exception as e:
            print("TAIEX fetch failed", ym, repr(e))
            continue
        fields, rows = data.get("fields", []), data.get("data", [])
        idate = _idx(fields, "日期")
        iindex = _idx(fields, "發行量加權股價指數")
        if idate is None or iindex is None:
            print("TAIEX fields not found", ym, fields)
            continue
        for row in rows:
            try:
                ds = parse_twse_date(row[idate])
                value = n(row[iindex])
            except Exception:
                continue
            if ds in wanted and value > 0:
                values[ds] = value
    return values


def pct_from_base(value, base):
    if value is None or base is None or float(base) <= 0:
        return None
    return (float(value) / float(base) - 1) * 100


def period_returns(values, days):
    if len(values) < days + 1:
        return []
    xs = values[-(days + 1):]
    base = xs[0]
    return [pct_from_base(v, base) for v in xs[1:]]


def clean_returns(values):
    return [round(x, 2) if x is not None else None for x in values]


def sector_market_cap_value(sector, snapshot, shares):
    stocks = snapshot.get("stocks", {})
    total, used = 0.0, 0
    members = sector.get("stocks", [])
    for item in members:
        t = str(item.get("ticker") or "")
        q = stocks.get(t, {})
        price = float(q.get("price") or 0)
        sh = int(shares.get(t) or 0)
        if price <= 0 or sh <= 0:
            continue
        total += price * sh
        used += 1
    coverage = used / len(members) if members else 0
    if total <= 0 or coverage < 0.6:
        return None
    return total


def build_period_block(values):
    return {str(days): clean_returns(period_returns(values, days)) for days in (5, 20, 60)}


def build_sector_series(sectors, market_rows, shares):
    out = {}
    for sec in sectors:
        name = sec.get("name")
        if not name:
            continue
        values = [sector_market_cap_value(sec, snap, shares) for snap in market_rows]
        periods = build_period_block(values)
        out[name] = {"returns": periods["60"], "returns_by_period": periods}
    return out


def all_tracked_tickers(sectors):
    return sorted({str(row.get("ticker")) for sec in sectors for row in sec.get("stocks", []) if row.get("ticker")})


def build_stock_series(tickers, market_rows, inst_rows, names, markets):
    out = {}
    for t in tickers:
        prices = []
        for snap in market_rows:
            q = snap.get("stocks", {}).get(t, {})
            price = q.get("price")
            prices.append(float(price) if price is not None and float(price) > 0 else None)

        periods = build_period_block(prices)
        institutional = []
        for snap in inst_rows:
            market = markets.get(t, "")
            row = {}
            if market in ("twse", "tpex"):
                row = snap.get(market, {}).get(t, {})
            if not row:
                row = snap.get("twse", {}).get(t, {}) or snap.get("tpex", {}).get(t, {})
            total_shares = int(row.get("total") or 0)
            institutional.append({
                "date": snap.get("date"),
                "date_label": str(snap.get("date") or "")[5:].replace("-", "/"),
                "foreign_lots": _extract_inst_lots(row, "foreign"),
                "trust_lots": _extract_inst_lots(row, "trust"),
                "dealer_lots": _extract_inst_lots(row, "dealer"),
                "total_lots": round(total_shares / 1000, 1),
            })

        out[t] = {
            "name": names.get(t, t),
            "market": markets.get(t, ""),
            "prices": [round(x, 2) if x is not None else None for x in prices[-TREND_DAYS:]],
            "returns": periods["60"],
            "returns_by_period": periods,
            "institutional": institutional,
            "institutional_5d_total_lots": round(sum(x["total_lots"] for x in institutional), 1),
        }
    return out


def main():
    market_rows = market_history()
    if len(market_rows) < NEEDED_MARKET_DAYS:
        raise RuntimeError(f"stock detail needs at least {NEEDED_MARKET_DAYS} market history days, got {len(market_rows)}")

    inst_rows = institutional_history()
    sectors = load_json(ROOT / "data/sectors.json", {}).get("sectors", [])
    names, shares, markets = display_names_and_shares()
    dates_all = [x.get("date") for x in market_rows]
    display_dates = dates_all[1:]

    date_periods = {
        str(days): display_dates[-days:]
        for days in (5, 20, 60)
    }
    label_periods = {
        key: [d[5:].replace("-", "/") for d in dates]
        for key, dates in date_periods.items()
    }

    taiex_values = fetch_taiex(dates_all)
    taiex_series = [taiex_values.get(d) for d in dates_all]
    benchmark_periods = build_period_block(taiex_series)

    tickers = all_tracked_tickers(sectors)
    out = {
        "updated_at": now_tpe().isoformat(timespec="minutes"),
        "as_of_date": display_dates[-1],
        "note": "走勢可切換近5／20／60個已完成交易日；各期間皆以前一交易日收盤為0%基準；籌碼固定近5日",
        "default_period": 20,
        "available_periods": [5, 20, 60],
        "dates": display_dates,
        "date_labels": label_periods["60"],
        "dates_by_period": date_periods,
        "date_labels_by_period": label_periods,
        "benchmark": {
            "name": "上市加權指數",
            "source": "TWSE FMTQIK",
            "returns": benchmark_periods["60"],
            "returns_by_period": benchmark_periods,
        },
        "sectors": build_sector_series(sectors, market_rows, shares),
        "stocks": build_stock_series(tickers, market_rows, inst_rows, names, markets),
    }

    save_json(ROOT / "data/stock_detail.json", out)
    print("stock detail saved", out["as_of_date"], "stocks", len(out["stocks"]), "sectors", len(out["sectors"]), "institutional_days", len(inst_rows), "trend_days", TREND_DAYS)


if __name__ == "__main__":
    main()
