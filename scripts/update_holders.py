from sources import *
from tech_universe import tech_tickers
import csv
import io
from datetime import datetime, timedelta


def field(r, names):
    return pick(r, names, None)


def normalize_rows(rows):
    out = []

    for r in rows:
        t = str(
            field(
                r,
                [
                    "證券代號",
                    "stockCode",
                    "SecurityCode"
                ]
            )
            or ""
        ).strip()

        if not ordinary_ticker(t):
            continue

        date = str(
            field(
                r,
                [
                    "資料日期",
                    "date",
                    "DataDate"
                ]
            )
            or ""
        ).strip()

        level = iv(
            field(
                r,
                [
                    "持股分級",
                    "level",
                    "HoldingLevel"
                ]
            )
        )

        shares = iv(
            field(
                r,
                [
                    "股數",
                    "shares",
                    "Shares"
                ]
            )
        )

        pct = n(
            field(
                r,
                [
                    "占集保庫存數比例%",
                    "佔集保庫存數比例%",
                    "占集保庫存數比例 (%)",
                    "percentage",
                    "Percentage"
                ]
            )
        )

        if not date or not level:
            continue

        out.append(
            (
                date,
                t,
                level,
                shares,
                pct
            )
        )

    return out


def aggregate(rows):
    by = {}

    for date, t, level, shares, pct in rows:
        d = by.setdefault(
            t,
            {
                "date": date,
                "total": 0,
                "400": 0,
                "1000": 0
            }
        )

        if level == 17:
            d["total"] = shares

        if level in (13, 14, 15):
            d["400"] += shares

        if level == 15:
            d["1000"] += shares

    for t, d in by.items():
        total = d["total"]

        d["400_ratio"] = (
            d["400"] / total * 100
            if total
            else 0
        )

        d["1000_ratio"] = (
            d["1000"] / total * 100
            if total
            else 0
        )

    return by


def fetch_archive_before(date):
    dt = datetime.strptime(
        date,
        "%Y%m%d"
    ).date()

    for back in range(1, 22):
        d = dt - timedelta(days=back)

        if d.weekday() != 4:
            continue

        url = (
            "https://raw.githubusercontent.com/"
            "wirelessr/tdcc-opendata-archive/"
            f"main/snapshots/{d.year}/{d.isoformat()}.csv"
        )

        try:
            r = S.get(
                url,
                timeout=30
            )

            if r.status_code != 200:
                continue

            rows = list(
                csv.DictReader(
                    io.StringIO(
                        r.text.lstrip("\ufeff")
                    )
                )
            )

            nr = normalize_rows(rows)

            if nr:
                dd = max(
                    x[0]
                    for x in nr
                )

                return {
                    "date": dd,
                    "stocks": aggregate(
                        [
                            x
                            for x in nr
                            if x[0] == dd
                        ]
                    )
                }

        except Exception as e:
            print(
                "archive fail",
                d,
                e
            )

    return None


def load_display_names():
    """
    全站顯示名稱優先使用 sectors.json 的市場簡稱。
    若不在 sectors.json，再 fallback 到 master.json。
    """
    names = {}

    master = load_json(
        ROOT / "data/master.json",
        {}
    ).get(
        "stocks",
        {}
    )

    for ticker, row in master.items():
        name = str(
            row.get("name")
            or ""
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
                row.get("ticker")
                or ""
            ).strip()

            name = str(
                row.get("name")
                or ""
            ).strip()

            if ticker and name:
                names[ticker] = name

    return names


def normalize_market_date(value):
    """
    market history 用 YYYY-MM-DD；
    TDCC 日期目前多為 YYYYMMDD。
    統一轉成 YYYY-MM-DD 方便比較。
    """
    s = str(value or "").strip()

    if len(s) == 8 and s.isdigit():
        return (
            f"{s[:4]}-"
            f"{s[4:6]}-"
            f"{s[6:8]}"
        )

    return s


def market_history_snapshots():
    """
    載入所有正式收盤 history。
    本週漲跌幅不使用 market_latest.change_pct，
    因為那只是單日漲跌幅。
    """
    out = []

    files = sorted(
        (
            ROOT
            / "data/history/market"
        ).glob("*.json")
    )

    for p in files:
        d = load_json(p, {})

        stocks = d.get(
            "stocks",
            {}
        )

        date = normalize_market_date(
            d.get("date")
            or p.stem
        )

        if date and stocks:
            out.append(
                {
                    "date": date,
                    "stocks": stocks
                }
            )

    return out


def market_snapshot_on_or_before(
    target_date,
    snapshots
):
    """
    找 target_date 當天的正式收盤。
    若 TDCC 日期剛好遇休市日，往前找最近一個交易日。
    """
    target = normalize_market_date(
        target_date
    )

    valid = [
        x
        for x in snapshots
        if x.get("date")
        and x["date"] <= target
    ]

    return (
        valid[-1]
        if valid
        else None
    )


