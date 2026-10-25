#!/usr/bin/env python3
"""Repair accidentally overwritten research JS and apply four-tab no-AI UI.
Only writes assets/research_merged.js. Does not alter sync_line_research.py.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'assets/research_merged.js'
KNOWN_GOOD = '53acaf8fa7414baedcab69504bf6c6dd086f7bb1'


def replace_once(text, before, after, label):
    if before not in text:
        if after in text:
            print('Already applied:', label)
            return text
        raise RuntimeError('Cannot locate expected original block: ' + label)
    if text.count(before) != 1:
        raise RuntimeError('Ambiguous original block: ' + label)
    return text.replace(before, after, 1)


def main():
    original = TARGET.read_text(encoding='utf-8') if TARGET.exists() else ''
    if original.lstrip().startswith('#!/usr/bin/env python3'):
        # A Python patcher was mistakenly uploaded under a .js filename.
        # Restore a verified historical JS from the repo's OWN Git history.
        source = subprocess.check_output(
            ['git', 'show', f'{KNOWN_GOOD}:assets/research_merged.js'],
            cwd=ROOT, text=True,
        )
        print('Restoring original JS from Git history:', KNOWN_GOOD[:12])
    elif original.startswith('/* 產業資料庫'):
        source = original
    else:
        raise RuntimeError('Unexpected JS contents; refusing to overwrite')

    source = replace_once(source,
        "const categories = [\n  '個股研究',\n  '產業研究',\n  '法說／訪談',\n  '週報',\n  '市場情報',\n  '券商報告'\n];",
        "const categories = [\n  '券商報告',\n  '法說／座談',\n  '市場情報'\n];", 'tabs')

    source = replace_once(source,
        "let category = '';\nlet market = 'TW';",
        "let category = '券商報告';\nlet market = 'TW';", 'default')

    source = replace_once(source,
        "    if (category === '券商報告' ? row.source_kind !== 'broker' : category && row.category !== category) return false;",
        """    if (market === 'TW') {
      const type = String(row.original_type || '').trim().toLowerCase();
      if (category === '券商報告') {
        if (row.source_kind !== 'broker') return false;
      } else if (category === '法說／座談') {
        if (row.source_kind !== 'line' || !['法說會', 'call memo'].includes(type)) return false;
      } else if (category === '市場情報') {
        if (row.source_kind !== 'line' || !['小作文', '漲停強勢'].includes(type)) return false;
      } else return false;
    }""", 'B-column filters')

    source = replace_once(source,
        "  const brokerMode = active && !ratingOn && category === '券商報告';",
        "  const brokerMode = active && !ratingOn && market === 'TW' && category === '券商報告';", 'broker renderer')

    source = replace_once(source,
        "    category = category === b.dataset.category\n      ? ''\n      : b.dataset.category;",
        "    market = 'TW';\n    category = b.dataset.category;", 'category selection')

    source = replace_once(source,
        "  market = market === 'US' ? 'TW' : 'US';\n  category = '';",
        "  market = market === 'US' ? 'TW' : 'US';\n  category = market === 'TW' ? '券商報告' : '';", 'US selection')

    source = replace_once(source,
        "  if (r.source_kind === 'broker') return brokerFullDetail(r,financialRecords);\n  if (r.ai_schema === 'broker-v1' && r.ai_research) return brokerFullDetail({...r.ai_research, date:r.date, source:r.source},financialRecords);\n  const d = r.display || {};",
        """  if (r.source_kind === 'broker') return brokerFullDetail(r,financialRecords);
  const type = String(r.original_type || m.original_type || '').trim().toLowerCase();
  if (r.source_kind === 'line' && r.market !== 'US' &&
      ['法說會', 'call memo', '小作文', '漲停強勢'].includes(type)) {
    const d = r.display || {};
    const texts = [d.full_text || r.full_text, d.full_text_2 || r.full_text_2,
      d.full_text_3 || r.full_text_3].map(clean).filter(Boolean);
    const unique = [...new Set(texts)];
    let html = `<div class="rm-info">${escape(r.date || m.date)} · ${escape(r.source || m.source)} · ${escape(r.original_type || '')}</div>`;
    if (unique.length) unique.forEach((txt, i) => {
      html += section(unique.length > 1 ? `原文 ${i + 1}` : '研究原文', displayText(txt));
    });
    else html += section('研究內容', displayText(d.story || r.story || m.story || '尚無原文'));
    return html;
  }
  if (r.ai_schema === 'broker-v1' && r.ai_research) return brokerFullDetail({...r.ai_research, date:r.date, source:r.source},financialRecords);
  const d = r.display || {};""", 'original texts')

    # Switching between the legacy broker renderer and the merged reader must
    # update visibility even when the US button is clicked.
    source = replace_once(source,
        "  if (!query) {\n    defaultMatches();\n  } else {\n    render();\n  }\n});\n\nlet timer;",
        "  if (!query) {\n    defaultMatches();\n  } else {\n    render();\n  }\n  sync();\n});\n\nlet timer;", 'US button sync')

    # Make hidden attribute effective for all four modes.
    source = replace_once(source,
        "#researchMergedPanel {\n  font: 14px/1.65",
        "#researchMergedPanel[hidden] { display: none !important; }\n#researchMergedPanel {\n  font: 14px/1.65", 'hidden panel CSS')

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.js', dir=TARGET.parent, delete=False) as temp:
        temp.write(source)
        temp_path = Path(temp.name)
    try:
        subprocess.run(['node', '--check', str(temp_path)], check=True, cwd=ROOT)
        TARGET.write_text(source, encoding='utf-8')
    finally:
        temp_path.unlink(missing_ok=True)
    print('OK:', TARGET, '(no OpenAI API, no backend modifications)')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('ERROR:', e, file=sys.stderr)
        sys.exit(1)
