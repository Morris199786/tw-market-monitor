#!/usr/bin/env python3
"""No-paid-call EPS publication from already saved AI report output.
Historical reports are sealed before deployment; never parse historical PDFs.
"""
import json, re, math
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PERIOD = re.compile(r'^20\d\d-Q[1-4]$')

def read(path, default):
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else default

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf8')

def normalize(rows):
    result = {}
    for row in rows if isinstance(rows,list) else []:
        if not isinstance(row,dict): continue
        period=str(row.get('period') or '').strip().upper().replace(' ','')
        try: value=float(row.get('eps'))
        except (ValueError,TypeError):continue
        if not PERIOD.fullmatch(period) or not -100<=value<=100:continue
        if row.get('type') in ('actual','consensus') or row.get('source') in ('consensus','actual'):continue
        if period in result and result[period]!=value:
            result[period]=None
        elif period not in result:result[period]=value
    return [{'period':k,'eps':v} for k,v in result.items() if v is not None]

def seal_historical(root=ROOT):
    data=root/'data'; ledger=read(data/'broker_eps_processed.json',{'version':1,'reports':{}})
    records=ledger.setdefault('reports',{})
    reports=read(data/'reports.json',{'items':[]})['items']
    added=0
    for r in reports:
        rid=str(r.get('source_file_id') or r.get('id') or '')
        if not rid or rid in records:continue
        records[rid]={'status':'historical_sealed','ticker':str(r.get('ticker') or ''),'broker':r.get('broker') or '',
                      'source_name':r.get('source_name') or '', 'accepted_forecasts':0}
        added+=1
    ledger['updated_at']=datetime.now(timezone.utc).isoformat()
    write(data/'broker_eps_processed.json',ledger)
    write(data/'broker_eps_baseline_sealed.json', {'sealed':True, 'baseline_report_count':len(reports)})
    print('Historical reports sealed:',added,'total:',len(records))

def ai_eps_rows(report):
    """Read ONLY previously persisted first-pass AI fields; no PDF text parsing.

    quarterly_eps is authoritative for quarterly EPS. financial_forecasts
    fills missing periods only when explicitly broker forecast, company scope.
    """
    primary = normalize(report.get('quarterly_eps'))
    indexed = {x['period']: x['eps'] for x in primary}
    disagreements = []
    for row in report.get('financial_forecasts') or []:
        if not isinstance(row, dict):
            continue
        if str(row.get('metric') or '').lower() != 'eps':
            continue
        if str(row.get('type') or 'forecast').lower() != 'forecast':
            continue
        if str(row.get('source') or 'broker').lower() != 'broker':
            continue
        if str(row.get('scope') or 'company').lower() != 'company':
            continue
        period = str(row.get('period') or '').strip().upper()
        if not PERIOD.fullmatch(period):
            continue
        value = row.get('value')
        if isinstance(value, bool):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or not -100 <= value <= 100:
            continue
        if period in indexed:
            if not math.isclose(indexed[period], value, abs_tol=0.011):
                disagreements.append({'period': period, 'quarterly_eps': indexed[period], 'financial_forecasts': value})
            continue
        indexed[period] = value
    return [{'period': k, 'eps': v} for k, v in sorted(indexed.items())], disagreements


def publish_new(root=ROOT):
    """Idempotently publish saved AI data, INCLUDING already-processed reports.

    Never call OpenAI, re-read PDF, or run the legacy text fallback. Preserve
    existing rows and historic sealed ledgers. Do not rewrite unchanged files.
    """
    data = root / 'data'
    ledger = read(data/'broker_eps_processed.json', {'version':1, 'reports':{}})
    records = ledger.setdefault('reports', {})
    forecasts = read(data/'broker_eps_forecasts.json', {'version':1, 'items':[]})
    items = forecasts.setdefault('items', [])
    review = read(data/'broker_eps_review_queue.json', {'items':[]})
    queue = review.setdefault('items', [])
    existing = {(str(x.get('report_id')), str(x.get('period'))): x for x in items}
    reviewed = {str(x.get('report_id')) for x in queue}
    added = 0
    new_ledger = 0
    added_review = 0
    for r in read(data/'reports.json', {'items':[]}).get('items', []):
        if not isinstance(r, dict):
            continue
        rid = str(r.get('source_file_id') or r.get('id') or '')
        if not rid:
            continue
        # A one-time sealed historical report stays sealed. Its saved output
        # is never reinterpreted or submitted to AI.
        previous = records.get(rid)
        if previous and previous.get('status') == 'historical_sealed':
            continue
        ticker = str(r.get('ticker') or '')
        broker = str(r.get('broker') or '')
        day = str(r.get('date') or '')[:10]
        valid_identity = bool(re.fullmatch(r'\d{4}', ticker) and broker and re.fullmatch(r'20\d\d-\d\d-\d\d', day))
        rows, disagreements = ai_eps_rows(r)
        if not valid_identity:
            rows = []
        for row in rows:
            key = (rid, row['period'])
            prior = existing.get(key)
            if prior:
                # Never rewrite previously-published data automatically.
                if (not math.isclose(float(prior['eps']), float(row['eps']), abs_tol=0.011)
                        and rid not in reviewed):
                    queue.append({'report_id':rid, 'ticker':ticker, 'broker':broker, 'report_date':day,
                                  'source_name':r.get('source_name') or '', 'status':'needs_manual_review',
                                  'reason':'AI EPS conflicts with previously published EPS; old value preserved',
                                  'evidence':[{'period':row['period'], 'published':prior['eps'], 'ai':row['eps']}]})
                    reviewed.add(rid); added_review += 1
                continue
            entry = {'report_id':rid, 'ticker':ticker, 'broker':broker, 'report_date':day,
                     'source_url':r.get('source_url') or '', **row}
            items.append(entry)
            existing[key] = entry
            added += 1
        if not previous:
            # Preserve the original ledger's no-retry semantics for AI;
            # only this offline publisher can revisit its saved output.
            records[rid] = {'status':'processed', 'accepted_forecasts':len(rows), 'ticker':ticker,
                            'broker':broker, 'source_name':r.get('source_name') or '',
                            'eps_source':'openai' if rows else 'unresolved'}
            new_ledger += 1
        if (not rows or disagreements or not valid_identity) and rid not in reviewed and not previous:
            queue.append({'report_id':rid, 'ticker':ticker, 'broker':broker, 'report_date':day,
                          'source_name':r.get('source_name') or '', 'status':'needs_manual_review',
                          'reason':'AI quarterly EPS absent, conflicting, or identity invalid; no automatic AI retry',
                          'evidence':disagreements[:12]})
            reviewed.add(rid)
            added_review += 1
    if added:
        forecasts['generated_at'] = datetime.now(timezone.utc).isoformat()
        write(data/'broker_eps_forecasts.json', forecasts)
    if new_ledger:
        ledger['updated_at'] = datetime.now(timezone.utc).isoformat()
        write(data/'broker_eps_processed.json', ledger)
    if added_review:
        write(data/'broker_eps_review_queue.json', review)
    print('New EPS rows:', added, 'new ledger reports:', new_ledger,
          'new review items:', added_review, 'review queue:', len(queue))


if __name__=='__main__':
    import sys
    if len(sys.argv)!=2 or sys.argv[1] not in ('seal','publish'):raise SystemExit('usage: broker_eps_pipeline.py seal|publish')
    (seal_historical if sys.argv[1]=='seal' else publish_new)()
