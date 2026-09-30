from sources import *

import re


TWSE_REV = f"{TWSE}/opendata/t187ap05_L"
TPEX_REV = f"{TPEX}/mopsfin_t187ap05_O"

TECH_INDUSTRY_CODES = {
    "24", "25", "26", "27",
    "28", "29", "30", "31",
}


def parse_roc_month(s):
    raw = re.sub(r"\D", "", str(s or ""))

    if len(raw) < 5:
        return None

    try:
        roc_y = int(raw[:-2])
        month = int(raw[-2:])

        return (
            roc_y + 1911,
            month,
        )
    except Exception:
        return None


def month_key(s):
    x = parse_roc_month(s)

    if not x:
        return ""

    return f"{x[0]:04d}-{x[1]:02d}"


def month_label(s):
    x = parse_roc_month(s)

    if not x:
        return ""

    return f"{x[0]}年{x[1]}月營收"


def row_code(r):
    return str(
        pick(
            r,
            [
                "公司代號",
                "證券代號",
                "股票代號",
                "代號",
                "SecuritiesCompanyCode",
            ],
            "",
        )
    ).strip()


def row_name(r):
    return clean_name(
        pick(
            r,
            [
                "公司名稱",
                "公司簡稱",
                "證券名稱",
                "名稱",
                "CompanyName",
            ],
            "",
        )
    )


def row_month(r):
    return str(
        pick(
            r,
            [
                "資料年月",
                "年月",
                "DataMonth",
            ],
            "",
        )
    ).strip()


def revenue_thousand(r):
    return n(
        pick(
            r,
            [
                "營業收入-當月營收",
                "營業收入－當月營收",
                "當月營收",
                "RevenueCurrentMonth",
            ],
            0,
        )
    )


def mom_value(r):
    return n(
        pick(
            r,
            [
                "營業收入-上月比較增減(%)",
                "營業收入－上月比較增減(%)",
                "上月比較增減(%)",
                "MoM",
            ],
            0,
        )
    )


def yoy_value(r):
    return n(
        pick(
            r,
            [
                "營業收入-去年同月增減(%)",
                "營業收入－去年同月增減(%)",
                "去年同月增減(%)",
                "YoY",
            ],
            0,
        )
    )


def fetch_market(url, market):
    arr = get_json(
        url,
        timeout=45,
    )

    if isinstance(arr, dict):
        arr = (
            arr.get("data")
            or arr.get("records")
            or arr.get("result")
            or []
        )

    if not isinstance(arr, list):
        return []

    out = []

    for r in arr:
        ticker = row_code(r)

        if not ordinary_ticker(ticker):
            continue

        raw_month = row_month(r)

        out.append(
            {
                "ticker": ticker,
                "name": row_name(r),
                "market": market,
                "raw_month": raw_month,
                "month": month_key(raw_month),
                "month_label": month_label(raw_month),
                "revenue_100m": (
                    revenue_thousand(r)
                    / 100000
                ),
                "mom": mom_value(r),
                "yoy": yoy_value(r),
            }
        )

    return out


def load_sector_map():
    d = load_json(
        ROOT / "data/sectors.json",
        {},
    )

    ticker_names = {}
    sectors = []

    for sec in d.get("sectors", []):
        name = str(
            sec.get("name")
            or ""
        ).strip()

        stocks = []

        for x in sec.get("stocks", []):
            ticker = str(
                x.get("ticker")
                or ""
            ).strip()

            if not ordinary_ticker(ticker):
                continue

            short_name = clean_name(
                x.get("name")
                or ""
            )

            stocks.append(
                {
                    "ticker": ticker,
                    "name": short_name,
                }
            )

            if short_name:
                ticker_names[ticker] = (
                    short_name
                )

        sectors.append(
            {
                "name": name,
                "stocks": stocks,
            }
        )

    return sectors, ticker_names


def load_tech_universe():
    d = load_json(
        ROOT / "data/master.json",
        {},
    )

    stocks = (
        d.get("stocks", {})
        if isinstance(d, dict)
        else {}
    )

    tech = set()
    names = {}

    for ticker, info in stocks.items():
        ticker = str(ticker).strip()

        if not ordinary_ticker(ticker):
            continue

        industry = str(
            info.get("industry")
            or ""
        ).strip()

        if industry not in TECH_INDUSTRY_CODES:
            continue

        tech.add(ticker)

        name = clean_name(
            info.get("name")
            or ""
        )

        if name:
            names[ticker] = name

    return tech, names


def update_history(rows):
    path = (
        ROOT
        / "data/monthly_revenue_history.json"
    )

    history = load_json(
        path,
        {"stocks": {}},
    )

    stocks = history.setdefault(
        "stocks",
        {},
    )

    for x in rows:
        ticker = x["ticker"]
        month = x["month"]

        info = stocks.setdefault(
            ticker,
            {"months": {}},
        )

        info.setdefault(
            "months",
            {},
        )[month] = x["revenue_100m"]

    save_json(
        path,
        history,
    )


