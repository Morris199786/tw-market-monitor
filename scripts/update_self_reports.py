from sources import *
import os
import re
import time
from datetime import timedelta
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

VERSION = "2026-09-26-v6-full-market-backfill"

TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"
MOPS_HISTORY_URL = "https://mops.twse.com.tw/mops/web/t05st01"
BACKFILL_STATE = ROOT / "data/self_reports_backfill_state.json"

SUBJECT_KEYWORDS = (
    "自結", "財務業務資訊", "近期財務資訊", "近期財務業務資訊",
    "最近一月", "最近一季", "達公布注意交易資訊標準",
    "達注意交易資訊標準", "多次達公布注意交易資訊標準",
    "有價證券達公布注意交易資訊標準", "注意交易資訊標準",
)

FINANCIAL_ANCHORS = (
    "營業收入", "營收", "稅前淨利", "稅前純益", "稅前損益",
    "稅後淨利", "稅後純益", "稅後損益", "本期淨利",
    "歸屬母公司", "每股盈餘", "EPS",
)

EXCLUDE_SUBJECT_KEYWORDS = (
    "股票面額", "面額變更", "除權", "除息", "股利", "現金股利",
    "盈餘分配", "董事會", "股東會", "法說會", "法人說明會",
    "增資", "減資", "現金增資", "可轉換公司債", "可轉債",
    "公司債", "私募", "庫藏股", "取得或處分資產", "背書保證",
    "資金貸與", "關係人交易", "更換會計師", "簽證會計師",
    "發言人", "代理發言人", "董事辭任", "獨立董事",
)


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.in_tr = False
        self.in_cell = False
        self.cells = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self.in_tr = True
            self.cells = []
        elif tag in ("td", "th") and self.in_tr:
            self.in_cell = True
            self.parts = []

    def handle_data(self, data):
        if self.in_cell:
            self.parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("td", "th") and self.in_cell:
            txt = re.sub(r"\s+", " ", "".join(self.parts)).strip()
            self.cells.append(txt)
            self.in_cell = False
            self.parts = []
        elif tag == "tr" and self.in_tr:
            if self.cells:
                self.rows.append(self.cells[:])
            self.in_tr = False
            self.cells = []


def p(row, names, default=""):
    return pick(row, names, default)


def norm_text(s):
    return str(s or "").replace("\r", " ").replace("\n", " ").replace("　", " ").strip()


def roc_to_iso(s):
    raw = str(s or "").strip()

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
        try:
            y = int(digits[:3]) + 1911
            return f"{y:04d}-{digits[3:5]}-{digits[5:7]}"
        except Exception:
            pass

    return ""


def clean_time(s):
    raw = str(s or "").strip()

    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}:{int(m.group(3) or 0):02d}"

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
            re.escape(anchor) + r".{0,120}?-?\d+(?:\.\d+)?",
            text,
            re.I | re.S,
        )
    )


def is_strict_self_report(subject, detail):
    if not subject_looks_like_self_report(subject):
        return False

    text = f"{subject}\n{detail}"

    signals = sum(
        1 for anchor in FINANCIAL_ANCHORS
        if has_number_near_anchor(text, anchor)
    )

    if signals < 2:
        return False

    return any(
        has_number_near_anchor(text, anchor)
        for anchor in (
            "稅前淨利", "稅前純益", "稅前損益", "稅後淨利",
            "稅後純益", "稅後損益", "本期淨利", "歸屬母公司",
            "每股盈餘", "EPS",
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
            [r"稅前(?:淨利|純益|損益).{0,100}?(-?\d+(?:\.\d+)?)"],
            text,
        ),
        "net_income_million": first_number(
            [r"(?:歸屬母公司(?:業主)?(?:淨利|損益)|稅後(?:淨利|純益|損益)|本期淨利).{0,100}?(-?\d+(?:\.\d+)?)"],
            text,
        ),
        "revenue_million": first_number(
            [r"(?:營業收入|營收).{0,100}?(-?\d+(?:\.\d+)?)"],
            text,
        ),
    }


def merge_identity(x):
    return "|".join(
        [
            str(x.get("ticker") or ""),
            str(x.get("publish_date") or ""),
            str(x.get("publish_time") or ""),
            re.sub(r"\s+", "", str(x.get("subject") or "")),
        ]
    )


