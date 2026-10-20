"""Daily pipeline: preserve independent updates even when AI coverage is insufficient."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = [
    'update_master.py',
    'update_close.py',
    'update_institutional.py',
    'update_stock_detail.py',
    'update_ai.py',
    'update_ai_backtest.py',
    'update_heatmap.py',
]


def main() -> int:
    failures = []
    for name in TASKS:
        print(f'\n== {name} ==', flush=True)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts' / name)], cwd=ROOT)
        if result.returncode:
            failures.append((name, result.returncode))
            print(f'::error title=Daily update failed::{name} exited {result.returncode}', flush=True)
        else:
            print(f'OK {name}', flush=True)
    if failures:
        print('FAILED TASKS: ' + ', '.join(f'{name} ({code})' for name, code in failures), flush=True)
        return 1
    print('Daily update completed successfully', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
