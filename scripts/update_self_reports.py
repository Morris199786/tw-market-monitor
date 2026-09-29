from sources import *
import json
import os
import re
import html
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

VERSION = "2026-09-29-v11-mops-ajax"

MOPS_BASES = (
    "https://mops.twse.com.tw",
    "https://mopsov.twse.com.tw",
)

MOPS_AJAX_PATH = "/mops/web/ajax_t05st01"
TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"

MONITOR_START_DATE = "2026-09-26"
SITE_URL = "https://morris199786.github.io/tw-market-monitor/"

SELF_REPORT_KEYWORDS = (
    "自結",
    "財務業務資訊",
    "近期財務資訊",
    "近期財務業務資訊",
    "最近一月",
    "最近一季",
)

ATTENTION_KEYWORDS = (
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
    "歸屬於母公司",
    "每股盈餘",
    "每股稅後盈餘",
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
    return re.sub(
        r"\s+",
        " ",
        html.unescape(
            str(s or "")
            .replace("\r", " ")
            .replace("\n", " ")
            .replace("　", " ")
        ),
    ).strip()


def roc_to_iso(s):
    raw = str(s or "").strip()

    m = re.search(
        r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})",
        raw,
    )
    if m:
        return (
            f"{int(m.group(1)):04d}-"
            f"{int(m.group(2)):02d}-"
            f"{int(m.group(3)):02d}"
        )

    m = re.search(
        r"(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})",
        raw,
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
        y = int(digits[:3]) + 1911
        return f"{y:04d}-{digits[3:5]}-{digits[5:7]}"

    return ""


def clean_time(s):
    raw = str(s or "").strip()

    m = re.search(
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?",
        raw,
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

    return (
        f"{digits[:2]}:"
        f"{digits[2:4]}:"
        f"{digits[4:6]}"
    )


def subject_excluded(subject):
    s = norm_text(subject)

    return any(
        k in s
        for k in EXCLUDE_SUBJECT_KEYWORDS
    )


def subject_is_candidate(subject):
    s = norm_text(subject)

    if not s or subject_excluded(s):
        return False

    return (
        any(
            k in s
            for k in ATTENTION_KEYWORDS
        )
        or any(
            k in s
            for k in SELF_REPORT_KEYWORDS
        )
    )


def first_number(patterns, text):
    for pat in patterns:
        m = re.search(
            pat,
            text,
            re.I | re.S,
        )

        if not m:
            continue

        raw = (
            str(m.group(1))
            .replace(",", "")
            .strip()
        )

        return n(
            raw,
            None,
        )

    return None


def extract_metrics(text):
    text = str(
        text or ""
    ).replace(
        "，",
        ",",
    )

    return {
        "eps": first_number(
            [
                r"每股(?:稅後)?盈餘.{0,180}?(-?[\d,]+(?:\.\d+)?)",
                r"\bEPS.{0,150}?(-?[\d,]+(?:\.\d+)?)",
            ],
            text,
        ),
        "pretax_million": first_number(
            [
                r"稅前(?:淨利|純益|損益).{0,180}?(-?[\d,]+(?:\.\d+)?)",
            ],
            text,
        ),
        "net_income_million": first_number(
            [
                r"(?:歸屬(?:於)?母公司(?:業主)?(?:淨利|損益)|"
                r"稅後(?:淨利|純益|損益)|本期淨利)"
                r".{0,180}?(-?[\d,]+(?:\.\d+)?)",
            ],
            text,
        ),
        "revenue_million": first_number(
            [
                r"(?:營業收入|營收).{0,180}?(-?[\d,]+(?:\.\d+)?)",
            ],
            text,
        ),
    }


class RowParser(HTMLParser):
    """
    把 MOPS 查詢結果中的每一列文字 + href/onclick/action
    全部保留下來，避免 detail button 不是 href 時抓不到。
    """

    def __init__(self):
        super().__init__()

        self.rows = []
        self.in_tr = False
        self.current_text = []
        self.current_attrs = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        if tag == "tr":
            self.in_tr = True
            self.current_text = []
            self.current_attrs = []

        if not self.in_tr:
            return

        attrs = dict(
            attrs
        )

        for key in (
            "href",
            "onclick",
            "action",
            "value",
        ):
            if attrs.get(key):
                self.current_attrs.append(
                    str(
                        attrs[key]
                    )
                )

    def handle_data(
        self,
        data,
    ):
        if self.in_tr:
            self.current_text.append(
                data
            )

    def handle_endtag(
        self,
        tag,
    ):
        if (
            tag == "tr"
            and self.in_tr
        ):
            text = norm_text(
                " ".join(
                    self.current_text
                )
            )

            if text:
                self.rows.append(
                    {
                        "text": text,
                        "attrs": list(
                            self.current_attrs
                        ),
                    }
                )

            self.in_tr = False
            self.current_text = []
            self.current_attrs = []


def mops_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/129.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": (
            "zh-TW,zh;q=0.9,en;q=0.6"
        ),
        "Referer": (
            "https://mops.twse.com.tw/"
            "mops/web/t05st01"
        ),
    }


