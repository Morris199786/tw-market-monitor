#!/usr/bin/env python3
"""00981A full daily holdings from issuer's EZMoney PCF JSON.
Uses actual TranDate (holdings date), never the PCF application date.
Writes atomically only after structural validation. No synthetic dates or holdings.
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'etf_00981a.json'
API = 'https://www.ezmoney.com.tw/ETF/Transaction/GetPCF'
FUND = '49YTW'
TZ = ZoneInfo('Asia/Taipei')


def api_date(value):
    if value is None:
        return None
    s = str(value)
    m = re.search(r'/Date\((-?\d+)', s)
    if m:
        d = dt.datetime.fromtimestamp(int(m.group(1)) / 1000, TZ).date()
        return d.isoformat() if d.year >= 2025 else None
    m = re.match(r'^(20\d\d)-(\d\d)-(\d\d)', s)
    if m:
        try:
            return dt.date(*map(int, m.groups())).isoformat()
        except ValueError:
            return None
    return None


def number(v):
    if v is None or isinstance(v, bool):
        raise ValueError(f'Invalid number: {v!r}')
    s = str(v).replace(',', '').replace('%', '').strip()
    if not re.fullmatch(r'\d+(?:\.\d+)?', s):
        raise ValueError(f'Invalid number: {v!r}')
    return float(s)


def fetch():
    today = dt.datetime.now(TZ).date()
    roc = f'{today.year-1911}/{today.month:02d}/{today.day:02d}'
    payload = json.dumps({'fundCode': FUND, 'date': roc, 'specificDate': False}).encode()
    req = urllib.request.Request(API, data=payload, method='POST', headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/json; charset=UTF-8',
        'Origin': 'https://www.ezmoney.com.tw',
        'Referer': 'https://www.ezmoney.com.tw/ETF/Transaction/PCF',
        'X-Requested-With': 'XMLHttpRequest',
    })
    with urllib.request.urlopen(req, timeout=35) as response:
        data = json.loads(response.read().decode('utf-8-sig'))
    if isinstance(data, dict) and isinstance(data.get('d'), str):
        data = json.loads(data['d'])
    if not isinstance(data, dict):
        raise RuntimeError('Unexpected official PCF response format')
    return data


def parse(data):
    pcf = data.get('pcf') or []
    if not isinstance(pcf, list) or not pcf or not isinstance(pcf[0], dict):
        raise RuntimeError('PCF metadata missing')
    date = api_date(pcf[0].get('TranDate'))
    assets = data.get('asset') or []
    if not isinstance(assets, list):
        raise RuntimeError('PCF asset format changed')
    stock = next((x for x in assets if isinstance(x, dict) and x.get('AssetCode') == 'ST'), None)
    if stock is None or not isinstance(stock.get('Details'), list):
        raise RuntimeError('Official PCF stock asset (ST) missing')
    details = stock['Details']
    if not date:
        dates = {api_date(x.get('TranDate')) for x in details if isinstance(x, dict)}
        dates.discard(None)
        if len(dates) == 1:
            date = dates.pop()
    if not date:
        raise RuntimeError('Missing official holdings date (TranDate); refusing to guess')
    if dt.date.fromisoformat(date) > dt.datetime.now(TZ).date():
        raise RuntimeError(f'Future holdings date {date}')
    holdings = {}
    for item in details:
        if not isinstance(item, dict):
            raise RuntimeError('Invalid stock record')
        code = str(item.get('DetailCode') or '').strip()
        name = str(item.get('DetailName') or '').strip()
        if not re.fullmatch(r'\d{4,6}', code) or not name:
            raise RuntimeError(f'Unexpected stock identifier: {code!r} {name!r}')
        if code in holdings:
            raise RuntimeError(f'Duplicate stock code: {code}')
        shares = number(item.get('Share'))
        weight = number(item.get('NavRate'))
        if not shares.is_integer() or shares < 0 or not 0 <= weight <= 100:
            raise RuntimeError(f'Invalid shares/weight for {code}')
        holdings[code] = {'name': name, 'shares': int(shares), 'weight': weight}
    if not 30 <= len(holdings) <= 150:
        raise RuntimeError(f'Parsed {len(holdings)} holdings, expected 30-150; refusing to overwrite')
    return date, holdings


def main():
    date, holdings = parse(fetch())
    data = {'etf': '00981A', 'source': API, 'snapshots': {}, 'updated_at': ''}
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding='utf-8'))
        if old.get('etf') != '00981A' or not isinstance(old.get('snapshots'), dict):
            raise RuntimeError('Existing ETF JSON schema mismatch')
        data['snapshots'] = old['snapshots']
    if date in data['snapshots']:
        if data['snapshots'][date] != holdings:
            raise RuntimeError(f'{date} already exists with different holdings; refusing silent rewrite')
        print(f'Unchanged: {date}, {len(holdings)} holdings')
        return
    data['snapshots'][date] = holdings
    data['snapshots'] = dict(sorted(data['snapshots'].items()))
    data['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(OUT)
    print(f'Updated {date}: {len(holdings)} holdings, snapshots={len(data["snapshots"])}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ETF 00981A update failed: {exc}', file=sys.stderr)
        sys.exit(1)
