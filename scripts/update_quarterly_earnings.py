from sources import *
from eps_news_backup import current_items
import os, re, html, math, unicodedata, time
from html.parser import HTMLParser
from urllib.parse import urlencode
from datetime import datetime, timedelta
from pathlib import Path

SOURCE_ERRORS = []

VERSION = "2026-10-22-v11-exclude-conference-invitations"
DATA = ROOT / "data"
OUT = DATA / "quarterly_earnings.json"
SENT = DATA / "quarterly_earnings_sent.json"
HISTORY = DATA / "quarterly_earnings_history.json"

TWSE_NEWS = f"{TWSE}/opendata/t187ap04_L"
TPEX_NEWS = f"{TPEX}/mopsfin_t187ap04_O"
TWSE_IS = f"{TWSE}/opendata/t187ap06_L_ci"
TPEX_IS = f"{TPEX}/mopsfin_t187ap06_O_ci"

def clean(v):
    return re.sub(r"\s+", " ", html.unescape(str(v or ""))).strip()

def num(v):
    if v is None:
        return None
    s = unicodedata.normalize("NFKC", clean(v)).replace(",", "").replace("−", "-").replace("－", "-")
    if s in ("", "-", "--", "N/A", "nan", "None"):
        return None
    if re.fullmatch(r"\(\s*[\d,.]+\s*\)", s): s = "-" + s[1:-1].strip()
    try:
        result=float(s)
        return result if math.isfinite(result) else None
    except Exception:
        return None

def roc_date(v):
    s = clean(v)
    m = re.search(r"(?:(20\d{2})|(\d{2,3}))[/-]?(\d{2})[/-]?(\d{2})", s)
    if not m:
        return ""
    y = int(m.group(1) or m.group(2))
    if y < 1911:
        y += 1911
    return f"{y:04d}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"

def period_from_text(s, fallback_date=""):
    s = clean(s).replace("年度第", "年第")
    patterns = [
        r"(?:(20\d{2})|(\d{2,3}))\s*年?\s*第?\s*([1-4一二三四])\s*季",
        r"(?:(20\d{2})|(\d{2,3}))\s*Q\s*([1-4])",
    ]
    for pat in patterns:
        m = re.search(pat, s, re.I)
        if m:
            y = int(m.group(1) or m.group(2))
            if y < 1911:
                y += 1911
            qtxt = m.group(3)
            q = {"一": 1, "二": 2, "三": 3, "四": 4}.get(
                qtxt,
                int(qtxt) if qtxt.isdigit() else 0,
            )
            return f"{y}-Q{q}"

    annual=re.search(r"(?:(20\d{2})|(\d{2,3}))\s*年(?:度)?(?:合併|個體|個別)?財務(?:報告|報表)", s)
    if annual:
        y=int(annual.group(1) or annual.group(2)); return f"{y+1911 if y<1911 else y}-Q4"
    half=re.search(r"(?:(20\d{2})|(\d{2,3}))\s*年(?:度)?上半年", s)
    if half:
        y=int(half.group(1) or half.group(2)); return f"{y+1911 if y<1911 else y}-Q2"

    m=re.search(r'(?<!\w)([1-4])Q\s*(20\d{2}|\d{2})(?!\w)',s,re.I)
    if m:
        year=int(m[2]); return f'{year+2000 if year<100 else year}-Q{m[1]}'
    return ""

def previous(p):
    y = int(p[:4])
    q = int(p[-1])
    return f"{y-1}-Q4" if q == 1 else f"{y}-Q{q-1}"

# This tab uses official technology industries UNION the user's heatmap members
# 36 is digital/cloud; 32 is cultural/creative, not a technology industry
EARNINGS_TECH_CODES = {"24", "25", "26", "27", "28", "29", "30", "31", "36"}
EARNINGS_TECH_NAMES = {"半導體", "電腦及週邊設備", "光電", "通信網路", "電子零組件", "電子通路", "資訊服務", "其他電子", "數位雲端", "電子商務"}

def select_earnings_universe(master, sectors):
    members = {str(row.get('ticker', '')).strip()
               for sec in sectors.get('sectors', []) for row in sec.get('stocks', [])}
    out = {}
    for ticker, meta in master.items():
        ticker = str(ticker).strip()
        if not isinstance(meta, dict) or meta.get('market') not in ('twse','tpex'):
            continue
        if not re.fullmatch(r'[1-9]\d{3}', ticker):
            continue
        industry = str(meta.get('industry') or '').strip()
        if industry.isdigit(): industry=industry.zfill(2)
        industry_name=industry.removesuffix('業')
        if ticker in members or industry in EARNINGS_TECH_CODES or industry_name in EARNINGS_TECH_NAMES:
            out[ticker] = clean(meta.get('name') or ticker)
    return out

def fetch_universe():
    # Cached official company metadata is retained if one market's API is unavailable
    cached=load_json(DATA/'master.json',{}).get('stocks',{})
    master=dict(cached) if isinstance(cached,dict) else {}
    try:
        fresh=fetch_master()
        if isinstance(fresh,dict):
            master.update({str(t):m for t,m in fresh.items() if isinstance(m,dict)})
    except Exception as exc:
        SOURCE_ERRORS.append('company_universe:'+type(exc).__name__)
    sectors=load_json(DATA/'sectors.json',{})
    if not isinstance(sectors.get('sectors'),list) or not sectors['sectors']:
        raise RuntimeError('heatmap sectors unavailable: refusing to publish an incomplete stock universe')
    for market in ('twse','tpex'):
        if not any(isinstance(m,dict) and m.get('market')==market for m in master.values()):
            raise RuntimeError('company universe unavailable: '+market)
    out=select_earnings_universe(master,sectors)
    if not out:
        raise RuntimeError('empty earnings universe: refusing to include all industries')
    return out

def rows_from_api(url):
    a = get_json(url, timeout=60)
    if isinstance(a, dict):
        a = next(
            (
                a[k]
                for k in ("data", "records", "result")
                if isinstance(a.get(k), list)
            ),
            [],
        )
    return a if isinstance(a, list) else []

def fetch_news():
    out = []

    for market, url in (
        ("twse", TWSE_NEWS),
        ("tpex", TPEX_NEWS),
    ):
        try:
            rows = rows_from_api(url)
        except Exception as e:
            print("news fail", market, type(e).__name__)
            SOURCE_ERRORS.append("news/"+market+":"+type(e).__name__)
            continue

        for r in rows:
            t = str(
                pick(
                    r,
                    ["公司代號", "證券代號", "股票代號"],
                    "",
                )
            ).strip()

            if not re.fullmatch(r"\d{4}", t):
                continue

            out.append(
                {
                    "ticker": t,
                    "market": market,
                    "name": clean(
                        pick(
                            r,
                            ["公司名稱", "證券名稱"],
                            "",
                        )
                    ),
                    "subject": clean(
                        pick(
                            r,
                            ["主旨", "Subject"],
                            "",
                        )
                    ),
                    "date": roc_date(
                        pick(
                            r,
                            ["發言日期", "公告日期", "Date"],
                            "",
                        )
                    ),
                    "time": clean(
                        pick(
                            r,
                            ["發言時間", "公告時間", "Time"],
                            "",
                        )
                    ),
                    "raw": r,
                }
            )

    return out

