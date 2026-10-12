#!/usr/bin/env python3
"""Independent V3 stock re-selection experiment; does not write production files.
Run at repository root: python ai_shadow_backtest.py
Historical daily prices and institutional flows are point-in-time; sector whitelist is
current (not historical) and holder history is unavailable, so this is a PROXY test,
NOT an exact reproduction of the production 966-stock V1 universe/model.
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent
MARKET = ROOT / 'data/history/market'
INST = ROOT / 'data/history/institutional'
SECTORS = ROOT / 'data/sectors.json'
BACKTEST = ROOT / 'data/ai_backtest.json'
OUT = ROOT / 'data/ai_shadow_test.json'
CSV = ROOT / 'data/ai_shadow_test.csv'


def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def val(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def pct(a, b):
    return 100 * (b / a - 1) if a and b and a > 0 else None


def rank_percentile(items, key):
    good = sorted([(val(x.get(key)), x['ticker']) for x in items if val(x.get(key)) is not None])
    n = len(good)
    ranks = {ticker: 100 * i / max(1, n - 1) for i, (_, ticker) in enumerate(good)}
    for x in items:
        x[key + '_rank'] = ranks.get(x['ticker'], 0)


def summary(rows):
    values = [x['return'] for x in rows if x.get('return') is not None]
    return {'samples': len(values), 'avg_return': round(mean(values), 4) if values else None,
            'median_return': round(median(values), 4) if values else None,
            'win_rate': round(100 * sum(x > 0 for x in values) / len(values), 2) if values else None}


def main():
    sector_data = read(SECTORS)
    sector_items = sector_data.get('sectors', []) if isinstance(sector_data, dict) else []
    universe = {str(s.get('ticker')) for sec in sector_items for s in sec.get('stocks', []) if isinstance(s, dict) and s.get('ticker')}
    if not universe:
        raise SystemExit('No sectors found: expected data/sectors.json; refusing misleading test')
    market = {p.stem: read(p).get('stocks', {}) for p in MARKET.glob('*.json')}
    market = {k: v for k, v in market.items() if isinstance(v, dict) and v}
    dates = sorted(market)
    institutional = {}
    for p in INST.glob('*.json'):
        d = read(p)
        institutional[p.stem] = {**d.get('twse', {}), **d.get('tpex', {})}
    old = read(BACKTEST)
    records = old.get('records', [])
    old_by_date_market = defaultdict(list)
    for r in records:
        if r.get('market') in ('twse', 'tpex') and r.get('status_5d') == 'complete':
            old_by_date_market[(r.get('selection_date'), r['market'])].append(r)
    if not old_by_date_market:
        raise SystemExit('No mature baseline dates in ai_backtest.json')
    day_index = {d: i for i, d in enumerate(dates)}
    # Only complete 5-day horizons; no future leakage in signal computation.
    all_results = []
    picks = []
    coverage = []
    for date, market_name in sorted(old_by_date_market):
        i = day_index.get(date)
        if i is None or i < 20 or i + 5 >= len(dates):
            coverage.append({'date': date, 'market': market_name, 'reason': 'insufficient 20-day history or future prices'})
            continue
        hist = dates[:i + 1]
        five = hist[-5:]
        today = market[date]
        pool = []
        for ticker in universe:
            now = today.get(ticker, {})
            if not isinstance(now, dict) or now.get('market') != market_name:
                continue
            closes = [val(market[d].get(ticker, {}).get('price')) for d in hist[-21:]]
            if len(closes) != 21 or any(p is None or p <= 0 for p in closes):
                continue
            volume = [val(market[d].get(ticker, {}).get('volume')) for d in hist[-6:]]
            if any(v is None for v in volume) or mean(volume[:-1]) <= 0:
                continue
            current = closes[-1]
            r5, r10, r20 = (pct(closes[-1-n], current) for n in (5, 10, 20))
            # Avoid treating missing institutional days as zeros.
            inst_days = [institutional.get(d) for d in five]
            if any(x is None or ticker not in x for x in inst_days):
                continue
            flows = [x[ticker] for x in inst_days]
            turnover = sum(val(market[d].get(ticker, {}).get('turnover')) or 0 for d in five)
            if turnover <= 0:
                continue
            net = sum(sum(val(f.get(k)) or 0 for k in ('foreign', 'trust', 'dealer')) * closes[-1 - (4 - j)] for j, f in enumerate(flows))
            ma10, ma20 = mean(closes[-10:]), mean(closes[-20:])
            volume_ratio = volume[-1] / mean(volume[:-1])
            # Explicitly no current-day or future information beyond selection-day close.
            pool.append({'ticker': ticker, 'name': now.get('name', ''), 'market': market_name,
                         'date': date, 'entry': current, 'r5': r5, 'r10': r10, 'r20': r20,
                         'flow': net / turnover * 100, 'volume_ratio': volume_ratio,
                         'breakout': (current / max(closes[-21:-1]) - 1) * 100,
                         'trend': 1 if current > ma10 > ma20 else 0,
                         'overheat': max(0, r5 - 15) * 1.5 + max(0, (current / ma20 - 1) * 100 - 18),
                         'return': pct(current, val(market[dates[i + 5]].get(ticker, {}).get('price')))})
        if len(pool) < 20:
            coverage.append({'date': date, 'market': market_name, 'reason': 'fewer than 20 valid sector-universe candidates', 'count': len(pool)})
            continue
        for key in ('flow', 'r5', 'r10', 'r20', 'volume_ratio', 'breakout'):
            rank_percentile(pool, key)
        for row in pool:
            row['score_A'] = .45 * row['flow_rank'] + .25 * row['breakout_rank'] + .20 * row['r10_rank'] + 10 * row['trend'] - row['overheat']
            row['score_B'] = .55 * row['flow_rank'] + .20 * row['r5_rank'] + .15 * row['volume_ratio_rank'] + .10 * row['r20_rank'] - 2 * row['overheat']
            row['score_C'] = .35 * row['flow_rank'] + .25 * row['r5_rank'] + .20 * row['breakout_rank'] + .10 * row['r10_rank'] + 10 * row['trend'] - 1.5 * row['overheat']
        baseline = sorted(old_by_date_market[(date, market_name)], key=lambda x: int(x.get('rank') or 999))
        for strategy in ('V1', 'A', 'B', 'C'):
            if strategy == 'V1':
                selected = [{'ticker': r['ticker'], 'name': r.get('name', ''), 'return': val(r.get('baseline_return_5d'))} for r in baseline]
            else:
                selected = sorted(pool, key=lambda x: (-x['score_' + strategy], x['ticker']))[:20]
            for pos, x in enumerate(selected, 1):
                picks.append({'date': date, 'market': market_name, 'strategy': strategy, 'rank': pos,
                              'ticker': x['ticker'], 'name': x.get('name', ''), 'return_5d': x.get('return')})
            for k in (5, 10, 20):
                ss = selected[:k]
                all_results.append({'date': date, 'market': market_name, 'strategy': strategy,
                                    'top': k, 'pool_size': len(pool), **summary(ss)})
    if not all_results:
        raise SystemExit('No valid historical dates. Need >=21 earlier daily snapshots and 5 future days. No results written.')
    grouped = defaultdict(list)
    for p in picks:
        grouped[(p['strategy'], p['market'], p['rank'] <= 5 and 5 or p['rank'] <= 10 and 10 or 20)].append(p)
    report = {}
    for strategy in ('V1', 'A', 'B', 'C'):
        report[strategy] = {}
        for mk in ('twse', 'tpex', 'all'):
            report[strategy][mk] = {}
            for top in (5, 10, 20):
                subset = [p for p in picks if p['strategy'] == strategy and (mk == 'all' or p['market'] == mk) and p['rank'] <= top]
                report[strategy][mk][f'top{top}'] = summary([{'return': p['return_5d']} for p in subset])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'method': 'point-in-time sector-universe proxy; NOT full original technology universe',
                              'limitations': ['Uses current sectors.json constituents (survivorship bias)',
                                              'Historical holder changes unavailable; V1 is the recorded original, V3 is a proxy model',
                                              'Sector whitelist is smaller than original technology universe',
                                              'Only 5-day mature returns; no transaction fees/slippage',
                                              'Selection at same-day close assumes executable close and published same-day institutional data'],
                              'summary': report, 'daily': all_results, 'skipped': coverage,
                              'selection_days': len(set(x['date'] for x in picks))}, ensure_ascii=False, indent=2), encoding='utf-8')
    with CSV.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'market', 'strategy', 'rank', 'ticker', 'name', 'return_5d'])
        writer.writeheader(); writer.writerows(picks)
    print('AI V3 proxy backtest completed; NO production files changed')
    print('Days:', len(set(x['date'] for x in picks)), 'picks:', len(picks), 'skipped:', len(coverage))
    for strategy in report:
        print(strategy, 'overall top20:', report[strategy]['all']['top20'])
    print('Output:', OUT.relative_to(ROOT), CSV.relative_to(ROOT))


if __name__ == '__main__':
    main()
