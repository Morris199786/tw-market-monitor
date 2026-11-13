"""Additive OPM recovery. Never changes EPS/GM or sends notifications."""
from __future__ import annotations

import argparse
import calendar
import html
import json
import math
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from html.parser import HTMLParser

from sources import ROOT, load_json, save_json, now_tpe

VERSION = '2026-11-13-opm-announcements-v3'
PERIOD = re.compile(r'^(20\d{2})-Q([1-4])$')
URLS = {'twse': 'https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci',
        'tpex': 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci'}


def number(value):
    text = unicodedata.normalize('NFKC', html.unescape(str(value if value is not None else '')))
    text = re.sub(r'\s+', '', text).replace(',', '').replace('−', '-')
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    try:
        result = float(text)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def previous(period):
    match = PERIOD.fullmatch(str(period))
    if not match:
        return None
    year, quarter = map(int, match.groups())
    return f'{year}-Q{quarter-1}' if quarter > 1 else f'{year-1}-Q4'


def ratio(profit, revenue):
    profit, revenue = number(profit), number(revenue)
    if profit is None or revenue is None or revenue <= 0:
        return None
    result = profit / revenue * 100
    return round(result, 6) if math.isfinite(result) else None


class LimitedRedirects(urllib.request.HTTPRedirectHandler):
    # MOPS sometimes loops redirects during rate limiting. Stop quickly and retry later.
    max_redirections = 2
    max_repeats = 1


def request(url, payload=None, timeout=10):
    encoded = urllib.parse.urlencode(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=encoded, headers={
        'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json,text/html,*/*',
        'Referer': 'https://mops.twse.com.tw/'})
    with urllib.request.build_opener(LimitedRedirects(), urllib.request.HTTPCookieProcessor(CookieJar())).open(req, timeout=timeout) as response:
        return response.read(12_000_001).decode('utf-8-sig', errors='replace')


def pick(record, labels):
    normalized = {re.sub(r'\s+', '', k): v for k, v in record.items()}
    for label in labels:
        if label in normalized:
            return normalized[label]
    return None


def raw_fact(record, period, market, source):
    ticker = str(pick(record, ['公司代號', '證券代號']) or '').strip()
    revenue = number(pick(record, ['營業收入', '營業收入合計', '營業收入淨額']))
    profit = number(pick(record, ['營業利益（損失）', '營業利益(損失)', '營業利益',
                                  '營業損益', '營業淨利（淨損）']))
    if not re.fullmatch(r'\d{4}', ticker) or not PERIOD.fullmatch(str(period)):
        return None
    if revenue is None or profit is None:
        return None
    return {'ticker': ticker, 'period': period, 'market': market,
            'revenue': revenue, 'operating_profit': profit,
            'basis': 'consolidated_industrial_ytd', 'unit': 'TWD_thousands', 'source_url': source,
            'fetched_at': now_tpe().isoformat(timespec='minutes')}


def snapshot_facts(market):
    url = URLS[market]
    data = json.loads(request(url))
    if not isinstance(data, list):
        raise ValueError('Official income table is not an array')
    result = []
    for row in data:
        year, quarter = number(pick(row, ['年度', 'Year'])), number(pick(row, ['季別', 'Season']))
        if year is None or quarter not in (1, 2, 3, 4):
            continue
        year = int(year) + (1911 if year < 1911 else 0)
        fact = raw_fact(row, f'{year}-Q{int(quarter)}', market, url)
        if fact:
            result.append(fact)
    return result


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows = []; self.row = []; self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row = []
        if tag in ('td', 'th'): self.cell = []

    def handle_data(self, value):
        if self.cell is not None: self.cell.append(value)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(re.sub(r'\s+', '', ''.join(self.cell))); self.cell = None
        if tag == 'tr' and self.row:
            self.rows.append(self.row); self.row = []


def historical_facts(page, period, market, source):
    year, quarter = int(period[:4])-1911, int(period[-1])
    flat = re.sub(r'\s+', '', html.unescape(re.sub('<[^>]+>', ' ', page)))
    word = {1: '一', 2: '二', 3: '三', 4: '四'}[quarter]
    if not (re.search(rf'{year}年第?0?{quarter}季', flat) or f'公司第{word}季資料' in flat):
        raise ValueError('Historical income table period mismatch/unavailable')
    parser = Tables(); parser.feed(page)
    header, result = None, []
    for row in parser.rows:
        if '公司代號' in row and any('營業利益' in v or '營業損益' in v for v in row):
            header = row; continue
        if not header or len(row) != len(header):
            continue
        fact = raw_fact(dict(zip(header, row)), period, market, source)
        if fact:
            result.append(fact)
    if not result:
        raise ValueError('Historical income table has no usable operating-profit rows')
    return result


def fetch_history(market, period):
    payload = {'encodeURIComponent': '1', 'step': '1', 'firstin': '1', 'off': '1',
               'isQuery': 'Y', 'TYPEK': 'sii' if market == 'twse' else 'otc',
               'year': str(int(period[:4])-1911), 'season': f'{int(period[-1]):02d}'}
    errors = []
    for host in ('mops.twse.com.tw', 'mopsov.twse.com.tw'):
        url = f'https://{host}/mops/web/ajax_t163sb04'
        try:
            return historical_facts(request(url, payload), period, market,
                                    url + '?' + urllib.parse.urlencode(payload))
        except Exception as exc:
            errors.append(type(exc).__name__ + ':' + str(exc)[:80])
    raise RuntimeError('; '.join(errors))


class InlineFacts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts = {}; self.units = {}; self.facts = []; self.current = None; self.stack = []

    def handle_starttag(self, tag, attrs):
        local = tag.split(':')[-1].lower(); attrs = dict(attrs)
        if self.current is None and local in ('context', 'unit', 'nonfraction'):
            self.current = {'kind': local, 'attrs': attrs, 'values': {}, 'text': [], 'dimensions': False}
            self.stack = []
        if self.current is not None:
            self.stack.append(local)
            if local in ('segment', 'scenario', 'explicitmember', 'typedmember'):
                self.current['dimensions'] = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs); self.handle_endtag(tag)

    def handle_data(self, value):
        if self.current is not None:
            self.current['text'].append(value)
            if self.stack:
                self.current['values'].setdefault(self.stack[-1], []).append(value)

    def handle_endtag(self, tag):
        local = tag.split(':')[-1].lower()
        if self.current is None: return
        if local == self.current['kind']:
            obj = self.current
            if local == 'context': self.contexts[obj['attrs'].get('id')] = obj
            elif local == 'unit': self.units[obj['attrs'].get('id')] = obj
            else: self.facts.append(obj)
            self.current = None; self.stack = []
        elif local in self.stack:
            self.stack = self.stack[:len(self.stack)-1-self.stack[::-1].index(local)]


