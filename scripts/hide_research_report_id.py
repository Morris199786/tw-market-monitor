#!/usr/bin/env python3
"""Hide report IDs from the temporary research UI, preserving internal dedup IDs."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'assets' / 'research_ai_status.js'
if not path.is_file():
    raise SystemExit(f'[ERROR] Missing {path}')
s = path.read_text(encoding='utf-8')
old = '''          ${esc(r.date)}
          <br>
          報告 ID：${esc(r.id)}'''
new = '''          ${esc(r.date)}'''
if old in s:
    s = s.replace(old, new)
    print('[PATCH] Removed visible report ID from all AI status cards')
elif '報告 ID：${esc(r.id)}' not in s:
    print('[OK] Visible report ID already absent')
else:
    raise SystemExit('[ERROR] Unknown report ID template; refusing unsafe replacement')
s = s.replace('placeholder="搜尋公司、券商、日期、報告 ID"',
              'placeholder="搜尋公司、券商、日期"')
# Keep r.id in plan/cache matching and in the backend ledger. Do not change any API logic.
path.write_text(s, encoding='utf-8')
print('[OK] Backend IDs and AI cache untouched; zero API calls')
