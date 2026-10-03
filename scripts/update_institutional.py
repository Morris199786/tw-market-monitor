from sources import *

PERIODS = [("1d", 1), ("3d", 3), ("5d", 5)]
MARKETS = ("twse", "tpex")
KINDS = ("foreign", "trust", "dealer", "total")

# 個股詳細頁需要 20 個交易日法人資料
REQUIRED_HISTORY_DAYS = 20

# 用較寬的市場歷史窗口避開休市日、單日 API 異常
LOOKBACK_MARKET_DAYS = 40


def load_display_names():
    names = {}

    master = load_json(
        ROOT / "data/master.json",
        {}
    ).get("stocks", {})

    for ticker, row in master.items():
        name = str(
            row.get("name") or ""
        ).strip()

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
            ticker = str(
                row.get("ticker") or ""
            ).strip()

            name = str(
                row.get("name") or ""
            ).strip()

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


def fetch_fresh(date, market):
    if market == "twse":
        rows = fetch_twse_institutional(date)
    else:
        rows = fetch_tpex_institutional(date)

    return repair_dealer(rows)


def maintain_history_for_market(
    market,
    market_snapshots
):
    """
    第一次：把缺少的歷史日期補到 20 個有效交易日
    之後：健康舊檔直接沿用，只抓新出現的交易日

    因此正常 Daily close 不會再每天重抓 20 日。
    """
    valid = []

    candidates = list(
        reversed(
            market_snapshots[
                -LOOKBACK_MARKET_DAYS:
            ]
        )
    )

    for m in candidates:
        date = m.get("date")
        closes = m.get("stocks", {})

        if not date or not closes:
            continue

        history_path = (
            ROOT
            / f"data/history/institutional/{date}.json"
        )

        old = load_json(
            history_path,
            {}
        )

        cached_rows = repair_dealer(
            old.get(market, {})
        )

        if healthy(cached_rows):
            # 關鍵：已有健康資料就不再打官方 API
            rows = cached_rows

            print(
                "reuse healthy cache",
                market,
                date,
                source_health(rows)
            )

        else:
            rows = {}

            try:
                rows = fetch_fresh(
                    date,
                    market
                )

                print(
                    "fresh",
                    market,
                    date,
                    source_health(rows)
                )

            except Exception as e:
                print(
                    "fresh fetch failed",
                    market,
                    date,
                    repr(e)
                )

            if not healthy(rows):
                print(
                    "skip invalid day",
                    market,
                    date,
                    "fresh=",
                    source_health(rows),
                    "cache=",
                    source_health(cached_rows)
                )
                continue

        merged = dict(old)

        merged["date"] = date
        merged["updated_at"] = (
            now_tpe()
            .isoformat(timespec="minutes")
        )

        # 同日期行情一起保留，供法人買賣超金額計算
        merged["closes"] = closes
        merged[market] = rows

        save_json(
            history_path,
            merged
        )

        valid.append(merged)

        if len(valid) >= REQUIRED_HISTORY_DAYS:
            break

    # 上面是新 -> 舊；後續統一使用舊 -> 新
    valid = list(reversed(valid))

    if len(valid) < REQUIRED_HISTORY_DAYS:
        raise RuntimeError(
            f"{market} institutional data only "
            f"{len(valid)}/{REQUIRED_HISTORY_DAYS} "
            f"healthy trading days"
        )

    return valid


def build_period(
    history,
    market,
    kind,
    days,
    names
):
    use = history[-days:]
    sums = {}

    for h in use:
        closes = h.get(
            "closes",
            {}
        )

        rows = h.get(
            market,
            {}
        )

        for ticker, r in rows.items():
            ticker = str(ticker)

            q = closes.get(
                ticker,
                {}
            )

            price = float(
                q.get("price") or 0
            )

            shares = int(
                r.get(kind) or 0
            )

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
            x["amount"] += (
                shares * price
            )

    arr = list(
        sums.values()
    )

    for x in arr:
        x["amount_100m"] = (
            x["amount"] / 1e8
        )

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

    latest = (
        use[-1]
        if use
        else {}
    )

    for x in buy + sell:
        q = latest.get(
            "closes",
            {}
        ).get(
            x["ticker"],
            {}
        )

        x["change_pct"] = (
            q.get("change_pct")
        )

        x["price"] = (
            q.get("price")
        )

    return {
        "buy": buy,
        "sell": sell,
        "complete": (
            len(use) >= days
        ),
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
        d = load_json(
            p,
            {}
        )

        if (
            d.get("date")
            and d.get("stocks")
        ):
            market_snapshots.append(d)

    if not market_snapshots:
        raise RuntimeError(
            "market history missing"
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
            [
                x.get("date")
                for x
                in histories[market]
            ]
        )

    today = (
        market_snapshots[-1]
        .get("date")
    )

    out = {
        "date": today,
        "updated_at": (
            now_tpe()
            .isoformat(timespec="minutes")
        ),
        "periods": {},
    }

    # 籌碼日報原本只需要 1 / 3 / 5 日排行；
    # 20 日歷史則保留給 stock_detail 使用。
    for period, days in PERIODS:
        out["periods"][period] = {}

        for market in MARKETS:
            out["periods"][
                period
            ][market] = {}

            for kind in KINDS:
                out["periods"][
                    period
                ][market][kind] = (
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
        ROOT
        / "data/institutional.json",
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
