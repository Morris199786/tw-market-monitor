#!/usr/bin/env python3
"""Shadow catalog only. No network, AI, PDF parsing or production data writes."""
import argparse
import collections
import json
import math
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PERIOD=re.compile(r'^20\d{2}(?:-Q[1-4])?$')
ALIASES={'gm':'gross_margin','gpm':'gross_margin','毛利率':'gross_margin','opm':'operating_margin','營益率':'operating_margin','營業利益率':'operating_margin'}
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))
def build(data):
    rows=[]
    rejected=collections.Counter()
    coverage=collections.Counter()
    def add(rid,report,row,origin,kind):
        if not isinstance(row,dict):
            rejected['invalid_row']+=1;return
        period=str(row.get('period') or '').strip().upper()
        raw_metric=str(row.get('metric') or '').strip().lower()
        metric=ALIASES.get(raw_metric,raw_metric)
        try:
            value=float(row.get('value'))
            if isinstance(row.get('value'),bool) or not math.isfinite(value): raise ValueError()
        except (ValueError,TypeError):
            rejected['invalid_number']+=1;return
        if not PERIOD.fullmatch(period) or not metric:
            rejected['missing_period_or_metric']+=1;return
        typ=str(row.get('type') or '').lower()
        source=str(row.get('source') or '').lower()
        scope=str(row.get('scope') or row.get('segment') or '').strip()
        unit=str(row.get('unit') or '').strip()
        evidence=str(row.get('evidence') or '').strip()
        ticker=str(report.get('ticker') or '').strip()
        day=str(report.get('date') or report.get('report_date') or '')[:10].replace('/','-')
        broker=str(report.get('broker') or '')
        # No default promotion of unknown nature/source into broker forecast.
        if origin=='legacy_eps':
            typ,source,scope,unit='forecast','broker','company','元/股'
        if origin=='meeting_saved':
            typ={'A':'actual','E':'forecast','F':'forecast'}.get(str(row.get('status') or '').upper(),'unknown')
            source='unknown' # meeting/Excel status alone does not establish author
        eligible=(kind in ('broker','business','legacy_eps') and bool(re.fullmatch(r'\d{4}',ticker)) and bool(re.fullmatch(r'20\d{2}-\d{2}-\d{2}',day)) and bool(broker) and typ=='forecast' and source=='broker' and scope in ('company','consolidated') and '-Q' in period and metric in ('eps','gross_margin','operating_margin') and (bool(evidence) or origin=='legacy_eps') and (metric=='eps' or unit in ('%','百分比','percent','pct')))
        rows.append(dict(report_id=rid,report_kind=kind,origin=origin,ticker=ticker,company=report.get('name') or report.get('company') or '',report_date=day,broker=broker,source_url=report.get('source_url') or report.get('url') or '',period=period,metric=metric,metric_name=str(row.get('metric_name') or ''),value=value,unit=unit,type=typ or 'unknown',source=source or 'unknown',scope=scope or 'unknown',evidence=evidence,comparison_candidate=eligible))
    for filename,kind in [('reports.json','broker'),('business_reports_ai.json','business')]:
        for report in read(data/filename).get('items',[]):
            if not isinstance(report,dict):continue
            if kind=='business' and report.get('status')!='ready':continue
            rid=str(report.get('source_file_id') or report.get('id') or '')
            if not rid: rejected['missing_report_id']+=1;continue
            coverage[kind]+=1
            for row in report.get('financial_forecasts') or []:add(rid,report,row,'structured',kind)
            # Add saved table/text evidence; never reparse PDF or call AI.
            from shared_margin_extract import saved_metric_rows
            for metric in ('gross_margin','operating_margin'):
                for period,value,evidence in saved_metric_rows(report,metric):
                    if evidence=='structured':continue
                    add(rid,report,dict(period=period,metric=metric,value=value,unit='%',type='forecast',source='broker',scope='company',evidence=evidence),'saved_margin_fallback',kind)
            for row in report.get('quarterly_eps') or []:
                if isinstance(row,dict):add(rid,report,{**row,'metric':'eps','value':row.get('eps'),'unit':'元/股','scope':row.get('scope') or 'company'},'saved_quarterly_eps',kind)
    for rid,report in read(data/'research_financial_forecasts.json').get('reports',{}).items():
        coverage['meeting_saved']+=1
        for row in report.get('forecasts') or []:add(rid,report,row,'meeting_saved','meeting')
    for row in read(data/'broker_eps_forecasts.json').get('items',[]):
        rid=str(row.get('report_id') or '')
        if rid:add(rid,row,{**row,'metric':'eps','value':row.get('eps')},'legacy_eps','legacy_eps')
    groups=collections.defaultdict(list)
    for row in rows:
        key=tuple(row[k] for k in ('report_id','ticker','period','metric','metric_name','type','source','scope','unit'))
        groups[key].append(row)
    output=[]
    conflicts=0
    for group in groups.values():
        values={r['value'] for r in group}
        conflict=len(values)>1
        conflicts+=int(conflict)
        for value in sorted(values):
            same=[r for r in group if r['value']==value]
            item=dict(same[0])
            item['provenance']=[{k:r[k] for k in ('origin','report_kind','evidence','source_url')} for r in same]
            item['needs_review']=conflict
            item['comparison_candidate']=not conflict and any(r['comparison_candidate'] for r in same)
            output.append(item)
    output.sort(key=lambda r:(r['report_id'],r['period'],r['metric'],r['type'],r['value']))
    audit=dict(input_reports=dict(coverage),raw_rows=len(rows),catalog_rows=len(output),conflict_groups=conflicts,rejected=dict(rejected),metrics=dict(collections.Counter(r['metric'] for r in output)),comparison_candidates=dict(collections.Counter(r['metric'] for r in output if r['comparison_candidate'])),origins=dict(collections.Counter(r['origin'] for r in output)))
    return {'schema':1,'mode':'shadow','items':output},audit
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.resolve()==args.data.resolve() or args.data.resolve() in args.output.resolve().parents:
        raise SystemExit('Shadow output must be outside production data directory')
    catalog,audit=build(args.data)
    args.output.mkdir(parents=True,exist_ok=True)
    for name,obj in [('catalog.json',catalog),('audit.json',audit)]:
        (args.output/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
