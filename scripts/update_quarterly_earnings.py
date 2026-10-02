from sources import *
import os, re, html
from datetime import datetime, timedelta
from pathlib import Path

VERSION = "2026-10-02-v3-event-only"
DATA = ROOT / "data"
OUT = DATA / "quarterly_earnings.json"
SENT = DATA / "quarterly_earnings_sent.json"
HISTORY = DATA / "quarterly_earnings_history.json"

TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"
TWSE_IS = f"{TWSE}/opendata/t187ap06_L_ci"
TPEX_IS = f"{TPEX}/mopsfin_t187ap06_O_ci"

def clean(v):
    return re.sub(r"\s+", " ", html.unescape(str(v or ""))).strip()

def num(v):
    if v is None:
        return None
    s = clean(v).replace(",", "").replace("−", "-").replace("－", "-")
    if s in ("", "-", "--", "N/A", "nan", "None"):
        return None
    try:
        return float(s)
    except Exception:
        return None

def roc_date(v):
    s = clean(v)
    m = re.search(r"(?:(20\d{2})|(\d{2,3}))[/-]?(\d{2})[/-]?(\d{2})", s)
    if not m:
        return ""
    y = int(m.group(1) or m.group(2))
    if y < 1911:
        y += 1911
    return f"{y:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"

def period_from_text(s, fallback_date=""):
    s = clean(s)
    patterns = [
        r"(?:(20\d{2})|(\d{2,3}))\s*年?\s*第?\s*([1-4一二三四])\s*季",
        r"(?:(20\d{2})|(\d{2,3}))\s*Q\s*([1-4])",
    ]
    for pat in patterns:
        m = re.search(pat, s, re.I)
        if m:
            y = int(m.group(1) or m.group(2))
            if y < 1911:
                y += 1911
            qtxt = m.group(3)
            q = {"一": 1, "二": 2, "三": 3, "四": 4}.get(
                qtxt,
                int(qtxt) if qtxt.isdigit() else 0,
            )
            return f"{y}-Q{q}"

    if fallback_date:
        y, mn, _ = map(int, fallback_date.split("-"))
        if mn in (4, 5):
            return f"{y}-Q1"
        if mn in (7, 8):
            return f"{y}-Q2"
        if mn in (10, 11):
            return f"{y}-Q3"
        if mn in (2, 3):
            return f"{y-1}-Q4"

    return ""

def previous(p):
    y = int(p[:4])
    q = int(p[-1])
    return f"{y-1}-Q4" if q == 1 else f"{y}-Q{q-1}"

def fetch_universe():
    out = {}
    try:
        m = fetch_master()
        if isinstance(m, dict):
            for t, x in m.items():
                if re.fullmatch(r"\d{4}", str(t)):
                    out[str(t)] = clean(
                        x.get("name") if isinstance(x, dict) else x
                    )
        elif isinstance(m, list):
            for x in m:
                t = str(x.get("ticker") or x.get("code") or "")
                if re.fullmatch(r"\d{4}", t):
                    out[t] = clean(x.get("name", ""))
    except Exception as e:
        print("fetch_master fail", e)

    if not out:
        d = load_json(DATA / "sectors.json", {})
        for sec in d.get("sectors", []):
            for x in sec.get("stocks", []):
                t = str(x.get("ticker", ""))
                if re.fullmatch(r"\d{4}", t):
                    out[t] = clean(x.get("name", ""))

    return out

def rows_from_api(url):
    a = get_json(url, timeout=60)
    if isinstance(a, dict):
        a = next(
            (
                a[k]
                for k in ("data", "records", "result")
                if isinstance(a.get(k), list)
            ),
            [],
        )
    return a if isinstance(a, list) else []

def fetch_news():
    out = []

    for market, url in (
        ("twse", TWSE_NEWS),
        ("tpex", TPEX_NEWS),
    ):
        try:
            rows = rows_from_api(url)
        except Exception as e:
            print("news fail", market, e)
            continue

        for r in rows:
            t = str(
                pick(
                    r,
                    ["公司代號", "證券代號", "股票代號"],
                    "",
                )
            ).strip()

            if not re.fullmatch(r"\d{4}", t):
                continue

            out.append(
                {
                    "ticker": t,
                    "market": market,
                    "name": clean(
                        pick(
                            r,
                            ["公司名稱", "證券名稱"],
                            "",
                        )
                    ),
                    "subject": clean(
                        pick(
                            r,
                            ["主旨", "Subject"],
                            "",
                        )
                    ),
                    "date": roc_date(
                        pick(
                            r,
                            ["發言日期", "公告日期", "Date"],
                            "",
                        )
                    ),
                    "time": clean(
                        pick(
                            r,
                            ["發言時間", "公告時間", "Time"],
                            "",
                        )
                    ),
                    "raw": r,
                }
            )

    return out

