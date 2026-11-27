"""Read-only candidate reconciliation. No production publication."""
import argparse
import collections
import json
from pathlib import Path
from shared_financial_catalog import build
from broker_eps_compare import actuals, valid_date, number, QUARTER, TICKER, load

METRICS=('eps','gross_margin','operating_margin')
def identity(x,metric):
    return (str(x['ticker']),x['period'],x.get('actual_kind','quarterly'),x.get('actual_period',x['period']),x['announcement_date'],str(x['report_id']),round(float(x['actual_'+metric]),6),round(float(x['forecast_'+metric]),6))

def reconcile(catalog,data):
    # Normalize only known equivalent units for identity; never convert currency.
    groups=collections.defaultdict(list)
    for r in catalog['items']:
        if r['comparison_candidate'] or (r['needs_review'] and r['type']=='forecast' and r['source']=='broker' and r['scope'] in ('company','consolidated') and r['metric'] in METRICS and QUARTER.fullmatch(r['period'])):
            groups[(r['ticker'],r['period'],r['metric'],r['report_id'])].append(r)
    forecasts=collections.defaultdict(list)
    quarantined=[]
    for key,rows in groups.items():
        ticker,period,metric,rid=key
        vals={r['value'] for r in rows}
        dates={r['report_date'] for r in rows}
        if len(vals)!=1 or len(dates)!=1 or any(r['needs_review'] for r in rows):
            quarantined.append({'key':key,'rows':rows,'reason':'conflicting_value_or_date'})
            continue
        r=next((r for r in rows if r['comparison_candidate']),None)
        if not r or not TICKER.fullmatch(ticker) or not valid_date(r['report_date']):continue
        if metric=='eps' and not any(x['unit'] in ('元/股','元／股','元','NT$','TWD','新台幣元','新台幣元/股') for x in rows):
            quarantined.append({'key':key,'rows':rows,'reason':'unverified_eps_unit'})
            continue
        forecasts[(ticker,period,metric)].append(r)
    actual_rows={'eps':list(actuals(data)),'gross_margin':[],'operating_margin':[]}
    merged={}
    for filename in ('quarterly_earnings_recovered.json','quarterly_earnings.json'):
        for row in load(data/filename,{}).get('reports',[]):
            k=(str(row.get('ticker') or ''),str(row.get('period') or ''))
            old=merged.get(k,{})
            merged[k]={**old,**{k:v for k,v in row.items() if v is not None},'_source':filename}
    opm=load(data/'quarterly_opm.json',{})
    if opm.get('schema')!=1 or not isinstance(opm.get('metrics'),dict):
        raise ValueError('OPM source unavailable: refuse incomplete audit')
    for (ticker,period),r in merged.items():
        day=valid_date(r.get('publish_date'))
        if not day or not QUARTER.fullmatch(period) or not TICKER.fullmatch(ticker):continue
        for metric in METRICS[1:]:
            side=opm['metrics'].get(ticker+'|'+period,{}) if metric=='operating_margin' else {}
            val=number(side.get('value'))
            source='quarterly_opm.json' if val is not None else r['_source']
            if val is None:val=number(r.get(metric))
            if val is not None:
                actual_rows[metric].append(dict(ticker=ticker,period=period,actual_period=period,kind='quarterly',announcement_date=day,actual_source=source,**{'actual_'+metric:val}))
    # Do not choose among conflicting disclosed EPS values automatically.
    # Retain all source records in the audit, suppress ambiguous comparisons.
    actual_conflicts=[]
    for metric in METRICS:
        by_period=collections.defaultdict(list)
        for row in actual_rows[metric]:
            by_period[(row['ticker'],row['kind'],row['actual_period'])].append(row)
        clean=[]
        for key,records in by_period.items():
            vals={round(r['actual_'+metric],6) for r in records}
            if len(vals)>1:
                actual_conflicts.append({'metric':metric,'key':key,'records':records})
                continue
            # Earliest verified disclosure prevents look-ahead and duplicate events.
            clean.append(min(records,key=lambda r:r['announcement_date']))
        actual_rows[metric]=clean
    results={}
    stats={}
    for metric in METRICS:
        matches={}
        late=same=0
        for a in actual_rows[metric]:
            for f in forecasts.get((a['ticker'],a['period'],metric),[]):
                if f['report_date']>=a['announcement_date']:
                    same+=int(f['report_date']==a['announcement_date'])
                    late+=int(f['report_date']>a['announcement_date'])
                    continue
                v=a['actual_'+metric]; est=f['value']
                row=dict(ticker=a['ticker'],period=a['period'],actual_kind=a['kind'],actual_period=a['actual_period'],announcement_date=a['announcement_date'],report_id=f['report_id'],broker=f['broker'],report_date=f['report_date'],source_url=f['source_url'],actual_source=a['actual_source'],provenance=f['provenance'],ratio_pct=round(v/est*100,1) if est>0 else None,difference=round(v-est,6),**{'actual_'+metric:v,'forecast_'+metric:est})
                matches[identity(row,metric)]=row
        previous=load(data/('broker_'+metric+'_comparisons.json'),{'items':[]})['items']
        old={identity(r,metric):r for r in previous}
        added=[matches[k] for k in sorted(matches.keys()-old.keys())]
        removed=[old[k] for k in sorted(old.keys()-matches.keys())]
        # Old EPS stays separately available; differences are not permission to delete.
        results[metric]={'items':list(matches.values()),'added':added,'removed_or_changed':removed}
        stats[metric]={'actual_rows':len(actual_rows[metric]),'previous':len(old),'shadow':len(matches),'unchanged':len(matches.keys()&old.keys()),'added':len(added),'removed_or_changed':len(removed),'excluded_same_day':same,'excluded_late':late}
    return results,{'metrics':stats,'quarantined_count':len(quarantined),'quarantined':quarantined,'actual_conflict_count':len(actual_conflicts),'actual_conflicts':actual_conflicts}
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path(__file__).resolve().parents[1]/'data')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.resolve()==a.data.resolve() or a.data.resolve() in a.output.resolve().parents:raise SystemExit('Refuse production output')
    catalog,_=build(a.data)
    results,audit=reconcile(catalog,a.data)
    a.output.mkdir(parents=True,exist_ok=True)
    for name,obj in [('comparison-shadow.json',results),('comparison-audit.json',audit)]:
        (a.output/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k not in ('quarantined','actual_conflicts')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
