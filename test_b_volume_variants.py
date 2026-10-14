#!/usr/bin/env python3
"""B strategy ablation comparison with explicit next-open execution. Run using existing B Volume Backtest workflow.
Only writes data/b_volume_comparison.{json,csv}; never modifies production code.
"""
import ast
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'ai_shadow_backtest.py'
TMP = ROOT / '_temp_b_volume_shadow.py'
OUTPUT = ROOT / 'data/b_volume_comparison.json'
CSV = ROOT / 'data/b_volume_comparison.csv'
BASE = 'BAL_MA_SLOPE_RANK_HEAT25_30'
VARIANTS = ('B_VOL_5D_15', 'B_VOL_5D_20D', 'B_CANDLE_VOLUME', 'B_CANDLE_VOLUME_FLOW', 'B_FLOW_PERSIST', 'B_LESS_MOMENTUM', 'B_COMBINED', 'B_COMBINED_GATE')


def patch_source(src):
    tree = ast.parse(src)
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'STRATEGIES' for t in n.targets))
    old = ast.literal_eval(assignment.value)
    if BASE not in old:
        raise RuntimeError('Original B strategy missing')
    lines = src.splitlines(keepends=True)
    lines[assignment.lineno - 1:assignment.end_lineno] = [
        'STRATEGIES = ' + repr(tuple(old) + VARIANTS) + '\n']
    src = ''.join(lines)

    # Inject once at main() scope, before candidate loops. Load K-bars once, not per stock.
    main_anchor = 'def main():\n'
    if src.count(main_anchor) != 1:
        raise RuntimeError('Cannot find shadow main()')
    setup = '''def main():
    # Date-indexed historical OHLC, from the repository's existing daily_k files.
    # Only historical dates matching the selection day are used.
    daily_k = {}
    for kpath in (ROOT / 'data/daily_k').glob('*.json'):
        kd = load(kpath)
        ticker_k = str(kd.get('ticker') or kpath.stem)
        bars = kd.get('bars', [])
        if isinstance(bars, list):
            daily_k[ticker_k] = {
                str(bar.get('time') or bar.get('date')): bar
                for bar in bars if isinstance(bar, dict)
                and (bar.get('time') or bar.get('date'))
            }
    b_volume_diagnostics = {
        'candidates': 0, 'valid_candles': 0,
        'missing_candles': 0, 'invalid_candles': 0,
        'valid_volume_ratios': 0, 'b3_penalty_changed': 0,
        'b4_penalty_changed': 0, 'institution_available': 0,
        'institution_buy': 0, 'institution_sell': 0,
    }
'''
    src = src.replace(main_anchor, setup, 1)
    anchor = '                # All experimental formulas are identical across TWSE and TPEx.\n'
    if src.count(anchor) != 1:
        raise RuntimeError('Shadow score insertion point changed')
    inject = '''                # Original B, B1, B2: exact same formulas as previous volume test.
                vr5 = row['volume_ratio']
                base_b = row['score_BAL_MA_SLOPE_RANK_HEAT25_30']
                new_5d = (min(8.0, 2.0 * max(0.0, vr5 - 1.5))
                          if vr5 is not None else mild_volume_penalty)
                row['score_B_VOL_5D_15'] = base_b + mild_volume_penalty - new_5d
                prior20 = [number(snapshots[j][1].get(row['ticker'], {}).get('volume'))
                           for j in range(i - 20, i)]
                vr20 = (row['daily_volume'] / mean(prior20)
                        if row['daily_volume'] is not None
                        and len(prior20) == 20
                        and all(x is not None and x >= 0 for x in prior20)
                        and mean(prior20) > 0 else None)
                p5 = min(4.0, 2.0 * max(0.0, vr5 - 1.5)) if vr5 is not None else 0.0
                p20 = min(6.0, 2.0 * max(0.0, vr20 - 2.0)) if vr20 is not None else 0.0
                new_both = (p5 + p20 if vr5 is not None and vr20 is not None
                            else mild_volume_penalty)
                row['score_B_VOL_5D_20D'] = base_b + mild_volume_penalty - new_both

                # B3: volume risk depends on where the stock CLOSES in its daily range.
                # A positive candle closing near the high is not treated as distribution.
                b_volume_diagnostics['candidates'] += 1
                candle = daily_k.get(row['ticker'], {}).get(day)
                valid = False
                if candle is None:
                    b_volume_diagnostics['missing_candles'] += 1
                else:
                    op = number(candle.get('open'))
                    hi = number(candle.get('high'))
                    lo = number(candle.get('low'))
                    cl = number(candle.get('close'))
                    valid = (all(x is not None for x in (op, hi, lo, cl))
                             and hi > lo and lo <= op <= hi and lo <= cl <= hi
                             and abs(cl - row['entry']) <= max(.01, row['entry'] * .001))
                    b_volume_diagnostics['valid_candles' if valid else 'invalid_candles'] += 1
                penalty_b3 = mild_volume_penalty
                if valid and vr5 is not None and vr20 is not None:
                    b_volume_diagnostics['valid_volume_ratios'] += 1
                    loc = (cl - lo) / (hi - lo)
                    positive_day = cl > op and (number(snapshots[i][1].get(row['ticker'], {}).get('change_pct')) or 0) > 0
                    if loc >= .80 and positive_day:
                        factor = 0.0
                    elif loc >= .60 and cl > op:
                        factor = .25
                    elif loc >= .40:
                        factor = .50
                    elif loc >= .25:
                        factor = .75
                    else:
                        factor = 1.0
                    penalty_b3 = new_both * factor
                    if abs(penalty_b3 - mild_volume_penalty) > 1e-9:
                        b_volume_diagnostics['b3_penalty_changed'] += 1
                row['score_B_CANDLE_VOLUME'] = base_b + mild_volume_penalty - penalty_b3

                # B4: use the SAME historical institutional source and columns
                # as ai_shadow_backtest.py: foreign/trust/dealer (signed shares).
                institution = inst.get(day, {}).get(row['ticker'])
                net = None
                if isinstance(institution, dict):
                    parts = [number(institution.get(k)) for k in ('foreign', 'trust', 'dealer')]
                    if all(x is not None for x in parts):
                        net = sum(parts)
                        b_volume_diagnostics['institution_available'] += 1
                        b_volume_diagnostics['institution_buy' if net > 0 else 'institution_sell'] += 1
                penalty_b4 = penalty_b3
                if valid and vr5 is not None and vr20 is not None and net is not None:
                    if net > 0 and loc >= .80 and positive_day:
                        penalty_b4 = 0.0
                    elif net < 0 and loc <= .40:
                        penalty_b4 = min(12.0, penalty_b3 * 1.25)
                    if abs(penalty_b4 - penalty_b3) > 1e-9:
                        b_volume_diagnostics['b4_penalty_changed'] += 1
                row['score_B_CANDLE_VOLUME_FLOW'] = base_b + mild_volume_penalty - penalty_b4

                # Reconstruct flow state from five historical days; missing parts are not zero.
                ratios = []
                for fd in five:
                    ir = inst.get(fd, {}).get(row['ticker'], {})
                    quote = snapshots[index[fd]][1].get(row['ticker'], {})
                    parts = [number(ir.get(k)) for k in ('foreign', 'trust', 'dealer')]
                    px, amount = number(quote.get('price')), number(quote.get('turnover'))
                    if all(v is not None for v in parts) and px and amount and amount > 0:
                        ratios.append(sum(parts) * px / amount * 100)
                flow_ok = len(ratios) == 5
                if flow_ok:
                    recent, previous = mean(ratios[-2:]), mean(ratios[:3])
                    accel = recent - previous
                    state = (1.0 if recent > 0 and previous > 0 and accel > 0 else
                             .75 if recent > 0 and previous <= 0 else
                             .25 if recent <= 0 and accel > 0 else 0.0)
                    # Replace old 10 points by 5 acceleration-state + 5 persistence points.
                    new_flow = .05 * row['flow_accel_rank'] * state + sum(v > 0 for v in ratios)
                    delta_flow = new_flow - .10 * row['flow_accel_rank']
                else:
                    delta_flow = -.10 * row['flow_accel_rank']
                row['score_B_FLOW_PERSIST'] = base_b + delta_flow
                # Transfer 10 momentum points to persistence, no market-cap factor added.
                delta_momentum = (-.05 * row['r5_rank'] - .05 * row['r10_rank']
                                  + (2 * sum(v > 0 for v in ratios) if flow_ok else 0))
                row['score_B_LESS_MOMENTUM'] = base_b + delta_momentum
                row['score_B_COMBINED'] = (base_b + mild_volume_penalty - penalty_b3
                                           + delta_flow + delta_momentum)
                row['score_B_COMBINED_GATE'] = row['score_B_COMBINED']
                row['b_eligible'] = (flow_ok and row['flow'] is not None and row['flow'] > 0
                                    and row['trend'] and valid
                                    and all(row.get(k) is not None for k in
                                            ('r5', 'r10', 'breakout', 'volume_ratio')))

'''
    src = src.replace(anchor, inject + anchor, 1)
    src = src.replace("OUT = ROOT / 'data/ai_shadow_test.json'",
                      "OUT = ROOT / 'data/_temp_b_volume_shadow.json'")
    src = src.replace("CSV = ROOT / 'data/ai_shadow_test.csv'",
                      "CSV = ROOT / 'data/_temp_b_volume_shadow.csv'")
    # Append diagnostics into shadow JSON via an insertion before its final write.
    marker = "'selection_days': len(set(r['date'] for r in picks)),"
    if src.count(marker) != 1:
        raise RuntimeError('Shadow output schema changed')
    src = src.replace(marker, marker + " 'b_volume_diagnostics': b_volume_diagnostics,", 1)
    chosen_anchor = "chosen = sorted(pool, key=lambda r: (-r['score_' + strategy], r['ticker']))[:20]"
    if src.count(chosen_anchor) != 1:
        raise RuntimeError('Shadow selection point changed')
    src = src.replace(chosen_anchor, "chosen = sorted([r for r in pool if strategy != 'B_COMBINED_GATE' or r['b_eligible']], key=lambda r: (-r['score_' + strategy], r['ticker']))[:20]")
    compile(src, str(TMP), 'exec')
    return src


