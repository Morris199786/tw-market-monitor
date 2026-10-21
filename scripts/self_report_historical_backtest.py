#!/usr/bin/env python3
"""Historical replay: listed Rule A, OTC unchanged legacy V17 Model.
Does not alter the production Prediction pipeline.
"""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path
import self_report_predict as model


def run(args):
    root = Path(args.root)
    out = root / args.out
    out.mkdir(parents=True, exist_ok=True)
    notices, status = model.attention(args.start, args.end, out / 'attention_cache')
    master = model.read(root / 'data/master.json')['stocks']
    events, rejected = model.reports(root / args.reports, master, ('twse', 'tpex'))
    events = [e for e in events if e['date'] <= args.end]
    cal = model.calendar(root, args.start, args.end, notices)
    days = [d for d in cal if args.backtest_start <= d <= args.end and cal.index(d) > 0]
    if not days or days[0] != args.backtest_start:
        raise RuntimeError(f'Requested first evaluation date {args.backtest_start} is not an available trading day; first available={days[0] if days else None}')
    training = []
    daily, picks_all, scores_all = [], [], []
    for d in cal:
        if d <= args.start or d > args.end:
            continue
        i = cal.index(d)
        if not i:
            continue
        rows = model.make_rows(cal[i-1], d, cal, notices, events, master)
        if d >= args.backtest_start:
            # TWSE A has no training/warmup requirement.
            listed = model.rule_a_select(rows)
            # OTC is EXACTLY the production legacy Model/eligible/threshold/ranking.
            # Only past dates train it; do not gate both markets on a common warmup.
            legacy = model.Model(training)
            otc_scores = []
            for r in rows:
                if r['market'] != 'tpex':
                    continue
                p, n = legacy.predict(r)
                otc_scores.append(dict(r, probability=p, cell_samples=n))
            otc = sorted((r for r in otc_scores if r['rule_eligible'] and r['probability'] >= .10),
                         key=lambda r: (-r['probability'], r['ticker']))[:model.CAP]
            picks = listed + otc
            actual = {(e['market'], e['ticker']) for e in events if e['date'] == d and e['kind'] == 'attention'}
            hits = {(r['market'], r['ticker']) for r in picks} & actual
            daily.append(dict(date=d, twse_picks=len(listed), tpex_picks=len(otc),
                              twse_hits=sum(x[0]=='twse' for x in hits),
                              tpex_hits=sum(x[0]=='tpex' for x in hits),
                              twse_actual=sum(x[0]=='twse' for x in actual),
                              tpex_actual=sum(x[0]=='tpex' for x in actual),
                              tpex_training_events=sum(r['label'] for r in training if r['market']=='tpex'),
                              tickers=' '.join(r['ticker'] for r in picks)))
            picks_all.extend(picks)
            scores_all.extend(otc_scores)
        training.extend(rows)
    def stat(market):
        selected = [r for r in picks_all if market is None or r['market'] == market]
        actual = sum((r['twse_actual'] if market in (None,'twse') else 0) +
                     (r['tpex_actual'] if market in (None,'tpex') else 0) for r in daily)
        return model.metrics(selected, actual)
    summary = dict(version=model.VERSION, asof=args.end, requested_start=args.backtest_start,
                   first_evaluated_date=daily[0]['date'],last_evaluated_date=daily[-1]['date'],
                   evaluated_days=len(daily), twse=stat('twse'), tpex=stat('tpex'), model=stat(None),
                   source_status=status,
                   warnings=['OTC uses unchanged Model/eligible/10% threshold; pre-7/23 training starts from available 7/1 rows, so this is not directly comparable with older archived 87.95% unless source/training/evaluation dates match.',
                             'Recall depends on completeness of archived historical filing labels.'])
    model.write(out / 'backtest_summary.json', summary)
    model.csvout(out / 'backtest_daily.csv', daily)
    model.csvout(out / 'backtest_picks.csv', picks_all)
    model.csvout(out / 'walk_forward_scores.csv', scores_all)
    model.csvout(out / 'event_audit.csv', events)
    model.csvout(out / 'excluded_announcements.csv', rejected)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('EVALUATED_DAYS',len(daily),'FIRST_EVALUATED_DATE',daily[0]['date'])

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',default='.')
    p.add_argument('--start',default='2026-07-01')
    p.add_argument('--backtest-start',default='2026-07-23')
    p.add_argument('--end',default='2026-10-20')
    p.add_argument('--reports',default='data/self_reports_history.json')
    p.add_argument('--out',default='self_report_historical_backtest')
    run(p.parse_args())