def weekly_price_change_pct(
    ticker,
    start_snapshot,
    end_snapshot
):
    """
    本週漲跌幅 =
    本期 TDCC 對應交易日收盤 /
    上期 TDCC 對應交易日收盤 - 1

    回傳百分比，例如 3.16 代表 +3.16%
    """
    if (
        not start_snapshot
        or not end_snapshot
    ):
        return None

    old = (
        start_snapshot
        .get("stocks", {})
        .get(str(ticker), {})
        .get("price")
    )

    cur = (
        end_snapshot
        .get("stocks", {})
        .get(str(ticker), {})
        .get("price")
    )

    try:
        old = float(old)
        cur = float(cur)
    except Exception:
        return None

    if old <= 0 or cur <= 0:
        return None

    return round(
        (
            cur / old - 1
        ) * 100,
        4
    )


def main():
    rows = normalize_rows(
        fetch_tdcc_distribution()
    )

    if not rows:
        raise RuntimeError(
            "TDCC 1-5 returned no usable rows"
        )

    date = max(
        x[0]
        for x in rows
    )

    rows = [
        x
        for x in rows
        if x[0] == date
    ]

    latest = aggregate(rows)

    # 原始 TDCC 快照仍保留全市場，供 AI 科技股股票池計算大戶因子使用。
    save_json(
        ROOT
        / f"data/history/holders/{date}.json",
        {
            "date": date,
            "stocks": latest
        }
    )

    files = sorted(
        (
            ROOT
            / "data/history/holders"
        ).glob("*.json")
    )

    prev = None

    if len(files) >= 2:
        prev = load_json(
            files[-2],
            {}
        )

    if not prev:
        prev = fetch_archive_before(
            date
        )

        if prev:
            save_json(
                ROOT
                / (
                    "data/history/holders/"
                    f"{prev['date']}.json"
                ),
                prev
            )

    master = load_json(
        ROOT / "data/master.json",
        {}
    ).get(
        "stocks",
        {}
    )

    tech = tech_tickers(
        master
    )

    if len(tech) < 100:
        raise RuntimeError(
            f"tech stock universe looks incomplete: {len(tech)}"
        )

    display_names = load_display_names()

    # 正確計算「本週漲跌幅」：
    # 使用前後兩期 TDCC 日期各自對應的正式收盤價。
    market_hist = market_history_snapshots()

    price_start = (
        market_snapshot_on_or_before(
            prev.get("date"),
            market_hist
        )
        if prev
        else None
    )

    price_end = (
        market_snapshot_on_or_before(
            date,
            market_hist
        )
        if prev
        else None
    )

    out = {
        "date": date,
        "previous_date": (
            prev.get("date")
            if prev
            else None
        ),
        "price_change_start_date": (
            price_start.get("date")
            if price_start
            else None
        ),
        "price_change_end_date": (
            price_end.get("date")
            if price_end
            else None
        ),
        "complete": bool(prev),
        "universe": "全台股科技普通股",
        "universe_count": len(tech),
        "twse": {
            "400": [],
            "1000": []
        },
        "tpex": {
            "400": [],
            "1000": []
        }
    }

    if prev:
        pstocks = prev.get(
            "stocks",
            {}
        )

        for t, d in latest.items():
            if (
                t not in pstocks
                or t not in master
                or t not in tech
            ):
                continue

            mk = master[t]["market"]

            if mk not in (
                "twse",
                "tpex"
            ):
                continue

            week_change_pct = (
                weekly_price_change_pct(
                    t,
                    price_start,
                    price_end
                )
            )

            for kind in (
                "400",
                "1000"
            ):
                cur = d[
                    f"{kind}_ratio"
                ]

                old = pstocks[t].get(
                    f"{kind}_ratio",
                    0
                )

                delta = cur - old

                if delta <= 0:
                    continue

                out[mk][kind].append(
                    {
                        "ticker": t,
                        "name": (
                            display_names.get(t)
                            or master[t].get(
                                "name",
                                ""
                            )
                        ),
                        "ratio": cur,
                        "delta": delta,
                        "week_change_pct": (
                            week_change_pct
                        ),
                        "score": 0
                    }
                )

        for mk in (
            "twse",
            "tpex"
        ):
            for kind in (
                "400",
                "1000"
            ):
                arr = sorted(
                    out[mk][kind],
                    key=lambda x: x["delta"],
                    reverse=True
                )[:30]

                for i, x in enumerate(
                    arr
                ):
                    x["score"] = round(
                        100
                        * (
                            len(arr) - i
                        )
                        / max(
                            1,
                            len(arr)
                        ),
                        1
                    )

                out[mk][kind] = arr

    save_json(
        ROOT / "data/holders.json",
        out
    )

    print(
        "holders",
        date,
        "previous",
        out["previous_date"],
        "weekly-price",
        out["price_change_start_date"],
        "->",
        out["price_change_end_date"],
        "universe",
        len(tech),
        "twse400",
        len(
            out["twse"]["400"]
        ),
        "twse1000",
        len(
            out["twse"]["1000"]
        ),
        "tpex400",
        len(
            out["tpex"]["400"]
        ),
        "tpex1000",
        len(
            out["tpex"]["1000"]
        )
    )


if __name__ == "__main__":
    main()
