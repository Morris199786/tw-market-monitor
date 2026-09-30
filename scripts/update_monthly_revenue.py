from sources import *

import json
import os
import re
from urllib.parse import urlencode


TWSE_REV = f"{TWSE}/opendata/t187ap05_L"
TPEX_REV = f"{TPEX}/mopsfin_t187ap05_O"

SITE_URL = "https://morris199786.github.io/tw-market-monitor/"


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

        if not ordinary_ticker(
            ticker
        ):
            continue

        raw_month = row_month(r)

        out.append(
            {
                "ticker": ticker,
                "name": row_name(r),
                "market": market,
                "raw_month": raw_month,
                "month": month_key(
                    raw_month
                ),
                "month_label": month_label(
                    raw_month
                ),
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
        ROOT
        / "data/sectors.json",
        {},
    )

    ticker_names = {}
    sectors = []

    for sec in d.get(
        "sectors",
        [],
    ):
        name = str(
            sec.get("name")
            or ""
        ).strip()

        stocks = []

        for x in sec.get(
            "stocks",
            [],
        ):
            ticker = str(
                x.get("ticker")
                or ""
            ).strip()

            if not ordinary_ticker(
                ticker
            ):
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
                ticker_names[
                    ticker
                ] = short_name

        sectors.append(
            {
                "name": name,
                "stocks": stocks,
            }
        )

    return (
        sectors,
        ticker_names,
    )


def send_telegram(
    title,
    message,
    url,
):
    token = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip()

    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID",
        "",
    ).strip()

    if not token or not chat_id:
        print(
            "telegram secrets missing; "
            "skip telegram"
        )
        return False

    try:
        r = S.post(
            (
                "https://api.telegram.org/"
                f"bot{token}/sendMessage"
            ),
            data={
                "chat_id": chat_id,
                "text": (
                    f"{title}\n"
                    f"{message}"
                ),
                "disable_web_page_preview": True,
                "reply_markup": json.dumps(
                    {
                        "inline_keyboard": [
                            [
                                {
                                    "text": (
                                        "開啟月營收"
                                    ),
                                    "url": url,
                                }
                            ]
                        ]
                    },
                    ensure_ascii=False,
                ),
            },
            timeout=30,
        )

        r.raise_for_status()

        return bool(
            r.json().get("ok")
        )

    except Exception as exc:
        print(
            "telegram failed",
            repr(exc),
        )
        return False


def row_seen_id(
    month,
    ticker,
):
    return (
        f"{month}|{ticker}"
    )


def bootstrap_seen_ids(
    sent_data,
    current_rows,
):
    """
    seen_ids 用來記錄「上一次執行時已經看過的月營收」。

    第一次升級到這版時：
    1. 優先從 monthly_revenue_history.json 建立基準
    2. 若歷史檔也沒有資料，直接把目前抓到的資料視為已看過

    這樣部署新版後不會把整批舊月營收補推一次。
    """
    if "seen_ids" in sent_data:
        return {
            str(x)
            for x in sent_data.get(
                "seen_ids",
                [],
            )
            if str(x).strip()
        }

    seen = set()

    history = load_json(
        ROOT
        / (
            "data/"
            "monthly_revenue_history.json"
        ),
        {},
    )

    for ticker, info in (
        history.get(
            "stocks",
            {},
        ).items()
    ):
        for month in (
            info.get(
                "months",
                {},
            ).keys()
        ):
            seen.add(
                row_seen_id(
                    str(month),
                    str(ticker),
                )
            )

    if not seen:
        for x in current_rows:
            seen.add(
                row_seen_id(
                    x.get(
                        "month",
                        "",
                    ),
                    x.get(
                        "ticker",
                        "",
                    ),
                )
            )

    return seen


