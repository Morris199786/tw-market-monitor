#!/usr/bin/env python3
"""B volume-penalty A/B backtest; does not modify production strategy or website JSON.
Run from repository root: python test_b_volume_variants.py
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
VARIANTS = ('B_VOL_5D_15', 'B_VOL_5D_20D', 'B3_CANDLE_VOLUME', 'B4_CANDLE_VOLUME_FLOW')


def patch_source(src):
    # Keep the existing 36 strategies, append two independent experimental scores.
    tree = ast.parse(src)
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'STRATEGIES' for t in n.targets))
    old = ast.literal_eval(assignment.value)
    if BASE not in old:
        raise RuntimeError('B baseline missing in shadow strategy list')
    lines = src.splitlines(keepends=True)
    start, end = assignment.lineno - 1, assignment.end_lineno
    lines[start:end] = ['STRATEGIES = ' + repr(tuple(old) + VARIANTS) + '\n']
    src = ''.join(lines)
    init_anchor = '    snapshots = []\n'
    if src.count(init_anchor) != 1:
        raise RuntimeError('Cannot locate snapshot initialization')
    src = src.replace(init_anchor, "    # Only use historical OHLC on or before each simulated selection date.\n    ohlc_by_ticker = {}\n    for kpath in (ROOT / 'data/daily_k').glob('*.json'):\n        code = kpath.stem\n        obj = load(kpath)\n        bars = obj.get('bars', [])\n        if isinstance(bars, list):\n            ohlc_by_ticker[code] = {str(b.get('time')): b for b in bars if isinstance(b, dict)}\n    candle_coverage = {'available': 0, 'missing': 0, 'price_mismatch': 0,\n                       'invalid_range': 0, 'flow_available': 0, 'flow_missing': 0}\n" + init_anchor)
    anchor = '                # All experimental formulas are identical across TWSE and TPEx.\n'
    if src.count(anchor) != 1:
        raise RuntimeError('Cannot locate score insertion point; shadow source changed')
    inject = '''                # Volume-only A/B: same exact baseline score and all other factors.
                # The shadow engine's volume_ratio uses TODAY / PREVIOUS FIVE sessions.
                vr5 = row['volume_ratio']
                base_b = row['score_BAL_MA_SLOPE_RANK_HEAT25_30']
                if vr5 is None:
                    new_5d = mild_volume_penalty
                else:
                    new_5d = min(8.0, 2.0 * max(0.0, vr5 - 1.5))
                row['score_B_VOL_5D_15'] = base_b + mild_volume_penalty - new_5d

                # TODAY / PREVIOUS TWENTY sessions, excluding selection day.
                prior20 = [number(snapshots[j][1].get(row['ticker'], {}).get('volume'))
                           for j in range(i - 20, i)]
                vr20 = (row['daily_volume'] / mean(prior20)
                        if row['daily_volume'] is not None
                        and all(x is not None and x >= 0 for x in prior20)
                        and mean(prior20) > 0 else None)
                p5 = min(4.0, 2.0 * max(0.0, vr5 - 1.5)) if vr5 is not None else 0.0
                p20 = min(6.0, 2.0 * max(0.0, vr20 - 2.0)) if vr20 is not None else 0.0
                # Missing volume baselines remain neutral, not a free bonus.
                new_both = p5 + p20 if vr5 is not None and vr20 is not None else mild_volume_penalty
                row['score_B_VOL_5D_20D'] = base_b + mild_volume_penalty - new_both

'''
    inject += "                # B3/B4: volume quality measured using historical selection-day candle.\n                # The base B volume penalty is removed and replaced only when candle\n                # data are available and match the selection-day market close.\n                base_b = row['score_BAL_MA_SLOPE_RANK_HEAT25_30']\n                vr5 = row['volume_ratio']  # today / PREVIOUS five sessions\n                prior20 = [number(snapshots[j][1].get(row['ticker'], {}).get('volume'))\n                           for j in range(i - 20, i)]\n                vr20 = (row['daily_volume'] / mean(prior20)\n                        if row['daily_volume'] is not None and row['daily_volume'] >= 0\n                        and all(v is not None and v >= 0 for v in prior20)\n                        and mean(prior20) > 0 else None)\n                candle = ohlc_by_ticker.get(row['ticker'], {}).get(day)\n                clv = None\n                candle_up = False\n                if not isinstance(candle, dict):\n                    candle_coverage['missing'] += 1\n                else:\n                    op, hi, lo, cl = (number(candle.get(k)) for k in ('open','high','low','close'))\n                    if any(v is None for v in (op, hi, lo, cl)) or hi <= lo or not (lo <= op <= hi and lo <= cl <= hi):\n                        candle_coverage['invalid_range'] += 1\n                    elif abs(cl - row['entry']) > max(0.05, row['entry'] * 0.002):\n                        # Prevent adjusted-price or stale OHLC from contaminating results.\n                        candle_coverage['price_mismatch'] += 1\n                    else:\n                        clv = (cl - lo) / (hi - lo)\n                        candle_up = cl >= op\n                        candle_coverage['available'] += 1\n                # Compare against B's existing volume guard. When historical candle\n                # is missing, retain ORIGINAL B penalty (not a free score bonus).\n                # More sensitive volume guard: V5>1.5 or V20>2; up to 10 pts.\n                p5 = min(4.0, 2.0 * max(0.0, vr5 - 1.5)) if vr5 is not None else 0.0\n                p20 = min(6.0, 2.0 * max(0.0, vr20 - 2.0)) if vr20 is not None else 0.0\n                sensitive = p5 + p20\n                # Strong green candle closing in top 20%: no new volume penalty.\n                # Lower close: progressively stronger penalty; clv<=25% gets full.\n                if clv is None or vr5 is None or vr20 is None:\n                    penalty_b3 = mild_volume_penalty\n                elif clv >= .8 and candle_up:\n                    penalty_b3 = 0.0\n                elif clv >= .6 and candle_up:\n                    penalty_b3 = sensitive * .25\n                elif clv >= .4:\n                    penalty_b3 = sensitive * .5\n                elif clv >= .25:\n                    penalty_b3 = sensitive * .75\n                else:\n                    penalty_b3 = sensitive\n                row['score_B3_CANDLE_VOLUME'] = base_b + mild_volume_penalty - penalty_b3\n\n                # B4: same B3 penalty, adjusted by same-day institutional net flow.\n                # Flow must be available on the selection day; otherwise B4 == B3.\n                inst_row = inst.get(day, {}).get(row['ticker'])\n                flow_amount = None\n                if isinstance(inst_row, dict) and row['entry'] is not None:\n                    values = [number(inst_row.get(k)) for k in ('foreign', 'trust', 'dealer')]\n                    if all(v is not None for v in values):\n                        flow_amount = sum(values) * row['entry']\n                if flow_amount is None:\n                    candle_coverage['flow_missing'] += 1\n                else:\n                    candle_coverage['flow_available'] += 1\n                penalty_b4 = penalty_b3\n                if clv is not None and vr5 is not None and vr20 is not None and flow_amount is not None:\n                    if flow_amount > 0 and clv >= .75 and candle_up:\n                        penalty_b4 = 0.0\n                    elif flow_amount < 0 and clv < .5:\n                        penalty_b4 = min(12.0, penalty_b3 * 1.25)\n                row['score_B4_CANDLE_VOLUME_FLOW'] = base_b + mild_volume_penalty - penalty_b4\n\n"
    src = src.replace(anchor, inject + anchor)
    # Use a separate output so no production/shadow artifacts are overwritten.
    src = src.replace("OUT = ROOT / 'data/ai_shadow_test.json'", "OUT = ROOT / 'data/_temp_b_volume_shadow.json'")
    src = src.replace("CSV = ROOT / 'data/ai_shadow_test.csv'", "CSV = ROOT / 'data/_temp_b_volume_shadow.csv'")
    marker = "'selection_days': len(set(r['date'] for r in picks)),"
    if src.count(marker) != 1:
        raise RuntimeError('Cannot locate result metadata')
    src = src.replace(marker, "'candle_coverage': candle_coverage,\n        " + marker)
    compile(src, str(TMP), 'exec')
    return src


def main():
    if not SOURCE.exists():
        raise SystemExit('Place this script in repository root beside ai_shadow_backtest.py')
    if TMP.exists():
        raise SystemExit(f'Temporary file already exists: {TMP}')
    src = patch_source(SOURCE.read_text(encoding='utf-8'))
    TMP.write_text(src, encoding='utf-8')
    try:
        subprocess.run([sys.executable, str(TMP)], cwd=ROOT, check=True)
        raw = json.loads((ROOT / 'data/_temp_b_volume_shadow.json').read_text(encoding='utf-8'))
        coverage = raw.get('candle_coverage', {})
        valid = coverage.get('available', 0)
        total = valid + coverage.get('missing', 0) + coverage.get('invalid_range', 0) + coverage.get('price_mismatch', 0)
        if not total or valid / total < .70:
            raise RuntimeError(f'Insufficient historical OHLC coverage: {valid}/{total}; refusing misleading comparison')
        strategies = (BASE,) + VARIANTS
        result = {
            'description': 'B baseline versus volume penalty variants; all other factors unchanged',
            'source': 'ai_shadow_backtest.py',
            'candle_coverage': coverage,
            'strategy_formulas': {
                BASE: 'min(6,2*max(0,V5-3))',
                'B_VOL_5D_15': 'min(8,2*max(0,V5-1.5))',
                'B_VOL_5D_20D': 'min(4,2*max(0,V5-1.5))+min(6,2*max(0,V20-2))',
                'B3_CANDLE_VOLUME': 'B2 volume penalty weighted by OHLC close location and candle body',
                'B4_CANDLE_VOLUME_FLOW': 'B3 plus institutional flow quality',
            },
            'note': 'V5 and V20 exclude selection day; same-date close entry and reconstructed historical picks have lookahead/survivorship bias; costs excluded',
            'selection_days': raw.get('selection_days'),
            'summary': {k: raw.get('summary', {}).get(k) for k in strategies},
            'paired_summary': {k: raw.get('paired_summary', {}).get(k) for k in strategies},
            'daily_picks': {d: {m: {k: values.get(k, []) for k in strategies}
                                for m, values in markets.items()}
                            for d, markets in raw.get('daily_picks', {}).items()},
        }
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        with CSV.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(['strategy', 'market', 'period', 'statistics_json'])
            for strategy in strategies:
                summary = result['summary'].get(strategy) or {}
                for market, block in summary.items():
                    w.writerow([strategy, market, 'all', json.dumps(block, ensure_ascii=False)])
        print('Results:', OUTPUT, CSV)
        for strategy in strategies:
            print(strategy, json.dumps(result['summary'].get(strategy), ensure_ascii=False)[:1800])
    finally:
        TMP.unlink(missing_ok=True)
        (ROOT / 'data/_temp_b_volume_shadow.json').unlink(missing_ok=True)
        (ROOT / 'data/_temp_b_volume_shadow.csv').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
