from sources import *

from datetime import datetime


DISPLAY_DAYS = 5
NEEDED_MARKET_DAYS = DISPLAY_DAYS + 1


def market_history():
    rows = []

    for p in sorted(
        (ROOT / "data/history/market").glob("*.json")
    ):
        d = load_json(p, {})

        if d.get("date") and d.get("stocks"):
            rows.append(d)

    return rows[-NEEDED_MARKET_DAYS:]


def institutional_history():
    rows = []

    for p in sorted(
        (ROOT / "data/history/institutional").glob("*.json")
    ):
        d = load_json(p, {})

        if d.get("date"):
            rows.append(d)

    return rows[-DISPLAY_DAYS:]


def display_names_and_shares():
    master = load_json(
        ROOT / "data/master.json",
        {}
    ).get("stocks", {})

    names = {}
    shares = {}
    markets = {}

    for ticker, row in master.items():
        t = str(ticker)

        names[t] = str(
            row.get("name") or t
        ).strip()

        shares[t] = int(
            row.get("shares_issued")
            or 0
        )

        markets[t] = str(
            row.get("market")
            or ""
        ).lower()

    # sectors.json 的簡稱優先
    cfg = load_json(
        ROOT / "data/sectors.json",
        {}
    )

    for sec in cfg.get("sectors", []):
        for row in sec.get("stocks", []):
            t = str(
                row.get("ticker")
                or ""
            ).strip()

            name = str(
                row.get("name")
                or ""
            ).strip()

            if t and name:
                names[t] = name

    # 若 master 沒股數，用目前 heatmap 已算出的市值 / 價格反推
    heat = load_json(
        ROOT / "data/heatmap.json",
        {}
    )

    for sec in heat.get("sectors", []):
        for row in sec.get("stocks", []):
            t = str(
                row.get("ticker")
                or ""
            ).strip()

            price = float(
                row.get("price")
                or 0
            )

            cap = float(
                row.get("market_cap")
                or 0
            )

            if (
                t
                and shares.get(t, 0) <= 0
                and price > 0
                and cap > 0
            ):
                shares[t] = int(
                    round(cap / price)
                )

    return names, shares, markets


def parse_twse_date(raw):
    s = str(raw or "").strip()

    if not s:
        return None

    parts = s.split("/")

    if len(parts) != 3:
        return None

    try:
        y = int(parts[0])
        m = int(parts[1])
        d = int(parts[2])

        if y < 1911:
            y += 1911

        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return None


def fetch_taiex(dates):
    """
    TWSE FMTQIK 官方「發行量加權股價指數」
    依 market history 的日期對齊。
    """
    wanted = set(dates)
    values = {}

    months = sorted({
        d[:7]
        for d in dates
    })

    for ym in months:
        y, m = ym.split("-")

        try:
            data = get_json(
                f"{TWSE_WEB}/rwd/zh/afterTrading/FMTQIK",
                params={
                    "date": f"{y}{m}01",
                    "response": "json",
                },
                timeout=45,
            )
        except Exception as e:
            print(
                "TAIEX fetch failed",
                ym,
                repr(e),
            )
            continue

        fields = data.get(
            "fields",
            []
        )

        rows = data.get(
            "data",
            []
        )

        idate = _idx(
            fields,
            "日期"
        )

        iindex = _idx(
            fields,
            "發行量加權股價指數"
        )

        if (
            idate is None
            or iindex is None
        ):
            print(
                "TAIEX fields not found",
                ym,
                fields,
            )
            continue

        for row in rows:
            try:
                ds = parse_twse_date(
                    row[idate]
                )

                value = n(
                    row[iindex]
                )
            except Exception:
                continue

            if (
                ds in wanted
                and value > 0
            ):
                values[ds] = value

    return values


def pct_from_base(
    value,
    base
):
    if (
        value is None
        or base is None
        or float(base) <= 0
    ):
        return None

    return (
        float(value)
        / float(base)
        - 1
    ) * 100


def sector_market_cap_value(
    sector,
    snapshot,
    shares
):
    stocks = snapshot.get(
        "stocks",
        {}
    )

    total = 0.0
    used = 0

    members = sector.get(
        "stocks",
        []
    )

    for item in members:
        t = str(
            item.get("ticker")
            or ""
        )

        q = stocks.get(
            t,
            {}
        )

        price = float(
            q.get("price")
            or 0
        )

        sh = int(
            shares.get(t)
            or 0
        )

        if (
            price <= 0
            or sh <= 0
        ):
            continue

        total += (
            price * sh
        )

        used += 1

    coverage = (
        used / len(members)
        if members
        else 0
    )

    if (
        total <= 0
        or coverage < 0.6
    ):
        return None

    return total


def build_sector_series(
    sectors,
    market_rows,
    shares
):
    out = {}

    for sec in sectors:
        name = sec.get(
            "name"
        )

        if not name:
            continue

        values = [
            sector_market_cap_value(
                sec,
                snap,
                shares,
            )
            for snap in market_rows
        ]

        base = values[0]

        returns = [
            pct_from_base(
                value,
                base,
            )
            for value in values[1:]
        ]

        out[name] = {
            "returns": [
                (
                    round(x, 2)
                    if x is not None
                    else None
                )
                for x in returns
            ]
        }

    return out


