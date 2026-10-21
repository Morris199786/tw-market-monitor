#!/usr/bin/env python3
"""Fetch official TWSE/TPEx attention notices for 2026 H1, privately.
No fabricated MOPS labels; reports an explicit blocker until separately audited.
"""
import argparse, collections, csv, datetime as dt, hashlib, json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import self_report_predict as model

def dump(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='private_h1_backfill')
    ap.add_argument('--start',default='2026-01-01')
    ap.add_argument('--end',default='2026-06-30')
    args=ap.parse_args()
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    # Use official market data as trading-day base; never infer sessions from notices alone.
    monitor=model.read(ROOT/'data/market_monitor.json')
    calendar=sorted({x['date'] for x in monitor.get('raw',[]) if x.get('index') is not None and args.start<=x['date']<=args.end})
    if not calendar or calendar[0]>'2026-01-05' or calendar[-1]<'2026-06-30':
        raise SystemExit('Incomplete official trading calendar: '+str((calendar[:1],calendar[-1:])))
    dump(out/'trading_calendar_2026_h1.json',calendar)
    all_notices=[];source=[]
    for market in ('twse','tpex'):
        start=dt.date.fromisoformat(args.start);end=dt.date.fromisoformat(args.end)
        while start<=end:
            stop=min(start+dt.timedelta(days=13),end)
            a,b=start.isoformat(),stop.isoformat()
            # Reuse the production parser, but use fresh private cache and fixed windows.
            rows,status=model.attention(a,b,cache=out/'attention_cache',markets=(market,))
            all_notices.extend(rows)
            source.append({'market':market,'start':a,'end':b,'count':len(rows),'source':status[market]['source']})
            start=stop+dt.timedelta(days=1)
    unique={}
    for n in all_notices:
        key=(n['date'],n['ticker'],n['market'])
        if key in unique:
            unique[key]['reason']+=' '+n.get('reason','')
        else:unique[key]=dict(n)
    notices=sorted(unique.values(),key=lambda x:(x['date'],x['market'],x['ticker']))
    dump(out/'attention_2026_h1.json',notices)
    coverage={m:{'records':sum(x['market']==m for x in notices),'dates':len({x['date'] for x in notices if x['market']==m})} for m in ('twse','tpex')}
    dump(out/'manifest.json',{'attention_source':'TWSE/TPEx official endpoints','range':[args.start,args.end], 'coverage':coverage,'queries':source,'trading_days':len(calendar),'attention_sha256':hashlib.sha256((out/'attention_2026_h1.json').read_bytes()).hexdigest(),'mops_events_complete':False,'backtest_allowed':False,'blocker':'Historical MOPS attention-triggered and voluntary self-report labels must be independently collected and verified; no accuracy metrics without them.'})
    print('ATTENTION_BACKFILL_DONE',json.dumps(coverage,ensure_ascii=False),'calendar_days',len(calendar))
    print('BLOCKED: MOPS H1 actuals not yet verified; no backtest performed.')
if __name__=='__main__':main()
