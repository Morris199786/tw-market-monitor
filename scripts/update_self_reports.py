from sources import *
import json
import os
import re
import html
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin

VERSION = "2026-09-29-v10-mops-primary"

MOPS_HOME = "https://mops.twse.com.tw/mops/"
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

PROFIT_ANCHORS = (
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
    return f"{digits[:2]}:{digits[2:4]}:{digits[4:6]}"


def subject_excluded(subject):
    s = norm_text(subject)
    return any(k in s for k in EXCLUDE_SUBJECT_KEYWORDS)


def subject_is_candidate(subject):
    s = norm_text(subject)

    if not s or subject_excluded(s):
        return False

    return (
        any(k in s for k in ATTENTION_KEYWORDS)
        or any(k in s for k in SELF_REPORT_KEYWORDS)
    )


def has_number_near_anchor(text, anchor):
    return bool(
        re.search(
            re.escape(anchor)
            + r".{0,180}?"
            + r"-?\d[\d,]*(?:\.\d+)?",
            text,
            re.I | re.S,
        )
    )


def classify(subject, full_text):
    subject = norm_text(subject)
    text = norm_text(full_text)

    if subject_excluded(subject):
        return False, "excluded"

    if any(k in subject for k in ATTENTION_KEYWORDS):
        return True, "attention_trading"

    if any(k in subject for k in SELF_REPORT_KEYWORDS):
        if any(
            has_number_near_anchor(text, x)
            for x in PROFIT_ANCHORS
        ):
            return True, "direct_self_report_profit"

        signals = sum(
            1
            for x in FINANCIAL_ANCHORS
            if has_number_near_anchor(text, x)
        )

        if signals >= 2:
            return True, "direct_self_report_financials"

    return False, "not_self_report"


def first_number(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, re.I | re.S)

        if not m:
            continue

        raw = str(m.group(1)).replace(",", "").strip()
        return n(raw, None)

    return None


def extract_metrics(text):
    text = str(text or "").replace("，", ",")

    return {
        "eps": first_number(
            [
                r"每股(?:稅後)?盈餘.{0,150}?(-?[\d,]+(?:\.\d+)?)",
                r"\bEPS.{0,120}?(-?[\d,]+(?:\.\d+)?)",
            ],
            text,
        ),
        "pretax_million": first_number(
            [
                r"稅前(?:淨利|純益|損益).{0,150}?(-?[\d,]+(?:\.\d+)?)",
            ],
            text,
        ),
        "net_income_million": first_number(
            [
                r"(?:歸屬(?:於)?母公司(?:業主)?(?:淨利|損益)|"
                r"稅後(?:淨利|純益|損益)|本期淨利)"
                r".{0,150}?(-?[\d,]+(?:\.\d+)?)",
            ],
            text,
        ),
        "revenue_million": first_number(
            [
                r"(?:營業收入|營收).{0,150}?(-?[\d,]+(?:\.\d+)?)",
            ],
            text,
        ),
    }


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.in_tr = False
        self.in_cell = False
        self.current_row = []
        self.current_cell = []
        self.current_links = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_tr = True
            self.current_row = []

        elif tag in ("td", "th") and self.in_tr:
            self.in_cell = True
            self.current_cell = []
            self.current_links = []

        elif tag == "a" and self.in_cell:
            href = dict(attrs).get("href")
            if href:
                self.current_links.append(href)

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.current_row.append(
                {
                    "text": norm_text(" ".join(self.current_cell)),
                    "links": list(self.current_links),
                }
            )
            self.in_cell = False

        elif tag == "tr" and self.in_tr:
            if self.current_row:
                self.rows.append(self.current_row)

            self.in_tr = False
            self.current_row = []


def fetch_html(url, timeout=45):
    r = S.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.5",
        },
    )

    r.raise_for_status()

    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"

    return r.text


