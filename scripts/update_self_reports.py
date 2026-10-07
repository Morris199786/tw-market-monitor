from sources import *

import html
import json
import math
import os
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse

VERSION = "2026-10-07-v29-direct-self-report-prev-quarter-eps"

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
    "注意交易",
    "財務業務",
    "近期財務",
    "自結",
    "自行結算",
    "自行結算損益",
)

SELF_REPORT_KEYWORDS = (
    "自結",
    "自行結算",
    "自行結算損益",
    "自結損益",
    "財務業務資訊",
    "相關財務業務",
    "近期財務資訊",
    "近期財務業務資訊",
    "最近一月",
    "最近一個月",
    "最近一季",
    "最近一個季",
    "單月",
    "單季",
)

ATTENTION_KEYWORDS = (
    "公布注意交易資訊標準",
    "達公布注意交易資訊標準",
    "達注意交易資訊標準",
    "多次達公布注意交易資訊標準",
    "有價證券達公布注意交易資訊標準",
    "注意交易資訊標準",
    "注意交易",
)

EXCLUDE_SUBJECT_KEYWORDS = (
    "股票面額", "面額變更", "除權", "除息", "股利", "現金股利",
    "盈餘分配", "董事會", "股東會", "法說會", "法人說明會",
    "增資", "減資", "現金增資", "可轉換公司債", "可轉債",
    "公司債", "私募", "庫藏股", "取得或處分資產", "背書保證",
    "資金貸與", "關係人交易", "更換會計師", "簽證會計師",
    "發言人", "代理發言人", "董事辭任", "獨立董事",
)

MONTH_WORD = r"(?:最近一(?:個)?月|單月|當月|本月)"
QUARTER_WORD = r"(?:最近一(?:個)?季|單季|本季)"
EPS_WORD = r"(?:每股(?:稅後)?(?:盈餘|損益)|每股(?:基本)?盈餘|EPS)(?:\s*[（(]\s*(?:元|新台幣元)\s*[）)])?"

CELL = (
    r"(?:[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*%?"
    r"|\(\s*\d+(?:\.\d+)?\s*\)\s*%?"
    r"|不適用|不適合|無法計算|由虧轉盈|由盈轉虧"
    r"|轉虧為盈|轉盈為虧|虧損減少|虧損增加|N/?A|--+|—|-)"
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


def normalize_for_parse(value):
    text = unicodedata.normalize("NFKC", html.unescape(str(value or "")))
    text = re.sub(r"<[^>]+>", " ", text)
    return (
        text.replace("−", "-")
        .replace("–", "-")
        .replace("，", ",")
        .replace("％", "%")
        .replace("：", ":")
        .replace("／", "/")
    )


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
        return f"{int(digits[:3]) + 1911:04d}-{digits[3:5]}-{digits[5:7]}"
    return ""


def clean_time(value):
    raw = str(value or "").strip()
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}:{int(m.group(3) or 0):02d}"
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    digits = digits.zfill(6)[-6:]
    return f"{digits[:2]}:{digits[2:4]}:{digits[4:6]}"


def subject_excluded(subject):
    text = compact_text(subject)
    return any(compact_text(k) in text for k in EXCLUDE_SUBJECT_KEYWORDS)


def direct_self_report_subject(subject):
    text = compact_text(subject)

    if not text or subject_excluded(subject):
        return False

    return bool(
        re.search(r"(?:自行結算|自結).{0,16}損益", text)
        or re.search(r"損益.{0,16}(?:自行結算|自結)", text)
    )