def extract_planned_date(subject, announce_date):
    s=re.sub(r"\s+", "", clean(subject))
    date_pattern=r"(?:(20\d{2})|(\d{2,3}))\s*[年/.-]\s*(\d{1,2})\s*[月/.-]\s*(\d{1,2})"
    # Only dates explicitly attached to the planned board meeting
    patterns=[r"(?:董事會(?:預計)?召開日期|董事會召集日期|預計(?:召開)?董事會日期)\s*[:：為]?\s*"+date_pattern,
              r"預計於\s*"+date_pattern+r"日?\s*(?:召開|提報|舉行)"]
    for pattern in patterns:
        m=re.search(pattern,s)
        if m:
            y=int(m.group(1) or m.group(2)); y=y+1911 if y<1911 else y
            try: return datetime(y,int(m.group(3)),int(m.group(4))).date().isoformat()
            except ValueError: return ""
    return ""

def is_preview_subject(s):
    s = re.sub(r"\s+", "", clean(s))
    if re.search(r"代.*子公司", s): return False
    if re.search(r"財務(?:報告|報表)",s) and re.search(r"董事會(?:預計)?召開日期|董事會召集日期",s): return True

    if not (
        "財務報告" in s
        or "財務報表" in s
    ):
        return False

    if any(
        k in s
        for k in (
            "通過",
            "決議",
            "提報董事會通過",
        )
    ):
        return False

    return any(
        k in s
        for k in (
            "董事會預計召開",
            "董事會召開日期",
            "董事會召集日期",
            "預計召開董事會",
            "預計提報董事會",
            "預計於",
        )
    )

def is_investor_invitation(subject):
    """Conference invitations/schedules are not quarterly earnings releases."""
    s = re.sub(r"\s+", "", clean(subject))
    return bool(re.search(
        r"受邀|應邀|邀請|參加|出席|舉辦|辦理|將於|預計|預告|召開|召集", s
    ))


def is_report_subject(s):
    s = re.sub(r"\s+", "", clean(s))
    if is_preview_subject(s) or is_investor_invitation(s) or re.search(
        r"代.*子公司|更正|重編|差異|預測|無法|未通過|會計政策", s
    ):
        return False
    formal = bool(re.search(r"財務(?:報告|報表)", s) and re.search(r"公告|通過|決議", s))
    quarterly = bool(
        period_from_text(s)
        and re.search(r"(?:合併)?(?:損益|財務業績|財務結果|營運結果|營運成果|財報|財務報告|財務報表)", s)
        and re.search(r"公告|公布|發布|揭露|自結|結算|通過|決議|說明會摘要|法說會摘要", s)
    )
    return formal or quarterly


def is_result_candidate(subject):
    if is_investor_invitation(subject):
        return False
    return is_report_subject(subject) or bool(re.search(
        r"(?:今日)?(?:法人說明會|法說會).*(?:摘要|結果|財務資訊)", clean(subject)
    ))


def is_quarterly_release(subject, text):
    if not is_result_candidate(subject):
        return False
    if is_report_subject(subject):
        return True
    return bool(period_from_text(text)) and bool(re.search(
        r"合併.*(?:財務|損益)|每股.*(?:盈餘|純益)|EPS", text, re.I
    ))


def valid_cached_earnings_report(x):
    """Drop stale false positives from persisted events on every update."""
    subject = x.get('subject', '')
    # IR PDF releases and news-backup results are independently verified sources.
    if x.get('release_type') == 'issuer_conference' or x.get('source') == 'news_backup':
        return True
    return not is_investor_invitation(subject)


def announcement_period_metrics(text, period):
    """Read period-labelled MOPS financial rows, without relying on fixed wording.

    Only a clearly labelled current-quarter column may supply direct EPS or
    gross margin. Cumulative-only releases continue through event_cumulative.
    """
    raw=unicodedata.normalize('NFKC', html.unescape(str(text or '')))
    flat=clean(raw).replace('－','-').replace('–','-').replace('—','-').replace('～','-')
    year,quarter=int(period[:4]),int(period[-1])
    first,last=3*quarter-2,3*quarter
    yy=rf'(?:{year}|{year-1911})'
    single_headers=[
        rf'{yy}\s*年?\s*{first}\s*[-~至/]\s*{last}\s*月',
        rf'{yy}\s*年(?:度)?\s*第?{quarter}\s*季\s*(?:單季|當季)',
    ]
    # A quarter mentioned only in the title is NOT evidence that the figures
    # are single-quarter; require a period-labelled financial table header.
    if not any(re.search(p,flat,re.I) for p in single_headers): return {}
    # Detect the order of period columns. A current quarter must precede the
    # next cumulative column, or appear alone. Reject ambiguous headers.
    cum_pat=rf'{yy}\s*年?\s*1\s*[-~至/]\s*{last}\s*月'
    sh=[m for pat in single_headers for m in re.finditer(pat,flat,re.I)]
    cm=list(re.finditer(cum_pat,flat,re.I))
    if not sh or (cm and min(m.start() for m in cm)<min(m.start() for m in sh)):
        return {}
    # MOPS renders a row-major table; its HTML may already have been flattened.
    # Match each financial label and stop at the next label to prevent pulling
    # a number from an unrelated row.
    labels={
        'eps':r'基本每股(?:盈餘|純益)(?:\s*\([^)]*\))*',
        'revenue':r'(?:合併)?營業收入(?:淨額|合計)?',
        'gross':r'(?:合併)?營業毛利(?:\s*\([^)]*\))?',
    }
    any_label=re.compile('|'.join(r'(?:'+x+r')' for x in labels.values()),re.I)
    numbers={}
    for key,pattern in labels.items():
        vals=[]
        for m in re.finditer(pattern,flat,re.I):
            tail=flat[m.end():]
            next_label=any_label.search(tail)
            if next_label: tail=tail[:next_label.start()]
            # A short row may contain a unit, colon, and several period columns.
            tail=tail[:150]
            if re.search(r'去年|上年|同比|年增|變動|增減',tail[:20]): continue
            found=re.findall(r'(?<![\dA-Za-z])\(?[+-]?\d[\d,]*(?:\.\d+)?\)?(?![\dA-Za-z])',tail)
            if not found: continue
            v=num(found[0]);
            if v is not None: vals.append(v)
        if len(set(vals))==1 and vals: numbers[key]=vals[0]
    out={}
    if 'eps' in numbers: out['eps']=numbers['eps']
    if numbers.get('revenue',0)>0 and 'gross' in numbers:
        margin=numbers['gross']/numbers['revenue']*100
        if -100<=margin<=100: out['gross_margin']=margin
    return out