def filing_facts(page, ticker, period, source):
    year, q = int(period[:4]), int(period[-1])
    end = f'{year}-{q*3:02d}-{calendar.monthrange(year, q*3)[1]:02d}'
    start = f'{year}-{q*3-2:02d}-01'
    parser = InlineFacts(); parser.feed(page)
    value = lambda obj, key: ''.join(obj['values'].get(key, [])).strip()
    contexts = {}
    for key, obj in parser.contexts.items():
        if obj['dimensions'] or value(obj, 'identifier') != str(ticker) or value(obj, 'enddate') != end:
            continue
        if value(obj, 'startdate') == start: contexts[key] = 'single'
        elif value(obj, 'startdate') == f'{year}-01-01': contexts[key] = 'ytd'
    units = {key: tuple(x.strip().split(':')[-1].lower() for x in obj['values'].get('measure', []))
             for key, obj in parser.units.items()}
    tags = {'revenue': 'revenue', 'operatingrevenue': 'revenue', 'operatingrevenues': 'revenue',
            'profitlossfromoperatingactivities': 'operating_profit',
            'operatingincomeloss': 'operating_profit', 'operatingprofitloss': 'operating_profit',
            'profitlossfromoperations': 'operating_profit', 'operatingincome': 'operating_profit'}
    amounts = defaultdict(lambda: defaultdict(set))
    for obj in parser.facts:
        attrs = obj['attrs']; kind = contexts.get(attrs.get('contextref'))
        key = tags.get(attrs.get('name', '').split(':')[-1].lower())
        if not kind or not key or units.get(attrs.get('unitref')) != ('twd',): continue
        if attrs.get('xsi:nil', '').lower() in ('true', '1'): continue
        fmt = attrs.get('format', '').split(':')[-1].lower()
        if fmt not in ('', 'numdotdecimal', 'num-dot-decimal', 'numcommadot', 'zerodash', 'fixed-zero'): continue
        amount = 0.0 if fmt in ('zerodash', 'fixed-zero') else number(''.join(obj['text']))
        if amount is None: continue
        try: amount *= 10 ** int(attrs.get('scale', '0'))
        except (ValueError, OverflowError): continue
        if attrs.get('sign') == '-': amount = -abs(amount)
        if math.isfinite(amount): amounts[kind][key].add(amount)
    out = {}
    for kind, fields in amounts.items():
        if all(len(fields[key]) == 1 for key in ('revenue', 'operating_profit')):
            out[kind] = {'ticker': ticker, 'period': period,
                         **{key: next(iter(fields[key])) for key in ('revenue', 'operating_profit')},
                         'basis': 'consolidated_industrial_' + kind, 'unit': 'TWD', 'source_url': source,
                         'fetched_at': now_tpe().isoformat(timespec='minutes')}
    if q == 1 and 'single' in out:
        out['ytd'] = {**out['single'], 'basis': 'consolidated_industrial_ytd'}
    return out


