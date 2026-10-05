from sources import *

PERIODS = [("1d", 1), ("3d", 3), ("5d", 5)]
MARKETS = ("twse", "tpex")
KINDS = ("foreign", "trust", "dealer", "total")

REQUIRED_HISTORY_DAYS = 20
LOOKBACK_MARKET_DAYS = 40


def load_display_names():
    names = {}

    master = load_json(
        ROOT / "data/master.json",
        {}
    ).get("stocks", {})

    for ticker, row in master.items():
        name = str(row.get("name") or "").strip()
        name = (
            name.replace("股份有限公司", "")
                .replace("有限公司", "")
                .strip()
        )

        if name:
            names[str(ticker)] = name

    sectors = load_json(
        ROOT / "data/sectors.json",
        {}
    )

    for sec in sectors.get("sectors", []):
        for row in sec.get("stocks", []):
            ticker = str(row.get("ticker") or "").strip()
            name = str(row.get("name") or "").strip()

            if ticker and name:
                names[ticker] = name

    return names


def repair_dealer(rows):
    fixed = {}

    for ticker, row in (rows or {}).items():
        r = dict(row)

        foreign = int(r.get("foreign") or 0)
        trust = int(r.get("trust") or 0)
        dealer = int(r.get("dealer") or 0)
        total = int(r.get("total") or 0)

        if dealer == 0 and total != foreign + trust:
            r["dealer"] = total - foreign - trust

        fixed[str(ticker)] = r

    return fixed


def source_health(rows):
    rows = rows or {}

    stats = {
        "rows": len(rows),
        "foreign_nonzero": 0,
        "trust_nonzero": 0,
        "dealer_nonzero": 0,
        "total_nonzero": 0,
    }

    for r in rows.values():
        if int(r.get("foreign") or 0) != 0:
            stats["foreign_nonzero"] += 1

        if int(r.get("trust") or 0) != 0:
            stats["trust_nonzero"] += 1

        if int(r.get("dealer") or 0) != 0:
            stats["dealer_nonzero"] += 1

        if int(r.get("total") or 0) != 0:
            stats["total_nonzero"] += 1

    return stats


def healthy(rows):
    s = source_health(rows)

    return (
        s["rows"] > 50
        and s["foreign_nonzero"] > 0
        and s["trust_nonzero"] > 0
        and s["dealer_nonzero"] > 0
        and s["total_nonzero"] > 0
    )


def fetch_fresh(date, market, latest_market_date):
    return (fetch_tpex_institutional(date) if market == "tpex"
            else fetch_twse_institutional(date))


def load_cached_history(market, market_snapshots):
    """
    只讀 repo 已經存在而且健康的法人歷史
    不呼叫任何外部 API
    回傳舊 -> 新
    """
    valid = []

    for m in market_snapshots[-LOOKBACK_MARKET_DAYS:]:
        date = m.get("date")
        closes = m.get("stocks", {})

        if not date or not closes:
            continue

        history_path = (
            ROOT
            / f"data/history/institutional/{date}.json"
        )

        old = load_json(history_path, {})
        rows = repair_dealer(old.get(market, {}))

        if not healthy(rows):
            continue

        merged = dict(old)
        merged["date"] = date
        merged["closes"] = closes
        merged[market] = rows

        valid.append(merged)

    return valid[-REQUIRED_HISTORY_DAYS:]


def save_market_day(date, market, closes, rows):
    history_path = (
        ROOT
        / f"data/history/institutional/{date}.json"
    )

    old = load_json(history_path, {})
    merged = dict(old)

    merged["date"] = date
    merged["updated_at"] = (
        now_tpe().isoformat(timespec="minutes")
    )
    merged["closes"] = closes
    merged[market] = rows
    merged.setdefault("verified_sources", {})[market] = "dated-v2"
    merged.setdefault("source_status", {})[market] = "available"

    save_json(history_path, merged)
    return merged


def maintain_history_for_market(market, market_snapshots):
    # Exact market-calendar window: never replace missing days with older sessions
    result = []
    for snapshot in market_snapshots[-REQUIRED_HISTORY_DAYS:]:
        date = snapshot["date"]
        old = load_json(ROOT / f"data/history/institutional/{date}.json", {})
        rows = old.get(market, {})
        verified = market != "tpex" or old.get("verified_sources", {}).get(market) == "dated-v2"
        if not healthy(rows) or not verified:
            try:
                fresh = fetch_fresh(date, market, market_snapshots[-1]["date"])
                if not healthy(fresh):
                    raise ValueError("institutional market data incomplete")
                old = save_market_day(date, market, snapshot["stocks"], fresh)
                rows = fresh
                print("repaired", market, date, len(rows))
            except Exception as exc:
                print("missing", market, date, str(exc))
                rows = {}  # Never relabel an unverified historical snapshot
                old["date"] = date
                old.setdefault("source_status", {})[market] = "unavailable"
                save_json(ROOT / f"data/history/institutional/{date}.json", old)
        result.append({"date": date, "closes": snapshot["stocks"], market: rows})
    return result


