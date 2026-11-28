"""Monthly FINRA margin debt and same-month S&P 500 comparison. No API key."""
import csv
import io
import json
import math
import re
import time
import urllib.error
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/us_market_monitor.json'
FINRA = 'https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx'
FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500&cosd=2023-01-01'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def previous(month, offset=1):
    y, m = map(int, month.split('-'))
    n = y * 12 + m - 1 - offset
    return f'{n // 12:04d}-{n % 12 + 1:02d}'


def positive(value):
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise ValueError('Invalid non-positive value')
    return n


def parse_finra(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        sheet = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
    result = {}
    for row in sheet.findall('.//s:row', NS):
        values = {}
        for cell in row.findall('s:c', NS):
            value = cell.findtext('s:v', '', NS)
            if cell.get('t') == 'inlineStr':
                value = ''.join(cell.find('s:is', NS).itertext())
            elif cell.get('t') == 's':
                value = shared[int(value)]
            values[re.sub(r'\d', '', cell.get('r', ''))] = value
        month = values.get('A', '')
        if re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
            result[month] = positive(values['B'])
    if not result:
        raise ValueError('FINRA monthly table missing')
    return result


def parse_sp500(blob, current_month):
    result = {}
    for row in csv.DictReader(io.StringIO(blob.decode('utf-8-sig'))):
        day = row['observation_date']
        datetime.strptime(day, '%Y-%m-%d')
        if day[:7] >= current_month or row['SP500'] in ('', '.'):
            continue
        close = positive(row['SP500'])
        month = day[:7]
        if month not in result or day > result[month]['date']:
            result[month] = {'date': day, 'close': close}
    if not result:
        raise ValueError('S&P 500 observations missing')
    return result


def rows_from(margin, prices, current_month):
    rows = []
    for month, balance in sorted(margin.items()):
        if month < '2024-01' or month >= current_month:
            continue
        prior = margin.get(previous(month))
        annual = margin.get(previous(month, 12))
        p, p0 = prices.get(month), prices.get(previous(month))
        mom = (balance / prior - 1) * 100 if prior else None
        sp = (p['close'] / p0['close'] - 1) * 100 if p and p0 else None
        rows.append({'month': month, 'margin_million': balance,
                     'change_million': balance - prior if prior else None,
                     'mom_pct': mom, 'yoy_pct': (balance / annual - 1) * 100 if annual else None,
                     'sp500_return_pct': sp,
                     'relative_pp': mom - sp if mom is not None and sp is not None else None})
    return rows


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Market Monitor)'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except (TimeoutError, urllib.error.URLError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


