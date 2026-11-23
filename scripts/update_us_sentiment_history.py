#!/usr/bin/env python3
"""US sentiment historical data collector, 2011 onward.

Standalone: only writes data/us_sentiment_history.json and audit JSON.
Does not touch FINRA, other market data, JS, HTML, or CSS.
Dependencies: yfinance, pandas. Run from repo: python scripts/update_us_sentiment_history.py
"""
import csv
import io
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

START = '2011-01-01'
ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == 'scripts' else Path.cwd()
OUT = ROOT / 'data/us_sentiment_history.json'
AUDIT = ROOT / 'data/us_sentiment_fetch_audit.json'
CNN = 'https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv'
HY_ARCHIVE = ('https://raw.githubusercontent.com/maaurocp/Trading_Protocol/'
              'bf64e83fa4c2a6e72c37d3883476dc81bd9d2e31/data/raw/fred_BAMLH0A0HYM2.csv')
IG_ARCHIVE = ('https://raw.githubusercontent.com/SimoneFarinelli10/'
              'hierarchical-copula-aggregation/main/BAMLC0A0CM.csv')
FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd=2011-01-01'
SYMBOLS = {'sp500': '^GSPC', 'nasdaq_composite': '^IXIC', 'vix_yahoo': '^VIX'}


def download(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; MarketMonitor/1.0)',
        'Accept': 'text/csv,text/plain,*/*'})
    error = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read(15_000_001)
            if len(raw) > 15_000_000 or not raw or b'<html' in raw[:300].lower():
                raise ValueError('Invalid or HTML response')
            return raw.decode('utf-8-sig')
        except (TimeoutError, OSError, urllib.error.URLError, ValueError) as exc:
            error = exc
            if i < 2:
                time.sleep(i + 1)
    raise RuntimeError(f'{url}: {error}')


def finite(value):
    try:
        n = float(str(value).strip())
        return round(n, 7) if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def parse_csv(blob, date_col, value_col, lo=0, hi=None):
    rows = {}
    for row in csv.DictReader(io.StringIO(blob)):
        date = (row.get(date_col) or '').strip()[:10]
        if len(date) != 10 or date < START:
            continue
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            continue
        value = finite(row.get(value_col))
        if value is None or value < lo or (hi is not None and value > hi):
            continue
        rows[date] = value
    return rows


def fetch_fred(sid):
    return parse_csv(download(FRED.format(id=sid)), 'observation_date', sid)


def fetch_prices():
    import yfinance as yf
    data, errors = {}, {}
    for key, ticker in SYMBOLS.items():
        try:
            df = yf.download(ticker, start=START, auto_adjust=False,
                             progress=False, threads=False, timeout=45)
            if df is None or df.empty:
                raise ValueError('Empty Yahoo history')
            close = df['Close']
            if hasattr(close, 'columns'):
                close = close.iloc[:, 0]
            rows = {}
            for stamp, val in close.items():
                n = finite(val)
                if n is not None and n > 0:
                    rows[str(stamp)[:10]] = n
            if len(rows) < 3000:
                raise ValueError(f'Only {len(rows)} valid prices')
            data[key] = rows
        except Exception as exc:
            errors[key] = str(exc)[:300]
    return data, errors


def coverage(rows):
    dates = sorted(rows)
    return {'rows': len(dates), 'start': dates[0] if dates else None,
            'end': dates[-1] if dates else None}


def fresh(rows, days=14):
    if not rows:
        return False
    last = datetime.strptime(max(rows), '%Y-%m-%d').date()
    return (datetime.now(timezone.utc).date() - last).days <= days


def overlap_quality(archive, fred):
    common = sorted(set(archive) & set(fred))
    diffs = [(day, archive[day], fred[day], round(abs(archive[day] - fred[day]), 5))
             for day in common if abs(archive[day] - fred[day]) > 0.02]
    return {'overlap_dates': len(common), 'difference_over_2bp_count': len(diffs),
            'difference_examples': diffs[:12]}


