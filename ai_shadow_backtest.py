#!/usr/bin/env python3
"""Read-only V1 vs V3 shadow experiment. No production files or workflow changes.
Same tech-universe definition, selection dates, 20 picks/market, entry and exit
accounting. V1 picks are the RECORDED picks; never reconstruct missing V1 dates.
"""
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data/ai_shadow_test.json'
CSV = ROOT / 'data/ai_shadow_test.csv'
START = '2026-09-24'
MARKETS = ('twse', 'tpex')
STRATEGIES = ('V1', 'A', 'B', 'C', 'A_RS', 'A_VOLUME', 'A_HEAT', 'A_PLUS', 'C_FLOW', 'C_TREND', 'C_SECTOR')
DEFAULT_CODES = {'24', '25', '26', '27', '28', '29', '30', '31', '32'}


def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def number(v):
    try:
        n = float(str(v).replace(',', ''))
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def percent(a, b):
    return 100 * (b / a - 1) if a is not None and b is not None and a > 0 else None


def stats(values):
    v = [x for x in values if x is not None and math.isfinite(x)]
    return {'samples': len(v), 'avg_return': round(mean(v), 4) if v else None,
            'median_return': round(median(v), 4) if v else None,
            'win_rate': round(100 * sum(x > 0 for x in v) / len(v), 2) if v else None,
            'worst_return': round(min(v), 4) if v else None}


def percentile(pool, field):
    vals = sorted((r[field], r['ticker']) for r in pool if r.get(field) is not None)
    ranks = {t: 100 * i / max(1, len(vals) - 1) for i, (_, t) in enumerate(vals)}
    for r in pool:
        r[field + '_rank'] = ranks.get(r['ticker'], 0)


def tech_universe(master):
    """Same eligibility union as scripts/tech_universe.py, without external deps."""
    config = load(ROOT / 'config.json')
    sectors = load(ROOT / 'data/sectors.json').get('sectors', [])
    sec = {str(x.get('ticker')) for s in sectors for x in s.get('stocks', []) if isinstance(x, dict)}
    supply = {str(t) for t in config.get('tech_supply_chain_tickers', [])}
    exclude = {str(t) for t in config.get('tech_exclude_tickers', [])}
    codes = {str(x) for x in config.get('tech_industry_codes', [])} or DEFAULT_CODES
    names = {str(x) for x in config.get('tech_industries', [])}
    return {str(t) for t, m in master.items()
            if re.fullmatch(r'\d{4}', str(t)) and isinstance(m, dict)
            and m.get('market') in MARKETS and str(t) not in exclude
            and (str(m.get('industry') or '').strip() in codes
                 or str(m.get('industry') or '').strip() in names
                 or str(t) in sec or str(t) in supply)}


def price_at(snapshots, index, ticker):
    if index < 0 or index >= len(snapshots):
        return None
    q = snapshots[index][1].get(ticker, {})
    return number(q.get('price')) if isinstance(q, dict) else None


def last_valid_price(snapshots, index, ticker):
    # Exactly V1: use latest available price on or before target date.
    for j in range(index, -1, -1):
        p = price_at(snapshots, j, ticker)
        if p is not None and p > 0:
            return p
    return None


def ma_at(snapshots, index, ticker, window):
    prices = []
    for j in range(index, -1, -1):
        p = price_at(snapshots, j, ticker)
        if p is not None and p > 0:
            prices.append(p)
        if len(prices) == window:
            return mean(prices)
    return None


def exits(snapshots, idx, ticker, entry):
    """Match scripts/update_ai_backtest.py: close-triggered exits, up to day 10."""
    found = {}
    for day in range(idx + 1, min(idx + 10, len(snapshots) - 1) + 1):
        close = price_at(snapshots, day, ticker)
        if close is None or close <= 0:
            continue
        for n in (10, 20):
            key = 'ma' + str(n)
            avg = ma_at(snapshots, day, ticker, n)
            if key not in found and avg is not None and close < avg:
                found[key] = (day, close)
        for n in (5, 10):
            key = 'stop' + str(n)
            if key not in found and close <= entry * (1 - n / 100):
                found[key] = (day, close)
    return found


