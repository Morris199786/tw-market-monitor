#!/usr/bin/env python3
"""Install UI and bump JS cache version, preserving existing HTML."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
p=root/'index.html'
s=p.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="./assets/broker_eps_comparison.css?v=20261022-1">'
js='<script src="./assets/broker_eps_comparison.js?v=20261022-compare-v3"></script>'
if 'broker_eps_comparison.css' not in s:s=s.replace('</head>',css+'\n</head>',1)
if 'broker_eps_comparison.js' not in s:s=s.replace('</body>',js+'\n</body>',1)
else:s=re.sub(r'<script\s+src="\./assets/broker_eps_comparison\.js\?v=[^"]+"\s*></script>',js,s)
p.write_text(s,encoding='utf-8')
print('Compare JS cache version updated')