def fetch_mops(
    base,
    payload,
):
    url = (
        base
        + MOPS_AJAX_PATH
    )

    # MOPS 常以 POST 查詢
    r = S.post(
        url,
        data=payload,
        headers=mops_headers(),
        timeout=45,
    )

    r.raise_for_status()

    if (
        not r.encoding
        or r.encoding.lower()
        == "iso-8859-1"
    ):
        r.encoding = (
            r.apparent_encoding
            or "utf-8"
        )

    return r.text


def parse_rows(
    html_text,
):
    parser = RowParser()
    parser.feed(
        html_text
    )

    return parser.rows


def query_payloads(
    iso_date,
    keyword,
):
    dt = datetime.strptime(
        iso_date,
        "%Y-%m-%d",
    )

    roc_year = (
        dt.year
        - 1911
    )

    month = str(
        dt.month
    )

    day = str(
        dt.day
    )

    # MOPS 歷年有多個表單欄位名稱
    # 同時嘗試新舊兩種搜尋格式
    return [
        {
            "firstin": "1",
            "step": "1",
            "off": "1",
            "TYPEK": "all",
            "year": str(
                roc_year
            ),
            "month": month,
            "b_date": day,
            "e_date": day,
            "keyword4": keyword,
            "queryName": "co_id",
            "co_id": "",
        },
        {
            "firstin": "1",
            "step": "1",
            "TYPEK": "all",
            "year": str(
                roc_year
            ),
            "month": month,
            "b_date": day,
            "e_date": day,
            "keyWord": keyword,
            "Condition2": "",
            "keyWord2": "",
        },
        {
            "firstin": "1",
            "step": "1",
            "TYPEK": "all",
            "year": str(
                roc_year
            ),
            "month1": month,
            "b_date": day,
            "e_date": day,
            "keyWord": keyword,
            "KIND": "all",
        },
    ]


def extract_detail_params(
    attrs,
    ticker,
    publish_date,
    publish_time,
):
    blob = " ".join(
        attrs or []
    )

    params = {
        "firstin": "1",
        "TYPEK": "all",
        "step": "2",
        "co_id": ticker,
    }

    # URL query string
    for m in re.finditer(
        r"https?://[^'\"\s]+",
        blob,
    ):
        try:
            qs = parse_qs(
                urlparse(
                    html.unescape(
                        m.group(0)
                    )
                ).query
            )

            for key in (
                "seq_no",
                "spoke_time",
                "spoke_date",
                "skey",
                "TYPEK",
                "off",
            ):
                if qs.get(key):
                    params[key] = (
                        qs[key][0]
                    )
        except Exception:
            pass

    # onclick / javascript 內的 key=value
    for key in (
        "seq_no",
        "spoke_time",
        "spoke_date",
        "skey",
        "TYPEK",
        "off",
    ):
        if key in params:
            continue

        m = re.search(
            rf"{key}\s*=\s*['\"]?([^&'\"\s,)]+)",
            blob,
            re.I,
        )

        if m:
            params[key] = (
                m.group(1)
            )

    # 日期/時間 fallback
    if (
        "spoke_date"
        not in params
    ):
        params[
            "spoke_date"
        ] = publish_date.replace(
            "-",
            "",
        )

    if (
        "spoke_time"
        not in params
        and publish_time
    ):
        params[
            "spoke_time"
        ] = publish_time.replace(
            ":",
            "",
        )

    return params


