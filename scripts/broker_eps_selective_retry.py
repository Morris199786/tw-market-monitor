#!/usr/bin/env python3
"""Select only new, incomplete or unverified PDF reports for parser revision.

Conservative policy: zero rows does not prove no quarterly EPS. Existing
published forecasts are never deleted. Retry at most once per parser revision.
"""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REVISION='2026-10-22-table-v3'
PRIORITY={'1590','3081','3406','6213','3013'}

def read(p,default):
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def select(root=ROOT,force=False):
    data=root/'data'
    reports=read(data/'reports.json',{'items':[]}).get('items',[])
    ledger=read(data/'broker_eps_processed.json',{'reports':{}})
    done=ledger.get('reports',{})
    published=read(data/'broker_eps_forecasts.json',{'items':[]}).get('items',[])
    selected=read(data/'broker_eps_new_reports.json',{'items':[]}).get('items',[])
    seen={str(x.get('id') or x.get('source_file_id')) for x in selected}
    existing={}
    for x in published:
        existing.setdefault(str(x.get('report_id')),set()).add(str(x.get('period')))
    counts={'new':len(selected),'retry':0,'skip_complete':0,'skip_no_forecast':0,'skip_version':0}
    for x in reports:
        rid=str(x.get('id') or x.get('source_file_id') or '')
        if not rid or rid in seen or not str(x.get('source_name','')).lower().endswith('.pdf') or not x.get('broker') or not str(x.get('ticker','')).isdigit():
            continue
        prev=done.get(rid,{})
        if not prev:
            selected.append(x);seen.add(rid);counts['new']+=1;continue
        if prev.get('eps_presence')=='absent_verified':
            counts['skip_no_forecast']+=1;continue
        if prev.get('completeness')=='complete_verified':
            counts['skip_complete']+=1;continue
        if prev.get('parser_revision')==REVISION and not force:
            counts['skip_version']+=1;continue
        # Previously processed does not imply complete. Prioritize known misses,
        # zero-row PDFs and reports without a verified complete-quarter inventory.
        if str(x.get('ticker')) in PRIORITY or not existing.get(rid) or prev.get('completeness')!='complete_verified':
            selected.append(x);seen.add(rid);counts['retry']+=1
    (data/'broker_eps_new_reports.json').write_text(json.dumps({'items':selected},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (data/'broker_eps_new_count.txt').write_text(str(len(selected))+'\n',encoding='utf-8')
    print('EPS selective retry:',counts,'total selected:',len(selected))
    return selected

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--force',action='store_true');args=a.parse_args()
    select(force=args.force)
