from sources import *
from datetime import timedelta


MIN_TWSE_ROWS = 500
MIN_TPEX_ROWS = 300
LOOKBACK_CALENDAR_DAYS = 10

TECH_INDUSTRY_CODES = {
    "24",  # 半導體
    "25",  # 電腦及週邊設備
    "26",  # 光電
    "27",  # 通信網路
    "28",  # 電子零組件
    "29",  # 電子通路
    "30",  # 資訊服務
    "31",  # 其他電子
    "32",  # 數位雲端
}


def tech_tickers(master):
    """
    突然放量／進階篩選股票池 = 全台股科技普通股，
    不再限制為 sectors.json 19 個自訂族群。
    """
    cfg = load_json(
        ROOT / "config.json",
        {}
    )

    tech_names = {
        str(x).strip()
        for x in cfg.get(
            "tech_industries",
            []
        )
    }

    out = set()

    for t, m in master.items():
        if not ordinary_ticker(t):
            continue

        if m.get("market") not in (
            "twse",
            "tpex"
        ):
            continue

        industry = str(
            m.get("industry")
            or ""
        ).strip()

        if (
            industry in TECH_INDUSTRY_CODES
            or industry in tech_names
        ):
            out.add(str(t))

    return out


def history_files():
    return sorted(
        (
            ROOT
            / "data/history/market"
        ).glob("*.json")
    )


def fetch_latest_official_close():
    """
    逐日查官方指定日期收盤資料，
    只有同一天 TWSE + TPEx 都取得足夠筆數才接受。
    """
    today = now_tpe().date()

    for offset in range(
        LOOKBACK_CALENDAR_DAYS
    ):
        d = today - timedelta(
            days=offset
        )

        if d.weekday() >= 5:
            continue

        ds = d.isoformat()

        try:
            twse = fetch_twse_quotes_by_date(
                ds
            )
            tpex = fetch_tpex_quotes_by_date(
                ds
            )
        except Exception as e:
            print(
                "official close fetch failed",
                ds,
                repr(e)
            )
            continue

        twse = {
            str(t): q
            for t, q in (
                twse or {}
            ).items()
            if ordinary_ticker(t)
        }

        tpex = {
            str(t): q
            for t, q in (
                tpex or {}
            ).items()
            if ordinary_ticker(t)
        }

        print(
            "official close candidate",
            ds,
            "twse",
            len(twse),
            "tpex",
            len(tpex),
        )

        if len(twse) < MIN_TWSE_ROWS:
            continue

        if len(tpex) < MIN_TPEX_ROWS:
            continue

        return ds, {
            **twse,
            **tpex
        }

    raise RuntimeError(
        "no complete official close data found"
    )


def repair_twse_changes_from_previous(
    quotes,
    trade_date
):
    """
    TWSE 指定日期 MI_INDEX 偶爾會把漲跌價差解析成 0。
    若今日收盤價和前一交易日收盤不同，就用前日價格補回。
    """
    prev_snap = None

    for hp in sorted(
        history_files(),
        reverse=True
    ):
        if hp.stem >= trade_date:
            continue

        d = load_json(
            hp,
            {}
        )

        if d.get("stocks"):
            prev_snap = d
            break

    if not prev_snap:
        print(
            "no previous market snapshot for TWSE change repair"
        )
        return quotes

    prev_stocks = prev_snap.get(
        "stocks",
        {}
    )

    fixed = 0

    for ticker, q in quotes.items():
        if q.get("market") != "twse":
            continue

        price = float(
            q.get("price")
            or 0
        )

        change = float(
            q.get("change")
            or 0
        )

        prev = prev_stocks.get(
            ticker,
            {}
        )

        prev_price = float(
            prev.get("price")
            or 0
        )

        if (
            price <= 0
            or prev_price <= 0
        ):
            continue

        if (
            abs(change) < 1e-12
            and abs(
                price - prev_price
            ) > 1e-12
        ):
            repaired_change = (
                price - prev_price
            )

            q["change"] = (
                repaired_change
            )

            q["change_pct"] = (
                repaired_change
                / prev_price
                * 100
            )

            fixed += 1

    print(
        "TWSE change repaired",
        fixed,
        "using previous date",
        prev_snap.get("date"),
    )

    return quotes


