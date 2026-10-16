"""Monthly FINRA margin debt and same-month S&P 500 comparison. No API key."""
import csv
import io
import json
import math
import re
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
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


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
    rows = rows_from(margin, prices, month)
    payload = {'schema_version': 1, 'checked_at': stamp, 'source_updated_at': successful,
               'as_of_month': rows[-1]['month'] if rows else None,
               'sources': {'FINRA': FINRA, 'FRED': FRED}, 'errors': errors,
               'rows': rows, 'margin_history': margin, 'sp500_monthly': prices}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.replace(OUT)
    print(f'US monitor: {len(rows)} months; latest {payload["as_of_month"]}; {len(errors)} source errors')
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
