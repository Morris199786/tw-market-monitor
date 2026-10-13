#!/usr/bin/env python3
"""Compare B/B1/B2/B3/B4 without modifying production strategy."""

import ast
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "ai_shadow_backtest.py"
TMP = ROOT / "_temp_b_volume_shadow.py"

OUTPUT = ROOT / "data/b_volume_comparison.json"
CSV = ROOT / "data/b_volume_comparison.csv"

BASE = "BAL_MA_SLOPE_RANK_HEAT25_30"

VARIANTS = (
    "B_VOL_5D_15",
    "B_VOL_5D_20D",
    "B_CANDLE_VOLUME",
    "B_CANDLE_VOLUME_FLOW",
)


def patch_source(src):
    tree = ast.parse(src)

    assignment = next(
        n for n in tree.body
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "STRATEGIES"
            for t in n.targets
        )
    )

    original = ast.literal_eval(assignment.value)

    if BASE not in original:
        raise RuntimeError("Original B strategy not found")

    lines = src.splitlines(keepends=True)

    lines[assignment.lineno - 1:assignment.end_lineno] = [
        "STRATEGIES = " + repr(tuple(original) + VARIANTS) + "\n"
    ]

    src = "".join(lines)

    anchor = (
        "                # All experimental formulas are identical "
        "across TWSE and TPEx.\n"
    )

    if src.count(anchor) != 1:
        raise RuntimeError("Cannot locate strategy insertion point")

    injection = '''
                # B1: Stronger five-day volume penalty.
                vr5 = row["volume_ratio"]
                base_b = row["score_BAL_MA_SLOPE_RANK_HEAT25_30"]

                if vr5 is None:
                    penalty_b1 = mild_volume_penalty
                else:
                    penalty_b1 = min(
                        8.0,
                        2.0 * max(0.0, vr5 - 1.5)
                    )

                row["score_B_VOL_5D_15"] = (
                    base_b + mild_volume_penalty - penalty_b1
                )

                # Twenty-day volume ratio, excluding selection day.
                prior20 = [
                    number(
                        snapshots[j][1]
                        .get(row["ticker"], {})
                        .get("volume")
                    )
                    for j in range(i - 20, i)
                ]

                if (
                    row["daily_volume"] is not None
                    and len(prior20) == 20
                    and all(
                        x is not None and x >= 0
                        for x in prior20
                    )
                    and mean(prior20) > 0
                ):
                    vr20 = row["daily_volume"] / mean(prior20)
                else:
                    vr20 = None

                if vr5 is not None and vr20 is not None:
                    penalty_b2 = (
                        min(4.0, 2.0 * max(0.0, vr5 - 1.5))
                        + min(6.0, 2.0 * max(0.0, vr20 - 2.0))
                    )
                else:
                    penalty_b2 = mild_volume_penalty

                row["score_B_VOL_5D_20D"] = (
                    base_b + mild_volume_penalty - penalty_b2
                )

                # Read historical OHLC from the market snapshot.
                candle = snapshots[i][1].get(row["ticker"], {})

                op = number(candle.get("open"))
                hi = number(candle.get("high"))
                lo = number(candle.get("low"))
                cl = number(candle.get("close"))

                # Only use verified same-day OHLC.
                candle_valid = (
                    all(
                        x is not None
                        for x in (op, hi, lo, cl)
                    )
                    and hi > lo
                    and lo <= op <= hi
                    and lo <= cl <= hi
                    and abs(cl - row["entry"])
                    <= max(0.01, row["entry"] * 0.001)
                )

                if candle_valid:
                    close_location = (cl - lo) / (hi - lo)
                    bullish = cl > op
                    daily_return = number(candle.get("change_pct"))
                else:
                    close_location = None
                    bullish = False
                    daily_return = None

                # B3: Volume penalty adjusted by candle quality.
                # A strong close can neutralize volume penalties.
                if (
                    candle_valid
                    and vr5 is not None
                    and vr20 is not None
                ):
                    raw_penalty = penalty_b2

                    if (
                        close_location >= 0.80
                        and bullish
                        and daily_return is not None
                        and daily_return > 0
                    ):
                        multiplier = 0.0

                    elif close_location >= 0.80 and bullish:
                        multiplier = 0.25

                    elif close_location >= 0.60 and bullish:
                        multiplier = 0.25

                    elif close_location >= 0.40:
                        multiplier = 0.50

                    elif close_location >= 0.25:
                        multiplier = 0.75

                    else:
                        multiplier = 1.0

                    penalty_b3 = raw_penalty * multiplier

                else:
                    # Missing OHLC must not create a free bonus.
                    penalty_b3 = mild_volume_penalty

                row["score_B_CANDLE_VOLUME"] = (
                    base_b + mild_volume_penalty - penalty_b3
                )

                # B4: Add institutional-flow direction.
                # Historical institutional data must match selection date.
                inst_today = inst.get(day, {}).get(row["ticker"], {})

                if not isinstance(inst_today, dict):
                    inst_today = {}

                def _net_value(record):
                    for key in (
                        "total_net",
                        "total_net_buy",
                        "net",
                        "net_buy",
                        "net_buy_sell",
                    ):
                        value = number(record.get(key))
                        if value is not None:
                            return value
                    return None

                institution_net = _net_value(inst_today)

                penalty_b4 = penalty_b3

                if (
                    candle_valid
                    and institution_net is not None
                    and vr5 is not None
                    and vr20 is not None
                ):
                    strong_close = (
                        close_location >= 0.80
                        and bullish
                        and daily_return is not None
                        and daily_return > 0
                    )

                    weak_close = close_location <= 0.40

                    if institution_net > 0 and strong_close:
                        penalty_b4 = 0.0

                    elif institution_net < 0 and weak_close:
                        penalty_b4 = min(
                            12.0,
                            penalty_b3 * 1.25
                        )

                row["score_B_CANDLE_VOLUME_FLOW"] = (
                    base_b + mild_volume_penalty - penalty_b4
                )

'''

    src = src.replace(anchor, injection + anchor)

    # Isolate all experimental outputs.
    src = src.replace(
        "OUT = ROOT / 'data/ai_shadow_test.json'",
        "OUT = ROOT / 'data/_temp_b_volume_shadow.json'"
    )

    src = src.replace(
        "CSV = ROOT / 'data/ai_shadow_test.csv'",
        "CSV = ROOT / 'data/_temp_b_volume_shadow.csv'"
    )

    compile(src, str(TMP), "exec")

    return src


