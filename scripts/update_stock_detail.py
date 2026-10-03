from sources import *
from sources import _idx

TREND_DAYS = 20
FLOW_DAYS = 20
NEEDED_MARKET_DAYS = TREND_DAYS + 1
PERIODS = (5, 10, 20)


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
            for subkey in (
                "total", "net", "net_buy_sell", "net_shares",
                "buy_sell", "shares", "lots", "value",
            ):
                if value.get(subkey) is not None:
                    try:
                        return float(value.get(subkey))
                    except Exception:
                        pass
    return 0.0


def _extract_inst_lots(row, kind):
    share_keys = {
        "foreign": ["foreign", "foreign_total", "foreign_net", "foreign_shares",
                    "foreign_buy_sell", "qfii", "foreign_investor"],
        "trust": ["trust", "investment_trust", "investmentTrust", "trust_total",
                  "trust_net", "trust_shares", "trust_buy_sell"],
        "dealer": ["dealer", "dealer_total", "dealer_net", "dealer_shares",
                   "dealer_buy_sell", "proprietary", "proprietary_dealer"],
    }
    lot_keys = {
        "foreign": ["foreign_lots", "foreign_net_lots"],
        "trust": ["trust_lots", "trust_net_lots", "investment_trust_lots"],
        "dealer": ["dealer_lots", "dealer_net_lots", "proprietary_lots"],
    }

    lot_value = _pick_number(row, lot_keys.get(kind, []))
    if lot_value:
        return int(round(lot_value))

    return int(round(_pick_number(row, share_keys.get(kind, [])) / 1000))


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
    names = {}
    shares = {}
    markets = {}

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
    wanted = set(dates)
    values = {}
    months = sorted({d[:7] for d in dates})

    for ym in months:
        y, m = ym.split("-")
        try:
            data = get_json(
                f"{TWSE_WEB}/rwd/zh/afterTrading/FMTQIK",
                params={"date": f"{y}{m}01", "response": "json"},
                timeout=45,
            )
        except Exception as e:
            print("TAIEX fetch failed", ym, repr(e))
            continue

        fields = data.get("fields", [])
        rows = data.get("data", [])
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


def _parse_tpex_daily_index(data, target_date):
    """
    解析櫃買中心「櫃買指數暨產業分類指數（日查詢）」。
    只取「櫃買指數 / 發行量加權股價指數」收盤值。
    """
    tables = []

    if isinstance(data, dict):
        if isinstance(data.get("tables"), list):
            tables.extend(data.get("tables") or [])

        if isinstance(data.get("data"), list):
            tables.append({
                "fields": data.get("fields") or [],
                "data": data.get("data") or [],
            })

    for tb in tables:
        fields = tb.get("fields") or []
        rows = tb.get("data") or []

        # 新版 API 常見欄位：指數名稱、收盤指數
        name_idx = None
        close_idx = None

        for i, field in enumerate(fields):
            f = str(field or "").replace(" ", "")

            if name_idx is None and (
                "指數名稱" in f
                or f in ("名稱", "種類")
            ):
                name_idx = i

            if close_idx is None and (
                "收盤指數" in f
                or "收市指數" in f
                or f in ("收盤", "收市")
            ):
                close_idx = i

        if name_idx is None or close_idx is None:
            continue

        for row in rows:
            try:
                name = str(row[name_idx] or "").strip()
            except Exception:
                continue

            if name not in (
                "櫃買指數",
                "發行量加權股價指數",
            ):
                continue

            try:
                value = n(row[close_idx])
            except Exception:
                value = 0

            if value > 0:
                return value

    return None


def fetch_tpex_index(dates):
    """
    官方 TPEx 櫃買指數歷史收盤。

    改用「櫃買指數暨產業分類指數（日查詢）」逐交易日取得，
    避免先前 monthly daily-indices endpoint 的 schema 差異。
    """
    values = {}

    for ds in dates:
        y, m, d = map(int, ds.split("-"))
        roc_date = f"{y - 1911}/{m:02d}/{d:02d}"

        candidates = [
            (
                "https://www.tpex.org.tw/www/zh-tw/indices/"
                "stock-index/industrial/inxsect",
                {
                    "date": roc_date,
                    "response": "json",
                },
            ),
            (
                "https://www.tpex.org.tw/web/stock/iNdex_info/"
                "inxh/inx_result.php",
                {
                    "l": "zh-tw",
                    "d": roc_date,
                    "o": "json",
                },
            ),
        ]

        value = None

        for url, params in candidates:
            try:
                data = get_json(
                    url,
                    params=params,
                    timeout=45,
                )

                value = _parse_tpex_daily_index(
                    data,
                    ds,
                )

                if value is not None:
                    break

            except Exception as e:
                print(
                    "TPEX index fetch failed",
                    ds,
                    url,
                    repr(e),
                )

        if value is not None:
            values[ds] = value
        else:
            print(
                "TPEX index missing",
                ds,
            )

    print(
        "TPEX index points",
        len(values),
        "/",
        len(dates),
    )

    return values


def pct_from_base(value, base):
    if value is None or base is None or float(base) <= 0:
        return None
    return ((float(value) / float(base)) - 1) * 100


def period_returns(values, days):
    if len(values) < days + 1:
        return []

    xs = values[-(days + 1):]
    base = xs[0]

    if base is None or float(base) <= 0:
        return [None for _ in range(days)]

    return [pct_from_base(v, base) for v in xs[1:]]


def clean_returns(values):
    return [round(x, 2) if x is not None else None for x in values]


