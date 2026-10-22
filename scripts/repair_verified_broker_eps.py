#!/usr/bin/env python3
"""One-time evidence-backed EPS corrections from four user-supplied report screenshots.
No API, PDF downloads, or old-report reparsing. Idempotent and scoped by Drive ID.
"""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
# All numbers visually verified against original report table screenshots.
CASES={
 '1uvr52w061JuH1R5V-NtBTImxskpwanKw':('6213','Daiwa','2026-10-14',{'2026-Q3':7.28,'2026-Q4':10.15,'2027-Q1':10.64,'2027-Q2':11.86,'2027-Q3':13.43,'2027-Q4':13.62}),
 '1zbkcfI3H2TkGTLm25IrcHQgflWOI-1xH':('3406','UBS','2026-10-15',{'2026-Q3':11.86,'2026-Q4':10.86}),
 '1IBWl2-ij9kFK1Esr1xqwaeAZkPaMu8MI':('1590','Goldman Sachs','2026-10-12',{'2026-Q3':16.04,'2026-Q4':15.17,'2027-Q1':15.84,'2027-Q2':20.36,'2027-Q3':19.45}),
 '14yrXoA7OJ6bncswNlVccY61s33x_yZ0u':('3081','Goldman Sachs','2026-10-05',{'2026-Q3':4.96,'2026-Q4':5.90}),
}

def repair(root=ROOT):
    path=root/'data/broker_eps_forecasts.json'
    raw=json.loads(path.read_text(encoding='utf-8'))
    items=raw['items']
    # Never affect unrelated report IDs. Replace only matching report+quarter;
    # preserve historical reports and all other broker forecasts.
    report_index=json.loads((root/'data/reports.json').read_text(encoding='utf-8'))['items']
    ids={str(r.get('id') or r.get('source_file_id')):r for r in report_index}
    for rid,(ticker,broker,report_date,quarters) in CASES.items():
        r=ids.get(rid)
        if not r or str(r.get('ticker'))!=ticker or str(r.get('broker'))!=broker or str(r.get('date'))[:10]!=report_date:
            raise ValueError(f'Report identity mismatch: {rid}; refusing write')
        # Replace all forecast periods for this report, so stale/incorrect
        # consensus values cannot survive. These screenshots contain all E quarters.
        items[:]=[x for x in items if str(x.get('report_id'))!=rid]
        for period,eps in quarters.items():
            items.append({'ticker':ticker,'period':period,'eps':eps,'broker':broker,
                          'report_date':report_date,'report_id':rid,
                          'source_url':r.get('source_url') or f'https://drive.google.com/file/d/{rid}/view?usp=drivesdk'})
    items.sort(key=lambda x:(str(x.get('ticker')),str(x.get('period')),str(x.get('report_date')),str(x.get('broker'))),reverse=True)
    if len({(x.get('report_id'),x.get('period')) for x in items})!=len(items):
        raise ValueError('Duplicate report/period detected; refusing write')
    path.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Verified report corrections applied: 4 reports / 15 forecast quarters; no API/PDF reparse')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    repair(parser.parse_args().root)
