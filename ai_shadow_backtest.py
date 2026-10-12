#!/usr/bin/env python3
"""Read-only V3 shadow backtest. Keep ai-shadow-test.yml unchanged.
Signals use selection-day close and institutional data: close execution is NOT
realistically guaranteed. Current sector membership creates survivorship bias.
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data/ai_shadow_test.json'
CSV = ROOT / 'data/ai_shadow_test.csv'


def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def ret(a, b):
    return 100 * (b / a - 1) if a is not None and b is not None and a > 0 else None


def percentile(pool, field):
    values = sorted((r[field], r['ticker']) for r in pool if r.get(field) is not None)
    ranks = {t: 100 * i / max(1, len(values) - 1) for i, (_, t) in enumerate(values)}
    for row in pool:
        row[field + '_rank'] = ranks.get(row['ticker'], 0)


def stats(values):
    a = [v for v in values if v is not None]
    return {'samples': len(a), 'avg_return': round(mean(a), 4) if a else None,
            'median_return': round(median(a), 4) if a else None,
            'win_rate': round(100 * sum(v > 0 for v in a) / len(a), 2) if a else None,
            'worst_return': round(min(a), 4) if a else None}


def main():
    sectors = load(ROOT / 'data/sectors.json').get('sectors', [])
    universe = {str(s['ticker']) for sec in sectors for s in sec.get('stocks', [])
                if isinstance(s, dict) and s.get('ticker')}
    if not universe:
        raise SystemExit('ERROR: sector universe missing')
    market = {}
    for path in (ROOT / 'data/history/market').glob('*.json'):
        stocks = load(path).get('stocks', {})
        if stocks:
            market[path.stem] = stocks
    dates = sorted(market)
    idx = {d: i for i, d in enumerate(dates)}
    inst = {}
    for path in (ROOT / 'data/history/institutional').glob('*.json'):
        data = load(path)
        inst[path.stem] = {**data.get('twse', {}), **data.get('tpex', {})}
    old = defaultdict(list)
    for record in load(ROOT / 'data/ai_backtest.json').get('records', []):
        if record.get('market') in ('twse', 'tpex') and record.get('status_5d') == 'complete':
            old[(record.get('selection_date'), record['market'])].append(record)
    if not old:
        raise SystemExit('ERROR: no mature V1 baseline')
    picks, daily, skipped = [], [], []
    strategies = ('V1', 'A', 'B', 'C', 'A_RS', 'A_VOLUME', 'A_HEAT', 'A_PLUS')
    for (day, exchange), original in sorted(old.items()):
        i = idx.get(day, -1)
        if i < 20 or i + 5 >= len(dates):
            skipped.append({'date': day, 'market': exchange, 'reason': 'insufficient history/future'})
            continue
        hist = dates[i-20:i+1]
        future = market[dates[i+5]]
        today = market[day]
        five_days = dates[i-4:i+1]
        pool = []
        for ticker in universe:
            stock = today.get(ticker, {})
            if stock.get('market') != exchange:
                continue
            closes = [num(market[d].get(ticker, {}).get('price')) for d in hist]
            if any(v is None or v <= 0 for v in closes):
                continue
            volumes = [num(market[d].get(ticker, {}).get('volume')) for d in dates[i-5:i+1]]
            if any(v is None for v in volumes) or mean(volumes[:-1]) <= 0:
                continue
            if any(d not in inst or ticker not in inst[d] for d in five_days):
                continue
            turnover = sum(num(market[d].get(ticker, {}).get('turnover')) or 0 for d in five_days)
            if turnover <= 0:
                continue
            flow = 0
            for j, d in enumerate(five_days):
                entry = inst[d][ticker]
                shares = sum(num(entry.get(k)) or 0 for k in ('foreign', 'trust', 'dealer'))
                flow += shares * closes[-5+j]
            price = closes[-1]
            r5, r10, r20 = (ret(closes[-1-n], price) for n in (5, 10, 20))
            ma10, ma20 = mean(closes[-10:]), mean(closes[-20:])
            volume_ratio = volumes[-1] / mean(volumes[:-1])
            # Volume confirmation: reward controlled 1.2x-2.5x expansion;
            # avoid rewarding extremely speculative volume spikes.
            volume_confirm = max(0, 100 - abs(volume_ratio - 1.7) * 65)
            heat = max(0, r5 - 15) * 1.5 + max(0, ret(ma20, price) - 18)
            # Smooth penalty begins at 10% five-day gain and 13% above MA20.
            heat_smooth = (max(0, r5 - 10) ** 1.2) * .7 + max(0, ret(ma20, price) - 13) * 1.1
            pool.append({'ticker': ticker, 'name': stock.get('name', ''), 'market': exchange,
                         'r5': r5, 'r10': r10, 'r20': r20, 'flow': flow / turnover * 100,
                         'breakout': ret(max(closes[:-1]), price), 'volume_ratio': volume_ratio,
                         'volume_confirm': volume_confirm, 'trend': int(price > ma10 > ma20),
                         'overheat': heat, 'heat_smooth': heat_smooth,
                         'return': ret(price, num(future.get(ticker, {}).get('price')))})
        if len(pool) < 20:
            skipped.append({'date': day, 'market': exchange, 'reason': 'fewer than 20 eligible stocks', 'pool_size': len(pool)})
            continue
        for key in ('flow', 'r5', 'r10', 'r20', 'breakout', 'volume_ratio', 'volume_confirm'):
            percentile(pool, key)
        # RS uses relative stock return versus median of same-market candidates,
        # not a future index return. Its percentile ranking is identical to r5_rank
        # within each market, so we deliberately test a different 20-day RS horizon.
        market_r20 = median(r['r20'] for r in pool)
        for row in pool:
            row['rs20'] = row['r20'] - market_r20
        percentile(pool, 'rs20')
        for row in pool:
            f, b, m10, m5 = (row[k+'_rank'] for k in ('flow', 'breakout', 'r10', 'r5'))
            trend = 10 * row['trend']
            row['score_A'] = .45*f + .25*b + .20*m10 + trend - row['overheat']
            row['score_B'] = .55*f + .20*m5 + .15*row['volume_ratio_rank'] + .10*row['r20_rank'] - 2*row['overheat']
            row['score_C'] = .35*f + .25*m5 + .20*b + .10*m10 + trend - 1.5*row['overheat']
            # Controlled ablation: modify ONE factor at a time from A.
            row['score_A_RS'] = .40*f + .25*b + .20*m10 + .05*row['rs20_rank'] + trend - row['overheat']
            row['score_A_VOLUME'] = .40*f + .25*b + .20*m10 + .05*row['volume_confirm_rank'] + trend - row['overheat']
            row['score_A_HEAT'] = .45*f + .25*b + .20*m10 + trend - row['heat_smooth']
            row['score_A_PLUS'] = (.35*f + .20*b + .15*m10 + .10*row['rs20_rank']
                                   + .10*row['volume_confirm_rank'] + trend - row['heat_smooth'])
        original.sort(key=lambda r: int(r.get('rank') or 999))
        for strategy in strategies:
            if strategy == 'V1':
                chosen = [{'ticker': r['ticker'], 'name': r.get('name', ''),
                           'return': num(r.get('baseline_return_5d'))} for r in original[:20]]
            else:
                chosen = sorted(pool, key=lambda r: (-r['score_'+strategy], r['ticker']))[:20]
            for rank, row in enumerate(chosen, 1):
                picks.append({'date': day, 'market': exchange, 'strategy': strategy,
                              'rank': rank, 'ticker': row['ticker'], 'name': row['name'],
                              'return_5d': row['return']})
            for top in (5, 10, 20):
                daily.append({'date': day, 'market': exchange, 'strategy': strategy,
                              'top': top, 'pool_size': len(pool),
                              **stats([r['return'] for r in chosen[:top]])})
    if not picks:
        raise SystemExit('ERROR: no eligible dates; outputs not written')
    report = {}
    for strategy in strategies:
        report[strategy] = {}
        for exchange in ('twse', 'tpex', 'all'):
            report[strategy][exchange] = {}
            for top in (5, 10, 20):
                rows = [r for r in picks if r['strategy'] == strategy
                        and (exchange == 'all' or r['market'] == exchange) and r['rank'] <= top]
                report[strategy][exchange]['top'+str(top)] = stats([r['return_5d'] for r in rows])
    # Day-level performance shows whether a strategy depends on one extraordinary date.
    daily_spread = {}
    for strategy in strategies:
        daily_spread[strategy] = {}
        for exchange in ('twse', 'tpex', 'all'):
            vals = [r['avg_return'] for r in daily if r['strategy'] == strategy and r['top'] == 20
                    and (exchange == 'all' or r['market'] == exchange) and r['avg_return'] is not None]
            daily_spread[strategy][exchange] = stats(vals)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        'method': 'V3-A factor ablation; same formulas for TWSE and TPEx; historical sector proxy',
        'strategies': list(strategies), 'summary': report, 'daily': daily,
        'daily_top20_distribution': daily_spread, 'skipped': skipped,
        'selection_days': len(set(p['date'] for p in picks)),
        'limitations': ['Current sectors.json membership causes survivorship bias',
                        'No historical TDCC large-holder factors',
                        'Selection-day closing price and same-day institutional flows are not executable point-in-time signals; potential look-ahead bias',
                        'Five-day returns overlap across selection dates',
                        'No fees, slippage or sample-out-of-time validation',
                        'RS20 is relative to the current same-market eligible candidate median']
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    with CSV.open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=['date', 'market', 'strategy', 'rank', 'ticker', 'name', 'return_5d'])
        writer.writeheader()
        writer.writerows(picks)
    print('V3 shadow factor-ablation complete; production files unchanged')
    print('Selection days:', len(set(p['date'] for p in picks)), 'picks:', len(picks), 'skipped:', len(skipped))
    for strategy in strategies:
        print(strategy, 'Top20:', report[strategy]['all']['top20'])
    print('Results:', OUT.relative_to(ROOT), CSV.relative_to(ROOT))


if __name__ == '__main__':
    main()