def main():
    if not SOURCE.exists():
        raise SystemExit(
            "Missing ai_shadow_backtest.py in repository root"
        )

    if TMP.exists():
        raise SystemExit(
            "Temporary shadow file already exists"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    src = patch_source(
        SOURCE.read_text(encoding="utf-8")
    )

    TMP.write_text(src, encoding="utf-8")

    try:
        subprocess.run(
            [sys.executable, str(TMP)],
            cwd=ROOT,
            check=True,
        )

        temp_json = (
            ROOT / "data/_temp_b_volume_shadow.json"
        )

        if not temp_json.exists():
            raise RuntimeError(
                "Shadow backtest did not produce JSON"
            )

        raw = json.loads(
            temp_json.read_text(encoding="utf-8")
        )

        strategies = (BASE,) + VARIANTS

        summary = {
            strategy: raw.get("summary", {}).get(strategy)
            for strategy in strategies
        }

        # Fail rather than silently commit old/incomplete results.
        for strategy in strategies:
            if not summary.get(strategy):
                raise RuntimeError(
                    f"Missing backtest results: {strategy}"
                )

        result = {
            "description": (
                "Original B versus B1/B2/B3/B4"
            ),
            "source": "ai_shadow_backtest.py",
            "strategies": list(strategies),
            "selection_days": raw.get("selection_days"),
            "summary": summary,
            "paired_summary": {
                strategy: raw.get(
                    "paired_summary", {}
                ).get(strategy)
                for strategy in strategies
            },
            "daily_picks": {
                date: {
                    market: {
                        strategy: values.get(strategy, [])
                        for strategy in strategies
                    }
                    for market, values in markets.items()
                }
                for date, markets in raw.get(
                    "daily_picks", {}
                ).items()
            },
            "notes": [
                "B/B1/B2 retain previous scoring formulas",
                "B3 uses volume and close-location quality",
                "B4 additionally uses institutional net direction",
                "Missing OHLC retains original B penalty",
                "Same-day close entry is a historical simulation",
                "Trading costs and slippage excluded",
            ],
        }

        OUTPUT.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        with CSV.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as f:
            writer = csv.writer(f)

            writer.writerow([
                "strategy",
                "market",
                "period",
                "statistics_json",
            ])

            for strategy in strategies:
                for market, block in (
                    summary[strategy] or {}
                ).items():
                    writer.writerow([
                        strategy,
                        market,
                        "all",
                        json.dumps(
                            block,
                            ensure_ascii=False,
                        ),
                    ])

        print("=" * 65)
        print("B VOLUME BACKTEST COMPLETED")
        print("=" * 65)

        for strategy in strategies:
            print()
            print("STRATEGY:", strategy)

            data = summary.get(strategy, {})

            if isinstance(data, dict):
                all_market = data.get("all", {})

                for group in (
                    "top5",
                    "top10",
                    "top20",
                ):
                    stats = (
                        all_market
                        .get(group, {})
                        .get("baseline_5d", {})
                    )

                    print(
                        group,
                        "samples=",
                        stats.get("samples"),
                        "avg_return=",
                        stats.get("avg_return"),
                        "win_rate=",
                        stats.get("win_rate"),
                    )

        print()
        print("Output:", OUTPUT)
        print("CSV:", CSV)

    finally:
        TMP.unlink(missing_ok=True)

        (
            ROOT / "data/_temp_b_volume_shadow.json"
        ).unlink(missing_ok=True)

        (
            ROOT / "data/_temp_b_volume_shadow.csv"
        ).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
