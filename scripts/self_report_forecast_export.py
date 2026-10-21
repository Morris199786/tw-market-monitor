#!/usr/bin/env python3
"""V17: frozen historical replay + append-only forward forecasts + audited settlements.

Optional settlement input: data/self_report_v17_actuals_verified.json:
{"days":{"2026-10-21":{"complete":true,"twse":["1234"],"tpex":["5678"]}}}
The upstream collector MUST set complete only after verifying the full-market
attention-triggered self-report announcements for the TARGET date.
"""
import argparse, csv, datetime as dt, json, os, tempfile
from pathlib import Path
from collections import Counter
from zoneinfo import ZoneInfo
TZ=ZoneInfo('Asia/Taipei')

def load(p, default=None):
    p=Path(p)
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else default

def atomic_write(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def stats(picks,hits,actual):
    return dict(predictions=picks,hits=hits,actual=actual,
                precision=hits/picks if picks else None,
                recall=hits/actual if actual else None,
                f1=2*hits/(picks+actual) if picks+actual else None)

def run(args):
    pred=load(args.predictions);hist=load(args.summary)
    if not isinstance(pred,dict) or not isinstance(hist,dict):raise SystemExit('missing prediction or historical summary')
    if hist.get('first_evaluated_date')!='2026-07-23' or hist.get('last_evaluated_date')!='2026-10-20' or hist.get('evaluated_days',0)<60:
        raise SystemExit('historical archive incomplete; refuse publication')
    day=pred.get('prediction_day');asof=pred.get('asof')
    if not day or not asof or day<=asof:raise SystemExit('invalid target/cutoff')
    picks=[dict(ticker=str(p['ticker']),name=str(p.get('name','')),market=p['market'],probability=p.get('probability'),reasons=p.get('reasons',[])) for p in pred.get('items',[]) if p.get('market') in ('twse','tpex')]
    counts=Counter(p['market'] for p in picks)
    if any(v>10 for v in counts.values()):raise SystemExit('more than 10 picks per market')
    ledger=load(args.ledger,{'schema':2,'forecasts':{},'settlements':{}})
    ledger.setdefault('forecasts',{});ledger.setdefault('settlements',{})
    rec=dict(asof=asof,model_version=pred['version'],picks=picks)
    old=ledger['forecasts'].get(day)
    if old is not None and old!=rec:raise SystemExit('immutable forecast conflict: '+day)
    ledger['forecasts'].setdefault(day,rec)
    verified=load(args.verified_actuals,{'days':{}})
    verified_days=verified.get('days',{})
    if not isinstance(verified_days,dict):raise SystemExit('invalid verified actuals')
    for target, record in sorted(ledger['forecasts'].items()):
        actual=verified_days.get(target)
        if not actual or actual.get('complete') is not True:continue
        if target>=dt.datetime.now(TZ).date().isoformat():continue
        if not all(k in actual and isinstance(actual[k],list) for k in ('twse','tpex')):raise SystemExit('verified day lacks market-wide lists: '+target)
        daily={};clean={}
        for market in ('twse','tpex'):
            codes=actual[market]
            if len(codes)!=len(set(codes)) or any(not str(c).isdigit() or len(str(c))!=4 for c in codes):raise SystemExit('invalid actual codes: '+target)
            clean[market]=sorted(str(c) for c in codes)
            recommended={p['ticker'] for p in record['picks'] if p['market']==market}
            hits=sorted(recommended & set(clean[market]))
            daily[market]=dict(**stats(len(recommended),len(hits),len(clean[market])),hit_tickers=hits,missed_tickers=sorted(set(clean[market])-recommended))
        settlement=dict(actuals=clean,metrics=daily,source=actual.get('source','verified_full_market'),verified_at=actual.get('verified_at'))
        existing=ledger['settlements'].get(target)
        if existing is not None and existing!=settlement:raise SystemExit('immutable settlement conflict: '+target)
        ledger['settlements'].setdefault(target,settlement)
    # Legacy settlement files remain unchanged; no retroactive mutation of historical picks.
    hist_stats={m:{k:hist[m].get(k) for k in ('predictions','hits','actual','precision','recall','f1')} for m in ('twse','tpex')}
    forward={}
    for market in ('twse','tpex'):
        settled=[v['metrics'][market] for v in ledger['settlements'].values()]
        totals={k:sum(v[k] for v in settled) for k in ('predictions','hits','actual')}
        forward[market]=dict(**stats(totals['predictions'],totals['hits'],totals['actual']),settled_days=len(settled))
    combined={m:stats(hist_stats[m]['predictions']+forward[m]['predictions'],hist_stats[m]['hits']+forward[m]['hits'],hist_stats[m]['actual']+forward[m]['actual']) for m in ('twse','tpex')}
    with open(args.daily,encoding='utf-8-sig',newline='') as f:daily=list(csv.DictReader(f))
    payload=dict(updated_at=dt.datetime.now(TZ).isoformat(timespec='seconds'),prediction_date=day,asof=asof,picks=picks,
        model_version=pred.get('version'),backtest=dict(start=hist['first_evaluated_date'],end=max([hist['last_evaluated_date']]+list(ledger['settlements'])),**combined),
        backtest_detail=dict(kind='historical_replay_plus_verified_forward',historical_end=hist['last_evaluated_date'],historical=hist_stats,forward=forward,daily=daily,
            warning='7～10月為歷史研究回測；未來日期只計入已驗證全市場公告的預測，不完整日期保持待核對。'),
        forward_forecasts=ledger['forecasts'],forward_settlements=ledger['settlements'],
        pending_dates=sorted(set(ledger['forecasts'])-set(ledger['settlements'])),source_status=pred.get('source_status',{}))
    atomic_write(args.ledger,ledger);atomic_write(args.output,payload)
    print('PUBLISHED',day,'historical',hist['first_evaluated_date'],hist['last_evaluated_date'],
          'settled',len(ledger['settlements']),'pending',len(payload['pending_dates']))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--predictions',required=True);ap.add_argument('--summary',required=True);ap.add_argument('--daily',required=True)
    ap.add_argument('--output',default='data/self_report_forecast.json');ap.add_argument('--ledger',default='data/self_report_v17_forecast_ledger.json')
    ap.add_argument('--verified-actuals',default='data/self_report_v17_actuals_verified.json')
    run(ap.parse_args())
if __name__=='__main__':main()
