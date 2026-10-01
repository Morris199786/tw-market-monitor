from sources import *

import html
import json
import math
import os
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse

VERSION = "2026-10-01-v19-eps-unit-label-fix-telegram-only"

MOPS_BASES = (
    "https://mops.twse.com.tw",
    "https://mopsov.twse.com.tw",
)
MOPS_AJAX_PATH = "/mops/web/ajax_t05st01"

TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"

MONITOR_START_DATE = "2026-09-26"
SITE_URL = "https://morris199786.github.io/tw-market-monitor/"

# 搜尋層刻意放寬；後面再用 subject_is_candidate 過濾
SEARCH_KEYWORDS = (
    "注意交易",
    "財務業務",
    "近期財務",
    "自結",
)

SELF_REPORT_KEYWORDS = (
    "自結",
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
    r"|轉虧為盈|轉盈為虧|N/?A|--+|—|-)"
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


def _ad_year(year):
    year = int(year)
    return year + 1911 if year < 1911 else year


def _quarter_num(q):
    return {"一": "1", "二": "2", "三": "3", "四": "4"}.get(str(q), str(q))


def _empty_metrics():
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
    out["eps_parse_reason"] = ""
    return out


def _find_month_period(text):
    patterns = (
        r"(?<!\d)(\d{2,4})\s*年\s*(\d{1,2})\s*月",
        r"(?<!\d)(\d{2,4})\s*/\s*(\d{1,2})(?!\s*/\s*\d)",
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
    patterns = (
        r"(?<!\d)(\d{2,4})\s*年\s*第?\s*([1-4一二三四])\s*季",
        r"(?<!\d)(20\d{2})\s*Q\s*([1-4])",
        r"(?<!\d)(\d{2,3})\s*Q\s*([1-4])",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return f"{_ad_year(m.group(1))}-Q{_quarter_num(m.group(2))}"
    return None


def _extract_mops_section_eps(section):
    """MOPS 注意交易公告直式表格 fallback：只在月/季 section 內抓 EPS 列。"""
    if not section:
        return None
    m = re.search(EPS_WORD, section, re.I)
    if not m:
        return None
    tail = section[m.end():]
    tail = re.sub(r"^\s*[（(]?\s*(?:元|新台幣元)\s*[）)]?\s*", "", tail, flags=re.I)
    vals = re.findall(CELL, tail, re.I)
    if not vals:
        return None
    current = _number(vals[0])
    if current is None:
        return None
    previous = None
    yoy = None
    yoy_text = None
    if len(vals) >= 2 and "%" not in vals[1]:
        previous = _number(vals[1])
    for raw in vals[1:4]:
        if "%" in raw:
            yoy = _number(raw, growth=True)
            yoy_text = raw.strip()
            break
    if yoy_text is None:
        for raw in vals[1:4]:
            if re.search(r"不適用|不適合|無法計算|由虧轉盈|由盈轉虧|轉虧為盈|轉盈為虧|N/?A|--+|—", raw, re.I):
                yoy_text = raw.strip()
                break
    return current, previous, yoy, yoy_text


def _extract_eps_triplet(section):
    """
    從單一月/季區塊中找 EPS 行。
    支援：
      每股盈餘 0.76 0.30 153%
      每股盈餘(元) 0.76 0.30 153%
      EPS 0.76 / 0.30 / 153%
    """
    eps = re.search(EPS_WORD, section, re.I)
    if not eps:
        return None

    tail = section[eps.end():]
    tail = re.sub(r"^\s*[（(]?\s*元\s*[）)]?\s*", "", tail)

    values = re.findall(CELL, tail, re.I)
    if len(values) < 3:
        return None

    # EPS 行的前三個有效 cell：本期、去年同期、YoY
    current, previous, yoy = values[:3]

    if "%" in current or "%" in previous:
        return None

    current_num = _number(current)
    previous_num = _number(previous)
    yoy_num = _number(yoy, growth=True)

    if current_num is None:
        return None

    return current_num, previous_num, yoy_num, yoy.strip()

def _extract_horizontal_eps(text):
    """
    橫向表格：
      最近一個月 | 與去年同期增減 | 最近一季 | 與去年同期增減
      每股盈餘     0.76   153%       2.33   203%

    也支援高力/禾伸堂這種沒有「去年同期 EPS 值」、只有 YoY 的橫向格式。
    """
    eps = re.search(EPS_WORD, text, re.I)
    if not eps:
        return None

    # 限制在 EPS 標籤後、下一個公告段落前，避免吃到其他數字
    tail = text[eps.end():]
    stop = re.search(r"(?:\s4\.|\s有無[「\"]|最近四季累計)", tail)
    if stop:
        tail = tail[:stop.start()]

    vals = re.findall(CELL, tail, re.I)
    if not vals:
        return None

    nums = []
    for raw in vals[:10]:
        nums.append((raw, _number(raw, growth=("%" in raw))))

    # 最常見：月EPS、月YoY、季EPS、季YoY
    if len(vals) >= 4 and "%" in vals[1] and "%" in vals[3]:
        return {
            "monthly_eps": _number(vals[0]),
            "monthly_eps_yoy": _number(vals[1], growth=True),
            "monthly_eps_yoy_text": vals[1].strip(),
            "quarter_eps": _number(vals[2]),
            "quarter_eps_yoy": _number(vals[3], growth=True),
            "quarter_eps_yoy_text": vals[3].strip(),
        }

    # 另一常見格式：月EPS、去年月EPS、月YoY、季EPS、去年季EPS、季YoY
    if len(vals) >= 6 and "%" in vals[2] and "%" in vals[5]:
        return {
            "monthly_eps": _number(vals[0]),
            "monthly_eps_yoy": _number(vals[2], growth=True),
            "monthly_eps_yoy_text": vals[2].strip(),
            "quarter_eps": _number(vals[3]),
            "quarter_eps_yoy": _number(vals[5], growth=True),
            "quarter_eps_yoy_text": vals[5].strip(),
        }

    return None


def _slice_semantic_sections(text):
    """
    切出單月 / 單季區塊。

    MOPS 常同時出現「(1)單月 最近一月單月」；舊版把第二個
    同類 marker 誤當成區塊終點，結果 monthly section 只剩「單月」。
    現在只用「另一種類型」的 marker 當區塊終點。
    """
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

        sections[kind] = text[start:end]

    return sections

def _fallback_period_sections(text):
    """
    有些 MOPS 表格沒有「最近一個月/最近一季」文字，
    只列 115年8月、115年第2季。用期間位置切區塊。
    """
    month = re.search(
        r"(?<!\d)(?:\d{2,4}\s*年\s*\d{1,2}\s*月|20\d{2}[-/]\d{1,2})",
        text,
    )
    quarter = re.search(
        r"(?<!\d)(?:\d{2,4}\s*年\s*第?\s*[1-4一二三四]\s*季|20\d{2}\s*Q\s*[1-4])",
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


def extract_metrics(text):
    """
    容錯版 EPS parser：
    - 最近一月 / 最近一個月 / 單月 / 當月 / 本月
    - 最近一季 / 最近一個季 / 單季 / 本季
    - 民國年 / 西元年 / YYYY/MM / YYYYQn
    - 由虧轉盈 / 由盈轉虧 / 不適用 / NA
    - 不再要求固定的「去年」出現次數或固定欄位空白
    """
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

    month_values = _extract_eps_triplet(month_section) if month_section else None
    quarter_values = _extract_eps_triplet(quarter_section) if quarter_section else None

    # MOPS 注意交易公告可能是直式表格，HTML 壓成文字後不一定符合一般 triplet 版型
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

    # 若月/季被排在同一列，語意切區塊會切不到 EPS；改用橫向 parser 補抓
    if out["monthly_eps"] is None or out["quarter_eps"] is None:
        horizontal = _extract_horizontal_eps(text)
        if horizontal:
            for key, value in horizontal.items():
                if out.get(key) is None:
                    out[key] = value

    # 期間從全文補抓，避免橫向表格期間在 EPS 列之前
    if not out.get("monthly_period"):
        out["monthly_period"] = _find_month_period(text)
    if not out.get("quarter_period"):
        out["quarter_period"] = _find_quarter_period(text)

    out["eps"] = out["monthly_eps"]

    if out["monthly_eps"] is not None and out["quarter_eps"] is not None:
        out["eps_parse_status"] = "parsed"
        out["eps_parse_reason"] = ""
    elif out["monthly_eps"] is not None or out["quarter_eps"] is not None:
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
            self.rows.append({"text": text, "attrs": list(self.current_attrs)})

        self.in_tr = False
        self.current_text = []
        self.current_attrs = []


def mops_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
            "firstin": "1", "step": "1", "off": "1", "TYPEK": "all",
            "year": str(roc_year), "month": month,
            "b_date": day, "e_date": day,
            "keyword4": keyword, "queryName": "co_id", "co_id": "",
        },
        {
            "firstin": "1", "step": "1", "TYPEK": "all",
            "year": str(roc_year), "month": month,
            "b_date": day, "e_date": day,
            "keyWord": keyword, "Condition2": "", "keyWord2": "",
        },
        {
            "firstin": "1", "step": "1", "TYPEK": "all",
            "year": str(roc_year), "month1": month,
            "b_date": day, "e_date": day,
            "keyWord": keyword, "KIND": "all",
        },
    ]


def extract_detail_params(attrs, ticker, publish_date, publish_time):
    blob = " ".join(attrs or [])
    params = {"firstin": "1", "TYPEK": "all", "step": "2", "co_id": ticker}

    for match in re.finditer(r"https?://[^'\"\s]+", blob):
        try:
            qs = parse_qs(urlparse(html.unescape(match.group(0))).query)
            for key in ("seq_no", "spoke_time", "spoke_date", "skey", "TYPEK", "off"):
                if qs.get(key):
                    params[key] = qs[key][0]
        except Exception:
            pass

    for key in ("seq_no", "spoke_time", "spoke_date", "skey", "TYPEK", "off"):
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
            f"{publish_date[5:7]}{publish_date[8:10]}"
        )

    if "spoke_time" not in params and publish_time:
        params["spoke_time"] = publish_time.replace(":", "")

    return params


def fetch_detail(params):
    errors = []

    if not params.get("seq_no"):
        return "", "", "missing_seq_no"

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
        "skey": params.get("skey") or params["co_id"] + date + params["seq_no"],
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

            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding or "utf-8"

            clean = norm_text(re.sub(r"<[^>]+>", " ", response.text))

            # 不再要求日期、時間字串一定要以固定格式出現在明細頁
            # 只要公司代號與 EPS 欄位存在，就保留全文給 parser
            if (
                params["co_id"] in clean
                and re.search(EPS_WORD, clean, re.I)
            ):
                return clean, url + "?" + urlencode(payload), ""

            errors.append(base + ":detail_validation_failed")

        except Exception as exc:
            errors.append(base + ":" + type(exc).__name__)

    return "", "", ";".join(errors)


def parse_candidate_row(row, source_keyword):
    text = row.get("text", "")
    compact = compact_text(text)

    if compact_text(source_keyword) not in compact and not subject_is_candidate(text):
        return None

    ticker_match = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
    if not ticker_match:
        return None

    ticker = ticker_match.group(1)
    if not ordinary_ticker(ticker):
        return None

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

    time_match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    publish_time = clean_time(time_match.group(0)) if time_match else ""

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
    detail, source_url, detail_error = fetch_detail(detail_params)

    full_text = "\n".join(v for v in (text, detail) if v)
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
                    wanted = compact_text(keyword)

                    hits = [
                        row for row in rows
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
                    "reason": "candidate_row_rejected",
                    "text": row.get("text", "")[:500],
                }
            )
            continue

        key = identity(item)
        if key in items:
            items[key] = merge_item(items[key], item)
        else:
            items[key] = item

    return {
        "ok": True,
        "rows": len(raw_rows),
        "items": list(items.values()),
        "debug": debug,
        "rejected": rejected,
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
        rows = get_json(url, timeout=45, tries=5)
    except Exception as exc:
        return {
            "market": market,
            "ok": False,
            "rows": [],
            "items": [],
            "error": repr(exc),
        }

    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("records") or rows.get("result") or []

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
            p(row, ["公司代號", "證券代號", "股票代號", "代號"], "")
        ).strip()

        if not ordinary_ticker(ticker):
            continue

        subject = norm_text(p(row, ["主旨", "主旨 ", "Subject"], ""))
        if not subject_is_candidate(subject):
            continue

        publish_date = roc_to_iso(
            p(row, ["發言日期", "公告日期", "出表日期"], "")
        )
        if not publish_date or publish_date < MONITOR_START_DATE:
            continue

        publish_time = clean_time(p(row, ["發言時間", "公告時間"], ""))
        full_text = "\n".join([subject, row_all_text(row)])

        items.append(
            {
                "market": market,
                "ticker": ticker,
                "name": clean_name(
                    p(row, ["公司名稱", "證券名稱", "名稱"], "")
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
                    if "注意交易" in compact_text(subject)
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
        ]
    )


def canonical_sent_id(value):
    parts = str(value or "").split("|")
    return "|".join(parts[:3]) if len(parts) >= 3 else str(value or "")


def merge_item(old, new):
    out = dict(old)

    for key, value in new.items():
        if value not in (None, "", [], {}) and out.get(key) in (None, "", [], {}):
            out[key] = value

    if new.get("source") == "mops_ajax":
        for key in (
            "name", "subject", "detail", "source",
            "source_url", "source_error", "match_reason",
        ):
            if new.get(key):
                out[key] = new[key]

    # EPS 採解析較完整者
    old_score = int(old.get("monthly_eps") is not None) + int(old.get("quarter_eps") is not None)
    new_score = int(new.get("monthly_eps") is not None) + int(new.get("quarter_eps") is not None)

    if new_score >= old_score:
        for key in (
            "monthly_eps", "monthly_eps_yoy", "monthly_period",
            "quarter_eps", "quarter_eps_yoy", "quarter_period",
            "monthly_eps_yoy_text", "quarter_eps_yoy_text",
            "eps_parse_status", "eps_parse_reason", "eps",
        ):
            if key in new:
                out[key] = new.get(key)

    return out


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


def diagnostic_entry(item):
    return {
        "ticker": item.get("ticker", ""),
        "name": item.get("name", ""),
        "publish_date": item.get("publish_date", ""),
        "publish_time": item.get("publish_time", ""),
        "subject": item.get("subject", ""),
        "source": item.get("source", ""),
        "source_error": item.get("source_error", ""),
        "eps_parse_status": item.get("eps_parse_status", ""),
        "eps_parse_reason": item.get("eps_parse_reason", ""),
        "monthly_eps": item.get("monthly_eps"),
        "quarter_eps": item.get("quarter_eps"),
    }


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
            "rows", mops.get("rows"),
            "candidates", len(mops.get("items", [])),
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

    # 關鍵：history 永久保存 candidate，不因 parser 失敗而刪除
    all_candidates = list(saved.values())

    # 對有 MOPS detail 的公告重新解析
    for item in all_candidates:
        parse_text = "\n".join(
            x for x in (
                item.get("subject") or "",
                item.get("detail") or "",
            )
            if x
        )
        parsed = extract_metrics(parse_text)

        # 只有新版解析結果較完整時才覆蓋
        old_score = int(item.get("monthly_eps") is not None) + int(item.get("quarter_eps") is not None)
        new_score = int(parsed.get("monthly_eps") is not None) + int(parsed.get("quarter_eps") is not None)

        if new_score >= old_score:
            item.update(parsed)

    all_candidates.sort(
        key=lambda item: (
            item.get("publish_date", ""),
            item.get("publish_time", ""),
            item.get("ticker", ""),
        ),
        reverse=True,
    )

    # 網站仍只顯示完整月 EPS + 季 EPS，避免把非 EPS 公告混進 UI
    display_items = [
        item for item in all_candidates
        if valid_eps_item(item)
    ]

    parse_failed = [
        diagnostic_entry(item)
        for item in all_candidates
        if not valid_eps_item(item)
        and subject_is_candidate(item.get("subject", ""))
    ]

    sent_data = load_json(sent_path, {})

    # 相容舊資料，但 v16 起不再發 Pushover
    legacy_pushover_ids = [
        canonical_sent_id(x)
        for x in sent_data.get("ids", [])
        if canonical_sent_id(x)
    ]

    telegram_sent = {
        canonical_sent_id(x)
        for x in sent_data.get("telegram_ids", [])
        if canonical_sent_id(x)
    }

    now = now_tpe()
    today = now.date().isoformat()

    for item in fresh:
        # fresh 可能來自 OpenAPI，重新使用 merge 後的完整版本
        full_item = saved.get(identity(item), item)

        if not valid_eps_item(full_item):
            continue

        base_key = identity(full_item)

        # 只推今天新公告；歷史補抓只補資料不重送
        if str(full_item.get("publish_date") or "") != today:
            continue

        if base_key in telegram_sent:
            continue

        page_url = (
            SITE_URL
            + "?"
            + urlencode(
                {
                    "page": "selfReports",
                    "ticker": full_item.get("ticker") or "",
                    "date": full_item.get("publish_date") or "",
                    "time": full_item.get("publish_time") or "",
                }
            )
        )

        if send_telegram("自結公布", push_text(full_item), page_url):
            telegram_sent.add(base_key)

    updated_at = now_tpe().isoformat(timespec="minutes")

    save_json(
        history_path,
        {
            "updated_at": updated_at,
            "version": VERSION,
            "monitor_start_date": MONITOR_START_DATE,
            "candidate_count": len(all_candidates),
            "parsed_count": len(display_items),
            "parse_failed_count": len(parse_failed),
            "parse_failed": parse_failed,
            "items": all_candidates,
        },
    )

    save_json(
        sent_path,
        {
            "updated_at": updated_at,
            # 保留舊欄位避免其他程式讀取出錯，但不再新增 Pushover id
            "ids": legacy_pushover_ids[-2000:],
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
                "MOPS ajax_t05st01 broad candidate search + "
                "TWSE/TPEx OpenAPI union; Telegram only"
            ),
            "diagnostics": {
                "candidate_count": len(all_candidates),
                "parsed_count": len(display_items),
                "parse_failed_count": len(parse_failed),
                "parse_failed": parse_failed,
            },
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
            "items": display_items,
        },
    )

    print(
        "self reports",
        "candidates", len(all_candidates),
        "parsed", len(display_items),
        "parse_failed", len(parse_failed),
        "fresh", len(fresh),
        "version", VERSION,
    )


if __name__ == "__main__":
    main()
