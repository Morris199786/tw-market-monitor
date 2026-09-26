from sources import *
import os
import re
import time
from datetime import timedelta
from html.parser import HTMLParser


TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"

VERSION = "2026-09-26-v5-self-report-plus-history"

MOPS_BASES = (
    "https://mops.twse.com.tw",
    "https://mopsov.twse.com.tw",
)

SELF_REPORT_PATHS = (
    "/mops/web/t05st08_all",
    "/mops/web/ajax_t05st08_all",
)

HISTORY_PATHS = (
    "/mops/web/t05st01",
    "/mops/web/ajax_t05st01",
)

STRONG_SUBJECT_KEYWORDS = (
    "自結",
    "財務業務資訊",
    "近期財務資訊",
    "近期財務業務資訊",
    "最近一月",
    "最近一季",
)

NOTICE_SUBJECT_KEYWORDS = (
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
    "薪資報酬委員",
    "審計委員",
)


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.in_tr = False
        self.in_cell = False
        self.cells = []
        self.cell_parts = []
        self.attr_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag == "tr":
            self.in_tr = True
            self.cells = []
            self.attr_parts = []

        if self.in_tr:
            for k, v in attrs:
                if v:
                    self.attr_parts.append(f"{k}={v}")

        if tag in ("td", "th") and self.in_tr:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data):
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in ("td", "th") and self.in_cell:
            txt = re.sub(
                r"\s+",
                " ",
                "".join(self.cell_parts)
            ).strip()

            self.cells.append(txt)
            self.in_cell = False
            self.cell_parts = []

        elif tag == "tr" and self.in_tr:
            if self.cells:
                self.rows.append({
                    "cells": self.cells[:],
                    "attrs": " ".join(self.attr_parts),
                })

            self.in_tr = False
            self.cells = []
            self.attr_parts = []


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data:
            self.parts.append(data)

    def text(self):
        return re.sub(
            r"\s+",
            " ",
            " ".join(self.parts)
        ).strip()


def html_text(raw):
    p = TextParser()

    try:
        p.feed(str(raw or ""))
    except Exception:
        pass

    return p.text()


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
        return (
            f"{digits[:4]}-"
            f"{digits[4:6]}-"
            f"{digits[6:8]}"
        )

    if len(digits) == 7:
        try:
            y = int(digits[:3]) + 1911

            return (
                f"{y:04d}-"
                f"{digits[3:5]}-"
                f"{digits[5:7]}"
            )
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

    return (
        f"{digits[:2]}:"
        f"{digits[2:4]}:"
        f"{digits[4:6]}"
    )


def subject_looks_like_self_report(subject):
    subject = norm_text(subject)

    if any(
        k in subject
        for k in EXCLUDE_SUBJECT_KEYWORDS
    ):
        return False

    return (
        any(
            k in subject
            for k in STRONG_SUBJECT_KEYWORDS
        )
        or any(
            k in subject
            for k in NOTICE_SUBJECT_KEYWORDS
        )
    )


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
    subject = norm_text(subject)
    detail = norm_text(detail)

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


def first_number(patterns, text):
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


def mops_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def mops_multi_request(paths, params, label, timeout=50):
    """
    MOPS 新舊頁面可能要求 GET 或 POST。
    v5 同一組參數依序嘗試 GET / POST、主站 / mopsov、一般頁 / ajax。
    成功條件不是 HTTP 200 而已，還要有實際 HTML 內容。
    """
    attempts = []

    for base in MOPS_BASES:
        for path in paths:
            url = base + path

            for method in ("get", "post"):
                try:
                    if method == "get":
                        r = S.get(
                            url,
                            params=params,
                            headers=mops_headers(),
                            timeout=timeout,
                        )
                    else:
                        r = S.post(
                            url,
                            data=params,
                            headers=mops_headers(),
                            timeout=timeout,
                        )

                    attempts.append(
                        f"{method.upper()} {r.status_code} {r.url}"
                    )

                    r.raise_for_status()

                    txt = r.text or ""

                    if (
                        len(txt) > 500
                        and "error.html" not in str(r.url)
                        and "查詢過於頻繁" not in txt
                        and "系統忙碌" not in txt
                    ):
                        print(
                            "MOPS request ok",
                            label,
                            method,
                            len(txt),
                            str(r.url)[:220]
                        )

                        return txt, str(r.url)

                except Exception as e:
                    attempts.append(
                        f"{method.upper()} ERR {url} {repr(e)}"
                    )

                time.sleep(0.4)

    print(
        "MOPS request exhausted",
        label,
        attempts[-6:]
    )

    return "", ""


