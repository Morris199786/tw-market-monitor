from sources import *

import html
import json
import math
import os
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse

VERSION = "2026-09-29-v14-30min-dedup-filter"

MOPS_BASES = (
    "https://mops.twse.com.tw",
    "https://mopsov.twse.com.tw",
)

MOPS_AJAX_PATH = "/mops/web/ajax_t05st01"
TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"

MONITOR_START_DATE = "2026-09-26"
SITE_URL = "https://morris199786.github.io/tw-market-monitor/"

SEARCH_KEYWORDS = (
    "注意交易資訊標準",
    "自結",
    "財務業務資訊",
)

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


def norm_text(value):
    return re.sub(
        r"\s+",
        " ",
        html.unescape(
            str(value or "")
            .replace("\r", " ")
            .replace("\n", " ")
            .replace("　", " ")
        ),
    ).strip()


def compact_text(value):
    return re.sub(r"\s+", "", norm_text(value))


def roc_to_iso(value):
    raw = str(value or "").strip()

    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    m = re.search(r"(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{int(m.group(1)) + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    digits = re.sub(r"\D", "", raw)

    if len(digits) == 8 and digits.startswith("20"):
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"

    if len(digits) == 7:
        year = int(digits[:3]) + 1911
        return f"{year:04d}-{digits[3:5]}-{digits[5:7]}"

    return ""


def clean_time(value):
    raw = str(value or "").strip()

    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
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
    text = compact_text(subject)
    return any(compact_text(k) in text for k in EXCLUDE_SUBJECT_KEYWORDS)


def subject_is_candidate(subject):
    text = compact_text(subject)

    if not text or subject_excluded(subject):
        return False

    return (
        any(compact_text(k) in text for k in ATTENTION_KEYWORDS)
        or any(compact_text(k) in text for k in SELF_REPORT_KEYWORDS)
    )


def _number(raw, growth=False):
    raw = str(raw or "").strip().replace(",", "").replace(" ", "")
    if not growth and "%" in raw:
        return None

    raw = raw.rstrip("%")

    if re.fullmatch(r"\(\d+(?:\.\d+)?\)", raw):
        raw = "-" + raw[1:-1]

    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def extract_split_eps(text, out):
    """
    上櫃常見格式：
    (一)單月 ... 本期 / 去年同期 / YoY
    (二)單季 ... 本期 / 去年同期 / YoY
    """
    month_start = re.search(r"單月|最近一月", text)
    if not month_start:
        return None

    quarter_match = re.search(r"單季|最近一季", text[month_start.end():])
    if not quarter_match:
        return None

    qpos = month_start.end() + quarter_match.start()
    tail_end = re.search(r"最近四季累計", text[qpos:])

    sections = {
        "monthly": text[month_start.start():qpos],
        "quarter": (
            text[qpos:qpos + tail_end.start()]
            if tail_end
            else text[qpos:]
        ),
    }

    cell = (
        r"(?:[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*%?"
        r"|\(\s*\d+(?:\.\d+)?\s*\)\s*%?"
        r"|不適用|不適合|無法計算|由虧轉盈|由盈轉虧"
        r"|轉虧為盈|轉盈為虧|N/A|NA|--+|—|-)"
    )

    for kind, section in sections.items():
        eps = re.search(
            r"每股(?:稅後)?(?:盈餘|損益)|每股(?:基本)?盈餘|\bEPS\b",
            section,
            re.I,
        )
        if not eps:
            return None

        header = section[:eps.start()]
        if "去年" not in header or not re.search(r"增\s*減|成\s*長", header):
            return None

        if kind == "monthly":
            pattern = r"(?<!\d)(\d{3,4})(?:年\s*|/)(\d{1,2})(?:月|\b)"
        else:
            pattern = r"(?<!\d)(\d{3,4})年?\s*第?([1-4一二三四])季"

        dates = re.findall(pattern, header)
        if len(dates) != 2:
            return None

        year, period = dates[0]
        prior_year, prior_period = dates[1]

        period_cmp = {"一": "1", "二": "2", "三": "3", "四": "4"}.get(period, period)
        prior_cmp = {"一": "1", "二": "2", "三": "3", "四": "4"}.get(
            prior_period, prior_period
        )

        if int(year) - int(prior_year) != 1:
            return None
        if str(period_cmp).lstrip("0") != str(prior_cmp).lstrip("0"):
            return None

        year = int(year)
        if year < 1911:
            year += 1911

        if kind == "monthly":
            if not 1 <= int(period_cmp) <= 12:
                return None
            out["monthly_period"] = f"{year}-{int(period_cmp):02d}"
        else:
            out["quarter_period"] = f"{year}-Q{period_cmp}"

        tail = re.sub(
            r"^\s*[（(]?\s*元\s*[）)]?",
            "",
            section[eps.end():],
        )

        match = re.match(
            r"\s*(" + cell + r")"
            r"\s*(?:/\s*|\s+)(" + cell + r")"
            r"\s*(?:/\s*|\s+)(" + cell + r")(?=\s|$)",
            tail,
            re.I,
        )

        if not match:
            return None

        current, previous, yoy = match.groups()

        if "%" in current or "%" in previous:
            return None

        out[kind + "_eps"] = _number(current)
        out[kind + "_eps_yoy"] = _number(yoy, growth=True)
        out[kind + "_eps_yoy_text"] = yoy.strip()

    out["eps"] = out["monthly_eps"]
    out["eps_parse_status"] = (
        "parsed"
        if out["monthly_eps"] is not None and out["quarter_eps"] is not None
        else "partial"
    )
    return out


def extract_metrics(text):
    """
    只從官方公告中的 EPS 欄位取值
    不用營收、稅前淨利或四季累計數字替代 EPS
    """
    text = unicodedata.normalize("NFKC", html.unescape(str(text or "")))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("−", "-").replace("，", ",")

    out = dict.fromkeys(
        (
            "eps",
            "monthly_eps",
            "monthly_eps_yoy",
            "monthly_period",
            "quarter_eps",
            "quarter_eps_yoy",
            "quarter_period",
            "monthly_eps_yoy_text",
            "quarter_eps_yoy_text",
        )
    )
    out["eps_parse_status"] = "unrecognized_layout"

    split = extract_split_eps(text, dict(out))
    if split is not None:
        return split

    anchor = re.search(r"最近一[月季]|當月|單月", text)
    if not anchor:
        return out

    section = text[anchor.start():]

    eps = re.search(
        r"每股(?:稅後)?(?:盈餘|損益)|每股(?:基本)?盈餘|\bEPS\b",
        section,
        re.I,
    )
    if not eps:
        return out

    header = section[:eps.start()]

    month = re.search(
        r"(?<!\d)(\d{3,4})年\s*(\d{1,2})\s*月",
        header,
    )

    quarter = (
        re.search(
            r"(?<!\d)(\d{3,4})年\s*第?\s*([1-4一二三四])\s*季",
            header[month.end():],
        )
        if month
        else None
    )

    if not month or not quarter:
        return out

    if (
        header.count("去年") != 2
        or header.count("同期") != 2
        or not re.search(r"增\s*減|成\s*長", header)
    ):
        return out

    months = re.findall(r"\d{3,4}年\s*\d{1,2}\s*月", header)
    if len(months) != 1:
        return out

    def ad_year(value):
        value = int(value)
        return value + 1911 if value < 1911 else value

    q = {"一": "1", "二": "2", "三": "3", "四": "4"}.get(
        quarter[2],
        quarter[2],
    )

    out["monthly_period"] = f"{ad_year(month[1])}-{int(month[2]):02d}"
    out["quarter_period"] = f"{ad_year(quarter[1])}-Q{q}"

    tail = re.sub(
        r"^\s*[（(]?\s*元\s*[）)]?",
        "",
        section[eps.end():],
    )

    cell = (
        r"(?:[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*%?"
        r"|\(\s*\d+(?:\.\d+)?\s*\)\s*%?"
        r"|不適用|不適合|無法計算|由虧轉盈|由盈轉虧"
        r"|轉虧為盈|轉盈為虧|N/A|NA|--+|—|-)"
    )

    match = re.match(
        r"\s*(" + cell + r")"
        r"\s+(" + cell + r")"
        r"\s+(" + cell + r")"
        r"\s+(" + cell + r")(?=\s|$)",
        tail,
        re.I,
    )

    if not match:
        return out

    monthly_eps, monthly_yoy, quarter_eps, quarter_yoy = match.groups()

    out.update(
        monthly_eps=_number(monthly_eps),
        monthly_eps_yoy=_number(monthly_yoy, growth=True),
        quarter_eps=_number(quarter_eps),
        quarter_eps_yoy=_number(quarter_yoy, growth=True),
        monthly_eps_yoy_text=monthly_yoy.strip(),
        quarter_eps_yoy_text=quarter_yoy.strip(),
    )

    out["eps"] = out["monthly_eps"]
    out["eps_parse_status"] = (
        "parsed"
        if out["monthly_eps"] is not None and out["quarter_eps"] is not None
        else "partial"
    )

    return out


class RowParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.in_tr = False
        self.current_text = []
        self.current_attrs = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_tr = True
            self.current_text = []
            self.current_attrs = []

        if not self.in_tr:
            return

        attrs = dict(attrs)

        for key in ("href", "onclick", "action", "value"):
            if attrs.get(key):
                self.current_attrs.append(str(attrs[key]))

    def handle_data(self, data):
        if self.in_tr:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag != "tr" or not self.in_tr:
            return

        text = norm_text(" ".join(self.current_text))

        if text:
            self.rows.append(
                {
                    "text": text,
                    "attrs": list(self.current_attrs),
                }
            )

        self.in_tr = False
        self.current_text = []
        self.current_attrs = []


def mops_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/129.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6",
        "Referer": "https://mops.twse.com.tw/mops/web/t05st01",
    }


