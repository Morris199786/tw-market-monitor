#!/usr/bin/env python3
"""Add previously zero-EPS PDF reports to this run's selected list, once on demand."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'data'
def load(name):return json.loads((root/name).read_text(encoding='utf-8'))
reports=load('reports.json').get('items',[])
ledger=load('broker_eps_processed.json').get('reports',{})
selected=load('broker_eps_new_reports.json').get('items',[])
seen={str(x.get('id') or x.get('source_file_id')) for x in selected}
added=0
for x in reports:
    rid=str(x.get('id') or x.get('source_file_id') or '')
    old=ledger.get(rid,{})
    if not rid or rid in seen or old.get('status')!='processed' or old.get('accepted_forecasts')!=0:continue
    if not str(x.get('source_name','')).lower().endswith('.pdf'):continue
    selected.append(x);seen.add(rid);added+=1
(root/'broker_eps_new_reports.json').write_text(json.dumps({'items':selected},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(root/'broker_eps_new_count.txt').write_text(str(len(selected))+'\n',encoding='utf-8')
print(f'One-time zero EPS backfill: {added} old reports, {len(selected)} total')
