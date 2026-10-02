from pathlib import Path

PATH = Path("scripts/update_self_reports.py")

s = PATH.read_text(encoding="utf-8")

old_version = 'VERSION = "2026-10-01-v19-eps-unit-label-fix-telegram-only"'
new_version = 'VERSION = "2026-10-02-v20-horizontal-eps-regression-fix-telegram-only"'

old = """    # 若月/季被排在同一列，語意切區塊會切不到 EPS；改用橫向 parser 補抓
    if out["monthly_eps"] is None or out["quarter_eps"] is None:
        horizontal = _extract_horizontal_eps(text)
        if horizontal:
            for key, value in horizontal.items():
                if out.get(key) is None:
                    out[key] = value
"""

new = """    # MOPS 注意交易公告常把「最近一月 / 最近一季」放在同一個橫向表格，
    # EPS 列格式為：月 EPS、月 YoY、季 EPS、季 YoY。
    # 這種版型必須以 horizontal parser 為準，不能讓 quarter section
    # 從 EPS 列第一個數字誤抓成月 EPS。
    eps_marker = re.search(EPS_WORD, text, re.I)
    month_marker = re.search(MONTH_WORD, text, re.I)
    quarter_marker = re.search(QUARTER_WORD, text, re.I)

    shared_horizontal_eps_row = bool(
        eps_marker
        and month_marker
        and quarter_marker
        and month_marker.start() < eps_marker.start()
        and quarter_marker.start() < eps_marker.start()
    )

    horizontal = None
    if shared_horizontal_eps_row or out["monthly_eps"] is None or out["quarter_eps"] is None:
        horizontal = _extract_horizontal_eps(text)

    if horizontal:
        for key, value in horizontal.items():
            if shared_horizontal_eps_row or out.get(key) is None:
                out[key] = value
"""

if old not in s:
    raise SystemExit(
        "STOP: 找不到預期的 v19 parser 區塊，沒有修改任何檔案。"
    )

s = s.replace(old, new, 1)
if old_version in s:
    s = s.replace(old_version, new_version, 1)

PATH.write_text(s, encoding="utf-8")
print("OK: scripts/update_self_reports.py 已修正")
print("VERSION:", new_version)
