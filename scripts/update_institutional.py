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
    """
    最新交易日：
      TPEx 直接走 sources.py 已有的官方 OpenAPI，不碰不穩定的歷史 PHP
      TWSE 維持原本官方來源

    舊交易日：
      只有 TWSE 允許補抓
      TPEx 不再逐日轟歷史 PHP，避免 RemoteDisconnected + 7~8 分鐘 timeout
    """
    if market == "tpex":
        if date != latest_market_date:
            return {}

        rows = fetch_tpex_institutional()
        return repair_dealer(rows)

    rows = fetch_twse_institutional(date)
    return repair_dealer(rows)


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

    save_json(history_path, merged)
    return merged


def maintain_history_for_market(market, market_snapshots):
    """
    安全增量模式

    1. 先沿用所有健康 cache
    2. TPEx 不再回補舊日期，避免歷史 PHP 連續斷線
    3. 最新交易日缺資料時才抓一次
       - TPEx：官方 OpenAPI 最新日
       - TWSE：原官方來源
    4. 不到 20 日不再 raise
       既有 9 日會保留，之後每個交易日自然累積到 20 日
    5. 籌碼日報只需要 5 日，因此只要 >=5 日仍可正常產出
    """
    cached = load_cached_history(
        market,
        market_snapshots
    )

    cached_dates = {
        x.get("date")
        for x in cached
        if x.get("date")
    }

    latest_snapshot = market_snapshots[-1]
    latest_date = latest_snapshot.get("date")
    latest_closes = latest_snapshot.get("stocks", {})

    print(
        "cached healthy history",
        market,
        len(cached),
        sorted(cached_dates)
    )

    # 正常每天只處理最新一個交易日
    if (
        latest_date
        and latest_closes
        and latest_date not in cached_dates
    ):
        rows = {}

        try:
            rows = fetch_fresh(
                latest_date,
                market,
                latest_date
            )

            print(
                "latest fresh",
                market,
                latest_date,
                source_health(rows)
            )

        except Exception as e:
            print(
                "latest fetch failed",
                market,
                latest_date,
                repr(e)
            )

        if healthy(rows):
            merged = save_market_day(
                latest_date,
                market,
                latest_closes,
                rows
            )

            cached.append(merged)
            cached = cached[-REQUIRED_HISTORY_DAYS:]

        else:
            print(
                "latest invalid; keep existing cache",
                market,
                latest_date,
                source_health(rows)
            )

    # TWSE 若未滿 20，可有限度補歷史
    # TPEx 明確不再碰會 RemoteDisconnected 的歷史 PHP
    if (
        market == "twse"
        and len(cached) < REQUIRED_HISTORY_DAYS
    ):
        cached_dates = {
            x.get("date")
            for x in cached
            if x.get("date")
        }

        missing_candidates = [
            m
            for m in reversed(
                market_snapshots[-LOOKBACK_MARKET_DAYS:]
            )
            if m.get("date")
            and m.get("stocks")
            and m.get("date") not in cached_dates
        ]

        for m in missing_candidates:
            if len(cached) >= REQUIRED_HISTORY_DAYS:
                break

            date = m.get("date")
            closes = m.get("stocks", {})

            try:
                rows = fetch_twse_institutional(date)
                rows = repair_dealer(rows)

                print(
                    "twse backfill",
                    date,
                    source_health(rows)
                )

            except Exception as e:
                print(
                    "twse backfill failed",
                    date,
                    repr(e)
                )
                continue

            if not healthy(rows):
                continue

            merged = save_market_day(
                date,
                market,
                closes,
                rows
            )

            cached.append(merged)
            cached.sort(
                key=lambda x: x.get("date") or ""
            )
            cached = cached[-REQUIRED_HISTORY_DAYS:]
            cached_dates.add(date)

    if len(cached) < 5:
        raise RuntimeError(
            f"{market} institutional data only "
            f"{len(cached)} healthy trading days; "
            f"minimum 5 required for ranking"
        )

    if len(cached) < REQUIRED_HISTORY_DAYS:
        print(
            "history not full yet",
            market,
            f"{len(cached)}/{REQUIRED_HISTORY_DAYS}",
            "- continue safely; future trading days will accumulate"
        )
    else:
        print(
            "history full",
            market,
            f"{len(cached)}/{REQUIRED_HISTORY_DAYS}"
        )

    return cached


def build_period(history, market, kind, days, names):
    use = history[-days:]
    sums = {}

    for h in use:
        closes = h.get("closes", {})
        rows = h.get(market, {})

        for ticker, r in rows.items():
            ticker = str(ticker)

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

    validate_output(out)

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
