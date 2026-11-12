#!/usr/bin/env python3
"""Collect official TWSE/TPEx traded-value / traded-shares average prices.

Stores only Taiwan equity symbols that the ETF Flow data references. The displayed
amount is an approximation to a *change in holdings*, not ETF executed trades.

The JSON store survives versioned ETF-Flow data rebuilds, and a temporary CSV is
produced for the existing update_etf_flow.py --market-csv interface. No non-TWD
securities or invented closes are accepted.
"""
import argparse
import csv
import datetime as dt
import json
import math
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TWSE_LATEST = 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'
TPEX_LATEST = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes'
TWSE_HIST = 'https://www.twse.com.tw/exchangeReport/MI_INDEX'
TPEX_HIST = 'https://www.tpex.org.tw/www/zh-tw/afterTrading/otc'
TZ = ZoneInfo('Asia/Taipei')
S = requests.Session()
S.headers.update({'User-Agent': 'ETF-Flow-Market-Price-Importer/1.0 (+daily public market data)', 'Accept': 'application/json', 'Referer': 'https://www.twse.com.tw/'})


def number(v):
    try:
        if v is None or isinstance(v, bool):
            return None
        s = str(v).strip().replace(',', '').replace(' ', '')
        if not s or s in {'--', '-', '---', 'N/A'}:
            return None
        n = float(s)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def date_iso(v):
    s = str(v or '').strip().replace('/', '').replace('-', '')
    if not re.fullmatch(r'\d{7,8}', s):
        return None
    try:
        if len(s) == 7:
            s = str(int(s[:3]) + 1911) + s[3:]
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])).isoformat()
    except ValueError:
        return None


def code4(v):
    c = str(v or '').strip()
    return c if re.fullmatch(r'\d{4}', c) else None


def get_json(url, params=None):
    r = S.get(url, params=params, timeout=35)
    r.raise_for_status()
    return r.json()


def rows_from_dicts(rows, code_cols, date_cols, volume_cols, value_cols, avg_cols=()):
    output = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        def val(keys):
            return next((item[k] for k in keys if k in item and item[k] not in (None,'')), None)
        code = code4(val(code_cols))
        date = date_iso(val(date_cols))
        vol, value, avg = number(val(volume_cols)), number(val(value_cols)), number(val(avg_cols))
        # Share and value units may both be in thousands, but must be equal.
        if avg is None and vol and vol > 0 and value and value > 0:
            avg = value / vol
        if code and date and avg and 0 < avg < 100000:
            output.setdefault(date, {})[code] = round(avg, 6)
    return output


def twse_latest():
    d = get_json(TWSE_LATEST)
    if not isinstance(d, list):
        raise ValueError('TWSE latest is not a list')
    return rows_from_dicts(d, ['Code','證券代號'], ['Date','日期'], ['TradeVolume','成交股數'], ['TradeValue','成交金額'])


def tpex_latest():
    d = get_json(TPEX_LATEST)
    if not isinstance(d, list):
        raise ValueError('TPEx latest is not a list')
    return rows_from_dicts(d, ['SecuritiesCompanyCode','Code','代號'], ['Date','資料日期','日期'],
                           ['TradingShares','TradeVolume','成交股數'], ['TransactionAmount','TradeValue','成交金額'],
                           ['AveragePrice','Average','均價'])


def row_tables(d):
    if not isinstance(d, dict):
        return []
    return [t for t in d.get('tables', []) if isinstance(t, dict) and isinstance(t.get('data'), list)]


def header_index(fields, options):
    normalized = [re.sub(r'[\s\(\)（）]', '', str(x)) for x in fields]
    for option in options:
        key = re.sub(r'[\s\(\)（）]', '', option)
        if key in normalized:
            return normalized.index(key)
    return None


def parse_historical_table(d, requested_date, market):
    out = {}
    for table in row_tables(d):
        fields = table.get('fields') or []
        if not isinstance(fields, list):
            continue
        code_i = header_index(fields, ['證券代號','代號','股票代號'])
        vol_i = header_index(fields, ['成交股數','成交量','成交股數股','成交張數','成交仟股'])
        val_i = header_index(fields, ['成交金額','成交金額元','成交仟元','成交金額千元','成交值'])
        avg_i = header_index(fields, ['均價','成交均價'])
        if code_i is None or (avg_i is None and (vol_i is None or val_i is None)):
            continue
        for row in table['data']:
            if not isinstance(row, list) or len(row) <= code_i:
                continue
            code = code4(row[code_i]);
            if not code:
                continue
            avg = number(row[avg_i]) if avg_i is not None and avg_i < len(row) else None
            if avg is None and vol_i is not None and val_i is not None and max(vol_i,val_i)<len(row):
                volume, value = number(row[vol_i]), number(row[val_i])
                if volume and volume > 0 and value and value > 0:
                    avg = value/volume
                    # Some historical feeds use 1,000-share / 1,000-NTD units, which cancel.
            if avg and 0 < avg < 100000:
                out[code] = round(avg, 6)
    return {requested_date:out} if out else {}


def historical_day(day, market):
    d = day.isoformat()
    if market == 'TWSE':
        raw = get_json(TWSE_HIST, {'response':'json','date':day.strftime('%Y%m%d'),'type':'ALLBUT0999'})
    else:
        raw = get_json(TPEX_HIST, {'date':day.strftime('%Y/%m/%d'), 'response':'json', 'type':'EW', 'id':''})
    return parse_historical_table(raw,d,market)


def merge(dst, src, valid_codes, today):
    added = 0
    for day, values in src.items():
        parsed = date_iso(day)
        if not parsed or parsed > today or not isinstance(values, dict):
            continue
        slot = dst.setdefault(parsed, {})
        for c,v in values.items():
            if c in valid_codes and isinstance(v,(int,float)) and 0 < v < 100000:
                if c not in slot:
                    slot[c] = v
                    added += 1
    return added


