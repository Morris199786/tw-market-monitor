#!/usr/bin/env python3
"""Run V17 ten times on a frozen working-tree snapshot and compare semantic outputs."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

def digest(path):
    obj = json.loads(Path(path).read_text(encoding='utf-8'))
    if path.endswith('predictions.json'):
        # exclude wall-clock updated_at; model, probabilities, rankings and diagnostics remain.
        obj.pop('updated_at', None)
    encoded = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--start', required=True)
    p.add_argument('--asof', required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--runs', type=int, default=10)
    a = p.parse_args()
    hashes = []
    for i in range(a.runs):
        out = f'self_report_determinism/run_{i:02d}'
        cmd = [sys.executable, 'scripts/self_report_predict.py', '--root', '.', '--start', a.start,
               '--asof', a.asof, '--prediction-date', a.target,
               '--reports', 'data/self_reports_history.json', '--out', out,
               '--attention-cache', Path('self_report_determinism/attention_cache').as_posix()]
        subprocess.run(cmd, check=True, env={**os.environ, 'PYTHONHASHSEED': '0',
                                            'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
                                            'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1'})
        h = digest(f'{out}/predictions.json')
        hashes.append(h)
        print(f'DETERMINISM {i+1}/{a.runs}: {h}', flush=True)
        if h != hashes[0]:
            raise SystemExit(f'NONDETERMINISTIC: run {i+1} != run 1; no publication')
    print('DETERMINISM_PASS', a.runs, 'identical predictions', hashes[0])
    Path('self_report_live').mkdir(exist_ok=True)
    Path('self_report_live/predictions.json').write_bytes(
        Path('self_report_determinism/run_00/predictions.json').read_bytes())

if __name__ == '__main__':
    main()
