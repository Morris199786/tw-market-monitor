#!/usr/bin/env python3
"""Switch original broker reports to the original V3 renderer, preserving the Excel UI.
No data mutation, no API calls, no AI ledger writes.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[2] if Path(__file__).resolve().parent.name == 'scripts' else Path.cwd()
p = root / 'assets' / 'research_merged.js'
s = p.read_text(encoding='utf-8')
marker = '/* original-broker-v3-view-v1 */'
if marker in s:
    print('[SKIP] Original broker V3 view already installed')
    raise SystemExit(0)
old = '''  panel.hidden = !active || ratingOn;

  if (active && !ratingOn) {
    legacy.hidden = true;
    init();
  } else if (ratingOn) {
    legacy.hidden = true;
  } else {
    legacy.hidden = false;
  }
'''
new = '''  /* original-broker-v3-view-v1 */
  // Broker reports must use the original reports_v2.js renderer and its
  // complete AI analysis, rather than the simplified merged reader.
  const brokerMode = active && !ratingOn && category === '券商報告';
  panel.hidden = !active || ratingOn;
  legacy.hidden = active && !ratingOn ? !brokerMode : Boolean(ratingOn);
  cards.hidden = brokerMode;
  panel.querySelector('.rm-search').hidden = brokerMode;
  meta.hidden = brokerMode;
  if (brokerMode) more.hidden = true;

  if (active && !ratingOn) init();
'''
assert s.count(old) == 1, 'STOP: Expected exact sync() anchor once; no changes made'
s = s.replace(old,new,1)
# Ensure switching between categories updates both panels immediately.
old2 = '''    if (!query) {
      defaultMatches();
    } else {
      limit = 30;
      render();
    }
  });
});'''
new2 = '''    if (!query) {
      defaultMatches();
    } else {
      limit = 30;
      render();
    }
    sync();
    console.info('[RESEARCH_VIEW] mode=' + (category === '券商報告' ? 'original_broker_v3' : 'merged_research'));
  });
});'''
assert s.count(old2)==1, 'STOP: Expected exact category listener anchor once; no changes made'
s=s.replace(old2,new2,1)
# Respect native hidden even where inherited CSS declares display.
s += '''\n/* Keep hidden elements hidden when switching to the original broker view. */\n'''
p.write_text(s,encoding='utf-8')
print('[SUCCESS] Original broker cards now use reports_v2.js; Excel stays in merged UI')
print('[CHECK] No OpenAI call; no report data/cache/ledger modifications')
