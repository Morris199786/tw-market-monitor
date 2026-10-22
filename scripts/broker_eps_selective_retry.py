#!/usr/bin/env python3
"""No automatic retry of completed PDFs. New PDFs are selected by incremental_broker_eps.py.
Failed PDFs remain eligible only when not in processed ledger. Explicit repair is
performed separately and never triggers PDF extraction.
"""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def select(root=ROOT, force=False):
    data=root/'data'
    path=data/'broker_eps_new_reports.json'
    selected=json.loads(path.read_text(encoding='utf-8')).get('items',[]) if path.exists() else []
    ledger_path=data/'broker_eps_processed.json'
    ledger=json.loads(ledger_path.read_text(encoding='utf-8')).get('reports',{}) if ledger_path.exists() else {}
    published_path=data/'broker_eps_forecasts.json'
    published=json.loads(published_path.read_text(encoding='utf-8')).get('items',[]) if published_path.exists() else []
    done=set(ledger)|{str(x.get('report_id')) for x in published if x.get('report_id')}
    unique={}
    for r in selected:
        rid=str(r.get('id') or r.get('source_file_id') or '')
        if rid and rid not in done:
            unique.setdefault(rid,r)
    output=list(unique.values())
    path.write_text(json.dumps({'items':output},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (data/'broker_eps_new_count.txt').write_text(str(len(output))+'\n',encoding='utf-8')
    print(f'EPS selection: {len(output)} truly new reports; {len(selected)-len(output)} previously processed skipped. No automatic historical retry.')
    return output

if __name__=='__main__':
    select()