def remove_bad_future_snapshots(
    as_of_date
):
    for p in history_files():
        if p.stem > as_of_date:
            print(
                "remove invalid future market snapshot",
                p.name
            )
            p.unlink(
                missing_ok=True
            )


def backfill_market(
    master,
    target=21,
    as_of_date=None
):
    existing = {
        p.stem
        for p in history_files()
    }

    have = sum(
        1
        for p in history_files()
        if load_json(
            p,
            {}
        ).get("stocks")
    )

    if have >= target:
        return

    if as_of_date:
        d = (
            datetime.strptime(
                as_of_date,
                "%Y-%m-%d"
            ).date()
            - timedelta(days=1)
        )
    else:
        d = (
            now_tpe().date()
            - timedelta(days=1)
        )

    tries = 0

    while (
        have < target
        and tries < 50
    ):
        ds = d.isoformat()
        tries += 1

        if ds not in existing:
            try:
                tw = (
                    fetch_twse_quotes_by_date(
                        ds
                    )
                )

                ot = (
                    fetch_tpex_quotes_by_date(
                        ds
                    )
                )

                q = {
                    **tw,
                    **ot
                }

                q = {
                    t: x
                    for t, x
                    in q.items()
                    if (
                        t in master
                        and ordinary_ticker(t)
                    )
                }

                if len(q) > 200:
                    save_json(
                        ROOT
                        / (
                            "data/history/market/"
                            f"{ds}.json"
                        ),
                        {
                            "date": ds,
                            "updated_at": (
                                now_tpe()
                                .isoformat(
                                    timespec="minutes"
                                )
                            ),
                            "stocks": q,
                        },
                    )

                    have += 1
                    existing.add(ds)

                    print(
                        "backfill market",
                        ds,
                        len(q),
                        have
                    )

            except Exception as e:
                print(
                    "skip market",
                    ds,
                    e
                )

        d -= timedelta(days=1)