def fetch_filing(ticker, period):
    errors = []
    for host in ('mopsov.twse.com.tw', 'mops.twse.com.tw'):
        url = f'https://{host}/server-java/t164sb01?' + urllib.parse.urlencode({
            'step': '3', 'SYEAR': period[:4],
            'file_name': f'tifrs-fr1-m1-ci-cr-{ticker}-{period.replace("-", "")}.html'})
        try:
            facts = filing_facts(request(url), ticker, period, url)
            if facts: return facts
            errors.append('no_matching_operating_profit')
        except Exception as exc: errors.append(type(exc).__name__)
    raise RuntimeError('; '.join(errors))


def announcement_fact(page, ticker, period, source, market=None, trusted_company=False):
    """Read an explicitly dated, consolidated YTD revenue/profit pair from MOPS."""
    parsed = urllib.parse.urlparse(source or '')
    if parsed.scheme != 'https' or parsed.hostname not in ('mops.twse.com.tw', 'mopsov.twse.com.tw'):
        return None
    if not PERIOD.fullmatch(str(period)):
        return None
    query = urllib.parse.parse_qs(parsed.query)
    identified = [v for name in ('COMPANY_ID', 'co_id', 'CO_ID') for v in query.get(name, [])]
    if identified and any(str(v) != str(ticker) for v in identified):
        return None
    text = re.sub(r'<script\b[^>]*>.*?</script>', ' ', str(page or ''), flags=re.I | re.S)
    text = unicodedata.normalize('NFKC', html.unescape(re.sub(r'<[^>]+>', ' ', text)))
    text = re.sub(r'\s+', ' ', text).replace('臺', '台')
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)
    compact = re.sub(r'\s+', '', text)
    if not trusted_company and not re.search(rf'(?<!\d){re.escape(str(ticker))}(?!\d)', text):
        return None
    # Some issuers identify consolidation in the earnings narrative as
    # "合併營收" rather than in the financial-report title. The dated YTD
    # revenue/profit pair below remains mandatory; narrative amounts are not used.
    if not re.search(r'合併(?:財務|綜合|損益|營收|營業收入)', text):
        return None
    year, q = int(period[:4]), int(period[-1])
    month, day = q * 3, calendar.monthrange(year, q * 3)[1]
    y = rf'(?:{year}|{year-1911})'
    date_range = rf'{y}[/年]0?1[/月]0?1日?[~～至\-]{y}[/年]0?{month}[/月]0?{day}日?'
    if not re.search(date_range, compact):
        return None
    def one(label):
        pattern = (r'(?:1月1日)?\s*累計至本期止\s*' + label +
                   r'(?:\s*\([^)]*\))*?\s*\((仟元|千元|元)\)\s*[:：]\s*' +
                   r'(\(\s*[+\-]?[\d,]+(?:\.\d+)?\s*\)|[+\-]?[\d,]+(?:\.\d+)?)')
        values = {(m.group(1), number(m.group(2))) for m in re.finditer(pattern, text)}
        values = {(unit, value) for unit, value in values if value is not None}
        return next(iter(values)) if len(values) == 1 else None
    revenue = one(r'(?:合併)?營業收入(?:淨額|合計)?')
    profit = one(r'(?:合併)?營業(?:利益|損益)(?:\(損失\)|\(利益及損失\))?')
    if not revenue or not profit or revenue[0] != profit[0] or revenue[1] <= 0:
        return None
    return {'ticker': str(ticker), 'period': period, 'market': market,
            'revenue': revenue[1], 'operating_profit': profit[1],
            'unit': 'TWD_thousands' if revenue[0] in ('仟元', '千元') else 'TWD',
            'basis': 'consolidated_industrial_ytd', 'source_type': 'official_announcement',
            'source_url': source, 'fetched_at': now_tpe().isoformat(timespec='minutes')}


