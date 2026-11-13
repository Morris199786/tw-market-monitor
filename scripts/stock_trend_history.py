"""Date-verified history for the 5/10/20-day trend only; shared data stays read-only."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from sources import (ROOT, TWSE_WEB, TZ, get_json, load_json, save_json,
                     now_tpe, ordinary_ticker, clean_name, n, iv)
from sources import _idx


def parse_date(raw):
    text = str(raw or '').strip()
    parts = text.replace('-', '/').split('/')
    try:
        if len(parts) == 3:
            year, month, day = map(int, parts)
            return datetime(year + 1911 if year < 1911 else year, month, day).date().isoformat()
        if text.isdigit() and len(text) in (7, 8):
            year = int(text[:-4])
            return datetime(year + 1911 if len(text) == 7 else year,
                            int(text[-4:-2]), int(text[-2:])).date().isoformat()
    except ValueError:
        pass
    return None


def close_cutoff(now=None):
    now = (now or now_tpe()).astimezone(TZ)
    # Never use an unfinished session. Allow official publication time after close.
    return now.date() if (now.hour, now.minute) >= (14, 30) else now.date() - timedelta(days=1)


def completed_sessions(count=21, now=None):
    """Use published exchange sessions, including holidays/typhoon closures."""
    cutoff = close_cutoff(now)
    sessions = set()
    month = cutoff.replace(day=1)
    for _ in range(4):
        data = get_json(f'{TWSE_WEB}/rwd/zh/afterTrading/FMTQIK',
                        params={'date': month.strftime('%Y%m01'), 'response': 'json'},
                        timeout=30, tries=3)
        if parse_date(data.get('date')) != month.isoformat():
            raise RuntimeError(f'Official calendar response month mismatch for {month}')
        fields = data.get('fields', [])
        idx = _idx(fields, '日期')
        if idx is None or not str(data.get('stat', '')).upper().startswith('OK'):
            raise RuntimeError(f'Official session calendar unavailable for {month:%Y-%m}')
        for row in data.get('data', []):
            ds = parse_date(row[idx])
            if ds and ds <= cutoff.isoformat():
                sessions.add(ds)
        if len(sessions) >= count:
            return sorted(sessions)[-count:]
        month = (month - timedelta(days=1)).replace(day=1)
    raise RuntimeError(f'Only {len(sessions)} official completed sessions; need {count}')


def dated_quote_table(data, day, market):
    if parse_date(data.get('date') or data.get('reportDate')) != day:
        raise RuntimeError(f'{market} response date mismatch for {day}')
    tables = data.get('tables') or [data]
    for table in tables:
        fields = table.get('fields', [])
        code = _idx(fields, ['證券代號', '代號'])
        close = _idx(fields, ['收盤價', '收盤'])
        if code is None or close is None:
            continue
        if table.get('date') and parse_date(table['date']) != day:
            raise RuntimeError(f'{market} table date mismatch for {day}')
        name = _idx(fields, ['證券名稱', '名稱'])
        # TWSE's sign column precedes the numeric delta; substring matching
        # '漲跌' would select the sign and silently parse most deltas as zero.
        change = _idx(fields, '漲跌價差') if market == 'twse' else _idx(fields, '漲跌')
        sign = _idx(fields, '漲跌(+/-)')
        volume = _idx(fields, '成交股數')
        turnover = _idx(fields, ['成交金額(元)', '成交金額'])
        if name is None or volume is None or turnover is None:
            raise RuntimeError(f'{market} required quote fields missing for {day}')
        result = {}
        for row in table.get('data', []):
            ticker = str(row[code]).strip()
            if not ordinary_ticker(ticker):
                continue
            price = n(row[close])
            delta = n(row[change]) if change is not None else 0
            if sign is not None:
                import re, html
                direction = re.sub(r'<[^>]+>', '', html.unescape(str(row[sign])))
                if '-' in direction or '－' in direction:
                    delta = -abs(delta)
            previous = price - delta
            result[ticker] = {'ticker': ticker, 'name': clean_name(row[name]),
                'market': market, 'price': price, 'change': delta,
                'change_pct': delta / previous * 100 if previous > 0 else 0,
                'volume': iv(row[volume]), 'turnover': iv(row[turnover])}
        return result
    raise RuntimeError(f'{market} closing quote table missing for {day}')


def fetch_official_market(day, market):
    if market == 'twse':
        url = f'{TWSE_WEB}/rwd/zh/afterTrading/MI_INDEX'
        params = {'date': day.replace('-', ''), 'type': 'ALLBUT0999', 'response': 'json'}
    else:
        url = 'https://www.tpex.org.tw/www/zh-tw/afterTrading/otc'
        params = {'date': day.replace('-', '/'), 'type': 'EW', 'response': 'json'}
    data = get_json(url, params=params, timeout=45, tries=3)
    quotes = dated_quote_table(data, day, market)
    minimum = 500 if market == 'twse' else 300
    valid = sum(isinstance(q.get('price'), (int, float)) and
                math.isfinite(q['price']) and q['price'] > 0 for q in quotes.values())
    if valid < minimum:
        raise RuntimeError(f'{market} {day}: only {valid} valid closes; need {minimum}')
    return quotes


def complete_snapshot(snapshot, day):
    if snapshot.get('date') != day:
        return False
    quotes = snapshot.get('stocks', {})
    return all(sum(q.get('market') == market and isinstance(q.get('price'), (int, float))
                   and math.isfinite(q['price']) and q['price'] > 0
                   for q in quotes.values()) >= minimum
               for market, minimum in [('twse', 500), ('tpex', 300)])


def ensure_close_history(count=21, dates=None):
    dates = dates or completed_sessions(count)
    rows, failures = [], []
    for day in dates:
        path = ROOT / f'data/history/stock-trend-market/{day}.json'
        snapshot = load_json(path, {})
        if not complete_snapshot(snapshot, day):
            # Reuse existing prices without modifying the shared snapshots.
            for candidate_path in (ROOT / f'data/history/market/{day}.json',
                                   ROOT / 'data/market_latest.json'):
                candidate = load_json(candidate_path, {})
                if complete_snapshot(candidate, day):
                    snapshot = candidate
                    break
        if not complete_snapshot(snapshot, day):
            quotes = dict(snapshot.get('stocks', {})) if snapshot.get('date') == day else {}
            for market in ('twse', 'tpex'):
                try:
                    quotes.update(fetch_official_market(day, market))
                except Exception as exc:
                    failures.append(f'{day} {market}: {exc}')
            snapshot = {'date': day, 'updated_at': now_tpe().isoformat(timespec='minutes'),
                        'source': 'date-verified official TWSE + TPEx close', 'stocks': quotes}
            if complete_snapshot(snapshot, day):
                # Repair valid dates individually; never delete any later snapshot.
                save_json(path, snapshot)
        if not complete_snapshot(snapshot, day):
            failures.append(f'{day}: incomplete snapshot')
        rows.append(snapshot)
    if failures:
        raise RuntimeError('Closing history incomplete; refusing an older end date: ' + '; '.join(failures))
    return rows


