/* Quarterly gross-margin comparison. JSON-only; does not change EPS matching. */
(() => {
  'use strict';
  const escapeHtml = v => String(v ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  }[c]));
  const number = value => {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };
  const dateOf = value => {
    const match = String(value || '').match(/20\d{2}[-/]\d{2}[-/]\d{2}/);
    return match ? match[0].replaceAll('/', '-') : '';
  };
  const quarterOf = value => String(value || '').match(/20\d{2}-Q[1-4]/)?.[0] || '';
  const keyOf = (ticker, period, date) => [ticker, period, date].join('|');
  let byKey = new Map();
  let inFlight = null;
  let scheduled = 0;

  const getCards = () => document.querySelectorAll('#quarterlyEarningsCards .earnings-report-row');
  function render() {
    getCards().forEach(card => {
      const ticker = card.querySelector('.earnings-company span')?.textContent.trim() || '';
      const date = dateOf(card.querySelector('.earnings-period')?.textContent);
      const period = quarterOf(card.querySelector('.earnings-detail.four > div:first-child small')?.textContent);
      const box = card.querySelector('.earnings-detail.four > div:nth-child(2)');
      const old = box?.querySelector(':scope > .broker-gm-comparison');
      if (!ticker || !date || !period || !box) { old?.remove(); return; }
      const visible = number((box.querySelector('b')?.textContent || '').replace('%', '').replace(/,/g, ''));
      const valid = (byKey.get(keyOf(ticker, period, date)) || []).filter(row =>
        visible !== null && Math.abs(visible - Number(row.actual_gross_margin)) < 0.06
      );
      if (!valid.length) { old?.remove(); return; }
      const signature = JSON.stringify(valid.map(x => [x.report_id, x.forecast_gross_margin, x.actual_gross_margin, x.difference_pp]));
      if (old?.dataset.signature === signature) return;
      const el = old || document.createElement('div');
      el.className = 'broker-eps-comparison broker-gm-comparison';
      el.dataset.signature = signature;
      el.innerHTML = valid.map(row => {
        const diff = Number(row.difference_pp);
        const sign = diff > 0 ? '+' : '';
        return `<div class="broker-eps-entry" title="${escapeHtml(period)} 毛利率：實際 ${Number(row.actual_gross_margin).toFixed(2)}%；券商預估 ${Number(row.forecast_gross_margin).toFixed(2)}%">` +
          `<span>${escapeHtml(String(row.report_date).slice(5).replace('-', '/'))}</span>` +
          `<span>${escapeHtml(row.broker)}</span>` +
          `<span class="broker-eps-rate">預估 ${Number(row.forecast_gross_margin).toFixed(2)}%｜差 ${sign}${diff.toFixed(2)} 個百分點</span>` +
          `</div>`;
      }).join('');
      if (!old) box.appendChild(el);
    });
  }
  function load() {
    if (inFlight) return inFlight;
    inFlight = fetch('./data/broker_gross_margin_comparisons.json?v=' + Math.floor(Date.now()/300000), {cache:'no-store'})
      .then(r => { if(!r.ok) throw Error('Gross margin comparison HTTP '+r.status); return r.json(); })
      .then(json => {
        const next = new Map();
        for (const row of json.items || []) {
          if (row.actual_kind !== 'quarterly' || !row.report_id) continue;
          const key = keyOf(row.ticker, row.period, row.announcement_date);
          if (!next.has(key)) next.set(key, []);
          if (!next.get(key).some(x => x.report_id === row.report_id)) next.get(key).push(row);
        }
        for (const rows of next.values()) rows.sort((a,b) => String(b.report_date).localeCompare(String(a.report_date)));
        byKey = next;
        render();
      }).catch(err => console.warn('[Broker gross margin]', err))
      .finally(() => { inFlight = null; });
    return inFlight;
  }
  function init() {
    const root = document.querySelector('#quarterlyEarningsCards');
    if (!root) return;
    new MutationObserver(changes => {
      if (changes.every(x => x.target.closest?.('.broker-gm-comparison'))) return;
      clearTimeout(scheduled);
      scheduled = setTimeout(render, 150);
    }).observe(root, {childList: true, subtree: true});
    load();
    document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
    setInterval(() => { if (!document.hidden) load(); }, 300000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