def fetch_announcement(row, market=None):
    source = row.get('source_url', '')
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme != 'https' or parsed.hostname not in ('mops.twse.com.tw', 'mopsov.twse.com.tw'):
        return None
    page = request(source)
    return announcement_fact(page, str(row['ticker']), row['period'], source, market)


def metric(facts, ticker, period):
    key = f'{ticker}|{period}'; record = facts.get(key, {})
    single = record.get('single')
    if single and ratio(single.get('operating_profit'), single.get('revenue')) is not None:
        return {'value': ratio(single['operating_profit'], single['revenue']),
                'basis': 'reported_single', 'sources': [single['source_url']]}
    current = record.get('ytd')
    if not current: return None
    if period.endswith('Q1'):
        value = ratio(current.get('operating_profit'), current.get('revenue'))
        return {'value': value, 'basis': 'q1_ytd', 'sources': [current['source_url']]} if value is not None else None
    prior = facts.get(f'{ticker}|{previous(period)}', {}).get('ytd')
    if not prior or current.get('basis') != prior.get('basis'):
        return None
    if current.get('market') and prior.get('market') and current['market'] != prior['market']:
        return None
    if period[:4] != previous(period)[:4]: return None
    units = {'TWD': 1, 'TWD_thousands': 1000}
    if current.get('unit') not in units or prior.get('unit') not in units: return None
    current_scale, prior_scale = units[current['unit']], units[prior['unit']]
    revenue = current['revenue'] * current_scale - prior['revenue'] * prior_scale
    profit = current['operating_profit'] * current_scale - prior['operating_profit'] * prior_scale
    value = ratio(profit, revenue)
    if value is None: return None
    return {'value': value, 'basis': 'same_year_ytd_difference',
            'sources': list(dict.fromkeys([current['source_url'], prior['source_url']]))}


def load_reports():
    reports = {}
    for name in ('quarterly_earnings_recovered.json', 'quarterly_earnings_events.json', 'quarterly_earnings.json'):
        for row in load_json(ROOT / 'data' / name, {}).get('reports', []):
            if re.fullmatch(r'\d{4}', str(row.get('ticker', ''))) and PERIOD.fullmatch(str(row.get('period', ''))):
                reports[(str(row['ticker']), row['period'])] = row
    return list(reports.values())


