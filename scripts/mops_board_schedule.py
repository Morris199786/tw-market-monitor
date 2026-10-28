"""Read-only official MOPS t170sb01 board-date schedule (TWSE + TPEX).

No Playwright, paid API, notification, or production writes. On partial
failure, returns successful markets and lets caller retain its legacy sources.
"""
from __future__ import annotations
import json
import re
import urllib.request
import urllib.error
from datetime import date
from http.cookiejar import CookieJar

BASE = 'https://mops.twse.com.tw'
API = BASE + '/mops/api/t170sb01'
PAGE = BASE + '/mops/#/web/t170sb01'


def normalize_date(value):
    raw = str(value or '').strip().replace('年', '/').replace('月', '/').replace('日', '').replace('.', '/')
    m = re.fullmatch(r'(\d{2,4})[/-](\d{1,2})[/-](\d{1,2})', raw)
    if not m:
        return ''
    y, mo, day = map(int, m.groups())
    if y < 1911:
        y += 1911
    try:
        return date(y, mo, day).isoformat()
    except ValueError:
        return ''


def request_market(opener, year, quarter, market, timeout=25):
    payload = json.dumps({'year': str(year - 1911), 'TYPEK': market,
                          'season': f'{quarter:02d}', 'sortType': '1'}).encode('utf-8')
    req = urllib.request.Request(API, data=payload, headers={
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': BASE,
        'Referer': PAGE,
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36',
    }, method='POST')
    with opener.open(req, timeout=timeout) as resp:
        data = json.load(resp)
    result = data.get('result') if isinstance(data, dict) else None
    rows = result.get('data') if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f'{market}: invalid MOPS response structure')
    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get('companyId') or '').strip()
        planned = normalize_date(row.get('displayBoardDate') or row.get('expectDate'))
        if not re.fullmatch(r'[1-9]\d{3}', ticker) or not planned:
            continue
        parsed.append({'ticker': ticker, 'name': str(row.get('companyName') or '').strip(),
                       'period': f'{year}-Q{quarter}', 'planned_date': planned,
                       'subject': '預計召開財報董事會', 'source': 'mops_t170sb01',
                       'source_label': '公開資訊觀測站（董事會預計日期）', 'source_url': PAGE})
    # Empty list is possible for older/future periods; caller keeps backup.
    return parsed


def fetch_board_schedule(today=None, quarters=None, timeout=25):
    today = today or date.today()
    # Check current quarter and preceding quarter, covering earnings season
    # across calendar-year boundaries (e.g. January Q4 announcements).
    if quarters is None:
        index = today.year * 4 + (today.month - 1) // 3
        quarters = [((index - offset - 1) // 4, ((index - offset - 1) % 4) + 1)
                    for offset in (0, 1)]
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    try:
        opener.open(urllib.request.Request(BASE + '/mops/', headers={
            'User-Agent': 'Mozilla/5.0'}), timeout=timeout).close()
    except Exception:
        pass
    output, errors, successes = [], [], []
    for year, quarter in quarters:
        for market in ('sii', 'otc'):
            try:
                rows = request_market(opener, year, quarter, market, timeout)
                output.extend(rows)
                successes.append(f'{year}-Q{quarter}/{market}:{len(rows)}')
            except Exception as exc:
                errors.append(f'{year}-Q{quarter}/{market}:{type(exc).__name__}:{str(exc)[:120]}')
    return output, errors, successes
