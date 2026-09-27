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

        mom = float(
            x.get("mom")
            or 0
        )

        yoy = float(
            x.get("yoy")
            or 0
        )

        x["name"] = (
            short_names.get(t)
            or x.get("name")
            or t
        )

        # 月營收 MoM > 10% 才推播
        # 每檔每月只推一次，避免同一家公司重複通知
        push_id = (
            f"mom10|{latest_month}|{t}"
        )

        if (
            mom > 10
            and push_id not in sent
        ):
            # 推播標題直接帶公司與 MoM，鎖定螢幕就能先看到重點
            title = (
                f"月營收｜{x['name']} {t}｜"
                f"MoM {mom:+.2f}%"
            )

            # 使用者要求固定顯示：月營收數字、MoM、YoY
            msg = (
                f"{latest_month} 月營收\n"
                f"月營收：{rev:.2f} 億元\n"
                f"MoM：{mom:+.2f}%\n"
                f"YoY：{yoy:+.2f}%"
            )

            if send_pushover(
                title,
                msg,
            ):
                sent.add(
                    push_id
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
            "logic": (
                "monthly revenue MoM > 10%"
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
            # 資料檔先依 MoM 高到低排
            # 前端預設依族群顯示，使用者可切換 MoM 排序
            arr.sort(
                key=lambda x:
                    float(
                        x.get(
                            "mom",
                            0
                        )
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

    mom10_count = len({
        x["ticker"]
        for x in rows
        if float(
            x.get("mom")
            or 0
        ) > 10
    })

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
            "highlight_basis": (
                "MoM > 10%"
            ),
            "mom_gt_10_count": (
                mom10_count
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
        "mom > 10%",
        mom10_count,
    )


if __name__ == "__main__":
    main()
