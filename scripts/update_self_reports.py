from sources import *
import os
import re
import time
from datetime import timedelta
from html.parser import HTMLParser


TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"

MOPS_LIST_URLS = (
    "https://mops.twse.com.tw/mops/web/ajax_t05st01",
    "https://mopsov.twse.com.tw/mops/web/ajax_t05st01",
)

MOPS_DETAIL_URLS = (
    "https://mops.twse.com.tw/mops/web/t05st01",
    "https://mopsov.twse.com.tw/mops/web/t05st01",
)

VERSION = "2026-09-26-v4-mops-get"

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


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data:
            self.parts.append(data)

    def text(self):
        return " ".join(self.parts)


class TableParser(HTMLParser):
    """
    解析 MOPS 重大訊息清單。
    保留列內 href / onclick，方便取 co_id / spoke_date / spoke_time / seq_no。
    """
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
                self.rows.append(
                    {
                        "cells": self.cells[:],
                        "attrs": " ".join(self.attr_parts),
                    }
                )

            self.in_tr = False
            self.cells = []
            self.attr_parts = []


def text_only(raw):
    p = _TextParser()

    try:
        p.feed(str(raw or ""))
    except Exception:
        pass

    return re.sub(
        r"\s+",
        " ",
        p.text()
    ).strip()


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

    digits = re.sub(
        r"\D",
        "",
        raw
    )

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

    digits = re.sub(
        r"\D",
        "",
        raw
    )

    if not digits:
        return ""

    digits = digits.zfill(6)[-6:]

    return (
        f"{digits[:2]}:"
        f"{digits[2:4]}:"
        f"{digits[4:6]}"
    )


def norm_text(s):
    return (
        str(s or "")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("　", " ")
        .strip()
    )


def p(row, names, default=""):
    return pick(
        row,
        names,
        default
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
            + r".{0,100}?"
            + r"-?\d+(?:\.\d+)?",
            text,
            re.I | re.S,
        )
    )