def extract_planned_date(subject, announce_date):
    s = clean(subject)

    ms = list(
        re.finditer(
            r"(?:(20\d{2})|(\d{2,3}))\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})",
            s,
        )
    )

    if ms:
        m = ms[-1]
        y = int(m.group(1) or m.group(2))
        if y < 1911:
            y += 1911
        return f"{y:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"

    # 主旨沒有真正董事會日期時不拿公告日冒充
    return ""

def is_preview_subject(s):
    s = clean(s)

    if not (
        "財務報告" in s
        or "財務報表" in s
    ):
        return False

    if any(
        k in s
        for k in (
            "通過",
            "決議",
            "提報董事會通過",
        )
    ):
        return False

    return any(
        k in s
        for k in (
            "董事會預計召開",
            "預計召開董事會",
            "預計提報董事會",
            "預計於",
        )
    )

def is_report_subject(s):
    s = clean(s)

    return (
        (
            "財務報告" in s
            or "財務報表" in s
        )
        and any(
            k in s
            for k in (
                "通過",
                "決議",
                "提報董事會通過",
            )
        )
    )

def financial_snapshot():
    rows = []

    for market, url in (
        ("twse", TWSE_IS),
        ("tpex", TPEX_IS),
    ):
        try:
            a = rows_from_api(url)
        except Exception as e:
            print("financial fail", market, e)
            continue

        for r in a:
            t = str(
                pick(
                    r,
                    ["公司代號", "證券代號"],
                    "",
                )
            ).strip()

            yy = pick(r, ["年度", "Year"], "")
            qq = pick(r, ["季別", "Season"], "")

            if (
                not re.fullmatch(r"\d{4}", t)
                or yy in ("", None)
                or qq in ("", None)
            ):
                continue

            try:
                y = int(
                    float(
                        str(yy).replace(",", "")
                    )
                )
                if y < 1911:
                    y += 1911

                q = int(
                    float(
                        str(qq).replace(",", "")
                    )
                )
            except Exception:
                continue

            rows.append(
                {
                    "ticker": t,
                    "market": market,
                    "period": f"{y}-Q{q}",
                    "cum_revenue": num(
                        pick(
                            r,
                            [
                                "營業收入",
                                "營業收入合計",
                                "Revenue",
                            ],
                            None,
                        )
                    ),
                    "cum_gross": num(
                        pick(
                            r,
                            [
                                "營業毛利（毛損）",
                                "營業毛利(毛損)",
                                "營業毛利",
                                "GrossProfit",
                            ],
                            None,
                        )
                    ),
                    "cum_eps": num(
                        pick(
                            r,
                            [
                                "基本每股盈餘（元）",
                                "基本每股盈餘(元)",
                                "基本每股盈餘",
                                "BasicEarningsPerShare",
                            ],
                            None,
                        )
                    ),
                }
            )

    return rows

def merge_history(snapshot):
    hist = load_json(
        HISTORY,
        {"rows": []},
    )

    by = {}

    for r in hist.get("rows", []):
        if (
            r.get("ticker")
            and r.get("period")
        ):
            by[
                (
                    r["ticker"],
                    r["period"],
                )
            ] = r

    for r in snapshot:
        by[
            (
                r["ticker"],
                r["period"],
            )
        ] = r

    rows = list(by.values())

    rows.sort(
        key=lambda x: (
            x.get("period", ""),
            x.get("ticker", ""),
        )
    )

    save_json(
        HISTORY,
        {
            "version": VERSION,
            "updated_at": now_tpe().isoformat(
                timespec="minutes"
            ),
            "rows": rows,
        },
    )

    return by

def single_metrics(by, t, p):
    r = by.get((t, p))

    if not r:
        return {
            "eps": None,
            "gross_margin": None,
        }

    q = int(p[-1])

    rev = r.get("cum_revenue")
    gp = r.get("cum_gross")
    ceps = r.get("cum_eps")

    if q == 1:
        srev = rev
        sgp = gp
        seps = ceps

    else:
        pp = previous(p)
        pr = by.get((t, pp))

        if not pr:
            return {
                "eps": None,
                "gross_margin": None,
            }

        srev = (
            rev - pr.get("cum_revenue")
            if (
                rev is not None
                and pr.get("cum_revenue") is not None
            )
            else None
        )

        sgp = (
            gp - pr.get("cum_gross")
            if (
                gp is not None
                and pr.get("cum_gross") is not None
            )
            else None
        )

        # 累計 EPS 不直接相減
        seps = r.get("single_eps")

    gm = (
        sgp / srev * 100
        if (
            sgp is not None
            and srev not in (None, 0)
        )
        else None
    )

    return {
        "eps": seps,
        "gross_margin": gm,
    }