def fetch_mops(base, payload):
    response = S.post(
        base + MOPS_AJAX_PATH,
        data=payload,
        headers=mops_headers(),
        timeout=45,
    )
    response.raise_for_status()

    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"

    return response.text


def parse_rows(html_text):
    parser = RowParser()
    parser.feed(html_text)
    return parser.rows


def query_payloads(iso_date, keyword):
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    roc_year = dt.year - 1911
    month = str(dt.month)
    day = str(dt.day)

    return [
        {
            "firstin": "1",
            "step": "1",
            "off": "1",
            "TYPEK": "all",
            "year": str(roc_year),
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
            "year": str(roc_year),
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
            "year": str(roc_year),
            "month1": month,
            "b_date": day,
            "e_date": day,
            "keyWord": keyword,
            "KIND": "all",
        },
    ]


def extract_detail_params(attrs, ticker, publish_date, publish_time):
    blob = " ".join(attrs or [])

    params = {
        "firstin": "1",
        "TYPEK": "all",
        "step": "2",
        "co_id": ticker,
    }

    for match in re.finditer(r"https?://[^'\"\s]+", blob):
        try:
            qs = parse_qs(urlparse(html.unescape(match.group(0))).query)
            for key in (
                "seq_no",
                "spoke_time",
                "spoke_date",
                "skey",
                "TYPEK",
                "off",
            ):
                if qs.get(key):
                    params[key] = qs[key][0]
        except Exception:
            pass

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

        match = re.search(
            rf"{key}(?:\.value)?\s*=\s*['\"]?([^&'\"\s,)]+)",
            blob,
            re.I,
        )
        if match:
            params[key] = match.group(1)

    if "spoke_date" not in params:
        params["spoke_date"] = (
            f"{int(publish_date[:4]) - 1911}"
            f"{publish_date[5:7]}"
            f"{publish_date[8:10]}"
        )

    if "spoke_time" not in params and publish_time:
        params["spoke_time"] = publish_time.replace(":", "")

    return params


