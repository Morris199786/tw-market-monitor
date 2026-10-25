#!/usr/bin/env python3
"""Install read-only Excel AI layout script. Idempotent, no API/cache writes."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
page=ROOT/'index.html'
js=ROOT/'assets/research_ai_layout_fix.js'
if not js.is_file():
    raise SystemExit(f'[ERROR] Missing {js}; upload the JS before running')
s=page.read_text(encoding='utf-8')
if 'research_ai_status.js' not in s:
    raise SystemExit('[ERROR] Existing AI status UI not found; no changes made')
script='<script defer src="assets/research_ai_layout_fix.js?v=20261025b"></script>'
s=re.sub(r'\s*<script[^>]*src=["\'][^"\']*research_ai_layout_fix\.js[^>]*></script>', '',s)
if '</body>' not in s:
    raise SystemExit('[ERROR] Missing </body>')
s=s.replace('</body>',script+'\n</body>')
page.write_text(s,encoding='utf-8')
print('[SUCCESS] Layout JS installed into index.html')
print('[INFO] No OpenAI calls; no changes to AI cache or research database')
