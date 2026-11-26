#!/usr/bin/env python3
"""Business reports: today's PDFs only; one Codex subscription call per report.
Uses the broker analyzer, never its main/claim/notification pipeline.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
import urllib.parse
import urllib.error
import time
import signal
import sys

import update_business_reports as index
from report_provider import complete_plan_report, NoReportCapacity

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
INDEX = DATA / 'business_reports.json'
OUTPUT = DATA / 'business_reports_ai.json'
TZ = ZoneInfo('Asia/Taipei')


def today(now=None):
    """Taipei business day changes at 02:00, not midnight."""
    local = datetime.now(TZ) if now is None else now.astimezone(TZ)
    return (local - timedelta(hours=2)).date().isoformat()


def processing_day():
    """Use the workflow's pinned business day throughout a single run."""
    return os.environ.get('BUSINESS_REPORT_DAY') or today()


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
        print("[AI stage] Codex request", flush=True)
        value = complete_plan_report(payload)
        print("[AI stage] Codex returned; decoding/validation", flush=True)
        return value

    original_normalize = broker.normalize_report

    def normalize(obj, src):
        print("[AI stage] normalize and audit", flush=True)
        result = original_normalize(obj, src)
        print('[AI stage] normalized; financial extraction', flush=True)
        result['quarterly_eps'] = broker_eps_pipeline.normalize(obj.get('quarterly_eps'))
        result['financial_forecasts'] = eps.normalize_financial(obj.get('financial_forecasts'))
        print('[AI stage] financial extraction complete; issuer audit next', flush=True)
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
        print('[AI stage] issuer audit complete', flush=True)
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
    if isinstance(exc, (ReportWorkerError, ReportRejected)):
        code = str(exc)
        return code if code in {'RuntimeError', 'ValueError', 'OSError', 'TypeError', 'KeyError', 'INVALID_JSON', 'ISSUER_TICKER_CONFLICT', 'ISSUER_AMBIGUOUS', 'COVER_ISSUER_CONFLICT', 'TARGET_PRICE_CONFLICT', 'SOURCE_TEXT_MISSING', 'INPUT_LIMIT', 'RESULT_IDENTITY_MISMATCH', 'INVALID_WORKER_RESPONSE', 'WORKER_INCOMPLETE', 'WORKER_FAILED', 'Incomplete analysis; retain PDF preview'} or code in {'SSH_PRIVATE_KEY_PERMISSIONS', 'SSH_PRIVATE_KEY_FORMAT', 'SSH_KEY_FORMAT', 'SSH_HOST_KEY_CHECK', 'SSH_LOGIN_DENIED', 'SSH_TARGET_NAME', 'SSH_TIMEOUT', 'SSH_CONNECTION_REFUSED', 'SSH_NO_ROUTE', 'SSH_CONNECTION_RESET', 'SSH_CONNECTION_CLOSED', 'SSH_UNCLASSIFIED'} else type(exc).__name__
    if isinstance(exc, ReportTimeout):
        return str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        return f'HTTP {exc.code}'
    if isinstance(exc, subprocess.TimeoutExpired):
        return 'subprocess timeout'
    if isinstance(exc, ValueError) and str(exc) in {
        'Not a PDF', 'PDF changed during download', 'PDF has no usable text; retain PDF preview',
        'Incomplete analysis; retain PDF preview', 'PDF exceeds download limit'}:
        return str(exc)
    # Only emit fixed diagnostic categories, never arbitrary exception text.
    if isinstance(exc, json.JSONDecodeError):
        return 'INVALID_JSON'
    message = str(exc)
    for prefix, code in (
        ('company name/ticker conflict:', 'ISSUER_TICKER_CONFLICT'),
        ('unsupported or ambiguous Taiwan identity:', 'ISSUER_AMBIGUOUS'),
        ('cover and generated issuer conflict', 'COVER_ISSUER_CONFLICT'),
        ('conflicting current target prices', 'TARGET_PRICE_CONFLICT'),
        ('source text unavailable', 'SOURCE_TEXT_MISSING'),
        ('Report exceeds safe input limit', 'INPUT_LIMIT'),
        ('isolated result identity mismatch', 'RESULT_IDENTITY_MISMATCH'),
    ):
        if message.startswith(prefix):
            return code
    if isinstance(exc, RuntimeError):
        # Provider diagnostics already consist of allowlisted labels.
        import re
        cause = exc
        while cause is not None:
            match = re.fullmatch(r'Private report worker failed \(exit \d+, ((?:SSH_[A-Z_]+|WORKER_FAILED))\)', str(cause))
            if match:
                return match.group(1)
            if str(cause) == 'Invalid private report worker response':
                return 'INVALID_WORKER_RESPONSE'
            if str(cause) == 'Private report worker did not complete the request':
                return 'WORKER_INCOMPLETE'
            cause = cause.__cause__
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



class ReportWorkerError(RuntimeError):
    """Isolated worker failure with a sanitized diagnostic category."""