def fetch_detail(
    params,
):
    for base in MOPS_BASES:
        try:
            text = fetch_mops(
                base,
                params,
            )

            clean = norm_text(
                re.sub(
                    r"<[^>]+>",
                    " ",
                    text,
                )
            )

            if (
                any(
                    anchor
                    in clean
                    for anchor
                    in FINANCIAL_ANCHORS
                )
                or "注意交易資訊標準"
                in clean
            ):
                return (
                    clean,
                    base
                    + MOPS_AJAX_PATH
                    + "?"
                    + urlencode(
                        params
                    ),
                    "",
                )

        except Exception as e:
            last_error = repr(
                e
            )

    return (
        "",
        "",
        locals().get(
            "last_error",
            "",
        ),
    )


def parse_candidate_row(
    row,
    source_keyword,
):
    text = row.get(
        "text",
        "",
    )

    if not (
        source_keyword
        in text
        or subject_is_candidate(
            text
        )
    ):
        return None

    ticker_m = re.search(
        r"(?<!\d)(\d{4})(?!\d)",
        text,
    )

    if not ticker_m:
        return None

    ticker = (
        ticker_m.group(1)
    )

    if not ordinary_ticker(
        ticker
    ):
        return None

    # 日期
    date_m = re.search(
        r"(?:(20\d{2})|(\d{2,3}))[/-](\d{1,2})[/-](\d{1,2})",
        text,
    )

    if date_m:
        publish_date = (
            roc_to_iso(
                date_m.group(0)
            )
        )
    else:
        publish_date = (
            now_tpe()
            .date()
            .isoformat()
        )

    if (
        publish_date
        < MONITOR_START_DATE
    ):
        return None

    # 時間
    time_m = re.search(
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?",
        text,
    )

    publish_time = (
        clean_time(
            time_m.group(0)
        )
        if time_m
        else ""
    )

    # 公司名稱：通常代號後面第一段
    after = text[
        ticker_m.end():
    ].strip()

    name = ""

    if after:
        name = re.split(
            r"\s+|"
            r"(?:20\d{2}|\d{2,3})[/-]\d{1,2}[/-]\d{1,2}",
            after,
            maxsplit=1,
        )[0].strip(
            "｜| "
        )

    # 主旨：從第一個關鍵字附近往前取完整列
    subject = text

    detail_params = (
        extract_detail_params(
            row.get(
                "attrs",
                [],
            ),
            ticker,
            publish_date,
            publish_time,
        )
    )

    detail, source_url, detail_error = (
        fetch_detail(
            detail_params
        )
    )

    full_text = "\n".join(
        x
        for x in (
            subject,
            detail,
        )
        if x
    )

    return {
        "market": "",
        "ticker": ticker,
        "name": clean_name(
            name
        ),
        "publish_date": (
            publish_date
        ),
        "publish_time": (
            publish_time
        ),
        "subject": subject,
        "detail": detail,
        "source": (
            "mops_ajax"
        ),
        "source_url": (
            source_url
        ),
        "source_error": (
            detail_error
        ),
        "match_reason": (
            "attention_trading"
            if "注意交易資訊標準"
            in full_text
            else "direct_self_report"
        ),
        **extract_metrics(
            full_text
        ),
    }