def fetch_detail(params):
    errors = []

    if not params.get("seq_no"):
        return "", "", "公告缺少 seq_no，未猜測公告序號"

    date = str(params.get("spoke_date", ""))

    if len(date) == 7:
        date = str(int(date[:3]) + 1911) + date[3:]

    payload = {
        "firstin": "true",
        "TYPEK": params.get("TYPEK", "all"),
        "step": "1",
        "COMPANY_ID": params["co_id"],
        "SPOKE_DATE": date,
        "SPOKE_TIME": params.get("spoke_time", ""),
        "SEQ_NO": params["seq_no"],
        "skey": (
            params.get("skey")
            or params["co_id"] + date + params["seq_no"]
        ),
    }

    for base in reversed(MOPS_BASES):
        url = base + "/mops/web/ajax_t05sr01_1"

        try:
            response = S.post(
                url,
                data=payload,
                headers=mops_headers(),
                timeout=(15, 45),
            )
            response.raise_for_status()

            if (
                not response.encoding
                or response.encoding.lower() == "iso-8859-1"
            ):
                response.encoding = response.apparent_encoding or "utf-8"

            clean = norm_text(re.sub(r"<[^>]+>", " ", response.text))

            roc_date = (
                f"{int(date[:4]) - 1911}/"
                f"{date[4:6]}/"
                f"{date[6:8]}"
            )

            spoke_time = payload["SPOKE_TIME"]
            time_text = ":".join(
                spoke_time[i:i + 2]
                for i in (0, 2, 4)
            )

            if (
                re.search(
                    r"每股(?:稅後)?(?:盈餘|損益)|每股(?:基本)?盈餘|\bEPS\b",
                    clean,
                    re.I,
                )
                and params["co_id"] in clean
                and roc_date in clean
                and (not spoke_time or time_text in clean)
            ):
                return clean, url + "?" + urlencode(payload), ""

            errors.append(base + ": 未取得含 EPS 的公告明細")

        except Exception as exc:
            errors.append(base + ": " + type(exc).__name__)

    return "", "", "; ".join(errors)