def parse_ticker_name(cells):
    ticker = ""
    name = ""

    for i, cell in enumerate(cells):
        c = cell.strip()

        if re.fullmatch(r"\d{4}", c):
            ticker = c

            if i + 1 < len(cells):
                cand = cells[i + 1].strip()

                if cand:
                    name = clean_name(cand)

            break

    return ticker, name


def parse_date_time_from_cells(cells):
    date = ""
    tm = ""

    for cell in cells:
        if not date:
            d = roc_to_iso(cell)

            if d:
                date = d

        if not tm and re.search(
            r"\d{1,2}:\d{2}(?::\d{2})?",
            cell
        ):
            tm = clean_time(cell)

    return date, tm


def best_subject(cells):
    strong = [
        c.strip()
        for c in cells
        if c.strip()
        and subject_looks_like_self_report(c)
    ]

    if strong:
        return max(
            strong,
            key=len
        )

    text_candidates = [
        c.strip()
        for c in cells
        if len(c.strip()) >= 10
    ]

    if text_candidates:
        return max(
            text_candidates,
            key=len
        )

    return ""


def parse_self_report_summary_html(raw, month_start, month_end):
    """
    自結損益公告彙總表本身可能直接含數字，因此不一定要再點 detail。
    """
    parser = TableParser()

    try:
        parser.feed(raw)
    except Exception:
        return []

    out = []

    for row in parser.rows:
        cells = row["cells"]

        ticker, name = parse_ticker_name(
            cells
        )

        if not ordinary_ticker(ticker):
            continue

        row_text = " | ".join(cells)

        # 彙總表若沒有主旨，就自行生成一個穩定主旨
        subject = best_subject(cells)

        if not subject_looks_like_self_report(subject):
            subject = "自結損益公告"

        # 日期可能是公告日期，也可能只有資料年月
        publish_date, publish_time = (
            parse_date_time_from_cells(cells)
        )

        # 彙總表沒有公告日的資料，不強塞進本週
        if publish_date:
            if not (
                month_start
                <= publish_date
                <= month_end
            ):
                continue

        detail = row_text

        # 只收真的有獲利/EPS數字的列
        if not is_self_report(
            subject,
            detail
        ):
            continue

        metrics = extract_metrics(
            detail
        )

        out.append({
            "id": "|".join(
                [
                    "mops_self_report",
                    ticker,
                    publish_date,
                    publish_time,
                    subject,
                ]
            ),
            "market": "",
            "ticker": ticker,
            "name": name,
            "publish_date": publish_date,
            "publish_time": publish_time,
            "subject": subject,
            "detail": detail,
            "source": "mops_self_report",
            **metrics,
        })

    return out


def fetch_self_report_summary(today):
    """
    官方 MOPS:
      單一公司 → 營運概況 → 自結損益公告
      route: t05st08_all

    v5 不再使用之前誤認的 t120sb02_q10。
    """
    roc_year = today.year - 1911

    variants = []

    for typek in ("sii", "otc"):
        variants.extend([
            {
                "firstin": "1",
                "TYPEK": typek,
                "year": str(roc_year),
                "month": str(today.month),
            },
            {
                "firstin": "true",
                "TYPEK": typek,
                "year": str(roc_year),
                "month": f"{today.month:02d}",
            },
            {
                "step": "1",
                "firstin": "1",
                "TYPEK": typek,
                "year": str(roc_year),
                "month": str(today.month),
                "co_id": "",
            },
        ])

    all_rows = []

    month_start = (
        f"{today.year:04d}-"
        f"{today.month:02d}-01"
    )

    month_end = (
        f"{today.year:04d}-"
        f"{today.month:02d}-31"
    )

    seen_html = set()

    for i, params in enumerate(variants, 1):
        raw, url = mops_multi_request(
            SELF_REPORT_PATHS,
            params,
            f"self-report-{i}",
            timeout=45,
        )

        if not raw:
            continue

        sig = (
            len(raw),
            raw[:120]
        )

        if sig in seen_html:
            continue

        seen_html.add(sig)

        rows = parse_self_report_summary_html(
            raw,
            month_start,
            month_end,
        )

        print(
            "MOPS self-report summary",
            i,
            "rows",
            len(rows),
            "url",
            url[:180],
        )

        all_rows.extend(
            rows
        )

    dedup = {}

    for x in all_rows:
        dedup[
            merge_identity(x)
        ] = x

    return list(
        dedup.values()
    )


