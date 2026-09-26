from sources import *
import os
import re

VERSION = "2026-09-26-v7-forward-monitor"

TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"

# 從新版架構啟用日開始，只收未來新公告
MONITOR_START_DATE = "2026-09-26"

SUBJECT_KEYWORDS = (
    "自結",
    "財務業務資訊",
    "近期財務資訊",
    "近期財務業務資訊",
    "最近一月",
    "最近一季",
    "達公布注意交易資訊標準",
    "達注意交易資訊標準",
    "多次達公布注意交易資訊標準",
    "有價證券達公布注意交易資訊標準",
    "注意交易資訊標準",
)

FINANCIAL_ANCHORS = (
    "營業收入",
    "營收",
    "稅前淨利",
    "稅前純益",
    "稅前損益",
    "稅後淨利",
    "稅後純益",
    "稅後損益",
    "本期淨利",
    "歸屬母公司",
    "每股盈餘",
    "EPS",
)

EXCLUDE_SUBJECT_KEYWORDS = (
    "股票面額",
    "面額變更",
    "除權",
    "除息",
    "股利",
    "現金股利",
    "盈餘分配",
    "董事會",
    "股東會",
    "法說會",
    "法人說明會",
    "增資",
    "減資",
    "現金增資",
    "可轉換公司債",
    "可轉債",
    "公司債",
    "私募",
    "庫藏股",
    "取得或處分資產",
    "背書保證",
    "資金貸與",
    "關係人交易",
    "更換會計師",
    "簽證會計師",
    "發言人",
    "代理發言人",
    "董事辭任",
    "獨立董事",
)


def p(row, names, default=""):
    return pick(row, names, default)


def norm_text(s):
    return (
        str(s or "")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("　", " ")
        .strip()
    )


def roc_to_iso(s):
    raw = str(s or "").strip()

    m = re.search(
        r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})",
        raw
    )
    if m:
        return (
            f"{int(m.group(1)):04d}-"
            f"{int(m.group(2)):02d}-"
            f"{int(m.group(3)):02d}"
        )

    m = re.search(
        r"(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})",
        raw
    )
    if m:
        return (
            f"{int(m.group(1)) + 1911:04d}-"
            f"{int(m.group(2)):02d}-"
            f"{int(m.group(3)):02d}"
        )

    digits = re.sub(r"\D", "", raw)

    if len(digits) == 8 and digits.startswith("20"):
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"

    if len(digits) == 7:
        try:
            y = int(digits[:3]) + 1911
            return f"{y:04d}-{digits[3:5]}-{digits[5:7]}"
        except Exception:
            return ""

    return ""


def clean_time(s):
    raw = str(s or "").strip()

    m = re.search(
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?",
        raw
    )
    if m:
        return (
            f"{int(m.group(1)):02d}:"
            f"{int(m.group(2)):02d}:"
            f"{int(m.group(3) or 0):02d}"
        )

    digits = re.sub(r"\D", "", raw)

    if not digits:
        return ""

    digits = digits.zfill(6)[-6:]
    return f"{digits[:2]}:{digits[2:4]}:{digits[4:6]}"


def subject_looks_like_self_report(subject):
    subject = norm_text(subject)

    if any(k in subject for k in EXCLUDE_SUBJECT_KEYWORDS):
        return False

    return any(k in subject for k in SUBJECT_KEYWORDS)


def has_number_near_anchor(text, anchor):
    return bool(
        re.search(
            re.escape(anchor)
            + r".{0,120}?"
            + r"-?\d+(?:\.\d+)?",
            text,
            re.I | re.S,
        )
    )


def is_self_report(subject, detail):
    if not subject_looks_like_self_report(subject):
        return False

    text = f"{subject}\n{detail}"

    signals = sum(
        1
        for anchor in FINANCIAL_ANCHORS
        if has_number_near_anchor(text, anchor)
    )

    if signals < 2:
        return False

    return any(
        has_number_near_anchor(text, anchor)
        for anchor in (
            "稅前淨利",
            "稅前純益",
            "稅前損益",
            "稅後淨利",
            "稅後純益",
            "稅後損益",
            "本期淨利",
            "歸屬母公司",
            "每股盈餘",
            "EPS",
        )
    )


def first_number(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, re.I | re.S)
        if m:
            return n(m.group(1), None)

    return None


def extract_metrics(detail):
    text = str(detail or "").replace(",", "")

    return {
        "eps": first_number(
            [
                r"每股盈餘.{0,100}?(-?\d+(?:\.\d+)?)",
                r"\bEPS.{0,80}?(-?\d+(?:\.\d+)?)",
            ],
            text,
        ),
        "pretax_million": first_number(
            [
                r"稅前(?:淨利|純益|損益).{0,100}?(-?\d+(?:\.\d+)?)",
            ],
            text,
        ),
        "net_income_million": first_number(
            [
                r"(?:歸屬母公司(?:業主)?(?:淨利|損益)|稅後(?:淨利|純益|損益)|本期淨利).{0,100}?(-?\d+(?:\.\d+)?)",
            ],
            text,
        ),
        "revenue_million": first_number(
            [
                r"(?:營業收入|營收).{0,100}?(-?\d+(?:\.\d+)?)",
            ],
            text,
        ),
    }


def identity(x):
    return "|".join(
        [
            str(x.get("market") or ""),
            str(x.get("ticker") or ""),
            str(x.get("publish_date") or ""),
            str(x.get("publish_time") or ""),
            re.sub(
                r"\s+",
                "",
                str(x.get("subject") or "")
            ),
        ]
    )