def direct_quarter_metrics(text, period):
    """Only explicit single-quarter values; never segment margin or YTD EPS."""
    text = unicodedata.normalize('NFKC', clean(text))
    y, q = int(period[:4]), int(period[-1])
    quarter = rf"(?:{y}|{y-1911})\s*年(?:度)?\s*第?\s*(?:{q}|{'一二三四'[q-1]})\s*季"
    result = {}
    # A year/quarter immediately preceding EPS prevents subsidiary contribution EPS
    # and '前三季累計' being mistaken for this quarter.
    for label, key in [(r'(?:基本)?每股(?:稅後)?(?:盈餘|純益)|EPS', 'eps'), (r'(?:合併)?毛利率', 'gross_margin')]:
        pattern = quarter + r"(?:自結|合併|單季|本公司|之|的|\s)*" + r"(?:" + label + r")\s*[:：為達約]?\s*(?:新[臺台]幣)?\s*([+-]?[\d,]+(?:\.\d+)?)"
        values = {num(m.group(1)) for m in re.finditer(pattern, text, re.I)}
        values.discard(None)
        if len(values) == 1: result[key] = values.pop()
    return result


def cached_official_announcements(now):
    """Read-only recovery from the existing official announcement cache."""
    from urllib.parse import urlparse
    out = []
    for row in load_json(DATA/'self_reports_history.json', {}).get('items', []):
        date = row.get('publish_date', '')
        if not (now.date()-timedelta(days=14)).isoformat() <= date <= now.date().isoformat(): continue
        url = row.get('source_url', '')
        if urlparse(url).hostname not in ('mops.twse.com.tw', 'mopsov.twse.com.tw'): continue
        if not is_report_subject(row.get('subject', '')): continue
        out.append(dict(ticker=row['ticker'], name=row.get('name', ''), date=date,
                        time=row.get('publish_time', ''), subject=row['subject'],
                        raw={'說明':row.get('detail', '')}, source_url=url))
    return out


def financial_snapshot():
    rows = []

    for market, url in (
        ("twse", TWSE_IS),
        ("tpex", TPEX_IS),
    ):
        try:
            a = rows_from_api(url)
        except Exception as e:
            print("financial fail", market, type(e).__name__)
            SOURCE_ERRORS.append("financial/"+market+":"+type(e).__name__)
            continue

        for r in a:
            t = str(
                pick(
                    r,
                    ["公司代號", "證券代號"],
                    "",
                )
            ).strip()

            yy = pick(r, ["年度", "Year"], "")
            qq = pick(r, ["季別", "Season"], "")

            if (
                not re.fullmatch(r"\d{4}", t)
                or yy in ("", None)
                or qq in ("", None)
            ):
                continue

            try:
                y = int(
                    float(
                        str(yy).replace(",", "")
                    )
                )
                if y < 1911:
                    y += 1911

                q = int(
                    float(
                        str(qq).replace(",", "")
                    )
                )
            except Exception:
                continue

            rows.append(
                {
                    "ticker": t,
                    "market": market,
                    "period": f"{y}-Q{q}",
                    "cum_revenue": num(
                        pick(
                            r,
                            [
                                "營業收入",
                                "營業收入合計",
                                "Revenue",
                            ],
                            None,
                        )
                    ),
                    "cum_gross": num(
                        pick(
                            r,
                            [
                                "營業毛利（毛損）淨額",
                                "營業毛利（毛損）",
                                "營業毛利(毛損)",
                                "營業毛利",
                                "GrossProfit",
                            ],
                            None,
                        )
                    ),
                    "cum_eps": num(
                        pick(
                            r,
                            [
                                "基本每股盈餘（元）",
                                "基本每股盈餘(元)",
                                "基本每股盈餘",
                                "BasicEarningsPerShare",
                            ],
                            None,
                        )
                    ),
                }
            )

    return rows

def merge_history(snapshot):
    hist = load_json(
        HISTORY,
        {"rows": []},
    )

    by = {}

    for r in hist.get("rows", []):
        if (
            r.get("ticker")
            and r.get("period")
        ):
            by[
                (
                    r["ticker"],
                    r["period"],
                )
            ] = r

    for r in snapshot:
        key=(r["ticker"],r["period"])
        by[key]={**by.get(key,{}),**{k:v for k,v in r.items() if v is not None}}

    rows = list(by.values())

    rows.sort(
        key=lambda x: (
            x.get("period", ""),
            x.get("ticker", ""),
        )
    )

    save_json(
        HISTORY,
        {
            "version": VERSION,
            "updated_at": now_tpe().isoformat(
                timespec="minutes"
            ),
            "rows": rows,
        },
    )

    return by

def single_metrics(by, t, p):
    r = by.get((t, p))

    if not r:
        return {
            "eps": None,
            "gross_margin": None,
        }

    q = int(p[-1])

    rev = r.get("cum_revenue")
    gp = r.get("cum_gross")
    ceps = r.get("cum_eps")

    if q == 1:
        srev = rev
        sgp = gp
        seps = ceps

    else:
        pp = previous(p)
        pr = by.get((t, pp))

        if not pr:
            return {
                "eps": r.get('single_eps'),
                "gross_margin": None,
            }

        srev = (
            rev - pr.get("cum_revenue")
            if (
                rev is not None
                and pr.get("cum_revenue") is not None
            )
            else None
        )

        sgp = (
            gp - pr.get("cum_gross")
            if (
                gp is not None
                and pr.get("cum_gross") is not None
            )
            else None
        )

        seps = r.get("single_eps")
        if seps is None and ceps is not None and pr.get("cum_eps") is not None:
            seps = round(ceps-pr["cum_eps"], 6)

    gm = (
        sgp / srev * 100
        if (
            sgp is not None
            and srev not in (None, 0)
        )
        else None
    )

    return {
        "eps": seps,
        "gross_margin": gm,
        "eps_basis": "reported_single" if q==1 or r.get("single_eps") is not None else "cumulative_difference",
    }

def f(v, s=""):
    return (
        "待官方公布"
        if v is None
        else f"{float(v):.2f}{s}"
    )

