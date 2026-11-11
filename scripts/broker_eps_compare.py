#!/usr/bin/env python3
"""Evidence-dated EPS comparison; offline, deterministic, no paid calls.

Only actual EPS with an explicit, verified announcement date may match a
broker report whose date is earlier than or equal to. Never derive a disclosure date
from a fiscal period, file mtime, or a scheduled board meeting.
"""
from __future__ import annotations
import json
import math
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARTER = re.compile(r'^20\d{2}-Q[1-4]$')
MONTH = re.compile(r'^20\d{2}-(?:0[1-9]|1[0-2])$')
TICKER = re.compile(r'^\d{4}$')

def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default

def valid_date(value):
    s = str(value or '')[:10]
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return ''

def gm_valid_date(value):
    """Normalize broker report dates for gross margin without changing EPS logic."""
    return valid_date(str(value or '')[:10].replace('/', '-'))

def number(value):
    if isinstance(value, bool) or value is None or str(value).strip() == '':
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None

def actuals(data):
    """All verifiably dated monthly/quarterly announcements, including history."""
    seen = set()
    sources = (
        ('self_reports.json', 'items'),
        ('self_reports_history.json', 'items'),
        ('quarterly_earnings.json', 'reports'),
        ('quarterly_earnings_announcements_history.json', 'items'),
    )
    for filename, key in sources:
        for r in load(data / filename, {}).get(key, []):
            ticker = str(r.get('ticker') or '')
            day = valid_date(r.get('publish_date'))
            if not TICKER.fullmatch(ticker) or not day:
                continue
            candidates = []
            if filename.startswith('self_reports'):
                month = str(r.get('monthly_period') or '')
                if MONTH.fullmatch(month):
                    period = f'{month[:4]}-Q{(int(month[5:])-1)//3+1}'
                    candidates.append(('monthly', month, period, number(r.get('monthly_eps'))))
                # A self-report may also explicitly disclose last quarter's EPS.
                # Its own publication date, not the financial period, is used.
                qp = str(r.get('quarter_period') or '')
                if QUARTER.fullmatch(qp):
                    candidates.append(('quarterly', qp, qp, number(r.get('quarter_eps'))))
            else:
                qp = str(r.get('period') or '')
                if QUARTER.fullmatch(qp):
                    candidates.append(('quarterly', qp, qp, number(r.get('eps'))))
            for kind, actual_period, period, eps in candidates:
                if eps is None:
                    continue
                ident = (ticker, kind, actual_period, day, eps)
                if ident in seen:
                    continue
                seen.add(ident)
                yield {'ticker': ticker, 'name': r.get('name') or '', 'kind': kind,
                       'actual_period': actual_period, 'period': period,
                       'announcement_date': day, 'actual_eps': eps,
                       'actual_source': filename}

