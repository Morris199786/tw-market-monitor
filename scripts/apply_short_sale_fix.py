from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent

py_path = ROOT / "scripts" / "update_margin_lending.py"
js_path = ROOT / "assets" / "margin_lending.js"
index_path = ROOT / "index.html"

for p in (py_path, js_path, index_path):
    if not p.exists():
        raise SystemExit(f"找不到檔案：{p}")

py = py_path.read_text(encoding="utf-8")
js = js_path.read_text(encoding="utf-8")
html = index_path.read_text(encoding="utf-8")

old = '''        field = (
            "margin_balance_lots"
            if key == "margin"
            else "borrow_balance_lots"
        )
'''
new = '''        field = (
            "margin_balance_lots"
            if key == "margin"
            else "short_sell_balance_lots"
        )
'''
if old not in py:
    raise SystemExit("Python: 找不到 metric_series field 區塊")
py = py.replace(old, new, 1)

old = '''        row = (
            h.get(
                key,
                {}
            )
            .get(
                market,
                {}
            )
            .get(
                ticker
            )
        )
'''
new = '''        source_key = (
            "margin"
            if key == "margin"
            else "short_sell"
        )

        row = (
            h.get(
                source_key,
                {}
            )
            .get(
                market,
                {}
            )
            .get(
                ticker
            )
        )
'''
if old not in py:
    raise SystemExit("Python: 找不到 metric_series row 區塊")
py = py.replace(old, new, 1)

old = '''    # 最近6日才需要借券賣出確認訊號，
    # 20日異常基準主要依融資／借券餘額本身。
    short_dates = set(
        candidate_dates[-6:]
    )

    for date in candidate_dates:
        snap = fetch_daily_snapshot(
            date,
            master,
            need_short=(
                date in short_dates
            ),
        )
'''
new = '''    # 借券頁主指標已改為「借券賣出餘額」，
    # 因此所有歷史日期都必須抓 TWT93U，
    # 才能正確計算 1日、5日、20日異常。
    for date in candidate_dates:
        snap = fetch_daily_snapshot(
            date,
            master,
            need_short=True,
        )
'''
if old not in py:
    raise SystemExit("Python: 找不到 short_dates 區塊")
py = py.replace(old, new, 1)

old = '''def healthy_snapshot(snap):
    return (
        len(
            snap.get(
                "margin",
                {}
            ).get(
                "twse",
                {}
            )
        )
        >= MIN_TWSE_MARGIN_ROWS
        and len(
            snap.get(
                "margin",
                {}
            ).get(
                "tpex",
                {}
            )
        )
        >= MIN_TPEX_MARGIN_ROWS
        and (
            len(
                snap.get(
                    "borrow",
                    {}
                ).get(
                    "twse",
                    {}
                )
            )
            + len(
                snap.get(
                    "borrow",
                    {}
                ).get(
                    "tpex",
                    {}
                )
            )
        )
        >= MIN_BORROW_ROWS
    )
'''
new = '''def healthy_snapshot(snap):
    short_count = (
        len(
            snap.get(
                "short_sell",
                {}
            ).get(
                "twse",
                {}
            )
        )
        + len(
            snap.get(
                "short_sell",
                {}
            ).get(
                "tpex",
                {}
            )
        )
    )

    return (
        len(
            snap.get(
                "margin",
                {}
            ).get(
                "twse",
                {}
            )
        )
        >= MIN_TWSE_MARGIN_ROWS
        and len(
            snap.get(
                "margin",
                {}
            ).get(
                "tpex",
                {}
            )
        )
        >= MIN_TPEX_MARGIN_ROWS
        and short_count >= MIN_BORROW_ROWS
        and bool(
            snap.get(
                "short_sell_checked"
            )
        )
    )
'''
if old not in py:
    raise SystemExit("Python: 找不到 healthy_snapshot 區塊")
py = py.replace(old, new, 1)

