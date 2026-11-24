#!/usr/bin/env python3
"""Incremental US sentiment update; preserves the existing 2011+ archive.

Writes only data/us_sentiment_history.json. The bulk history backfill script
remains unchanged and manual-only. Requires yfinance and pandas on CI.
"""
import csv
import io
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/us_sentiment_history.json'
CNN_URL = 'https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv'
FRED_URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}'
SERIES = ('cnn_fear_greed', 'sp500', 'nasdaq_composite', 'vix', 'hy_oas_pct', 'ig_oas_pct')
DAYS = 35  # 30+ calendar days: cover delayed releases, weekends and holidays.


def daily_window(now=None):
    """Use an exclusive end date, allowing today's NY data after 17:30 ET.

    The conservative cutoff covers regular and early-close sessions, including
    the later VIX close. It also leaves time for providers to publish closes.
    Missing observations are never fabricated; weekends/holidays retain the
    provider's actual dates. No extra exchange-calendar dependency is needed.
    """
    ny = ZoneInfo('America/New_York')
    now = datetime.now(ny) if now is None else now.astimezone(ny)
    today_ny = now.date()
    after_buffer = (now.hour, now.minute) >= (17, 30)
    end = today_ny + timedelta(days=1) if after_buffer and now.weekday() < 5 else today_ny
    return (today_ny - timedelta(days=DAYS)).isoformat(), end.isoformat()


def number(value):
    try:
        n = float(str(value).strip())
        return round(n, 7) if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def download(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; MarketMonitor/1.0)',
                'Accept': 'text/csv,text/plain,*/*',
            })
            with urllib.request.urlopen(req, timeout=40) as response:
                body = response.read(15_000_001)
            if not body or len(body) > 15_000_000 or b'<html' in body[:300].lower():
                raise ValueError('Invalid provider response')
            return body.decode('utf-8-sig')
        except (OSError, ValueError) as error:
            last = error
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(str(last))


def read_csv_recent(url, date_field, value_field, since, before, minimum=0, maximum=None):
    rows = {}
    for r in csv.DictReader(io.StringIO(download(url))):
        day = (r.get(date_field) or '').strip()[:10]
        if len(day) != 10 or not since <= day < before:
            continue
        try:
            datetime.strptime(day, '%Y-%m-%d')
        except ValueError:
            continue
        value = number(r.get(value_field))
        if value is None or value < minimum or (maximum is not None and value > maximum):
            continue
        rows[day] = value
    if not rows:
        raise ValueError('No valid recent rows from provider')
    return rows


def yahoo_recent(since, before):
    import yfinance as yf
    out = {}
    for name, ticker in [('sp500', '^GSPC'), ('nasdaq_composite', '^IXIC'), ('vix_yahoo', '^VIX')]:
        df = yf.download(ticker, start=since, end=before,
                         auto_adjust=False, progress=False, threads=False, timeout=45)
        if df is None or df.empty:
            raise ValueError('Yahoo '+ticker+' has no rows')
        close = df['Close']
        if hasattr(close, 'columns'):
            close = close.iloc[:, 0]
        rows = {}
        for dt, value in close.items():
            day = str(dt)[:10]
            n = number(value)
            if since <= day < before and n is not None and n > 0:
                rows[day] = n
        if len(rows) < 4:
            raise ValueError('Yahoo '+ticker+': too few recent rows: '+str(len(rows)))
        out[name] = rows
    return out


def merge_recent(old, recent, since, before):
    result = dict(old)
    changed = 0
    for day, value in recent.items():
        if since <= day < before and result.get(day) != value:
            result[day] = value
            changed += 1
    return dict(sorted(result.items())), changed