def run(args):
    meta_path = Path(args.meta)
    if args.meta == 'auto':
        manifest_path = Path('data/etf-flow-v2/manifest.json')
        pointer = json.loads(manifest_path.read_text(encoding='utf-8'))
        relative = pointer.get('path', '')
        if not re.fullmatch(r'versions/[0-9a-f]{12}/', relative):
            raise ValueError('Unsafe or invalid ETF Flow manifest version path')
        meta_path = manifest_path.parent/relative/'meta.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    codes = {x['code'] for x in meta.get('stocks',[]) if code4(x.get('code'))}
    today = dt.datetime.now(TZ).date()
    out = Path(args.out)
    old = json.loads(out.read_text(encoding='utf-8')) if out.exists() else {}
    records = old.get('prices', {}) if isinstance(old, dict) else {}
    records = {d:{c:v for c,v in row.items() if c in codes} for d,row in records.items() if isinstance(row,dict)}
    count = 0
    fetched = []
    # Use the current TPEx snapshot to identify the OTC universe.
    # Older snapshots with TWSE data but no OTC data must still be backfilled.
    tpex_codes = set()
    for market, fn in [('TWSE',twse_latest),('TPEx',tpex_latest)]:
        try:
            got = fn()
            count += merge(records, got, codes, today.isoformat())
            if market == 'TPEx':
                tpex_codes = {code for day_rows in got.values() for code in day_rows if code in codes}
            fetched.append(market)
            print(f'{market}: {[ (d,len(v)) for d,v in got.items() ]}', flush=True)
        except Exception as e:
            print(f'WARNING: {market} latest not available: {type(e).__name__}: {e}', flush=True)
    # Incrementally fill missing dates AND partially covered OTC dates.
    # A calendar date may already contain hundreds of TWSE prices while all
    # TPEx stocks (e.g., 5274 / 6488) are missing; date-only checks miss this.
    if args.backfill_days > 0:
        earliest_hold = min((date_iso(f.get('earliest')) for f in meta.get('funds', [])
                             if f.get('region') == 'TW' and date_iso(f.get('earliest'))), default=None)
        start = dt.date.fromisoformat(earliest_hold) if earliest_hold else None
        saved_days = {dt.date.fromisoformat(d) for d, vals in records.items()
                      if date_iso(d) == d and vals}
        candidates = []
        if saved_days:
            newest = max(saved_days)
            for offset in range(1, min(args.backfill_days, 30) + 1):
                day = today - dt.timedelta(days=offset)
                if day.weekday() >= 5 or (start and day < start) or day > newest:
                    continue
                existing = records.get(day.isoformat(), {})
                # Refresh when the date is missing, or OTC coverage is much
                # lower than the current official OTC reference universe.
                otc_seen = sum(c in existing for c in tpex_codes)
                missing_otc = bool(tpex_codes) and otc_seen < len(tpex_codes) * .80
                if not existing or missing_otc:
                    candidates.append(day)
            oldest = min(saved_days)
            for offset in range(1, args.backfill_days + 1):
                day = oldest - dt.timedelta(days=offset)
                if start and day < start:
                    break
                if day.weekday() < 5 and day not in saved_days:
                    candidates.append(day)
        else:
            for offset in range(1, args.backfill_days + 1):
                day = today - dt.timedelta(days=offset)
                if start and day < start:
                    break
                if day.weekday() < 5:
                    candidates.append(day)
        # Keep each run bounded; records are merged without overwriting prices
        # on dates which are already populated.
        for day in list(dict.fromkeys(candidates))[:10]:
            day_key = day.isoformat()
            existing = records.get(day_key, {})
            before = len(existing)
            # On OTC-only gaps, do not re-download populated TWSE data.
            markets = ('TWSE', 'TPEx') if not existing else ('TPEx',)
            for market in markets:
                try:
                    got = historical_day(day, market)
                    count += merge(records, got, codes, today.isoformat())
                    matched = sum(map(len, got.values()))
                    print(f'{market} historical {day}: {matched} matched', flush=True)
                    if market == 'TPEx' and tpex_codes and not matched:
                        print(f'WARNING: TPEx historical query returned no matches for {day}', flush=True)
                except Exception as e:
                    print(f'WARNING: {market} historical {day}: {type(e).__name__}: {e}', flush=True)
                time.sleep(0.15)
            after = len(records.get(day_key, {}))
            print(f'BACKFILL {day}: {before} -> {after} covered stocks', flush=True)
    if not records:
        raise RuntimeError('TWSE/TPEx official average prices unavailable; no market prices will be published')
    # Keep market snapshots useful for long historical ETF ranges; no old-date truncation.
    data = {'schema':1,'source':'TWSE/TPEx daily turnover divided by traded shares',
            'prices':dict(sorted(records.items()))}
    out.parent.mkdir(parents=True,exist_ok=True)
    temp = out.with_name(out.name+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    temp.replace(out)
    with open(args.csv,'w',encoding='utf-8',newline='') as fp:
        writer=csv.writer(fp);writer.writerow(['date','code','adjusted_close','average_price'])
        for day, items in sorted(records.items()):
            for code,price in sorted(items.items()):
                writer.writerow([day,code,'',price])
    print(f'market prices {len(records)} days, {sum(map(len,records.values()))} stock/days; {count} new/changed; sources {fetched}')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--meta',default='auto')
    p.add_argument('--out',default='data/etf-flow-v2/market-prices.json')
    p.add_argument('--csv',default='/tmp/etf-flow-market.csv')
    p.add_argument('--backfill-days',type=int,default=18)
    run(p.parse_args())

if __name__=='__main__':
    main()
