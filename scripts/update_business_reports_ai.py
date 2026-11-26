#!/usr/bin/env python3
"""Business reports: today's PDFs only; one Codex subscription call per report.
Uses the broker analyzer, never its main/claim/notification pipeline.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import urllib.parse
import urllib.error
import time

import update_business_reports as index
from report_provider import complete_plan_report, NoReportCapacity

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
INDEX = DATA / 'business_reports.json'
OUTPUT = DATA / 'business_reports_ai.json'
TZ = ZoneInfo('Asia/Taipei')


def today():
    return datetime.now(TZ).date().isoformat()


def read_items(path):
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding='utf-8'))
    rows = obj['items']
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('Invalid business report items')
    return rows


def key(row):
    return (str(row.get('id') or ''), str(row.get('source_fingerprint') or row.get('modified_time') or ''))


def pending(rows, saved, day):
    done = {key(r) for r in saved if r.get('status') == 'ready'}
    seen = set()
    for row in rows:
        k = key(row)
        if row.get('date') != day or not all(k) or '邀請' in str(row.get('filename') or '') or k in done or k in seen:
            continue
        seen.add(k)
        yield row


def extract_text(file):
    """Same layout-aware PDF extraction as the broker pipeline, no AI/OCR."""
    raw = index.request(index.API + '/' + urllib.parse.quote(file['id'], safe='') + '?alt=media',
                        max_bytes=index.MAX_PDF_BYTES)
    if not raw.startswith(b'%PDF-'):
        raise ValueError('Not a PDF')
    import hashlib
    checksum = file.get('md5Checksum')
    if checksum and hashlib.md5(raw).hexdigest() != checksum:
        raise ValueError('PDF changed during download')
    with tempfile.TemporaryDirectory(prefix='business-ai-') as tmp:
        src = Path(tmp) / 'report.pdf'
        out = Path(tmp) / 'report.txt'
        src.write_bytes(raw)
        subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(src), str(out)],
                       check=True, capture_output=True, timeout=120)
        text = out.read_text(encoding='utf-8').replace('\x00', '').strip()
    if len(text) < 40:
        raise ValueError('PDF has no usable text; retain PDF preview')
    return text


def broker_analyzer():
    # Lazily import: if no pending reports, no AI pipeline initialization is needed.
    import update_reports_ai as broker
    import update_reports_ai_eps as eps
    import broker_eps_pipeline
    from report_identity import registry
    companies = registry(refresh=False)  # Read only; do not write broker registry or inbox.

    def complete(payload):
        # Reuse the exact financial extraction instructions, with ONE subscription call.
        payload['input'][0]['content'][0]['text'] += eps.EPS_INSTRUCTION
        return complete_plan_report(payload)

    original_normalize = broker.normalize_report

    def normalize(obj, src):
        result = original_normalize(obj, src)
        result['quarterly_eps'] = broker_eps_pipeline.normalize(obj.get('quarterly_eps'))
        result['financial_forecasts'] = eps.normalize_financial(obj.get('financial_forecasts'))
        return result

    def analyze(row, text):
        src = {'drive_file_id': row['id'], 'name': row.get('filename'),
               'drive_url': row.get('url'), 'report_date': row.get('report_date') or row['date'],
               'modified_time': row.get('modified_time'), 'text': text}
        # Patch only this process, only for this call. Never call broker.main().
        with patch.object(broker, 'complete_report', complete), \
             patch.object(broker, 'normalize_report', normalize), \
             patch.object(broker, 'COMPANIES', companies):
            result = broker.analyze_report(src)
        if not result.get('summary') or not (result.get('research_sections') or result.get('industry_sections') or result.get('detail')):
            raise ValueError('Incomplete analysis; retain PDF preview')
        # The normalized broker result excludes raw PDF text. Whitelist public fields.
        fields = ('visualizations','emphasis','date','broker','report_type','title','action','ticker','name',
                  'rating','target_price_old','target_price_new','push_reason','summary','key_points','beneficiaries',
                  'risks','forecast_changes','detail','research_sections','industry_sections','ai_layout_version',
                  'ai_processed_at','quarterly_eps','financial_forecasts','recommendation_headlines','stock_views',
                  'implied_upside_pct','upside_basis','reference_close','validation_status','audit_version')
        public = {k: result[k] for k in fields if k in result}
        public.update(id=row['id'], source_fingerprint=key(row)[1], status='ready', group_date=row['date'],
                      source_name=row.get('filename'), source_url=row.get('url'), provider='codex-plan')
        return public
    return analyze


def error_reason(exc):
    # Never print PDF text, authentication headers or raw model responses.
    if isinstance(exc, urllib.error.HTTPError):
        return f'HTTP {exc.code}'
    if isinstance(exc, subprocess.TimeoutExpired):
        return 'subprocess timeout'
    if isinstance(exc, ValueError) and str(exc) in {
        'Not a PDF', 'PDF changed during download', 'PDF has no usable text; retain PDF preview',
        'Incomplete analysis; retain PDF preview', 'PDF exceeds download limit'}:
        return str(exc)
    return type(exc).__name__


def refreshable_drive_request(credentials, transport, original):
    """Use ADC to refresh Drive credentials only during the download phase."""
    def request(url, max_bytes=None):
        for attempt in range(2):
            headers = {}
            credentials.before_request(transport, 'GET', url, headers)
            index.TOKEN = credentials.token
            try:
                return original(url, max_bytes=max_bytes)
            except urllib.error.HTTPError as exc:
                if exc.code != 401 or attempt:
                    raise
                print('Drive HTTP 401; refreshing credentials and retrying once', flush=True)
                credentials.refresh(transport)
    return request


def run(rows, saved, day, get_files, extract, analyze, persist, clock=today):
    """Prepare private local text before Codex; no Drive requests during analysis."""
    todo = list(pending(rows, saved, day))
    total = len(todo)
    if not total:
        return 0
    started = time.monotonic()
    count = failed = download_failed = 0
    print(f'Business reports pending: {total}; phase 1: prepare PDFs', flush=True)
    files = {f['id']: f for f in get_files()}
    with tempfile.TemporaryDirectory(prefix='business-prefetch-') as tmp:
        prepared = []
        for n, row in enumerate(todo, 1):
            if clock() != day:
                print('Taipei date changed; stop preparation', flush=True)
                break
            file = files.get(row['id'])
            if not file or index.fingerprint(file) != key(row)[1]:
                download_failed += 1
                print(f'[PDF {n}/{total}] Changed or missing; retain preview: {row["id"]}', flush=True)
                continue
            try:
                text = extract(file)
                path = Path(tmp) / f'{n}.txt'
                path.write_text(text, encoding='utf-8')
                prepared.append((row, path))
                print(f'[PDF {n}/{total}] Ready: {row.get("filename", row["id"])}', flush=True)
            except Exception as exc:
                download_failed += 1
                print(f'[PDF {n}/{total}] Failed: {row.get("filename", row["id"])} | {error_reason(exc)}', flush=True)
        print(f'PDF preparation complete: {len(prepared)}/{total}; failed={download_failed}; phase 2: Codex', flush=True)
        for n, (row, path) in enumerate(prepared, 1):
            if clock() != day:
                print('Taipei date changed; stop analysis', flush=True)
                break
            label = row.get('filename') or row['id']
            t = time.monotonic()
            print(f'[AI {n}/{len(prepared)}] Analyzing: {label} | success={count} failed={failed}', flush=True)
            try:
                result = analyze(row, path.read_text(encoding='utf-8'))
            except NoReportCapacity:
                print('Codex plan exhausted; remaining reports keep PDF preview.', flush=True)
                break
            except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
                print(f'Business Codex unavailable: {error_reason(exc)}; remaining reports keep PDF preview', flush=True)
                break
            except Exception as exc:
                failed += 1
                print(f'[AI {n}/{len(prepared)}] Rejected: {label} | {error_reason(exc)} | {time.monotonic()-t:.1f}s', flush=True)
                continue
            saved[:] = [r for r in saved if r.get('id') != row['id']] + [result]
            persist(saved)
            count += 1
            print(f'[AI {n}/{len(prepared)}] Success: {label} | {time.monotonic()-t:.1f}s | success={count}/{total} failed={failed} | elapsed={time.monotonic()-started:.1f}s', flush=True)
    print(f'Business progress: success={count}/{total}, PDF failures={download_failed}, AI rejected={failed}, other uncompleted={total-count-download_failed-failed}, elapsed={time.monotonic()-started:.1f}s', flush=True)
    return count


def main():
    day = today()
    rows = read_items(INDEX)
    saved = read_items(OUTPUT)
    if not list(pending(rows, saved, day)):
        print('No unparsed business reports for', day)
        return
    analyze = broker_analyzer()
    def persist(items):
        index.write_json(OUTPUT, {'items': sorted(items, key=lambda x: (x.get('group_date',''),x.get('id','')), reverse=True)})
    # The workflow provides a freshly generated token and an ADC credential file.
    # Keep refresh local to this process; the existing index and broker jobs are unchanged.
    if os.environ.get('BUSINESS_DRIVE_REFRESH') == '1':
        import google.auth
        from google.auth.transport.requests import Request
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive.readonly'])
        with patch.object(index, 'request', refreshable_drive_request(credentials, Request(), index.request)):
            count = run(rows, saved, day, index.list_files, extract_text, analyze, persist)
    else:
        count = run(rows, saved, day, index.list_files, extract_text, analyze, persist)
    print('Business reports newly analyzed:', count)


if __name__ == '__main__':
    main()
