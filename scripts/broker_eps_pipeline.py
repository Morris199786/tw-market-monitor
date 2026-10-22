#!/usr/bin/env python3
"""No-paid-call EPS publication from already saved AI report output.
Historical reports are sealed before deployment; never parse historical PDFs.
"""
import json, re
from broker_eps_fallback import extract as fallback_extract
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

def publish_new(root=ROOT):
    data=root/'data'
    ledger=read(data/'broker_eps_processed.json',{'version':1,'reports':{}})
    records=ledger.setdefault('reports',{})
    forecasts=read(data/'broker_eps_forecasts.json',{'version':1,'items':[]})
    items=forecasts.setdefault('items',[])
    review=read(data/'broker_eps_review_queue.json',{'items':[]})
    queue=review.setdefault('items',[])
    existing={(str(x.get('report_id')),str(x.get('period'))) for x in items}
    reviewed={str(x.get('report_id')) for x in queue}
    inbox={str(x.get('drive_file_id')):x for x in read(data/'report_inbox.json',{'items':[]}).get('items',[]) if x.get('drive_file_id')}
    new_count=0
    for r in read(data/'reports.json',{'items':[]}).get('items',[]):
        rid=str(r.get('source_file_id') or r.get('id') or '')
        if not rid or rid in records:continue
        ticker=str(r.get('ticker') or '')
        broker=str(r.get('broker') or '')
        rows=normalize(r.get('quarterly_eps'))
        fallback_review=[]
        eps_source='openai' if rows else 'unresolved'
        if not rows:
            src=inbox.get(rid,{})
            rows, fallback_review=fallback_extract(str(src.get('text') or ''))
            eps_source='python_fallback' if rows else 'unresolved'
        date=str(r.get('date') or '')[:10]
        if not re.fullmatch(r'\d{4}',ticker) or not broker or not re.fullmatch(r'20\d\d-\d\d-\d\d',date):
            rows=[]
        for row in rows:
            key=(rid,row['period'])
            if key in existing:continue
            items.append({'report_id':rid,'ticker':ticker,'broker':broker,'report_date':date,
                          'source_url':r.get('source_url') or '',**row})
            existing.add(key);new_count+=1
        if (not rows or fallback_review) and rid not in reviewed:
            queue.append({'report_id':rid,'ticker':ticker,'broker':broker,'report_date':date,
                          'source_name':r.get('source_name') or '',
                          'status':'needs_manual_review','reason':'No verified EPS or ambiguous Python evidence; no automatic retry',
                          'evidence':fallback_review[:12]})
            reviewed.add(rid)
        records[rid]={'status':'processed','accepted_forecasts':len(rows),'ticker':ticker,'broker':broker,
                      'source_name':r.get('source_name') or '', 'eps_source':eps_source}
    write(data/'broker_eps_forecasts.json',forecasts)
    write(data/'broker_eps_processed.json',ledger)
    write(data/'broker_eps_review_queue.json',review)
    print('New EPS rows:',new_count,'review queue:',len(queue))

if __name__=='__main__':
    import sys
    if len(sys.argv)!=2 or sys.argv[1] not in ('seal','publish'):raise SystemExit('usage: broker_eps_pipeline.py seal|publish')
    (seal_historical if sys.argv[1]=='seal' else publish_new)()
