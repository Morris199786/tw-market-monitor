from sources import *
import os
import re


TWSE_REV = f"{TWSE}/opendata/t187ap05_L"
TPEX_REV = f"{TPEX}/mopsfin_t187ap05_O"


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
        t = row_code(r)

        if not ordinary_ticker(t):
            continue

        m = row_month(r)

        out.append(
            {
                "ticker": t,
                "name": row_name(r),
                "market": market,
                "raw_month": m,
                "month": month_key(m),
                "month_label": month_label(m),
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
        {}
    )

    ticker_names = {}
    sectors = []

    for sec in d.get(
        "sectors",
        []
    ):
        name = str(
            sec.get("name")
            or ""
        ).strip()

        stocks = []

        for x in sec.get(
            "stocks",
            []
        ):
            t = str(
                x.get("ticker")
                or ""
            ).strip()

            if not ordinary_ticker(t):
                continue

            n2 = clean_name(
                x.get("name")
                or ""
            )

            stocks.append(
                {
                    "ticker": t,
                    "name": n2,
                }
            )

            if n2:
                ticker_names[t] = n2

        sectors.append(
            {
                "name": name,
                "stocks": stocks,
            }
        )

    return sectors, ticker_names


def send_pushover(title, message):
    token = os.getenv(
        "PUSHOVER_APP_TOKEN",
        ""
    ).strip()

    user = os.getenv(
        "PUSHOVER_USER_KEY",
        ""
    ).strip()

    if not token or not user:
        print(
            "pushover secrets missing; "
            "skip push"
        )
        return False

    try:
        r = S.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": token,
                "user": user,
                "title": title,
                "message": message,
                "priority": 0,
            },
            timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(
            "pushover failed",
            repr(e)
        )
        return False


def main():
    sector_defs, short_names = (
        load_sector_map()
    )

    wanted = {
        x["ticker"]
        for sec in sector_defs
        for x in sec["stocks"]
    }

    rows = []

    for market, url in (
        ("twse", TWSE_REV),
        ("tpex", TPEX_REV),
    ):
        try:
            rows.extend(
                fetch_market(
                    url,
                    market,
                )
            )
        except Exception as e:
            print(
                "monthly revenue source fail",
                market,
                repr(e),
            )

    rows = [
        x
        for x in rows
        if x["ticker"] in wanted
        and x["month"]
    ]

    if not rows:
        raise RuntimeError(
            "no monthly revenue rows"
        )

    latest_month = max(
        x["month"]
        for x in rows
    )

    rows = [
        x
        for x in rows
        if x["month"]
        == latest_month
    ]

    by_ticker = {
        x["ticker"]: x
        for x in rows
    }

    tracker_path = (
        ROOT
        / "data/monthly_revenue_tracker.json"
    )

    tracker = load_json(
        tracker_path,
        {}
    )

    max_map = tracker.get(
        "max_revenue_100m",
        {}
    )

    months_seen = tracker.get(
        "months_seen",
        []
    )

    sent_path = (
        ROOT
        / "data/monthly_revenue_sent.json"
    )

    sent_data = load_json(
        sent_path,
        {}
    )

    sent = set(
        sent_data.get(
            "ids",
            []
        )
    )

    for x in rows:
        t = x["ticker"]
        rev = float(
            x["revenue_100m"]
            or 0
        )

        previous_max = max_map.get(
            t
        )

        # 第一次建立基準不推播。
        # 後續月份只有真正突破本站已留存的歷史最高值才推播。
        checked = (
            previous_max is not None
        )

        is_high = (
            checked
            and rev > float(
                previous_max
            )
        )

        x["record_high"] = (
            bool(is_high)
        )

        x["record_high_checked"] = (
            bool(checked)
        )

        x["name"] = (
            short_names.get(t)
            or x.get("name")
            or t
        )

        if (
            previous_max is None
            or rev > float(
                previous_max
            )
        ):
            max_map[t] = rev

        push_id = (
            f"{latest_month}|{t}"
        )

        if (
            is_high
            and push_id not in sent
        ):
            msg = (
                f"{x['name']} {t}\n"
                f"{latest_month} 營收 "
                f"{rev:.2f} 億\n"
                f"MoM {x['mom']:+.2f}%｜"
                f"YoY {x['yoy']:+.2f}%"
            )

            if send_pushover(
                "月營收創新高",
                msg,
            ):
                sent.add(
                    push_id
                )

    if latest_month not in months_seen:
        months_seen.append(
            latest_month
        )

    months_seen = months_seen[-24:]

    save_json(
        tracker_path,
        {
            "updated_at": (
                now_tpe()
                .isoformat(
                    timespec="minutes"
                )
            ),
            "months_seen": (
                months_seen
            ),
            "max_revenue_100m": (
                max_map
            ),
        },
    )

    save_json(
        sent_path,
        {
            "updated_at": (
                now_tpe()
                .isoformat(
                    timespec="minutes"
                )
            ),
            "ids": list(
                sent
            )[-500:],
        },
    )

    sectors_out = []

    for sec in sector_defs:
        arr = []

        for item in sec["stocks"]:
            t = item["ticker"]
            x = by_ticker.get(
                t
            )

            if not x:
                continue

            arr.append(
                x
            )

        if arr:
            arr.sort(
                key=lambda x: (
                    x.get(
                        "record_high",
                        False
                    ),
                    x.get(
                        "yoy",
                        0
                    ),
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
            "month": (
                latest_month
            ),
            "month_label": (
                sample.get(
                    "month_label"
                )
                or latest_month
            ),
            "universe": (
                "19個自訂科技族群"
            ),
            "record_high_basis": (
                "本站開始留存後的歷史最高值"
            ),
            "sectors": sectors_out,
        },
    )

    print(
        "monthly revenue",
        latest_month,
        "rows",
        len(rows),
        "sectors",
        len(sectors_out),
    )


if __name__ == "__main__":
    main()
