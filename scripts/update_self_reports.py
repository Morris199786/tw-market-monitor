from sources import *
import os
import re
from datetime import datetime, timedelta


TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"

KEYWORDS = (
    "自結",
    "財務業務資訊",
    "每股盈餘",
    "EPS",
    "稅前淨利",
    "稅前純益",
    "稅後淨利",
    "稅後純益",
    "歸屬母公司",
    "歸屬母公司業主",
)


def roc_to_iso(s):
    s = re.sub(r"\D", "", str(s or ""))
    if len(s) < 7:
        return ""
    try:
        y = int(s[:-4]) + 1911
        m = int(s[-4:-2])
        d = int(s[-2:])
        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return ""


def clean_time(s):
    t = re.sub(r"\D", "", str(s or ""))
    if not t:
        return ""
    t = t.zfill(6)
    return f"{t[-6:-4]}:{t[-4:-2]}:{t[-2:]}"


def p(row, names, default=""):
    return pick(row, names, default)


def is_self_report(subject, detail):
    text = f"{subject}\n{detail}"
    if not any(k.lower() in text.lower() for k in KEYWORDS):
        return False

    # 真正有自結財務數字，或注意交易／異常交易而公告財務業務資訊
    anchors = (
        "自結",
        "財務業務資訊",
        "最近一月",
        "每股盈餘",
        "EPS",
    )
    return any(x.lower() in text.lower() for x in anchors)


def first_number(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, re.I | re.S)
        if m:
            return n(m.group(1), None)
    return None


def extract_metrics(detail):
    text = str(detail or "").replace(",", "")

    eps = first_number(
        [
            r"每股盈餘.{0,35}?(-?\d+(?:\.\d+)?)",
            r"\bEPS.{0,20}?(-?\d+(?:\.\d+)?)",
        ],
        text,
    )

    pretax = first_number(
        [
            r"稅前(?:淨利|純益|損益).{0,35}?(-?\d+(?:\.\d+)?)",
        ],
        text,
    )

    net = first_number(
        [
            r"(?:歸屬母公司(?:業主)?(?:淨利|損益)|稅後(?:淨利|純益|損益)|本期淨利).{0,35}?(-?\d+(?:\.\d+)?)",
        ],
        text,
    )

    revenue = first_number(
        [
            r"營業收入.{0,35}?(-?\d+(?:\.\d+)?)",
        ],
        text,
    )

    return {
        "eps": eps,
        "pretax_million": pretax,
        "net_income_million": net,
        "revenue_million": revenue,
    }


def fetch_rows():
    out = []

    for market, url in (
        ("twse", TWSE_NEWS),
        ("tpex", TPEX_NEWS),
    ):
        try:
            arr = get_json(url, timeout=45)
        except Exception as e:
            print("self report source fail", market, repr(e))
            continue

        if isinstance(arr, dict):
            arr = (
                arr.get("data")
                or arr.get("records")
                or arr.get("result")
                or []
            )

        if not isinstance(arr, list):
            continue

        for r in arr:
            t = str(
                p(
                    r,
                    ["公司代號", "證券代號", "股票代號", "代號"],
                    "",
                )
            ).strip()

            if not ordinary_ticker(t):
                continue

            subject = str(
                p(r, ["主旨", "主旨 ", "Subject"], "")
            ).strip()

            detail = str(
                p(r, ["說明", "Description", "內容"], "")
            ).strip()

            if not is_self_report(subject, detail):
                continue

            publish_date = roc_to_iso(
                p(r, ["發言日期", "公告日期", "出表日期"], "")
            )

            publish_time = clean_time(
                p(r, ["發言時間", "公告時間"], "")
            )

            metrics = extract_metrics(detail)

            uid = "|".join(
                [
                    market,
                    t,
                    publish_date,
                    publish_time,
                    subject,
                ]
            )

            out.append(
                {
                    "id": uid,
                    "market": market,
                    "ticker": t,
                    "name": clean_name(
                        p(r, ["公司名稱", "證券名稱", "名稱"], "")
                    ),
                    "publish_date": publish_date,
                    "publish_time": publish_time,
                    "subject": subject,
                    "detail": detail,
                    **metrics,
                }
            )

    return out


def week_bounds(date_obj):
    monday = date_obj - timedelta(days=date_obj.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def week_label(monday, friday):
    return (
        f"{monday.month}/{monday.day}"
        f"～{friday.month}/{friday.day}"
    )


def send_pushover(title, message):
    token = os.getenv("PUSHOVER_APP_TOKEN", "").strip()
    user = os.getenv("PUSHOVER_USER_KEY", "").strip()

    if not token or not user:
        print("pushover secrets missing; skip push")
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
        print("pushover failed", repr(e))
        return False


def push_text(x):
    lines = [
        f"{x['name']} {x['ticker']}",
        x.get("subject") or "公布自結財務資訊",
    ]

    if x.get("eps") is not None:
        lines.append(f"EPS {x['eps']:.2f} 元")

    if x.get("pretax_million") is not None:
        lines.append(f"稅前淨利 {x['pretax_million']:.0f} 百萬")

    if x.get("net_income_million") is not None:
        lines.append(f"稅後／歸母淨利 {x['net_income_million']:.0f} 百萬")

    return "\n".join(lines)


def main():
    today = now_tpe().date()
    monday, friday = week_bounds(today)

    current_key = monday.isoformat()
    label = week_label(monday, friday)

    hist_path = ROOT / "data/self_reports_history.json"
    sent_path = ROOT / "data/self_reports_sent.json"

    old = load_json(hist_path, {})
    items_by_id = {
        str(x.get("id")): x
        for x in old.get("items", [])
        if x.get("id")
    }

    fresh = fetch_rows()

    for x in fresh:
        d = x.get("publish_date")
        if not d:
            continue

        # 僅保留本週，週一自動清掉上週資料
        if monday.isoformat() <= d <= friday.isoformat():
            items_by_id[x["id"]] = x

    items = list(items_by_id.values())
    items = [
        x for x in items
        if monday.isoformat()
        <= str(x.get("publish_date") or "")
        <= friday.isoformat()
    ]

    items.sort(
        key=lambda x: (
            x.get("publish_date", ""),
            x.get("publish_time", ""),
            x.get("ticker", ""),
        ),
        reverse=True,
    )

    sent_data = load_json(sent_path, {})
    sent = set(sent_data.get("ids", []))

    for x in fresh:
        if x["id"] in sent:
            continue

        d = x.get("publish_date") or ""
        if not (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            continue

        if send_pushover(
            "自結公布",
            push_text(x),
        ):
            sent.add(x["id"])

    save_json(
        hist_path,
        {
            "week_key": current_key,
            "updated_at": now_tpe().isoformat(timespec="minutes"),
            "items": items,
        },
    )

    # sent state 只保留最近 500 筆即可
    save_json(
        sent_path,
        {
            "updated_at": now_tpe().isoformat(timespec="minutes"),
            "ids": list(sent)[-500:],
        },
    )

    save_json(
        ROOT / "data/self_reports.json",
        {
            "updated_at": now_tpe().isoformat(timespec="minutes"),
            "current_week_key": current_key,
            "current_week_label": label,
            "weeks": [
                {
                    "key": current_key,
                    "label": label,
                    "items": items,
                }
            ],
        },
    )

    print("self reports", label, len(items))


if __name__ == "__main__":
    main()
