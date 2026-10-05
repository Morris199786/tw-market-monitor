from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "data/reports.json"


def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except Exception:
        return default


def save_json(path: Path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def as_number(value):
    if value is None:
        return None

    if isinstance(
        value,
        (int, float),
    ):
        return float(value)

    raw = (
        str(value)
        .replace(",", "")
        .replace("NT$", "")
        .replace("TWD", "")
        .replace("元", "")
        .strip()
    )

    if not raw:
        return None

    try:
        return float(raw)
    except Exception:
        return None


def classify_action(report):
    if report.get("validation_status")=="needs_review": return "none"
    report_type = str(
        report.get("report_type")
        or ""
    ).strip().lower()

    current = str(
        report.get("action")
        or "none"
    ).strip().lower()

    # 產業／主題報告永遠歸在產業
    if report_type in (
        "sector",
        "theme",
    ):
        return "sector"

    # 初評優先保留，不因首次給目標價而誤判為上調
    if current == "initiate":
        return "initiate"

    old_tp = as_number(
        report.get(
            "target_price_old"
        )
    )

    new_tp = as_number(
        report.get(
            "target_price_new"
        )
    )

    # 只要新舊目標價都有，而且真的有變動，
    # 就用數字直接判斷，不交給 AI 自由判斷
    if (
        old_tp is not None
        and new_tp is not None
    ):
        if new_tp > old_tp:
            return "upgrade"

        if new_tp < old_tp:
            return "downgrade"

    # 若沒有可比較的新舊目標價，
    # 保留 AI 從報告明確文字辨識出的評等動作
    if current in (
        "upgrade",
        "downgrade",
        "maintain",
        "none",
    ):
        return current

    return "none"


def main():
    data = load_json(
        REPORTS_PATH,
        {
            "items": [],
        },
    )

    items = (
        data.get("items")
        or []
    )

    changed = 0
    stats = {
        "upgrade": 0,
        "downgrade": 0,
        "initiate": 0,
        "maintain": 0,
        "sector": 0,
        "none": 0,
    }

    for report in items:
        old_action = str(
            report.get("action")
            or "none"
        )

        new_action = classify_action(
            report
        )

        if old_action != new_action:
            report[
                "action_before_rule"
            ] = old_action

            report[
                "action"
            ] = new_action

            changed += 1

        stats[
            new_action
        ] = (
            stats.get(
                new_action,
                0,
            )
            + 1
        )

    data[
        "_action_rule"
    ] = (
        "個股報告：若新舊目標價皆存在且不同，"
        "target_price_new > target_price_old 歸類上調；"
        "target_price_new < target_price_old 歸類下調；"
        "初評優先保留；無可比較目標價時保留報告明確評等動作。"
    )

    save_json(
        REPORTS_PATH,
        data,
    )

    print(
        "report action fix",
        "changed=",
        changed,
        "stats=",
        stats,
    )


if __name__ == "__main__":
    main()

