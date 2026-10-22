#!/usr/bin/env python3
"""Idempotently install the independent EPS comparison UI into index.html."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
path = root / 'index.html'
html = path.read_text(encoding='utf-8')
css = '<link rel="stylesheet" href="./assets/broker_eps_comparison.css?v=20261022-1">'
js = '<script src="./assets/broker_eps_comparison.js?v=20261022-1"></script>'
if 'broker_eps_comparison.css' not in html:
    if '</head>' not in html:
        raise SystemExit('index.html missing </head>')
    html = html.replace('</head>', css + '\n</head>', 1)
if 'broker_eps_comparison.js' not in html:
    if '</body>' not in html:
        raise SystemExit('index.html missing </body>')
    html = html.replace('</body>', js + '\n</body>', 1)
path.write_text(html, encoding='utf-8')
print('EPS comparison UI installed')
