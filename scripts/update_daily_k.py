"""Daily OHLCV for heatmap constituents; isolated from other market data."""
import json
import math
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Taipei')
DEST = ROOT / 'data/daily_k'


def read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(path)


def valid_bar(row):
    try:
        o, h, l, c, v = (float(row[k]) for k in ('open', 'high', 'low', 'close', 'volume'))
        return (all(math.isfinite(x) for x in (o, h, l, c, v))
                and min(o, h, l, c) > 0 and v >= 0
                and l <= min(o, c) <= max(o, c) <= h)
    except (KeyError, TypeError, ValueError):
        return False


def parse_chart(payload, symbol, now, gaps=None, rejected_dates=None):
    chart = payload.get('chart', {})
    if chart.get('error'):
        raise ValueError(str(chart['error'])[:160])
    result = chart.get('result') or []
    if len(result) != 1:
        raise ValueError('missing chart result')
    r = result[0]
    if r.get('meta', {}).get('symbol') != symbol:
        raise ValueError('ticker mismatch')
    timestamps = r.get('timestamp') or []
    quote = (r.get('indicators', {}).get('quote') or [{}])[0]
    rows = {}
    for i, ts in enumerate(timestamps):
        date = datetime.fromtimestamp(ts, TZ).date()
        if date > now.date() or (date == now.date() and (now.hour, now.minute) < (14, 0)):
            continue
        values = []
        for key in ('open', 'high', 'low', 'close', 'volume'):
            array = quote.get(key) or []
            v = array[i] if i < len(array) else None
            values.append(float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None)
        o, h, l, c, v = values
        if all(x is None for x in values):
            if gaps is not None:
                gaps.append(date.isoformat())
            continue
        row = {'time': date.isoformat(), 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}
        if not valid_bar(row):
            if rejected_dates is not None:
                rejected_dates.append(date.isoformat())
            continue
        rows[row['time']] = {
            'time': row['time'], 'open': round(o, 4), 'high': round(h, 4),
            'low': round(l, 4), 'close': round(c, 4), 'volume': int(v),
        }
    bars = [rows[k] for k in sorted(rows)]
    if not bars:
        raise ValueError('no valid completed candles')
    return bars


def merge_bars(old, incoming, rejected_dates):
    """Keep existing bars for dates absent/rejected in new Yahoo data.

    Do not splice price bases across a split: if overlapping closes show a
    widespread scaling change, keep old history and report a source conflict.
    """
    existing = {r['time']: r for r in old.get('bars', []) if isinstance(r, dict)
                and r.get('time') and valid_bar(r)}
    fresh = {r['time']: r for r in incoming}
    overlap = sorted(set(existing) & set(fresh))
    if len(overlap) >= 10:
        ratios = [fresh[d]['close'] / existing[d]['close'] for d in overlap[-30:]
                  if existing[d]['close'] > 0]
        large = [x for x in ratios if x < .8 or x > 1.25]
        if len(large) > len(ratios) // 2:
            raise ValueError('historical price basis changed; existing data preserved')
    merged = dict(existing)
    merged.update(fresh)
    # For explicitly rejected source bars, prefer a previously validated bar.
    # Never invent a bar for a date missing in both sources.
    for day in rejected_dates:
        if day in existing:
            merged[day] = existing[day]
    return [merged[d] for d in sorted(merged)]


def fetch_one(ticker, meta, now):
    symbol = ticker + ('.TW' if meta['market'] == 'twse' else '.TWO')
    path = DEST / (ticker + '.json')
    old = read(path, {})
    if old.get('fetched_on') == now.date().isoformat() and old.get('bars'):
        try:
            fetched = datetime.fromisoformat(old['updated_at'])
            if fetched.hour >= 14 or now.hour < 14:
                return old, 'cached'
        except (KeyError, ValueError, TypeError):
            pass
    error = None
    for attempt in range(3):
        try:
            response = requests.get(
                'https://query1.finance.yahoo.com/v8/finance/chart/' + symbol,
                params={'range': '2y', 'interval': '1d', 'events': 'splits,div',
                        'includeAdjustedClose': 'false'},
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=(10, 35))
            response.raise_for_status()
            gaps, rejected = [], []
            incoming = parse_chart(response.json(), symbol, now, gaps, rejected)
            bars = merge_bars(old, incoming, rejected)
            latest_source = incoming[-1]['time']
            latest_saved = old.get('date', '')
            if latest_saved and latest_source < latest_saved:
                # Do not call this a successful refresh: source is stale.
                # Keep the old file unchanged and record the reason in manifest.
                return old, f'stale source: latest {latest_source}, saved {latest_saved}; rejected={rejected[-5:]}'
            value = {
                'ticker': ticker, 'name': meta['name'], 'market': meta['market'],
                'source': 'Yahoo Finance',
                'price_basis': 'Yahoo OHLC/Close（非 Adj Close；來源可能調整拆股）',
                'volume_unit': 'shares', 'missing_dates': gaps,
                'invalid_dates': rejected, 'updated_at': now.isoformat(timespec='seconds'),
                'fetched_on': now.date().isoformat(), 'date': bars[-1]['time'], 'bars': bars,
            }
            write(path, value)
            return value, 'updated'
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'[:180]
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return old, error


def main():
    now = datetime.now(TZ)
    sectors = read(ROOT / 'data/sectors.json', {}).get('sectors', [])
    master = read(ROOT / 'data/master.json', {}).get('stocks', {})
    tickers = {str(x.get('ticker', '')) for sector in sectors
               for x in sector.get('stocks', [])}
    rankings = read(ROOT / 'data/institutional.json', {}).get('periods', {})
    for period in rankings.values():
        for market in period.values():
            for group in market.values():
                for side in ('buy', 'sell'):
                    tickers.update(str(row.get('ticker', '')) for row in group.get(side, []))
    if not tickers:
        raise RuntimeError('empty heatmap universe')
    universe, errors = {}, {}
    for ticker in sorted(tickers):
        meta = master.get(ticker, {})
        if not ticker.isdigit() or len(ticker) != 4 or meta.get('market') not in ('twse', 'tpex'):
            errors[ticker] = 'missing valid market identity'
            continue
        universe[ticker] = meta
    status, success = {}, 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = {pool.submit(fetch_one, t, m, now): t for t, m in universe.items()}
        for future in as_completed(tasks):
            ticker = tasks[future]
            try:
                value, result = future.result()
            except Exception as exc:
                value, result = {}, f'{type(exc).__name__}: {exc}'[:180]
            ok = result in ('updated', 'cached')
            if ok:
                success += 1
            else:
                errors[ticker] = result
            status[ticker] = {
                'available': bool(value.get('bars')), 'refresh_ok': ok,
                'date': value.get('date'), 'bars': len(value.get('bars', [])),
                'invalid_dates': value.get('invalid_dates', []),
            }
    write(DEST / 'manifest.json', {
        'updated_at': now.isoformat(timespec='seconds'), 'source': 'Yahoo Finance',
        'stocks': status, 'errors': errors, 'success': success,
        'requested': len(tickers),
    })
    print(f'daily K: {success}/{len(tickers)} refreshed; {len(errors)} errors')
    if errors:
        print('WARNING: some daily K sources failed; valid existing data retained; see manifest.json')
    # Partial source failures are visible in manifest but do not fail the whole
    # workflow when valid historical data is still available.
    if not any(x['available'] for x in status.values()):
        raise RuntimeError('No daily K data available for any stock')


if __name__ == '__main__':
    main()