def fetch_mops_search():
    """
    直接查 MOPS ajax_t05st01
    不再抓首頁 HTML
    """

    today = (
        now_tpe()
        .date()
        .isoformat()
    )

    keywords = (
        "注意交易資訊標準",
        "自結",
        "財務業務資訊",
    )

    raw_rows = []
    debug = []

    for keyword in keywords:
        got_keyword = False

        for base in MOPS_BASES:
            for payload in query_payloads(
                today,
                keyword,
            ):
                try:
                    html_text = (
                        fetch_mops(
                            base,
                            payload,
                        )
                    )

                    rows = parse_rows(
                        html_text
                    )

                    hits = [
                        r
                        for r in rows
                        if keyword
                        in r.get(
                            "text",
                            "",
                        )
                    ]

                    debug.append(
                        {
                            "base": base,
                            "keyword": keyword,
                            "rows": len(
                                rows
                            ),
                            "hits": len(
                                hits
                            ),
                        }
                    )

                    if hits:
                        raw_rows.extend(
                            (
                                keyword,
                                r,
                            )
                            for r in hits
                        )

                        got_keyword = True
                        break

                except Exception as e:
                    debug.append(
                        {
                            "base": base,
                            "keyword": keyword,
                            "error": repr(
                                e
                            ),
                        }
                    )

            if got_keyword:
                break

    items = {}
    rejected = []

    for keyword, row in raw_rows:
        x = parse_candidate_row(
            row,
            keyword,
        )

        if not x:
            rejected.append(
                {
                    "keyword": keyword,
                    "text": (
                        row.get(
                            "text",
                            "",
                        )[:300]
                    ),
                }
            )
            continue

        key = (
            x["ticker"],
            x[
                "publish_date"
            ],
            x[
                "publish_time"
            ],
        )

        # 同檔同時間只留一筆
        items[key] = x

    return {
        "ok": True,
        "rows": len(
            raw_rows
        ),
        "items": list(
            items.values()
        ),
        "debug": debug,
        "rejected": rejected[
            :20
        ],
        "error": "",
    }


def row_all_text(
    row,
):
    parts = []

    if isinstance(
        row,
        dict,
    ):
        for key, value in (
            row.items()
        ):
            if isinstance(
                value,
                (
                    str,
                    int,
                    float,
                ),
            ):
                v = norm_text(
                    value
                )

                if v:
                    parts.append(
                        f"{norm_text(key)} {v}"
                    )

    return "\n".join(
        parts
    )


def fetch_openapi(
    market,
    url,
):
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
            "rows": [],
            "items": [],
            "error": repr(
                e
            ),
        }

    if isinstance(
        arr,
        dict,
    ):
        arr = (
            arr.get("data")
            or arr.get(
                "records"
            )
            or arr.get(
                "result"
            )
            or []
        )

    if not isinstance(
        arr,
        list,
    ):
        return {
            "market": market,
            "ok": False,
            "rows": [],
            "items": [],
            "error": (
                "response is not list"
            ),
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

        if not ordinary_ticker(
            ticker
        ):
            continue

        subject = norm_text(
            p(
                r,
                [
                    "主旨",
                    "主旨 ",
                    "Subject",
                ],
                "",
            )
        )

        if not subject_is_candidate(
            subject
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

        if (
            not publish_date
            or publish_date
            < MONITOR_START_DATE
        ):
            continue

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

        full_text = "\n".join(
            [
                subject,
                row_all_text(
                    r
                ),
            ]
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
                "publish_date": (
                    publish_date
                ),
                "publish_time": (
                    publish_time
                ),
                "subject": subject,
                "detail": full_text,
                "source": (
                    f"{market}_openapi"
                ),
                "source_url": "",
                "source_error": "",
                "match_reason": (
                    "attention_trading"
                    if "注意交易資訊標準"
                    in subject
                    else "direct_self_report"
                ),
                **extract_metrics(
                    full_text
                ),
            }
        )

    return {
        "market": market,
        "ok": True,
        "rows": arr,
        "items": items,
        "error": "",
    }


def identity(
    x,
):
    return "|".join(
        [
            str(
                x.get(
                    "ticker"
                )
                or ""
            ),
            str(
                x.get(
                    "publish_date"
                )
                or ""
            ),
            str(
                x.get(
                    "publish_time"
                )
                or ""
            ),
            re.sub(
                r"\s+",
                "",
                str(
                    x.get(
                        "subject"
                    )
                    or ""
                ),
            ),
        ]
    )


def merge_item(
    old,
    new,
):
    out = dict(
        old
    )

    for k, v in (
        new.items()
    ):
        if (
            v
            not in (
                None,
                "",
                [],
                {},
            )
            and out.get(k)
            in (
                None,
                "",
                [],
                {},
            )
        ):
            out[k] = v

    if (
        new.get("source")
        == "mops_ajax"
    ):
        for k in (
            "name",
            "subject",
            "detail",
            "source",
            "source_url",
            "match_reason",
        ):
            if new.get(k):
                out[k] = (
                    new[k]
                )

    for k in (
        "eps",
        "pretax_million",
        "net_income_million",
        "revenue_million",
    ):
        if (
            new.get(k)
            is not None
        ):
            out[k] = (
                new[k]
            )

    return out


def send_pushover(
    title,
    message,
    url,
):
    token = os.getenv(
        "PUSHOVER_APP_TOKEN",
        "",
    ).strip()

    user = os.getenv(
        "PUSHOVER_USER_KEY",
        "",
    ).strip()

    if not token or not user:
        print(
            "pushover secrets missing; skip"
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
                "url": url,
                "url_title": (
                    "開啟這筆自結"
                ),
            },
            timeout=30,
        )

        r.raise_for_status()
        return True

    except Exception as e:
        print(
            "pushover failed",
            repr(e),
        )
        return False


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
            "telegram secrets missing; skip"
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
                "reply_markup": (
                    json.dumps(
                        {
                            "inline_keyboard": [
                                [
                                    {
                                        "text": "開啟台股市場監測",
                                        "url": url,
                                    }
                                ]
                            ]
                        },
                        ensure_ascii=False,
                    )
                ),
            },
            timeout=30,
        )

        r.raise_for_status()

        return bool(
            r.json()
            .get(
                "ok"
            )
        )

    except Exception as e:
        print(
            "telegram failed",
            repr(e),
        )
        return False