def all_tracked_tickers(
    sectors
):
    return sorted({
        str(
            row.get("ticker")
        )
        for sec in sectors
        for row in sec.get(
            "stocks",
            []
        )
        if row.get("ticker")
    })


def build_stock_series(
    tickers,
    market_rows,
    inst_rows,
    names,
    markets,
):
    out = {}

    for t in tickers:
        prices = []

        for snap in market_rows:
            q = (
                snap.get(
                    "stocks",
                    {}
                ).get(
                    t,
                    {}
                )
            )

            price = q.get(
                "price"
            )

            prices.append(
                (
                    float(price)
                    if price is not None
                    and float(price) > 0
                    else None
                )
            )

        base = prices[0]

        stock_returns = [
            pct_from_base(
                value,
                base,
            )
            for value in prices[1:]
        ]

        institutional = []

        for snap in inst_rows:
            market = markets.get(
                t,
                ""
            )

            row = {}

            if market in (
                "twse",
                "tpex",
            ):
                row = (
                    snap.get(
                        market,
                        {}
                    ).get(
                        t,
                        {}
                    )
                )

            if not row:
                row = (
                    snap.get(
                        "twse",
                        {}
                    ).get(
                        t,
                        {}
                    )
                    or
                    snap.get(
                        "tpex",
                        {}
                    ).get(
                        t,
                        {}
                    )
                )

            total_shares = int(
                row.get("total")
                or 0
            )

            institutional.append({
                "date": (
                    snap.get("date")
                ),
                "date_label": (
                    str(
                        snap.get("date")
                        or ""
                    )[5:].replace(
                        "-",
                        "/",
                    )
                ),
                "total_lots": round(
                    total_shares
                    / 1000,
                    1,
                ),
            })

        out[t] = {
            "name": (
                names.get(
                    t,
                    t,
                )
            ),
            "market": (
                markets.get(
                    t,
                    ""
                )
            ),
            "prices": [
                (
                    round(
                        x,
                        2,
                    )
                    if x is not None
                    else None
                )
                for x in prices[1:]
            ],
            "returns": [
                (
                    round(
                        x,
                        2,
                    )
                    if x is not None
                    else None
                )
                for x in stock_returns
            ],
            "institutional": institutional,
            "institutional_5d_total_lots": round(
                sum(
                    x[
                        "total_lots"
                    ]
                    for x in institutional
                ),
                1,
            ),
        }

    return out


def main():
    market_rows = (
        market_history()
    )

    if (
        len(market_rows)
        < NEEDED_MARKET_DAYS
    ):
        raise RuntimeError(
            "stock detail needs at least "
            f"{NEEDED_MARKET_DAYS} market history days, "
            f"got {len(market_rows)}"
        )

    inst_rows = (
        institutional_history()
    )

    cfg = load_json(
        ROOT
        / "data/sectors.json",
        {}
    )

    sectors = cfg.get(
        "sectors",
        []
    )

    names, shares, markets = (
        display_names_and_shares()
    )

    dates_all = [
        x.get("date")
        for x in market_rows
    ]

    display_dates = (
        dates_all[1:]
    )

    taiex_values = (
        fetch_taiex(
            dates_all
        )
    )

    taiex_base = (
        taiex_values.get(
            dates_all[0]
        )
    )

    taiex_returns = [
        pct_from_base(
            taiex_values.get(d),
            taiex_base,
        )
        for d in display_dates
    ]

    tickers = (
        all_tracked_tickers(
            sectors
        )
    )

    out = {
        "updated_at": (
            now_tpe()
            .isoformat(
                timespec="minutes"
            )
        ),
        "as_of_date": (
            display_dates[-1]
        ),
        "note": (
            "近5個已完成交易日；走勢以5日前一交易日收盤為0%基準"
        ),
        "dates": display_dates,
        "date_labels": [
            d[5:].replace(
                "-",
                "/",
            )
            for d in display_dates
        ],
        "benchmark": {
            "name": (
                "上市加權指數"
            ),
            "source": (
                "TWSE FMTQIK"
            ),
            "returns": [
                (
                    round(
                        x,
                        2,
                    )
                    if x is not None
                    else None
                )
                for x in taiex_returns
            ],
        },
        "sectors": (
            build_sector_series(
                sectors,
                market_rows,
                shares,
            )
        ),
        "stocks": (
            build_stock_series(
                tickers,
                market_rows,
                inst_rows,
                names,
                markets,
            )
        ),
    }

    save_json(
        ROOT
        / "data/stock_detail.json",
        out,
    )

    print(
        "stock detail saved",
        out["as_of_date"],
        "stocks",
        len(out["stocks"]),
        "sectors",
        len(out["sectors"]),
        "institutional_days",
        len(inst_rows),
        "taiex",
        sum(
            x is not None
            for x in out[
                "benchmark"
            ][
                "returns"
            ]
        ),
    )


if __name__ == "__main__":
    main()
