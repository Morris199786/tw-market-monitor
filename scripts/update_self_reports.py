#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore the complete self-report updater from the last intact repository revision.

This is a one-time self-restoring entry point. On its first execution, it
restores the original full script (including functions imported by the
quarterly-earnings updater), applies the single EPS display fix, and runs it.
The GitHub Actions commit step should commit the restored full script.
"""
from pathlib import Path
import runpy
import sys
from urllib.request import Request, urlopen

HISTORICAL_SHA = "628e764fc1359d3055103c0961ea2573f070ecf6"
URL = (
    "https://raw.githubusercontent.com/Morris199786/tw-market-monitor/"
    + HISTORICAL_SHA + "/scripts/update_self_reports.py"
)
OLD = '''    # 原本注意交易規則完全保留：
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
        )'''
NEW = '''    # 注意交易自結：單月 EPS 成功就收錄，不要求上一季 EPS
    if (
        item.get("match_reason")
        == "attention_trading"
    ):
        return item.get("monthly_eps") is not None'''


def restore_and_run():
    target = Path(__file__).resolve()
    print("[self_reports] Restoring full updater from known-good commit", HISTORICAL_SHA, flush=True)
    req = Request(URL, headers={"User-Agent": "tw-market-monitor-self-report-recovery/1.0"})
    with urlopen(req, timeout=45) as response:
        source = response.read().decode("utf-8-sig")
    if source.count(OLD) != 1:
        raise RuntimeError("Original EPS condition does not match; aborting without overwriting")
    for name in ("parse_rows", "extract_detail_params", "mops_headers", "valid_eps_item"):
        if "def " + name + "(" not in source:
            raise RuntimeError("Historical full script is missing " + name)
    updated = source.replace(OLD, NEW, 1).replace(
        'VERSION = "2026-10-07-v30-safe-revenue-prefilter-timing"',
        'VERSION = "2026-10-20-v31-attention-partial-eps-visible"', 1,
    )
    compile(updated, str(target), "exec")
    target.write_text(updated, encoding="utf-8")
    print("[self_reports] Full updater restored, import functions preserved, EPS filter fixed", flush=True)
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    try:
        restore_and_run()
    except Exception as exc:
        print(f"[self_reports] Recovery failed: {exc}", file=sys.stderr, flush=True)
        raise