def compare(root=ROOT):
    data = root / 'data'
    # Keep the legacy EPS JSON (including sealed historical forecasts).
    # Supplement only missing report+quarter pairs from the ONE-SHOT AI data.
    # No calls to the model and no PDF reads in this comparison action.
    forecasts = list(load(data / 'broker_eps_forecasts.json', {'items': []}).get('items', []))
    known = {(str(x.get('report_id')), str(x.get('period'))) for x in forecasts}
    ai_added = 0
    from broker_eps_pipeline import ai_eps_rows
    for report in load(data / 'reports.json', {'items': []}).get('items', []):
        if not isinstance(report, dict):
            continue
        rid = str(report.get('source_file_id') or report.get('id') or '')
        ticker = str(report.get('ticker') or '')
        broker = str(report.get('broker') or '')
        report_day = valid_date(report.get('date'))
        if not rid or not TICKER.fullmatch(ticker) or not broker or not report_day:
            continue
        rows, _ = ai_eps_rows(report)
        for row in rows:
            key = (rid, row['period'])
            if key in known:
                continue
            forecasts.append({'report_id':rid, 'ticker':ticker, 'broker':broker,
                              'report_date':report_day, 'source_url':report.get('source_url') or '',
                              'period':row['period'], 'eps':row['eps']})
            known.add(key)
            ai_added += 1
    by_key = {}
    for f in forecasts:
        ticker, period = str(f.get('ticker') or ''), str(f.get('period') or '')
        day, eps = valid_date(f.get('report_date')), number(f.get('eps'))
        if not TICKER.fullmatch(ticker) or not QUARTER.fullmatch(period) or not day or eps in (None, 0) or not f.get('report_id'):
            continue
        by_key.setdefault((ticker, period), []).append((f, day, eps))
    matches = {}
    audit = {'direct_ai_forecasts_added': ai_added, 'forecasts': len(forecasts), 'valid_forecasts': sum(map(len, by_key.values())),
             'dated_actuals': 0, 'potential_same_ticker_period': 0,
             'excluded_late': 0, 'matches': 0}
    for a in actuals(data):
        audit['dated_actuals'] += 1
        for f, report_day, estimate in by_key.get((a['ticker'], a['period']), []):
            audit['potential_same_ticker_period'] += 1
            if report_day > a['announcement_date']:
                audit['excluded_late'] += 1
                continue
            rid = str(f['report_id'])
            key = (a['ticker'], a['kind'], a['actual_period'], a['announcement_date'], a['actual_eps'], rid)
            matches[key] = {
                'ticker': a['ticker'], 'name': a['name'], 'period': a['period'],
                'actual_kind': a['kind'], 'actual_period': a['actual_period'],
                'announcement_date': a['announcement_date'], 'actual_eps': a['actual_eps'],
                'broker': f.get('broker') or '', 'report_date': report_day,
                'report_id': rid, 'forecast_eps': estimate,
                'ratio_pct': round(a['actual_eps'] / estimate * 100, 1),
                'ratio_label': '單月／季預估比' if a['kind'] == 'monthly' else '季度達成率',
                'source_url': f.get('source_url') or '',
                'actual_source': a['actual_source']}
    output = {'version': 3, 'items': sorted(matches.values(), key=lambda x:
              (x['ticker'], x['period'], x['actual_period'], x['announcement_date'], x['report_date'], x['report_id']))}
    audit['matches'] = len(output['items'])
    for filename, value in (('broker_eps_comparisons.json', output), ('broker_eps_compare_audit.json', audit)):
        p = data / filename
        content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if not p.exists() or p.read_text(encoding='utf-8') != content:
            p.write_text(content, encoding='utf-8')
    print('EPS compare audit:', json.dumps(audit, ensure_ascii=False))
    gm_output = compare_gross_margin(root)
    print('Quarterly gross-margin matches:', len(gm_output['items']))
    print('API calls=0; PDF parses=0')
    return output



def parse_quarter(value):
    """Recognize explicit *quarter* periods only; never turn an annual figure into a quarter."""
    value = str(value or '').strip().upper().replace(' ', '')
    patterns = (
        r'(20\d{2})-Q([1-4])(?:E|F)?',   # 2026-Q4 / 2026-Q4E
        r'([1-4])Q(20\d{2}|\d{2})(?:E|F)?', # 3Q26 / 4Q2026E
        r'Q([1-4])(20\d{2}|\d{2})(?:E|F)?', # Q326 / Q4'26 (without apostrophe)
        r'(20\d{2})\u5e74\u7b2c?([\u4e00-\u56db1-4])\u5b63(?:\u5ea6)?',
    )
    for i, pattern in enumerate(patterns):
        m = re.fullmatch(pattern, value)
        if not m:
            continue
        if i == 0 or i == 3:
            year, q = m.groups()
            if i == 3:
                q = {'\u4e00':'1','\u4e8c':'2','\u4e09':'3','\u56db':'4'}.get(q, q)
        else:
            q, year = m.groups()
            if len(year) == 2:
                year = '20' + year
        return f'{year}-Q{q}'
    return ''


def table_margin_value(cell):
    """Accept an unambiguous percentage cell only, never ranges, deltas or text explanations."""
    if isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        value = number(cell)
    else:
        s = str(cell or '').strip().replace(',', '')
        if not re.fullmatch(r'\d+(?:\.\d+)?\s*%?', s):
            return None
        value = number(s.rstrip('%').strip())
    return value if value is not None and 0 <= value <= 100 else None


def quarter_mentions(text):
    """Look for a unique explicit fiscal quarter within a title or header."""
    s = str(text or '').upper()
    spans = re.findall(r'20\d{2}-Q[1-4]|[1-4]Q(?:20)?\d{2}|20\d{2}\u5e74\u7b2c?[\u4e00-\u56db1-4]\u5b63', s)
    periods = {p for fragment in spans if (p := parse_quarter(fragment))}
    return next(iter(periods)) if len(periods) == 1 else ''


