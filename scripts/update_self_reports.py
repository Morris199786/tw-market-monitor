from sources import *
import os
import re
from datetime import datetime, timedelta


TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"

# 明確屬於自結／近期財務業務資訊的主旨關鍵字
STRONG_SUBJECT_KEYWORDS = (
    "自結",
    "財務業務資訊",
    "近期財務資訊",
    "近期財務業務資訊",
    "最近一月",
    "最近一季",
)

# 常見「注意交易」而被要求公告近期財務業務資訊的主旨
NOTICE_SUBJECT_KEYWORDS = (
    "達公布注意交易資訊標準",
    "達注意交易資訊標準",
    "多次達公布注意交易資訊標準",
    "有價證券達公布注意交易資訊標準",
)

# 內容中至少要真的出現財務數字欄位
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

# 明顯不是自結的公告主旨，即使內文剛好出現財務字眼也排除
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
    "薪資報酬委員",
    "審計委員",
)


def roc_to_iso(s):
    s = re.sub(
        r"\D",
        "",
        str(s or "")
    )

    if len(s) < 7:
        return ""

    try:
        y = int(s[:-4]) + 1911
        m = int(s[-4:-2])
        d = int(s[-2:])

        return (
            f"{y:04d}-"
            f"{m:02d}-"
            f"{d:02d}"
        )

    except Exception:
        return ""


def clean_time(s):
    t = re.sub(
        r"\D",
        "",
        str(s or "")
    )

    if not t:
        return ""

    t = t.zfill(6)

    return (
        f"{t[-6:-4]}:"
        f"{t[-4:-2]}:"
        f"{t[-2:]}"
    )


def p(row, names, default=""):
    return pick(
        row,
        names,
        default
    )


def norm_text(s):
    return (
        str(s or "")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("　", " ")
        .strip()
    )


def has_number_near_anchor(text, anchor):
    """
    財務欄位後方 60 字內需真的有數字，
    避免只因公告模板或引用文字提到 EPS／營收就誤判。
    """
    pat = (
        re.escape(anchor)
        + r".{0,60}?"
        + r"-?\d+(?:\.\d+)?"
    )

    return bool(
        re.search(
            pat,
            text,
            re.I | re.S
        )
    )


def financial_signal_count(text):
    count = 0

    for anchor in FINANCIAL_ANCHORS:
        if has_number_near_anchor(
            text,
            anchor
        ):
            count += 1

    return count


