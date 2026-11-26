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


def run(rows, saved, day, get_files, extract, analyze, persist, clock=today):
    """Save every success; stop on capacity/worker failures, skip bad individual PDFs."""
    todo = list(pending(rows, saved, day))
    if not todo:
        return 0
    files = {f['id']: f for f in get_files()}
    count = 0
    for row in todo:
        if clock() != day:  # Prevent cross-midnight historical backfill.
            break
        file = files.get(row['id'])
        if not file or index.fingerprint(file) != key(row)[1]:
            print('Business PDF changed or missing; retain preview:', row['id'])
            continue
        try:
            text = extract(file)
        except Exception as exc:
            print('Business PDF extraction skipped:', row['id'], type(exc).__name__)
            continue
        if clock() != day:
            break
        try:
            result = analyze(row, text)
        except NoReportCapacity:
            print('Codex plan exhausted; remaining reports keep PDF preview.')
            break
        except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
            # SSH, worker or Codex unavailable. Do not call API or loop through all PDFs.
            print('Business Codex unavailable; remaining reports keep PDF preview:', type(exc).__name__)
            break
        except Exception as exc:
            print('Business analysis rejected; retain PDF preview:', row['id'], type(exc).__name__)
            continue
        # Keep the prior successful version until a new version has succeeded.
        saved[:] = [r for r in saved if r.get('id') != row['id']] + [result]
        persist(saved)
        count += 1
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
    count = run(rows, saved, day, index.list_files, extract_text, analyze, persist)
    print('Business reports newly analyzed:', count)


if __name__ == '__main__':
    main()
