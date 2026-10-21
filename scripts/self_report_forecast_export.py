#!/usr/bin/env python3
"""Publish recomputed forecasts. Repeated runs are allowed; settled history is protected."""
import argparse
import datetime as dt
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Taipei')
START = '2026-10-21'

def load(path, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else default

def save(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + p.name, dir=p.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write('\n')
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def stats(predictions, hits, actual):
    return dict(predictions=predictions, hits=hits, actual=actual,
                precision=hits / predictions if predictions else None,
                recall=hits / actual if actual else None,
                f1=2 * hits / (predictions + actual) if predictions + actual else None)

def run(args):
    ledger = load(args.ledger, {'schema': 2, 'forecasts': {}, 'settlements': {}})
    if not isinstance(ledger, dict):
        raise ValueError('Invalid ledger')
    forecasts = ledger.setdefault('forecasts', {})
    settlements = ledger.setdefault('settlements', {})
    prediction = load(args.predictions)
    day = args.target_date or (prediction or {}).get('prediction_day')
    if not day or day < START:
        raise ValueError('Missing/invalid target date: ' + str(day))
    # No date-based skip: a real freshly computed prediction is mandatory.
    if not isinstance(prediction, dict) or prediction.get('prediction_day') != day:
        raise ValueError('Missing fresh prediction for ' + day)
    asof = prediction.get('asof')
    if not asof or asof >= day:
        raise ValueError('Invalid cutoff')
    picks = [dict(ticker=str(p['ticker']), name=str(p.get('name', '')),
                  market=p['market'], probability=p.get('probability'),
                  reasons=p.get('reasons', [])) for p in prediction.get('items', [])
             if p.get('market') in ('twse', 'tpex')]
    counts = Counter(p['market'] for p in picks)
    if any(n > 10 for n in counts.values()):
        raise ValueError('More than 10 picks in one market')
    if len({(p['market'], p['ticker']) for p in picks}) != len(picks):
        raise ValueError('Duplicate pick')
    rec = dict(asof=asof, model_version=prediction['version'], picks=picks)
    old = forecasts.get(day)
    if day in settlements or (old is not None and day <= dt.datetime.now(TZ).date().isoformat()):
        # Always recompute and verify, but never rewrite a scored historical prediction.
        if old is None:
            raise ValueError('Settled day has no original forecast: '+day)
        print('HISTORICAL_SETTLED_PRESERVED', day,
              'fresh_model', rec['model_version'], 'stored_model', old['model_version'])
        rec = old
    elif old is None:
        forecasts[day] = rec
        print('SAVE_NEW_FORECAST', day, 'picks', len(picks))
    elif old != rec:
        # Keep an audit trail for model/data revisions without creating a new date.
        revisions = ledger.setdefault('revisions', {}).setdefault(day, [])
        if not revisions or revisions[-1] != old:
            revisions.append(old)
        forecasts[day] = rec
        print('UPDATE_FORECAST', day, 'old_model', old.get('model_version'),
              'new_model', rec['model_version'], 'picks', len(picks))
    else:
        print('RECOMPUTED_IDENTICAL_FORECAST', day, 'picks', len(picks))

    verified = load(args.verified_actuals, {'days': {}})
    if not isinstance(verified, dict) or not isinstance(verified.get('days'), dict):
        raise ValueError('Invalid actuals')
    today = dt.datetime.now(TZ).date().isoformat()
    for target, original in sorted(forecasts.items()):
        if target < START or target > today:
            continue
        actual = verified['days'].get(target)
        if not isinstance(actual, dict) or actual.get('complete') is not True:
            continue
        actuals, daily = {}, {}
        for market in ('twse', 'tpex'):
            codes = actual.get(market)
            if not isinstance(codes, list) or any(not isinstance(c, str) or len(c) != 4 or not c.isdigit() for c in codes):
                raise ValueError(f'Invalid actuals {target} {market}')
            if len(set(codes)) != len(codes):
                raise ValueError(f'Duplicate actuals {target} {market}')
            actuals[market] = sorted(codes)
            predicted = {p['ticker'] for p in original['picks'] if p['market'] == market}
            hits = sorted(predicted & set(codes))
            daily[market] = dict(**stats(len(predicted), len(hits), len(codes)),
                                 hit_tickers=hits, missed_tickers=sorted(set(codes) - predicted))
        settlements[target] = dict(actuals=actuals, metrics=daily,
                                   provisional=actual.get('provisional', False),
                                   source=actual.get('source', 'site_self_reports_history_assumed_complete'),
                                   verified_at=actual.get('verified_at'))

    forward = {}
    for market in ('twse', 'tpex'):
        rows = [v['metrics'][market] for date, v in settlements.items() if date >= START]
        totals = {k: sum(x[k] for x in rows) for k in ('predictions', 'hits', 'actual')}
        forward[market] = dict(**stats(**totals), settled_days=len(rows))
    settled_dates = sorted(x for x in settlements if x >= START)
    payload = dict(updated_at=dt.datetime.now(TZ).isoformat(timespec='seconds'),
                   prediction_date=day, asof=rec['asof'], picks=rec['picks'],
                   model_version=rec['model_version'],
                   backtest=dict(start=START, end=settled_dates[-1] if settled_dates else None,
                                 twse=forward['twse'], tpex=forward['tpex']),
                   backtest_detail=dict(kind='prospective_only', start=START, forward=forward,
                                        includes_provisional=any(settlements[d].get('provisional', False) for d in settled_dates),
                                        daily=[dict(date=d, provisional=settlements[d].get('provisional', False), **settlements[d]['metrics']) for d in settled_dates]),
                   pending_dates=sorted(d for d in forecasts if d >= START and d not in settlements),
                   forward_forecasts=forecasts, forward_settlements=settlements,
                   source_status=prediction.get('source_status', {}))
    save(args.ledger, ledger)
    save(args.output, payload)
    print('PUBLISHED', day, 'settled_days', len(settled_dates), 'pending', len(payload['pending_dates']))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--predictions', default='self_report_live/predictions.json')
    p.add_argument('--target-date', default='')
    p.add_argument('--summary', default='')
    p.add_argument('--daily', default='')
    p.add_argument('--ledger', default='data/self_report_v17_forecast_ledger.json')
    p.add_argument('--verified-actuals', default='data/self_report_v17_actuals_verified.json')
    p.add_argument('--output', default='data/self_report_forecast.json')
    run(p.parse_args())

if __name__ == '__main__':
    main()