def parse_candidate_row(row, source_keyword):
    text = row.get("text", "")
    compact = compact_text(text)

    # 關鍵修正：MOPS 可能把「注意交易資訊標準」拆成多段
    # 所以所有關鍵字比對都先移除空白/換行
    if (
        compact_text(source_keyword) not in compact
        and not subject_is_candidate(text)
    ):
        return None

    ticker_match = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
    if not ticker_match:
        return None

    ticker = ticker_match.group(1)

    if not ordinary_ticker(ticker):
        return None

    # 純財務比率公告不是使用者要的 EPS 自結
    if (
        any(k in text for k in ("流動比率", "速動比率", "負債比率"))
        and "注意交易" not in compact
    ):
        return None

    date_match = re.search(
        r"(?:(20\d{2})|(\d{2,3}))[/-](\d{1,2})[/-](\d{1,2})",
        text,
    )

    publish_date = (
        roc_to_iso(date_match.group(0))
        if date_match
        else now_tpe().date().isoformat()
    )

    if publish_date < MONITOR_START_DATE:
        return None

    time_match = re.search(
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?",
        text,
    )
    publish_time = (
        clean_time(time_match.group(0))
        if time_match
        else ""
    )

    after = text[ticker_match.end():].strip()
    name = ""

    if after:
        name = re.split(
            r"\s+|(?:20\d{2}|\d{2,3})[/-]\d{1,2}[/-]\d{1,2}",
            after,
            maxsplit=1,
        )[0].strip("｜| ")

    subject = text

    detail_params = extract_detail_params(
        row.get("attrs", []),
        ticker,
        publish_date,
        publish_time,
    )

    detail, source_url, detail_error = fetch_detail(detail_params)

    full_text = "\n".join(
        value
        for value in (subject, detail)
        if value
    )

    full_compact = compact_text(full_text)

    return {
        "market": "",
        "ticker": ticker,
        "name": clean_name(name),
        "publish_date": publish_date,
        "publish_time": publish_time,
        "subject": subject,
        "detail": detail,
        "source": "mops_ajax",
        "source_url": source_url,
        "source_error": detail_error,
        "match_reason": (
            "attention_trading"
            if compact_text("注意交易資訊標準") in full_compact
            else "direct_self_report"
        ),
        **extract_metrics(full_text),
    }


