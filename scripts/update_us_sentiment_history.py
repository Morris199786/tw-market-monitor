#!/usr/bin/env python3
"""Independent US market sentiment historical data collector (2011+).

Writes ONLY data/us_sentiment_history.json. Never touches FINRA or web files.
Run: python scripts/update_us_sentiment_history.py
Requires: pip install yfinance pandas
"""
import csv
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

START = '2011-01-01'
ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == 'scripts' else Path.cwd()
OUT = ROOT / 'data' / 'us_sentiment_history.json'
BASE = 'https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv'
HY_ARCHIVE = ('https://raw.githubusercontent.com/maaurocp/Trading_Protocol/'
              'bf64e83fa4c2a6e72c37d3883476dc81bd9d2e31/data/raw/fred_BAMLH0A0HYM2.csv')
FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd=2011-01-01'
PRICE_SYMBOLS = {'sp500': '^GSPC', 'nasdaq_composite': '^IXIC', 'vix_yahoo': '^VIX'}


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; MarketMonitor/1.0)',
                                                   'Accept': 'text/csv,text/plain,*/*'})
    error = None
    for i in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                content = response.read(15_000_000)
                if not content or b'<html' in content[:200].lower():
                    raise ValueError('Invalid/HTML response')
                return content.decode('utf-8-sig')
        except (TimeoutError, OSError, urllib.error.URLError, ValueError) as exc:
            error = exc
            if i != 2:
                time.sleep(i + 1)
    raise RuntimeError(f'{url}: {error}')


def finite(value):
    try:
        x = float(str(value).strip())
        return round(x, 7) if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def parse_csv(content, date_column, value_column, minimum=None, maximum=None):
    output = {}
    for row in csv.DictReader(io.StringIO(content)):
        date = (row.get(date_column) or '').strip()[:10]
        if date < START or len(date) != 10:
            continue
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            continue
        val = finite(row.get(value_column))
        if val is None or (minimum is not None and val < minimum) or (maximum is not None and val > maximum):
            continue
        output[date] = val
    return output


def fetch_fred(series_id):
    return parse_csv(download(FRED.format(id=series_id)), 'observation_date', series_id, minimum=0)


def fetch_prices():
    import yfinance as yf
    # Download symbols individually: one bad ticker cannot corrupt others.
    results = {}
    errors = {}
    for name, ticker in PRICE_SYMBOLS.items():
        try:
            frame = yf.download(ticker, start=START, auto_adjust=False, progress=False,
                                threads=False, timeout=45)
            if frame is None or frame.empty:
                raise RuntimeError('Empty Yahoo price history')
            close = frame['Close']
            # yfinance sometimes returns a 2-level column index.
            if hasattr(close, 'columns'):
                close = close.iloc[:, 0]
            rows = {}
            for date, value in close.items():
                number = finite(value)
                if number is not None and number > 0:
                    rows[str(date)[:10]] = number
            if len(rows) < 1000:
                raise RuntimeError(f'Too few rows: {len(rows)}')
            results[name] = rows
        except Exception as exc:
            errors[name] = str(exc)[:250]
    return results, errors


def coverage(rows):
    days = sorted(rows)
    return {'rows': len(days), 'start': days[0] if days else None, 'end': days[-1] if days else None}


def recent_enough(rows, max_calendar_days=14):
    if not rows:
        return False
    latest = datetime.strptime(max(rows), '%Y-%m-%d').date()
    return (datetime.now(timezone.utc).date() - latest).days <= max_calendar_days