def build_period(history, market, kind, days, names):
    use = history[-days:]
    sums = {}
    if len(use) != days or any(not healthy(h.get(market, {})) for h in use):
        return {"buy": [], "sell": [], "complete": False, "days_used": sum(bool(h.get(market)) for h in use), "dates_used": [h["date"] for h in use]}
    eligible = set.intersection(*(set(h.get(market, {})) for h in use))
    eligible = {t for t in eligible if all(float(h.get("closes", {}).get(t, {}).get("price") or 0)>0 for h in use)}

    for h in use:
        closes = h.get("closes", {})
        rows = h.get(market, {})

        for ticker, r in rows.items():
            ticker = str(ticker)
            if ticker not in eligible: continue

            q = closes.get(ticker, {})
            price = float(q.get("price") or 0)
            shares = int(r.get(kind) or 0)

            if price <= 0:
                continue

            x = sums.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "name": (
                        names.get(ticker)
                        or r.get("name", "")
                    ),
                    "shares": 0,
                    "amount": 0.0,
                }
            )

            x["shares"] += shares
            x["amount"] += shares * price

    arr = list(sums.values())

    for x in arr:
        x["amount_100m"] = x["amount"] / 1e8

    buy = sorted(
        [
            x for x in arr
            if x["amount"] > 0
        ],
        key=lambda x: x["amount"],
        reverse=True
    )[:20]

    sell = sorted(
        [
            x for x in arr
            if x["amount"] < 0
        ],
        key=lambda x: x["amount"]
    )[:20]

    latest = use[-1] if use else {}

    for x in buy + sell:
        q = latest.get(
            "closes",
            {}
        ).get(
            x["ticker"],
            {}
        )

        x["change_pct"] = q.get("change_pct")
        x["price"] = q.get("price")

    return {
        "buy": buy,
        "sell": sell,
        "complete": len(use) >= days,
        "days_used": len(use),
        "dates_used": [
            x.get("date")
            for x in use
        ],
    }


def validate_output(out):
    errors = []

    for period, days in PERIODS:
        for market in MARKETS:
            for kind in KINDS:
                g = (
                    out
                    .get("periods", {})
                    .get(period, {})
                    .get(market, {})
                    .get(kind, {})
                )

                if not g.get("complete"):
                    errors.append(
                        f"{period} {market} {kind}: incomplete"
                    )

                if int(g.get("days_used") or 0) != days:
                    errors.append(
                        f"{period} {market} {kind}: "
                        f"days_used={g.get('days_used')} "
                        f"expected={days}"
                    )

                if (
                    len(g.get("buy", [])) == 0
                    and len(g.get("sell", [])) == 0
                ):
                    errors.append(
                        f"{period} {market} {kind}: "
                        f"buy/sell both empty"
                    )

    if errors:
        print("VALIDATION FAILED")

        for e in errors:
            print(" -", e)

        raise RuntimeError(
            "institutional validation failed"
        )

    print("VALIDATION PASSED")


def main():
    market_files = sorted(
        (
            ROOT
            / "data/history/market"
        ).glob("*.json")
    )

    market_snapshots = []

    for p in market_files:
        d = load_json(p, {})

        if d.get("date") and d.get("stocks"):
            market_snapshots.append(d)

    if not market_snapshots:
        raise RuntimeError(
            "market history missing"
        )

    market_snapshots.sort(
        key=lambda x: x.get("date") or ""
    )

    names = load_display_names()
    histories = {}

    for market in MARKETS:
        histories[market] = (
            maintain_history_for_market(
                market,
                market_snapshots
            )
        )

        print(
            "healthy history",
            market,
            len(histories[market]),
            [
                x.get("date")
                for x in histories[market]
            ]
        )

    today = market_snapshots[-1].get("date")

    out = {
        "date": today,
        "updated_at": (
            now_tpe()
            .isoformat(timespec="minutes")
        ),
        "periods": {},
    }

    for period, days in PERIODS:
        out["periods"][period] = {}

        for market in MARKETS:
            out["periods"][period][market] = {}

            for kind in KINDS:
                out["periods"][period][market][kind] = (
                    build_period(
                        histories[market],
                        market,
                        kind,
                        days,
                        names
                    )
                )

    try:
        validate_output(out)
    except RuntimeError as exc:
        out["warning"] = str(exc)

    save_json(
        ROOT / "data/institutional.json",
        out
    )

    print(
        "institutional saved",
        today,
        "twse_history_days",
        len(histories["twse"]),
        "tpex_history_days",
        len(histories["tpex"]),
        "incremental_mode",
        True,
    )


if __name__ == "__main__":
    main()

