#!/usr/bin/env python3
"""Recompute prediction ten times; compare decision outputs, not volatile diagnostics."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def semantic(path):
    obj = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    # The first run fetches official notices; subsequent runs read the cache.
    # source_status.offline and wall-clock timestamps necessarily differ, even
    # when every prediction is identical. Do not hash those diagnostics.
    fields = ('ticker', 'market', 'probability', 'score', 'rule_eligible', 'reasons')
    picks = []
    for row in obj.get('items', []):
        picks.append({key: row.get(key) for key in fields if key in row})
    return {
        'version': obj.get('version'),
        'asof': obj.get('asof'),
        'prediction_day': obj.get('prediction_day'),
        'items': picks,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--start', required=True)
    p.add_argument('--asof', required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--runs', type=int, default=10)
    a = p.parse_args()
    baseline = None
    for i in range(a.runs):
        out = f'self_report_determinism/run_{i:02d}'
        cmd = [sys.executable, 'scripts/self_report_predict.py', '--root', '.',
               '--start', a.start, '--asof', a.asof, '--prediction-date', a.target,
               '--reports', 'data/self_reports_history.json', '--out', out,
               '--attention-cache', 'self_report_determinism/attention_cache']
        subprocess.run(cmd, check=True, env={**os.environ, 'PYTHONHASHSEED': '0',
                                            'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
                                            'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1'})
        decision = semantic(f'{out}/predictions.json')
        digest = hashlib.sha256(json.dumps(decision, sort_keys=True,
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        print(f'DETERMINISM {i+1}/{a.runs}: {digest}', flush=True)
        if baseline is not None and decision != baseline:
            raise SystemExit(f'NONDETERMINISTIC: run {i+1} != run 1; prediction decisions differ')
        baseline = decision
    print('DETERMINISM_PASS', a.runs, 'identical prediction decisions', flush=True)
    Path('self_report_live').mkdir(exist_ok=True)
    Path('self_report_live/predictions.json').write_bytes(
        Path('self_report_determinism/run_00/predictions.json').read_bytes())

if __name__ == '__main__':
    main()
