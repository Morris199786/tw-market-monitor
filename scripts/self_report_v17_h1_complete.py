#!/usr/bin/env python3
"""Private historical MOPS reconciliation -> V17 event CSV. No production writes."""
import argparse,csv,json,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import self_report_predict as model

def main():
 p=argparse.ArgumentParser();p.add_argument('--historical',default='private_h1_mops');p.add_argument('--out',default='private_h1_verified');args=p.parse_args()
 base=Path(args.historical);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
 chunks=[base/'jan_apr',base/'may_jun']
 errors=[]; all_items=[]; audits={}
 for folder in chunks:
  if not (folder/'coverage_warnings.json').is_file() or not (folder/'self_reports_history.json').is_file():
   errors.append(f'Missing MOPS output: {folder}');continue
  w=json.loads((folder/'coverage_warnings.json').read_text(encoding='utf-8'))
  audits[folder.name]=w
  for key in ('failed_days','low_row_open_days','cross_query_count_disagreements','unparsed_candidate_days'):
   if w.get(key):errors.append(f'{folder.name}/{key}: {w[key][:20]}')
  all_items+=json.loads((folder/'self_reports_history.json').read_text(encoding='utf-8'))['items']
 # Historical MOPS source must be verified before treating unobserved events as negatives.
 if errors:
  (out/'blocking_audit.json').write_text(json.dumps({'errors':errors,'warnings':audits},ensure_ascii=False,indent=2),encoding='utf-8')
  raise SystemExit('H1 MOPS historical coverage not verified: '+json.dumps(errors,ensure_ascii=False))
 master=model.read(ROOT/'data/master.json')['stocks']
 # model.reports() is the production event classifier and deduplicator.
 tmp=out/'raw_mops_history.json';model.write(tmp,{'items':all_items})
 events,rejected=model.reports(tmp,master,('twse','tpex'))
 events=[e for e in events if '2026-01-01'<=e['date']<='2026-06-30']
 if not any(e['kind']=='attention' and e['date']<'2026-05-01' for e in events) or not any(e['kind']=='attention' and '2026-05-01'<=e['date']<='2026-05-31' for e in events) or not any(e['kind']=='attention' and '2026-06-01'<=e['date']<='2026-06-30' for e in events):
  raise SystemExit('Historical attention-triggered monthly reports absent in required training/evaluation windows')
 # Never drop ambiguous candidate filings without auditing them.
 uncertain=[x for x in rejected if '公告種類需人工確認' in x['reason']]
 model.write(out/'classification_audit.json',{'accepted':len(events),'rejected':rejected,'ambiguous_count':len(uncertain),'mops_coverage':audits})
 if uncertain:raise SystemExit(f'{len(uncertain)} ambiguous MOPS candidates require audit; metrics blocked')
 model.csvout(out/'events_2026_h1.csv',events)
 print('H1_MOPS_EVENTS_VERIFIED',len(events),collections.Counter((e['date'][:7],e['market'],e['kind']) for e in events))
if __name__=='__main__':main()