def parse_history_html(raw, start_date, end_date):
    parser = TableParser()

    try:
        parser.feed(raw)
    except Exception:
        return []

    out = []

    for row in parser.rows:
        cells = row["cells"]

        ticker, name = parse_ticker_name(
            cells
        )

        if not ordinary_ticker(ticker):
            continue

        publish_date, publish_time = (
            parse_date_time_from_cells(cells)
        )

        if not publish_date:
            continue

        if not (
            start_date
            <= publish_date
            <= end_date
        ):
            continue

        subject = best_subject(
            cells
        )

        if not subject_looks_like_self_report(
            subject
        ):
            continue

        detail = " | ".join(
            cells
        )

        out.append({
            "ticker": ticker,
            "name": name,
            "publish_date": publish_date,
            "publish_time": publish_time,
            "subject": subject,
            "detail": detail,
            "source": "mops_history_list",
        })

    return out


def fetch_history_week(monday, friday):
    """
    官方 MOPS:
      重大訊息/公告 → 歷史重大訊息
      route: t05st01

    這邊專門補『注意交易而公布近期財務業務資訊』這種重大訊息。
    """
    roc_year = monday.year - 1911

    variants = []

    for typek in ("sii", "otc"):
        variants.extend([
            {
                "firstin": "1",
                "TYPEK": typek,
                "year": str(roc_year),
                "month": str(monday.month),
                "b_date": str(monday.day),
                "e_date": str(friday.day),
            },
            {
                "firstin": "true",
                "TYPEK": typek,
                "year": str(roc_year),
                "month": f"{monday.month:02d}",
                "b_date": f"{monday.day:02d}",
                "e_date": f"{friday.day:02d}",
                "co_id": "",
            },
            {
                "step": "1",
                "firstin": "1",
                "TYPEK": typek,
                "year": str(roc_year),
                "month": str(monday.month),
                "b_date": str(monday.day),
                "e_date": str(friday.day),
                "co_id": "",
                "type": "",
            },
        ])

    all_rows = []
    seen_html = set()

    for i, params in enumerate(variants, 1):
        raw, url = mops_multi_request(
            HISTORY_PATHS,
            params,
            f"history-{i}",
            timeout=45,
        )

        if not raw:
            continue

        sig = (
            len(raw),
            raw[:120]
        )

        if sig in seen_html:
            continue

        seen_html.add(sig)

        rows = parse_history_html(
            raw,
            monday.isoformat(),
            friday.isoformat(),
        )

        print(
            "MOPS history week",
            i,
            "rows",
            len(rows),
            "url",
            url[:180],
        )

        all_rows.extend(
            rows
        )

    dedup = {}

    for x in all_rows:
        dedup[
            merge_identity(x)
        ] = x

    return list(
        dedup.values()
    )


def fetch_current_openapi():
    out = []

    for market, url in (
        ("twse", TWSE_NEWS),
        ("tpex", TPEX_NEWS),
    ):
        try:
            arr = get_json(
                url,
                timeout=45
            )

        except Exception as e:
            print(
                "self report OpenAPI fail",
                market,
                repr(e)
            )
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

            metrics = extract_metrics(
                detail
            )

            out.append({
                "id": "|".join(
                    [
                        "openapi",
                        market,
                        ticker,
                        publish_date,
                        publish_time,
                        subject,
                    ]
                ),
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
                **metrics,
            })

    return out


def merge_identity(x):
    return "|".join(
        [
            str(
                x.get("ticker")
                or ""
            ),
            str(
                x.get("publish_date")
                or ""
            ),
            str(
                x.get("publish_time")
                or ""
            ),
            re.sub(
                r"\s+",
                "",
                str(
                    x.get("subject")
                    or ""
                )
            ),
        ]
    )


