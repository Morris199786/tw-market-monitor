#!/usr/bin/env python3
"""LINE research Google Sheets ingestion: rolling 3 calendar months, no AI/Telegram.

The output is a separate JSON file. No existing broker report state is modified.
"""
import calendar
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/line_research.json'
BROKER_FILE = ROOT / 'data/reports.json'
SHEET_ID = '1ujXlmxd7h5lap-Np6saR9i9Dp1V8Q5orgO9Ko1ccISM'
SHEET_TAB = 'LINE產業研究資料庫'
COLUMNS = ('date','type','source','industry','company','ticker','period','story',
           'revenue','eps','inventory','utilization','guidance','trend','rating_target',
           'numbers','dividend_current','dividend_next','dividend_policy',
           'source_row','full_text','full_text_2','full_text_3')
BROKER_TYPES = {'券商評等', '個股報告', '產業報告'}


def normalize(value):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', unicodedata.normalize('NFKC', str(value or '')).casefold())


def cutoff_date(today):
    y, m = today.year, today.month - 3
    if m <= 0:
        y -= 1
        m += 12
    return date(y, m, min(today.day, calendar.monthrange(y, m)[1]))


def parse_date(value):
    match = re.search(r'(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})', str(value or ''))
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def ticker(value):
    match = re.search(r'(?<!\d)\d{4}(?!\d)', str(value or ''))
    return match.group() if match else ''


def broker_candidates(row, brokers):
    if row['type'] not in BROKER_TYPES:
        return []
    day = row['date']
    stock_code = ticker(row['ticker'])
    company = normalize(row['company'])
    matches = []
    for report in brokers:
        if report.get('date') != day:
            continue
        same_stock = (stock_code and ticker(report.get('ticker')) == stock_code) or (company and normalize(report.get('name')) == company)
        if same_stock:
            matches.append({'id': report.get('id'), 'broker': report.get('broker'), 'title': report.get('title')})
    return matches


def transform(values, brokers, today):
    if not values or not values[0]:
        raise ValueError('Empty sheet; refuse to overwrite existing data')
    cutoff = cutoff_date(today)
    items, seen = [], set()
    skipped_old = skipped_invalid = duplicates = 0
    for sheet_row_number, raw in enumerate(values[1:], start=2):
        cells = (list(raw) + [''] * len(COLUMNS))[:len(COLUMNS)]
        record = dict(zip(COLUMNS, cells))
        day = parse_date(record['date'])
        if day is None:
            skipped_invalid += 1
            continue
        if day < cutoff or day > today:
            skipped_old += 1
            continue
        record['date'] = day.isoformat()
        record['sheet_row_number'] = sheet_row_number
        content = json.dumps({key: record[key] for key in COLUMNS}, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        if digest in seen:
            duplicates += 1
            continue
        seen.add(digest)
        record['id'] = 'line-' + digest[:20]
        # Candidate matches are NOT automatically removed: avoid false merges.
        record['possible_broker_duplicates'] = broker_candidates(record, brokers)
        items.append(record)
    items.sort(key=lambda r: (r['date'], r['sheet_row_number']), reverse=True)
    return {'window_start': cutoff.isoformat(), 'window_end': today.isoformat(),
            'count': len(items), 'items': items}, {
            'input_rows': len(values)-1, 'kept': len(items), 'skipped_outside_window': skipped_old,
            'invalid_dates': skipped_invalid, 'identical_rows_removed': duplicates,
            'broker_overlap_candidates': sum(bool(r['possible_broker_duplicates']) for r in items)}


def fetch_sheet(access_token):
    endpoint = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{SHEET_TAB}!A1:W'
    resp = requests.get(endpoint, headers={'Authorization': 'Bearer ' + access_token},
                        params={'valueRenderOption': 'FORMATTED_VALUE'}, timeout=120)
    if not resp.ok:
        try:
            detail = resp.json().get('error', {})
        except ValueError:
            detail = {}
        diagnostics = {
            'http_status': resp.status_code,
            'google_status': detail.get('status', 'UNKNOWN'),
            'google_message': detail.get('message', 'No JSON error message returned'),
            'reasons': [e.get('reason') for e in detail.get('errors', []) if isinstance(e, dict)],
            'error_info': [
                {'reason': e.get('reason'), 'domain': e.get('domain'), 'metadata': {
                    k: v for k, v in e.get('metadata', {}).items()
                    if k in ('service', 'method', 'consumer', 'permission')
                }}
                for e in detail.get('details', [])
                if isinstance(e, dict) and e.get('@type', '').endswith('ErrorInfo')
            ],
        }
        print('GOOGLE_SHEETS_API_ERROR ' + json.dumps(diagnostics, ensure_ascii=False), file=sys.stderr)
        raise RuntimeError(f'Google Sheets request failed (HTTP {resp.status_code}); see GOOGLE_SHEETS_API_ERROR above')
    return resp.json().get('values', [])


def get_access_token():
    """Refresh an end-user OAuth token; never print credentials or tokens."""
    client_id = os.getenv('LINE_GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.getenv('LINE_GOOGLE_CLIENT_SECRET', '').strip()
    refresh_token = os.getenv('LINE_GOOGLE_REFRESH_TOKEN', '').strip()
    if not all((client_id, client_secret, refresh_token)):
        raise RuntimeError('Missing LINE_GOOGLE_CLIENT_ID / LINE_GOOGLE_CLIENT_SECRET / LINE_GOOGLE_REFRESH_TOKEN GitHub Secrets')
    try:
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={'client_id': client_id, 'client_secret': client_secret,
                  'refresh_token': refresh_token, 'grant_type': 'refresh_token'},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError('Google OAuth token refresh network failure') from exc
    if not response.ok:
        try:
            error_code = response.json().get('error', 'unknown')
        except ValueError:
            error_code = 'unknown'
        # Do not log raw server response: it might contain private details.
        raise RuntimeError(f'Google OAuth refresh failed: HTTP {response.status_code}, error={error_code}. '
                           'Check consent-screen testing status, token expiry and secrets.')
    token = response.json().get('access_token')
    if not token:
        raise RuntimeError('Google OAuth refresh response lacks access_token')
    return token


def main():
    today = date.fromisoformat(os.environ['LINE_SYNC_TODAY']) if os.getenv('LINE_SYNC_TODAY') else datetime.now(ZoneInfo('Asia/Taipei')).date()
    fixture = os.getenv('LINE_SYNC_FIXTURE')
    if fixture:
        values = json.loads(Path(fixture).read_text(encoding='utf-8'))
    else:
        # Prefer the user's own OAuth identity. Never fall back to a service account.
        token = get_access_token()
        values = fetch_sheet(token)
    brokers = load_json(BROKER_FILE).get('items', [])
    data, stats = transform(values, brokers, today)
    print(json.dumps(stats, ensure_ascii=False))
    if os.getenv('LINE_SYNC_DRY_RUN') == '1':
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if load_json(OUTPUT) == data:
        print('Unchanged; skip write')
        return
    tmp = OUTPUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(OUTPUT)
    print(f'Updated {OUTPUT}; no AI calls or notifications')


if __name__ == '__main__':
    main()
