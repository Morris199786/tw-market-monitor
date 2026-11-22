#!/usr/bin/env python3
"""Conservative capture of official TWSE credit dashboard display.

This intentionally does NOT infer figures from the margin-balance report. The
new dashboard's machine-readable interface is not documented; the browser
adapter must see seven distinct official values and the same selected date.
If TWSE changes its DOM/date controls, the run reports an error and leaves the
last published JSON untouched. Use --probe for field/date diagnostics.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, re, time, sys
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
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


def inspect_date_controls(page):
    """Capture actual DOM controls, rather than relying on input[type=date]."""
    return page.evaluate("""() => [...document.querySelectorAll('input,button,[role=button],[role=textbox]')]
      .filter(x => x.getBoundingClientRect().width > 0)
      .map(x => ({tag:x.tagName, type:x.type||'', value:x.value||'',
         placeholder:x.getAttribute('placeholder')||'', label:x.getAttribute('aria-label')||'',
         text:(x.innerText||'').slice(0,80), outer:x.outerHTML.slice(0,400)}))
      .filter(x => /date|日期|時間|[0-9]{4}[/\\-][0-9]{1,2}/i.test(JSON.stringify(x))).slice(0,45)""")


def add_network_diagnostics(page):
    """Keep a bounded view of *official* JSON response shapes and request dates.

    Network observations are diagnostic only: an endpoint is not trusted as a
    historical record unless the response explicitly proves its own date.
    """
    observations=[]
    def record(response):
        try:
            parts=urlsplit(response.url)
            if not (parts.hostname or '').endswith('twse.com.tw'):
                return
            mime=response.headers.get('content-type','').lower()
            if 'json' not in mime:
                return
            entry={'url_path':parts.path,'query':dict(parse_qsl(parts.query)),
                   'status':response.status, 'mime':mime[:75]}
            payload=response.json()
            if isinstance(payload,dict):
                entry['keys']=list(payload.keys())[:35]
                entry['sample']=json.dumps(payload,ensure_ascii=False)[:2500]
            elif isinstance(payload,list):
                entry['length']=len(payload)
                entry['sample']=json.dumps(payload[:2],ensure_ascii=False)[:2500]
            if len(observations)<220: observations.append(entry)
        except Exception as exc:
            if len(observations)<220:observations.append({'parse_error':str(exc)[:160]})
    page.on('response',record)
    return observations


def set_date(page, day):
    """Try actual calendar widgets (including readonly/React inputs).

    Confirming a chosen date is a *separate* step in capture_day. Merely
    filling an input is never proof that the server supplied historical data.
    """
    variants=(day, day.replace('-','/'), day.replace('-',''))
    selectors=(
        'input[type="date"]', 'input[placeholder*="日期"]',
        'input[placeholder*="時間"]', 'input[aria-label*="日期"]',
        'input[aria-label*="時間"]', '.el-date-editor input',
        '.ant-picker-input input', '.react-datepicker__input-container input',
        'input[readonly]',
    )
    for selector in selectors:
        for input_el in page.locator(selector).all()[:12]:
            try:
                if not input_el.is_visible(): continue
                for value in variants[:2]:
                    try:
                        input_el.click(timeout=1800)
                        input_el.evaluate("""(el, value) => {
                          const setter=Object.getOwnPropertyDescriptor(
                            HTMLInputElement.prototype,'value').set;
                          setter.call(el,value);
                          el.dispatchEvent(new Event('input',{bubbles:true}));
                          el.dispatchEvent(new Event('change',{bubbles:true}));
                        }""",value)
                        input_el.press('Enter',timeout=1800)
                        page.wait_for_timeout(850)
                        if day in page.locator('body').inner_text() or value in page.locator('body').inner_text():
                            return True
                    except Exception:pass
                # Calendar widgets with a date input may accept the keyboard.
                try:
                    input_el.click(timeout=1500)
                    input_el.press('ControlOrMeta+A',timeout=1500)
                    input_el.type(day.replace('-','/'),delay=35,timeout=2500)
                    input_el.press('Enter',timeout=1500)
                    page.wait_for_timeout(650)
                    return True
                except Exception:pass
            except Exception:pass
    return False


def capture_day(page, day=None, reload=True):
    if reload:
        page.goto(URL,wait_until='domcontentloaded',timeout=45000)
        page.wait_for_timeout(2000)
    selected=False
    if day:
        selected=set_date(page,day)
        page.wait_for_timeout(1100)
    body=page.locator('body').inner_text(timeout=19000)
    reported=report_date_from_body(body)
    if not reported:
        return None, {'wanted':day,'selected':selected,
                      'reason':'Official data date not detectable in rendered page',
                      'body_excerpt':body[:1300]}
    if day and reported!=day:
        return None, {'wanted':day,'actual':reported,'selected':selected,
                      'reason':'Official date did not change: refusing to backdate latest figures'}
    row,err=parse_visible_text(body,reported)
    if err:
        return None, {'wanted':day,'actual':reported,'selected':selected,
                      'reason':err,'body_excerpt':body[:1300]}
    return row, {'date':reported,'selected':selected}


def save_probe(info,page,network):
    probe=DEST.parent.parent/'.cache/twse-credit-probe.json'
    probe.parent.mkdir(parents=True,exist_ok=True)
    try: controls=inspect_date_controls(page)
    except Exception as exc: controls=[{'error':str(exc)}]
    probe.write_text(json.dumps({
        'created_at':dt.datetime.now(TZ).isoformat(), 'page':page.url,
        'date_controls':controls,'official_json_responses':network,
        'diagnostics':info,
        'note':'These are diagnostics, NOT verified historical observations.'
    },ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('TWSE_CREDIT_PROBE',str(probe),'responses',len(network),flush=True)


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
    print('TWSE_CREDIT_PUBLISHED_LOCALLY',len(obj['rows']),obj['rows'][-1]['date'] if obj['rows'] else 'none',flush=True)


def main():
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--daily',action='store_true')
    g.add_argument('--backfill',action='store_true')
    g.add_argument('--probe',action='store_true')
    p.add_argument('--start',default=str(START))
    p.add_argument('--end')
    p.add_argument('--max-consecutive-failures',type=int,default=3)
    args=p.parse_args()
    from playwright.sync_api import sync_playwright
    today=dt.datetime.now(TZ).date()
    output=[];failures=[];attempted=0
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(locale='zh-TW',timezone_id='Asia/Taipei',viewport={'width':1280,'height':1000})
        page.set_default_timeout(13000)
        network=add_network_diagnostics(page)
        if args.daily or args.probe:
            try:
                row,info=capture_day(page)
                print('TWSE_CREDIT_LATEST',json.dumps(info,ensure_ascii=False),flush=True)
                if row and str(START)<=row['date']<=str(today): output.append(row)
                else:failures.append(info)
            except Exception as exc:failures.append({'mode':'latest','error':repr(exc)[:500]})
        else:
            start=dt.date.fromisoformat(args.start)
            end=min(dt.date.fromisoformat(args.end) if args.end else today,today)
            if end<start: raise SystemExit('End date precedes start date')
            old_dates={r['date'] for r in read_old()['rows']}
            market_path=DEST.parent/'market_monitor.json'
            if not market_path.exists(): raise SystemExit('Market trading calendar missing')
            market=json.loads(market_path.read_text(encoding='utf-8'))
            trading_days={r.get('date') for r in market.get('rows',[]) if isinstance(r,dict)}
            dates=[start+dt.timedelta(days=n) for n in range((end-start).days+1)]
            dates=[str(d) for d in dates if str(d) in trading_days and str(d) not in old_dates]
            print('TWSE_CREDIT_BACKFILL_START',len(dates),str(start),str(end),flush=True)
            consecutive=0
            for index,day in enumerate(dates):
                attempted+=1
                try:
                    row,info=capture_day(page,day,reload=(index==0 or consecutive>0))
                    if row:
                        output.append(row);consecutive=0
                        print('TWSE_CREDIT_VERIFIED',day,flush=True)
                    else:
                        failures.append(info);consecutive+=1
                        print('TWSE_CREDIT_MISSING',json.dumps(info,ensure_ascii=False)[:700],flush=True)
                except Exception as exc:
                    failures.append({'date':day,'error':repr(exc)[:450]});consecutive+=1
                if len(output)>=10:
                    commit(output);output.clear()
                if consecutive>=args.max_consecutive_failures:
                    print('TWSE_CREDIT_EARLY_STOP',consecutive,
                          'consecutive failures; do not waste 38 browser page loads',flush=True)
                    break
                time.sleep(.25)
        if output and not args.probe:commit(output)
        if args.probe or failures:save_probe(failures[:30],page,network)
        browser.close()
    print('TWSE_CREDIT_SUMMARY',json.dumps({'attempted':attempted,
          'failed':len(failures),'verified_total':len(read_old()['rows'])},ensure_ascii=False),flush=True)
    if args.probe:return
    if failures:
        print('TWSE_CREDIT_INCOMPLETE_BACKFILL' if args.backfill else
              'TWSE_CREDIT_NO_VERIFIED_DAILY_ROW',len(failures),flush=True)
        raise SystemExit(3 if args.backfill else 2)

if __name__=='__main__':main()