def parse_mops_latest():
    html_text = fetch_html(MOPS_HOME)

    parser = TableParser()
    parser.feed(html_text)

    items = []
    seen = set()

    for row in parser.rows:
        texts = [
            c["text"]
            for c in row
            if c["text"]
        ]

        if len(texts) < 3:
            continue

        ticker = ""
        ticker_idx = None

        for i, txt in enumerate(texts):
            if re.fullmatch(r"\d{4}", txt):
                ticker = txt
                ticker_idx = i
                break

        if not ticker or not ordinary_ticker(ticker):
            continue

        publish_date = ""
        publish_time = ""

        for txt in texts:
            if re.search(
                r"(?:20\d{2}|\d{2,3})[/-]\d{1,2}[/-]\d{1,2}",
                txt,
            ):
                publish_date = roc_to_iso(txt)
                publish_time = clean_time(txt)
                break

        if not publish_date or publish_date < MONITOR_START_DATE:
            continue

        subject = ""

        for txt in texts:
            if subject_is_candidate(txt):
                subject = txt
                break

        if not subject:
            continue

        name = ""

        if ticker_idx is not None and ticker_idx + 1 < len(texts):
            possible = texts[ticker_idx + 1]
            if not re.search(r"\d{1,2}:\d{2}", possible):
                name = possible

        detail_url = ""

        for cell in row:
            for href in cell.get("links", []):
                if (
                    "t05st02" in href
                    or "t05st01" in href
                    or "ajax" in href.lower()
                    or "mops" in href.lower()
                ):
                    detail_url = urljoin(
                        MOPS_HOME,
                        href,
                    )
                    break

            if detail_url:
                break

        key = (
            ticker,
            publish_date,
            publish_time,
            re.sub(r"\s+", "", subject),
        )

        if key in seen:
            continue

        seen.add(key)

        detail = ""
        detail_error = ""

        if detail_url:
            try:
                detail_html = fetch_html(
                    detail_url,
                    timeout=30,
                )

                detail = norm_text(
                    re.sub(
                        r"<[^>]+>",
                        " ",
                        detail_html,
                    )
                )

            except Exception as e:
                detail_error = repr(e)

        full_text = "\n".join(
            x
            for x in (
                subject,
                detail,
                " | ".join(texts),
            )
            if x
        )

        accepted, reason = classify(
            subject,
            full_text,
        )

        if not accepted:
            continue

        items.append(
            {
                "market": "",
                "ticker": ticker,
                "name": clean_name(name),
                "publish_date": publish_date,
                "publish_time": publish_time,
                "subject": subject,
                "detail": detail,
                "source": "mops",
                "source_url": detail_url,
                "source_error": detail_error,
                "match_reason": reason,
                **extract_metrics(full_text),
            }
        )

    return {
        "ok": True,
        "rows": len(parser.rows),
        "items": items,
        "error": "",
    }


def row_all_text(row):
    parts = []

    if isinstance(row, dict):
        for key, value in row.items():
            if isinstance(value, (str, int, float)):
                v = norm_text(value)

                if v:
                    parts.append(
                        f"{norm_text(key)} {v}"
                    )

    return "\n".join(parts)


def fetch_openapi(market, url):
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
            "error": repr(e),
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
            "rows": [],
            "items": [],
            "error": "response is not list",
        }

    items = []

    for r in arr:
        ticker = str(
            p(
                r,
                ["公司代號", "證券代號", "股票代號", "代號"],
                "",
            )
        ).strip()

        if not ordinary_ticker(ticker):
            continue

        subject = norm_text(
            p(
                r,
                ["主旨", "主旨 ", "Subject"],
                "",
            )
        )

        if not subject_is_candidate(subject):
            continue

        publish_date = roc_to_iso(
            p(
                r,
                ["發言日期", "公告日期", "出表日期"],
                "",
            )
        )

        if not publish_date or publish_date < MONITOR_START_DATE:
            continue

        publish_time = clean_time(
            p(
                r,
                ["發言時間", "公告時間"],
                "",
            )
        )

        full_text = "\n".join(
            [
                subject,
                norm_text(
                    p(
                        r,
                        ["說明", "Description", "內容"],
                        "",
                    )
                ),
                row_all_text(r),
            ]
        )

        accepted, reason = classify(
            subject,
            full_text,
        )

        if not accepted:
            continue

        items.append(
            {
                "market": market,
                "ticker": ticker,
                "name": clean_name(
                    p(
                        r,
                        ["公司名稱", "證券名稱", "名稱"],
                        "",
                    )
                ),
                "publish_date": publish_date,
                "publish_time": publish_time,
                "subject": subject,
                "detail": full_text,
                "source": f"{market}_openapi",
                "source_url": "",
                "source_error": "",
                "match_reason": reason,
                **extract_metrics(full_text),
            }
        )

    return {
        "market": market,
        "ok": True,
        "rows": arr,
        "items": items,
        "error": "",
    }