def f(v, s=""):
    return (
        "—"
        if v is None
        else f"{float(v):.2f}{s}"
    )

def tg(text):
    token = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip()

    chat = os.getenv(
        "TELEGRAM_CHAT_ID",
        "",
    ).strip()

    if not token or not chat:
        return False

    r = S.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={
            "chat_id": chat,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    r.raise_for_status()
    return True

def next_weekday(d):
    """
    暫以平日作下一交易日。
    週五 -> 週一。
    """
    x = d + timedelta(days=1)

    while x.weekday() >= 5:
        x += timedelta(days=1)

    return x

def main():
    uni = fetch_universe()

    old = load_json(
        OUT,
        {
            "upcoming": [],
            "reports": [],
        },
    )

    sent = set(
        load_json(
            SENT,
            {"ids": []},
        ).get(
            "ids",
            [],
        )
    )

    news = fetch_news()

    # 歷史財報仍留在後台
    # 不代表要顯示在前端
    by = merge_history(
        financial_snapshot()
    )

    now = now_tpe()
    today = now.date().isoformat()

    # =====================================================
    # 即將開財報
    #
    # 沒抓到真正日期就完全不 show
    # =====================================================

    upcoming = {}

    # 保留之前已確認、而且尚未過期的 upcoming
    for x in old.get(
        "upcoming",
        [],
    ):
        t = str(
            x.get(
                "ticker",
                "",
            )
        )

        p = str(
            x.get(
                "period",
                "",
            )
        )

        d = str(
            x.get(
                "planned_date",
                "",
            )
        )

        if (
            t
            and p
            and d
            and d >= today
        ):
            upcoming[
                (t, p)
            ] = x

    # 新的 MOPS 財報預告
    for x in news:
        t = x["ticker"]

        if t not in uni:
            continue

        subject = x["subject"]

        if not is_preview_subject(
            subject
        ):
            continue

        d = extract_planned_date(
            subject,
            x["date"],
        )

        p = period_from_text(
            subject,
            d or x["date"],
        )

        # 沒有真正董事會日期：
        # 不顯示、不拿公告日代替
        if not d or not p:
            continue

        upcoming[
            (t, p)
        ] = {
            "ticker": t,
            "name": (
                uni.get(t)
                or x["name"]
                or t
            ),
            "period": p,
            "planned_date": d,
            "announcement_date": x["date"],
            "subject": subject,
        }

    # =====================================================
    # 正式財報事件
    #
    # 不再把 OpenAPI 裡所有 Q2 財報塞進前端
    # =====================================================

    report_events = {}

    # 保留舊的「事件型」正式財報
    # 只保留到下一個交易日
    for x in old.get(
        "reports",
        [],
    ):
        t = str(
            x.get(
                "ticker",
                "",
            )
        )

        p = str(
            x.get(
                "period",
                "",
            )
        )

        publish_date = str(
            x.get(
                "publish_date",
                "",
            )
        )

        # 舊版那批 Q2 沒 publish_date
        # 會在這裡直接被清掉
        if (
            not t
            or not p
            or not publish_date
        ):
            continue

        try:
            pub = datetime.strptime(
                publish_date,
                "%Y-%m-%d",
            ).date()
        except Exception:
            continue

        remove_day = next_weekday(
            pub
        )

        # 下一交易日白天保留
        # 晚上 18:00 後移除
        keep = (
            now.date() < remove_day
            or (
                now.date() == remove_day
                and now.hour < 18
            )
        )

        if keep:
            report_events[
                (t, p)
            ] = x

    # 掃描今天/近期重大訊息
    # 只有真正「通過財務報告」才建立事件
    for x in news:
        t = x["ticker"]

        if t not in uni:
            continue

        subject = x["subject"]

        if not is_report_subject(
            subject
        ):
            continue

        publish_date = x.get(
            "date",
            "",
        )

        if not publish_date:
            continue

        p = period_from_text(
            subject,
            publish_date,
        )

        if not p:
            continue

        try:
            pub = datetime.strptime(
                publish_date,
                "%Y-%m-%d",
            ).date()
        except Exception:
            continue

        remove_day = next_weekday(
            pub
        )

        # 已經超過顯示期限的舊重大訊息
        # 不重新加回來
        if (
            now.date() > remove_day
            or (
                now.date() == remove_day
                and now.hour >= 18
            )
        ):
            continue

        cur = single_metrics(
            by,
            t,
            p,
        )

        prevp = previous(p)

        prev = single_metrics(
            by,
            t,
            prevp,
        )

        report_events[
            (t, p)
        ] = {
            "ticker": t,
            "name": (
                uni.get(t)
                or x["name"]
                or t
            ),
            "period": p,
            "publish_date": publish_date,
            "publish_time": x.get(
                "time",
                "",
            ),
            "subject": subject,
            "eps": cur.get(
                "eps"
            ),
            "gross_margin": cur.get(
                "gross_margin"
            ),
            "prev_period": prevp,
            "prev_eps": prev.get(
                "eps"
            ),
            "prev_gross_margin": prev.get(
                "gross_margin"
            ),
        }

    # =====================================================
    # 正式財報已公布
    # upcoming 就移除
    # =====================================================

    ups = []

    for key, x in upcoming.items():
        if key in report_events:
            continue

        d = str(
            x.get(
                "planned_date",
                "",
            )
        )

        if (
            not d
            or d < today
        ):
            continue

        prevp = previous(
            x["period"]
        )

        pm = single_metrics(
            by,
            x["ticker"],
            prevp,
        )

        x["prev_period"] = prevp

        x["prev_eps"] = pm.get(
            "eps"
        )

        x[
            "prev_gross_margin"
        ] = pm.get(
            "gross_margin"
        )

        ups.append(x)

    ups.sort(
        key=lambda x: (
            x.get(
                "planned_date",
                "9999",
            ),
            x.get(
                "ticker",
                "",
            ),
        )
    )

    reports = list(
        report_events.values()
    )

    reports.sort(
        key=lambda x: (
            x.get(
                "publish_date",
                "",
            ),
            x.get(
                "publish_time",
                "",
            ),
            x.get(
                "ticker",
                "",
            ),
        ),
        reverse=True,
    )

    # =====================================================
    # Telegram：即將開財報
    # =====================================================

    for x in ups:
        k = (
            f'preview|'
            f'{x["ticker"]}|'
            f'{x["period"]}|'
            f'{x["planned_date"]}'
        )

        if k in sent:
            continue

        msg = (
            f'📅 {x["name"]} '
            f'{x["ticker"]}｜'
            f'{x["period"]} 財報預告\n'
            f'財報董事會：'
            f'{x["planned_date"]}\n'
            f'上一季 EPS：'
            f'{f(x.get("prev_eps"))} 元\n'
            f'上一季毛利率：'
            f'{f(x.get("prev_gross_margin"), "%")}'
        )

        if tg(msg):
            sent.add(k)

    # =====================================================
    # Telegram：正式財報
    #
    # 數字尚未可靠取得時不亂推
    # =====================================================

    for x in reports:
        k = (
            f'report|'
            f'{x["ticker"]}|'
            f'{x["period"]}|'
            f'{x.get("publish_date", "")}'
        )

        if k in sent:
            continue

        if (
            x.get("eps") is None
            and x.get(
                "gross_margin"
            ) is None
        ):
            continue

        msg = (
            f'📊 {x["name"]} '
            f'{x["ticker"]}｜'
            f'{x["period"]} 財報\n'
            f'本季 EPS：'
            f'{f(x.get("eps"))} 元\n'
            f'本季毛利率：'
            f'{f(x.get("gross_margin"), "%")}\n'
            f'上一季 EPS：'
            f'{f(x.get("prev_eps"))} 元\n'
            f'上一季毛利率：'
            f'{f(x.get("prev_gross_margin"), "%")}'
        )

        if tg(msg):
            sent.add(k)

    # =====================================================
    # 前端只輸出事件
    #
    # 沒有事件時就是：
    # upcoming []
    # reports []
    #
    # HISTORY 仍保留後台計算
    # =====================================================

    save_json(
        OUT,
        {
            "version": VERSION,
            "updated_at": now.isoformat(
                timespec="minutes"
            ),
            "upcoming": ups,
            "reports": reports,
        },
    )

    save_json(
        SENT,
        {
            "updated_at": now.isoformat(
                timespec="minutes"
            ),
            "ids": sorted(sent)[-4000:],
        },
    )

    print(
        "quarterly earnings",
        "universe",
        len(uni),
        "upcoming",
        len(ups),
        "reports",
        len(reports),
    )

    print(
        "historical financial data stays in "
        "quarterly_earnings_history.json; "
        "frontend is event-only."
    )

if __name__ == "__main__":
    main()