def push_text(
    x,
):
    lines = [
        (
            f"{x.get('name') or x['ticker']} "
            f"{x['ticker']}"
        ),
        (
            x.get("subject")
            or "公布自結財務資訊"
        ),
    ]

    if (
        x.get("eps")
        is not None
    ):
        lines.append(
            f"EPS {x['eps']:.2f} 元"
        )

    if (
        x.get(
            "pretax_million"
        )
        is not None
    ):
        lines.append(
            "稅前淨利 "
            f"{x['pretax_million']:.0f} 百萬"
        )

    if (
        x.get(
            "net_income_million"
        )
        is not None
    ):
        lines.append(
            "稅後／歸母淨利 "
            f"{x['net_income_million']:.0f} 百萬"
        )

    return "\n".join(
        lines
    )


def main():
    history_path = (
        ROOT
        / "data/self_reports_history.json"
    )

    sent_path = (
        ROOT
        / "data/self_reports_sent.json"
    )

    old = load_json(
        history_path,
        {},
    )

    saved = {}

    for x in old.get(
        "items",
        [],
    ):
        if str(
            x.get(
                "publish_date"
            )
            or ""
        ) < MONITOR_START_DATE:
            continue

        saved[
            identity(x)
        ] = x

    try:
        mops = (
            fetch_mops_search()
        )

        print(
            "MOPS AJAX",
            "rows",
            mops.get(
                "rows"
            ),
            "self_reports",
            len(
                mops.get(
                    "items",
                    [],
                )
            ),
        )

    except Exception as e:
        mops = {
            "ok": False,
            "rows": 0,
            "items": [],
            "debug": [],
            "rejected": [],
            "error": repr(
                e
            ),
        }

        print(
            "MOPS AJAX failed",
            repr(e),
        )

    twse_result = (
        fetch_openapi(
            "twse",
            TWSE_NEWS,
        )
    )

    tpex_result = (
        fetch_openapi(
            "tpex",
            TPEX_NEWS,
        )
    )

    fresh_map = {}

    for source in (
        mops,
        twse_result,
        tpex_result,
    ):
        for x in source.get(
            "items",
            [],
        ):
            key = identity(
                x
            )

            if key in fresh_map:
                fresh_map[
                    key
                ] = merge_item(
                    fresh_map[
                        key
                    ],
                    x,
                )
            else:
                fresh_map[
                    key
                ] = x

    fresh = list(
        fresh_map.values()
    )

    for x in fresh:
        key = identity(
            x
        )

        if key in saved:
            saved[
                key
            ] = merge_item(
                saved[key],
                x,
            )
        else:
            saved[
                key
            ] = x

    items = list(
        saved.values()
    )

    items.sort(
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

    sent_data = load_json(
        sent_path,
        {},
    )

    pushover_sent = set(
        sent_data.get(
            "ids",
            [],
        )
    )

    telegram_sent = set(
        sent_data.get(
            "telegram_ids",
            [],
        )
    )

    for x in fresh:
        key = identity(
            x
        )

        page_url = (
            SITE_URL
            + "?"
            + urlencode(
                {
                    "page": "selfReports",
                    "ticker": (
                        x.get(
                            "ticker"
                        )
                        or ""
                    ),
                    "date": (
                        x.get(
                            "publish_date"
                        )
                        or ""
                    ),
                    "time": (
                        x.get(
                            "publish_time"
                        )
                        or ""
                    ),
                }
            )
        )

        title = (
            "自結公布"
        )

        msg = push_text(
            x
        )

        if (
            key
            not in pushover_sent
        ):
            if send_pushover(
                title,
                msg,
                page_url,
            ):
                pushover_sent.add(
                    key
                )

        if (
            key
            not in telegram_sent
        ):
            if send_telegram(
                title,
                msg,
                page_url,
            ):
                telegram_sent.add(
                    key
                )

    updated_at = (
        now_tpe()
        .isoformat(
            timespec="minutes"
        )
    )

    save_json(
        history_path,
        {
            "updated_at": (
                updated_at
            ),
            "version": (
                VERSION
            ),
            "monitor_start_date": (
                MONITOR_START_DATE
            ),
            "items": items,
        },
    )

    save_json(
        sent_path,
        {
            "updated_at": (
                updated_at
            ),
            "ids": list(
                pushover_sent
            )[-2000:],
            "telegram_ids": list(
                telegram_sent
            )[-2000:],
        },
    )

    save_json(
        ROOT
        / "data/self_reports.json",
        {
            "updated_at": (
                updated_at
            ),
            "monitor_start_date": (
                MONITOR_START_DATE
            ),
            "filter_version": (
                VERSION
            ),
            "source_mode": (
                "MOPS ajax_t05st01 關鍵字查詢主來源 + "
                "TWSE/TPEx OpenAPI 備援"
            ),
            "source_status": {
                "mops": {
                    "ok": (
                        mops.get(
                            "ok",
                            False,
                        )
                    ),
                    "rows": (
                        mops.get(
                            "rows",
                            0,
                        )
                    ),
                    "self_reports": len(
                        mops.get(
                            "items",
                            [],
                        )
                    ),
                    "debug": (
                        mops.get(
                            "debug",
                            [],
                        )
                    ),
                    "rejected": (
                        mops.get(
                            "rejected",
                            [],
                        )
                    ),
                    "error": (
                        mops.get(
                            "error",
                            "",
                        )
                    ),
                },
                "twse": {
                    "ok": (
                        twse_result.get(
                            "ok",
                            False,
                        )
                    ),
                    "rows": len(
                        twse_result.get(
                            "rows",
                            [],
                        )
                    ),
                    "self_reports": len(
                        twse_result.get(
                            "items",
                            [],
                        )
                    ),
                    "error": (
                        twse_result.get(
                            "error",
                            "",
                        )
                    ),
                },
                "tpex": {
                    "ok": (
                        tpex_result.get(
                            "ok",
                            False,
                        )
                    ),
                    "rows": len(
                        tpex_result.get(
                            "rows",
                            [],
                        )
                    ),
                    "self_reports": len(
                        tpex_result.get(
                            "items",
                            [],
                        )
                    ),
                    "error": (
                        tpex_result.get(
                            "error",
                            "",
                        )
                    ),
                },
            },
            "items": items,
        },
    )

    print(
        "self reports",
        "stored",
        len(
            items
        ),
        "fresh",
        len(
            fresh
        ),
        "version",
        VERSION,
    )


if __name__ == "__main__":
    main()
