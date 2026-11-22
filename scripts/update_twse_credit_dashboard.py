#!/usr/bin/env python3
"""Conservative capture of official TWSE credit dashboard display.

This intentionally does NOT infer figures from the margin-balance report. The
new dashboard's machine-readable interface is not documented; the browser
adapter must see seven distinct official values and the same selected date.
If TWSE changes its DOM/date controls, the run reports an error and leaves the
last published JSON untouched. Use --probe for field/date diagnostics.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, re, time
from pathlib import Path
from zoneinfo import ZoneInfo

URL = 'https://www.twse.com.tw/dashboard/zh/credit/margin.html'
DEST = Path(__file__).resolve().parents[1] / 'data/twse_credit_dashboard.json'
START = dt.date(2026, 9, 23)
TZ = ZoneInfo('Asia/Taipei')
FIELDS = {
    'maintenance_ratio': (('全市場擔保維持率','全市場整戶擔保維持率'), 'pct'),
    'call_accounts': (('追繳戶數','追繳帳戶數'), 'int'),
    'call_amount': (('追繳金額',), 'money'),
    'disposal_accounts': (('處分戶數','處分帳戶數'), 'int'),
    'disposal_amount': (('處分金額',), 'money'),
    'credit_accounts': (('當日信用交易戶數','信用交易戶數'), 'int'),
    'credit_account_ratio': (('信用交易戶數占總開戶數比重','信用交易戶數占總開戶數','信用交易戶數比重'), 'pct'),
}
DEFAULT = {'schema':1, 'source':URL, 'first_date':str(START), 'rows':[]}


def normalize(text):
    return re.sub(r'[\s\u00a0\u200b]+','', str(text or '')).replace('％','%')


def parse_value(label, nearby, kind):
    """Keep label-to-number adjacency tight; ambiguous matches are rejected."""
    raw = normalize(nearby)
    label = normalize(label)
    at = raw.find(label)
    if at < 0:
        return None
    following = raw[at+len(label):]
    # Do not take values from a subsequent KPI label.
    cutoff = min([following.index(normalize(n)) for k,(names,_) in FIELDS.items() for n in names
                  if normalize(n) and normalize(n) in following] or [len(following)])
    following = following[:cutoff]
    if kind=='pct':
        match = re.search(r'(?<!\d)(\d{1,3}(?:\.\d{1,4})?)%', following[:90])
        return float(match.group(1)) if match else None
    match = re.search(r'(?<!\d)([\d,]+(?:\.\d{1,4})?)(戶|億元|萬元|元)?', following[:72])
    if not match:
        return None
    number = float(match.group(1).replace(',',''))
    unit = match.group(2) or ''
    if kind == 'int':
        return int(number) if number.is_integer() and (unit in ('', '戶')) else None
    if kind == 'money':
        if unit == '億元': return round(number, 4)
        if unit == '萬元': return round(number / 10000, 4)
        # A money value without a displayed unit cannot be safely normalized.
        return None
    return None


def parse_visible_text(text, date):
    """Parse labels followed by numbers, including layouts with line breaks."""
    compact=normalize(text)
    row={'date':date}
    for key,(labels,kind) in FIELDS.items():
        values=[]
        for label in labels:
            label=normalize(label)
            for match in re.finditer(re.escape(label),compact):
                value=parse_value(label,compact[match.start():match.start()+len(label)+120],kind)
                if value is not None:values.append(value)
        values=list(dict.fromkeys(values))
        if len(values)!=1:
            return None, f'{key}: expected one distinct official value; found {values[:8]}'
        row[key]=values[0]
    return validate(row),None


def validate(row):
    if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',str(row.get('date',''))):
        raise ValueError('bad report date')
    for key in FIELDS:
        v=row.get(key)
        if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<0:
            raise ValueError(f'missing or invalid {key}')
    if not 100 <= row['maintenance_ratio'] <= 500:
        raise ValueError('maintenance ratio is out of plausible bounds; do not publish')
    if not 0 <= row['credit_account_ratio'] <= 100:
        raise ValueError('credit account ratio invalid')
    if not all(isinstance(row[k],int) for k in ('call_accounts','disposal_accounts','credit_accounts')):
        raise ValueError('account counts must be integers')
    return row


def report_date_from_body(text):
    candidates=re.findall(r'(?:資料時間|資料日期)\s*([12]\d{3})[/-](\d{1,2})[/-](\d{1,2})',text)
    dates=[]
    for y,m,d in candidates:
        try: dates.append(str(dt.date(int(y),int(m),int(d))))
        except ValueError: pass
    return dates[-1] if len(set(dates))==1 else None


def set_date(page, day):
    """Request a specific date through the visible picker; never assume a URL parameter works."""
    control = page.locator('input[type="date"]:visible')
    if control.count():
        control.first.fill(day)
        control.first.dispatch_event('change')
        control.first.dispatch_event('input')
        page.wait_for_timeout(850)
        return True
    # Some TWSE builds use a plain text DatePicker input.
    for selector in ('input[placeholder*="日期"]:visible','input[aria-label*="日期"]:visible'):
        loc=page.locator(selector)
        if loc.count():
            loc.first.fill(day.replace('-','/'))
            loc.first.press('Enter')
            page.wait_for_timeout(850)
            return True
    return False


def capture_day(page, day=None):
    page.goto(URL, wait_until='domcontentloaded',timeout=35000)
    page.wait_for_timeout(1800)
    selected = False
    if day: selected = set_date(page,day)
    page.wait_for_timeout(900)
    body = page.locator('body').inner_text(timeout=18000)
    report_day = report_date_from_body(body)
    if not report_day:
        return None, {'reason':'Page did not expose an unambiguous official data date','selected':selected,'wanted':day,'body_excerpt':body[:1200]}
    if day and report_day != day:
        return None, {'reason':'Selected date not reflected in official report date; no backfill row', 'wanted':day,'actual':report_day,'selected':selected}
    row,err=parse_visible_text(body,report_day)
    if err:
        return None, {'reason':err,'date':report_day,'body_excerpt':body[:1600]}
    return row,{'date':report_day,'selected':selected}


def read_old():
    if not DEST.exists(): return DEFAULT
    obj=json.loads(DEST.read_text(encoding='utf-8'))
    if not isinstance(obj.get('rows'),list): raise ValueError('existing dashboard JSON malformed')
    for row in obj['rows']: validate(row)
    return obj


def commit(rows):
    obj=read_old()
    by_date={r['date']:r for r in obj['rows']}
    for r in rows: by_date[r['date']]=validate(r)
    trading_path=DEST.parent/'market_monitor.json'
    calendar=sorted({r['date'] for r in json.loads(trading_path.read_text(encoding='utf-8')).get('rows',[])
                     if r.get('date','')>=str(START)}) if trading_path.exists() else obj.get('calendar',[])
    obj.update({'schema':1,'source':URL,'first_date':str(START),
                'calendar':calendar,'rows':sorted(by_date.values(),key=lambda r:r['date'])})
    if obj['rows'] == read_old()['rows'] and obj['calendar']==read_old().get('calendar',[]):
        print('TWSE_CREDIT_UNCHANGED',len(obj['rows']),flush=True);return
    DEST.parent.mkdir(parents=True, exist_ok=True)
    temp=DEST.with_suffix('.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(DEST)
    print('TWSE_CREDIT_PUBLISHED_LOCALLY',len(obj['rows']),obj['rows'][-1]['date'],flush=True)


def main():
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--daily',action='store_true')
    group.add_argument('--backfill',action='store_true')
    group.add_argument('--probe',action='store_true')
    p.add_argument('--start',default=str(START));p.add_argument('--end')
    args=p.parse_args()
    from playwright.sync_api import sync_playwright
    today=dt.datetime.now(TZ).date()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(locale='zh-TW',timezone_id='Asia/Taipei',viewport={'width':1200,'height':1100})
        page.set_default_timeout(14000)
        output=[];diagnostics=[]
        if args.daily or args.probe:
            try:
                row,info=capture_day(page)
                print('TWSE_CREDIT_LATEST',json.dumps(info,ensure_ascii=False),flush=True)
                if row and str(START)<=row['date']<=str(today):output.append(row)
                else:diagnostics.append(info)
            except Exception as e: diagnostics.append({'mode':'latest','error':str(e)[:600]})
        else:
            start=dt.date.fromisoformat(args.start)
            end=min(dt.date.fromisoformat(args.end) if args.end else today,today)
            existing={r['date'] for r in read_old()['rows']}
            days=[start+dt.timedelta(days=n) for n in range((end-start).days+1)]
            # Restrict to actual trading days in the already-maintained market calendar.
            calendar_path=DEST.parent/'market_monitor.json'
            calendar=(json.loads(calendar_path.read_text(encoding='utf-8')).get('rows',[]) if calendar_path.exists() else [])
            trading_days={r.get('date') for r in calendar}
            days=[d for d in days if str(d) in trading_days and str(d) not in existing]
            print('TWSE_CREDIT_BACKFILL_START',len(days),str(start),str(end),flush=True)
            for index,date in enumerate(days):
                try:
                    row,info=capture_day(page,str(date))
                    if row:output.append(row)
                    else:diagnostics.append(info)
                except Exception as e:diagnostics.append({'date':str(date),'error':str(e)[:500]})
                if index%10==9 and output:commit(output);output.clear()
                time.sleep(.5)
        browser.close()
    if output and not args.probe: commit(output)
    print('TWSE_CREDIT_DIAGNOSTICS',json.dumps(diagnostics[:8],ensure_ascii=False),flush=True)
    if args.daily and not output:
        print('TWSE_CREDIT_NO_VERIFIED_DAILY_ROW: official dashboard adapter needs DOM/API validation',flush=True)
        raise SystemExit(2)
    if args.backfill and diagnostics:
        print('TWSE_CREDIT_INCOMPLETE_BACKFILL',len(diagnostics),flush=True)
        raise SystemExit(3)

if __name__=='__main__':main()
