#!/usr/bin/env python3
"""One-time non-destructive addition of ETF tab JS to existing index.html."""
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'index.html'
s=p.read_text(encoding='utf-8')
line='<script src="./assets/etf_flow.js?v=20261020-1"></script>'
if 'assets/etf_flow.js' not in s:
    if '</body>' not in s: raise RuntimeError('index.html missing </body>')
    p.write_text(s.replace('</body>',line+'\n</body>'),encoding='utf-8')
print('ETF tab script installed; existing HTML content retained')