def main():
    sector_defs, short_names = (
        load_sector_map()
    )

    wanted = {
        x["ticker"]
        for sec in sector_defs
        for x in sec["stocks"]
    }

    all_rows = []

    for market, url in (
        (
            "twse",
            TWSE_REV,
        ),
        (
            "tpex",
            TPEX_REV,
        ),
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
            x["ticker"]
            in wanted
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
        if x["month"]
        == latest_month
    ]

    by_ticker = {
        x["ticker"]: x
        for x in rows
    }

    sent_path = (
        ROOT
        / (
            "data/"
            "monthly_revenue_sent.json"
        )
    )

    sent_data = load_json(
        sent_path,
        {},
    )

    # 已經真正 Telegram 推播過的紀錄
    telegram_sent = set(
        sent_data.get(
            "telegram_ids",
            [],
        )
    )

    # 關鍵：記錄上一次執行前已經存在的月營收資料
    seen_before = (
        bootstrap_seen_ids(
            sent_data,
            rows,
        )
    )

    current_seen = {
        row_seen_id(
            latest_month,
            x["ticker"],
        )
        for x in rows
    }

    newly_published = [
        x
        for x in rows
        if row_seen_id(
            latest_month,
            x["ticker"],
        )
        not in seen_before
    ]

    print(
        "monthly revenue newly published",
        latest_month,
        len(newly_published),
    )

    # 只有「本次相較上一次真的新出現」的公司才有資格推播
    for x in newly_published:
        ticker = x[
            "ticker"
        ]

        rev = float(
            x.get(
                "revenue_100m"
            )
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
            short_names.get(
                ticker
            )
            or x.get("name")
            or ticker
        )

        # 推播門檻維持使用者設定：MoM > 10%
        if mom <= 10:
            continue

        push_id = (
            f"mom10|"
            f"{latest_month}|"
            f"{ticker}"
        )

        # 即使 seen 判斷異常，也再用 telegram_ids 做第二層防重
        if push_id in telegram_sent:
            continue

        title = (
            f"月營收｜"
            f"{x['name']} "
            f"{ticker}｜"
            f"MoM {mom:+.2f}%"
        )

        message = (
            f"{latest_month} 月營收\n"
            f"月營收："
            f"{rev:.2f} 億元\n"
            f"MoM："
            f"{mom:+.2f}%\n"
            f"YoY："
            f"{yoy:+.2f}%"
        )

        page_url = (
            SITE_URL
            + "?"
            + urlencode(
                {
                    "page": (
                        "monthlyRevenue"
                    ),
                    "ticker": ticker,
                    "month": (
                        latest_month
                    ),
                }
            )
        )

        if send_telegram(
            title,
            message,
            page_url,
        ):
            telegram_sent.add(
                push_id
            )

    # 無論 MoM 是否 >10%，只要本次已看到，就記成 seen
    # 下一次執行不會把它當成新公布再補推
    seen_after = (
        seen_before
        | current_seen
    )

    save_json(
        sent_path,
        {
            "updated_at": (
                now_tpe()
                .isoformat(
                    timespec=(
                        "minutes"
                    )
                )
            ),
            "logic": (
                "only newly published "
                "monthly revenue; "
                "Telegram when MoM > 10%"
            ),
            # 保留舊欄位相容，不再作推播判斷
            "ids": list(
                sent_data.get(
                    "ids",
                    [],
                )
            )[-500:],
            "telegram_ids": (
                list(
                    telegram_sent
                )[-500:]
            ),
            "seen_ids": list(
                seen_after
            )[-3000:],
        },
    )

    sectors_out = []

    for sec in sector_defs:
        arr = []

        for item in sec[
            "stocks"
        ]:
            ticker = item[
                "ticker"
            ]

            x = by_ticker.get(
                ticker
            )

            if not x:
                continue

            x["name"] = (
                short_names.get(
                    ticker
                )
                or x.get("name")
                or ticker
            )

            arr.append(
                x
            )

        if arr:
            arr.sort(
                key=lambda x:
                    float(
                        x.get(
                            "mom",
                            0,
                        )
                        or 0
                    ),
                reverse=True,
            )

            sectors_out.append(
                {
                    "name": (
                        sec["name"]
                    ),
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
            )
            > 10
        }
    )

    save_json(
        ROOT
        / (
            "data/"
            "monthly_revenue.json"
        ),
        {
            "updated_at": (
                now_tpe()
                .isoformat(
                    timespec=(
                        "minutes"
                    )
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
            "sectors": (
                sectors_out
            ),
        },
    )

    print(
        "monthly revenue",
        latest_month,
        "rows",
        len(rows),
        "new",
        len(
            newly_published
        ),
        "sectors",
        len(
            sectors_out
        ),
        "mom > 10%",
        mom10_count,
    )


if __name__ == "__main__":
    main()
