/* Business report display-title enhancement. No PDF parsing, API calls, or data mutation. */
(() => {
  'use strict';
  const DATA_URL = './data/business_reports.json';
  const PANEL_ID = 'researchMergedPanel';
  const clean = v => String(v == null ? '' : v).trim();
  const noExt = s => clean(s).replace(/\.pdf$/i, '');
  const normalize = s => clean(s).replace(/[\s_\-]+/g, ' ').toLowerCase();
  const meaningfulTicker = s => /^(?:\d{4,6}|[A-Z]{1,5})$/.test(clean(s));
  const isBadCompany = (s, ticker) => !s || s === ticker || /(?:投顧股市彙報|投資早報|股市彙報|晨訊|盤後分析)/.test(s);
  const stripDate = s => s.replace(/(?:20\d{2}[-_/年]?[01]\d[-_/月]?[0-3]\d|1\d{2}[01]\d[0-3]\d|\b[01]\d[0-3]\d20\d{2}\b)/g, '').replace(/^[\s_\-｜:：]+|[\s_\-｜:：]+$/g, '');
  function titleOf(r) {
    const filename = clean(r.filename || r.name || r.title);
    const base = noExt(filename);
    const broker = clean(r.broker);
    let company = clean(r.company || r.company_name);
    let ticker = clean(r.ticker);
    // A date such as 1030 must never become a stock ticker.
    if (/^(?:10|11|12|0[1-9])[0-3]\d$/.test(ticker) && /(?:彙報|早報|晨訊)/.test(base)) ticker = '';
    if (isBadCompany(company, ticker)) company = '';
    const multi = base.match(/(?:^|[\s_｜-])(\d{4,6})\s*([^\d｜,，、\s]+)[、,，]\s*(\d{4,6})\s*([^\d｜,，、\s]+)/);
    if (multi) return `${multi[2]}（${multi[1]}）、${multi[4]}（${multi[3]}）｜個股研究`;
    if (company && meaningfulTicker(ticker)) {
      const category = /(?:takeaway|重點整理)/i.test(base) ? '重點整理' : /(?:速報|速評)/.test(base) ? '個股速報' : '個股研究';
      return `${company}（${ticker}）｜${category}`;
    }
    if (company) return `${company}｜個股研究`;
    if (/^Industry_US Software/i.test(base)) return '美國軟體產業｜產業研究';
    if (/^(?:daily story_Economics|國際經濟評論)/i.test(base)) return '總體經濟｜研究報告';
    if (/^(?:US daily|康和投顧-【美股早報】)/i.test(base)) return `${broker ? broker + '｜' : ''}美股早報`;
    if (/港股早報/.test(base)) return `${broker ? broker + '｜' : ''}港股早報`;
    if (/投資早報|投資日報|投資晨報|投資早訊/.test(base)) return `${broker ? broker + '｜' : ''}投資早報`;
    if (/晨訊|晨會/.test(base)) return `${broker ? broker + '｜' : ''}晨訊`;
    if (/股市彙報/.test(base)) return `${broker ? broker + '｜' : ''}股市彙報`;
    if (/盤後分析|台股盤後/.test(base)) {
      const detail = stripDate(base.replace(/^.*?(?:盤後分析|台股盤後)/, ''));
      return `${broker ? broker + '｜' : ''}台股盤後${detail ? '｜' + detail : ''}`;
    }
    if (/美股分析/.test(base)) {
      const detail = stripDate(base.replace(/^.*?美股分析/, ''));
      return `美股分析${detail ? '｜' + detail : ''}`;
    }
    if (/產業速報|產業速報|產業展望/.test(base)) return `${broker ? broker + '｜' : ''}${stripDate(base.replace(/^.*?【?(產業速報|產業速報|產業展望)】?/, '')) || '產業研究'}`;
    if (/總經|FOMC|利率決議/.test(base)) return `${broker ? broker + '｜' : ''}${stripDate(base.replace(/^.*?(?:總經重點簡評|總經速報)/, '')) || '總經研究'}`;
    // Do not fabricate company names or report topics when the index is ambiguous.
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
          const filename = filenameNode ? filenameNode.textContent : titleNode.dataset.originalFilename || titleNode.textContent;
          const r = find(filename);
          if (!r) continue; // Never change existing broker/industry/earnings report cards.
          if (!titleNode.dataset.originalFilename) titleNode.dataset.originalFilename = clean(filename);
          const next = titleOf(r);
          if (titleNode.textContent !== next) titleNode.textContent = next;
          if (!filenameNode) {
            // All-category search cards don't have a filename line: preserve it in small text.
            if (!card.querySelector('.br-original-filename')) {
              const n = document.createElement('div');
              n.className = 'br-original-filename';
              n.style.cssText = 'font-size:12px;color:#64748b;overflow-wrap:anywhere;margin-top:5px';
              n.textContent = clean(filename);
              titleNode.insertAdjacentElement('afterend', n);
            }
          }
        }
      } finally { busy = false; }
    }
    const observer = new MutationObserver(enhance);
    observer.observe(cards, { childList: true, subtree: true });
    fetch(DATA_URL, { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => {
        const items = Array.isArray(data) ? data : data.items;
        if (!Array.isArray(items)) return;
        byName = new Map(items.map(r => [key(r.filename || r.name || r.title), r]));
        enhance();
      }).catch(e => console.warn('業務報告標題優化：索引讀取失敗，保留原始標題', e));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