def fetch_mops_search():
    today = now_tpe().date().isoformat()

    raw_rows = []
    debug = []

    for keyword in SEARCH_KEYWORDS:
        got_keyword = False

        for base in MOPS_BASES:
            for payload in query_payloads(today, keyword):
                try:
                    html_text = fetch_mops(base, payload)
                    rows = parse_rows(html_text)

                    # 關鍵修正：比對前去掉空白與換行
                    wanted = compact_text(keyword)
                    hits = [
                        row
                        for row in rows
                        if wanted in compact_text(row.get("text", ""))
                    ]

                    debug.append(
                        {
                            "base": base,
                            "keyword": keyword,
                            "rows": len(rows),
                            "hits": len(hits),
                        }
                    )

                    if hits:
                        raw_rows.extend((keyword, row) for row in hits)
                        got_keyword = True
                        break

                except Exception as exc:
                    debug.append(
                        {
                            "base": base,
                            "keyword": keyword,
                            "error": repr(exc),
                        }
                    )

            if got_keyword:
                break

    items = {}
    rejected = []

    for keyword, row in raw_rows:
        item = parse_candidate_row(row, keyword)

        if not item:
            rejected.append(
                {
                    "keyword": keyword,
                    "text": row.get("text", "")[:300],
                }
            )
            continue

        key = (
            item["ticker"],
            item["publish_date"],
            item["publish_time"],
        )
        items[key] = item

    return {
        "ok": True,
        "rows": len(raw_rows),
        "items": list(items.values()),
        "debug": debug,
        "rejected": rejected[:20],
        "error": "",
    }


def row_all_text(row):
    parts = []

    if isinstance(row, dict):
        for key, value in row.items():
            if isinstance(value, (str, int, float)):
                value = norm_text(value)
                if value:
                    parts.append(f"{norm_text(key)} {value}")

    return "\n".join(parts)