def update_tracker(rows):
    path = (
        ROOT
        / "data/monthly_revenue_tracker.json"
    )

    tracker = load_json(
        path,
        {},
    )

    months_seen = set(
        tracker.get(
            "months_seen",
            [],
        )
    )

    max_revenue = dict(
        tracker.get(
            "max_revenue_100m",
            {},
        )
    )

    for x in rows:
        months_seen.add(
            x["month"]
        )

        ticker = x["ticker"]
        rev = float(
            x.get("revenue_100m")
            or 0
        )

        old = float(
            max_revenue.get(
                ticker,
                0,
            )
            or 0
        )

        if rev > old:
            max_revenue[ticker] = rev

    save_json(
        path,
        {
            "updated_at": (
                now_tpe()
                .isoformat(
                    timespec="minutes"
                )
            ),
            "months_seen": sorted(
                months_seen
            ),
            "max_revenue_100m": (
                max_revenue
            ),
        },
    )


def main():
    sector_defs, sector_names = (
        load_sector_map()
    )

    tech_tickers, tech_names = (
        load_tech_universe()
    )

    sector_tickers = {
        x["ticker"]
        for sec in sector_defs
        for x in sec["stocks"]
    }

    wanted = (
        tech_tickers
        | sector_tickers
    )

    short_names = {
        **tech_names,
        **sector_names,
    }

    print(
        "monthly revenue universe",
        "tech",
        len(tech_tickers),
        "custom-sector",
        len(sector_tickers),
        "union",
        len(wanted),
    )

    all_rows = []

    for market, url in (
        ("twse", TWSE_REV),
        ("tpex", TPEX_REV),
    ):
        try:
            all_rows.extend(
                fetch_market(
                    url,
                    market,
                )
            )
        except Exception as exc:
            print(
                "monthly revenue source fail",
                market,
                repr(exc),
            )

    all_rows = [
        x
        for x in all_rows
        if (
            x["ticker"] in wanted
            and x["month"]
        )
    ]

    if not all_rows:
        raise RuntimeError(
            "no monthly revenue rows"
        )

    latest_month = max(
        x["month"]
        for x in all_rows
    )

    rows = [
        x
        for x in all_rows
        if x["month"] == latest_month
    ]

    for x in rows:
        ticker = x["ticker"]

        x["name"] = (
            short_names.get(ticker)
            or x.get("name")
            or ticker
        )

        x["is_tech"] = (
            ticker in tech_tickers
        )

        x["is_custom_sector"] = (
            ticker in sector_tickers
        )

    by_ticker = {
        x["ticker"]: x
        for x in rows
    }

    tech_rows = [
        dict(x)
        for x in rows
        if x["ticker"] in tech_tickers
    ]

    tech_rows.sort(
        key=lambda x: float(
            x.get("mom", 0)
            or 0
        ),
        reverse=True,
    )

    sectors_out = []

    if tech_rows:
        sectors_out.append(
            {
                "name": "全部科技股",
                "stocks": tech_rows,
            }
        )

    for sec in sector_defs:
        arr = []

        for item in sec["stocks"]:
            ticker = item["ticker"]

            x = by_ticker.get(
                ticker
            )

            if not x:
                continue

            arr.append(
                dict(x)
            )

        if arr:
            arr.sort(
                key=lambda x: float(
                    x.get("mom", 0)
                    or 0
                ),
                reverse=True,
            )

            sectors_out.append(
                {
                    "name": sec["name"],
                    "stocks": arr,
                }
            )

    sample = rows[0]

    mom10_count = len(
        {
            x["ticker"]
            for x in rows
            if float(
                x.get("mom")
                or 0
            ) > 10
        }
    )

    save_json(
        ROOT
        / "data/monthly_revenue.json",
        {
            "updated_at": (
                now_tpe()
                .isoformat(
                    timespec="minutes"
                )
            ),
            "month": latest_month,
            "month_label": (
                sample.get(
                    "month_label"
                )
                or latest_month
            ),
            "universe": (
                "全上市櫃科技股＋自訂族群股"
            ),
            "tech_industry_codes": sorted(
                TECH_INDUSTRY_CODES
            ),
            "tech_count": len(
                tech_rows
            ),
            "union_count": len(
                {
                    x["ticker"]
                    for x in rows
                }
            ),
            "highlight_basis": (
                "MoM > 10%"
            ),
            "mom_gt_10_count": (
                mom10_count
            ),
            "sectors": (
                sectors_out
            ),
        },
    )

    update_history(rows)
    update_tracker(rows)

    print(
        "Telegram disabled: "
        "monthly revenue only updates website"
    )

    print(
        "monthly revenue",
        latest_month,
        "rows",
        len(rows),
        "tech",
        len(tech_rows),
        "sectors",
        len(sectors_out),
        "mom > 10%",
        mom10_count,
    )


if __name__ == "__main__":
    main()