def subject_is_candidate(subject):
    text = compact_text(subject)

    if not text or subject_excluded(subject):
        return False

    return (
        direct_self_report_subject(subject)
        or any(compact_text(k) in text for k in ATTENTION_KEYWORDS)
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


def _ad_year(year):
    year = int(year)
    return year + 1911 if year < 1911 else year


def _quarter_num(q):
    return {"一": "1", "二": "2", "三": "3", "四": "4"}.get(str(q), str(q))


def _empty_metrics():
    out = dict.fromkeys((
        "eps", "monthly_eps", "monthly_eps_yoy", "monthly_period",
        "quarter_eps", "quarter_eps_yoy", "quarter_period",
        "monthly_eps_yoy_text", "quarter_eps_yoy_text",
    ))
    out["eps_parse_status"] = "unrecognized_layout"
    out["eps_parse_reason"] = ""
    return out


def _find_month_period(text):
    patterns = (
        r"(?<!\d)(\d{2,4})\s*年\s*(\d{1,2})\s*月",
        r"(?<!\d)(\d{2,4})\s*[/\.]\s*(\d{1,2})(?!\s*/\s*\d)",
        r"(?<!\d)(20\d{2})[-/](\d{1,2})(?![-/]\d)",
    )
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            month = int(m.group(2))
            if 1 <= month <= 12:
                return f"{_ad_year(m.group(1))}-{month:02d}"
    return None


def _find_quarter_period(text):
    text = re.sub(
        r"\d{2,4}\s*年?\s*第?\s*[1-4一二三四]\s*季\s*(?:至|~|～)",
        "",
        text,
    )

    patterns = (
        r"(?<!\d)(\d{2,4})\s*年?\s*第?\s*([1-4一二三四])\s*季",
        r"(?<!\d)(20\d{2})\s*[.]?\s*Q\s*([1-4])",
        r"(?<!\d)(\d{2,3})\s*[.]?\s*Q\s*([1-4])",
    )

    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return f"{_ad_year(m.group(1))}-Q{_quarter_num(m.group(2))}"

    return None


def _eps_cells(section):
    """Read only adjacent EPS cells; never scan later notes for numbers."""
    m = re.search(EPS_WORD, section, re.I)

    if not m:
        return []

    tail = section[m.end():]
    tail = re.split(r"\s+[4-9]\s*[.、]\s*[^\d]", tail, maxsplit=1)[0]
    tail = re.sub(
        r"^\s*[（(]?\s*(?:元|新台幣元)\s*[）)]?\s*",
        "",
        tail,
    )
    tail = re.sub(r"^\s*[:：]\s*", "", tail)

    cells = []

    for _ in range(8):
        tail = tail.lstrip(" \t\r\n/|｜")
        token = re.match(CELL, tail, re.I)

        if not token:
            break

        cells.append(token.group(0).strip())
        tail = tail[token.end():]

    return cells


def _growth(raw):
    value = _number(raw, growth=True)
    return value, (
        raw.strip()
        if value is None or "%" in raw
        else f"{value:+.2f}%"
    )


def _extract_eps_triplet(section):
    vals = _eps_cells(section)

    if len(vals) < 3 or "%" in vals[0] or "%" in vals[1]:
        return None

    current = _number(vals[0])

    if current is None:
        return None

    yoy, label = _growth(vals[2])

    return current, _number(vals[1]), yoy, label


def _extract_mops_section_eps(section):
    return _extract_eps_triplet(section)


def _extract_horizontal_eps(text):
    vals = _eps_cells(text)

    if len(vals) in (4, 5):
        mi, my, qi, qy = 0, 1, 2, 3

    elif len(vals) in (6, 7):
        mi, my, qi, qy = 0, 2, 3, 5

    else:
        return None

    if _number(vals[mi]) is None or _number(vals[qi]) is None:
        return None

    month_yoy, month_label = _growth(vals[my])
    quarter_yoy, quarter_label = _growth(vals[qy])

    return {
        "monthly_eps": _number(vals[mi]),
        "monthly_eps_yoy": month_yoy,
        "monthly_eps_yoy_text": month_label,
        "quarter_eps": _number(vals[qi]),
        "quarter_eps_yoy": quarter_yoy,
        "quarter_eps_yoy_text": quarter_label,
    }


def _slice_semantic_sections(text):
    markers = []

    for kind, pattern in (
        ("monthly", MONTH_WORD),
        ("quarter", QUARTER_WORD),
    ):
        for m in re.finditer(pattern, text, re.I):
            markers.append((m.start(), kind))

    markers.sort()
    sections = {}

    for start, kind in markers:
        if kind in sections:
            continue

        end = len(text)

        for next_start, next_kind in markers:
            if next_start > start and next_kind != kind:
                end = next_start
                break

        section = text[start:end]

        cumulative = re.search(r"最近四季累計", section)

        if cumulative:
            section = section[:cumulative.start()]

        sections[kind] = section

    return sections


def _fallback_period_sections(text):
    month = re.search(
        r"(?<!\d)(?:\d{2,4}\s*年\s*\d{1,2}\s*月|20\d{2}[-/]\d{1,2})",
        text,
    )

    quarter = re.search(
        r"(?<!\d)(?:\d{2,4}\s*年\s*第?\s*[1-4一二三四]\s*季|20\d{2}\s*[.]?\s*Q\s*[1-4])",
        text,
        re.I,
    )

    sections = {}

    if month and quarter:
        if month.start() < quarter.start():
            sections["monthly"] = text[month.start():quarter.start()]
            sections["quarter"] = text[quarter.start():]

        else:
            sections["quarter"] = text[quarter.start():month.start()]
            sections["monthly"] = text[month.start():]

    return sections


def _extract_direct_self_report_metrics(text):
    """Only explicitly labelled single-month EPS; never use cumulative EPS.

    Voluntary disclosures need not include a previous quarter or YoY value.
    Missing values remain None and use the existing presentation rules.
    """
    normalized = normalize_for_parse(text)
    if not re.search(r"(?:自行結算|自結).{0,16}損益|損益.{0,16}(?:自行結算|自結)",
                     compact_text(normalized)):
        return None

    label = r"(?:每股(?:稅後)?(?:盈餘|損益)|每股(?:基本)?盈餘|EPS)"
    number = r"(\(?[+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\)?)"
    # Keep the month label adjacent to EPS: don't cross a net-income field,
    # a cumulative-period label, or another numeric item to find a value.
    patterns = (
        rf"(?:當月|本月|單月)\s*{label}\s*(?:\(元\)|元)?\s*(?:[:：]|為)?\s*{number}",
        rf"{label}\s*(?:\(元\)|元)?\s*(?:[:：])?\s*(?:當月|本月|單月)\s*(?:[:：]|為)?\s*{number}",
    )
    match = next((m for pattern in patterns
                  if (m := re.search(pattern, normalized, re.I))), None)
    if match is None:
        return None
    value = _number(match.group(1))
    if value is None:
        return None

    # Prefer the reporting month in the subject over the announcement date.
    period_match = re.search(
        r"(?:截至|本公司|公告)[^\n]{0,30}?((?:20\d{2}|\d{2,3})\s*年\s*\d{1,2}\s*月)",
        normalized,
    )
    period = _find_month_period(period_match.group(1)) if period_match else None
    if not period:
        period_match = re.search(r"(?:20\d{2}|\d{2,3})\s*年\s*\d{1,2}\s*月", normalized)
        period = _find_month_period(period_match.group()) if period_match else None

    return {"eps": value, "monthly_eps": value, "monthly_period": period}


def extract_metrics(text):
    text = normalize_for_parse(text)
    out = _empty_metrics()

    if not re.search(EPS_WORD, text, re.I):
        out["eps_parse_reason"] = "eps_label_not_found"
        return out

    sections = _slice_semantic_sections(text)

    if not sections.get("monthly") or not sections.get("quarter"):
        fallback = _fallback_period_sections(text)
        sections.setdefault("monthly", fallback.get("monthly"))
        sections.setdefault("quarter", fallback.get("quarter"))

    month_section = sections.get("monthly") or ""
    quarter_section = sections.get("quarter") or ""

    out["monthly_period"] = _find_month_period(month_section or text)
    out["quarter_period"] = _find_quarter_period(quarter_section or text)

    month_values = (
        _extract_eps_triplet(month_section)
        if month_section
        else None
    )

    quarter_values = (
        _extract_eps_triplet(quarter_section)
        if quarter_section
        else None
    )

    if month_values is None and month_section:
        month_values = _extract_mops_section_eps(month_section)

    if quarter_values is None and quarter_section:
        quarter_values = _extract_mops_section_eps(quarter_section)

    if month_values:
        out["monthly_eps"] = month_values[0]
        out["monthly_eps_yoy"] = month_values[2]
        out["monthly_eps_yoy_text"] = month_values[3]

    if quarter_values:
        out["quarter_eps"] = quarter_values[0]
        out["quarter_eps_yoy"] = quarter_values[2]
        out["quarter_eps_yoy_text"] = quarter_values[3]

    eps_marker = re.search(EPS_WORD, text, re.I)
    month_marker = re.search(MONTH_WORD, text, re.I)
    quarter_marker = re.search(QUARTER_WORD, text, re.I)

    shared_horizontal_eps_row = bool(
        eps_marker
        and month_marker
        and quarter_marker
        and month_marker.start() < eps_marker.start()
        and quarter_marker.start() < eps_marker.start()
    )

    if shared_horizontal_eps_row:
        for key in (
            "monthly_eps",
            "monthly_eps_yoy",
            "monthly_eps_yoy_text",
            "quarter_eps",
            "quarter_eps_yoy",
            "quarter_eps_yoy_text",
        ):
            out[key] = None

        header = text[month_marker.start():eps_marker.start()]

        header = re.sub(
            r"\d{2,4}\s*年?\s*第?\s*[1-4一二三四]\s*季\s*"
            r"(?:至|~|～)\s*"
            r"\d{2,4}\s*年?\s*第?\s*[1-4一二三四]\s*季",
            "",
            header,
        )

        out["monthly_period"] = _find_month_period(header)

        header = re.split(
            r"營業收入|營收",
            header,
            maxsplit=1,
        )[0]

        quarters = re.findall(
            r"(?<!\d)(\d{2,4})\s*年?\s*第?\s*([1-4一二三四])\s*季",
            header,
        )

        out["quarter_period"] = (
            max(
                f"{_ad_year(y)}-Q{_quarter_num(q)}"
                for y, q in quarters
            )
            if quarters
            else _find_quarter_period(header)
        )

    if shared_horizontal_eps_row:
        horizontal = _extract_horizontal_eps(text)

        if horizontal:
            for key, value in horizontal.items():
                if (
                    shared_horizontal_eps_row
                    or out.get(key) is None
                ):
                    out[key] = value

    if not out.get("monthly_period"):
        out["monthly_period"] = _find_month_period(text)

    if not out.get("quarter_period"):
        out["quarter_period"] = _find_quarter_period(text)

    # Add voluntary disclosures after the existing attention-report parser.
    # Do not discard a parsed quarter or YoY comparison.
    direct = _extract_direct_self_report_metrics(text)
    if direct and out["monthly_eps"] is None:
        out.update(direct)

    out["eps"] = out["monthly_eps"]

    if (
        out["monthly_eps"] is not None
        and out["quarter_eps"] is not None
    ):
        out["eps_parse_status"] = "parsed"
        out["eps_parse_reason"] = ""

    elif direct and out["monthly_eps"] is not None:
        out["eps_parse_status"] = "direct_self_report"
        out["eps_parse_reason"] = ""

    elif (
        out["monthly_eps"] is not None
        or out["quarter_eps"] is not None
    ):
        out["eps_parse_status"] = "partial"
        out["eps_parse_reason"] = "only_one_eps_section_parsed"

    else:
        out["eps_parse_status"] = "failed"
        out["eps_parse_reason"] = "eps_values_not_parsed"

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
            self.rows.append({
                "text": text,
                "attrs": list(self.current_attrs),
            })

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

    if (
        not response.encoding
        or response.encoding.lower() == "iso-8859-1"
    ):
        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

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


def extract_detail_params(
    attrs,
    ticker,
    publish_date,
    publish_time,
):
    blob = " ".join(attrs or [])

    params = {
        "firstin": "1",
        "TYPEK": "all",
        "step": "2",
        "co_id": ticker,
    }

    for match in re.finditer(
        r"https?://[^'\"\s]+",
        blob,
    ):
        try:
            qs = parse_qs(
                urlparse(
                    html.unescape(match.group(0))
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
            rf"{key}(?:\.value)?\s*=\s*"
            rf"['\"]?([^&'\"\s,)]+)",
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

    if (
        "spoke_time" not in params
        and publish_time
    ):
        params["spoke_time"] = publish_time.replace(":", "")

    return params


def fetch_detail(params):
    errors = []

    if not params.get("seq_no"):
        return "", "", "missing_seq_no"

    date = str(params.get("spoke_date", ""))

    if len(date) == 7:
        date = (
            str(int(date[:3]) + 1911)
            + date[3:]
        )

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
            or params["co_id"]
            + date
            + params["seq_no"]
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
                or response.encoding.lower()
                == "iso-8859-1"
            ):
                response.encoding = (
                    response.apparent_encoding
                    or "utf-8"
                )

            clean = norm_text(
                re.sub(
                    r"<[^>]+>",
                    " ",
                    response.text,
                )
            )

            if (
                params["co_id"] in clean
                and re.search(EPS_WORD, clean, re.I)
            ):
                return (
                    clean,
                    url + "?" + urlencode(payload),
                    "",
                )

            errors.append(
                base + ":detail_validation_failed"
            )

        except Exception as exc:
            errors.append(
                base + ":" + type(exc).__name__
            )

    return "", "", ";".join(errors)


def parse_candidate_row(row, source_keyword):
    text = row.get("text", "")
    compact = compact_text(text)

    if source_keyword == "daily_broad":
        if not subject_is_candidate(text):
            return None

    elif (
        compact_text(source_keyword) not in compact
        and not subject_is_candidate(text)
    ):
        return None

    ticker_match = re.search(
        r"(?<!\d)(\d{4})(?!\d)",
        text,
    )

    if not ticker_match:
        return None

    ticker = ticker_match.group(1)

    if not ordinary_ticker(ticker):
        return None

    if (
        any(
            k in text
            for k in (
                "流動比率",
                "速動比率",
                "負債比率",
            )
        )
        and "注意交易" not in compact
    ):
        return None

    date_match = re.search(
        r"(?:(20\d{2})|(\d{2,3}))"
        r"[/-](\d{1,2})[/-](\d{1,2})",
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

    detail_params = extract_detail_params(
        row.get("attrs", []),
        ticker,
        publish_date,
        publish_time,
    )

    detail, source_url, detail_error = fetch_detail(
        detail_params
    )

    full_text = "\n".join(
        v
        for v in (text, detail)
        if v
    )

    full_compact = compact_text(full_text)

    return {
        "market": "",
        "ticker": ticker,
        "name": clean_name(name),
        "publish_date": publish_date,
        "publish_time": publish_time,
        "subject": text,
        "detail": detail,
        "source": "mops_ajax",
        "source_url": source_url,
        "source_error": detail_error,
        "match_reason": (
            "attention_trading"
            if "注意交易" in full_compact
            else "direct_self_report"
        ),
        **extract_metrics(full_text),
    }


TWSE_ATTENTION_URL = (
    "https://www.twse.com.tw/"
    "rwd/zh/announcement/notice"
)


def fetch_twse_attention_tickers(iso_date):
    params = {
        "response": "json",
        "startDate": iso_date.replace("-", ""),
        "endDate": iso_date.replace("-", ""),
    }

    try:
        response = S.get(
            TWSE_ATTENTION_URL,
            params=params,
            headers={
                "User-Agent":
                mops_headers()["User-Agent"]
            },
            timeout=(10, 25),
        )

        response.raise_for_status()
        data = response.json()

    except Exception as exc:
        return [], {
            "ok": False,
            "error": repr(exc),
        }

    tickers = []
    seen = set()
    rows = data.get("data") or []

    for row in rows:
        ticker = ""

        if isinstance(row, list):
            for cell in row[:4]:
                m = re.fullmatch(
                    r"\s*(\d{4})\s*",
                    str(cell or ""),
                )

                if (
                    m
                    and ordinary_ticker(m.group(1))
                ):
                    ticker = m.group(1)
                    break

        elif isinstance(row, dict):
            for key in (
                "Code",
                "證券代號",
                "股票代號",
                "代號",
            ):
                value = str(
                    row.get(key) or ""
                ).strip()

                if ordinary_ticker(value):
                    ticker = value
                    break

        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)

    return tickers, {
        "ok": True,
        "rows": len(rows),
        "tickers": len(tickers),
    }


def fetch_mops_company_today(ticker, iso_date):
    dt = datetime.strptime(
        iso_date,
        "%Y-%m-%d",
    )

    payload = {
        "firstin": "1",
        "step": "1",
        "off": "1",
        "TYPEK": "all",
        "co_id": ticker,
        "year": str(dt.year - 1911),
        "month": str(dt.month),
        "b_date": str(dt.day),
        "e_date": str(dt.day),
    }

    errors = []

    for base in reversed(MOPS_BASES):
        try:
            html_text = fetch_mops(
                base,
                payload,
            )

            rows = parse_rows(html_text)
            candidates = []

            for row in rows:
                row_text = row.get(
                    "text",
                    "",
                )

                if ticker not in row_text:
                    continue

                if not subject_is_candidate(
                    row_text
                ):
                    continue

                candidates.append(row)

            return candidates, {
                "ticker": ticker,
                "base": base,
                "rows": len(rows),
                "hits": len(candidates),
                "error": "",
            }

        except Exception as exc:
            errors.append(
                f"{base}:{type(exc).__name__}"
            )

    return [], {
        "ticker": ticker,
        "rows": 0,
        "hits": 0,
        "error": ";".join(errors),
    }
def fetch_mops_search():
    """
    v26 SAFE / ADDITIVE discovery

    原本 broad scan 保留
    額外補：
      1. 公司主動公布「自行結算損益」
      2. rescue 排除的是已成功辨識的 ticker，
         不再是所有曾出現在 broad list 的 ticker
    """
    today = now_tpe().date().isoformat()
    dt = datetime.strptime(today, "%Y-%m-%d")
    roc_year = dt.year - 1911
    month = str(dt.month)
    day = str(dt.day)

    debug = []
    raw_rows = []
    seen_rows = set()

    def add_row(source_keyword, row):
        sig = (
            compact_text(row.get("text", "")),
            tuple(row.get("attrs", [])),
        )
        if sig in seen_rows:
            return
        seen_rows.add(sig)
        raw_rows.append((source_keyword, row))

    # ---------- A. 原本 broad scan ----------
    broad_payloads = [
        {
            "firstin": "1",
            "step": "1",
            "off": "1",
            "TYPEK": "all",
            "year": str(roc_year),
            "month": month,
            "b_date": day,
            "e_date": day,
            "keyword4": "",
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
            "keyWord": "",
            "Condition2": "",
            "keyWord2": "",
        },
    ]

    broad_ok = False
    candidate_tickers = set()

    for base in reversed(MOPS_BASES):
        for idx, payload in enumerate(broad_payloads, 1):
            try:
                html_text = fetch_mops(base, payload)
                rows = parse_rows(html_text)

                candidates = [
                    row
                    for row in rows
                    if subject_is_candidate(
                        row.get("text", "")
                    )
                ]

                debug.append({
                    "mode": "daily_broad",
                    "base": base,
                    "payload": idx,
                    "rows": len(rows),
                    "hits": len(candidates),
                })

                if rows:
                    for row in candidates:
                        add_row("daily_broad", row)

                        m = re.search(
                            r"(?<!\d)(\d{4})(?!\d)",
                            row.get("text", ""),
                        )

                        if (
                            m
                            and ordinary_ticker(
                                m.group(1)
                            )
                        ):
                            candidate_tickers.add(
                                m.group(1)
                            )

                    broad_ok = True
                    break

            except Exception as exc:
                debug.append({
                    "mode": "daily_broad",
                    "base": base,
                    "payload": idx,
                    "error": repr(exc),
                })

        if broad_ok:
            break

    # ---------- B. 主動自行結算 keyword 補抓 ----------
    direct_keywords = (
        "自行結算",
        "自行結算損益",
    )

    for keyword in direct_keywords:
        got_keyword = False

        for base in reversed(MOPS_BASES):
            for payload in query_payloads(
                today,
                keyword,
            ):
                try:
                    html_text = fetch_mops(
                        base,
                        payload,
                    )

                    rows = parse_rows(html_text)

                    hits = [
                        row
                        for row in rows
                        if direct_self_report_subject(
                            row.get("text", "")
                        )
                    ]

                    debug.append({
                        "mode": "direct_self_report_keyword",
                        "base": base,
                        "keyword": keyword,
                        "rows": len(rows),
                        "hits": len(hits),
                    })

                    if hits:
                        for row in hits:
                            add_row(
                                keyword,
                                row,
                            )

                            m = re.search(
                                r"(?<!\d)(\d{4})(?!\d)",
                                row.get("text", ""),
                            )

                            if (
                                m
                                and ordinary_ticker(
                                    m.group(1)
                                )
                            ):
                                candidate_tickers.add(
                                    m.group(1)
                                )

                        got_keyword = True
                        break

                except Exception as exc:
                    debug.append({
                        "mode": "direct_self_report_keyword",
                        "base": base,
                        "keyword": keyword,
                        "error": repr(exc),
                    })

            if got_keyword:
                break

    # ---------- C. 原本官方重大訊息 rescue pool ----------
    rescue_tickers = set()
    rescue_source_debug = []

    for market, url in (
        ("twse", TWSE_NEWS),
        ("tpex", TPEX_NEWS),
    ):
        try:
            rows = get_json(
                url,
                timeout=30,
                tries=3,
            )

            if isinstance(rows, dict):
                rows = (
                    rows.get("data")
                    or rows.get("records")
                    or rows.get("result")
                    or []
                )

            if not isinstance(rows, list):
                rows = []

            market_tickers = set()

            for row in rows:
                if not isinstance(row, dict):
                    continue

                ticker = str(
                    p(
                        row,
                        [
                            "公司代號",
                            "證券代號",
                            "股票代號",
                            "代號",
                        ],
                        "",
                    )
                ).strip()

                if ordinary_ticker(ticker):
                    market_tickers.add(ticker)

            rescue_tickers.update(
                market_tickers
            )

            rescue_source_debug.append({
                "market": market,
                "rows": len(rows),
                "ticker_pool": len(market_tickers),
            })

        except Exception as exc:
            rescue_source_debug.append({
                "market": market,
                "error": repr(exc),
            })

    debug.append({
        "mode": "openapi_rescue_pool",
        "sources": rescue_source_debug,
        "tickers": len(rescue_tickers),
    })

    # ---------- D. Company-specific rescue ----------
    #
    # 只有已經成功辨識為候選公告的 ticker 才排除 rescue
    # 避免公司雖出現在 broad list，
    # 但自行結算公告沒命中時完全漏抓
    targets = sorted(
        rescue_tickers
        - candidate_tickers
    )

    rescued_tickers = []

    for ticker in targets:
        rows, status = fetch_mops_company_today(
            ticker,
            today,
        )

        debug.append({
            "mode": "company_rescue",
            **status,
        })

        if rows:
            rescued_tickers.append(ticker)

        for row in rows:
            add_row(
                "daily_broad",
                row,
            )

    debug.append({
        "mode": "company_rescue_summary",
        "targets": len(targets),
        "rescued": len(rescued_tickers),
        "rescued_tickers": rescued_tickers,
    })

    # ---------- E. 原本 keyword fallback ----------
    if not broad_ok and not raw_rows:
        debug.append({
            "mode": "fallback",
            "reason": "daily_broad_returned_no_rows",
        })

        for keyword in SEARCH_KEYWORDS:
            got_keyword = False

            for base in reversed(MOPS_BASES):
                for payload in query_payloads(
                    today,
                    keyword,
                ):
                    try:
                        html_text = fetch_mops(
                            base,
                            payload,
                        )

                        rows = parse_rows(html_text)

                        wanted = compact_text(keyword)

                        hits = [
                            row
                            for row in rows
                            if wanted
                            in compact_text(
                                row.get(
                                    "text",
                                    "",
                                )
                            )
                        ]

                        debug.append({
                            "mode": "keyword_fallback",
                            "base": base,
                            "keyword": keyword,
                            "rows": len(rows),
                            "hits": len(hits),
                        })

                        if hits:
                            for row in hits:
                                add_row(
                                    keyword,
                                    row,
                                )

                            got_keyword = True
                            break

                    except Exception as exc:
                        debug.append({
                            "mode": "keyword_fallback",
                            "base": base,
                            "keyword": keyword,
                            "error": repr(exc),
                        })

                if got_keyword:
                    break

    items = {}
    rejected = []

    for source_keyword, row in raw_rows:
        item = parse_candidate_row(
            row,
            source_keyword,
        )

        if not item:
            rejected.append({
                "keyword": source_keyword,
                "reason": "candidate_row_rejected",
                "text": row.get(
                    "text",
                    "",
                )[:500],
            })
            continue

        key = identity(item)

        items[key] = (
            merge_item(
                items[key],
                item,
            )
            if key in items
            else item
        )

    return {
        "ok": broad_ok or bool(raw_rows),
        "rows": len(raw_rows),
        "items": list(items.values()),
        "debug": debug,
        "rejected": rejected,
        "error": (
            ""
            if broad_ok or raw_rows
            else "mops_daily_scan_no_rows"
        ),
    }


def row_all_text(row):
    parts = []

    if isinstance(row, dict):
        for key, value in row.items():
            if isinstance(
                value,
                (str, int, float),
            ):
                value = norm_text(value)

                if value:
                    parts.append(
                        f"{norm_text(key)} "
                        f"{value}"
                    )

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
            "error": "response_is_not_list",
        }

    items = []

    for row in rows:
        ticker = str(
            p(
                row,
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

        subject = norm_text(
            p(
                row,
                [
                    "主旨",
                    "主旨 ",
                    "Subject",
                ],
                "",
            )
        )

        if not subject_is_candidate(subject):
            continue

        publish_date = roc_to_iso(
            p(
                row,
                [
                    "發言日期",
                    "公告日期",
                    "出表日期",
                ],
                "",
            )
        )

        if (
            not publish_date
            or publish_date < MONITOR_START_DATE
        ):
            continue

        publish_time = clean_time(
            p(
                row,
                [
                    "發言時間",
                    "公告時間",
                ],
                "",
            )
        )

        full_text = "\n".join([
            subject,
            row_all_text(row),
        ])

        items.append({
            "market": market,
            "ticker": ticker,
            "name": clean_name(
                p(
                    row,
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
            "detail": full_text,
            "source": f"{market}_openapi",
            "source_url": "",
            "source_error": "",
            "match_reason": (
                "attention_trading"
                if "注意交易"
                in compact_text(subject)
                else "direct_self_report"
            ),
            **extract_metrics(full_text),
        })

    return {
        "market": market,
        "ok": True,
        "rows": rows,
        "items": items,
        "error": "",
    }


def identity(item):
    return "|".join([
        str(item.get("ticker") or ""),
        str(item.get("publish_date") or ""),
        str(item.get("publish_time") or ""),
    ])


def canonical_sent_id(value):
    parts = str(value or "").split("|")

    return (
        "|".join(parts[:3])
        if len(parts) >= 3
        else str(value or "")
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
            "source_error",
            "match_reason",
        ):
            if new.get(key):
                out[key] = new[key]

    old_score = (
        int(old.get("monthly_eps") is not None)
        + int(old.get("quarter_eps") is not None)
    )

    new_score = (
        int(new.get("monthly_eps") is not None)
        + int(new.get("quarter_eps") is not None)
    )

    if new_score >= old_score:
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
            "eps_parse_reason",
            "eps",
        ):
            if key in new:
                out[key] = new.get(key)

    return out


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
            "telegram secrets "
            "missing; skip"
        )
        return False

    try:
        response = S.post(
            (
                "https://api.telegram.org/"
                f"bot{token}/sendMessage"
            ),
            data={
                "chat_id": chat_id,
                "text": f"{title}\n{message}",
                "disable_web_page_preview": True,
                "reply_markup": json.dumps(
                    {
                        "inline_keyboard": [[
                            {
                                "text": "開啟台股市場監測",
                                "url": url,
                            }
                        ]]
                    },
                    ensure_ascii=False,
                ),
            },
            timeout=30,
        )

        response.raise_for_status()

        return bool(
            response.json().get("ok")
        )

    except Exception as exc:
        print(
            "telegram failed",
            repr(exc),
        )
        return False


def eps_line(item, kind):
    period = item.get(
        kind + "_period"
    )

    label = (
        period
        + (
            " 單月 EPS"
            if kind == "monthly"
            else " 上一季 EPS"
        )
        if period
        else (
            "單月 EPS"
            if kind == "monthly"
            else "上一季 EPS"
        )
    )

    value = item.get(
        kind + "_eps"
    )

    growth = item.get(
        kind + "_eps_yoy"
    )

    value_text = (
        f"{value:.2f} 元"
        if value is not None
        else "未取得"
    )

    growth_text = (
        f"{growth:+.2f}%"
        if growth is not None
        else item.get(
            kind + "_eps_yoy_text"
        )
        or "未取得"
    )

    return (
        f"{label}：{value_text}"
        f"｜與去年同期增減："
        f"{growth_text}"
    )



def _previous_quarter_from_month_period(month_period):
    m = re.fullmatch(r"(20\d{2})-(\d{2})", str(month_period or ""))
    if not m:
        return ""
    year = int(m.group(1))
    month = int(m.group(2))
    if not 1 <= month <= 12:
        return ""
    current_q = (month - 1) // 3 + 1
    if current_q == 1:
        return f"{year - 1}-Q4"
    return f"{year}-Q{current_q - 1}"


def _previous_year_same_quarter(period):
    m = re.fullmatch(r"(20\d{2})-Q([1-4])", str(period or ""))
    if not m:
        return ""
    return f"{int(m.group(1)) - 1}-Q{m.group(2)}"


def _quarterly_single_eps_from_history(rows_by_key, ticker, period):
    row = rows_by_key.get((ticker, period))
    if not row:
        return None

    q = int(period[-1])
    if row.get("single_eps") is not None:
        return _number(row.get("single_eps"))

    current = _number(row.get("cum_eps"))
    if current is None:
        return None

    if q == 1:
        return current

    year = int(period[:4])
    prev_period = f"{year}-Q{q - 1}"
    prev = rows_by_key.get((ticker, prev_period))
    if not prev:
        return None

    prev_cum = _number(prev.get("cum_eps"))
    if prev_cum is None:
        return None

    return round(current - prev_cum, 6)


def _load_quarterly_eps_rows():
    path = ROOT / "data/quarterly_earnings_history.json"
    data = load_json(path, {"rows": []})
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return {
        (str(row.get("ticker") or ""), str(row.get("period") or "")): row
        for row in rows
        if isinstance(row, dict) and row.get("ticker") and row.get("period")
    }


def _ensure_quarterly_eps_rows(ticker, periods, rows_by_key):
    needed = set()
    for period in periods:
        if not period:
            continue
        needed.add(period)
        if int(period[-1]) > 1:
            needed.add(f"{period[:4]}-Q{int(period[-1]) - 1}")

    complete = all((ticker, period) in rows_by_key for period in needed)
    if complete:
        return rows_by_key

    try:
        from update_quarterly_earnings import backfill_history

        targets = {period: {ticker} for period in needed}
        backfill_history(rows_by_key, needed, targets)
    except Exception as exc:
        print(
            "quarter EPS fallback failed",
            ticker,
            type(exc).__name__,
        )

    return rows_by_key


def enrich_direct_self_report_quarter_eps(items):
    """Add only prior-quarter EPS + YoY to voluntary self-reports.

    Existing attention-trading parsing is untouched.  Official quarterly
    earnings history is used; when the cache lacks a required period, the
    existing official MOPS quarterly backfill helper is called.
    """
    direct_items = [
        item
        for item in items
        if item.get("match_reason") == "direct_self_report"
        and item.get("monthly_eps") is not None
    ]
    if not direct_items:
        return

    rows_by_key = _load_quarterly_eps_rows()

    for item in direct_items:
        period = _previous_quarter_from_month_period(item.get("monthly_period"))
        if not period:
            continue

        yoy_period = _previous_year_same_quarter(period)
        rows_by_key = _ensure_quarterly_eps_rows(
            str(item.get("ticker") or ""),
            (period, yoy_period),
            rows_by_key,
        )

        current_eps = _quarterly_single_eps_from_history(
            rows_by_key,
            str(item.get("ticker") or ""),
            period,
        )
        last_year_eps = _quarterly_single_eps_from_history(
            rows_by_key,
            str(item.get("ticker") or ""),
            yoy_period,
        )

        if current_eps is None:
            continue

        item["quarter_period"] = period
        item["quarter_eps"] = current_eps
        item["quarter_eps_yoy"] = None
        item["quarter_eps_yoy_text"] = ""

        if last_year_eps not in (None, 0):
            yoy = (current_eps / last_year_eps - 1.0) * 100.0
            if math.isfinite(yoy):
                item["quarter_eps_yoy"] = yoy
                item["quarter_eps_yoy_text"] = f"{yoy:+.2f}%"

def push_text(item):
    lines = [
        (
            f"{item.get('name') or item['ticker']} "
            f"{item['ticker']}"
        ),
    ]

    if item.get("match_reason") == "direct_self_report":
        period = item.get("monthly_period")
        label = f"{period} 單月 EPS" if period else "單月 EPS"
        value = item.get("monthly_eps")
        value_text = f"{value:.2f} 元" if value is not None else "未取得"
        lines.append(f"{label}：{value_text}")
    else:
        lines.append(
            eps_line(
                item,
                "monthly",
            )
        )

    if item.get("quarter_eps") is not None:
        lines.append(
            eps_line(
                item,
                "quarter",
            )
        )

    return "\n".join(lines)


def valid_eps_item(item):
    # 原本注意交易規則完全保留：
    # 必須同時有單月 EPS + 上一季 EPS
    if (
        item.get("match_reason")
        == "attention_trading"
    ):
        return (
            item.get("monthly_eps")
            is not None
            and item.get("quarter_eps")
            is not None
        )

    # 公司主動公布自行結算損益：
    # 只要有明確單月 EPS 即可
    if (
        item.get("match_reason")
        == "direct_self_report"
    ):
        return (
            item.get("monthly_eps")
            is not None
        )

    return (
        item.get("monthly_eps")
        is not None
        and item.get("quarter_eps")
        is not None
    )


def diagnostic_entry(item):
    return {
        "ticker": item.get("ticker", ""),
        "name": item.get("name", ""),
        "publish_date": item.get(
            "publish_date",
            "",
        ),
        "publish_time": item.get(
            "publish_time",
            "",
        ),
        "subject": item.get("subject", ""),
        "source": item.get("source", ""),
        "source_error": item.get(
            "source_error",
            "",
        ),
        "eps_parse_status": item.get(
            "eps_parse_status",
            "",
        ),
        "eps_parse_reason": item.get(
            "eps_parse_reason",
            "",
        ),
        "monthly_eps": item.get("monthly_eps"),
        "quarter_eps": item.get("quarter_eps"),
    }


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

    for item in old.get(
        "items",
        [],
    ):
        if (
            str(
                item.get(
                    "publish_date"
                )
                or ""
            )
            < MONITOR_START_DATE
        ):
            continue

        saved[
            identity(item)
        ] = item

    try:
        mops = fetch_mops_search()

        print(
            "MOPS AJAX",
            "rows",
            mops.get("rows"),
            "candidates",
            len(
                mops.get(
                    "items",
                    [],
                )
            ),
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

        print(
            "MOPS AJAX failed",
            repr(exc),
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
        for item in source.get(
            "items",
            [],
        ):
            key = identity(item)

            fresh_map[key] = (
                merge_item(
                    fresh_map[key],
                    item,
                )
                if key in fresh_map
                else item
            )

    fresh = list(
        fresh_map.values()
    )

    for item in fresh:
        key = identity(item)

        saved[key] = (
            merge_item(
                saved[key],
                item,
            )
            if key in saved
            else item
        )

    all_candidates = list(
        saved.values()
    )

    # 保留原本重新解析 history
    for item in all_candidates:
        parse_text = "\n".join(
            x
            for x in (
                item.get("subject")
                or "",
                item.get("detail")
                or "",
            )
            if x
        )

        parsed = extract_metrics(
            parse_text
        )

        old_score = (
            int(
                item.get("monthly_eps")
                is not None
            )
            + int(
                item.get("quarter_eps")
                is not None
            )
        )

        new_score = (
            int(
                parsed.get("monthly_eps")
                is not None
            )
            + int(
                parsed.get("quarter_eps")
                is not None
            )
        )

        if new_score >= old_score:
            item.update(parsed)

    # Voluntary self-reports may only publish the current monthly EPS.
    # Fill only prior-quarter EPS and its YoY from official quarterly data.
    enrich_direct_self_report_quarter_eps(all_candidates)

    all_candidates.sort(
        key=lambda item: (
            item.get(
                "publish_date",
                "",
            ),
            item.get(
                "publish_time",
                "",
            ),
            item.get(
                "ticker",
                "",
            ),
        ),
        reverse=True,
    )

    display_items = [
        item
        for item in all_candidates
        if valid_eps_item(item)
    ]

    parse_failed = [
        diagnostic_entry(item)
        for item in all_candidates
        if (
            not valid_eps_item(item)
            and subject_is_candidate(
                item.get(
                    "subject",
                    "",
                )
            )
        )
    ]

    sent_data = load_json(
        sent_path,
        {},
    )

    legacy_pushover_ids = [
        canonical_sent_id(x)
        for x in sent_data.get(
            "ids",
            [],
        )
        if canonical_sent_id(x)
    ]

    telegram_sent = {
        canonical_sent_id(x)
        for x in sent_data.get(
            "telegram_ids",
            [],
        )
        if canonical_sent_id(x)
    }

    now = now_tpe()
    today = now.date().isoformat()

    for item in fresh:
        full_item = saved.get(
            identity(item),
            item,
        )

        if not valid_eps_item(
            full_item
        ):
            continue

        base_key = identity(
            full_item
        )

        if (
            str(
                full_item.get(
                    "publish_date"
                )
                or ""
            )
            != today
        ):
            continue

        if base_key in telegram_sent:
            continue

        page_url = (
            SITE_URL
            + "?"
            + urlencode({
                "page": "selfReports",
                "ticker": (
                    full_item.get("ticker")
                    or ""
                ),
                "date": (
                    full_item.get(
                        "publish_date"
                    )
                    or ""
                ),
                "time": (
                    full_item.get(
                        "publish_time"
                    )
                    or ""
                ),
            })
        )

        if send_telegram(
            "自結公布",
            push_text(full_item),
            page_url,
        ):
            telegram_sent.add(
                base_key
            )

    updated_at = (
        now_tpe().isoformat(
            timespec="minutes"
        )
    )

    save_json(
        history_path,
        {
            "updated_at": updated_at,
            "version": VERSION,
            "monitor_start_date":
                MONITOR_START_DATE,
            "candidate_count":
                len(all_candidates),
            "parsed_count":
                len(display_items),
            "parse_failed_count":
                len(parse_failed),
            "parse_failed":
                parse_failed,
            "items":
                all_candidates,
        },
    )

    save_json(
        sent_path,
        {
            "updated_at":
                updated_at,
            "ids":
                legacy_pushover_ids[
                    -2000:
                ],
            "telegram_ids":
                list(
                    telegram_sent
                )[-2000:],
        },
    )

    save_json(
        ROOT
        / "data/self_reports.json",
        {
            "updated_at":
                updated_at,
            "monitor_start_date":
                MONITOR_START_DATE,
            "filter_version":
                VERSION,
            "source_mode":
                (
                    "MOPS daily broad primary "
                    "+ direct self-report keyword "
                    "+ official feed ticker "
                    "company-rescue additive fallback; "
                    "Telegram only"
                ),
            "diagnostics": {
                "candidate_count":
                    len(all_candidates),
                "parsed_count":
                    len(display_items),
                "parse_failed_count":
                    len(parse_failed),
                "parse_failed":
                    parse_failed,
            },
            "source_status": {
                "mops": {
                    "ok":
                        mops.get(
                            "ok",
                            False,
                        ),
                    "rows":
                        mops.get(
                            "rows",
                            0,
                        ),
                    "self_reports":
                        len(
                            mops.get(
                                "items",
                                [],
                            )
                        ),
                    "debug":
                        mops.get(
                            "debug",
                            [],
                        ),
                    "rejected":
                        mops.get(
                            "rejected",
                            [],
                        ),
                    "error":
                        mops.get(
                            "error",
                            "",
                        ),
                },
                "twse": {
                    "ok":
                        twse_result.get(
                            "ok",
                            False,
                        ),
                    "rows":
                        len(
                            twse_result.get(
                                "rows",
                                [],
                            )
                        ),
                    "self_reports":
                        len(
                            twse_result.get(
                                "items",
                                [],
                            )
                        ),
                    "error":
                        twse_result.get(
                            "error",
                            "",
                        ),
                },
                "tpex": {
                    "ok":
                        tpex_result.get(
                            "ok",
                            False,
                        ),
                    "rows":
                        len(
                            tpex_result.get(
                                "rows",
                                [],
                            )
                        ),
                    "self_reports":
                        len(
                            tpex_result.get(
                                "items",
                                [],
                            )
                        ),
                    "error":
                        tpex_result.get(
                            "error",
                            "",
                        ),
                },
            },
            "items":
                display_items,
        },
    )

    print(
        "self reports",
        "candidates",
        len(all_candidates),
        "parsed",
        len(display_items),
        "parse_failed",
        len(parse_failed),
        "fresh",
        len(fresh),
        "version",
        VERSION,
    )


if __name__ == "__main__":
    main()
