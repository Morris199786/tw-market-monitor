#!/usr/bin/env python3
"""Incremental broker PDF selection and durable processed-report ledger.

Only NEW report IDs are parsed. A successful parse with zero EPS is still
marked processed. Transient failures remain retryable. No AI/Telegram.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def eligible(report):
    return (bool(re.fullmatch(r'\d{4}', str(report.get('ticker') or '')))
            and bool(report.get('source_file_id') or report.get('id'))
            and str(report.get('source_name') or '').lower().endswith('.pdf')
            and bool(report.get('broker')))


def report_id(report):
    return str(report.get('id') or report.get('source_file_id') or '').strip()


def select_new(reports, ledger, forecasts):
    done = set(ledger.get('reports', {}))
    # Backward compatibility if the ledger was not present at initial deployment:
    # any report already published is automatically considered processed.
    done.update(str(x.get('report_id')) for x in forecasts.get('items', []) if x.get('report_id'))
    seen = set()
    selected = []
    for r in reports.get('items', []):
        rid = report_id(r)
        if eligible(r) and rid and rid not in done and rid not in seen:
            selected.append(r)
            seen.add(rid)
    selected.sort(key=lambda r: (str(r.get('date') or ''), str(r.get('received_at') or '')))
    return selected


def prepare(args):
    reports = load(args.reports, {'items': []})
    if not args.reports.exists():
        raise FileNotFoundError(f'Missing reports index: {args.reports}')
    ledger = load(args.ledger, {'version': 1, 'reports': {}})
    forecasts = load(args.forecasts, {'items': []})
    selected = select_new(reports, ledger, forecasts)
    args.selected.parent.mkdir(parents=True, exist_ok=True)
    args.selected.write_text(json.dumps({'items': selected}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    args.marker.write_text(str(len(selected)) + '\n', encoding='utf-8')
    print(f'Incremental EPS: {len(selected)} new PDF(s); previously processed PDFs skipped.')
    for r in selected:
        print(f"NEW: {report_id(r)} {r.get('ticker')} {r.get('broker')} {r.get('source_name')}")


def finalize(args):
    audit = load(args.audit, None)
    if not isinstance(audit, dict) or not isinstance(audit.get('reports'), list):
        raise ValueError('Missing/invalid new PDF audit; refusing to mark reports processed')
    ledger = load(args.ledger, {'version': 1, 'reports': {}})
    records = ledger.setdefault('reports', {})
    now = datetime.now(timezone.utc).isoformat()
    completed = 0
    retry = 0
    for r in audit['reports']:
        rid = str(r.get('report_id') or '').strip()
        if not rid:
            continue
        if r.get('status') == 'error':
            retry += 1
            print(f'RETRY NEXT RUN: {rid} {r.get("error", "unknown error")}')
            continue
        if r.get('status') not in ('processed', 'pdf_text_empty_or_scanned'):
            retry += 1
            print(f'RETRY NEXT RUN: {rid} unexpected status {r.get("status")}')
            continue
        records[rid] = {
            'ticker': str(r.get('ticker') or ''),
            'broker': str(r.get('broker') or ''),
            'report_date': str(r.get('report_date') or ''),
            'source_name': str(r.get('source_name') or ''),
            'status': r['status'],
            'accepted_forecasts': int(r.get('accepted_forecasts') or 0),
            'pdf_sha256': str(r.get('pdf_sha256') or ''),
            'processed_at': now,
        }
        completed += 1
    ledger['version'] = 1
    ledger['updated_at'] = now
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Ledger updated: {completed} newly processed; {retry} retryable failures; total={len(records)}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=('prepare', 'finalize'))
    p.add_argument('--reports', type=Path, default=ROOT / 'data/reports.json')
    p.add_argument('--ledger', type=Path, default=ROOT / 'data/broker_eps_processed.json')
    p.add_argument('--forecasts', type=Path, default=ROOT / 'data/broker_eps_forecasts.json')
    p.add_argument('--selected', type=Path, default=ROOT / 'data/broker_eps_new_reports.json')
    p.add_argument('--marker', type=Path, default=ROOT / 'data/broker_eps_new_count.txt')
    p.add_argument('--audit', type=Path, default=ROOT / 'data/broker_eps_audit_new.json')
    args = p.parse_args()
    (prepare if args.command == 'prepare' else finalize)(args)


if __name__ == '__main__':
    main()