def is_self_report(subject, detail):
    """
    嚴格版判斷：

    1. 主旨本身要明確是自結／近期財務業務資訊，
       或屬注意交易而被要求公告財務業務資訊
    2. 內文至少要有 2 個真正帶數字的財務欄位
    3. 面額、股利、董事會、增資、法說等明顯非自結公告直接排除
    """
    subject = norm_text(
        subject
    )
    detail = norm_text(
        detail
    )

    text = (
        f"{subject}\n{detail}"
    )

    if any(
        k in subject
        for k in EXCLUDE_SUBJECT_KEYWORDS
    ):
        return False

    strong_subject = any(
        k in subject
        for k in STRONG_SUBJECT_KEYWORDS
    )

    notice_subject = any(
        k in subject
        for k in NOTICE_SUBJECT_KEYWORDS
    )

    # 主旨都沒有自結／財務公告意圖，直接排除
    if not (
        strong_subject
        or notice_subject
    ):
        return False

    signals = (
        financial_signal_count(
            text
        )
    )

    # 至少兩個財務欄位帶實際數字
    if signals < 2:
        return False

    # 再要求其中至少有一個核心獲利欄位
    core_profit = any(
        has_number_near_anchor(
            text,
            anchor
        )
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

    return core_profit


def first_number(
    patterns,
    text
):
    for pat in patterns:
        m = re.search(
            pat,
            text,
            re.I | re.S
        )

        if m:
            return n(
                m.group(1),
                None
            )

    return None


def extract_metrics(detail):
    text = (
        str(detail or "")
        .replace(",", "")
    )

    eps = first_number(
        [
            r"每股盈餘.{0,45}?(-?\d+(?:\.\d+)?)",
            r"\bEPS.{0,30}?(-?\d+(?:\.\d+)?)",
        ],
        text,
    )

    pretax = first_number(
        [
            r"稅前(?:淨利|純益|損益).{0,45}?(-?\d+(?:\.\d+)?)",
        ],
        text,
    )

    net = first_number(
        [
            r"(?:歸屬母公司(?:業主)?(?:淨利|損益)|稅後(?:淨利|純益|損益)|本期淨利).{0,45}?(-?\d+(?:\.\d+)?)",
        ],
        text,
    )

    revenue = first_number(
        [
            r"(?:營業收入|營收).{0,45}?(-?\d+(?:\.\d+)?)",
        ],
        text,
    )

    return {
        "eps": eps,
        "pretax_million": (
            pretax
        ),
        "net_income_million": (
            net
        ),
        "revenue_million": (
            revenue
        ),
    }


def fetch_rows():
    out = []

    for market, url in (
        (
            "twse",
            TWSE_NEWS
        ),
        (
            "tpex",
            TPEX_NEWS
        ),
    ):
        try:
            arr = get_json(
                url,
                timeout=45
            )

        except Exception as e:
            print(
                "self report source fail",
                market,
                repr(e)
            )
            continue

        if isinstance(
            arr,
            dict
        ):
            arr = (
                arr.get("data")
                or arr.get("records")
                or arr.get("result")
                or []
            )

        if not isinstance(
            arr,
            list
        ):
            continue

        for r in arr:
            t = str(
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

            if not ordinary_ticker(
                t
            ):
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

            publish_date = (
                roc_to_iso(
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
            )

            publish_time = (
                clean_time(
                    p(
                        r,
                        [
                            "發言時間",
                            "公告時間",
                        ],
                        "",
                    )
                )
            )

            metrics = (
                extract_metrics(
                    detail
                )
            )

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
                    "publish_date": (
                        publish_date
                    ),
                    "publish_time": (
                        publish_time
                    ),
                    "subject": (
                        subject
                    ),
                    "detail": (
                        detail
                    ),
                    **metrics,
                }
            )

    return out


def week_bounds(
    date_obj
):
    monday = (
        date_obj
        - timedelta(
            days=date_obj.weekday()
        )
    )

    friday = (
        monday
        + timedelta(
            days=4
        )
    )

    return (
        monday,
        friday
    )


def week_label(
    monday,
    friday
):
    return (
        f"{monday.month}/"
        f"{monday.day}"
        f"～"
        f"{friday.month}/"
        f"{friday.day}"
    )


def send_pushover(
    title,
    message
):
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


def push_text(x):
    lines = [
        (
            f"{x['name']} "
            f"{x['ticker']}"
        ),
        (
            x.get("subject")
            or "公布自結財務資訊"
        ),
    ]

    if x.get("eps") is not None:
        lines.append(
            f"EPS "
            f"{x['eps']:.2f} 元"
        )

    if (
        x.get(
            "pretax_million"
        )
        is not None
    ):
        lines.append(
            "稅前淨利 "
            f"{x['pretax_million']:.0f} "
            "百萬"
        )

    if (
        x.get(
            "net_income_million"
        )
        is not None
    ):
        lines.append(
            "稅後／歸母淨利 "
            f"{x['net_income_million']:.0f} "
            "百萬"
        )

    return "\n".join(
        lines
    )


def main():
    today = (
        now_tpe().date()
    )

    monday, friday = (
        week_bounds(
            today
        )
    )

    current_key = (
        monday.isoformat()
    )

    label = week_label(
        monday,
        friday
    )

    hist_path = (
        ROOT
        / "data/self_reports_history.json"
    )

    sent_path = (
        ROOT
        / "data/self_reports_sent.json"
    )

    old = load_json(
        hist_path,
        {}
    )

    # 舊資料也重新跑一次嚴格判斷，
    # 會自動清掉上一版誤抓到的非自結公告。
    items_by_id = {}

    for x in old.get(
        "items",
        []
    ):
        if not x.get("id"):
            continue

        if not is_self_report(
            x.get(
                "subject",
                ""
            ),
            x.get(
                "detail",
                ""
            ),
        ):
            continue

        d = str(
            x.get(
                "publish_date"
            )
            or ""
        )

        if (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            items_by_id[
                str(x["id"])
            ] = x

    fresh = fetch_rows()

    for x in fresh:
        d = x.get(
            "publish_date"
        )

        if not d:
            continue

        if (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            items_by_id[
                x["id"]
            ] = x

    items = list(
        items_by_id.values()
    )

    items.sort(
        key=lambda x: (
            x.get(
                "publish_date",
                ""
            ),
            x.get(
                "publish_time",
                ""
            ),
            x.get(
                "ticker",
                ""
            ),
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
        if x["id"] in sent:
            continue

        d = (
            x.get(
                "publish_date"
            )
            or ""
        )

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
            sent.add(
                x["id"]
            )

    save_json(
        hist_path,
        {
            "week_key": (
                current_key
            ),
            "updated_at": (
                now_tpe()
                .isoformat(
                    timespec="minutes"
                )
            ),
            "items": items,
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

    save_json(
        ROOT
        / "data/self_reports.json",
        {
            "updated_at": (
                now_tpe()
                .isoformat(
                    timespec="minutes"
                )
            ),
            "current_week_key": (
                current_key
            ),
            "current_week_label": (
                label
            ),
            "filter_version": (
                "2026-09-26-v2-strict"
            ),
            "weeks": [
                {
                    "key": (
                        current_key
                    ),
                    "label": (
                        label
                    ),
                    "items": (
                        items
                    ),
                }
            ],
        },
    )

    print(
        "self reports",
        label,
        len(items),
        "fresh",
        len(fresh),
        "filter",
        "2026-09-26-v2-strict",
    )


if __name__ == "__main__":
    main()