def fetch_source(market, url):
    try:
        arr = get_json(
            url,
            timeout=45,
            tries=5,
        )

    except Exception as e:
        return {
            "market": market,
            "ok": False,
            "error": repr(e),
            "rows": [],
            "items": [],
        }

    if isinstance(arr, dict):
        arr = (
            arr.get("data")
            or arr.get("records")
            or arr.get("result")
            or []
        )

    if not isinstance(arr, list):
        return {
            "market": market,
            "ok": False,
            "error": "response is not a list",
            "rows": [],
            "items": [],
        }

    items = []

    for r in arr:
        ticker = str(
            p(
                r,
                [
                    "公司代號",
                    "證券代號",
                    "股票代號",
                    "代號",
                ],
                "",
            )
        ).strip()

        if not ordinary_ticker(ticker):
            continue

        subject = str(
            p(
                r,
                [
                    "主旨",
                    "主旨 ",
                    "Subject",
                ],
                "",
            )
        ).strip()

        detail = str(
            p(
                r,
                [
                    "說明",
                    "Description",
                    "內容",
                ],
                "",
            )
        ).strip()

        if not is_self_report(
            subject,
            detail
        ):
            continue

        publish_date = roc_to_iso(
            p(
                r,
                [
                    "發言日期",
                    "公告日期",
                    "出表日期",
                ],
                "",
            )
        )

        # 新架構只收 9/26 之後的公告
        if (
            not publish_date
            or publish_date < MONITOR_START_DATE
        ):
            continue

        publish_time = clean_time(
            p(
                r,
                [
                    "發言時間",
                    "公告時間",
                ],
                "",
            )
        )

        items.append(
            {
                "market": market,
                "ticker": ticker,
                "name": clean_name(
                    p(
                        r,
                        [
                            "公司名稱",
                            "證券名稱",
                            "名稱",
                        ],
                        "",
                    )
                ),
                "publish_date": publish_date,
                "publish_time": publish_time,
                "subject": subject,
                "detail": detail,
                "source": "openapi",
                **extract_metrics(detail),
            }
        )

    return {
        "market": market,
        "ok": True,
        "error": "",
        "rows": arr,
        "items": items,
    }


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
            "pushover secrets missing; skip push"
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


def push_text(x):
    lines = [
        f"{x.get('name') or x['ticker']} {x['ticker']}",
        x.get("subject") or "公布自結財務資訊",
    ]

    if x.get("eps") is not None:
        lines.append(
            f"EPS {x['eps']:.2f} 元"
        )

    if x.get("pretax_million") is not None:
        lines.append(
            "稅前淨利 "
            f"{x['pretax_million']:.0f} 百萬"
        )

    if x.get("net_income_million") is not None:
        lines.append(
            "稅後／歸母淨利 "
            f"{x['net_income_million']:.0f} 百萬"
        )

    return "\n".join(lines)


def main():
    history_path = (
        ROOT / "data/self_reports_history.json"
    )
    sent_path = (
        ROOT / "data/self_reports_sent.json"
    )

    old = load_json(
        history_path,
        {}
    )

    # 只保留新版架構開始後的資料
    saved = {}

    for x in old.get(
        "items",
        []
    ):
        d = str(
            x.get("publish_date")
            or ""
        )

        if d < MONITOR_START_DATE:
            continue

        if not subject_looks_like_self_report(
            x.get("subject", "")
        ):
            continue

        saved[
            identity(x)
        ] = x

    results = [
        fetch_source(
            "twse",
            TWSE_NEWS
        ),
        fetch_source(
            "tpex",
            TPEX_NEWS
        ),
    ]

    ok_sources = [
        x
        for x in results
        if x["ok"]
    ]

    # 兩個來源同時掛掉時直接讓 workflow 失敗，
    # 不會假裝成功，也不會覆蓋舊資料
    if not ok_sources:
        for x in results:
            print(
                "source fail",
                x["market"],
                x["error"],
            )

        raise RuntimeError(
            "TWSE and TPEx self-report sources both failed"
        )

    fresh = []

    for result in results:
        print(
            "source",
            result["market"],
            "ok" if result["ok"] else "fail",
            "rows",
            len(result["rows"]),
            "self_reports",
            len(result["items"]),
            result["error"],
        )

        for x in result["items"]:
            key = identity(x)
            fresh.append(x)

            # 新資料覆蓋舊版本
            saved[key] = x

    items = list(
        saved.values()
    )

    items.sort(
        key=lambda x: (
            x.get("publish_date", ""),
            x.get("publish_time", ""),
            x.get("ticker", ""),
        ),
        reverse=True,
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

    for x in fresh:
        key = identity(x)

        if key in sent:
            continue

        if send_pushover(
            "自結公布",
            push_text(x),
        ):
            sent.add(key)

    updated_at = (
        now_tpe()
        .isoformat(
            timespec="minutes"
        )
    )

    save_json(
        history_path,
        {
            "updated_at": updated_at,
            "version": VERSION,
            "monitor_start_date": MONITOR_START_DATE,
            "items": items,
        },
    )

    save_json(
        sent_path,
        {
            "updated_at": updated_at,
            "ids": list(sent)[-2000:],
        },
    )

    save_json(
        ROOT / "data/self_reports.json",
        {
            "updated_at": updated_at,
            "monitor_start_date": MONITOR_START_DATE,
            "filter_version": VERSION,
            "source_mode": (
                "TWSE/TPEx OpenAPI 即時監控 + 本站永久保存"
            ),
            "source_status": {
                x["market"]: {
                    "ok": x["ok"],
                    "rows": len(x["rows"]),
                    "self_reports": len(x["items"]),
                    "error": x["error"],
                }
                for x in results
            },
            "items": items,
        },
    )

    print(
        "self reports",
        "stored",
        len(items),
        "fresh",
        len(fresh),
        "version",
        VERSION,
    )


if __name__ == "__main__":
    main()
