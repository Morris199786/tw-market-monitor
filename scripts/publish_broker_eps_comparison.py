#!/usr/bin/env python3
"""Publish validated, report-level quarterly broker EPS forecasts (no AI, no push)."""
import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_BROKERS = re.compile(r'morgan\s*stanley|摩根士丹利|bofa|merrill|美銀|美林', re.I)
PERIOD = re.compile(r'^(20\d\d)-Q([1-4])$')


def build(raw, excluded_ids=()):
    dedup = {}
    for r in raw.get('forecasts', []):
        ticker = str(r.get('ticker') or '').strip()
        broker = str(r.get('broker') or '').strip()
        period = str(r.get('period') or '')
        report_date = str(r.get('report_date') or '')[:10].replace('/', '-').replace('.', '-')
        m = PERIOD.fullmatch(period)
        if not (re.fullmatch(r'\d{4}', ticker) and broker and m and re.fullmatch(r'20\d\d-\d\d-\d\d', report_date)):
            continue
        if EXCLUDE_BROKERS.search(broker):
            continue  # Broker families explicitly excluded from EPS matching until validated.
        try:
            rd = date.fromisoformat(report_date)
            qy, q = int(m[1]), int(m[2])
            quarter_end = date(qy, q * 3 + 1, 1) - timedelta(days=1) if q < 4 else date(qy, 12, 31)
        except ValueError:
            continue
        # Historical EPS in a current report are not a forecast. Retain recent
        # completed quarters, since reports can precede official EPS releases.
        if rd > quarter_end + timedelta(days=100):
            continue
        value = r.get('eps')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not (-100 <= value <= 100):
            continue
        report_id = str(r.get('report_id') or '').strip()
        if not report_id or report_id in excluded_ids:
            continue
        key = (ticker, period, report_id)
        candidate = {
            'ticker': ticker, 'period': period, 'eps': round(float(value), 5),
            'broker': broker, 'report_date': report_date, 'report_id': report_id,
            'source_url': r.get('source_url') or '',
        }
        # Conflicting EPS for same report+quarter are ambiguous: discard rather than guess.
        if key in dedup and dedup[key] != candidate:
            dedup[key] = None
        elif key not in dedup:
            dedup[key] = candidate
    items = [x for x in dedup.values() if x is not None]
    items.sort(key=lambda r: (r['ticker'], r['period'], r['report_date'], r['broker']), reverse=True)
    return {'version': 1, 'generated_at': raw.get('generated_at'), 'items': items}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, default=ROOT/'data/broker_eps_pdf_test.json')
    p.add_argument('--output', type=Path, default=ROOT/'data/broker_eps_forecasts.json')
    p.add_argument('--merge-existing', action='store_true', help='Append only new report IDs; preserve existing published forecasts')
    a = p.parse_args()
    quarantine = ROOT / 'data/broker_eps_review_exclusions.json'
    excluded_ids = set(json.loads(quarantine.read_text(encoding='utf-8')).get('report_ids', [])) if quarantine.exists() else set()
    result = build(json.loads(a.input.read_text(encoding='utf-8')), excluded_ids)
    if a.merge_existing and a.output.exists():
        old = json.loads(a.output.read_text(encoding='utf-8'))
        original = old.get('items', [])
        known = {(str(x.get('report_id')), str(x.get('ticker')), str(x.get('period'))) for x in original}
        fresh = [x for x in result['items'] if (str(x.get('report_id')), str(x.get('ticker')), str(x.get('period'))) not in known]
        if not fresh:
            print(f'No new forecast rows; keeping all {len(original)} existing forecasts unchanged')
            return
        result['items'] = original + fresh
        result['items'].sort(key=lambda r: (r['ticker'], r['period'], r['report_date'], r['broker']), reverse=True)
        print(f'Preserved {len(original)} existing rows; added {len(fresh)} new rows')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"Published {len(result['items'])} broker quarterly EPS forecasts (no AI)")

if __name__ == '__main__':
    main()