def tg(text):
    token = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip()

    chat = os.getenv(
        "TELEGRAM_CHAT_ID",
        "",
    ).strip()

    if not token or not chat:
        return False

    r = S.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={
            "chat_id": chat,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    r.raise_for_status()
    return r.json().get("ok") is True

# Historical records use the same cumulative basis as the official income table
class FinancialTableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=[]; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag=='tr': self.row=[]
        if tag in ('td','th'): self.cell=[]
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(clean(' '.join(self.cell))); self.cell=None
        if tag=='tr' and self.row: self.rows.append(self.row); self.row=[]


def historical_rows(page, period, market):
    page_text=clean(re.sub('<[^>]+>',' ',page))
    roc=int(period[:4])-1911; quarter=int(period[-1])
    # This endpoint echoes quarter in Chinese but does not echo year in its result HTML
    # Year is bound to the explicit POST request, never taken from a latest snapshot
    qword={1:'一',2:'二',3:'三',4:'四'}[quarter]
    if not (re.search(rf"{roc}\s*年\s*第?\s*0?{quarter}\s*季",page_text) or re.search(rf"公司第{qword}季資料",page_text)):
        return []
    parser=FinancialTableParser(); parser.feed(page); header=None; out=[]
    for row in parser.rows:
        row=[re.sub(r'\s+','',c) for c in row]
        if any('公司代號' in c for c in row) and any('每股盈餘' in c for c in row):
            header=row; continue
        if not header or len(row)!=len(header): continue
        record=dict(zip(header,row))
        ticker=next((v for k,v in record.items() if '公司代號' in k),'')
        if not re.fullmatch(r'\d{4}',ticker): continue
        def val(words):
            return next((num(v) for k,v in record.items() if any(w in k.replace(' ','') for w in words)),None)
        out.append(dict(ticker=ticker,market=market,period=period,
                        cum_eps=val(['基本每股盈餘']),cum_revenue=val(['營業收入']),
                        cum_gross=val(['營業毛利（毛損）淨額']) if any('營業毛利（毛損）淨額' in k for k in record) else val(['營業毛利']),source='mops_t163sb04'))
    return out


def backfill_history(by, periods, targets=None):
    errors=[]
    # Each market/quarter is one full-market query, not one request per company
    for period in sorted(periods):
        for market,kind in [('twse','sii'),('tpex','otc')]:
            existing=[r for (t,p),r in by.items() if p==period and r.get('market')==market]
            needed=(targets or {}).get(period,set())
            if needed and all((t,period) in by and all(by[(t,period)].get(k) is not None for k in ('cum_eps','cum_revenue','cum_gross')) for t in needed): continue
            payload=dict(encodeURIComponent='1',step='1',firstin='1',off='1',isQuery='Y',TYPEK=kind,year=str(int(period[:4])-1911),season=f'{int(period[-1]):02d}')
            success=False
            for base in ['https://mopsov.twse.com.tw','https://mops.twse.com.tw']:
                try:
                    res=S.post(base+'/mops/web/ajax_t163sb04',data=payload,timeout=(10,30))
                    res.raise_for_status(); res.encoding='utf-8'
                    records=historical_rows(res.text,period,market)
                    if not records: raise ValueError('historical table unavailable or schema mismatch')
                    for r in records: by[(r['ticker'],period)]={**by.get((r['ticker'],period),{}),**{k:v for k,v in r.items() if v is not None}}
                    success=True; break
                except Exception as exc: error=type(exc).__name__
            if not success: errors.append(f'{market}/{period}: {error}')
    return errors


def announcement_text(x):
    raw=x.get('raw',{})
    return clean(' '.join([x.get('subject',''),str(pick(raw,['說明','內容','Description'],''))]))


def daily_mops_news():
    # Daily MOPS is generally fresher than the OpenAPI feed
    from update_self_reports import parse_rows, extract_detail_params
    out=[]
    for base in ['https://mopsov.twse.com.tw','https://mops.twse.com.tw']:
        try:
            r=S.post(base+'/mops/web/ajax_t05sr01_1',data={'step':'0','firstin':'true','TYPEK':'all'},timeout=(10,30))
            r.raise_for_status();r.encoding='utf-8'
            for row in parse_rows(r.text):
                m=re.match(r'(\d{4})\s+(.+?)\s+(\d{2,3}/\d{1,2}/\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(.+)',row['text'])
                if not m: continue
                ticker,name,day,clock,subject=m.groups()
                if not (is_preview_subject(subject) or is_result_candidate(subject)): continue
                date=roc_date(day); params=extract_detail_params(row['attrs'],ticker,date,clock)
                if not params.get('seq_no'): continue
                payload=dict(firstin='true',TYPEK='all',step='1',COMPANY_ID=ticker,SPOKE_DATE=date.replace('-',''),SPOKE_TIME=clock.replace(':',''),SEQ_NO=params['seq_no'])
                payload['skey']=params.get('skey') or ticker+date.replace('-','')+params['seq_no']
                detail=S.post(base+'/mops/web/ajax_t05sr01_1',data=payload,timeout=(10,30))
                detail.raise_for_status();detail.encoding='utf-8'
                page=re.sub(r'<script\b[^>]*>.*?</script>','',detail.text,flags=re.S|re.I)
                text=clean(re.sub('<[^>]+>',' ',page))
                if ticker not in text or day not in text: continue
                out.append(dict(ticker=ticker,name=name,date=date,time=clock,subject=subject,raw={'說明':text},source_url=base+'/mops/web/ajax_t05sr01_1?'+urlencode(payload)))
            if out or '公司代號' in r.text: break
        except Exception as exc:
            print('daily MOPS',type(exc).__name__)
            SOURCE_ERRORS.append('daily_mops:'+type(exc).__name__)
    return out


SCAN_STATUS = {}

def historical_mops_news():
    """Recover announcements missed between runs; scan all companies, not theme lists."""
    from update_self_reports import parse_rows, extract_detail_params, mops_headers
    state_path=DATA/'quarterly_earnings_scan.json'
    state=load_json(state_path,{})
    today=now_tpe().date()
    try: start=datetime.strptime(state.get('through',''),'%Y-%m-%d').date()-timedelta(days=3)
    except ValueError: start=today-timedelta(days=45)
    start=max(min(start,today-timedelta(days=14)),today-timedelta(days=90))
    out=[]; successful=True; cursor=start; started=time.monotonic()
    while cursor<=today:
        if time.monotonic()-started > 180:
            successful=False;SOURCE_ERRORS.append('announcement_scan:time_budget');break
        import calendar
        end=min(today,cursor.replace(day=calendar.monthrange(cursor.year,cursor.month)[1]))
        ok=False; last_error='no validated response'
        for base in ['https://mopsov.twse.com.tw','https://mops.twse.com.tw']:
            try:
                payload={'firstin':'1','step':'1','off':'1','TYPEK':'all','year':str(cursor.year-1911),
                         'month':str(cursor.month),'b_date':str(cursor.day),'e_date':str(end.day),
                         'keyword4':'','co_id':'','queryName':'co_id'}
                r=S.post(base+'/mops/web/ajax_t05st01',data=payload,headers=mops_headers(),timeout=(10,35))
                r.raise_for_status();r.encoding='utf-8'
                page=r.text
                if not ('公司代號' in page and ('主旨' in page or '發言日期' in page)):
                    if re.search(r'查無資料|查無所需資料',page): ok=True;break
                    raise ValueError('announcement schema unavailable')
                rows=parse_rows(page); dated=0
                for row in rows:
                    if time.monotonic()-started > 180: raise TimeoutError('announcement scan time budget; will retry next run')
                    text=row['text']
                    # Header and nested outer table rows must not be mistaken for announcements
                    m=re.match(r'\s*(\d{4})\s+(.*?)\s+((?:\d{3}|20\d{2})/\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2}:\d{2})\s+(.+)',text)
                    if not m: continue
                    t,name,day,clock,title=m.groups()
                    parts=[int(v) for v in day.split('/')];parts[0]+=1911 if parts[0]<1911 else 0
                    date=datetime(*parts).date().isoformat()
                    if not cursor.isoformat()<=date<=end.isoformat(): continue
                    dated+=1
                    if not (is_preview_subject(title) or is_result_candidate(title)): continue
                    if is_result_candidate(title) and date < (today-timedelta(days=14)).isoformat(): continue
                    known=extract_planned_date(title,date)
                    if is_preview_subject(title) and known and known < today.isoformat(): continue
                    params=extract_detail_params(row['attrs'],t,date,clock)
                    detail='';url=base+'/mops/web/t05st01?'+urlencode({'co_id':t,'year':str(parts[0]-1911)})
                    if params.get('seq_no'):
                        dp=dict(firstin='true',TYPEK='all',step='1',COMPANY_ID=t,SPOKE_DATE=date.replace('-',''),SPOKE_TIME=clock.replace(':',''),SEQ_NO=params['seq_no'])
                        dp['skey']=params.get('skey') or t+dp['SPOKE_DATE']+dp['SEQ_NO']
                        try:
                            dr=S.post(base+'/mops/web/ajax_t05sr01_1',data=dp,headers=mops_headers(),timeout=(10,25))
                            dr.raise_for_status();dr.encoding='utf-8'
                            detail=clean(re.sub('<[^>]+>',' ',dr.text))
                            if t not in detail: detail=''
                            else: url=base+'/mops/web/ajax_t05sr01_1?'+urlencode(dp)
                        except Exception:
                            successful=False;SOURCE_ERRORS.append('detail/'+t+'/'+date)
                    if is_preview_subject(title) and not extract_planned_date(title+' '+detail,date):
                        successful=False;SOURCE_ERRORS.append('planned_date/'+t+'/'+date+':unavailable')
                    out.append(dict(ticker=t,name=name,date=date,time=clock,subject=title,raw={'說明':detail},source_url=url))
                if not dated: raise ValueError('no dated announcement rows parsed')
                ok=True;break
            except Exception as exc: last_error=type(exc).__name__+':'+str(exc)[:120]
        label=cursor.isoformat()+'~'+end.isoformat()
        SCAN_STATUS[label]='ok' if ok else 'failed'
        if not ok:
            successful=False;SOURCE_ERRORS.append('announcement_scan/'+label+':'+last_error)
        cursor=end+timedelta(days=1)
    if successful: state['through']=today.isoformat()
    state['attempted_at']=now_tpe().isoformat(timespec='minutes');state['coverage']=dict(SCAN_STATUS)
    save_json(state_path,state)
    return out


def event_cumulative(x, period):
    text=announcement_text(x)
    # Board-result announcements explicitly report YTD, not single-quarter values
    if not re.search(r'累計',text): return None
    def find(labels):
        for label in labels:
            m=re.search(label+r'\s*(?:[（(][^）)]*[）)])?\s*[:：]\s*([+-]?[\d,]+(?:\.\d+)?)',text)
            if m: return num(m.group(1))
        return None
    eps=find([r'(?:截至本期止)?累計基本每股盈餘(?:[（(]損失[）)])?',r'基本每股盈餘(?:[（(]損失[）)])?'])
    revenue=find([r'(?:報導期間)?累計營業收入',r'營業收入'])
    gross=find([r'(?:報導期間)?累計營業毛利(?:[（(]毛損[）)])?',r'營業毛利(?:[（(]毛損[）)])?'])
    if not re.search(r"(?:單位.{0,8}[千仟]元|營業收入.{0,12}[千仟]元)",text):
        revenue=gross=None
    if eps is None and revenue is None: return None
    return dict(ticker=x['ticker'],period=period,market=x.get('market',''),cum_eps=eps,cum_revenue=revenue,cum_gross=gross,source='board_announcement',source_url=x.get('source_url',''))


def closed_dates(year):
    key=str(year)
    cached=load_json(DATA/'earnings_calendar.json',{'years':{}})
    try:
        payload=get_json(f'https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?response=json&queryYear={year-1911}',timeout=30)
        if str(payload.get('date',''))[:4]!=key or not payload.get('data'): raise ValueError('calendar year mismatch')
        dates=[]
        for row in payload['data']:
            if re.search(r'開始交易|最後交易',str(row[1])): continue
            dates.append(row[0])
        cached.setdefault('years',{})[key]=dates;save_json(DATA/'earnings_calendar.json',cached)
        return set(dates)
    except Exception:
        if key in cached.get('years',{}): return set(cached['years'][key])
        return None


def expiry_date(publish_date, calendars):
    day=datetime.strptime(publish_date,'%Y-%m-%d').date();count=0
    for _ in range(40):
        day+=timedelta(days=1)
        if day.year not in calendars: calendars[day.year]=closed_dates(day.year)
        closed=calendars[day.year]
        if closed is None: return None  # Never assume public holidays are trading days
        if day.weekday()<5 and day.isoformat() not in closed:
            count+=1
            if count==1: return day.isoformat()
    return None


def report_visible(event, now, calendars):
    expiry=expiry_date(event['publish_date'],calendars)
    event['expires_at']=expiry+'T18:00:00+08:00' if expiry else None
    event['retention_status']='exchange_calendar' if expiry else 'calendar_unavailable'
    return expiry is None or now.date().isoformat()<expiry or (now.date().isoformat()==expiry and now.hour<18)


def save_financial_history(by):
    save_json(HISTORY,{'version':VERSION,'updated_at':now_tpe().isoformat(timespec='minutes'),'rows':sorted(by.values(),key=lambda x:(x['period'],x['ticker']))})


def notify_earnings(upcoming, reports, now, source_incomplete=False):
    """Shared cron runner, Taiwan time; successful deliveries are checkpointed separately."""
    sent=set(load_json(SENT,{'ids':[]}).get('ids',[]))
    def checkpoint():
        save_json(SENT,{'updated_at':now.isoformat(timespec='minutes'),'ids':sorted(sent)})
    def deliver(key, text):
        if key in sent: return True
        try:
            if not tg(text): return False
        except Exception as exc:
            print('Telegram delivery failed:',type(exc).__name__)
            return False
        sent.add(key);checkpoint();return True

    today=now.date().isoformat()
    digest_key='morning|'+today
    # First run at/after 08:30; allow delayed Actions / retry until market close
    minute=now.hour*60+now.minute
    if 510 <= minute < 810 and digest_key not in sent:
        due=sorted([x for x in upcoming if x.get('planned_date')==today],key=lambda x:(x['ticker'],x['period']))
        # No empty messages. Incomplete sources are not interpreted as no announcements
        if due:
            remaining=[x for x in due if f"morning-item|{today}|{x['ticker']}|{x['period']}" not in sent]
            ok=True
            for offset in range(0,len(remaining),35):
                part=remaining[offset:offset+35]
                text='📅 今日預計開財報｜'+today+'\n'
                text+='\n'.join(f"• {x['name']} {x['ticker']}｜{x['period']}" for x in part)
                text+='\n\n依公司公告的財報董事會或季度法說日期整理，未公告時間者不預設為盤後'
                if source_incomplete: text+='\n部分來源未完成，以上為已確認名單'
                try: delivered=tg(text)
                except Exception as exc:
                    print('Telegram morning delivery failed:',type(exc).__name__);delivered=False
                if not delivered:
                    ok=False;break
                for x in part: sent.add(f"morning-item|{today}|{x['ticker']}|{x['period']}")
                checkpoint()
            if ok: sent.add(digest_key);checkpoint()
        elif not source_incomplete:
            sent.add(digest_key);checkpoint()

    for x in reports:
        # Keep legacy ID format so already delivered reports are not sent again
        key=f"report|{x['ticker']}|{x['period']}|{x['publish_date']}"
        if (key in sent or any(i.startswith(f"report|{x['ticker']}|{x['period']}|") for i in sent)) or all(x.get(k) is None for k in ('gross_margin','eps')):
            continue
        text=(f"📊 {x['name']} {x['ticker']}｜財報公布\n"
              f"上一季 {x['prev_period']}\n毛利率：{f(x['prev_gross_margin'],'%')}\nEPS：{f(x['prev_eps'])} 元\n\n"
              f"本季 {x['period']}\n毛利率：{f(x['gross_margin'],'%')}\nEPS：{f(x['eps'])} 元")
        if x.get('release_type')=='quarterly_preliminary': text+='\n公司公布之季度初步業績（自結／未核閱）'
        if x.get('eps_news_source'):
            text+='\nEPS 來源：新聞備援｜'+x['eps_news_source'].get('source_label','')
            text+='\n'+x['eps_news_source'].get('source_url','')
        if x.get('source_url'): text+='\n'+x['source_url']
        if x.get('release_type')=='issuer_conference': text+='\n來源：公司官方法說資料（非核閱報告）'
        if 'cumulative_difference' in (x.get('eps_basis'),x.get('prev_eps_basis')):
            text+='\n\nEPS 含累計差額推算值'
        deliver(key,text)
    checkpoint()


# Company IR adapters supplement MOPS board announcements. Values are NEVER seeded
# from news or inferred from a scheduled meeting alone.
class IRTableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.depth=0
    def handle_starttag(self, tag, attrs):
        if tag=='tr':
            if self.row is None: self.row={'text':[], 'links':[]}
            self.depth+=1
        if self.row is not None and tag=='a':
            href=dict(attrs).get('href','')
            if href: self.row['links'].append(href)
    def handle_data(self, data):
        if self.row is not None: self.row['text'].append(data)
    def handle_endtag(self, tag):
        if tag=='tr' and self.row is not None:
            self.depth-=1
            if self.depth==0:
                self.row['text']=clean(' '.join(self.row['text']))
                self.rows.append(self.row); self.row=None


def ir_meeting_date(text, year):
    match=re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})',text)
    if match:
        try: return datetime(*map(int,match.groups())).date().isoformat()
        except ValueError: return None
    match=re.search(r'(\d{1,2}|[一二三四五六七八九十]{1,3})月(\d{1,2}|[一二三四五六七八九十]{1,3})日',text)
    if not match: return None
    def integer(s):
        if s.isdigit(): return int(s)
        digits={c:i for i,c in enumerate('零一二三四五六七八九')}
        if '十' in s:
            a,b=s.split('十'); return (digits.get(a,1)*10)+digits.get(b,0)
        return digits.get(s,0)
    try: return datetime(year,integer(match[1]),integer(match[2])).date().isoformat()
    except ValueError: return None