def week_bounds(date_obj):
    monday = date_obj - timedelta(days=date_obj.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def week_label(monday, friday):
    return f"{monday.month}/{monday.day}～{friday.month}/{friday.day}"


def fetch_current_openapi():
    out = []

    for market, url in (("twse", TWSE_NEWS), ("tpex", TPEX_NEWS)):
        try:
            arr = get_json(url, timeout=45)
        except Exception as e:
            print("self report OpenAPI fail", market, repr(e))
            continue

        if isinstance(arr, dict):
            arr = arr.get("data") or arr.get("records") or arr.get("result") or []

        if not isinstance(arr, list):
            continue

        for r in arr:
            ticker = str(
                p(r, ["公司代號", "證券代號", "股票代號", "代號"], "")
            ).strip()

            if not ordinary_ticker(ticker):
                continue

            subject = str(
                p(r, ["主旨", "主旨 ", "Subject"], "")
            ).strip()

            detail = str(
                p(r, ["說明", "Description", "內容"], "")
            ).strip()

            if not is_strict_self_report(subject, detail):
                continue

            publish_date = roc_to_iso(
                p(r, ["發言日期", "公告日期", "出表日期"], "")
            )

            publish_time = clean_time(
                p(r, ["發言時間", "公告時間"], "")
            )

            out.append(
                {
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
                        p(r, ["公司名稱", "證券名稱", "名稱"], "")
                    ),
                    "publish_date": publish_date,
                    "publish_time": publish_time,
                    "subject": subject,
                    "detail": detail,
                    "source": "openapi",
                    **extract_metrics(detail),
                }
            )

    return out


def new_history_session():
    s = requests.Session()

    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6",
            "Cache-Control": "no-cache",
        }
    )

    return s


def parse_company_history_html(raw, ticker, market, monday, friday):
    parser = TableParser()

    try:
        parser.feed(raw)
    except Exception:
        return []

    out = []

    for row in parser.rows:
        cells = [norm_text(x) for x in row if norm_text(x)]

        if not cells:
            continue

        joined = " | ".join(cells)

        if ticker not in joined:
            continue

        publish_date = ""

        for cell in cells:
            d = roc_to_iso(cell)
            if d:
                publish_date = d
                break

        if not publish_date:
            continue

        if not (
            monday.isoformat()
            <= publish_date
            <= friday.isoformat()
        ):
            continue

        publish_time = ""

        for cell in cells:
            if re.search(r"\d{1,2}:\d{2}(?::\d{2})?", cell):
                publish_time = clean_time(cell)
                break

        candidates = [
            cell
            for cell in cells
            if subject_looks_like_self_report(cell)
        ]

        if not candidates:
            continue

        subject = max(candidates, key=len)

        name = ""

        for i, cell in enumerate(cells):
            if cell == ticker and i + 1 < len(cells):
                cand = cells[i + 1]

                if (
                    not roc_to_iso(cand)
                    and not re.fullmatch(
                        r"\d{1,2}:\d{2}(?::\d{2})?",
                        cand
                    )
                ):
                    name = clean_name(cand)
                    break

        detail = joined

        out.append(
            {
                "id": "|".join(
                    [
                        "mops_company_history",
                        market,
                        ticker,
                        publish_date,
                        publish_time,
                        subject,
                    ]
                ),
                "market": market,
                "ticker": ticker,
                "name": name,
                "publish_date": publish_date,
                "publish_time": publish_time,
                "subject": subject,
                "detail": detail,
                "source": "mops_company_history",
                **extract_metrics(detail),
            }
        )

    return out


def fetch_one_company_history(ticker, market, monday, friday):
    roc_year = monday.year - 1911

    params = {
        "TYPEK": "all",
        "co_id": ticker,
        "encodeURIComponent": "1",
        "firstin": "1",
        "inpuType": "co_id",
        "off": "1",
        "step": "1",
        "year": str(roc_year),
    }

    for attempt in range(2):
        try:
            s = new_history_session()

            r = s.get(
                MOPS_HISTORY_URL,
                params=params,
                timeout=22,
            )

            r.raise_for_status()
            raw = r.text or ""

            if (
                len(raw) > 1000
                and "error.html" not in str(r.url)
            ):
                return parse_company_history_html(
                    raw,
                    ticker,
                    market,
                    monday,
                    friday,
                )

        except Exception:
            pass

        time.sleep(0.5 * (attempt + 1))

    return []


def load_master_map():
    master = load_json(ROOT / "data/master.json", {})

    if isinstance(master, dict):
        if isinstance(master.get("stocks"), dict):
            return master["stocks"]

        return master

    return {}


def need_weekly_backfill(week_key):
    state = load_json(BACKFILL_STATE, {})
    return state.get("completed_week") != week_key


