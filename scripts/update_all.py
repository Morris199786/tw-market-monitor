import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(name):
    print("\\n==", name, "==")
    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / name)]
    )


if __name__ == "__main__":
    # 順序很重要：
    # 1. master
    # 2. 當日官方收盤（成交排行／突然放量／進階篩選）
    # 3. 法人
    # 4. AI 選股
    # 5. 熱力圖收盤版，確保盤後仍有最後一筆正式更新
    for f in [
        "update_master.py",
        "update_close.py",
        "update_institutional.py",
        "update_ai.py",
        "update_heatmap.py",
    ]:
        run(f)
