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
        if not r['metric'] or not r['unit']:continue
        # Current chart consumer accepts only annual/quarterly company forecasts.
        from shared_financial_catalog import PERIOD
        if not PERIOD.fullmatch(r['period']):continue
        if r['metric'] in ('gross_margin','operating_margin') and r['unit'] not in ('%','百分比','percent','pct'):continue
        key=(r['report_id'],r['ticker'],r['period'],r['metric'])
        groups.setdefault(key,[]).append(r)
    safe=[]
    for key,rows in groups.items():
        # Different units or values require review; no guessed conversion.
        if len({(r['value'],r['unit'],r['report_date']) for r in rows})!=1:
            from decimal import Decimal, ROUND_HALF_UP
            tables=[r for r in rows if r['origin']=='saved_margin_fallback' and r['evidence'].startswith('table:')]
            texts=[r for r in rows if r['origin']=='structured']
            if not (key[-1] in ('gross_margin','operating_margin') and len(tables)==1 and len(texts)==len(rows)-1 and texts and len({r['report_date'] for r in rows})==1 and all(r['unit']=='%' for r in rows) and all(Decimal(str(tables[0]['value'])).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)==Decimal(str(r['value'])) for r in texts)):continue
            rows=tables
        r=rows[0]
        safe.append({k:r[k] for k in ('report_id','ticker','report_date','period','metric','value','unit','type','source','scope','evidence','needs_review','origin')})
    # Include the historical EPS forecasts actually used by comparison, with explicit
    # legacy status and provenance, never present them as newly source-verified.
    by_key={(r['report_id'],r['ticker'],r['period'],r['metric']):r for r in safe}
    raw={}
    for r in catalog['items']:
        if r['comparison_candidate'] and not r['needs_review']:
            raw.setdefault((r['report_id'],r['ticker'],r['period'],r['metric'],r['value']),[]).append(r)
    for metric,result in results.items():
        for row in result['items']:
            k=(row['report_id'],row['ticker'],row['period'],metric)
            value=row['forecast_'+metric]
            if k in by_key:
                if by_key[k]['value']!=value:raise ValueError('Forecast consumer mismatch: '+str(k))
                continue
            candidates=raw.get((*k,value),[])
            if not candidates:raise ValueError('Comparison missing source fact: '+str(k))
            r=next((x for x in candidates if x['origin']!='legacy_eps' and x['evidence']),candidates[0])
            fact={k:r[k] for k in ('report_id','ticker','report_date','period','metric','value','unit','type','source','scope','evidence','needs_review','origin')}
            fact['source_url']=r['source_url']
            fact['trust']='legacy_baseline' if r['origin']=='legacy_eps' else 'comparison_candidate'
            if fact['trust']=='legacy_baseline' and not fact['source_url']:raise ValueError('Legacy forecast without source')
            safe.append(fact)
            by_key[k]=fact
    for r in safe:
        r.setdefault('trust','verified_report')
    safe.sort(key=lambda r:(r['report_id'],r['period'],r['metric']))
    # Only reconciled comparisons are published; unresolved records stay quarantined.
    return {'schema':1,'mode':'verified_additive','comparison_mode':'production','items':safe,'comparisons':{m:results[m]['items'] for m in results}}, {'catalog':audit,'comparison':{k:v for k,v in check.items() if k not in ('quarantined','actual_conflicts','resolved_actual_records','unresolved_actual_records')},'published_facts':len(safe),'archive_facts':len(catalog['items']),'raw_ai_records':len(catalog['raw_records'])}, {'schema':1,'mode':'complete_archive','items':catalog['items'],'raw_records':catalog['raw_records']}
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data',type=Path,default=ROOT/'data')
    a=p.parse_args()
    out,audit,archive=payload(a.data)
    a.output.mkdir(parents=True,exist_ok=True)
    for name,obj in [('shared_financial_v1.json',out),('shared_financial_status.json',audit),('shared_financial_archive.json',archive)]:
        path=a.output/name
        temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
        os.replace(temp,path)
    print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