def main():
    sources, raw, issues = {}, {}, []

    def get(name, action, url, minimum, max_age=14):
        try:
            rows = action()
            if len(rows) < minimum:
                raise ValueError(f'Only {len(rows)} rows (minimum {minimum})')
            status = 'ok' if fresh(rows, max_age) else 'stale'
            sources[name] = {'status': status, 'url': url, **coverage(rows)}
            raw[name] = rows
            if status == 'stale':
                issues.append(f'{name}: stale at {max(rows)}')
        except Exception as exc:
            sources[name] = {'status': 'failed', 'url': url, 'error': str(exc)[:500]}
            issues.append(f'{name}: {exc}')

    get('cnn_fear_greed', lambda: parse_csv(download(CNN), 'Date', 'Fear Greed', 0, 100), CNN, 3500)
    get('hy_oas_archive', lambda: parse_csv(download(HY_ARCHIVE), 'date', 'BAMLH0A0HYM2'),
        HY_ARCHIVE, 3000, 10000)
    get('ig_oas_archive', lambda: parse_csv(download(IG_ARCHIVE), 'observation_date', 'BAMLC0A0CM'),
        IG_ARCHIVE, 3000, 10000)
    for key, sid in [('hy_oas_fred', 'BAMLH0A0HYM2'),
                     ('ig_oas_fred', 'BAMLC0A0CM'), ('vix_fred', 'VIXCLS')]:
        # FRED recent rows are deliberately an overlay; older CSV archive supplies IG/HY history.
        get(key, lambda sid=sid: fetch_fred(sid), FRED.format(id=sid),
            300 if key != 'vix_fred' else 300)

    prices, price_errors = fetch_prices()
    for name, ticker in SYMBOLS.items():
        key = 'vix_yahoo' if name == 'vix_yahoo' else name
        if name not in prices:
            sources[key] = {'status': 'failed', 'url': 'Yahoo Finance: ' + ticker,
                            'error': price_errors.get(name, 'Empty data')}
            issues.append(key + ': ' + price_errors.get(name, 'Empty data'))
            continue
        raw[key] = prices[name]
        status = 'ok' if fresh(prices[name]) else 'stale'
        sources[key] = {'status': status, 'url': 'Yahoo Finance: ' + ticker,
                        **coverage(prices[name])}
        if status != 'ok':
            issues.append(f'{key}: stale')

    # Archives fill historical dates only; FRED wins on overlapping observations.
    hy = {**raw.get('hy_oas_archive', {}), **raw.get('hy_oas_fred', {})}
    ig = {**raw.get('ig_oas_archive', {}), **raw.get('ig_oas_fred', {})}

    # Preserve FRED historical VIX and add Yahoo completed US trading sessions
    # only when FRED does not yet have the same observation. Avoid intraday data.
    vix = dict(raw.get('vix_fred', {}))
    us_today = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    vix_added = []
    for day, value in sorted(raw.get('vix_yahoo', {}).items()):
        if day < us_today and day not in vix:
            vix[day] = value
            vix_added.append(day)

    comparisons = {
        'ig_archive_vs_fred': overlap_quality(raw.get('ig_oas_archive', {}), raw.get('ig_oas_fred', {})),
        'hy_archive_vs_fred': overlap_quality(raw.get('hy_oas_archive', {}), raw.get('hy_oas_fred', {})),
        'vix_yahoo_dates_added': vix_added[-15:],
        'vix_yahoo_dates_added_count': len(vix_added),
    }
    # Historical providers should have a sizable exact-date overlap.
    if comparisons['ig_archive_vs_fred']['overlap_dates'] < 100:
        issues.append('IG: historical archive and FRED lack sufficient overlap for validation')
    if comparisons['ig_archive_vs_fred']['difference_over_2bp_count'] > 20:
        issues.append('IG: excessive archive/FRED mismatches; inspect audit')

    series = {
        'cnn_fear_greed': raw.get('cnn_fear_greed', {}),
        'sp500': raw.get('sp500', {}),
        'nasdaq_composite': raw.get('nasdaq_composite', {}),
        'vix': vix,
        'hy_oas_pct': hy,
        'ig_oas_pct': ig,
    }
    for name, rows in series.items():
        sources['merged_' + name] = coverage(rows)

    checks = {'cnn_under_10_days': sum(v < 10 for v in series['cnn_fear_greed'].values()),
              'cnn_under_10_segments': 0, 'mandatory_historical_coverage': {}}
    was_low = False
    for day in sorted(series['cnn_fear_greed']):
        low = series['cnn_fear_greed'][day] < 10
        if low and not was_low:
            checks['cnn_under_10_segments'] += 1
        was_low = low
    for name, rows in series.items():
        info = coverage(rows)
        checks['mandatory_historical_coverage'][name] = info
        if info['rows'] < 3000 or not info['start'] or info['start'] > '2011-03-01':
            issues.append(f'{name}: inadequate 2011+ coverage ({info})')
        if not fresh(rows):
            issues.append(f'{name}: latest data not recent')
    if checks['cnn_under_10_days'] < 100 or checks['cnn_under_10_segments'] < 30:
        issues.append('CNN extreme fear history unexpectedly reduced')

    payload = {
        'schema_version': 2, 'start_requested': START,
        'checked_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'complete': not issues, 'issues': sorted(set(issues)),
        'units': {'cnn_fear_greed': '0-100', 'sp500': 'index_points',
                  'nasdaq_composite': 'index_points', 'vix': 'index_points',
                  'hy_oas_pct': 'percentage_points', 'ig_oas_pct': 'percentage_points'},
        'sources': sources, 'checks': checks, 'comparisons': comparisons,
        'series': {name: dict(sorted(rows.items())) for name, rows in series.items()},
    }
    audit = {k: payload[k] for k in ('checked_at_utc', 'complete', 'issues',
                                      'sources', 'checks', 'comparisons')}
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    if issues:
        print('ERROR: source verification failed; existing history JSON preserved.', file=sys.stderr)
        return 1
    temp = OUT.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'),
                               allow_nan=False) + '\n')
    temp.replace(OUT)
    print(f'SUCCESS: {OUT}, {OUT.stat().st_size:,} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
