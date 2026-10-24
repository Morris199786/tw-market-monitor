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
from urllib.parse import quote, urlparse, unquote

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/line_research.json'
BROKER_FILE = ROOT / 'data/reports.json'
SHEET_ID = os.getenv('LINE_SHEET_ID', '1ujXlmxd7h5lap-Np6saR9i9Dp1V8Q5orgO9Ko1ccISM').strip()
SHEET_TAB = os.getenv('LINE_SHEET_TAB', 'LINE產業研究資料庫').strip()
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


def configured_identity():
    """Read only impersonation target; never print credential contents or tokens."""
    expected = os.getenv('LINE_EXPECTED_SERVICE_ACCOUNT', '').strip()
    path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    actual = None
    if path:
        config = json.loads(Path(path).read_text(encoding='utf-8'))
        url = config.get('service_account_impersonation_url', '')
        match = re.search(r'/serviceAccounts/([^/:]+):', unquote(url))
        actual = match.group(1) if match else config.get('client_email')
    if expected and actual and expected != actual:
        raise RuntimeError('SERVICE_ACCOUNT_MISMATCH: workflow 帳號與預期帳號不同；停止讀取')
    print(json.dumps({'service_account': actual or expected or 'not_verified',
                      'identity_verified_from_auth_config': bool(actual),
                      'spreadsheet_id': SHEET_ID}, ensure_ascii=False))


def sheets_get(endpoint, access_token, params):
    resp = requests.get(endpoint, headers={'Authorization': 'Bearer ' + access_token},
                        params=params, timeout=120)
    if resp.ok:
        return resp.json()
    try:
        detail = resp.json().get('error', {})
    except ValueError:
        detail = {}
    reasons = [x.get('reason') for x in detail.get('errors', []) if isinstance(x, dict)]
    reasons += [x.get('reason') for x in detail.get('details', []) if isinstance(x, dict)]
    # Do not print arbitrary server messages: they can include URLs or request data.
    print('GOOGLE_SHEETS_API_ERROR ' + json.dumps({
        'http_status': resp.status_code, 'google_status': detail.get('status'),
        'reasons': reasons, 'spreadsheet_id': SHEET_ID}, ensure_ascii=False), file=sys.stderr)
    if 'SERVICE_DISABLED' in reasons or 'accessNotConfigured' in reasons:
        hint = 'SHEETS_API_DISABLED: 請在服務帳號所屬專案啟用 Google Sheets API'
    elif 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' in reasons or 'insufficientPermissions' in reasons:
        hint = 'TOKEN_SCOPE_INSUFFICIENT: token 缺少 spreadsheets.readonly scope'
    elif resp.status_code == 403:
        hint = ('SHEET_ACCESS_DENIED: 指定服務帳號無法讀取這個試算表 ID。'
                '請核對作者分享的是同一份原始試算表，且分享名單中的完整帳號一致；'
                '若皆一致，需由作者或 Workspace 管理員檢查檔案存取限制。'
                '你的個人帳號權限不會自動套用到服務帳號。')
    elif resp.status_code == 404:
        hint = 'SHEET_NOT_FOUND_OR_HIDDEN: ID 錯誤、檔案不存在或此帳號無權看見'
    elif resp.status_code == 401:
        hint = 'TOKEN_INVALID: 權杖失效，請重新執行 workflow 取得新權杖'
    else:
        hint = 'SHEETS_REQUEST_FAILED: HTTP ' + str(resp.status_code)
    raise RuntimeError(hint)


def fetch_sheet(access_token):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', SHEET_ID):
        raise ValueError('LINE_SHEET_ID 必須填 /d/ 後面的 ID，不是完整網址')
    configured_identity()
    base = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}'
    metadata = sheets_get(base, access_token,
                         {'fields': 'spreadsheetId,sheets.properties(title,sheetId)'})
    titles = [x.get('properties', {}).get('title') for x in metadata.get('sheets', [])]
    if SHEET_TAB not in titles:
        raise RuntimeError('SHEET_TAB_NOT_FOUND: 已有讀取檔案權限，但找不到指定分頁；請確認 LINE_SHEET_TAB')
    print('SHEET_ACCESS_OK: 已通過指定試算表及分頁的讀取檢查')
    a1_range = "'" + SHEET_TAB.replace("'", "''") + "'!A1:W"
    result = sheets_get(base + '/values/' + quote(a1_range, safe=''), access_token,
                        {'valueRenderOption': 'FORMATTED_VALUE'})
    return result.get('values', [])


def main():
    today = date.fromisoformat(os.environ['LINE_SYNC_TODAY']) if os.getenv('LINE_SYNC_TODAY') else datetime.now(ZoneInfo('Asia/Taipei')).date()
    fixture = os.getenv('LINE_SYNC_FIXTURE')
    if fixture:
        values = json.loads(Path(fixture).read_text(encoding='utf-8'))
    else:
        token = os.getenv('ACCESS_TOKEN', '').strip()
        if not token:
            sys.exit('ACCESS_TOKEN missing; no output written')
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