def ir_meeting_clock(text):
    m=re.search(r'(?:下午|上午)?\s*(\d{1,2})[:：](\d{2})',text)
    if m:
        hour,minute=map(int,m.groups())
        if '下午' in m[0] and hour<12: hour+=12
        if '上午' in m[0] and hour==12: hour=0
        if hour<24 and minute<60: return f'{hour:02d}:{minute:02d}:00'
    # Official Chinese calendar wording, e.g. 下午兩點三十分
    m=re.search(r'(上午|下午)([一二兩三四五六七八九十]+)點([一二三四五六七八九十]+分|半|整)?',text)
    if not m: return None
    def integer(value):
        value=value.replace('兩','二'); digits={c:i for i,c in enumerate('零一二三四五六七八九')}
        if '十' in value:
            a,b=value.split('十'); return digits.get(a,1)*10+digits.get(b,0)
        return digits.get(value,0)
    hour=integer(m[2]);minute=30 if m[3]=='半' else integer((m[3] or '').removesuffix('分'))
    if m[1]=='下午' and hour<12: hour+=12
    if m[1]=='上午' and hour==12: hour=0
    return f'{hour:02d}:{minute:02d}:00' if hour<24 and minute<60 else None


def ir_quarter_headers(line):
    # Only explicit single-quarter column headers, never 9M/YTD/annual headings
    pattern=r'(?<!\w)(?:(20\d{2})\s*[-/]?\s*Q([1-4])|([1-4])Q\s*(20\d{2}|\d{2})|Q([1-4])\s*(20\d{2}))(?!\w)'
    result=[]
    for m in re.finditer(pattern,line,re.I):
        if m[1]: year,q=int(m[1]),int(m[2])
        elif m[3]: year,q=int(m[4]),int(m[3]); year+=2000 if year<100 else 0
        else: year,q=int(m[6]),int(m[5])
        result.append(f'{year}-Q{q}')
    return result


