from sources import *

def latest_tdcc_totals():
    """
    用最新一份 TDCC 大戶歷史快照補發行股數。
    master.json 對部分上櫃公司會拿不到 shares_issued，
    但 TDCC level 17 的 total 就是該檔集保總股數，可作為市值加權 fallback。
    """
    files = sorted((ROOT / "data/history/holders").glob("*.json"), reverse=True)

    for p in files:
        d = load_json(p, {})
        stocks = d.get("stocks", {})

        if not stocks:
            continue

        totals = {}

        for ticker, row in stocks.items():
            total = int(row.get("total") or 0)

            if total > 0:
                totals[str(ticker)] = total

        if totals:
            print("heatmap share fallback:", p.name, len(totals))
            return totals

    return {}


def main():
    cfg = load_json(ROOT / "data/sectors.json", {})
    master = load_json(ROOT / "data/master.json", {}).get("stocks", {})

    if not master:
        master = fetch_master()

        save_json(
            ROOT / "data/master.json",
            {
                "updated_at": now_tpe().isoformat(timespec="minutes"),
                "stocks": master
            }
        )

    # TDCC fallback：主要解決上櫃 shares_issued = 0 導致熱力圖「缺 X 檔」
    tdcc_totals = latest_tdcc_totals()

    tickers = sorted({
        str(stock["ticker"])
        for sector in cfg.get("sectors", [])
        for stock in sector.get("stocks", [])
    })

    quotes = fetch_mis_quotes(tickers)

    sectors = []

    for sec in cfg.get("sectors", []):
        members = []
        weighted = 0.0
        capsum = 0.0
        missing = []

        for s in sec.get("stocks", []):
            t = str(s["ticker"])
            q = quotes.get(t)
            m = master.get(t, {})

            # 公司名稱永遠優先使用 sectors.json 的市場簡稱
            short_name = s.get("name") or m.get("name") or t

            shares = int(m.get("shares_issued") or 0)

            # 上櫃 master 若沒有發行股數，改用 TDCC 總股數
            if shares <= 0:
                shares = int(tdcc_totals.get(t) or 0)

            # 報價缺失
            if not q:
                missing.append(t)

                members.append({
                    "ticker": t,
                    "name": short_name,
                    "price": None,
                    "change_pct": None,
                    "market_cap": None,
                    "weight": None,
                    "shares_source": None
                })

                continue

            price = q.get("price")
            change_pct = q.get("change_pct")

            # 沒有有效股數才算真正缺漏
            if shares <= 0 or price is None or NumberLike(price) <= 0:
                missing.append(t)

                members.append({
                    "ticker": t,
                    "name": short_name,
                    "price": price,
                    "change_pct": change_pct,
                    "market_cap": None,
                    "weight": None,
                    "shares_source": None
                })

                continue

            cap = float(price) * shares

            capsum += cap
            weighted += float(change_pct or 0) * cap

            members.append({
                "ticker": t,
                "name": short_name,
                "price": price,
                "change_pct": round(float(change_pct or 0), 2),
                "market_cap": cap,
                "weight": None,
                "shares_source": (
                    "master"
                    if int(m.get("shares_issued") or 0) > 0
                    else "tdcc"
                )
            })

        sector_pct = weighted / capsum if capsum else None

        for x in members:
            if x["market_cap"] is not None and capsum:
                x["weight"] = x["market_cap"] / capsum

        sectors.append({
            "name": sec["name"],
            "change_pct": (
                round(sector_pct, 2)
                if sector_pct is not None
                else None
            ),
            "complete": len(missing) == 0,
            "missing": missing,
            "stocks": members
        })

    save_json(
        ROOT / "data/heatmap.json",
        {
            "updated_at": now_tpe().strftime("%Y/%m/%d %H:%M"),
            "method": "market_cap_weighted",
            "source": "TWSE MIS + TWSE/TPEx master + TDCC share fallback",
            "sectors": sectors
        }
    )

    print(
        "heatmap",
        len(sectors),
        "quotes",
        len(quotes),
        "missing",
        sum(len(x["missing"]) for x in sectors)
    )


def NumberLike(v):
    try:
        return float(v)
    except Exception:
        return 0.0


if __name__ == "__main__":
    main()
