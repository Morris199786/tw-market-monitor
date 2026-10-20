#!/usr/bin/env python3
"""一次性修復既有 scripts/update_self_reports.py 的自結顯示條件。
不改公告抓取、Telegram 去重、推播與資料來源。
"""
from pathlib import Path
import sys

target = Path("scripts/update_self_reports.py")
if not target.exists():
    sys.exit(f"找不到 {target}，請從 repository 根目錄執行")

src = target.read_text(encoding="utf-8")
old = """    # 原本注意交易規則完全保留：
    # 必須同時有單月 EPS + 上一季 EPS
    if (
        item.get("match_reason")
        == "attention_trading"
    ):
        return (
            item.get("monthly_eps")
            is not None
            and item.get("quarter_eps")
            is not None
        )"""
new = """    # 注意交易公告已取得單月 EPS 就可顯示；
    # 季 EPS 尚未解析時保留空值，不隱藏整筆公告。
    # Telegram 仍沿用既有 identity 去重。
    if (
        item.get("match_reason")
        == "attention_trading"
    ):
        return item.get("monthly_eps") is not None"""
if old not in src:
    if new in src:
        print("已套用修正，無須重複修改")
        sys.exit(0)
    sys.exit("程式版本與預期不符，停止修改，避免破壞既有功能")

updated = src.replace(old, new, 1)
updated = updated.replace(
    'VERSION = "2026-10-07-v30-safe-revenue-prefilter-timing"',
    'VERSION = "2026-10-20-v31-attention-partial-eps-visible"', 1
)
compile(updated, str(target), "exec")
target.write_text(updated, encoding="utf-8")
print(f"修正完成：{target}")