def full_market_week_backfill(monday, friday):
    master = load_master_map()
    jobs = []

    for ticker, info in master.items():
        if not ordinary_ticker(ticker):
            continue

        market = str(info.get("market") or "").lower()

        if market not in ("twse", "tpex"):
            continue

        jobs.append((ticker, market))

    print(
        "weekly full-market backfill start",
        monday.isoformat(),
        friday.isoformat(),
        "stocks",
        len(jobs),
    )

    out = []
    done = 0

    with ThreadPoolExecutor(max_workers=8) as ex:
        future_map = {
            ex.submit(
                fetch_one_company_history,
                ticker,
                market,
                monday,
                friday,
            ): (ticker, market)
            for ticker, market in jobs
        }

        for fut in as_completed(future_map):
            ticker, market = future_map[fut]

            try:
                rows = fut.result()

                if rows:
                    out.extend(rows)
                    print("backfill hit", ticker, len(rows))

            except Exception as e:
                print(
                    "backfill worker fail",
                    ticker,
                    market,
                    repr(e),
                )

            done += 1

            if done % 100 == 0:
                print(
                    "backfill progress",
                    done,
                    "/",
                    len(jobs),
                    "hits",
                    len(out),
                )

    dedup = {}

    for x in out:
        dedup[merge_identity(x)] = x

    rows = list(dedup.values())

    print(
        "weekly full-market backfill done",
        "hits",
        len(rows),
    )

    return rows


def enrich_name_market(items):
    master = load_master_map()

    for x in items:
        m = master.get(x.get("ticker"), {})

        if not x.get("name"):
            x["name"] = clean_name(m.get("name", ""))

        if not x.get("market"):
            x["market"] = m.get("market", "")

    return items


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
        f"{x.get('name') or x['ticker']} {x['ticker']}",
        x.get("subject") or "公布自結財務資訊",
    ]

    if x.get("eps") is not None:
        lines.append(f"EPS {x['eps']:.2f} 元")

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
    today = now_tpe().date()
    monday, friday = week_bounds(today)

    current_key = monday.isoformat()
    label = week_label(monday, friday)

    hist_path = ROOT / "data/self_reports_history.json"
    sent_path = ROOT / "data/self_reports_sent.json"

    old = load_json(hist_path, {})
    merged = {}

    for x in old.get("items", []):
        d = str(x.get("publish_date") or "")

        if not (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            continue

        if not subject_looks_like_self_report(
            x.get("subject", "")
        ):
            continue

        merged[merge_identity(x)] = x

    current = fetch_current_openapi()

    for x in current:
        d = x.get("publish_date") or ""

        if (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            merged[merge_identity(x)] = x

    backfill_rows = []

    if need_weekly_backfill(current_key):
        backfill_rows = full_market_week_backfill(
            monday,
            friday,
        )

        for x in backfill_rows:
            key = merge_identity(x)

            if key not in merged:
                merged[key] = x

        save_json(
            BACKFILL_STATE,
            {
                "completed_week": current_key,
                "completed_at": now_tpe().isoformat(
                    timespec="minutes"
                ),
                "rows_found": len(backfill_rows),
                "version": VERSION,
            },
        )

    items = enrich_name_market(
        list(merged.values())
    )

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

    # 歷史回補不一次轟炸通知，只推本次即時新公告
    for x in current:
        d = x.get("publish_date") or ""

        if not (
            monday.isoformat()
            <= d
            <= friday.isoformat()
        ):
            continue

        key = merge_identity(x)

        if key in sent:
            continue

        if send_pushover(
            "自結公布",
            push_text(x),
        ):
            sent.add(key)

    updated_at = now_tpe().isoformat(
        timespec="minutes"
    )

    save_json(
        hist_path,
        {
            "week_key": current_key,
            "updated_at": updated_at,
            "version": VERSION,
            "items": items,
        },
    )

    save_json(
        sent_path,
        {
            "updated_at": updated_at,
            "ids": list(sent)[-1000:],
        },
    )

    save_json(
        ROOT / "data/self_reports.json",
        {
            "updated_at": updated_at,
            "current_week_key": current_key,
            "current_week_label": label,
            "filter_version": VERSION,
            "source_mode": (
                "OpenAPI 即時 + MOPS t05st01 全市場逐公司每週一次歷史回補"
            ),
            "backfill_this_run": len(backfill_rows),
            "weeks": [
                {
                    "key": current_key,
                    "label": label,
                    "items": items,
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
        "backfill",
        len(backfill_rows),
        "version",
        VERSION,
    )


if __name__ == "__main__":
    main()
