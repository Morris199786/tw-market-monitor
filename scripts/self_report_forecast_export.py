#!/usr/bin/env python3
"""Export forecast/backtest into the exact static JSON schema consumed by assets/self_report_forecast.js."""
import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--predictions',required=True)
    ap.add_argument('--summary',required=True)
    ap.add_argument('--output',default='data/self_report_forecast.json')
    a=ap.parse_args()
    pred=json.loads(Path(a.predictions).read_text(encoding='utf-8-sig'))
    summary=json.loads(Path(a.summary).read_text(encoding='utf-8-sig'))
    picks=[]
    for p in pred.get('items',[]):
        if p.get('market') not in ('twse','tpex'):
            continue
        picks.append({'ticker':str(p.get('ticker','')),'name':str(p.get('name','')),
                      'market':p['market'],'probability':p.get('probability'),
                      'reasons':p.get('reasons',[])})
    picks=picks[:10]
    def stat(key):
        m=summary.get(key) or {}
        return {k:m.get(k) for k in ('predictions','hits','actual','precision','recall')}
    payload={'updated_at':dt.datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
             'prediction_date':pred.get('prediction_day'),
             'asof':pred.get('asof'),
             'picks':picks,
             'backtest':{'start':summary.get('first_evaluated_date'),
                         'end':summary.get('last_evaluated_date'),
                         'twse':stat('twse'),'tpex':stat('tpex')},
             'source_status':pred.get('source_status',{}),
             'model_version':pred.get('version')}
    # Do not publish stale predictions under a fresh update timestamp.
    if not payload['prediction_date']:
        raise SystemExit('ERROR: prediction_day is empty; refuse to overwrite website forecast')
    if not payload['asof']:
        raise SystemExit('ERROR: asof is empty; refuse to publish')
    dest=Path(a.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Wrote {dest}: {len(picks)} picks, asof {payload["asof"]}, target {payload["prediction_date"]}')

if __name__=='__main__':main()