def main():
    sources = {}
    data = {}
    problems = []
    def record(name, action, url, min_count, freshness_days=14):
        try:
            rows = action()
            if len(rows) < min_count:
                raise ValueError(f'Only {len(rows)} valid rows, expected >= {min_count}')
            state = 'ok' if recent_enough(rows, freshness_days) else 'stale'
            if state != 'ok':
                problems.append(f'{name}: latest {max(rows)} is stale')
            data[name] = rows
            sources[name] = {'status': state, 'url': url, **coverage(rows)}
        except Exception as exc:
            sources[name] = {'status': 'failed', 'url': url, 'error': str(exc)[:500]}
            problems.append(f'{name}: {exc}')

    record('cnn_fear_greed', lambda: parse_csv(download(BASE), 'Date', 'Fear Greed', 0, 100), BASE, 3500)
    record('hy_oas_archive', lambda: parse_csv(download(HY_ARCHIVE), 'date', 'BAMLH0A0HYM2', 0),
           HY_ARCHIVE, 3000, freshness_days=10000)
    record('hy_oas_fred', lambda: fetch_fred('BAMLH0A0HYM2'), FRED.format(id='BAMLH0A0HYM2'), 300)
    record('ig_oas_fred', lambda: fetch_fred('BAMLC0A0CM'), FRED.format(id='BAMLC0A0CM'), 300)
    record('vix_fred', lambda: fetch_fred('VIXCLS'), FRED.format(id='VIXCLS'), 300)

    try:
        prices, errs = fetch_prices()
        for name, ticker in PRICE_SYMBOLS.items():
            key = name.replace('_yahoo', '')
            if name in prices and len(prices[name]) >= 3000:
                data[key] = prices[name]
                state = 'ok' if recent_enough(prices[name]) else 'stale'
                sources[key] = {'status': state, 'url': 'Yahoo Finance: ' + ticker,
                                **coverage(prices[name])}
                if state == 'stale':
                    problems.append(f'{key}: latest {max(prices[name])} stale')
            else:
                error = errs.get(name, 'Incomplete data')
                sources[key] = {'status': 'failed', 'url': 'Yahoo Finance: ' + ticker, 'error': error}
                problems.append(f'{key}: {error}')
    except Exception as exc:
        for key in ('sp500', 'nasdaq_composite', 'vix'):
            sources[key] = {'status': 'failed', 'error': str(exc)[:300]}
            problems.append(f'{key}: {exc}')

    # Never fill missing days with stale observations. Distinguish market holidays
    # from missing data by keeping all original dates and sparse values.
    hy = {**data.get('hy_oas_archive', {}), **data.get('hy_oas_fred', {})}
    vix = data.get('vix_fred') or data.get('vix', {})
    series = {
        'cnn_fear_greed': data.get('cnn_fear_greed', {}),
        'sp500': data.get('sp500', {}),
        'nasdaq_composite': data.get('nasdaq_composite', {}),
        'vix': vix,
        'hy_oas_pct': hy,
        'ig_oas_pct': data.get('ig_oas_fred', {}),
    }
    for name, rows in series.items():
        sources['merged_' + name] = coverage(rows)

    # Guardrails: refuse to publish partial historical coverage as complete.
    mandatory = ('cnn_fear_greed', 'sp500', 'nasdaq_composite', 'vix', 'hy_oas_pct')
    checks = {'cnn_under_10_days': sum(v < 10 for v in series['cnn_fear_greed'].values()),
              'cnn_under_10_segments': 0, 'mandatory_historical_coverage': {}}
    previous_low = False
    for date in sorted(series['cnn_fear_greed']):
        low = series['cnn_fear_greed'][date] < 10
        if low and not previous_low:
            checks['cnn_under_10_segments'] += 1
        previous_low = low
    for name in mandatory:
        info = coverage(series[name]); checks['mandatory_historical_coverage'][name] = info
        if info['rows'] < 3000 or not info['start'] or info['start'] > '2011-03-01':
            problems.append(f'{name}: insufficient 2011+ historical coverage')
        if not recent_enough(series[name]):
            problems.append(f'{name}: no recent data')

    payload = {'schema_version': 1, 'start_requested': START,
               'checked_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'complete': not problems, 'issues': sorted(set(problems)),
               'units': {'cnn_fear_greed':'0-100', 'sp500':'index_points',
                         'nasdaq_composite':'index_points', 'vix':'index_points',
                         'hy_oas_pct':'percentage_points', 'ig_oas_pct':'percentage_points'},
               'sources': sources, 'checks': checks,
               'series': {key: dict(sorted(values.items())) for key, values in series.items()}}
    report = {'complete': payload['complete'], 'sources': sources, 'checks': checks, 'issues': payload['issues']}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    (OUT.parent / 'us_sentiment_fetch_audit.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    # Don't replace a prior valid file if any critical input is broken.
    if not payload['complete']:
        print('ERROR: Incomplete source coverage; existing JSON kept unchanged.', file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_name(OUT.name + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
    temp.replace(OUT)
    print(f'SUCCESS wrote {OUT}, {OUT.stat().st_size:,} bytes')
    return 0

if __name__ == '__main__':
    sys.exit(main())