def main():
    master_data = load_json(
        ROOT / "data/master.json",
        {}
    )

    master = master_data.get(
        "stocks",
        {}
    )

    if not master:
        master = fetch_master()

        save_json(
            ROOT / "data/master.json",
            {
                "updated_at": (
                    now_tpe()
                    .isoformat(
                        timespec="minutes"
                    )
                ),
                "stocks": master,
            },
        )

    trade_date, quotes = (
        fetch_latest_official_close()
    )

    quotes = (
        repair_twse_changes_from_previous(
            quotes,
            trade_date,
        )
    )

    filtered = {
        t: q
        for t, q in quotes.items()
        if (
            t in master
            and ordinary_ticker(t)
        )
    }

    if len(filtered) < 800:
        raise RuntimeError(
            f"official close looks incomplete: {trade_date} rows={len(filtered)}"
        )

    remove_bad_future_snapshots(
        trade_date
    )

    updated_at = (
        now_tpe()
        .isoformat(
            timespec="minutes"
        )
    )

    snap = {
        "date": trade_date,
        "updated_at": updated_at,
        "source": (
            "official date-specific "
            "TWSE + TPEx close"
        ),
        "stocks": filtered,
    }

    save_json(
        ROOT
        / (
            "data/history/market/"
            f"{trade_date}.json"
        ),
        snap,
    )

    save_json(
        ROOT
        / "data/market_latest.json",
        snap
    )

    backfill_market(
        master,
        21,
        trade_date
    )

    topn = (
        load_json(
            ROOT / "config.json",
            {}
        )
        .get(
            "top_n",
            {}
        )
        .get(
            "turnover",
            30
        )
    )

    turnover = {
        "date": trade_date,
        "updated_at": updated_at,
        "source": (
            "official date-specific "
            "TWSE + TPEx close"
        ),
        "twse": [],
        "tpex": [],
    }

    for market in (
        "twse",
        "tpex"
    ):
        arr = [
            q
            for q in filtered.values()
            if (
                q.get("market")
                == market
            )
        ]

        arr.sort(
            key=lambda x: x.get(
                "turnover",
                0
            ),
            reverse=True,
        )

        turnover[market] = (
            arr[:topn]
        )

    save_json(
        ROOT / "data/turnover.json",
        turnover
    )

    hist = []

    for p in history_files()[-30:]:
        d = load_json(
            p,
            {}
        )

        if d.get("stocks"):
            hist.append(d)

    latest = (
        hist[-1]
        if hist
        else snap
    )

    tech = tech_tickers(
        master
    )

    if len(tech) < 100:
        raise RuntimeError(
            f"tech stock universe looks incomplete: {len(tech)}"
        )

    volume_items = []
    screen_items = []

    if len(hist) >= 6:
        for t, q in (
            latest["stocks"]
            .items()
        ):
            if t not in tech:
                continue

            prior = [
                h["stocks"].get(t)
                for h in hist[:-1]
                if h["stocks"].get(t)
            ]

            last5 = prior[-5:]

            if len(last5) < 5:
                continue

            if any(
                x.get(
                    "volume",
                    0
                ) <= 0
                for x in last5
            ):
                continue

            avg5 = (
                sum(
                    x["volume"]
                    for x in last5
                )
                / 5
            )

            ratio = (
                q["volume"]
                / avg5
                if avg5
                else 0
            )

            volume_items.append(
                {
                    **q,
                    "volume_ratio_5d": ratio,
                    "low_base": (
                        avg5 < 100000
                    ),
                }
            )

            if len(prior) >= 20:
                avg20 = (
                    sum(
                        x["volume"]
                        for x
                        in prior[-20:]
                    )
                    / 20
                )

                seq = prior + [q]

                avg3 = (
                    sum(
                        x["volume"]
                        for x
                        in seq[-3:]
                    )
                    / 3
                )

                avg5i = (
                    sum(
                        x["volume"]
                        for x
                        in seq[-5:]
                    )
                    / 5
                )

                avg10 = (
                    sum(
                        x["volume"]
                        for x
                        in seq[-10:]
                    )
                    / 10
                )

                lots = (
                    q["volume"]
                    / 1000
                )

                if (
                    avg20 > 0
                    and q["volume"]
                    >= avg20 * 1.3
                    and q["volume"]
                    <= avg20 * 2.0
                    and avg3 > avg5i > avg10
                    and lots >= 1000
                ):
                    screen_items.append(
                        {
                            **q,
                            "volume_ratio_5d": ratio,
                            "volume_ratio_20d": (
                                q["volume"]
                                / avg20
                            ),
                            "avg3": round(
                                avg3 / 1000
                            ),
                            "avg5": round(
                                avg5i / 1000
                            ),
                            "avg10": round(
                                avg10 / 1000
                            ),
                        }
                    )

    volume_items.sort(
        key=lambda x: x[
            "volume_ratio_5d"
        ],
        reverse=True,
    )

    screen_items.sort(
        key=lambda x: x[
            "volume_ratio_5d"
        ],
        reverse=True,
    )

    save_json(
        ROOT / "data/volume.json",
        {
            "date": trade_date,
            "updated_at": updated_at,
            "source": (
                "official date-specific "
                "TWSE + TPEx close"
            ),
            "complete": (
                len(hist) >= 6
            ),
            "history_days": len(hist),
            "universe": (
                "全台股科技普通股"
            ),
            "universe_count": len(tech),
            "items": volume_items[:50],
        },
    )

    save_json(
        ROOT / "data/screener.json",
        {
            "date": trade_date,
            "updated_at": updated_at,
            "source": (
                "official date-specific "
                "TWSE + TPEx close"
            ),
            "complete": (
                len(hist) >= 21
            ),
            "history_days": len(hist),
            "universe": (
                "全台股科技普通股"
            ),
            "universe_count": len(tech),
            "items": screen_items,
        },
    )

    print(
        "close",
        trade_date,
        len(filtered),
        "history",
        len(hist),
        "tech universe",
        len(tech),
        "volume",
        len(volume_items),
        "screen",
        len(screen_items),
    )


if __name__ == "__main__":
    main()