def fetch_openapi(market, url):
    try:
        rows = get_json(
            url,
            timeout=45,
            tries=5,
        )
    except Exception as exc:
        return {
            "market": market,
            "ok": False,
            "rows": [],
            "items": [],
            "error": repr(exc),
        }

    if isinstance(rows, dict):
        rows = (
            rows.get("data")
            or rows.get("records")
            or rows.get("result")
            or []
        )

    if not isinstance(rows, list):
        return {
            "market": market,
            "ok": False,
            "rows": [],
            "items": [],
            "error": "response is not list",
        }

    items = []

    for row in rows:
        ticker = str(
            p(
                row,
                ["公司代號", "證券代號", "股票代號", "代號"],
                "",
            )
        ).strip()

        if not ordinary_ticker(ticker):
            continue

        subject = norm_text(
            p(
                row,
                ["主旨", "主旨 ", "Subject"],
                "",
            )
        )

        if not subject_is_candidate(subject):
            continue

        publish_date = roc_to_iso(
            p(
                row,
                ["發言日期", "公告日期", "出表日期"],
                "",
            )
        )

        if not publish_date or publish_date < MONITOR_START_DATE:
            continue

        publish_time = clean_time(
            p(
                row,
                ["發言時間", "公告時間"],
                "",
            )
        )

        full_text = "\n".join(
            [
                subject,
                row_all_text(row),
            ]
        )

        items.append(
            {
                "market": market,
                "ticker": ticker,
                "name": clean_name(
                    p(
                        row,
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
                "match_reason": (
                    "attention_trading"
                    if compact_text("注意交易資訊標準")
                    in compact_text(subject)
                    else "direct_self_report"
                ),
                **extract_metrics(full_text),
            }
        )

    return {
        "market": market,
        "ok": True,
        "rows": rows,
        "items": items,
        "error": "",
    }


def identity(item):
    return "|".join(
        [
            str(item.get("ticker") or ""),
            str(item.get("publish_date") or ""),
            str(item.get("publish_time") or ""),
            compact_text(item.get("subject") or ""),
        ]
    )


def merge_item(old, new):
    out = dict(old)

    for key, value in new.items():
        if (
            value not in (None, "", [], {})
            and out.get(key) in (None, "", [], {})
        ):
            out[key] = value

    if new.get("source") == "mops_ajax":
        for key in (
            "name",
            "subject",
            "detail",
            "source",
            "source_url",
            "match_reason",
        ):
            if new.get(key):
                out[key] = new[key]

    for key in (
        "monthly_eps",
        "monthly_eps_yoy",
        "monthly_period",
        "quarter_eps",
        "quarter_eps_yoy",
        "quarter_period",
        "monthly_eps_yoy_text",
        "quarter_eps_yoy_text",
        "eps_parse_status",
        "eps",
        "pretax_million",
        "net_income_million",
        "revenue_million",
    ):
        if new.get(key) is not None:
            out[key] = new[key]

    return out


def send_pushover(title, message, url):
    token = os.getenv("PUSHOVER_APP_TOKEN", "").strip()
    user = os.getenv("PUSHOVER_USER_KEY", "").strip()

    if not token or not user:
        print("pushover secrets missing; skip")
        return False

    try:
        response = S.post(
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
        response.raise_for_status()
        return True
    except Exception as exc:
        print("pushover failed", repr(exc))
        return False


def send_telegram(title, message, url):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print("telegram secrets missing; skip")
        return False

    try:
        response = S.post(
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
        response.raise_for_status()
        return bool(response.json().get("ok"))
    except Exception as exc:
        print("telegram failed", repr(exc))
        return False


def eps_line(item, kind):
    period = item.get(kind + "_period")
    label = (
        period + (" 單月 EPS" if kind == "monthly" else " 上一季 EPS")
        if period
        else ("單月 EPS" if kind == "monthly" else "上一季 EPS")
    )

    value = item.get(kind + "_eps")
    growth = item.get(kind + "_eps_yoy")

    value_text = f"{value:.2f} 元" if value is not None else "未取得"

    growth_text = (
        f"{growth:+.2f}%"
        if growth is not None
        else item.get(kind + "_eps_yoy_text") or "未取得"
    )

    return f"{label}：{value_text}｜與去年同期增減：{growth_text}"


def push_text(item):
    return "\n".join(
        [
            f"{item.get('name') or item['ticker']} {item['ticker']}",
            eps_line(item, "monthly"),
            eps_line(item, "quarter"),
        ]
    )


def valid_eps_item(item):
    return (
        item.get("monthly_eps") is not None
        and item.get("quarter_eps") is not None
    )


def main():
    history_path = ROOT / "data/self_reports_history.json"
    sent_path = ROOT / "data/self_reports_sent.json"

    old = load_json(history_path, {})
    saved = {}

    for item in old.get("items", []):
        if str(item.get("publish_date") or "") < MONITOR_START_DATE:
            continue
        saved[identity(item)] = item

    try:
        mops = fetch_mops_search()
        print(
            "MOPS AJAX",
            "rows",
            mops.get("rows"),
            "self_reports",
            len(mops.get("items", [])),
        )
    except Exception as exc:
        mops = {
            "ok": False,
            "rows": 0,
            "items": [],
            "debug": [],
            "rejected": [],
            "error": repr(exc),
        }
        print("MOPS AJAX failed", repr(exc))

    twse_result = fetch_openapi("twse", TWSE_NEWS)
    tpex_result = fetch_openapi("tpex", TPEX_NEWS)

    fresh_map = {}

    for source in (mops, twse_result, tpex_result):
        for item in source.get("items", []):
            key = identity(item)

            if key in fresh_map:
                fresh_map[key] = merge_item(fresh_map[key], item)
            else:
                fresh_map[key] = item

    fresh = list(fresh_map.values())

    for item in fresh:
        key = identity(item)

        if key in saved:
            saved[key] = merge_item(saved[key], item)
        else:
            saved[key] = item

    items = list(saved.values())

    # 每次都用 detail 重新解析，避免沿用舊版錯位的 EPS
    for item in items:
        parsed = extract_metrics(item.get("detail") or "")
        item.update(parsed)

    # 網站只呈現真正有「單月 EPS + 上一季 EPS」的公告
    # 因此寶得利這類純流動比率／負債比率公告會被排除
    items = [item for item in items if valid_eps_item(item)]

    items.sort(
        key=lambda item: (
            item.get("publish_date", ""),
            item.get("publish_time", ""),
            item.get("ticker", ""),
        ),
        reverse=True,
    )

    sent_data = load_json(sent_path, {})

    pushover_sent = set(sent_data.get("ids", []))
    telegram_sent = set(sent_data.get("telegram_ids", []))

    for item in fresh:
        # 推播也只送有完整兩個 EPS 欄位的新公告
        if not valid_eps_item(item):
            continue

        base_key = identity(item)

        # 舊版曾把格式版本放進 key
        # 為避免升級後把已推過的舊公告重送，保留 legacy key 相容判斷
        legacy_key = base_key + "|period-eps-yoy-v1"

        page_url = (
            SITE_URL
            + "?"
            + urlencode(
                {
                    "page": "selfReports",
                    "ticker": item.get("ticker") or "",
                    "date": item.get("publish_date") or "",
                    "time": item.get("publish_time") or "",
                }
            )
        )

        title = "自結公布"
        message = push_text(item)

        if (
            base_key not in pushover_sent
            and legacy_key not in pushover_sent
        ):
            if send_pushover(title, message, page_url):
                pushover_sent.add(base_key)

        if (
            base_key not in telegram_sent
            and legacy_key not in telegram_sent
        ):
            if send_telegram(title, message, page_url):
                telegram_sent.add(base_key)

    updated_at = now_tpe().isoformat(timespec="minutes")

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
            "ids": list(pushover_sent)[-2000:],
            "telegram_ids": list(telegram_sent)[-2000:],
        },
    )

    save_json(
        ROOT / "data/self_reports.json",
        {
            "updated_at": updated_at,
            "monitor_start_date": MONITOR_START_DATE,
            "filter_version": VERSION,
            "source_mode": (
                "MOPS ajax_t05st01 關鍵字查詢主來源 + "
                "TWSE/TPEx OpenAPI 備援"
            ),
            "source_status": {
                "mops": {
                    "ok": mops.get("ok", False),
                    "rows": mops.get("rows", 0),
                    "self_reports": len(mops.get("items", [])),
                    "debug": mops.get("debug", []),
                    "rejected": mops.get("rejected", []),
                    "error": mops.get("error", ""),
                },
                "twse": {
                    "ok": twse_result.get("ok", False),
                    "rows": len(twse_result.get("rows", [])),
                    "self_reports": len(twse_result.get("items", [])),
                    "error": twse_result.get("error", ""),
                },
                "tpex": {
                    "ok": tpex_result.get("ok", False),
                    "rows": len(tpex_result.get("rows", [])),
                    "self_reports": len(tpex_result.get("items", [])),
                    "error": tpex_result.get("error", ""),
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