def week_bounds(date_obj):
    monday = (
        date_obj
        - timedelta(
            days=date_obj.weekday()
        )
    )

    friday = (
        monday
        + timedelta(days=4)
    )

    return (
        monday,
        friday
    )


def week_label(monday, friday):
    return (
        f"{monday.month}/{monday.day}"
        f"～"
        f"{friday.month}/{friday.day}"
    )


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
        (
            f"{x.get('name') or x['ticker']} "
            f"{x['ticker']}"
        ),
        (
            x.get("subject")
            or "公布自結財務資訊"
        ),
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


def enrich_name_market(items):
    master = load_json(
        ROOT / "data/master.json",
        {}
    )

    if isinstance(master, dict):
        stock_map = (
            master.get("stocks")
            if isinstance(
                master.get("stocks"),
                dict
            )
            else master
        )
    else:
        stock_map = {}

    for x in items:
        m = stock_map.get(
            x.get("ticker"),
            {}
        )

        if not x.get("name"):
            x["name"] = clean_name(
                m.get("name", "")
            )

        if not x.get("market"):
            x["market"] = (
                m.get("market", "")
            )

    return items


def main():
    today = now_tpe().date()

    monday, friday = (
        week_bounds(today)
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

    merged = {}

    # 先保留舊的本週正確資料
    for x in old.get(
        "items",
        []
    ):
        d = str(
            x.get("publish_date")
            or ""
        )

        if d and not (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            continue

        if not is_self_report(
            x.get("subject", ""),
            x.get("detail", "")
        ):
            continue

        merged[
            merge_identity(x)
        ] = x

    # 1) 即時 OpenAPI
    current = fetch_current_openapi()

    for x in current:
        d = (
            x.get("publish_date")
            or ""
        )

        if (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            merged[
                merge_identity(x)
            ] = x

    # 2) 官方自結損益公告專區
    self_report_rows = (
        fetch_self_report_summary(
            today
        )
    )

    for x in self_report_rows:
        d = (
            x.get("publish_date")
            or ""
        )

        # 有公告日期就限制本週
        if d and not (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            continue

        merged[
            merge_identity(x)
        ] = x

    # 3) 官方歷史重大訊息，補注意交易財務業務公告
    history_rows = (
        fetch_history_week(
            monday,
            friday
        )
    )

    # 歷史清單頁通常只有主旨，不一定含完整數字。
    # 先合併候選，若之後 OpenAPI/自結專區有同筆完整內容會覆蓋。
    for x in history_rows:
        merged[
            merge_identity(x)
        ] = x

    items = enrich_name_market(
        list(
            merged.values()
        )
    )

    # 最後只留下真正符合條件的完整資料
    final_items = []

    for x in items:
        if is_self_report(
            x.get("subject", ""),
            x.get("detail", "")
        ):
            final_items.append(x)

    items = final_items

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

    push_candidates = {}

    for x in (
        current
        + self_report_rows
    ):
        d = (
            x.get("publish_date")
            or ""
        )

        if d and not (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            continue

        key = merge_identity(x)

        if is_self_report(
            x.get("subject", ""),
            x.get("detail", "")
        ):
            push_candidates[
                key
            ] = x

    for key, x in push_candidates.items():
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
        hist_path,
        {
            "week_key": (
                current_key
            ),
            "updated_at": (
                updated_at
            ),
            "version": VERSION,
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
                sent
            )[-1000:],
        },
    )

    save_json(
        ROOT
        / "data/self_reports.json",
        {
            "updated_at": (
                updated_at
            ),
            "current_week_key": (
                current_key
            ),
            "current_week_label": (
                label
            ),
            "filter_version": (
                VERSION
            ),
            "source_mode": (
                "OpenAPI 即時 + MOPS 自結損益公告 t05st08_all + MOPS 歷史重大訊息 t05st01"
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
        "total",
        len(items),
        "openapi",
        len(current),
        "self_report_summary",
        len(self_report_rows),
        "history_candidates",
        len(history_rows),
        "version",
        VERSION,
    )


if __name__ == "__main__":
    main()
