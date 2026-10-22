#!/usr/bin/env python3
"""Show real matchable comparisons; does not modify EPS source data."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):return json.loads((ROOT/'data'/name).read_text(encoding='utf-8'))
def main():
    forecasts=load('broker_eps_forecasts.json').get('items',[])
    self_reports=load('self_reports.json').get('items',[])
    earnings=load('quarterly_earnings.json').get('reports',[])
    by_key={}
    for r in forecasts:by_key.setdefault((str(r.get('ticker')),r.get('period')),[]).append(r)
    matches=[]
    def add(x,period,kind,eps):
        if not period or eps is None:return
        for r in by_key.get((str(x.get('ticker')),period),[]):
            if str(r.get('report_date') or '') > str(x.get('publish_date') or ''):continue
            try:ratio=float(eps)/float(r['eps'])*100
            except (ValueError,TypeError,ZeroDivisionError):continue
            matches.append({'ticker':x['ticker'],'name':x.get('name'),'announcement_date':x.get('publish_date'),
                'period':period,'kind':kind,'actual_eps':eps,'broker':r['broker'],
                'report_date':r['report_date'],'forecast_eps':r['eps'],'achievement_pct':round(ratio,1),
                'same_day':r['report_date']==x.get('publish_date')})
    for x in self_reports:
        month=x.get('monthly_period','')
        if len(month)==7 and month[5:].isdigit():add(x,month[:4]+'-Q'+str((int(month[5:])-1)//3+1),'monthly',x.get('monthly_eps'))
    for x in earnings:add(x,x.get('period'),'quarter',x.get('eps'))
    out={'matches':matches,'match_count':len(matches),'matched_companies':len({x['ticker'] for x in matches})}
    dest=ROOT/'data/broker_eps_compare_audit.json';dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Compare matches:',len(matches),'companies:',out['matched_companies'])
    for x in matches:print(x['announcement_date'],x['ticker'],x['name'],x['broker'],x['period'],x['achievement_pct'])
if __name__=='__main__':main()