def identity(x):
    return "|".join(
        [
            str(x.get("ticker") or ""),
            str(x.get("publish_date") or ""),
            str(x.get("publish_time") or ""),
            re.sub(
                r"\s+",
                "",
                str(x.get("subject") or ""),
            ),
        ]
    )


def merge_item(old, new):
    out = dict(old)

    for k, v in new.items():
        if v not in (None, "", [], {}):
            if out.get(k) in (None, "", [], {}):
                out[k] = v

    if new.get("source") == "mops":
        for k in (
            "name",
            "subject",
            "detail",
            "source",
            "source_url",
            "match_reason",
        ):
            if new.get(k) not in (None, ""):
                out[k] = new[k]

    for k in (
        "eps",
        "pretax_million",
        "net_income_million",
        "revenue_million",
    ):
        if new.get(k) is not None:
            out[k] = new[k]

    return out


def send_pushover(title, message, url):
    token = os.getenv("PUSHOVER_APP_TOKEN", "").strip()
    user = os.getenv("PUSHOVER_USER_KEY", "").strip()

    if not token or not user:
        print("pushover secrets missing; skip")
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
                "url_title": "開啟這筆自結",
            },
            timeout=30,
        )

        r.raise_for_status()
        return True

    except Exception as e:
        print("pushover failed", repr(e))
        return False


def send_telegram(title, message, url):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("telegram secrets missing; skip")
        return False

    try:
        r = S.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": f"{title}\n{message}",
                "disable_web_page_preview": True,
                "reply_markup": json.dumps(
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
                ),
            },
            timeout=30,
        )

        r.raise_for_status()
        return bool(r.json().get("ok"))

    except Exception as e:
        print("telegram failed", repr(e))
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
            f"稅前淨利 {x['pretax_million']:.0f} 百萬"
        )

    if x.get("net_income_million") is not None:
        lines.append(
            f"稅後／歸母淨利 {x['net_income_million']:.0f} 百萬"
        )

    return "\n".join(lines)


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

    for x in old.get("items", []):
        if str(
            x.get("publish_date")
            or ""
        ) < MONITOR_START_DATE:
            continue

        saved[
            identity(x)
        ] = x

    try:
        mops = parse_mops_latest()

        print(
            "MOPS",
            "rows",
            mops.get("rows"),
            "self_reports",
            len(
                mops.get("items", [])
            ),
        )

    except Exception as e:
        mops = {
            "ok": False,
            "rows": 0,
            "items": [],
            "error": repr(e),
        }

        print(
            "MOPS failed",
            repr(e),
        )

    twse_result = fetch_openapi(
        "twse",
        TWSE_NEWS,
    )

    tpex_result = fetch_openapi(
        "tpex",
        TPEX_NEWS,
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
            key = identity(x)

            if key in fresh_map:
                fresh_map[key] = (
                    merge_item(
                        fresh_map[key],
                        x,
                    )
                )
            else:
                fresh_map[key] = x

    fresh = list(
        fresh_map.values()
    )

    for x in fresh:
        key = identity(x)

        if key in saved:
            saved[key] = merge_item(
                saved[key],
                x,
            )
        else:
            saved[key] = x

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

    if "telegram_ids" in sent_data:
        telegram_sent = set(
            sent_data.get(
                "telegram_ids",
                [],
            )
        )
    else:
        telegram_sent = set(
            pushover_sent
        )

    for x in fresh:
        key = identity(x)

        page_url = (
            SITE_URL
            + "?"
            + urlencode(
                {
                    "page": "selfReports",
                    "ticker": (
                        x.get("ticker")
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

        title = "自結公布"
        msg = push_text(x)

        if key not in pushover_sent:
            if send_pushover(
                title,
                msg,
                page_url,
            ):
                pushover_sent.add(
                    key
                )

        if key not in telegram_sent:
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
            "updated_at": updated_at,
            "version": VERSION,
            "monitor_start_date": (
                MONITOR_START_DATE
            ),
            "items": items,
        },
    )

    save_json(
        sent_path,
        {
            "updated_at": updated_at,
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
            "updated_at": updated_at,
            "monitor_start_date": (
                MONITOR_START_DATE
            ),
            "filter_version": VERSION,
            "source_mode": (
                "MOPS 即時重大訊息主來源 + "
                "TWSE/TPEx OpenAPI 備援 + "
                "注意交易資訊標準優先"
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
        len(items),
        "fresh",
        len(fresh),
        "version",
        VERSION,
    )


if __name__ == "__main__":
    main()
