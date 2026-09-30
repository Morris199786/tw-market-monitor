import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(name):
    print("\n==", name, "==")
    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / name)]
    )


if __name__ == "__main__":
    # 順序很重要：
    # 1. master
    # 2. 當日官方收盤（也會保存 market history）
    # 3. 法人
    # 4. 個股熱力圖近5日明細
    # 5. AI 選股
    # 6. AI 5日／10日績效回測
    # 7. 熱力圖收盤版
    for f in [
        "update_master.py",
        "update_close.py",
        "update_institutional.py",
        "update_stock_detail.py",
        "update_ai.py",
        "update_ai_backtest.py",
        "update_heatmap.py",
    ]:
        run(f)