def sector_market_cap_value(sector, snapshot, shares):
    stocks = snapshot.get("stocks", {})
    total = 0.0
    used = 0
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
    return {
        str(days): clean_returns(period_returns(values, days))
        for days in PERIODS
    }


def build_sector_series(sectors, market_rows, shares):
    out = {}

    for sec in sectors:
        name = sec.get("name")
        if not name:
            continue

        values = [
            sector_market_cap_value(sec, snap, shares)
            for snap in market_rows
        ]
        periods = build_period_block(values)

        out[name] = {
            "returns": periods["5"],
            "returns_by_period": periods,
        }

    return out


def all_tracked_tickers(sectors):
    return sorted({
        str(row.get("ticker"))
        for sec in sectors
        for row in sec.get("stocks", [])
        if row.get("ticker")
    })


def build_stock_series(tickers, market_rows, inst_rows, names, markets):
    out = {}

    for t in tickers:
        prices = []

        for snap in market_rows:
            q = snap.get("stocks", {}).get(t, {})
            price = q.get("price")
            prices.append(
                float(price)
                if price is not None and float(price) > 0
                else None
            )

        periods = build_period_block(prices)
        institutional = []

        for snap in inst_rows:
            market = markets.get(t, "")
            row = {}

            if market in ("twse", "tpex"):
                row = snap.get(market, {}).get(t, {})

            if not row:
                row = (
                    snap.get("twse", {}).get(t, {})
                    or snap.get("tpex", {}).get(t, {})
                )

            total_shares = int(row.get("total") or 0)

            institutional.append({
                "date": snap.get("date"),
                "date_label": str(snap.get("date") or "")[5:].replace("-", "/"),
                "foreign_lots": _extract_inst_lots(row, "foreign"),
                "trust_lots": _extract_inst_lots(row, "trust"),
                "dealer_lots": _extract_inst_lots(row, "dealer"),
                "total_lots": int(round(total_shares / 1000)),
            })

        out[t] = {
            "name": names.get(t, t),
            "market": markets.get(t, ""),
            "prices": [
                round(x, 2) if x is not None else None
                for x in prices[-TREND_DAYS:]
            ],
            "returns": periods["5"],
            "returns_by_period": periods,
            "institutional": institutional,
            "institutional_5d_total_lots": int(round(
                sum(x["total_lots"] for x in institutional[-5:])
            )),
        }

    return out


def main():
    market_rows = market_history()

    if len(market_rows) < NEEDED_MARKET_DAYS:
        raise RuntimeError(
            f"stock detail needs at least {NEEDED_MARKET_DAYS} "
            f"market history days, got {len(market_rows)}"
        )

    inst_rows = institutional_history()
    sectors = load_json(ROOT / "data/sectors.json", {}).get("sectors", [])
    names, shares, markets = display_names_and_shares()

    dates_all = [x.get("date") for x in market_rows]
    display_dates = dates_all[1:]

    date_periods = {
        str(days): display_dates[-days:]
        for days in PERIODS
    }

    label_periods = {
        key: [d[5:].replace("-", "/") for d in dates]
        for key, dates in date_periods.items()
    }

    taiex_values = fetch_taiex(dates_all)
    taiex_series = [taiex_values.get(d) for d in dates_all]
    benchmark_periods = build_period_block(taiex_series)

    tpex_values = fetch_tpex_index(dates_all)
    tpex_series = [tpex_values.get(d) for d in dates_all]
    tpex_benchmark_periods = build_period_block(tpex_series)

    tickers = all_tracked_tickers(sectors)
    ticker_sectors = {}

    for sec in sectors:
        sec_name = str(sec.get("name") or "").strip()
        if not sec_name:
            continue

        for row in sec.get("stocks", []):
            ticker = str(row.get("ticker") or "").strip()
            if not ticker:
                continue
            ticker_sectors.setdefault(ticker, []).append(sec_name)

    stock_series = build_stock_series(
        tickers, market_rows, inst_rows, names, markets
    )

    for ticker, stock in stock_series.items():
        sector_names = ticker_sectors.get(ticker, [])
        stock["sectors"] = sector_names
        stock["primary_sector"] = sector_names[0] if sector_names else ""

    out = {
        "updated_at": now_tpe().isoformat(timespec="minutes"),
        "as_of_date": display_dates[-1],
        "note": (
            "走勢與籌碼可同步切換近5／10／20個已完成交易日；"
            "各走勢期間皆以前一交易日收盤為0%基準；"
            "法人籌碼保留近20日"
        ),
        "default_period": 5,
        "available_periods": [5, 10, 20],
        "dates": date_periods["5"],
        "date_labels": label_periods["5"],
        "dates_by_period": date_periods,
        "date_labels_by_period": label_periods,

        "benchmark": {
            "name": "上市加權指數",
            "source": "TWSE FMTQIK",
            "returns": benchmark_periods["5"],
            "returns_by_period": benchmark_periods,
        },

        "tpex_benchmark": {
            "name": "櫃買指數",
            "source": "TPEx 日成交量值、指數",
            "returns": tpex_benchmark_periods["5"],
            "returns_by_period": tpex_benchmark_periods,
        },

        "sectors": build_sector_series(sectors, market_rows, shares),
        "stocks": stock_series,
    }

    save_json(ROOT / "data/stock_detail.json", out)

    print(
        "stock detail saved",
        out["as_of_date"],
        "stocks", len(out["stocks"]),
        "sectors", len(out["sectors"]),
        "institutional_days", len(inst_rows),
        "trend_days", TREND_DAYS,
        "taiex_points", len(taiex_values),
        "tpex_points", len(tpex_values),
    )


if __name__ == "__main__":
    main()
