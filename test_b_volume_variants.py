#!/usr/bin/env python3
"""B/B1/B2/B3/B4 historical comparison. Run using existing B Volume Backtest workflow.
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
VARIANTS = ('B_VOL_5D_15', 'B_VOL_5D_20D', 'B_CANDLE_VOLUME', 'B_CANDLE_VOLUME_FLOW')


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
                    positive_day = cl > op and number(snapshots[i][1].get(row['ticker'], {}).get('change_pct')) > 0
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
    compile(src, str(TMP), 'exec')
    return src


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
            raise RuntimeError(f'Insufficient valid daily K coverage ({coverage:.1%} < 70%)')
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
            'description': 'Original B vs B1/B2/B3/B4, with verified daily_k OHLC',
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
            'notes': [
                'B/B1/B2 formulas unchanged; B3/B4 use same-date historical OHLC from data/daily_k',
                'B4 uses signed foreign+trust+dealer from historical institutional records',
                'Insufficient candle coverage or inactive variants cause a hard failure',
                'Reconstructed universe and same-close entry can introduce bias; costs excluded',
            ],
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        with CSV.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['strategy', 'market', 'period', 'statistics_json'])
            for strategy in strategies:
                for market, block in (summary[strategy] or {}).items():
                    writer.writerow([strategy, market, 'all', json.dumps(block, ensure_ascii=False)])
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
