from sources import *

import re
import time
from collections import Counter
from urllib.parse import urljoin


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

        if month < 1 or month > 12:
            return None

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
        month = month_key(raw_month)

        if not month:
            continue

        out.append(
            {
                "ticker": ticker,
                "name": row_name(r),
                "market": market,
                "raw_month": raw_month,
                "month": month,
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
                ticker_names[ticker] = short_name

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


def newest_row_per_ticker(rows):
    newest = {}

    for x in rows:
        ticker = x["ticker"]
        old = newest.get(ticker)

        if (
            old is None
            or x["month"] > old["month"]
            or (
                x["month"] == old["month"]
                and x.get("source") == "moneylink"
                and old.get("source") != "moneylink"
            )
        ):
            newest[ticker] = x

    return list(newest.values())


# ------------------------------------------------------------
# Money-Link 即時營收快訊（快速來源）
# ------------------------------------------------------------

MONEYLINK_BASE = "https://ww2.money-link.com.tw"
MONEYLINK_LIST = f"{MONEYLINK_BASE}/RealtimeNews/"


def expected_revenue_month():
    z = now_tpe()
    if z.month == 1:
        return f"{z.year - 1}-12"
    return f"{z.year:04d}-{z.month - 1:02d}"


def _prev_month(k):
    y, m = map(int, k.split("-"))
    if m == 1:
        return f"{y - 1}-12"
    return f"{y:04d}-{m - 1:02d}"


def _prev_year(k):
    y, m = map(int, k.split("-"))
    return f"{y - 1:04d}-{m:02d}"


def _ml_get(url, params=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "zh-TW,zh;q=0.9",
        "Referer": MONEYLINK_BASE + "/",
    }
    last = None
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            r.raise_for_status()
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as exc:
            last = exc
            if i < 2:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Money-Link GET failed: {last}")


def _ml_text(body):
    s = html.unescape(str(body or ""))
    s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", s)
    s = re.sub(r"(?i)<br\\s*/?>|</(?:p|div|li|tr|h\\d)>", "\\n", s)
    s = re.sub(r"<[^>]+>", " ", s).replace("\\u3000", " ")
    return re.sub(r"\\s+", " ", s).strip()


def _ml_links():
    seen, out = set(), []
    pattern = r"(?i)href\\s*=\\s*[\\\"']([^\\\"']*NewsContent\\.aspx\\?[^\\\"']+)[\\\"']"
    for page in range(1, 9):
        try:
            body = _ml_get(MONEYLINK_LIST, {"NType": "1002", "PGNum": str(page)})
        except Exception as exc:
            print("Money-Link list fail", page, repr(exc))
            continue
        for href in re.findall(pattern, body):
            u = urljoin(MONEYLINK_BASE, html.unescape(href))
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def _ml_ticker(text):
    for pattern in (
        r"[（(]\\s*(\\d{4})\\s*[）)]",
        r"(?:股票|公司|代號)[：:\\s]*(\\d{4})",
        r"\\b(\\d{4})\\b",
    ):
        m = re.search(pattern, text)
        if m and ordinary_ticker(m.group(1)):
            return m.group(1)
    return ""


def _ml_revenue(text):
    patterns = (
        (r"(?:單月|本月|當月|月)?營收[^0-9]{0,25}([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*億(?:元)?", 1.0),
        (r"(?:單月|本月|當月|月)?營收[^0-9]{0,25}([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*(?:千|仟)元", 1 / 100000),
        (r"(?:單月|本月|當月|月)?營收[^0-9]{0,25}([0-9][0-9,]*(?:\\.[0-9]+)?)\\s*元", 1 / 100000000),
    )
    for pattern, mul in patterns:
        m = re.search(pattern, text)
        if m:
            v = n(m.group(1), None)
            if v is not None and v > 0:
                return v * mul
    return None


def _ml_pct(text, kind):
    labels = ["月增", "月減", "MoM", "較上月", "上月比較"] if kind == "mom" else ["年增", "年減", "YoY", "較去年同期", "去年同月"]
    for label in labels:
        m = re.search(re.escape(label) + r"[^0-9+\\-－−]{0,15}([+\\-－−]?\\s*[0-9]+(?:\\.[0-9]+)?)\\s*%", text, re.I)
        if m:
            return n(m.group(1).replace(" ", "").replace("－", "-").replace("−", "-"), None)
    return None


def _history_revenue(history, ticker, month):
    try:
        return float(history["stocks"][ticker]["months"][month])
    except Exception:
        return None


def fetch_moneylink_fast_rows(wanted):
    target = expected_revenue_month()
    month_num = int(target[5:7])
    links = _ml_links()
    out = {}
    print("Money-Link links", len(links), "target", target)

    history = load_json(ROOT / "data/monthly_revenue_history.json", {"stocks": {}})

    for url in links:
        try:
            text = _ml_text(_ml_get(url))
            if "營收" not in text:
                continue
            ticker = _ml_ticker(text)
            if ticker not in wanted:
                continue
            if not re.search(rf"(?<!\\d){month_num}\\s*月(?:份)?(?:合併)?營收", text):
                continue
            revenue = _ml_revenue(text)
            if revenue is None:
                continue

            mom = _ml_pct(text, "mom")
            yoy = _ml_pct(text, "yoy")

            if mom is None:
                prev = _history_revenue(history, ticker, _prev_month(target))
                mom = (revenue / prev - 1) * 100 if prev else 0.0
            if yoy is None:
                prev_y = _history_revenue(history, ticker, _prev_year(target))
                yoy = (revenue / prev_y - 1) * 100 if prev_y else 0.0

            if ticker not in out:
                out[ticker] = {
                    "ticker": ticker,
                    "name": "",
                    "market": "",
                    "raw_month": "",
                    "month": target,
                    "month_label": f"{target[:4]}年{int(target[5:7])}月營收",
                    "revenue_100m": revenue,
                    "mom": mom,
                    "yoy": yoy,
                    "source": "moneylink",
                    "source_url": url,
                }
        except Exception as exc:
            print("Money-Link article fail", url, repr(exc))

    print("Money-Link fast rows", len(out))
    return list(out.values())


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
            market_rows = fetch_market(
                url,
                market,
            )

            market_latest = max(
                (
                    x["month"]
                    for x in market_rows
                    if x.get("month")
                ),
                default="none",
            )

            print(
                "monthly revenue source",
                market,
                "rows",
                len(market_rows),
                "latest",
                market_latest,
            )

            all_rows.extend(
                market_rows
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

    # Money-Link 快速來源：若已出現本月最新公告，先補進來。
    # 失敗時不影響 OpenData 正常更新。
    try:
        fast_rows = fetch_moneylink_fast_rows(wanted)
    except Exception as exc:
        print("Money-Link fast source fail", repr(exc))
        fast_rows = []

    for x in fast_rows:
        ticker = x["ticker"]
        x["name"] = short_names.get(ticker) or x.get("name") or ticker

    # 同一股票同月份時，Money-Link 放在後面，讓 newest_row_per_ticker
    # 的新版邏輯可取得較新的月份；不同月份則一定取月份較新的資料。
    all_rows.extend(fast_rows)

    source_latest_month = max(
        x["month"]
        for x in all_rows
    )

    source_month_counts = Counter(
        x["month"]
        for x in all_rows
    )

    print(
        "monthly revenue source months",
        dict(
            sorted(
                source_month_counts.items()
            )
        ),
    )

    # 歷史資料保留來源抓到的所有月份
    update_history(all_rows)
    update_tracker(all_rows)

    # 每檔股票各自取最新月份：
    # 已公布新月份 -> 使用新月份
    # 尚未公布     -> 保留上一月份
    rows = newest_row_per_ticker(
        all_rows
    )

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

        x["is_latest_month"] = (
            x["month"]
            == source_latest_month
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

    display_month_counts = Counter(
        x["month"]
        for x in rows
    )

    latest_rows = [
        x
        for x in rows
        if x["month"]
        == source_latest_month
    ]

    pending_rows = [
        x
        for x in rows
        if x["month"]
        != source_latest_month
    ]

    latest_tech_count = len(
        [
            x
            for x in latest_rows
            if x["ticker"]
            in tech_tickers
        ]
    )

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
            "month": source_latest_month,
            "month_label": (
                f"{source_latest_month[:4]}年"
                f"{int(source_latest_month[5:7])}月營收"
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
                rows
            ),
            "latest_month_count": len(
                latest_rows
            ),
            "latest_month_tech_count": (
                latest_tech_count
            ),
            "pending_count": len(
                pending_rows
            ),
            "month_counts": dict(
                sorted(
                    display_month_counts.items()
                )
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
        "Telegram disabled: "
        "monthly revenue only updates website"
    )

    print(
        "monthly revenue latest source month",
        source_latest_month,
        "display rows",
        len(rows),
        "latest-month rows",
        len(latest_rows),
        "pending old-month rows",
        len(pending_rows),
        "display months",
        dict(
            sorted(
                display_month_counts.items()
            )
        ),
        "tech",
        len(tech_rows),
        "latest tech",
        latest_tech_count,
        "sectors",
        len(sectors_out),
        "mom > 10%",
        mom10_count,
    )


if __name__ == "__main__":
    main()