def ir_pdf_metrics(pages):
    # Fail closed if headers/values cannot be aligned. Reject estimates/outlook.
    metrics={}
    if not re.search(r'Largan|大立光','\n'.join(pages),re.I): return {}
    for page in pages:
        if re.search(r'forecast|guidance|預估|預測',page,re.I): continue
        headers=[]
        for line in page.splitlines():
            found=ir_quarter_headers(line)
            if found:
                headers=[] if re.search(r'forecast|estimate|guidance|預估|預測',line,re.I) else found
                continue
            if not headers: continue
            field=None; values=[]
            if re.search(r'gross\s*(?:profit\s*)?margin|毛利率',line,re.I):
                field='gross_margin'
                values=[num(v) for v in re.findall(r'([+-]?\d+(?:\.\d+)?)\s*%',line)]
            elif re.search(r'net\s+revenue|gross\s+profit|營業收入|營業毛利',line,re.I):
                field='revenue' if re.search(r'net\s+revenue|營業收入',line,re.I) else 'gross'
                tail=re.split(r'net\s+revenue|gross\s+profit|營業收入|營業毛利',line,flags=re.I,maxsplit=1)[-1]
                tail=re.sub(r'[+-]?[\d,.]+\s*%', '',tail)
                values=[num(v) for v in re.findall(r'\(?[+-]?\d[\d,]*(?:\.\d+)?\)?',tail)]
            elif re.search(r'\bEPS\b|earnings\s+per\s+share|每股盈餘',line,re.I) and not re.search(r'diluted|稀釋',line,re.I):
                field='eps'
                tail=re.split(r'\bEPS\b|earnings\s+per\s+share|每股盈餘',line,flags=re.I,maxsplit=1)[-1]
                values=[num(v) for v in re.findall(r'(?<![\w.])\(?[+-]?\d+(?:\.\d+)?\)?(?![\w.%])',tail)]
            if not field or len(values)!=len(headers) or len(set(headers))!=len(headers): continue
            for period,value in zip(headers,values):
                if value is None or (field=='gross_margin' and not -100<=value<=100): continue
                existing=metrics.setdefault(period,{})
                if field in existing and abs(existing[field]-value)>0.02:
                    raise ValueError('conflicting single-quarter PDF values: '+period+'/'+field)
                existing[field]=value
    for values in metrics.values():
        if 'gross_margin' not in values and values.get('revenue',0)>0 and 'gross' in values:
            values['gross_margin']=values['gross']/values['revenue']*100
    return {p:{k:v[k] for k in ('eps','gross_margin')} for p,v in metrics.items() if all(k in v for k in ('eps','gross_margin'))}