old = '''    if (
        len(old_margin.get("twse", {}))
        >= MIN_TWSE_MARGIN_ROWS
        and len(old_margin.get("tpex", {}))
        >= MIN_TPEX_MARGIN_ROWS
        and (
            len(old_borrow.get("twse", {}))
            + len(old_borrow.get("tpex", {}))
        ) >= MIN_BORROW_ROWS
        and (
            not need_short
            or old.get(
                "short_sell_checked"
            )
        )
    ):
        return old
'''
new = '''    old_short = old.get(
        "short_sell",
        {}
    )

    if (
        len(old_margin.get("twse", {}))
        >= MIN_TWSE_MARGIN_ROWS
        and len(old_margin.get("tpex", {}))
        >= MIN_TPEX_MARGIN_ROWS
        and (
            not need_short
            or (
                old.get(
                    "short_sell_checked"
                )
                and (
                    len(old_short.get("twse", {}))
                    + len(old_short.get("tpex", {}))
                ) >= MIN_BORROW_ROWS
            )
        )
    ):
        return old
'''
if old not in py:
    raise SystemExit("Python: 找不到 snapshot early-return 區塊")
py = py.replace(old, new, 1)

start = py.find('    short_d1 = None\n    short_d5 = None\n\n    if kind == "borrow":')
end = py.find('    reason_bits = []', start)
if start == -1 or end == -1:
    raise SystemExit("Python: 找不到 short confirm 區塊")
py = py[:start] + '''    short_d1 = None
    short_d5 = None

''' + py[end:]

pattern = re.compile(
    r'''\n    if \(\n        kind == "borrow"\n        and short_d1 is not None\n        and short_d1 > 0\n    \):\n        reason_bits\.append\(\n            "借券賣出同步\+"\n            f"\{short_d1:,.0f\}張"\n        \)\n''',
    re.M,
)
py, n = pattern.subn("\n", py, count=1)
if n != 1:
    raise SystemExit("Python: 找不到 reason 同步增加區塊")

py = py.replace(
    '''                "融資暴增"
                if kind == "margin"
                else "借券暴增"
''',
    '''                "融資暴增"
                if kind == "margin"
                else "借券賣出暴增"
''',
    1,
)

pattern = re.compile(
    r'''\n            "short_sell_change_1d_lots": \(.*?\n            \),\n            "short_sell_change_5d_lots": \(.*?\n            \),''',
    re.S,
)
py, n = pattern.subn("", py, count=1)
if n != 1:
    raise SystemExit("Python: 找不到 raw short_sell_change 欄位")

py = py.replace(
    '"version": "2026-09-25-v4-tech-universe"',
    '"version": "2026-09-29-v5-short-sale-balance"',
    1,
)
py = py.replace(
    '"借券主排名使用借券餘額；借券賣出餘額只作確認訊號。兩者同步增加會另外標示，不把所有借券增加直接視為放空",',
    '"借券頁主排名改用「借券賣出餘額」：直接觀察已借入且實際賣出的未回補部位，1日、5日與20日異常全部以借券賣出餘額計算",',
    1,
)

js = js.replace("借券暴增", "借券賣出暴增")
js = js.replace("融資／借券資料", "融資／借券賣出資料")

js = re.sub(
    r'''\n      \$\{\n        mlState\.kind === "borrow".*?\n      \}\n\n      \$\{\n        mlState\.kind === "borrow".*?\n      \}\n''',
    "\n",
    js,
    count=1,
    flags=re.S,
)

html = html.replace(
    "<h1>融資／借券異動</h1>",
    "<h1>融資／借券賣出異動</h1>",
    1,
)
html = html.replace(
    "先抓單日突然暴增，再找近期持續累積｜科技股上市、上櫃各 TOP30",
    "融資與借券賣出｜先抓單日突然暴增，再找近期持續累積｜科技股上市、上櫃各 TOP30",
    1,
)
html = html.replace(
    '<button class="tab" data-ml-kind="borrow">借券增加</button>',
    '<button class="tab" data-ml-kind="borrow">借券賣出增加</button>',
    1,
)
html = html.replace(
    './assets/margin_lending.js?v=20260925-ml1',
    './assets/margin_lending.js?v=20260929-short-sale-v5',
    1,
)

py_path.write_text(py, encoding="utf-8")
js_path.write_text(js, encoding="utf-8")
index_path.write_text(html, encoding="utf-8")

print("完成：")
print(py_path)
print(js_path)
print(index_path)
print()
print("下一步請手動執行 Margin lending update 一次，重新建立借券賣出歷史與排行")
