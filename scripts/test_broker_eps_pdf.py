#!/usr/bin/env python3
"""Isolated, read-only audit of quarterly EPS estimates in broker PDFs on Google Drive.

No OpenAI, no Telegram, no changes to existing report data. Downloads at most 10
stock-specific PDFs using the same Google Cloud service account as reports-drive.yml.
Conservative extraction: accepts only EPS rows under explicitly forecast-marked
quarter columns. Ambiguous matches are recorded for manual review, not published.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
QUARTER = re.compile(r'(?<![\w\d])(?:(?P<q1>[1-4])\s*Q\s*(?P<y1>20\d{2}|\d{2})|(?P<y2>20\d{2}|\d{2})\s*Q\s*(?P<q2>[1-4]))\s*(?P<flag>[AEFP])?(?!\w)', re.I)
EPS_ROW = re.compile(r'(?<![A-Za-z])EPS(?![A-Za-z])|每股(?:稅後)?(?:盈餘|純益)|每股收益', re.I)
NUM = re.compile(r'^\(?[-+]?\d+(?:,\d{3})*(?:\.\d+)?\)?$')
FORECAST_CONTEXT = re.compile(r'forecast|estimate|預估|預測|預期|預計|預估值', re.I)
ACTUAL_CONTEXT = re.compile(r'actual|reported|實際|已公布|已公告', re.I)


def normalize_quarter(m):
    year = int(m.group('y1') or m.group('y2'))
    if year < 100:
        year += 2000
    return f"{year}-Q{m.group('q1') or m.group('q2')}"


def number(raw):
    raw = raw.strip().replace(',', '')
    if not NUM.fullmatch(raw.replace(',', '')):
        return None
    negative = raw.startswith('(') and raw.endswith(')')
    try:
        n = float(raw.strip('()')) * (-1 if negative else 1)
    except ValueError:
        return None
    return round(n, 5) if -100 <= n <= 100 else None


def extract_table(text):
    """Conservative row/column alignment with pdftotext -layout preserved spacing."""
    lines = text.splitlines()
    accepted, review = [], []
    for idx, line in enumerate(lines):
        if not EPS_ROW.search(line):
            continue
        # Reject ratios, growth rates, revisions and prose; look for numeric EPS row.
        if re.search(r'growth|YoY|QoQ|%|成長|增幅|調整|變動|修正|上修|下修', line, re.I):
            continue
        matches = list(re.finditer(r'(?<!\S)\(?[-+]?\d+(?:,\d{3})*(?:\.\d+)?\)?(?=\s|$)', line))
        values = [(m.start(), number(m.group())) for m in matches if number(m.group()) is not None]
        if not values:
            continue
        candidates = []
        for hidx in range(max(0, idx-12), idx):
            header = lines[hidx]
            periods = list(QUARTER.finditer(header))
            if not periods:
                continue
            # Only consider tables where the period headings map one-to-one to
            # the number of EPS columns. This prevents silent column shifts.
            if len(periods) != len(values):
                continue
            for col, pm in enumerate(periods):
                flag = (pm.group('flag') or '').upper()
                # A missing E/F/P may be a historical actual: never assume forecast.
                if flag not in ('E', 'F', 'P'):
                    continue
                # Strictly ensure numerical value lies under heading (allow text-width drift).
                pos, eps = values[col]
                if abs(pos - pm.start()) > 22:
                    continue
                candidates.append({
                    'period': normalize_quarter(pm), 'eps': eps,
                    'method': 'pdf_table_explicit_forecast',
                    'page_line': idx + 1,
                    'header': header.strip()[:200],
                    'eps_row': line.strip()[:200],
                })
        uniq = {(x['period'], x['eps']): x for x in candidates}
        if len(uniq) == 1:
            accepted.append(next(iter(uniq.values())))
        elif len(uniq) > 1:
            # Multiple forecast quarters in a row are valid if from a single
            # consistent header; do not reject a well-formed multi-quarter table.
            hset = {x['header'] for x in uniq.values()}
            if len(hset) == 1:
                accepted.extend(uniq.values())
            else:
                review.append({'reason': 'conflicting_headers', 'line': idx+1, 'eps_row': line.strip()[:200]})
        else:
            review.append({'reason': 'no_safe_quarter_column_alignment', 'line': idx+1, 'eps_row': line.strip()[:200]})
    # Avoid duplicates and conflicting EPS for a report and period.
    by_period = {}
    for x in accepted:
        by_period.setdefault(x['period'], []).append(x)
    safe = []
    for period, xs in by_period.items():
        vals = {x['eps'] for x in xs}
        if len(vals) == 1:
            safe.append(xs[0])
        else:
            review.append({'reason': 'conflicting_eps_same_period', 'period': period,
                           'values': sorted(vals)})
    return safe, review


def download_pdf(file_id, token, path):
    url = f'https://www.googleapis.com/drive/v3/files/{file_id}'
    response = requests.get(url, params={'alt': 'media', 'supportsAllDrives': 'true'},
                            headers={'Authorization': f'Bearer {token}'}, timeout=75)
    response.raise_for_status()
    if not response.content.startswith(b'%PDF'):
        raise ValueError('Drive response is not a PDF')
    path.write_bytes(response.content)


def run(args):
    reports = json.loads(args.source.read_text(encoding='utf-8'))['items']
    # Stock-specific PDFs only, recent first; skip thematic and missing tickers.
    eligible = [x for x in reports if re.fullmatch(r'\d{4}', str(x.get('ticker') or ''))
                and (x.get('source_file_id') or x.get('id'))
                and str(x.get('source_name') or '').lower().endswith('.pdf')
                and x.get('broker')]
    eligible.sort(key=lambda x: (str(x.get('date') or ''), str(x.get('received_at') or '')), reverse=True)
    if args.tickers:
        allowed = set(args.tickers.split(','))
        eligible = [x for x in eligible if str(x.get('ticker')) in allowed]
    selected = eligible[:min(args.limit, 10)]
    output, audit, counts = [], [], Counter()
    token = os.getenv('ACCESS_TOKEN', '').strip()
    if not token:
        raise SystemExit('ACCESS_TOKEN missing: run through test-broker-eps-pdf.yml')
    with tempfile.TemporaryDirectory() as temp:
        for report in selected:
            fid = report.get('source_file_id') or report['id']
            entry = {'ticker': report['ticker'], 'broker': report['broker'],
                     'report_date': report.get('date'), 'report_id': report.get('id'),
                     'source_name': report.get('source_name')}
            try:
                pdf = Path(temp) / 'source.pdf'
                download_pdf(fid, token, pdf)
                proc = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(pdf), '-'],
                                      capture_output=True, text=True, timeout=45)
                if proc.returncode:
                    raise RuntimeError('pdftotext failed: ' + proc.stderr[:180])
                if len(proc.stdout.strip()) < 100:
                    entry['status'] = 'pdf_text_empty_or_scanned'
                    counts[entry['status']] += 1
                    audit.append(entry)
                    continue
                safe, review = extract_table(proc.stdout)
                for x in safe:
                    output.append({**x, 'ticker': str(report['ticker']),
                                   'name': report.get('name') or '', 'broker': report['broker'],
                                   'report_date': report.get('date'), 'report_id': report.get('id'),
                                   'source_url': report.get('source_url')})
                entry.update(status='processed', extracted_characters=len(proc.stdout),
                             accepted_forecasts=len(safe), review_count=len(review),
                             review_examples=review[:8])
                counts['processed'] += 1
                counts['accepted'] += len(safe)
                counts['needs_review'] += len(review)
            except Exception as exc:
                entry.update(status='error', error=str(exc)[:250])
                counts['error'] += 1
            audit.append(entry)
            print(f"{entry['ticker']} {entry['broker']}: {entry['status']} "
                  f"EPS={entry.get('accepted_forecasts', 0)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'mode': 'test_only_no_ai_no_push',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'forecasts': output}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    args.audit.write_text(json.dumps({'mode': 'read_only_pdf_test',
        'eligible_reports': len(eligible), 'selected_reports': len(selected),
        'accepted_forecasts': len(output), 'counts': dict(counts),
        'reports': audit,
        'limitations': ['Only explicitly forecast-marked quarterly EPS table columns are accepted.',
                        'All matches require human verification against the PDF before production use.',
                        'Scanned/image-only PDF tables are not OCRed.',
                        'No OpenAI API, no Telegram, no commits or changes to existing data.']},
        ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Eligible={len(eligible)}, tested={len(selected)}, accepted={len(output)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT/'data/reports.json')
    parser.add_argument('--output', type=Path, default=ROOT/'data/broker_eps_pdf_test.json')
    parser.add_argument('--audit', type=Path, default=ROOT/'data/broker_eps_pdf_audit.json')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--tickers', default='', help='Optional comma-separated stock codes')
    run(parser.parse_args())