def largan_ir_events(universe, now):
    """Discover dated releases and PDFs from the issuer; no guessed file IDs/URLs."""
    if '3008' not in universe: return [],[]
    from urllib.parse import urljoin, urlparse, unquote
    from io import BytesIO
    url='https://www.largan.com.tw/tw/investor/shareholder'
    upcoming=[]; released=[]
    try:
        response=S.get(url,timeout=(10,25)); response.raise_for_status(); response.encoding='utf-8'
        page=response.text
        # The initial shareholder page is not the conference list; use its own AJAX endpoint.
        if 'investor/shareholder/ajax/data1' in page:
            response=S.get(url+'/ajax/data1',params={'class_id':'1','year':str(now.year)},
                           headers={'Referer':url,'X-Requested-With':'XMLHttpRequest'},timeout=(10,25))
            response.raise_for_status()
            page=response.json().get('html','')
        parser=IRTableParser();parser.feed(page)
        rows=[r for r in parser.rows if re.search(r'法說|conference|results',r['text'],re.I)]
        if not rows: raise ValueError('IR calendar rows unavailable')
        today=now.date().isoformat()
        for row in rows:
            period=period_from_text(row['text'])
            if not period: continue
            date=ir_meeting_date(row['text'],int(period[:4]))
            if not date: continue
            if date < (now.date()-timedelta(days=14)).isoformat(): continue
            event=dict(ticker='3008',name=universe['3008'],period=period,subject=row['text'],source_url=url,release_type='issuer_conference',source_label='公司官方法說資料')
            if date>=today:
                upcoming.append({**event,'planned_date':date,'announcement_date':None})
            if date>today: continue
            clock=ir_meeting_clock(row['text'])
            # No assumption about the call time when the calendar does not specify it
            if date==today and (not clock or now.strftime('%H:%M:%S')<clock): continue
            candidates=[]
            for link in row['links']:
                absolute=urljoin(url,link)
                if urlparse(absolute).hostname!='www.largan.com.tw': continue
                if re.search(r'\.pdf(?:\?|$)|tool-download',absolute,re.I) and not re.search(r'audio|video|錄音|影音',unquote(absolute),re.I):
                    if absolute not in candidates: candidates.append(absolute)
            if not candidates:
                SOURCE_ERRORS.append('issuer_ir/3008/'+period+':no_PDF_links'); continue
            found={};sources=[];conflict=False
            for link in candidates[:3]:
                try:
                    from pypdf import PdfReader
                    doc=S.get(link,timeout=(10,25)); doc.raise_for_status()
                    if not doc.content.startswith(b'%PDF') or len(doc.content)>20_000_000: raise ValueError('not a supported PDF')
                    reader=PdfReader(BytesIO(doc.content))
                    if len(reader.pages)>60: raise ValueError('PDF exceeds page budget')
                    values=ir_pdf_metrics([p.extract_text(extraction_mode='layout') or '' for p in reader.pages])
                    if period in values:
                        for p,v in values.items():
                            if p in found and any(abs(found[p][k]-v[k])>0.02 for k in v):
                                conflict=True;raise ValueError('conflicting PDFs')
                            found[p]=v
                        sources.append(link)
                except Exception as exc:
                    SOURCE_ERRORS.append('issuer_pdf/3008/'+period+':'+type(exc).__name__)
            if conflict or period not in found:
                SOURCE_ERRORS.append('issuer_ir/3008/'+period+':single_quarter_metrics_unavailable');continue
            released.append({**event,'publish_date':date,'publish_time':clock or '','source_url':sources[0],'released_metrics':found,'official_sources':sources})
    except Exception as exc:
        SOURCE_ERRORS.append('issuer_ir/3008:'+type(exc).__name__)
    return upcoming,released