def next_open_test(daily_picks, strategies):
    """Fixed 5/10-session holds, signal close -> next session open.
    Missing OHLC is unavailable, never replaced by a same-day close.
    Costs are explicit simulation assumptions, configurable by environment.
    """
    import math
    import os
    from statistics import mean, median
    commission = float(os.environ.get('B_COMMISSION_BPS', '14.25')) / 10000
    tax = float(os.environ.get('B_SELL_TAX_BPS', '30')) / 10000
    slip = float(os.environ.get('B_SLIPPAGE_BPS', '10')) / 10000
    if not all(math.isfinite(v) and 0 <= v < .1 for v in (commission, tax, slip)):
        raise ValueError('Invalid cost assumptions')
    snapshots = {}
    for p in sorted((ROOT / 'data/history/market').glob('*.json')):
        snapshots[p.stem] = json.loads(p.read_text()).get('stocks', {})
    dates = sorted(snapshots)
    ix = {d: i for i, d in enumerate(dates)}
    bars = {}
    for p in (ROOT / 'data/daily_k').glob('*.json'):
        obj = json.loads(p.read_text())
        bars[str(obj.get('ticker') or p.stem)] = {
            str(b.get('time') or b.get('date')): b for b in obj.get('bars', [])}

    def valid_bar(ticker, day):
        b = bars.get(ticker, {}).get(day)
        if not b:
            return None
        try:
            o,h,l,c,v = [float(b[k]) for k in ('open','high','low','close','volume')]
            reference = float(snapshots[day][ticker]['price'])
            if not all(math.isfinite(x) for x in (o,h,l,c,v,reference)):
                return None
            if not (0 < l <= min(o,c) <= max(o,c) <= h and v > 0):
                return None
            if abs(c-reference) > max(.01, reference*.001):
                return None
            return o,h,l,c
        except (KeyError,TypeError,ValueError):
            return None

    records = []
    for day, markets in sorted(daily_picks.items()):
        i = ix[day]
        for market, variants in markets.items():
            for strategy in strategies:
                for pick in variants.get(strategy, []):
                    for horizon in (5,10):
                        r = dict(selection_date=day, market=market, strategy=strategy,
                                 ticker=pick['ticker'], rank=pick['rank'], horizon=horizon,
                                 status='pending', net_return=None, gross_return=None)
                        records.append(r)
                        if i+horizon >= len(dates):
                            continue
                        entry_day, exit_day = dates[i+1], dates[i+horizon]
                        r.update(entry_date=entry_day, exit_date=exit_day)
                        first, last = valid_bar(r['ticker'], entry_day), valid_bar(r['ticker'], exit_day)
                        if not first or not last:
                            r['status'] = 'missing_or_mismatched_ohlc'
                            continue
                        # Conservative: a one-price session is not assumed executable.
                        if first[1] == first[2] or last[1] == last[2]:
                            r['status'] = 'one_price_session_unverified'
                            continue
                        entry, end = first[0], last[3]
                        r.update(status='complete', entry_price=entry, exit_price=end,
                                 gross_return=100*(end/entry-1),
                                 net_return=100*(end*(1-slip)*(1-commission-tax)/
                                                 (entry*(1+slip)*(1+commission))-1))
    def stats(rows):
        done = [r for r in rows if r['status']=='complete']
        vals = [r['net_return'] for r in done]
        mature = [r for r in rows if r['status']!='pending']
        return dict(signals=len(rows), mature_signals=len(mature), samples=len(vals),
                    coverage_pct=round(100*len(vals)/len(mature),2) if mature else None,
                    avg_return=round(mean(vals),4) if vals else None,
                    median_return=round(median(vals),4) if vals else None,
                    win_rate=round(100*sum(v>0 for v in vals)/len(vals),2) if vals else None,
                    worst_trade=round(min(vals),4) if vals else None)
    summary = {}
    for st in strategies:
        summary[st] = {m: {f'top{n}_{h}d': stats([r for r in records if
            r['strategy']==st and (m=='all' or r['market']==m) and
            r['rank']<=n and r['horizon']==h]) for n in (5,10,20) for h in (5,10)}
            for m in ('twse','tpex','all')}
    # Strict paired comparisons: include a day/market only if BOTH lists have
    # complete fills. Do not compare cherry-picked available stocks to missing ones.
    comparisons = {}
    for st in strategies:
        if st == BASE:
            continue
        comparisons[st] = {}
        for h in (5,10):
            groups = {}
            for r in records:
                if r['horizon']==h and r['strategy'] in (BASE,st):
                    groups.setdefault((r['selection_date'],r['market']),{}).setdefault(r['strategy'],[]).append(r)
            units = []
            for (day,m), pair in sorted(groups.items()):
                if set(pair)!={BASE,st} or any(any(r['status']!='complete' for r in v) for v in pair.values()):
                    continue
                b,c = (mean(r['net_return'] for r in pair[k]) for k in (BASE,st))
                units.append(dict(date=day,market=m,base=b,variant=c,difference_pp=c-b))
            comparisons[st][f'{h}d'] = dict(units=len(units),
                avg_difference_pp=mean(u['difference_pp'] for u in units) if units else None,
                per_date_market=units)
    return dict(method='Next trading session open to 5th/10th session close, fixed holding only',
                assumptions=dict(commission_bps_each_side=commission*10000,
                                 sell_tax_bps=tax*10000,slippage_bps_each_side=slip*10000),
                summary=summary, paired_comparisons=comparisons, records=records,
                limitations=['Current universe creates survivorship bias',
                    'Incomplete daily_k coverage can bias unpaired summaries; inspect coverage',
                    'One-price sessions excluded, other execution capacity not verified',
                    'Overlapping signals are not independent trades or a portfolio equity curve',
                    'No out-of-sample claim; prospective signals must be frozen separately',
                    'Legacy summary uses same-close entry and no costs; never mix with next_open_test'])


