from sources import *
import os, re, html, math, unicodedata, time
from html.parser import HTMLParser
from urllib.parse import urlencode
from datetime import datetime, timedelta
from pathlib import Path

SOURCE_ERRORS = []

VERSION = "2026-10-04-v7-telegram-digest"
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

def is_report_subject(s):
    s = re.sub(r"\s+", "", clean(s))
    if is_preview_subject(s) or re.search(r"代.*子公司|更正|重編|差異|預測|會計師|無法|未通過|淨值|簽證|會計政策",s): return False
    if re.search(r'公告.*(?:合併|個體|個別)財務報告',s): return True

    return (
        (
            "財務報告" in s
            or "財務報表" in s
        )
        and any(
            k in s
            for k in (
                "通過",
                "決議",
                "提報董事會通過",
            )
        )
    )

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
        "—"
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
                if not (is_preview_subject(subject) or is_report_subject(subject)): continue
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
    start=max(start,today-timedelta(days=90))
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
                         'keyword4':'財務','co_id':'','queryName':'co_id'}
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
                    if not (is_preview_subject(title) or is_report_subject(title)): continue
                    if is_report_subject(title) and date < (today-timedelta(days=14)).isoformat(): continue
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
                text+='\n\n依公司公告的財報董事會日期整理，未公告時間者不預設為盤後'
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
        if key in sent or any(x.get(k) is None for k in ('prev_gross_margin','prev_eps','gross_margin','eps')):
            continue
        text=(f"📊 {x['name']} {x['ticker']}｜財報公布\n"
              f"上一季 {x['prev_period']}\n毛利率：{f(x['prev_gross_margin'],'%')}\nEPS：{f(x['prev_eps'])} 元\n\n"
              f"本季 {x['period']}\n毛利率：{f(x['gross_margin'],'%')}\nEPS：{f(x['eps'])} 元")
        if 'cumulative_difference' in (x.get('eps_basis'),x.get('prev_eps_basis')):
            text+='\n\nEPS 含累計差額推算值'
        deliver(key,text)
    checkpoint()


def main():
    SOURCE_ERRORS.clear()
    save_json(DATA/'earnings_calendar.json',load_json(DATA/'earnings_calendar.json',{'years':{}}))
    now=now_tpe();today=now.date().isoformat();uni=fetch_universe()
    if not uni: SOURCE_ERRORS.append('company_universe:unavailable')
    old=load_json(OUT,{'upcoming':[],'reports':[]})
    # Persist all future events, independent of this week's view
    event_history=load_json(DATA/'quarterly_earnings_events.json',old)
    news=fetch_news()+historical_mops_news()
    by=merge_history(financial_snapshot());upcoming={};events={};calendars={}
    for x in event_history.get('upcoming',[]):
        if x.get('ticker') in uni and x.get('planned_date','')>=today: upcoming[(x['ticker'],x['period'])]=x
    for x in event_history.get('reports',[]):
        if x.get('ticker') in uni and x.get('publish_date') and report_visible(x,now,calendars): events[(x['ticker'],x['period'])]=x
    for x in news:
        if not x.get('date') or x['ticker'] not in uni: continue
        text=announcement_text(x);subject=x['subject']
        if is_preview_subject(subject):
            date=extract_planned_date(text,x['date']);period=period_from_text(subject)
            if not period: period=period_from_text(text)
            if date and period and date>=today:
                upcoming[(x['ticker'],period)]=dict(ticker=x['ticker'],name=uni.get(x['ticker']) or x['name'],period=period,planned_date=date,announcement_date=x['date'],subject=subject,source_url=x.get('source_url',''))
        elif is_report_subject(subject):
            period=period_from_text(subject) or period_from_text(text)
            if not period: continue
            event=dict(ticker=x['ticker'],name=uni.get(x['ticker']) or x['name'],period=period,publish_date=x['date'],publish_time=x.get('time',''),subject=subject,source_url=x.get('source_url',''))
            if report_visible(event,now,calendars):
                events[(x['ticker'],period)]=event
                row=event_cumulative(x,period)
                if row:
                    prev=by.get((x['ticker'],period),{})
                    by[(x['ticker'],period)]={**prev,**{k:v for k,v in row.items() if v is not None}}
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
        x.update(eps=cur['eps'],gross_margin=cur['gross_margin'],eps_basis=cur.get('eps_basis'),prev_period=prevp,prev_eps=prev['eps'],prev_gross_margin=prev['gross_margin'],prev_eps_basis=prev.get('eps_basis'))
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
