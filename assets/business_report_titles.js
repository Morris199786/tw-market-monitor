/* Business report title enhancement */
(() => {
  'use strict';

  const DATA_URL = './data/business_reports.json';
  const PANEL_ID = 'researchMergedPanel';

  const clean = v => String(v == null ? '' : v).trim();
  const noExt = s => clean(s).replace(/\.pdf$/i, '');
  const normalize = s =>
    clean(s).replace(/[\s_\-]+/g, ' ').toLowerCase();

  const meaningfulTicker = s =>
    /^(?:\d{4,6}|[A-Z]{1,5})$/.test(clean(s));

  const isBadCompany = (s, ticker) =>
    !s ||
    s === ticker ||
    /(?:投顧股市彙報|投資早報|股市彙報|晨訊|盤後分析)/.test(s);

  const stripDate = s =>
    s.replace(
      /(?:20\d{2}[-_/年]?[01]\d[-_/月]?[0-3]\d|1\d{2}[01]\d[0-3]\d|\b[01]\d[0-3]\d20\d{2}\b)/g,
      ''
    ).replace(/^[\s_\-｜:：]+|[\s_\-｜:：]+$/g, '');

  // CF 格式在尚無明確券商資料時，依目前設定標記為永豐。
  function displayBroker(r, filename) {
    const raw = clean(r.broker);

    if (/永豐/.test(raw)) return '永豐';

    if (
      /^CF\d{4,6}[_\s-]/i.test(clean(filename)) &&
      (!raw || /^CF$/i.test(raw))
    ) {
      return '永豐';
    }

    return raw;
  }

  function titleOf(r) {
    const filename = clean(r.filename || r.name || r.title);
    const base = noExt(filename);
    const broker = displayBroker(r, filename);

    let company = clean(r.company || r.company_name);
    let ticker = clean(r.ticker);

    // 避免把 1030 這類日期誤判成股票代號。
    if (
      /^(?:10|11|12|0[1-9])[0-3]\d$/.test(ticker) &&
      /(?:彙報|早報|晨訊)/.test(base)
    ) {
      ticker = '';
    }

    if (isBadCompany(company, ticker)) {
      company = '';
    }

    // CF3443_創意_10302026.pdf
    // CF2379_瑞昱_10302026.pdf
    const cf = base.match(
      /^CF(\d{4,6})[_\s-]+(.+?)[_\s-]+\d{8}$/i
    );

    if (cf) {
      ticker = cf[1];
      company = cf[2].trim();
    }

    // 多公司報告
    const multi = base.match(
      /(?:^|[\s_｜-])(\d{4,6})\s*([^\d｜,，、\s]+)[、,，]\s*(\d{4,6})\s*([^\d｜,，、\s]+)/
    );

    if (multi) {
      return `${multi[2]}（${multi[1]}）、${multi[4]}（${multi[3]}）｜個股研究`;
    }

    if (company && meaningfulTicker(ticker)) {
      const category =
        /(?:takeaway|重點整理)/i.test(base)
          ? '重點整理'
          : /(?:速報|速評)/.test(base)
            ? '個股速報'
            : '個股研究';

      return `${company}（${ticker}）｜${category}`;
    }

    if (company) {
      return `${company}｜個股研究`;
    }

    if (/^Industry_US Software/i.test(base)) {
      return '美國軟體產業｜產業研究';
    }

    if (/^(?:daily story_Economics|國際經濟評論)/i.test(base)) {
      return '總體經濟｜研究報告';
    }

    if (/^(?:US daily|康和投顧-【美股早報】)/i.test(base)) {
      return `${broker ? broker + '｜' : ''}美股早報`;
    }

    if (/港股早報/.test(base)) {
      return `${broker ? broker + '｜' : ''}港股早報`;
    }

    if (/投資早報|投資日報|投資晨報|投資早訊/.test(base)) {
      return `${broker ? broker + '｜' : ''}投資早報`;
    }

    if (/晨訊|晨會/.test(base)) {
      return `${broker ? broker + '｜' : ''}晨訊`;
    }

    if (/股市彙報/.test(base)) {
      return `${broker ? broker + '｜' : ''}股市彙報`;
    }

    if (/盤後分析|台股盤後/.test(base)) {
      const detail = stripDate(
        base.replace(/^.*?(?:盤後分析|台股盤後)/, '')
      );

      return `${broker ? broker + '｜' : ''}台股盤後${
        detail ? '｜' + detail : ''
      }`;
    }

    if (/美股分析/.test(base)) {
      const detail = stripDate(
        base.replace(/^.*?美股分析/, '')
      );

      return `美股分析${detail ? '｜' + detail : ''}`;
    }

    if (/產業速報|產業展望/.test(base)) {
      return `${broker ? broker + '｜' : ''}${
        stripDate(
          base.replace(
            /^.*?【?(產業速報|產業展望)】?/,
            ''
          )
        ) || '產業研究'
      }`;
    }

    if (/總經|FOMC|利率決議/.test(base)) {
      return `${broker ? broker + '｜' : ''}${
        stripDate(
          base.replace(
            /^.*?(?:總經重點簡評|總經速報)/,
            ''
          )
        ) || '總經研究'
      }`;
    }

    // 無法辨識時保留原始檔名。
    return base;
  }

  function init() {
    const panel = document.getElementById(PANEL_ID);
    if (!panel) return;

    const cards = panel.querySelector('#rmCards');
    if (!cards) return;

    let byName = new Map();
    let busy = false;

    const key = s => normalize(noExt(s));
    const find = name => byName.get(key(name));

    function enhance() {
      if (busy || !byName.size) return;

      busy = true;

      try {
        for (const card of cards.querySelectorAll('.rm-card')) {
          const filenameNode = card.querySelector('.br-name');
          const titleNode = card.querySelector('.rm-title');

          if (!titleNode) continue;

          const filename = filenameNode
            ? filenameNode.textContent
            : titleNode.dataset.originalFilename ||
              titleNode.textContent;

          const r = find(filename);

          if (!r) continue;

          if (!titleNode.dataset.originalFilename) {
            titleNode.dataset.originalFilename = clean(filename);
          }

          const next = titleOf(r);
          const broker = displayBroker(r, filename);

          // 修正：網站實際使用 .rm-sub 顯示灰色副標題。
          if (broker) {
            const meta = card.querySelector(
              '.rm-sub, .rm-meta, .rm-subtitle, .br-meta'
            );

            if (meta) {
              const current = clean(meta.textContent);

              const parts = current
                .split(/[·・]/)
                .map(clean)
                .filter(Boolean);

              // 如果原本顯示 CF，改成券商名稱。
              const old = parts.findIndex(
                x => /^CF$/i.test(x)
              );

              if (old >= 0) {
                parts[old] = broker;
              } else if (
                !parts.some(
                  x => x === broker || x.includes(broker)
                )
              ) {
                // 券商名稱放在日期前面。
                const dateAt = parts.findIndex(
                  x => /^20\d{2}[-/]\d{2}[-/]\d{2}$/.test(x)
                );

                parts.splice(
                  dateAt >= 0 ? dateAt : parts.length,
                  0,
                  broker
                );
              }

              const updated = parts.join('・');

              if (updated && updated !== current) {
                meta.textContent = updated;
              }
            }
          }

          if (titleNode.textContent !== next) {
            titleNode.textContent = next;
          }

          // 搜尋結果沒有原始檔名欄位時，補上小字。
          if (!filenameNode) {
            if (!card.querySelector('.br-original-filename')) {
              const n = document.createElement('div');

              n.className = 'br-original-filename';

              n.style.cssText =
                'font-size:12px;' +
                'color:#64748b;' +
                'overflow-wrap:anywhere;' +
                'margin-top:5px';

              n.textContent = clean(filename);

              titleNode.insertAdjacentElement('afterend', n);
            }
          }
        }
      } finally {
        busy = false;
      }
    }

    const observer = new MutationObserver(enhance);

    observer.observe(cards, {
      childList: true,
      subtree: true
    });

    fetch(DATA_URL, { cache: 'no-store' })
      .then(response => {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }

        return response.json();
      })
      .then(data => {
        const items = Array.isArray(data)
          ? data
          : data.items;

        if (!Array.isArray(items)) return;

        byName = new Map(
          items.map(r => [
            key(r.filename || r.name || r.title),
            r
          ])
        );

        enhance();
      })
      .catch(error => {
        console.warn(
          '業務報告標題優化：索引讀取失敗，保留原始標題',
          error
        );
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      init,
      { once: true }
    );
  } else {
    init();
  }
})();