def main():
    SOURCE_ERRORS.clear()
    save_json(DATA/'earnings_calendar.json',load_json(DATA/'earnings_calendar.json',{'years':{}}))
    now=now_tpe();today=now.date().isoformat();uni=fetch_universe()
    if not uni: SOURCE_ERRORS.append('company_universe:unavailable')
    old=load_json(OUT,{'upcoming':[],'reports':[]})
    # Persist all future events, independent of this week's view
    event_history=load_json(DATA/'quarterly_earnings_events.json',old)
    news=fetch_news()+historical_mops_news()+daily_mops_news()+cached_official_announcements(now)
    by=merge_history(financial_snapshot());upcoming={};events={};calendars={}
    ir_upcoming,ir_reports=largan_ir_events(uni,now)
    for x in event_history.get('upcoming',[]):
        if x.get('ticker') in uni and x.get('planned_date','')>=today: upcoming[(x['ticker'],x['period'])]=x
    for x in event_history.get('reports',[]):
        if x.get('ticker') in uni and x.get('publish_date') and valid_cached_earnings_report(x) and report_visible(x,now,calendars): events[(x['ticker'],x['period'])]=x
    for x in news:
        if not x.get('date') or x['ticker'] not in uni: continue
        text=announcement_text(x);subject=x['subject']
        if not x.get('source_url'):
            x['source_url']='https://mops.twse.com.tw/mops/web/t05st01?'+urlencode({'co_id':x['ticker'],'year':str(int(x['date'][:4])-1911)})
        if is_preview_subject(subject):
            date=extract_planned_date(text,x['date']);period=period_from_text(subject)
            if not period: period=period_from_text(text)
            if date and period and date>=today:
                upcoming[(x['ticker'],period)]=dict(ticker=x['ticker'],name=uni.get(x['ticker']) or x['name'],period=period,planned_date=date,announcement_date=x['date'],subject=subject,source_url=x.get('source_url',''))
        elif is_quarterly_release(subject,text):
            period=period_from_text(subject) or period_from_text(text)
            if not period: continue
            event=dict(ticker=x['ticker'],name=uni.get(x['ticker']) or x['name'],period=period,publish_date=x['date'],publish_time=x.get('time',''),subject=subject,source_url=x.get('source_url',''))
            if report_visible(event,now,calendars):
                values=direct_quarter_metrics(text,period)
                values.update(announcement_period_metrics(text,period))
                if values: event['released_metrics']={period:values}
                event['release_type']='quarterly_preliminary' if re.search(r'自結|自行結算|未經.*核閱',subject) else 'financial_report'
                event['source_label']='公開資訊觀測站'
                existing=events.get((x['ticker'],period),{})
                merged={**existing.get('released_metrics',{})}
                for p,v in event.get('released_metrics',{}).items(): merged[p]={**merged.get(p,{}),**v}
                event['released_metrics']=merged
                events[(x['ticker'],period)]={**existing,**event}
                row=event_cumulative(x,period)
                if row:
                    prev=by.get((x['ticker'],period),{})
                    by[(x['ticker'],period)]={**prev,**{k:v for k,v in row.items() if v is not None}}
    for x in ir_upcoming:
        upcoming.setdefault((x['ticker'],x['period']),x)
    for x in ir_reports:
        key=(x['ticker'],x['period'])
        if report_visible(x,now,calendars):
            if key in events:
                events[key].update(released_metrics=x['released_metrics'],official_sources=x['official_sources'])
            else: events[key]=x
    news_eps = {(x['ticker'],x['period']):x for x in current_items('quarterly',now) if x['ticker'] in uni}
    for key,x in news_eps.items():
        if key not in events and report_visible(x,now,calendars):
            events[key] = dict(x, released_metrics={})
    # Both current and prior quarter need their preceding YTD period
    periods=set()
    for x in list(upcoming.values())+list(events.values()):
        p=x['period']; periods.add(previous(p))
        if int(previous(p)[-1])>1: periods.add(previous(previous(p)))
        if (x['ticker'],p) in events: periods.add(p)
    targets={p:set() for p in periods}
    for x in list(upcoming.values())+list(events.values()):
        required=[previous(x['period'])]
        if int(required[0][-1])>1: required.append(previous(required[0]))
        if (x['ticker'],x['period']) in events: required.append(x['period'])
        for p in required: targets.setdefault(p,set()).add(x['ticker'])
    errors=backfill_history(by,set(targets),targets)
    save_financial_history(by)
    for key,x in events.items():
        cur=single_metrics(by,x['ticker'],x['period']);prevp=previous(x['period']);prev=single_metrics(by,x['ticker'],prevp)
        verified=x.get('released_metrics',{})
        if x['period'] in verified:
            cur.update({k:v for k,v in verified[x['period']].items() if v is not None})
            if verified[x['period']].get('eps') is not None: cur['eps_basis']='reported_single'
        if prevp in verified:
            prev.update({k:v for k,v in verified[prevp].items() if v is not None})
            if verified[prevp].get('eps') is not None: prev['eps_basis']='reported_single'
        fallback = news_eps.get(key) or (dict(x) if x.get('source') == 'news_backup' else None)
        x.update(eps=cur['eps'],gross_margin=cur['gross_margin'],eps_basis=cur.get('eps_basis'),prev_period=prevp,prev_eps=prev['eps'],prev_gross_margin=prev['gross_margin'],prev_eps_basis=prev.get('eps_basis'))
        if x['eps'] is None and fallback and fallback.get('eps') is not None:
            x['eps'] = fallback['eps']
            x['eps_basis'] = 'news_reported_single'
            x['eps_news_source'] = {k:fallback.get(k) for k in ('source_label','source_url','evidence')}
            x['source_label'] = 'EPS 新聞備援（其餘欄位沿用官方資料）'
        elif x['eps'] is not None:
            x.pop('eps_news_source', None)
        x['data_status']='complete' if all(x[k] is not None for k in ['eps','gross_margin','prev_eps','prev_gross_margin']) else 'pending_financial_data'
        upcoming.pop(key,None)
    for x in upcoming.values():
        pp=previous(x['period']);pm=single_metrics(by,x['ticker'],pp)
        x.update(prev_period=pp,prev_eps=pm['eps'],prev_gross_margin=pm['gross_margin'])
    ups=sorted(upcoming.values(),key=lambda x:(x['planned_date'],x['ticker']))
    reports=sorted(events.values(),key=lambda x:(x['publish_date'],x.get('publish_time','')),reverse=True)
    result=dict(universe_scope='上市上櫃科技普通股＋熱力圖成分股',universe_count=len(uni),version=VERSION,updated_at=now.isoformat(timespec='minutes'),upcoming=ups,reports=reports,diagnostics={'source_errors':SOURCE_ERRORS,'historical_errors':errors,'coverage':SCAN_STATUS,'calendar_errors':[y for y,v in calendars.items() if v is None]},retention_note='公告當日及下一交易日保留，下一交易日18:00移除；官方休市表排除假日')
    save_json(DATA/'quarterly_earnings_events.json',result)
    save_json(OUT,result)
    notify_earnings(ups, reports, now_tpe(), bool(SOURCE_ERRORS))
    print('quarterly earnings',len(ups),'upcoming',len(reports),'reports','history errors',len(errors))

if __name__=='__main__': main()



