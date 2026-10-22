#!/usr/bin/env python3
"""Persist retry version and conservative completeness status after extraction."""
import json
from pathlib import Path
from datetime import datetime,timezone
from broker_eps_selective_retry import REVISION
root=Path(__file__).resolve().parents[1]/'data'
def read(n,d):
 p=root/n;return json.loads(p.read_text(encoding='utf-8')) if p.exists() else d
ledger=read('broker_eps_processed.json',{'version':1,'reports':{}})
audit=read('broker_eps_audit_new.json',{'reports':[]})
records=ledger.setdefault('reports',{})
for row in audit.get('reports',[]):
 rid=str(row.get('report_id') or '')
 if not rid:continue
 rec=records.setdefault(rid,{})
 if row.get('status')=='error':
  rec['completeness']='retry_error';continue
 rec['parser_revision']=REVISION
 rec['last_eps_retry_at']=datetime.now(timezone.utc).isoformat()
 rec['accepted_forecasts']=max(int(rec.get('accepted_forecasts') or 0),int(row.get('accepted_forecasts') or 0))
 diag=row.get('diagnostic_status','')
 # Do not declare complete or no EPS from heuristics alone.
 rec['completeness']='unverified' if diag else 'unknown'
 rec['diagnostic_status']=diag
ledger['updated_at']=datetime.now(timezone.utc).isoformat()
(root/'broker_eps_processed.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Retry audit persisted:',len(audit.get('reports',[])))