def is_self_report(subject, detail):
    subject = norm_text(subject)
    detail = norm_text(detail)

    if not subject_looks_like_self_report(
        subject
    ):
        return False

    text = (
        f"{subject}\n{detail}"
    )

    signals = sum(
        1
        for anchor in FINANCIAL_ANCHORS
        if has_number_near_anchor(
            text,
            anchor
        )
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
                r"每股盈餘.{0,80}?(-?\d+(?:\.\d+)?)",
                r"\bEPS.{0,50}?(-?\d+(?:\.\d+)?)",
            ],
            text,
        ),
        "pretax_million": first_number(
            [
                r"稅前(?:淨利|純益|損益).{0,80}?(-?\d+(?:\.\d+)?)",
            ],
            text,
        ),
        "net_income_million": first_number(
            [
                r"(?:歸屬母公司(?:業主)?(?:淨利|損益)|稅後(?:淨利|純益|損益)|本期淨利).{0,80}?(-?\d+(?:\.\d+)?)",
            ],
            text,
        ),
        "revenue_million": first_number(
            [
                r"(?:營業收入|營收).{0,80}?(-?\d+(?:\.\d+)?)",
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


def get_mops(urls, params, timeout=45):
    last = None

    for url in urls:
        try:
            r = S.get(
                url,
                params=params,
                headers=mops_headers(),
                timeout=timeout,
            )

            r.raise_for_status()

            txt = r.text

            if (
                txt
                and len(txt) > 300
                and "查詢過於頻繁" not in txt
                and "系統忙碌" not in txt
                and "error.html" not in str(r.url)
            ):
                return txt, str(r.url)

            last = RuntimeError(
                f"empty/blocked MOPS page: {r.url}"
            )

        except Exception as e:
            last = e

        time.sleep(1.0)

    raise RuntimeError(
        f"MOPS GET failed: {last}"
    )


def parse_params(blob):
    def one(name):
        pats = (
            rf"{name}=([^&'\"\s)>]+)",
            rf"{name}\s*=\s*['\"]?([^'\"&\s)>]+)",
        )

        for pat in pats:
            m = re.search(
                pat,
                blob,
                re.I
            )

            if m:
                return m.group(1).strip()

        return ""

    return {
        "co_id": one("co_id"),
        "spoke_date": one("spoke_date"),
        "spoke_time": one("spoke_time"),
        "seq_no": one("seq_no"),
    }


def parse_list_row(row, day, market):
    cells = row["cells"]
    attrs = row["attrs"]

    blob = (
        attrs
        + " "
        + " ".join(cells)
    )

    params = parse_params(
        blob
    )

    ticker = str(
        params.get("co_id")
        or ""
    ).strip()

    if not ordinary_ticker(
        ticker
    ):
        for cell in cells:
            if re.fullmatch(
                r"\d{4}",
                cell.strip()
            ):
                ticker = cell.strip()
                break

    if not ordinary_ticker(
        ticker
    ):
        return None

    publish_date = roc_to_iso(
        params.get("spoke_date")
    )

    if not publish_date:
        for cell in cells:
            d = roc_to_iso(cell)

            if d:
                publish_date = d
                break

    publish_time = clean_time(
        params.get("spoke_time")
    )

    if not publish_time:
        for cell in cells:
            if re.fullmatch(
                r"\d{1,2}:\d{2}(?::\d{2})?",
                cell.strip()
            ):
                publish_time = clean_time(
                    cell
                )
                break

    if (
        publish_date
        and publish_date != day.isoformat()
    ):
        return None

    name = ""

    for i, cell in enumerate(cells):
        if (
            cell.strip() == ticker
            and i + 1 < len(cells)
        ):
            cand = cells[
                i + 1
            ].strip()

            if cand:
                name = clean_name(
                    cand
                )

                break

    candidates = [
        c.strip()
        for c in cells
        if c.strip()
        and c.strip() != ticker
        and c.strip() != name
    ]

    strong = [
        c
        for c in candidates
        if subject_looks_like_self_report(
            c
        )
    ]

    if strong:
        subject = max(
            strong,
            key=len
        )

    else:
        subject = (
            max(
                candidates,
                key=len
            )
            if candidates
            else ""
        )

    if not subject_looks_like_self_report(
        subject
    ):
        return None

    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "publish_date": (
            publish_date
            or day.isoformat()
        ),
        "publish_time": publish_time,
        "subject": subject,
        "seq_no": params.get(
            "seq_no"
        ) or "1",
        "spoke_date": (
            params.get(
                "spoke_date"
            )
            or day.strftime("%Y%m%d")
        ),
        "spoke_time": (
            params.get(
                "spoke_time"
            )
            or publish_time.replace(":", "")
        ),
    }


def fetch_mops_detail(item, roc_year):
    params = {
        "encodeURIComponent": "1",
        "firstin": "true",
        "b_date": "",
        "e_date": "",
        "TYPEK": "all",
        "month": "all",
        "type": "",
        "e_month": "all",
        "step": "2",
        "off": "1",
        "co_id": item["ticker"],
        "spoke_date": (
            item.get("spoke_date")
            or item["publish_date"].replace("-", "")
        ),
        "spoke_time": (
            item.get("spoke_time")
            or item.get("publish_time", "").replace(":", "")
        ),
        "seq_no": item.get(
            "seq_no"
        ) or "1",
        "year": str(
            roc_year
        ),
    }

    try:
        raw, url = get_mops(
            MOPS_DETAIL_URLS,
            params,
            timeout=40
        )

        return (
            text_only(raw),
            url
        )

    except Exception as e:
        print(
            "MOPS detail fail",
            item["ticker"],
            item.get("publish_date"),
            repr(e)
        )

        return "", ""


def fetch_mops_history_day(day):
    """
    v4 重點：
    - 改用 GET，符合 MOPS 歷史重大訊息既有 URL 形式
    - TYPEK 分 sii / otc 查，避免 TYPEK=all 在歷史頁回空
    - year 用民國年，month 用實際月份，b_date/e_date 用日
    """
    roc_year = (
        day.year - 1911
    )

    all_candidates = []

    for typek, market in (
        ("sii", "twse"),
        ("otc", "tpex"),
    ):
        params = {
            "firstin": "1",
            "TYPEK": typek,
            "co_id": "",
            "year": str(
                roc_year
            ),
            "month": str(
                day.month
            ),
            "b_date": str(
                day.day
            ),
            "e_date": str(
                day.day
            ),
        }

        try:
            raw, final_url = get_mops(
                MOPS_LIST_URLS,
                params,
                timeout=60
            )

        except Exception as e:
            print(
                "MOPS history list fail",
                day.isoformat(),
                typek,
                repr(e)
            )
            continue

        parser = TableParser()

        try:
            parser.feed(
                raw
            )

        except Exception as e:
            print(
                "MOPS table parse fail",
                day.isoformat(),
                typek,
                repr(e)
            )
            continue

        raw_row_count = len(
            parser.rows
        )

        accepted_candidates = 0

        for row in parser.rows:
            item = parse_list_row(
                row,
                day,
                market
            )

            if not item:
                continue

            item[
                "list_source_url"
            ] = final_url

            all_candidates.append(
                item
            )

            accepted_candidates += 1

        print(
            "MOPS list",
            day.isoformat(),
            typek,
            "rows",
            raw_row_count,
            "self_candidates",
            accepted_candidates,
        )

        time.sleep(0.6)

    dedup = {}

    for x in all_candidates:
        key = (
            x["ticker"],
            x.get(
                "publish_date",
                ""
            ),
            x.get(
                "publish_time",
                ""
            ),
            re.sub(
                r"\s+",
                "",
                x.get(
                    "subject",
                    ""
                )
            ),
        )

        dedup[
            key
        ] = x

    out = []

    for item in dedup.values():
        detail, detail_url = (
            fetch_mops_detail(
                item,
                roc_year
            )
        )

        if not detail:
            continue

        if not is_self_report(
            item.get(
                "subject",
                ""
            ),
            detail
        ):
            continue

        metrics = extract_metrics(
            detail
        )

        uid = "|".join(
            [
                "mops_history",
                item["market"],
                item["ticker"],
                item.get(
                    "publish_date",
                    ""
                ),
                item.get(
                    "publish_time",
                    ""
                ),
                item.get(
                    "subject",
                    ""
                ),
            ]
        )

        out.append(
            {
                "id": uid,
                "market": (
                    item["market"]
                ),
                "ticker": (
                    item["ticker"]
                ),
                "name": (
                    item.get(
                        "name",
                        ""
                    )
                ),
                "publish_date": (
                    item.get(
                        "publish_date",
                        ""
                    )
                ),
                "publish_time": (
                    item.get(
                        "publish_time",
                        ""
                    )
                ),
                "subject": (
                    item.get(
                        "subject",
                        ""
                    )
                ),
                "detail": (
                    detail
                ),
                "source": (
                    "mops_history"
                ),
                "source_url": (
                    detail_url
                ),
                **metrics,
            }
        )

        time.sleep(
            0.25
        )

    print(
        "MOPS history",
        day.isoformat(),
        "candidates",
        len(dedup),
        "accepted",
        len(out),
    )

    return out


def fetch_current_openapi():
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
                "self report OpenAPI fail",
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

            uid = "|".join(
                [
                    "openapi",
                    market,
                    ticker,
                    publish_date,
                    publish_time,
                    subject,
                ]
            )

            out.append(
                {
                    "id": uid,
                    "market": (
                        market
                    ),
                    "ticker": (
                        ticker
                    ),
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
                    "source": (
                        "openapi"
                    ),
                    **metrics,
                }
            )

    return out


def merge_identity(x):
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
            "pushover secrets missing; skip push"
        )

        return False

    try:
        r = S.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": (
                    token
                ),
                "user": (
                    user
                ),
                "title": (
                    title
                ),
                "message": (
                    message
                ),
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
            x.get(
                "subject"
            )
            or "公布自結財務資訊"
        ),
    ]

    if x.get(
        "eps"
    ) is not None:
        lines.append(
            f"EPS "
            f"{x['eps']:.2f} 元"
        )

    if x.get(
        "pretax_million"
    ) is not None:
        lines.append(
            "稅前淨利 "
            f"{x['pretax_million']:.0f} 百萬"
        )

    if x.get(
        "net_income_million"
    ) is not None:
        lines.append(
            "稅後／歸母淨利 "
            f"{x['net_income_million']:.0f} 百萬"
        )

    return "\n".join(
        lines
    )


