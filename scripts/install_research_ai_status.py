#!/usr/bin/env python3
"""Install read-only temporary AI audit UI, no API calls or ledger changes."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
html = ROOT / 'index.html'
js = ROOT / 'assets/research_ai_status.js'
if not js.is_file():
    raise SystemExit('ERROR missing assets/research_ai_status.js')
s = html.read_text(encoding='utf-8')
if 'assets/research_merged.js' not in s:
    raise SystemExit('ERROR research_merged.js script not found; refusing patch')
# Idempotent: update existing tag or insert immediately after merged research script.
tag = '<script src="./assets/research_ai_status.js?v=20261025-temporary-audit-v1"></script>'
pattern = r'<script\s+src="\./assets/research_ai_status\.js[^\"]*"\s*></script>'
if re.search(pattern, s):
    s = re.sub(pattern, tag, s)
else:
    pattern = r'(<script\s+src="\./assets/research_merged\.js[^\"]*"\s*></script>)'
    s, n = re.subn(pattern, lambda m: m.group(1)+'\n'+tag, s, count=1)
    if n != 1:
        raise SystemExit('ERROR cannot locate exact research_merged.js tag; refusing patch')
html.write_text(s, encoding='utf-8')
print('[OK] installed temporary AI audit script after merged research script')
print('[OK] no AI calls; no cache/ledger modification')
