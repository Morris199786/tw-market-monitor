#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
產業資料庫前端更新
- 保留券商報告原版介面
- 法說／座談：B 欄法說會、call memo
- 市場情報：B 欄小作文、漲停強勢
- 保留美股
- 其他分類隱藏，後台資料不刪除
- 原文直接排版，不使用 OpenAI API
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "assets" / "research_merged.js"


def replace_once(source, old, new, label):
    if old not in source:
        if new in source:
            print(f"[SKIP] {label} 已更新")
            return source

        raise RuntimeError(
            f"找不到修改位置：{label}。"
            "可能是原始 JS 已變更，停止修改。"
        )

    if source.count(old) != 1:
        raise RuntimeError(
            f"修改位置不唯一：{label}"
        )

    print(f"[OK] {label}")
    return source.replace(old, new, 1)


def main():
    if not JS.exists():
        raise FileNotFoundError(JS)

    original = JS.read_text(encoding="utf-8")
    code = original

    # 1. 只保留指定分類
    code = replace_once(
        code,
        """const categories = [
  '個股研究',
  '產業研究',
  '法說／訪談',
  '週報',
  '市場情報',
  '券商報告'
];""",
        """const categories = [
  '券商報告',
  '法說／座談',
  '市場情報'
];""",
        "分類按鈕",
    )

    # 2. 預設顯示券商報告
    code = replace_once(
        code,
        """let category = '';
let market = 'TW';""",
        """let category = '券商報告';
let market = 'TW';""",
        "預設分類",
    )

    # 3. 嚴格按照 Excel B 欄分類
    code = replace_once(
        code,
        """    if (category === '券商報告' ? row.source_kind !== 'broker' : category && row.category !== category) return false;""",
        """    if (market === 'TW') {
      const type = String(
        row.original_type || ''
      ).trim().toLowerCase();

      if (category === '券商報告') {
        if (row.source_kind !== 'broker') return false;
      } else if (category === '法說／座談') {
        if (row.source_kind !== 'line') return false;
        if (!['法說會', 'call memo'].includes(type)) {
          return false;
        }
      } else if (category === '市場情報') {
        if (row.source_kind !== 'line') return false;
        if (!['小作文', '漲停強勢'].includes(type)) {
          return false;
        }
      } else {
        return false;
      }
    }""",
        "B 欄分類過濾",
    )

    # 4. 保留券商報告原版
    code = replace_once(
        code,
        """  const brokerMode = active && !ratingOn && category === '券商報告';""",
        """  const brokerMode =
    active &&
    !ratingOn &&
    market === 'TW' &&
    category === '券商報告';""",
        "券商報告原版顯示",
    )

    # 5. 切換分類
    code = replace_once(
        code,
        """    category = category === b.dataset.category
      ? ''
      : b.dataset.category;""",
        """    market = 'TW';
    category = b.dataset.category;""",
        "分類切換",
    )

    # 6. 美股按鈕
    code = replace_once(
        code,
        """  market = market === 'US' ? 'TW' : 'US';
  category = '';""",
        """  market = market === 'US' ? 'TW' : 'US';
  category = market === 'TW' ? '券商報告' : '';""",
        "美股切換",
    )

    # 7. 原文閱讀
    old = """  if (r.source_kind === 'broker') return brokerFullDetail(r,financialRecords);
  if (r.ai_schema === 'broker-v1' && r.ai_research) return brokerFullDetail({...r.ai_research, date:r.date, source:r.source},financialRecords);
  const d = r.display || {};"""

    new = """  if (r.source_kind === 'broker') {
    return brokerFullDetail(r, financialRecords);
  }

  const originalType = String(
    r.original_type || ''
  ).trim().toLowerCase();

  const directTypes = [
    '法說會',
    'call memo',
    '小作文',
    '漲停強勢'
  ];

  // 指定分類直接顯示原文，不使用 AI 摘要。
  if (
    r.market !== 'US' &&
    r.source_kind === 'line' &&
    directTypes.includes(originalType)
  ) {
    const d = r.display || {};

    const texts = [
      d.full_text || r.full_text,
      d.full_text_2 || r.full_text_2,
      d.full_text_3 || r.full_text_3
    ]
      .map(clean)
      .filter(Boolean);

    const uniqueTexts = [...new Set(texts)];

    let html = `
      <div class="rm-info">
        ${escape(r.date || m.date)}
        · ${escape(r.source || m.source)}
        · ${escape(r.original_type || '')}
      </div>
    `;

    if (uniqueTexts.length) {
      uniqueTexts.forEach((text, index) => {
        const title = uniqueTexts.length > 1
          ? `原文 ${index + 1}`
          : '研究原文';

        html += section(
          title,
          displayText(text)
        );
      });
    } else {
      html += section(
        '研究重點',
        displayText(
          d.story || r.story || m.story || ''
        )
      );
    }

    return html;
  }

  if (r.ai_schema === 'broker-v1' && r.ai_research) {
    return brokerFullDetail(
      {
        ...r.ai_research,
        date: r.date,
        source: r.source
      },
      financialRecords
    );
  }

  const d = r.display || {};"""

    code = replace_once(
        code, old, new, "原文閱讀版面"
    )

    # 8. 搜尋時仍只顯示目前選取的分類
    # 原本 visible() 已經負責分類過濾，不改動搜尋索引。

    # 9. 原文排版 CSS
    extra_css = """
/* 法說／座談、市場情報：原文排版 */
#rmReader .rm-section {
  overflow-wrap: anywhere;
}

#rmReader .rm-section .rm-prose {
  line-height: 1.9;
  text-align: left;
}

#rmReader .rm-section .rm-prose p {
  margin: 0 0 1em;
  text-indent: 0;
  overflow-wrap: anywhere;
}

#rmReader .rm-section .rm-company-line {
  margin-bottom: 12px;
}

#researchMergedPanel .rm-cats {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
}

#researchMergedPanel .rm-cats::-webkit-scrollbar {
  display: none;
}
"""

    code = replace_once(
        code,
        "document.head.appendChild(css);",
        "css.textContent += "
        + repr(extra_css)
        + ";\n\ndocument.head.appendChild(css);",
        "原文 CSS",
    )

    if code == original:
        print("沒有需要更新的內容")
        return

    backup = JS.with_name(
        JS.name + ".before_research_ui.bak"
    )

    if not backup.exists():
        backup.write_text(
            original,
            encoding="utf-8"
        )

    JS.write_text(code, encoding="utf-8")

    print()
    print("更新完成：", JS)
    print("備份位置：", backup)
    print("未修改同步程式、Excel、JSON 或 API。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