def enrich_name_market(items):
    master = load_json(
        ROOT
        / "data/master.json",
        {}
    )

    if isinstance(
        master,
        dict
    ):
        stock_map = (
            master.get(
                "stocks"
            )
            if isinstance(
                master.get(
                    "stocks"
                ),
                dict
            )
            else master
        )

    else:
        stock_map = {}

    for x in items:
        m = stock_map.get(
            x.get(
                "ticker"
            ),
            {}
        )

        if not x.get(
            "name"
        ):
            x[
                "name"
            ] = clean_name(
                m.get(
                    "name",
                    ""
                )
            )

        if not x.get(
            "market"
        ):
            x[
                "market"
            ] = (
                m.get(
                    "market",
                    ""
                )
            )

    return items


def main():
    today = now_tpe().date()

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

    merged = {}

    for x in old.get(
        "items",
        []
    ):
        d = str(
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

        merged[
            merge_identity(x)
        ] = x

    current = (
        fetch_current_openapi()
    )

    for x in current:
        d = (
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
            merged[
                merge_identity(x)
            ] = x

    history_fresh = []

    day = monday

    while day <= friday:
        if day <= today:
            rows = (
                fetch_mops_history_day(
                    day
                )
            )

            history_fresh.extend(
                rows
            )

            for x in rows:
                merged[
                    merge_identity(x)
                ] = x

            time.sleep(
                0.8
            )

        day += timedelta(
            days=1
        )

    items = enrich_name_market(
        list(
            merged.values()
        )
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

    push_candidates = {}

    for x in (
        current
        + history_fresh
    ):
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

        key = merge_identity(
            x
        )

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
            sent.add(
                key
            )

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
            "version": (
                VERSION
            ),
            "items": (
                items
            ),
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
                "OpenAPI 即時 + MOPS 歷史重大訊息 GET 回補"
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
        "history_new",
        len(history_fresh),
        "version",
        VERSION,
    )


if __name__ == "__main__":
    main()