def evaluate(snapshots, idx, ticker, entry):
    result = {}
    found = exits(snapshots, idx, ticker, entry)
    for days in (5, 10):
        mature = idx + days < len(snapshots)
        base = last_valid_price(snapshots, idx + days, ticker) if mature else None
        for key in ('baseline', 'ma10', 'ma20', 'stop5', 'stop10'):
            exit_day, exit_price = found.get(key, (None, None))
            price = exit_price if mature and exit_day is not None and exit_day <= idx + days else base
            result[f'{key}_{days}d'] = percent(entry, price) if mature else None
            result[f'{key}_{days}d_status'] = 'pending' if not mature else ('complete' if price is not None else 'unavailable')
    return result


def main():
    master = load(ROOT / 'data/master.json').get('stocks', {})
    universe = tech_universe(master)
    if len(universe) < 500:
        raise SystemExit(f'ERROR: V1 technology universe not found or too small: {len(universe)}')
    sectors_raw = load(ROOT / 'data/sectors.json').get('sectors', [])
    ticker_sectors = defaultdict(list)
    for sec in sectors_raw:
        label = str(sec.get('name') or sec.get('id') or '').strip()
        if not label:
            continue
        for item in sec.get('stocks', []):
            if isinstance(item, dict) and item.get('ticker') is not None:
                ticker_sectors[str(item['ticker'])].append(label)
    snapshots = []
    for path in sorted((ROOT / 'data/history/market').glob('*.json')):
        stocks = load(path).get('stocks', {})
        if isinstance(stocks, dict) and stocks:
            snapshots.append((path.stem, stocks))
    dates = [x[0] for x in snapshots]
    index = {d: i for i, d in enumerate(dates)}
    inst = {}
    for path in (ROOT / 'data/history/institutional').glob('*.json'):
        d = load(path)
        inst[path.stem] = {**d.get('twse', {}), **d.get('tpex', {})}
    original = defaultdict(list)
    for row in load(ROOT / 'data/ai_backtest.json').get('records', []):
        if row.get('market') in MARKETS:
            original[(row.get('selection_date'), row['market'])].append(row)
    if not original:
        raise SystemExit('ERROR: no recorded V1 selection history')
    for rows in original.values():
        rows.sort(key=lambda r: int(r.get('rank') or 999))

    picks, daily_results, coverage = [], [], []
    for day in dates:
        if day < START:
            continue
        i = index[day]
        for exchange in MARKETS:
            baseline = original.get((day, exchange), [])
            if i < 20:
                coverage.append({'date': day, 'market': exchange, 'status': 'skipped', 'reason': 'needs 20 previous market days', 'v1_available': bool(baseline)})
                continue
            # V1 tech stock definition and V1 market availability: no sectors-only cap.
            today = snapshots[i][1]
            candidate_tickers = sorted(t for t in universe if t in today and today[t].get('market') == exchange)
            if len(candidate_tickers) < 20:
                coverage.append({'date': day, 'market': exchange, 'status': 'skipped', 'reason': 'fewer than 20 V1-universe candidates', 'count': len(candidate_tickers)})
                continue
            five = dates[max(0, i - 4):i + 1]
            pool = []
            for ticker in candidate_tickers:
                q = today[ticker]
                price = number(q.get('price'))
                if price is None or price <= 0:
                    continue
                close = [price_at(snapshots, j, ticker) for j in range(i - 20, i + 1)]
                vol = [number(snapshots[j][1].get(ticker, {}).get('volume')) for j in range(i - 5, i + 1)]
                r5 = percent(close[-6], price) if close[-6] else None
                r10 = percent(close[-11], price) if close[-11] else None
                r20 = percent(close[0], price) if close[0] else None
                ma10 = mean(close[-10:]) if all(v is not None and v > 0 for v in close[-10:]) else None
                ma20 = mean(close[-20:]) if all(v is not None and v > 0 for v in close[-20:]) else None
                breakout = percent(max(close[:-1]), price) if all(v is not None and v > 0 for v in close[:-1]) else None
                ratio = vol[-1] / mean(vol[:-1]) if all(v is not None for v in vol) and mean(vol[:-1]) > 0 else None
                volume_confirm = max(0, 100 - abs(ratio - 1.7) * 65) if ratio is not None else None
                turnover = 0.0
                flow = 0.0
                healthy = True
                daily_flow_ratios = []
                for j, d in enumerate(five):
                    row = inst.get(d, {}).get(ticker)
                    daily = snapshots[index[d]][1].get(ticker, {})
                    p = number(daily.get('price'))
                    t = number(daily.get('turnover'))
                    if not isinstance(row, dict) or p is None or t is None:
                        healthy = False
                        break
                    turnover += t
                    net_amount = sum(number(row.get(k)) or 0 for k in ('foreign', 'trust', 'dealer')) * p
                    flow += net_amount
                    daily_flow_ratios.append(net_amount / t * 100 if t > 0 else None)
                flow_metric = flow / turnover * 100 if healthy and turnover > 0 else None
                # Flow acceleration compares recent 2 days with prior 3, normalized by turnover.
                flow_accel = (mean(daily_flow_ratios[-2:]) - mean(daily_flow_ratios[:3])
                              if healthy and len(daily_flow_ratios) == 5
                              and all(v is not None for v in daily_flow_ratios) else None)
                # Slope checks use only prices known at selection close.
                ma10_prev5 = (mean(close[-15:-5]) if all(v is not None and v > 0 for v in close[-15:-5]) else None)
                ma20_prev1 = (mean(close[-21:-1]) if all(v is not None and v > 0 for v in close[-21:-1]) else None)
                trend_slope = (int(ma10 is not None and ma20 is not None
                                   and ma10_prev5 is not None and ma20_prev1 is not None
                                   and price > ma10 > ma20 and ma10 > ma10_prev5
                                   and ma20 > ma20_prev1))
                heat = (max(0, r5 - 15) * 1.5 + max(0, percent(ma20, price) - 18)) if r5 is not None and ma20 else 0
                heat_smooth = (max(0, r5 - 10) ** 1.2 * .7 + max(0, percent(ma20, price) - 13) * 1.1) if r5 is not None and ma20 else 0
                pool.append({'ticker': ticker, 'name': q.get('name', ''), 'entry': price,
                             'r5': r5, 'r10': r10, 'r20': r20, 'flow': flow_metric,
                             'breakout': breakout, 'volume_ratio': ratio, 'volume_confirm': volume_confirm,
                             'trend': int(ma10 is not None and ma20 is not None and price > ma10 > ma20),
                             'overheat': heat, 'heat_smooth': heat_smooth,
                             'flow_accel': flow_accel, 'trend_slope': trend_slope,
                             'sectors': ticker_sectors.get(ticker, [])})
            if len(pool) < 20:
                coverage.append({'date': day, 'market': exchange, 'status': 'skipped', 'reason': 'fewer than 20 priced candidates'})
                continue
            for field in ('flow', 'r5', 'r10', 'r20', 'breakout', 'volume_ratio', 'volume_confirm', 'flow_accel'):
                percentile(pool, field)
            r20_median = median([r['r20'] for r in pool if r['r20'] is not None]) if any(r['r20'] is not None for r in pool) else 0
            for row in pool:
                row['rs20'] = row['r20'] - r20_median if row['r20'] is not None else None
            percentile(pool, 'rs20')
            # Sector strength: equally-weighted 5-day return of members in this
            # day's eligible pool. Multiple sector membership uses strongest sector.
            sector_returns = defaultdict(list)
            for item in pool:
                if item['r5'] is not None:
                    for sector in item['sectors']:
                        sector_returns[sector].append(item['r5'])
            sector_strength = {s: mean(vals) for s, vals in sector_returns.items() if len(vals) >= 3}
            sector_rank = {s: v for s, v in sector_strength.items()}
            for row in pool:
                row['sector_strength'] = (max((sector_rank[s] for s in row['sectors'] if s in sector_rank),
                                              default=None))
            percentile(pool, 'sector_strength')
            for row in pool:
                f, b, r10, r5 = (row[k + '_rank'] for k in ('flow', 'breakout', 'r10', 'r5'))
                trend = 10 * row['trend']
                row['score_A'] = .45*f + .25*b + .20*r10 + trend - row['overheat']
                row['score_B'] = .55*f + .20*r5 + .15*row['volume_ratio_rank'] + .10*row['r20_rank'] - 2*row['overheat']
                row['score_C'] = .35*f + .25*r5 + .20*b + .10*r10 + trend - 1.5*row['overheat']
                row['score_A_RS'] = .40*f + .25*b + .20*r10 + .05*row['rs20_rank'] + trend - row['overheat']
                row['score_A_VOLUME'] = .40*f + .25*b + .20*r10 + .05*row['volume_confirm_rank'] + trend - row['overheat']
                row['score_A_HEAT'] = .45*f + .25*b + .20*r10 + trend - row['heat_smooth']
                row['score_A_PLUS'] = .35*f + .20*b + .15*r10 + .10*row['rs20_rank'] + .10*row['volume_confirm_rank'] + trend - row['heat_smooth']
                # One-factor-at-a-time experiments relative to C. Keep original C untouched.
                # Center percentile additions around 50 to avoid inflating scores.
                row['score_C_FLOW'] = row['score_C'] + .10 * (row['flow_accel_rank'] - 50)
                row['score_C_TREND'] = row['score_C'] + 10 * (row['trend_slope'] - row['trend'])
                row['score_C_SECTOR'] = row['score_C'] + (.10 * (row['sector_strength_rank'] - 50)
                                                             if row['sector_strength'] is not None else 0)
            paired = len(baseline) >= 20
            coverage.append({'date': day, 'market': exchange, 'status': 'evaluated',
                             'v1_available': paired, 'pool_size': len(pool),
                             'five_day_mature': i + 5 < len(dates), 'ten_day_mature': i + 10 < len(dates)})
            for strategy in STRATEGIES:
                if strategy == 'V1':
                    if not paired:
                        continue
                    chosen = [{'ticker': str(x['ticker']), 'name': x.get('name', ''),
                               'entry': number(x.get('entry_price')), 'record': x} for x in baseline[:20]]
                else:
                    chosen = sorted(pool, key=lambda r: (-r['score_' + strategy], r['ticker']))[:20]
                evaluated = []
                for rank, row in enumerate(chosen, 1):
                    entry = row['entry']
                    if entry is None or entry <= 0:
                        continue
                    # V1 stored results take precedence for exact parity; V3 uses identical exit function.
                    returns = evaluate(snapshots, i, row['ticker'], entry)
                    if strategy == 'V1':
                        source = row['record']
                        for days in (5, 10):
                            for tag, key in (('baseline', 'baseline_'), ('ma10', ''), ('ma20', 'ma20_'), ('stop5', 'stop5_'), ('stop10', 'stop10_')):
                                k = f'{key}return_{days}d'
                                returns[f'{tag}_{days}d'] = number(source.get(k)) if source.get(f'{key}status_{days}d') == 'complete' else None
                    record = {'date': day, 'market': exchange, 'strategy': strategy, 'rank': rank,
                              'ticker': row['ticker'], 'name': row['name'], 'entry_price': entry,
                              'score': (number(row.get('score_' + strategy)) if strategy != 'V1'
                                        else number(row['record'].get('score'))),
                              'paired_with_v1': paired, **returns}
                    picks.append(record)
                    evaluated.append(record)
                for top in (5, 10, 20):
                    block = {'date': day, 'market': exchange, 'strategy': strategy, 'top': top,
                             'paired_with_v1': paired, 'pool_size': len(pool)}
                    for days in (5, 10):
                        for tag in ('baseline', 'ma10', 'ma20', 'stop5', 'stop10'):
                            block[f'{tag}_{days}d'] = stats([r[f'{tag}_{days}d'] for r in evaluated[:top]])
                    daily_results.append(block)
    if not picks:
        raise SystemExit('ERROR: no shadow selections generated')
    summary = {}
    paired_summary = {}
    for strategy in STRATEGIES:
        summary[strategy] = {}
        paired_summary[strategy] = {}
        for market_name in (*MARKETS, 'all'):
            summary[strategy][market_name] = {}
            paired_summary[strategy][market_name] = {}
            for top in (5, 10, 20):
                rows = [r for r in picks if r['strategy'] == strategy and r['rank'] <= top
                        and (market_name == 'all' or r['market'] == market_name)]
                for destination, subset in ((summary, rows), (paired_summary, [r for r in rows if r['paired_with_v1']])):
                    block = {}
                    for days in (5, 10):
                        for tag in ('baseline', 'ma10', 'ma20', 'stop5', 'stop10'):
                            block[f'{tag}_{days}d'] = stats([r[f'{tag}_{days}d'] for r in subset])
                    destination[strategy][market_name][f'top{top}'] = block
    # Preserve every day's ranked picks, including pending dates, in the JSON artifact.
    # This is additive only: scoring, evaluation, summaries and production stay unchanged.
    daily_picks = {}
    for r in picks:
        daily_picks.setdefault(r['date'], {}).setdefault(r['market'], {}).setdefault(r['strategy'], []).append({
            'rank': r['rank'], 'ticker': r['ticker'], 'name': r['name'],
            'score': round(r['score'], 4) if r['score'] is not None else None,
            'entry_price': r['entry_price'], 'paired_with_v1': r['paired_with_v1'],
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        'method': 'V1 same tech-universe rule, recorded V1 selection dates, same close-entry and V1 exit accounting',
        'universe_definition': 'scripts/tech_universe.py equivalent: master industry + sectors + supply-chain whitelist - exclusions',
        'current_master_universe_size': len(universe),
        'strategies': list(STRATEGIES), 'summary': summary, 'paired_summary': paired_summary,
        'daily': daily_results, 'daily_picks': daily_picks, 'coverage': coverage,
        'selection_days': len(set(r['date'] for r in picks)),
        'limitations': ['Historical universe membership not archived: current master/config/sectors used for past dates (survivorship bias)',
                        'V1 dates without saved selections cannot be reconstructed; paired_summary uses only recorded V1 dates',
                        '20 prior daily prices needed for momentum, missing factors rank as zero',
                        'Same-day close execution with same-day institutional data is not realistically guaranteed',
                        'V3 has no TDCC holder factor because its strategies do not use it; universe still matches V1 definition',
                        'Overlapping returns; no transaction costs or slippage',
                        'C_FLOW uses the latest five market dates, not five separately validated healthy institutional dates',
                        'C_SECTOR uses current sectors.json membership, not archived historical sector membership; sectors with fewer than 3 priced members are excluded',
                        'C_TREND checks MA10 against five trading days ago and MA20 against one trading day ago']
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['date', 'market', 'strategy', 'rank', 'ticker', 'name', 'score', 'entry_price', 'paired_with_v1']
    fields += [f'{tag}_{days}d' for days in (5, 10) for tag in ('baseline', 'ma10', 'ma20', 'stop5', 'stop10')]
    with CSV.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(picks)
    print('V1-matched V3 shadow complete; NO production files changed')
    print('Universe:', len(universe), 'Selection days:', len(set(r['date'] for r in picks)),
          'picks:', len(picks), 'evaluated dates:', sum(r['status'] == 'evaluated' for r in coverage))
    for strategy in STRATEGIES:
        print(strategy, 'paired fixed 5d top20:', paired_summary[strategy]['all']['top20']['baseline_5d'])
    print('Outputs:', OUT.relative_to(ROOT), CSV.relative_to(ROOT))


if __name__ == '__main__':
    main()
