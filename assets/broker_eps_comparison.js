/* Quarterly broker EPS forecasts versus disclosed monthly / quarterly EPS.
   Additive UI only; no changes to existing self-report or earnings rendering. */
(() => {
  'use strict';
  const FILE = './data/broker_eps_forecasts.json';
  const PERIOD = /^(20\d\d)-Q([1-4])$/;
  const MONTH = /(20\d\d)[-\/]0?([1-9]|1[0-2])\b/;
  let index = new Map(), loaded = false, loading = null, lastLoad = 0, timer = 0;
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const quarterOfMonth = s => {
    const m = String(s || '').match(MONTH);
    return m ? `${m[1]}-Q${Math.ceil(Number(m[2]) / 3)}` : '';
  };
  const numeric = s => {
    const raw = String(s ?? '').trim();
    if (!raw || raw === '—') return null;
    const n = Number(raw.replace(/[,元\s]/g, ''));
    return Number.isFinite(n) ? n : null;
  };
  const publishedBefore = (r, published) => !published || (r.report_date && r.report_date <= published);

  function normalize(data) {
    const next = new Map();
    for (const x of data?.items || []) {
      if (!/^\d{4}$/.test(String(x.ticker || '')) || !PERIOD.test(x.period || '') ||
          !/^20\d\d-\d\d-\d\d$/.test(x.report_date || '') ||
          !x.broker || !Number.isFinite(Number(x.eps))) continue;
      const key = `${x.ticker}|${x.period}`;
      if (!next.has(key)) next.set(key, []);
      next.get(key).push(x);
    }
    for (const rows of next.values()) {
      rows.sort((a, b) => b.report_date.localeCompare(a.report_date) || a.broker.localeCompare(b.broker));
    }
    index = next;
  }

  async function refresh(force = false) {
    if (loading) return loading;
    if (loaded && !force && Date.now() - lastLoad < 5 * 60 * 1000) return;
    loading = fetch(`${FILE}?v=${Math.floor(Date.now() / 300000)}`, {cache:'no-store'})
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => { normalize(data); loaded = true; lastLoad = Date.now(); })
      .catch(err => { console.warn('[broker EPS comparison] no data', err); })
      .finally(() => { loading = null; });
    return loading;
  }

  function attach(target, ticker, period, actual, published) {
    if (!target) return;
    const existing = target.querySelector(':scope > .broker-eps-comparison');
    const rows = index.get(`${ticker}|${period}`) || [];
    const eligible = rows.filter(r => publishedBefore(r, published) && Number.isFinite(Number(r.eps)) && Number(r.eps) !== 0);
    if (!eligible.length || !Number.isFinite(actual)) {
      existing?.remove();
      return;
    }
    const signature = `${ticker}|${period}|${actual}|${published}|${eligible.map(x=>x.report_id+':'+x.eps).join(',')}`;
    if (existing?.dataset.signature === signature) return;
    const html = eligible.map(r => {
      const ratio = (actual / Number(r.eps)) * 100;
      if (!Number.isFinite(ratio)) return '';
      const date = r.report_date.slice(5).replace('-', '/');
      const eps = Number(r.eps).toFixed(2);
      const title = `券商預估 ${period} EPS ${eps} 元；實際 EPS ${actual.toFixed(2)} 元；達成率＝實際／預估 ×100%`;
      return `<div class="broker-eps-entry" title="${esc(title)}"><span>${esc(date)}</span> <span>${esc(r.broker)}</span> <span class="broker-eps-rate">達成率 ${ratio.toFixed(1)}%</span></div>`;
    }).join('');
    if (!html) return;
    const panel = existing || document.createElement('div');
    panel.className = 'broker-eps-comparison';
    panel.dataset.signature = signature;
    panel.innerHTML = html;
    if (!existing) target.appendChild(panel);
  }

  function render() {
    if (!loaded) return;
    document.querySelectorAll('#selfReportCards .self-report-card').forEach(card => {
      const ticker = card.querySelector('.titleline span')?.textContent.trim();
      const monthMetric = card.querySelector('.metric-grid .metric-box');
      const month = monthMetric?.querySelector('small')?.textContent || '';
      const period = quarterOfMonth(month);
      const value = numeric(monthMetric?.querySelector('strong')?.textContent);
      const publish = card.querySelector('.eyebrow')?.textContent.match(/20\d\d-\d\d-\d\d/)?.[0] || '';
      if (ticker && period && value !== null) attach(monthMetric, ticker, period, value, publish);
    });
    document.querySelectorAll('#quarterlyEarningsCards .earnings-report-row').forEach(card => {
      const ticker = card.querySelector('.earnings-company span')?.textContent.trim();
      const metric = card.querySelector('.earnings-detail.four > div:first-child');
      const period = metric?.querySelector('small')?.textContent.match(/20\d\d-Q[1-4]/)?.[0] || '';
      const value = numeric(metric?.querySelector('b')?.textContent);
      const publish = card.querySelector('.earnings-period')?.textContent.match(/20\d\d\/\d\d\/\d\d/)?.[0]?.replaceAll('/','-') || '';
      if (ticker && period && value !== null) attach(metric, ticker, period, value, publish);
    });
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!document.querySelector('#selfReports')) return;
      await refresh();
      render();
    }, 100);
  }

  function init() {
    const page = document.querySelector('#selfReports');
    if (!page) return;
    const observer = new MutationObserver(records => {
      if (records.every(r => r.target.closest?.('.broker-eps-comparison'))) return;
      schedule();
    });
    observer.observe(page, {childList:true, subtree:true});
    document.addEventListener('visibilitychange', () => { if (!document.hidden) schedule(); });
    setInterval(() => { if (!document.hidden && page.classList.contains('active')) { refresh(true).then(render); } }, 5 * 60 * 1000);
    schedule();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