class ReportRejected(ValueError):
    """Isolated report validation failure with a sanitized category."""


class ReportTimeout(ValueError):
    """One report exceeded the local end-to-end deadline."""


def bounded_process(cmd, limit, heartbeat=30, label='report'):
    """Linux runner: separate process group, inherited live stdout, no pipe deadlock."""
    started = time.monotonic()
    proc = subprocess.Popen(cmd, start_new_session=True)
    try:
        while True:
            remaining = limit - (time.monotonic() - started)
            if remaining <= 0:
                raise ReportTimeout(f'{label} exceeded {limit}s')
            try:
                return proc.wait(timeout=min(heartbeat, remaining))
            except subprocess.TimeoutExpired:
                print(f'[heartbeat] {label} | elapsed={time.monotonic()-started:.0f}s', flush=True)
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)


def child_analyze(input_path, output_path):
    """Only whitelisted result crosses the process boundary; never print raw text."""
    try:
        request = json.loads(Path(input_path).read_text(encoding='utf-8'))
        result = broker_analyzer()(request['row'], request['text'])
        reply = {'status': 'ok', 'result': result}
    except NoReportCapacity:
        reply = {'status': 'limit'}
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        cause = exc
        while cause is not None and not isinstance(cause, subprocess.TimeoutExpired):
            cause = cause.__cause__
        reply = {'status': 'timeout' if cause is not None else 'worker_error', 'reason': error_reason(exc)}
    except Exception as exc:
        reply = {'status': 'rejected', 'reason': error_reason(exc)}
    Path(output_path).write_text(json.dumps(reply, ensure_ascii=False), encoding='utf-8')


def isolated_analyze(row, text, limit=720, heartbeat=30):
    with tempfile.TemporaryDirectory(prefix='business-single-') as tmp:
        inp, out = Path(tmp)/'input.json', Path(tmp)/'output.json'
        inp.write_text(json.dumps({'row':row,'text':text}, ensure_ascii=False), encoding='utf-8')
        rc = bounded_process([sys.executable, '-u', str(Path(__file__).resolve()), '--single', str(inp), str(out)], limit, heartbeat, 'single report')
        if rc != 0 or not out.exists():
            raise ValueError(f'isolated report exited {rc}')
        reply = json.loads(out.read_text(encoding='utf-8'))
        status = reply.get('status')
        if status == 'limit':
            raise NoReportCapacity('Codex plan limit reached')
        if status == 'worker_error':
            raise ReportWorkerError(str(reply.get('reason', 'unknown'))) 
        if status == 'timeout':
            raise ReportTimeout('SSH/Codex request timeout')
        if status != 'ok':
            raise ReportRejected(str(reply.get('reason', 'unknown')))
        result = reply['result']
        if key(result) != key(row) or result.get('status') != 'ready':
            raise ValueError('isolated result identity mismatch')
        return result


def publish_checkpoint():
    publisher = os.environ.get('BUSINESS_CHECKPOINT_PUBLISHER')
    if not publisher:
        return
    rc = bounded_process([publisher, 'Update business report AI checkpoint', 'data/business_reports_ai.json'], 120, 30, 'publish checkpoint')
    if rc:
        raise RuntimeError(f'checkpoint publishing failed (exit {rc})')
    print('[checkpoint] published to GitHub', flush=True)


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
            except ReportTimeout as exc:
                failed += 1
                print(f'[AI {n}/{len(prepared)}] Timeout; retain PDF: {label} | {error_reason(exc)}', flush=True)
                continue
            except NoReportCapacity:
                print('Codex plan exhausted; remaining reports keep PDF preview.', flush=True)
                break
            except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
                failed += 1
                print(f'[AI {n}/{len(prepared)}] Worker failure; retain PDF and continue: {label} | {error_reason(exc)} | {time.monotonic()-t:.1f}s', flush=True)
                continue
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
    day = processing_day()
    rows = read_items(INDEX)
    saved = read_items(OUTPUT)
    if not list(pending(rows, saved, day)):
        print('No unparsed business reports for', day)
        return
    analyze = isolated_analyze
    def persist(items):
        index.write_json(OUTPUT, {'items': sorted(items, key=lambda x: (x.get('group_date',''),x.get('id','')), reverse=True)})
        publish_checkpoint()
    # The workflow provides a freshly generated token and an ADC credential file.
    # Keep refresh local to this process; the existing index and broker jobs are unchanged.
    if os.environ.get('BUSINESS_DRIVE_REFRESH') == '1':
        import google.auth
        from google.auth.transport.requests import Request
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive.readonly'])
        with patch.object(index, 'request', refreshable_drive_request(credentials, Request(), index.request)):
            count = run(rows, saved, day, index.list_files, extract_text, analyze, persist, clock=lambda: day)
    else:
        count = run(rows, saved, day, index.list_files, extract_text, analyze, persist, clock=lambda: day)
    print('Business reports newly analyzed:', count)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--single':
        child_analyze(sys.argv[2], sys.argv[3])
    else:
        main()