def table_gm_forecasts(report):
    """Read pre-parsed AI visualization tables; require explicit broker estimate provenance.

    Supported: (A) quarter-per-row tables with GM column and forecast row;
    (B) metric-per-row tables with quarter-specific broker-estimate column.
    Never infer quarter from report date or a single annual estimate.
    """
    for table in report.get('visualizations') or []:
        if not isinstance(table, dict) or table.get('type') != 'table':
            continue
        headers = table.get('headers') or []
        rows = table.get('rows') or []
        if not isinstance(headers, list) or not isinstance(rows, list):
            continue
        headers = [str(h or '').strip() for h in headers]
        gm_cols = [i for i,h in enumerate(headers) if re.search(r'\u6bdb\u5229\u7387|gross\s*margin', h, re.I)]
        # A: period in first cell, GM in designated column, explicitly labeled forecast.
        for row in rows:
            if not isinstance(row, list) or not row:
                continue
            period = parse_quarter(row[0])
            if period and gm_cols:
                hint = ' '.join(str(x or '') for x in row)
                # Disallow historical/actual/consensus even when an E suffix occurs elsewhere.
                marked_forecast = (bool(re.search(r'\u5238\u5546\u9810\u4f30|\u5206\u6790\u5e2b\u9810\u4f30|\u6295\u9867\u9810\u4f30', hint))
                                   or bool(re.fullmatch(r'.*(?:E|F)', str(row[0]).strip().upper())))
                marked_actual = bool(re.search(r'\u5be6\u969b|\u5be6\u7e3e|\u6b77\u53f2|\u5171\u8b58|consensus', hint, re.I))
                if marked_forecast and not marked_actual:
                    for i in gm_cols:
                        if i < len(row) and (v := table_margin_value(row[i])) is not None:
                            yield period, v, f'table:{table.get("title") or ""}'
            # B: metric in first cell, explicit quarterly forecast in column header.
            if not re.search(r'\u6bdb\u5229\u7387|gross\s*margin', str(row[0]), re.I):
                continue
            title_quarter = quarter_mentions(table.get('title'))
            for i, header in enumerate(headers[1:], start=1):
                if i >= len(row):
                    continue
                if not re.search(r'\u9810\u4f30|estimate|forecast|\u9810\u6e2c', header, re.I):
                    continue
                if re.search(r'\u5171\u8b58|consensus|\u516c\u53f8\u6307\u5f15|guidance|\u5be6\u969b|\u5be6\u7e3e', header, re.I):
                    continue
                period = quarter_mentions(header) or title_quarter
                if not period:
                    continue
                # Do not use '2026 Q4 company guidance' as broker forecast.
                # A specific broker must be named in the header or table description.
                named_broker = str(report.get('broker') or '').lower() in header.lower()
                explicit_broker = bool(re.search(r'\u5238\u5546\u9810\u4f30|\u6295\u9867\u9810\u4f30|\u5206\u6790\u5e2b\u9810\u4f30', header))
                short_broker = bool(re.search(r'\b(?:citi|morgan stanley|goldman sachs|daiwa|ubs|clsa)\b', header, re.I))
                if not (named_broker or explicit_broker or short_broker):
                    continue
                if (v := table_margin_value(row[i])) is not None:
                    yield period, v, f'table:{table.get("title") or ""}'


