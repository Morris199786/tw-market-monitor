"""Backfill broker rating action and price-target action without OpenAI calls.

Runs over *all* existing data/reports.json items on every workflow run.
Idempotent: writes only when values actually change.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "data/reports.json"
VALID_ACTIONS = {"upgrade", "downgrade", "initiate", "maintain", "sector", "none"}


def as_number(value):
    if value is None or isinstance(value, bool):
        return None
    raw = re.sub(r"^(?:NT\$|TWD|NTD|\$)\s*", "", str(value).strip(), flags=re.I)
    raw = raw.replace(",", "").replace("元", "").strip()
    try:
        result = float(raw)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def classify_target_action(report):
    old = as_number(report.get("target_price_old"))
    new = as_number(report.get("target_price_new"))
    if old is None or new is None:
        return "unknown"
    if new > old:
        return "upgrade"
    if new < old:
        return "downgrade"
    return "maintain"


def classify_action(report):
    """Rating action: restore pre-legacy-rule value when available.

    Legacy fix_report_actions.py overwrote action based solely on target prices,
    while preserving the previous AI rating action in action_before_rule.
    Do not infer a rating upgrade/downgrade from a price-target change.
    """
    if report.get("validation_status") == "needs_review":
        return "none"
    if str(report.get("report_type") or "").strip().lower() in {"sector", "theme"}:
        return "sector"
    prior = str(report.get("action_before_rule") or "").strip().lower()
    current = str(report.get("action") or "none").strip().lower()
    if prior in VALID_ACTIONS:
        return prior
    return current if current in VALID_ACTIONS else "none"


def main():
    if not REPORTS_PATH.exists():
        raise FileNotFoundError(f"Missing report database: {REPORTS_PATH}")
    data = json.loads(REPORTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("Invalid data/reports.json format; refusing to overwrite")

    rating_changed = 0
    target_changed = 0
    stats = {"upgrade": 0, "downgrade": 0, "maintain": 0, "unknown": 0}
    for report in data["items"]:
        if not isinstance(report, dict):
            continue
        rating_action = classify_action(report)
        target_action = classify_target_action(report)
        if report.get("action") != rating_action:
            report["action"] = rating_action
            rating_changed += 1
        if report.get("target_price_action") != target_action:
            report["target_price_action"] = target_action
            target_changed += 1
        stats[target_action] += 1

    rule = (
        "action=券商評等動作；優先還原先前規則覆蓋前的action_before_rule；"
        "target_price_action=以可比較的新舊目標價計算上調/下調/維持；"
        "沒有完整新舊目標價則unknown；不根據目標價推定評等變化"
    )
    if data.get("_action_rule") != rule:
        data["_action_rule"] = rule

    output = json.dumps(data, ensure_ascii=False, indent=2)
    original = REPORTS_PATH.read_text(encoding="utf-8")
    if original != output:
        REPORTS_PATH.write_text(output, encoding="utf-8")

    print(
        f"Report actions backfilled: reports={len(data['items'])}, "
        f"rating_changed={rating_changed}, target_changed={target_changed}, "
        f"target_stats={stats}; OpenAI calls=0, Telegram calls=0"
    )


if __name__ == "__main__":
    main()
