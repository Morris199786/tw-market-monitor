"""Fubon broker branches: 60-session ranking + daily lots, no paid API or AI.

Dates without source rows stay missing, never silently converted to zero.
Successful branches are cached per ranking window; failed branches retry on rerun.
"""
import argparse
import concurrent.futures
import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/broker_branches'
BASE = 'https://fubon-ebrokerdj.fbs.com.tw'
VERSION = 1


def read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(path)


def text(value):
    return html.unescape(re.sub(r'<[^>]+>', '', value)).strip()


def rows(page):
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', page, re.I | re.S):
        yield re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.I | re.S)


def number(value):
    value = float(text(value).replace(',', ''))
    if not math.isfinite(value):
        raise ValueError('non-finite lots')
    return value


def iso(value):
    y, m, d = map(int, value.split('/'))
    return date(y, m, d).isoformat()


def fetch(url):
    error = None
    for attempt in range(2):
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0', 'Referer': BASE + '/', 'Accept': 'text/html'})
            with urllib.request.urlopen(request, timeout=25) as response:
                page = response.read().decode('cp950', errors='replace')
            if '<table' not in page.lower():
                raise ValueError('source returned no table')
            return page
        except Exception as exc:
            error = exc
            if attempt == 0:
                time.sleep(2)
    raise RuntimeError(str(error)[:180])


def parse_ranking(page, ticker):
    if not re.search(r'<title>[^<]*' + re.escape(ticker) + r'[^<]*</title>', page, re.I):
        raise ValueError('ranking ticker mismatch')
    end = re.search(r"getYMD1\s*=\s*'([\d/]+)'", page)
    start = re.search(r"getYMD2\s*=\s*'([\d/]+)'", page)
    if not start or not end:
        raise ValueError('ranking range missing')
    start, end = iso(start[1]), iso(end[1])
    if not 45 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 150:
        raise ValueError('not a plausible 60-session range')
    branches = []
    counts = {'buy': 0, 'sell': 0}
    for cells in rows(page):
        if len(cells) != 10:
            continue
        for offset, side, sign in [(0, 'buy', 1), (5, 'sell', -1)]:
            link = re.search(r'href=[\"\']([^\"\']+)', cells[offset], re.I)
            if not link or counts[side] >= 5:
                continue
            query = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(link[1])).query)
            if query.get('a') != [ticker] or not query.get('b') or not query.get('BHID'):
                raise ValueError('invalid branch identity')
            net = number(cells[offset + 3]) * sign
            if net * sign <= 0:
                continue
            counts[side] += 1
            branches.append({'id': query['BHID'][0] + ':' + query['b'][0],
                             'broker': query['BHID'][0], 'branch': query['b'][0],
                             'name': text(cells[offset]), 'side': side, 'rank': counts[side],
                             'net_lots': net})
    if not branches:
        raise ValueError('no ranked branches in source')
    if len({b['id'] for b in branches}) != len(branches):
        raise ValueError('duplicate ranked branch')
    return start, end, branches


def parse_daily(page, ticker, branch, start, end):
    if f"GenFundCorpCombo('{branch['broker']}','{branch['branch']}'" not in page:
        raise ValueError('daily branch identity mismatch')
    if not re.search(r'<title>[^<]*' + re.escape(ticker) + r'[^<]*</title>', page, re.I):
        raise ValueError('daily ticker mismatch')
    result = {}
    for cells in rows(page):
        if len(cells) != 5 or not re.fullmatch(r'\d{4}/\d{1,2}/\d{1,2}', text(cells[0])):
            continue
        day = iso(text(cells[0]))
        if not start <= day <= end or day in result:
            raise ValueError('daily dates outside range or duplicated')
        buy, sell, total, net = map(number, cells[1:])
        # Source publishes rounded lots; daily buy - sell may differ by a lot.
        if min(buy, sell, total) < 0 or abs(buy - sell - net) > 2:
            raise ValueError('invalid daily lots')
        result[day] = {'time': day, 'buy': buy, 'sell': sell, 'net': net}
    if not result:
        raise ValueError('no daily rows; cannot assume zero trading')
    if len(result) > 60:
        raise ValueError('more than 60 sessions returned')
    return [result[k] for k in sorted(result)]


def update_one(ticker):
    path = DEST / (ticker + '.json')
    old = read(path, {})
    now = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    url = BASE + f'/z/zc/zco/zco_{ticker}_6.djhtm'
    try:
        start, end, ranked = parse_ranking(fetch(url), ticker)
        if old.get('date', '') > end:
            raise ValueError('source date regressed')
    except Exception as exc:
        return ticker, {'ok': False, 'date': old.get('date'), 'error': str(exc)}
    same_window = (old.get('schema') == VERSION and old.get('start') == start and old.get('date') == end)
    cached = {b['id']: b for b in old.get('branches', [])} if same_window else {}
    errors = {}
    for branch in ranked:
        prior = cached.get(branch['id'], {})
        if prior.get('status') == 'ok' and prior.get('net_lots') == branch['net_lots']:
            branch.update({k: prior[k] for k in ('days', 'status', 'sum_delta')})
            continue
        try:
            query = urllib.parse.urlencode({'A': ticker, 'BHID': branch['broker'], 'b': branch['branch'],
                                           'C': '0', 'D': start, 'E': end, 'ver': 'V3'})
            page = fetch(BASE + '/z/zc/zco/zco0/zco0.djhtm?' + query)
            days = parse_daily(page, ticker, branch, start, end)
            delta = round(sum(d['net'] for d in days) - branch['net_lots'], 4)
            # Protect against a silently truncated 20-day response; allow source lot rounding.
            if abs(delta) > max(60, len(days) * 2):
                raise ValueError('daily sum disagrees with 60-session ranking')
            branch.update(days=days, status='ok', sum_delta=delta)
        except Exception as exc:
            branch.update(days=[], status='error', error=str(exc))
            errors[branch['id']] = str(exc)
        time.sleep(0.25)
    value = {'schema': VERSION, 'ticker': ticker, 'start': start, 'date': end,
             'updated_at': now, 'source': '富邦 eBroker / MoneyDJ', 'source_url': url,
             'unit': 'lots', 'period': 60, 'branches': ranked, 'errors': errors}
    write(path, value)
    return ticker, {'ok': not errors, 'date': end, 'branches': len(ranked), 'errors': errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', default='', help='Optional comma-separated tickers; default all heatmap stocks')
    args = parser.parse_args()
    if args.tickers:
        tickers = set(re.split(r'[,\s]+', args.tickers.strip()))
    else:
        sectors = read(ROOT / 'data/sectors.json', {}).get('sectors', [])
        tickers = {str(s.get('ticker', '')) for sector in sectors for s in sector.get('stocks', [])}
    if not tickers or any(not re.fullmatch(r'\d{4}', t) for t in tickers):
        raise ValueError('empty or invalid ticker universe')
    manifest = read(DEST / 'manifest.json', {'stocks': {}})
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for ticker, status in pool.map(update_one, sorted(tickers)):
            manifest['stocks'][ticker] = status
            failures += not status['ok']
            manifest['updated_at'] = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
            write(DEST / 'manifest.json', manifest)
            print(ticker, json.dumps(status, ensure_ascii=False), flush=True)
    print(f'{len(tickers) - failures}/{len(tickers)} stocks refreshed')
    if failures:
        raise SystemExit('Partial source failures; saved valid data. Rerun to retry failed branches.')


if __name__ == '__main__':
    main()
