from sources import *

PERIODS = [("1d", 1), ("3d", 3), ("5d", 5)]
MARKETS = ("twse", "tpex")
KINDS = ("foreign", "trust", "dealer", "total")

# 為了避免舊 cache 把錯誤資料一直沿用，
# 每次執行都會重新抓最近法人資料，直到各市場各自取得 5 個有效交易日。
LOOKBACK_MARKET_DAYS = 12
REQUIRED_VALID_DAYS = 5


def load_display_names():
    """
    網頁顯示名稱：
    1. sectors.json 的自訂市場簡稱優先
    2. master.json 次之
    """
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
    """
    三大法人合計 = 外資 + 投信 + 自營商
    如果來源的 dealer 欄位因欄名變動而抓成 0，
    但 total 明顯不等於 foreign + trust，
    直接用恆等式補回 dealer。
    """
    fixed = {}

    for ticker, row in (rows or {}).items():
        r = dict(row)

        foreign = int(r.get("foreign") or 0)
        trust = int(r.get("trust") or 0)
        dealer = int(r.get("dealer") or 0)
        total = int(r.get("total") or 0)

        if dealer == 0 and total != foreign + trust:
            dealer = total - foreign - trust
            r["dealer"] = dealer

        fixed[str(ticker)] = r

    return fixed


def source_health(rows):
    """
    檢查法人來源是否真的有解析到各分類。
    不只看 rows 是否存在，避免再次出現
    「有 900 檔股票，但 foreign/trust/dealer 全部是 0」。
    """
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
    """
    正常交易日不可能全市場所有法人分類都同時為 0。
    這個 gate 可直接擋掉欄位解析錯誤。
    """
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


def refresh_history_for_market(
    market,
    market_snapshots
):
    """
    強制重抓，不沿用最近五日的舊解析結果。

    若當日 API 暫時失敗：
    - 舊檔若通過健康檢查才允許 fallback
    - 舊檔若也是壞資料，直接跳過並往更早日期補
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

        rows = {}

        try:
            rows = fetch_fresh(
                date,
                market
            )

            stats = source_health(rows)

            print(
                "fresh",
                market,
                date,
                stats
            )

        except Exception as e:
            print(
                "fresh fetch failed",
                market,
                date,
                repr(e)
            )

        if not healthy(rows):
            old_rows = repair_dealer(
                old.get(market, {})
            )

            if healthy(old_rows):
                print(
                    "fallback healthy cache",
                    market,
                    date,
                    source_health(old_rows)
                )

                rows = old_rows

            else:
                print(
                    "reject invalid day",
                    market,
                    date,
                    "fresh=",
                    source_health(rows),
                    "cache=",
                    source_health(old_rows)
                )

                continue

        merged = dict(old)

        merged["date"] = date
        merged["updated_at"] = (
            now_tpe()
            .isoformat(timespec="minutes")
        )

        # 每次都更新對應的收盤行情
        merged["closes"] = closes
        merged[market] = rows

        save_json(
            history_path,
            merged
        )

        valid.append(merged)

        if len(valid) >= REQUIRED_VALID_DAYS:
            break

    # candidates 是新 -> 舊
    # build_period 需要舊 -> 新
    valid = list(reversed(valid))

    if len(valid) < REQUIRED_VALID_DAYS:
        raise RuntimeError(
            f"{market} institutional data only "
            f"{len(valid)}/{REQUIRED_VALID_DAYS} "
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

            # 沒有當日收盤價就不能算「逐日買賣超 × 當日收盤價」
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
    """
    產檔前自動回測／健檢。

    如果任何市場在任何 1/3/5 日區間的四種法人分類
    沒有買超或賣超資料，直接讓 workflow fail，
    不再把「看似成功但其實整欄空白」的 JSON commit 上去。
    """
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

                # 排行至少要有一邊有資料
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

    for period, days in PERIODS:
        for market in MARKETS:
            line = []

            for kind in KINDS:
                g = out["periods"][
                    period
                ][market][kind]

                line.append(
                    f"{kind}:"
                    f"{len(g['buy'])}/"
                    f"{len(g['sell'])}"
                )

            print(
                period,
                market,
                f"{days} days",
                " ".join(line)
            )


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
            refresh_history_for_market(
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
            .isoformat(
                timespec="minutes"
            )
        ),
        "periods": {},
    }

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

    # 先驗證，通過才寫入正式檔
    validate_output(out)

    save_json(
        ROOT
        / "data/institutional.json",
        out
    )

    print(
        "institutional saved",
        today,
        "twse_dates",
        [
            x.get("date")
            for x in histories["twse"]
        ],
        "tpex_dates",
        [
            x.get("date")
            for x in histories["tpex"]
        ]
    )


if __name__ == "__main__":
    main()
