#!/usr/bin/env python3
"""Refresh candidate JSON through the same validated prediction implementation.
Does not fetch/alter self-report announcements, delivery ledgers, or Telegram state.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=60)  # legacy compatibility; fixed research start below
    ap.add_argument('--backtest', action='store_true')
    ap.add_argument('--asof', default='')
    a = ap.parse_args()
    cmd = [sys.executable, str(ROOT / 'scripts/self_report_predict.py'), '--root', str(ROOT),
           '--out', 'self_report_model', '--backtest']
    if a.asof: cmd += ['--asof', a.asof]
    subprocess.run(cmd, cwd=ROOT, check=True)
    result = json.loads((ROOT / 'self_report_model/predictions.json').read_text())
    assert set(result['source_status']) == {'twse', 'tpex'}
    assert len(result['candidates']) <= 10
    result['disclaimer'] = '下一交易日自結候選，分數是小樣本估計，非官方公告保證'
    for item in result['candidates']:
        item['level'] = '觀察'
        item['attention_3d'] = item['n3']; item['attention_5d'] = item['n5']; item['attention_10d'] = item['n10']
        item['days_since_last_self_report'] = item['days_since_report']
    target = ROOT / 'data/self_report_candidates.json'
    temp = target.with_suffix('.json.tmp')
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)

if __name__ == '__main__': main()