def update_opm(*, history_rows=None, reports=None, full=False, budget=110):
    started = time.monotonic(); now = now_tpe(); data_path = ROOT / 'data/quarterly_opm.json'
    old = load_json(data_path, {}); facts = dict(old.get('facts', {})); attempts = dict(old.get('attempts', {})); errors = []
    history_rows = list(history_rows.values()) if isinstance(history_rows, dict) else history_rows
    history_rows = history_rows if history_rows is not None else load_json(ROOT / 'data/quarterly_earnings_history.json', {}).get('rows', [])
    reports = reports if reports is not None else load_reports()
    targets = {(str(row['ticker']), row['period']) for row in history_rows + reports
               if re.fullmatch(r'\d{4}', str(row.get('ticker', ''))) and PERIOD.fullmatch(str(row.get('period', '')))}
    for key in set(old.get('metrics', {})) | set(facts):
        parts = key.split('|')
        if len(parts) == 2 and re.fullmatch(r'\d{4}', parts[0]) and PERIOD.fullmatch(parts[1]):
            targets.add(tuple(parts))
    for row in reports:
        if PERIOD.fullmatch(str(row.get('period', ''))): targets.add((str(row['ticker']), previous(row['period'])))
    # Include the preceding cumulative quarter needed to derive each standalone ratio.
    required = set(targets)
    required.update((t, previous(p)) for t, p in targets if not p.endswith('Q1'))
    def add(record, kind='ytd'):
        key = f"{record['ticker']}|{record['period']}"
        facts.setdefault(key, {})[kind] = record
    history_index = {(str(row.get('ticker')), row.get('period')): row for row in history_rows}
    def consistent_with_same_announcement(fact):
        row = history_index.get((fact.get('ticker'), fact.get('period')), {})
        known = number(row.get('cum_revenue'))
        if (known is not None and row.get('source_url') == fact.get('source_url')
                and fact.get('unit') == 'TWD_thousands'):
            return abs(known - fact['revenue']) <= max(0.01, abs(known) * 1e-8)
        return True
    # The main report parser now persists the independently validated amount pair.
    # Never take a cached revenue from one source/unit and a profit from another.
    for row in history_rows:
        fact = row.get('opm_ytd_fact')
        if (isinstance(fact, dict) and fact.get('ticker') == str(row.get('ticker'))
                and fact.get('period') == row.get('period')
                and fact.get('source_type') == 'official_announcement'
                and consistent_with_same_announcement(fact)):
            key = f"{fact['ticker']}|{fact['period']}"
            facts.setdefault(key, {}).setdefault('ytd', fact)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {market: pool.submit(snapshot_facts, market) for market in URLS}
        for market, job in jobs.items():
            try:
                for row in job.result(): add(row)
            except Exception as exc: errors.append(f'snapshot/{market}: {exc}')
    markets = {str(row.get('ticker')): row.get('market') for row in history_rows}
    markets.update({str(t): row.get('market') for t, row in load_json(ROOT / 'data/master.json', {}).get('stocks', {}).items()})
    groups = defaultdict(set)
    for ticker, period in required:
        market = markets.get(ticker)
        if market in URLS and not facts.get(f'{ticker}|{period}', {}).get('ytd'):
            groups[(market, period)].add(ticker)
    def due(key):
        stamp = attempts.get(key, {}).get('at')
        if full or attempts.get(key, {}).get('version') != VERSION or not stamp: return True
        cooldown = 7200 if not key.startswith(('filing|', 'announcement|')) and attempts.get(key, {}).get('status') == 'pending' else 1800
        try: return (now - datetime.fromisoformat(stamp)).total_seconds() >= cooldown
        except (ValueError, TypeError): return True
    ranked = sorted(groups, key=lambda k: (attempts.get('|'.join(k), {}).get('at', ''), k[1], k[0]))
    # Recover existing announcements too, even when EPS and GM were already complete.
    announcement_rows = [row for row in reports
                         if not facts.get(f"{row['ticker']}|{row['period']}", {}).get('ytd')
                         and metric(facts, str(row['ticker']), row['period']) is None
                         and urllib.parse.urlparse(row.get('source_url', '')).hostname in ('mops.twse.com.tw', 'mopsov.twse.com.tw')
                         and due(f"announcement|{row['ticker']}|{row['period']}")]
    announcement_rows.sort(key=lambda row: (
        0 if facts.get(f"{row['ticker']}|{previous(row['period'])}", {}).get('ytd') else 1,
        attempts.get(f"announcement|{row['ticker']}|{row['period']}", {}).get('at', ''),
        -int(str(row.get('publish_date', '')).replace('-', '') or '0'), str(row['ticker'])))
    # Give announcement recovery its own time slice. Slow snapshot requests
    # must not consume this entire slice before the first saved report is read.
    announcement_started = time.monotonic()
    def announcement_lookup(row):
        if (time.monotonic() - started > budget if full else
                time.monotonic() - announcement_started > min(40, budget / 2)):
            return row, None, None
        try:
            fact = fetch_announcement(row, markets.get(str(row['ticker'])))
            if fact and not consistent_with_same_announcement(fact):
                return row, None, 'revenue_conflicts_with_same_cached_announcement'
            return row, fact, None if fact else 'no_validated_ytd_operating_profit'
        except Exception as exc:
            return row, None, type(exc).__name__ + ':' + str(exc)[:100]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for row, fact, error in pool.map(announcement_lookup, announcement_rows if full else announcement_rows[:12]):
            if fact is None and error is None: continue
            key = f"announcement|{row['ticker']}|{row['period']}"
            attempts[key] = {'at': now.isoformat(timespec='minutes'), 'version': VERSION,
                             'status': 'received' if fact else 'pending'}
            if fact: add(fact)
            elif error: errors.append(f'{key}: {error}')
    for market, period in ranked:
        key = f'{market}|{period}'
        if not due(key): continue
        if time.monotonic() - started > (budget if full else min(45, budget / 2)): break
        attempts[key] = {'at': now.isoformat(timespec='minutes'), 'version': VERSION}
        try:
            for row in fetch_history(market, period): add(row)
            attempts[key]['status'] = 'received'
        except Exception as exc:
            attempts[key]['status'] = 'pending'; errors.append(f'history/{key}: {exc}')
    # OPM has its own queue; complete EPS/GM records are still eligible.
    published = {}
    for row in reports:
        key = (str(row['ticker']), row['period'])
        published[key] = row.get('publish_date', '')
        prior_key = (key[0], previous(key[1]))
        published[prior_key] = max(published.get(prior_key, ''), row.get('publish_date', ''))
    missing = [(t, p) for t, p in targets if metric(facts, t, p) is None and due(f'filing|{t}|{p}')]
    priority = lambda k: (0 if published.get(k) == now.date().isoformat() else 1 if k in published else 2,
                          attempts.get(f'filing|{k[0]}|{k[1]}', {}).get('at', ''), k[1], k[0])
    missing.sort(key=priority)
    if full:
        selected = missing
    else:
        urgent = [key for key in missing if key in published]
        backlog = sorted((key for key in missing if key not in published),
                         key=lambda k: (attempts.get(f'filing|{k[0]}|{k[1]}', {}).get('at', ''), k))
        selected = urgent[:36] + backlog[:max(12, 48-min(36, len(urgent)))]
    def lookup(key):
        ticker, period = key
        if time.monotonic() - started > budget: return key, None, None
        try: return key, fetch_filing(ticker, period), None
        except Exception as exc: return key, {}, str(exc)
    # Keep old and new quarters moving even when a bulk endpoint is unavailable.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for (ticker, period), found, error in pool.map(lookup, selected):
            if found is None: continue
            key = f'filing|{ticker}|{period}'
            attempts[key] = {'at': now.isoformat(timespec='minutes'), 'version': VERSION,
                             'status': 'pending' if error else 'received'}
            if error:
                errors.append(f'{key}: {error}')
            else:
                for kind, row in found.items(): add(row, kind)
    metrics = {}
    for ticker, period in sorted(targets):
        result = metric(facts, ticker, period)
        if result: metrics[f'{ticker}|{period}'] = result
    result = {'schema': 1, 'version': VERSION, 'updated_at': now_tpe().isoformat(timespec='minutes'),
              'metrics': metrics, 'facts': facts, 'attempts': attempts,
              'coverage': {'total': len(targets), 'complete': len(metrics), 'pending': len(targets)-len(metrics)},
              'source_errors': errors}
    save_json(data_path, result)
    print('OPM coverage:', result['coverage'], flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-backfill', action='store_true', help='Process the complete saved history, without a short per-run budget')
    args = parser.parse_args()
    update_opm(full=args.full_backfill, budget=1500 if args.full_backfill else 110)