CFTC = 'https://publicreporting.cftc.gov/resource/gpe5-46if.json'
CFTC_FIELDS = {
    'leveraged_long':'lev_money_positions_long','leveraged_short':'lev_money_positions_short',
    'asset_long':'asset_mgr_positions_long','asset_short':'asset_mgr_positions_short',
    'small_long':'nonrept_positions_long_all','small_short':'nonrept_positions_short_all',
    'open_interest':'open_interest_all',
}
def refresh_cftc(old, stamp):
    from urllib.parse import urlencode
    saved = old.get('rows', [])
    latest = max((r['date'] for r in saved), default=None)
    query = {'cftc_contract_market_code':'209742','$limit':5000,
             '$order':'report_date_as_yyyy_mm_dd ASC',
             '$select':','.join(['report_date_as_yyyy_mm_dd','cftc_contract_market_code','futonly_or_combined']+list(CFTC_FIELDS.values()))}
    if latest:
        from datetime import timedelta
        start=(datetime.fromisoformat(latest)-timedelta(days=35)).date().isoformat()
        query['$where']="report_date_as_yyyy_mm_dd >= '"+start+"T00:00:00'"
    raw=json.loads(fetch(CFTC+'?'+urlencode(query)))
    if not isinstance(raw,list) or not raw or len(raw)>=5000:
        raise ValueError('CFTC response empty or truncated')
    incoming={}
    for item in raw:
        if item['cftc_contract_market_code']!='209742' or item['futonly_or_combined']!='FutOnly':
            raise ValueError('Unexpected CFTC contract/report')
        day=item['report_date_as_yyyy_mm_dd'][:10]
        datetime.strptime(day,'%Y-%m-%d')
        if day>stamp[:10] or day in incoming:raise ValueError('Invalid/duplicate CFTC date')
        row={'date':day}
        for key,field in CFTC_FIELDS.items():
            row[key]=int(item[field])
            if row[key]<0:raise ValueError('Negative position')
        oi=row['open_interest']
        if oi<=0 or any(row[k]>oi for k in CFTC_FIELDS if k!='open_interest'):
            raise ValueError('Invalid open interest')
        for group in ('leveraged','asset','small'):
            row[group+'_net']=row[group+'_long']-row[group+'_short']
        row['leveraged_net_pct']=round(100*row['leveraged_net']/oi,6)
        incoming[day]=row
    if latest and max(incoming)<latest:raise ValueError('CFTC source regressed')
    if not saved and (len(incoming)<900 or min(incoming)>'2007-01-01'):
        raise ValueError('CFTC historical coverage incomplete')
    merged={r['date']:r for r in saved}
    merged.update(incoming)
    rows=[merged[k] for k in sorted(merged)]
    for i,row in enumerate(rows):
        for key in ('leveraged_long','leveraged_short','leveraged_net','asset_net','small_net'):
            row[key+'_change']=row[key]-rows[i-1][key] if i else None
        row['leveraged_net_4report_change']=row['leveraged_net']-rows[i-4]['leveraged_net'] if i>=4 else None
        window=rows[max(0,i-259):i+1]
        row['leveraged_net_pct_percentile']=round(100*sum(x['leveraged_net_pct']<=row['leveraged_net_pct'] for x in window)/len(window),2) if len(window)>=52 else None
    return {'source':CFTC,'contract_code':'209742','contract':'NASDAQ MINI','report':'TFF Futures Only','date_basis':'position_date_not_release_date','rows':rows,'as_of':rows[-1]['date'],'source_updated_at':stamp if rows!=saved else old.get('source_updated_at',stamp),'status':'ok'}

def main():
    now = datetime.now(ZoneInfo('Asia/Taipei'))
    stamp, month = now.isoformat(timespec='seconds'), now.strftime('%Y-%m')
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    margin = dict(old.get('margin_history', {}))
    prices = dict(old.get('sp500_monthly', {}))
    successful = dict(old.get('source_updated_at', {}))
    errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {'FINRA': pool.submit(fetch, FINRA), 'FRED': pool.submit(fetch, FRED)}
        for name, job in jobs.items():
            try:
                blob = job.result()
                parsed = parse_finra(blob) if name == 'FINRA' else parse_sp500(blob, month)
                if name == 'FINRA':
                    if max(parsed) >= month:
                        raise ValueError('Unexpected unpublished FINRA month')
                    margin.update(parsed)
                else:
                    prices.update(parsed)
                successful[name] = stamp
            except Exception as exc:
                errors.append(f'{name}: {type(exc).__name__}: {exc}')
    cftc = old.get('cftc', {})
    try:
        cftc = refresh_cftc(cftc, stamp)
        successful['CFTC'] = stamp
        print('CFTC:',len(cftc['rows']),'reports; latest',cftc['as_of'])
    except Exception as exc:
        cftc = dict(cftc, status='failed', error=str(exc)[:250])
        errors.append('CFTC: '+str(exc))
    rows = rows_from(margin, prices, month)
    payload = {'schema_version': 1, 'checked_at': stamp, 'source_updated_at': successful,
               'as_of_month': rows[-1]['month'] if rows else None,
               'sources': {'FINRA': FINRA, 'FRED': FRED, 'CFTC': CFTC}, 'errors': errors, 'cftc': cftc,
               'rows': rows, 'margin_history': margin, 'sp500_monthly': prices}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.replace(OUT)
    print(f'US monitor: {len(rows)} months; latest {payload["as_of_month"]}; {len(errors)} source errors')
    for error in errors:
        print(error, file=sys.stderr)
    if errors and rows and all(e.startswith('FRED:') for e in errors) and prices:
        print('::warning::FRED unavailable. Retained saved S&P 500 history; missing months remain blank.')
        return 0
    return 1 if errors or not rows else 0


if __name__ == '__main__':
    sys.exit(main())
