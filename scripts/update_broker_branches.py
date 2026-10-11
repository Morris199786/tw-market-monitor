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
import threading
import requests
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/broker_branches'
BASE = 'https://fubon-ebrokerdj.fbs.com.tw'
VERSION = 1
# Shared ceiling across ranking + detail requests; never 12 requests per stock.
HTTP_LIMIT = threading.BoundedSemaphore(12)
HTTP_LOCAL = threading.local()
METRICS_LOCK = threading.Lock()
METRICS = {'requests': 0, 'cached': 0, 'incremental': 0, 'full': 0}


def metric(key):
    with METRICS_LOCK:
        METRICS[key] += 1



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
    if not hasattr(HTTP_LOCAL, 'session'):
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': BASE + '/', 'Accept': 'text/html'})
        session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=2, pool_maxsize=1))
        HTTP_LOCAL.session = session
    error = None
    for attempt in range(2):
        delay = 1
        try:
            with HTTP_LIMIT:
                metric('requests')
                response = HTTP_LOCAL.session.get(url, timeout=(8, 20))
                if response.status_code == 429:
                    retry = response.headers.get('Retry-After', '5')
                    delay = min(30, max(5, int(retry))) if retry.isdigit() else 5
                response.raise_for_status()
                page = response.content.decode('cp950', errors='replace')
            if '<table' not in page.lower():
                raise ValueError('source returned no table')
            return page
        except Exception as exc:
            error = exc
            if attempt == 0:
                time.sleep(delay)
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


def detail_days(ticker, branch, start, end):
    query = urllib.parse.urlencode({'A': ticker, 'BHID': branch['broker'], 'b': branch['branch'],
                                   'C': '0', 'D': start, 'E': end, 'ver': 'V3'})
    page = fetch(BASE + '/z/zc/zco/zco0/zco0.djhtm?' + query)
    return parse_daily(page, ticker, branch, start, end)


def delta_check(days, branch):
    delta = round(sum(d['net'] for d in days) - branch['net_lots'], 4)
    if not days or len(days) > 60 or abs(delta) > max(60, len(days) * 2):
        raise ValueError('daily sum disagrees with 60-session ranking')
    return delta


def refresh_branch(ticker, branch, prior, old, start, end):
    """Merge verified old history with a recent overlap; fallback if reconciliation fails."""
    try:
        incremental = (old.get('schema') == VERSION and prior.get('status') == 'ok'
                       and bool(prior.get('days')) and old.get('start', '9999') <= start
                       and start <= old.get('date', '') < end
                       and (date.fromisoformat(end) - date.fromisoformat(old['date'])).days <= 14)
        if incremental:
            # Re-fetch recent overlap to handle late source corrections. No assumed zero rows.
            since = max(start, (date.fromisoformat(old['date']) - timedelta(days=3)).isoformat())
            try:
                recent = detail_days(ticker, branch, since, end)
                history = {d['time']: d for d in prior['days'] if start <= d['time'] < since}
                history.update({d['time']: d for d in recent})
                days = [history[k] for k in sorted(history)]
                delta = delta_check(days, branch)
                metric('incremental')
                branch.update(days=days, status='ok', sum_delta=delta)
                return branch
            except Exception:
                # An empty or inconsistent short-range response cannot erase history.
                pass
        days = detail_days(ticker, branch, start, end)
        delta = delta_check(days, branch)
        metric('full')
        branch.update(days=days, status='ok', sum_delta=delta)
    except Exception as exc:
        branch.update(days=[], status='error', error=str(exc))
    return branch


def update_one(ticker, detail_pool):
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
    same_window = old.get('schema') == VERSION and old.get('start') == start and old.get('date') == end
    cached = {b['id']: b for b in old.get('branches', [])}
    tasks = []
    for branch in ranked:
        prior = cached.get(branch['id'], {})
        if same_window and prior.get('status') == 'ok' and prior.get('net_lots') == branch['net_lots']:
            branch.update({k: prior[k] for k in ('days', 'status', 'sum_delta')})
            metric('cached')
        else:
            tasks.append(detail_pool.submit(refresh_branch, ticker, branch, prior, old, start, end))
    for future in concurrent.futures.as_completed(tasks):
        future.result()
    errors = {b['id']: b['error'] for b in ranked if b.get('status') != 'ok'}
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
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as details, \
            concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(update_one, ticker, details): ticker for ticker in sorted(tickers)}
        for future in concurrent.futures.as_completed(futures):
            try:
                ticker, status = future.result()
            except Exception as exc:
                ticker, status = futures[future], {'ok': False, 'error': str(exc)[:180]}
            manifest['stocks'][ticker] = status
            failures += not status['ok']
            manifest['updated_at'] = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
            write(DEST / 'manifest.json', manifest)
            print(ticker, json.dumps(status, ensure_ascii=False), flush=True)
    print(f'{len(tickers) - failures}/{len(tickers)} stocks refreshed in {time.monotonic() - started:.1f}s; {METRICS}')
    if failures:
        raise SystemExit('Partial source failures; saved valid data. Rerun to retry failed branches.')


if __name__ == '__main__':
    main()

