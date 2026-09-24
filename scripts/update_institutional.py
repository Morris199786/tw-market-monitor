from sources import *

PERIODS = [("1d", 1), ("3d", 3), ("5d", 5)]
KINDS = ("foreign", "trust", "dealer", "total")
MARKETS = ("twse", "tpex")


def load_master_names():
    master = load_json(ROOT / "data/master.json", {}).get("stocks", {})
    sectors = load_json(ROOT / "data/sectors.json", {})

    names = {}

    # 先放 master
    for t, row in master.items():
        n = str(row.get("name") or "").strip()
        if n:
            n = (
                n.replace("股份有限公司", "")
                 .replace("有限公司", "")
                 .strip()
            )
            names[str(t)] = n

    # 自訂族群中的名稱優先，這裡是網站希望顯示的市場簡稱
    for sec in sectors.get("sectors", []):
        for row in sec.get("stocks", []):
            t = str(row.get("ticker") or "")
            n = str(row.get("name") or "").strip()
            if t and n:
                names[t] = n

    return names


def ensure_history_for_market(market, market_snapshots):
    """
    對 TWSE / TPEx 分開補資料。
    不是只看最後 5 個市場交易日，而是往前找，直到該市場累積至少 5 個有效法人交易日。
    """
    valid = []

    # 往前最多看 20 個市場交易日，避免其中幾天 API 暫時失敗就整段缺漏
    for m in reversed(market_snapshots[-20:]):
        date = m.get("date")
        closes = m.get("stocks", {})

        if not date or not closes:
            continue

        p = ROOT / f"data/history/institutional/{date}.json"
        old = load_json(p, {})

        market_rows = old.get(market, {})

        if not market_rows:
            try:
                if market == "twse":
                    market_rows = fetch_twse_institutional(date)
                else:
                    market_rows = fetch_tpex_institutional(date)

                print(
                    "backfill",
                    market,
                    date,
                    len(market_rows or {})
                )

            except Exception as e:
                print(
                    market,
                    "institutional fetch fail",
                    date,
                    e
                )
                market_rows = {}

        # 保留另一個市場舊資料，不要因為其中一邊失敗就整份覆蓋掉
        old.setdefault("date", date)
        old["updated_at"] = now_tpe().isoformat(timespec="minutes")
        old["closes"] = closes

        if market_rows:
            old[market] = market_rows

        save_json(p, old)

        if market_rows:
            valid.append(old)

        if len(valid) >= 5:
            break

    # reversed 是新到舊，輸出要改回舊到新
    return list(reversed(valid))


def build_period(history, market, kind, days, names):
    """
    history 已經是「該市場有效法人資料」，
    因此 complete 是看該市場實際有效交易日，不會把空白日算進去。
    """
    use = history[-days:]
    sums = {}

    for h in use:
        closes = h.get("closes", {})
        rows = h.get(market, {})

        for t, r in rows.items():
            t = str(t)
            q = closes.get(t, {})

            price = float(q.get("price") or 0)
            shares = int(r.get(kind) or 0)

            # 沒收盤價就無法計算金額，該檔該日不硬算
            if price <= 0:
                continue

            x = sums.setdefault(
                t,
                {
                    "ticker": t,
                    "name": names.get(t) or r.get("name", ""),
                    "shares": 0,
                    "amount": 0.0
                }
            )

            x["shares"] += shares
            x["amount"] += shares * price

    arr = list(sums.values())

    for x in arr:
        x["amount_100m"] = x["amount"] / 1e8

    buy = sorted(
        [x for x in arr if x["amount"] > 0],
        key=lambda x: x["amount"],
        reverse=True
    )[:20]

    sell = sorted(
        [x for x in arr if x["amount"] < 0],
        key=lambda x: x["amount"]
    )[:20]

    latest = use[-1] if use else {}

    for x in buy + sell:
        q = latest.get("closes", {}).get(x["ticker"], {})
        x["change_pct"] = q.get("change_pct")
        x["price"] = q.get("price")

    return {
        "buy": buy,
        "sell": sell,
        "complete": len(use) >= days,
        "days_used": len(use),
        "dates_used": [h.get("date") for h in use]
    }


def main():
    market_files = sorted(
        (ROOT / "data/history/market").glob("*.json")
    )

    market_snapshots = []

    for p in market_files:
        d = load_json(p, {})
        if d.get("date") and d.get("stocks"):
            market_snapshots.append(d)

    if not market_snapshots:
        raise RuntimeError("market history missing")

    names = load_master_names()

    histories = {}

    for market in MARKETS:
        histories[market] = ensure_history_for_market(
            market,
            market_snapshots
        )

        print(
            market,
            "valid institutional days",
            len(histories[market]),
            [x.get("date") for x in histories[market]]
        )

    today = market_snapshots[-1].get("date")

    out = {
        "date": today,
        "updated_at": now_tpe().isoformat(timespec="minutes"),
        "periods": {}
    }

    for period, days in PERIODS:
        out["periods"][period] = {}

        for market in MARKETS:
            out["periods"][period][market] = {}

            for kind in KINDS:
                out["periods"][period][market][kind] = build_period(
                    histories[market],
                    market,
                    kind,
                    days,
                    names
                )

    save_json(
        ROOT / "data/institutional.json",
        out
    )

    print(
        "institutional complete",
        "twse",
        len(histories["twse"]),
        "tpex",
        len(histories["tpex"]),
        "latest",
        today
    )


if __name__ == "__main__":
    main()
