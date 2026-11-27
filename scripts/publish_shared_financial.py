#!/usr/bin/env python3
"""Publish versioned additive catalog only. Never replace historical comparisons."""
import argparse
import json
import os
from pathlib import Path
from shared_financial_catalog import build
from shared_financial_shadow_compare import reconcile
ROOT=Path(__file__).resolve().parents[1]
def payload(data):
    catalog,audit=build(data)
    results,check=reconcile(catalog,data)
    # Preserve original consumer payloads. Only publish exact-report verified facts.
    groups={}
    for r in catalog['items']:
        if not r['verified_report'] or r['needs_review'] or r['type']!='forecast' or r['source']!='broker' or r['scope']!='company':continue
        if r['origin'] not in ('structured','saved_margin_fallback'):continue
        if not r['ticker'] or not r['report_date'] or not r['evidence']:continue
        if r['metric'] not in ('gross_margin','operating_margin','eps','revenue','net_income','operating_profit'):continue
        if r['metric'] in ('gross_margin','operating_margin') and r['unit'] not in ('%','百分比','percent','pct'):continue
        key=(r['report_id'],r['ticker'],r['period'],r['metric'])
        groups.setdefault(key,[]).append(r)
    safe=[]
    for key,rows in groups.items():
        # Different units or values require review; no guessed conversion.
        if len({(r['value'],r['unit'],r['report_date']) for r in rows})!=1:continue
        r=rows[0]
        safe.append({k:r[k] for k in ('report_id','ticker','report_date','period','metric','value','unit','type','source','scope','evidence','needs_review','origin')})
    safe.sort(key=lambda r:(r['report_id'],r['period'],r['metric']))
    # Comparisons remain a shadow audit until official actual conflicts are resolved.
    return {'schema':1,'mode':'verified_additive','items':safe,'comparisons':{m:results[m]['items'] for m in results}}, {'catalog':audit,'comparison':{k:v for k,v in check.items() if k not in ('quarantined','actual_conflicts','resolved_actual_records','unresolved_actual_records')},'published_facts':len(safe)}
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data',type=Path,default=ROOT/'data')
    a=p.parse_args()
    out,audit=payload(a.data)
    a.output.mkdir(parents=True,exist_ok=True)
    for name,obj in [('shared_financial_v1.json',out),('shared_financial_status.json',audit)]:
        path=a.output/name
        temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
        os.replace(temp,path)
    print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
