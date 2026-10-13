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
VARIANTS = ('B_VOL_5D_15', 'B_VOL_5D_20D')


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
    src = src.replace(anchor, inject + anchor)
    # Use a separate output so no production/shadow artifacts are overwritten.
    src = src.replace("OUT = ROOT / 'data/ai_shadow_test.json'", "OUT = ROOT / 'data/_temp_b_volume_shadow.json'")
    src = src.replace("CSV = ROOT / 'data/ai_shadow_test.csv'", "CSV = ROOT / 'data/_temp_b_volume_shadow.csv'")
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
        strategies = (BASE,) + VARIANTS
        result = {
            'description': 'B baseline versus volume penalty variants; all other factors unchanged',
            'source': 'ai_shadow_backtest.py',
            'strategy_formulas': {
                BASE: 'min(6,2*max(0,V5-3))',
                'B_VOL_5D_15': 'min(8,2*max(0,V5-1.5))',
                'B_VOL_5D_20D': 'min(4,2*max(0,V5-1.5))+min(6,2*max(0,V20-2))',
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