def compare_gross_margin(root=ROOT):
    """Compare only QUARTERLY actual gross margins to same-quarter broker AI estimates.

    One-shot AI forecasts are already persisted in reports.json. This function
    never opens PDFs or calls any external service. Existing EPS output is untouched.
    """
    data = root / 'data'
    by_key = {}
    seen_forecasts = set()
    report_count = 0
    ambiguous = 0
    table_candidates = 0
    for report in load(data / 'reports.json', {'items': []}).get('items', []):
        if not isinstance(report, dict):
            continue
        rid = str(report.get('source_file_id') or report.get('id') or '')
        ticker = str(report.get('ticker') or '')
        broker = str(report.get('broker') or '')
        report_day = gm_valid_date(report.get('date'))
        if not rid or not TICKER.fullmatch(ticker) or not broker or not report_day:
            continue
        candidates = {}
        conflicts = set()
        for r in report.get('financial_forecasts') or []:
            if not isinstance(r, dict):
                continue
            if str(r.get('metric') or '').lower() != 'gross_margin':
                continue
            if str(r.get('type') or '').lower() != 'forecast' or str(r.get('source') or '').lower() != 'broker':
                continue
            if str(r.get('scope') or 'company').lower() != 'company':
                continue
            period = str(r.get('period') or '')
            unit = str(r.get('unit') or '').strip().lower()
            value = number(r.get('value'))
            if not QUARTER.fullmatch(period) or value is None or not 0 <= value <= 100:
                continue
            # Gross margin is a percentage. Reject fractional or currency units
            # rather than silently rescaling them.
            if unit and '%' not in unit and '百分' not in unit and 'percent' not in unit and 'pct' not in unit:
                continue
            if period in candidates and abs(candidates[period] - value) > 0.01:
                conflicts.add(period)
            else:
                candidates[period] = value
        # Use saved tables only to fill structured forecast gaps. On disagreement
        # between two saved AI fields, omit the ambiguous report-quarter.
        table_added = 0
        for period, value, evidence in table_gm_forecasts(report):
            if period in candidates:
                if abs(candidates[period] - value) > 0.011:
                    conflicts.add(period)
            else:
                candidates[period] = value
                table_added += 1
        table_candidates += table_added
        for period, estimate in candidates.items():
            if period in conflicts:
                ambiguous += 1
                continue
            ident = (rid, period)
            if ident in seen_forecasts:
                continue
            seen_forecasts.add(ident)
            by_key.setdefault((ticker, period), []).append((report, rid, report_day, estimate))
            report_count += 1

    matches = {}
    seen_actuals = set()
    dated_actuals = 0
    excluded_late = 0
    for source in ('quarterly_earnings.json', 'quarterly_earnings_announcements_history.json'):
        key = 'reports' if source == 'quarterly_earnings.json' else 'items'
        for actual in load(data / source, {}).get(key, []):
            ticker = str(actual.get('ticker') or '')
            period = str(actual.get('period') or '')
            day = valid_date(actual.get('publish_date'))
            margin = number(actual.get('gross_margin'))
            if not TICKER.fullmatch(ticker) or not QUARTER.fullmatch(period) or not day or margin is None or not 0 <= margin <= 100:
                continue
            actual_key = (ticker, period, day, margin)
            if actual_key in seen_actuals:
                continue
            seen_actuals.add(actual_key)
            dated_actuals += 1
            for report, rid, report_day, estimate in by_key.get((ticker, period), []):
                if report_day > day:
                    excluded_late += 1
                    continue
                key = (ticker, period, day, margin, rid)
                matches[key] = {
                    'ticker': ticker, 'name': actual.get('name') or report.get('name') or '',
                    'period': period, 'actual_kind': 'quarterly',
                    'announcement_date': day, 'actual_gross_margin': margin,
                    'broker': report.get('broker') or '', 'report_date': report_day,
                    'report_id': rid, 'forecast_gross_margin': estimate,
                    'difference_pp': round(margin - estimate, 2),
                    'source_url': report.get('source_url') or '',
                    'actual_source': source,
                }
    output = {
        'version': 1,
        'metric': 'gross_margin',
        'unit': '%',
        'difference_unit': 'percentage_points',
        'items': sorted(matches.values(), key=lambda x: (
            x['ticker'], x['period'], x['announcement_date'], x['report_date'], x['report_id'])),
    }
    dest = data / 'broker_gross_margin_comparisons.json'
    content = json.dumps(output, ensure_ascii=False, indent=2) + '\n'
    if not dest.exists() or dest.read_text(encoding='utf-8') != content:
        dest.write_text(content, encoding='utf-8')
    print('Gross margin audit:', json.dumps({
        'broker_quarter_forecasts': report_count, 'ambiguous_forecasts': ambiguous,
        'table_forecast_candidates': table_candidates,
        'dated_quarterly_actuals': dated_actuals, 'excluded_late': excluded_late,
        'matches': len(output['items'])}, ensure_ascii=False))
    return output


if __name__ == '__main__':
    compare()