def main():
    if not SOURCE.exists():
        raise SystemExit('Missing ai_shadow_backtest.py')
    if TMP.exists():
        raise SystemExit(f'Temporary file already exists: {TMP}')
    src = patch_source(SOURCE.read_text(encoding='utf-8'))
    TMP.write_text(src, encoding='utf-8')
    try:
        subprocess.run([sys.executable, str(TMP)], cwd=ROOT, check=True)
        raw = json.loads((ROOT / 'data/_temp_b_volume_shadow.json').read_text(encoding='utf-8'))
        diag = raw.get('b_volume_diagnostics') or {}
        total = diag.get('candidates', 0)
        valid = diag.get('valid_candles', 0)
        coverage = valid / total if total else 0
        print('CANDLE / INSTITUTION DIAGNOSTICS:', json.dumps(diag, ensure_ascii=False), flush=True)
        print(f'Candle coverage: {valid}/{total} = {coverage:.1%}', flush=True)
        if coverage < .70:
            print(f'WARNING: candle coverage {coverage:.1%}; missing candles keep original B volume penalty')
        if not diag.get('b3_penalty_changed'):
            raise RuntimeError('B3 never changed any penalty; refusing misleading backtest')
        if not diag.get('institution_available'):
            raise RuntimeError('B4 has no valid institutional observations')
        if not diag.get('b4_penalty_changed'):
            raise RuntimeError('B4 never changed any penalty; refusing misleading backtest')
        strategies = (BASE,) + VARIANTS
        summary = {k: raw.get('summary', {}).get(k) for k in strategies}
        for strategy, value in summary.items():
            if not value:
                raise RuntimeError(f'Missing backtest summary for {strategy}')
        result = {
            'description': 'B baseline vs volume, flow persistence, momentum reweighting and gated variants',
            'source': 'ai_shadow_backtest.py',
            'strategies': list(strategies),
            'selection_days': raw.get('selection_days'),
            'diagnostics': {**diag, 'candle_coverage_pct': round(coverage * 100, 2)},
            'summary': summary,
            'paired_summary': {k: raw.get('paired_summary', {}).get(k) for k in strategies},
            'daily_picks': {
                day: {market: {k: values.get(k, []) for k in strategies}
                      for market, values in markets.items()}
                for day, markets in raw.get('daily_picks', {}).items()},
            'variant_rules': {
                BASE: 'Unchanged production B baseline',
                'B_FLOW_PERSIST': 'Replace original 10 acceleration points with 5 state-gated acceleration + 5 buy-day persistence points',
                'B_LESS_MOMENTUM': 'Reduce r5 and r10 weights by 5 points each; add up to 10 points for five buy days',
                'B_COMBINED': 'Candle volume + flow persistence + reduced momentum',
                'B_COMBINED_GATE': 'Combined; require complete five-day institutional fields, positive net flow, bullish trend, valid candle and price/volume factors; at most 20',
            },
            'notes': [
                'B/B1/B2 formulas unchanged; B3/B4 use same-date historical OHLC from data/daily_k',
                'B4 uses signed foreign+trust+dealer from historical institutional records',
                'Low candle coverage is exploratory only; missing candles retain B penalty, and gated universe differs',
                'Reconstructed universe and same-close entry can introduce bias; costs excluded',
            ],
        }
        result['next_open_test'] = next_open_test(result['daily_picks'], strategies)
        result['validation_status'] = ('insufficient_coverage_for_strategy_decision'
            if coverage < .70 or not any(
                b['units'] for v in result['next_open_test']['paired_comparisons'].values()
                for b in v.values()) else 'exploratory_in_sample_only')
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        with CSV.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['strategy', 'market', 'period', 'statistics_json'])
            for strategy in strategies:
                for market, block in (summary[strategy] or {}).items():
                    writer.writerow([strategy, market, 'all', json.dumps(block, ensure_ascii=False)])
            for strategy in strategies:
                for market, block in result['next_open_test']['summary'][strategy].items():
                    writer.writerow([strategy, market, 'next_open_after_costs', json.dumps(block, ensure_ascii=False)])
        print('VALIDATION:', result['validation_status'])
        print('SUCCESS:', OUTPUT, CSV)
        for strategy in strategies:
            block = (summary[strategy] or {}).get('all', {})
            print(strategy, 'Top20 5d:', block.get('top20', {}).get('baseline_5d', {}))
    finally:
        TMP.unlink(missing_ok=True)
        (ROOT / 'data/_temp_b_volume_shadow.json').unlink(missing_ok=True)
        (ROOT / 'data/_temp_b_volume_shadow.csv').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