def main():
    if not DEST.is_file():
        print('US_DAILY_NO_ARCHIVE: run US Sentiment History Backfill (2011+) first', file=sys.stderr)
        return 1
    original = json.loads(DEST.read_text(encoding='utf-8'))
    if not isinstance(original.get('series'), dict) or any(
            not isinstance(original['series'].get(k), dict) or
            len(original['series'][k]) < 3000 or
            min(original['series'][k], default='9999') > '2011-03-01' for k in SERIES):
        print('US_DAILY_BAD_ARCHIVE: existing 2011+ history missing/incomplete; refusing overwrite', file=sys.stderr)
        return 1

    since, before = daily_window()
    updates, provider_status = {}, {}
    def collect(label, action):
        try:
            rows = action()
            if not rows:
                raise ValueError('empty recent data')
            updates[label] = rows
            provider_status[label] = {'status': 'ok', 'rows': len(rows), 'latest': max(rows)}
        except Exception as error:
            provider_status[label] = {'status': 'failed', 'error': str(error)[:250]}
            print('US_DAILY_SOURCE_FAILED', label, str(error), file=sys.stderr)

    # CNN publishes a CSV snapshot. It has no date-filtered endpoint: download
    # the CSV once but parse/merge only this 35-day window.
    collect('cnn_fear_greed', lambda: read_csv_recent(
        CNN_URL, 'Date', 'Fear Greed', since, before, 0, 100))
    try:
        price_rows = yahoo_recent(since, before)
        for name in ('sp500', 'nasdaq_composite'):
            updates[name] = price_rows[name]
            provider_status[name] = {'status': 'ok', 'rows': len(price_rows[name]), 'latest': max(price_rows[name])}
    except Exception as error:
        price_rows = {}
        for name in ('sp500', 'nasdaq_composite'):
            provider_status[name] = {'status': 'failed', 'error': str(error)[:250]}
        print('US_DAILY_SOURCE_FAILED Yahoo', str(error), file=sys.stderr)

    for name, sid in [('hy_oas_pct', 'BAMLH0A0HYM2'),
                      ('ig_oas_pct', 'BAMLC0A0CM')]:
        collect(name, lambda sid=sid: read_csv_recent(
            FRED_URL.format(sid=sid, start=since), 'observation_date', sid,
            since, before))

    # FRED is authoritative for VIXCLS; Yahoo fills lagged released closes.
    fred_vix = {}
    try:
        fred_vix = read_csv_recent(
            FRED_URL.format(sid='VIXCLS', start=since), 'observation_date',
            'VIXCLS', since, before)
        provider_status['vix_fred'] = {'status': 'ok', 'rows': len(fred_vix), 'latest': max(fred_vix)}
    except Exception as error:
        provider_status['vix_fred'] = {'status': 'failed', 'error': str(error)[:250]}
    vix = {**price_rows.get('vix_yahoo', {}), **fred_vix}
    if vix:
        updates['vix'] = vix
        provider_status['vix'] = {'status': 'ok', 'rows': len(vix), 'latest': max(vix)}
    else:
        provider_status['vix'] = {'status': 'failed', 'error': 'Yahoo and FRED unavailable'}

    if not updates:
        print('US_DAILY_NO_UPDATES: all recent sources failed; existing JSON preserved', file=sys.stderr)
        return 1

    merged = {k: dict(original['series'][k]) for k in SERIES}
    changed = {}
    for name, rows in updates.items():
        merged[name], changed[name] = merge_recent(merged[name], rows, since, before)
    # Final archive continuity guard: every 2011+ observation must remain present.
    for name in SERIES:
        if any(day not in merged[name] for day in original['series'][name]):
            raise RuntimeError('Attempt to remove historical dates: '+name)

    problems = [k for k in SERIES if k not in updates]
    payload = dict(original)
    payload['series'] = {k:dict(sorted(v.items())) for k,v in merged.items()}
    payload['checked_at_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    payload['complete'] = not problems
    payload['issues'] = ['daily provider unavailable: '+k for k in problems]
    payload['daily_update'] = {
        'mode': 'incremental', 'window_start': since, 'window_end_exclusive': before,
        'provider_status': provider_status, 'changed_rows': changed,
        'original_history_preserved': True,
    }
    # The previous full-backfill source audits are historical snapshots; do not
    # pretend they were fetched again. Update merged coverage metadata only.
    sources = dict(payload.get('sources', {}))
    mandatory = dict(payload.get('checks', {}).get('mandatory_historical_coverage', {}))
    for name, rows in merged.items():
        dates = sorted(rows)
        info = {'rows': len(dates), 'start': dates[0], 'end': dates[-1]}
        sources['merged_'+name] = info
        mandatory[name] = info
    payload['sources'] = sources
    checks = dict(payload.get('checks', {}))
    checks['mandatory_historical_coverage'] = mandatory
    cnn = merged['cnn_fear_greed']
    checks['cnn_under_10_days'] = sum(v < 10 for v in cnn.values())
    count = 0; prev_low = False
    for day in sorted(cnn):
        low = cnn[day] < 10
        if low and not prev_low:
            count += 1
        prev_low = low
    checks['cnn_under_10_segments'] = count
    payload['checks'] = checks

    # Avoid repeated commits of identical content on market holidays unless
    # there is an actual new/corrected observation.
    if not any(changed.values()):
        print('US_DAILY_UNCHANGED', json.dumps({
            'window_start':since, 'latest':{k:max(v) for k,v in merged.items()},
            'provider_status':provider_status}, ensure_ascii=False))
        return 0
    temp = DEST.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'),
                               allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temp, DEST)
    print('US_DAILY_UPDATED', json.dumps({
        'changed_rows':changed, 'latest':{k:max(v) for k,v in merged.items()},
        'issues':payload['issues']}, ensure_ascii=False))
    return 0 if not problems else 2


if __name__ == '__main__':
    sys.exit(main())
