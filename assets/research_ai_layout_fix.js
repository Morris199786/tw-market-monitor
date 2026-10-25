/* Excel AI reports: compact broker-style presentation. Read-only; no API calls. */
(() => {
  'use strict';

  const ROOT = 'researchAiAudit';

  const esc = v => String(v ?? '').replace(
    /[&<>"']/g,
    c => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[c])
  );

  const nonempty = v =>
    v !== null &&
    v !== undefined &&
    String(v).trim() !== '';

  const str = v =>
    Array.isArray(v)
      ? v.map(str).join('\n')
      : (typeof v === 'object' && v
          ? JSON.stringify(v)
          : String(v ?? ''));

  const css = `
    #researchAiAudit .raa-card {
      padding: 16px !important;
      margin: 10px 0 !important;
      line-height: 1.55 !important;
      min-height: 0 !important;
    }

    #researchAiAudit .raa-card * {
      box-sizing: border-box !important;
    }

    #researchAiAudit .raa-card .raa-section {
      white-space: normal !important;
      margin: 12px 0 0 !important;
      padding: 12px 0 0 !important;
      min-height: 0 !important;
      line-height: 1.6 !important;
    }

    #researchAiAudit .raa-card .raa-section strong {
      margin: 0 0 5px !important;
    }

    #researchAiAudit .raa-card .raa-section p {
      margin: 0 0 7px !important;
      padding: 0 !important;
    }

    #researchAiAudit .raa-card .raa-section ul {
      margin: 5px 0 !important;
      padding: 0 0 0 22px !important;
    }

    #researchAiAudit .raa-card .raa-section li {
      margin: 0 0 6px !important;
      padding: 0 !important;
    }

    #researchAiAudit .raa-card details {
      margin: 8px 0 0 !important;
    }

    #researchAiAudit .raa-card details summary {
      padding: 7px 0 !important;
    }

    #researchAiAudit .raa-v2-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 8px;
    }

    #researchAiAudit .raa-v2-name {
      font-size: 19px;
      font-weight: 800;
      line-height: 1.35;
      color: #132944;
    }

    #researchAiAudit .raa-v2-ticker {
      font-weight: 750;
      color: #57718b;
      margin-left: 7px;
    }

    #researchAiAudit .raa-v2-broker {
      font-size: 12px;
      color: #61738b;
      margin-top: 4px;
    }

    #researchAiAudit .raa-v2-title {
      font-size: 14px;
      font-weight: 650;
      color: #344b68;
      margin: 6px 0 12px;
      line-height: 1.5;
    }

    #researchAiAudit .raa-v2-facts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin: 10px 0;
    }

    #researchAiAudit .raa-v2-fact {
      background: #f3f7fc;
      border: 1px solid #e1eaf5;
      border-radius: 11px;
      padding: 9px 10px;
      min-width: 0;
    }

    #researchAiAudit .raa-v2-fact .label {
      font-size: 11px;
      color: #64748b;
      display: block;
      margin-bottom: 2px;
    }

    #researchAiAudit .raa-v2-fact .value {
      font-size: 17px;
      font-weight: 800;
      color: #193c68;
      overflow-wrap: anywhere;
    }

    #researchAiAudit .raa-v2-fact.wide {
      grid-column: span 2;
    }

    #researchAiAudit .raa-v2-text {
      white-space: pre-line !important;
      line-height: 1.62 !important;
      overflow-wrap: anywhere;
    }

    #researchAiAudit .raa-v2-table-wrap {
      max-width: 100%;
      overflow-x: auto;
      margin-top: 6px;
    }

    #researchAiAudit .raa-v2-table {
      border-collapse: collapse;
      width: 100%;
      font-size: 13px;
      line-height: 1.5;
    }

    #researchAiAudit .raa-v2-table th {
      background: #edf3fa;
      color: #365170;
      font-weight: 750;
      text-align: left;
    }

    #researchAiAudit .raa-v2-table th,
    #researchAiAudit .raa-v2-table td {
      padding: 8px !important;
      border-bottom: 1px solid #e1e8f1 !important;
      vertical-align: top;
    }

    #researchAiAudit .raa-v2-table td.num {
      text-align: right;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }

    #researchAiAudit .raa-v2-table tr:nth-child(even) td {
      background: #f9fbfe;
    }

    #researchAiAudit .raa-v2-note {
      font-size: 11px;
      color: #7b8899;
      margin: 8px 0;
    }

    @media (max-width: 500px) {
      #researchAiAudit .raa-card {
        padding: 12px !important;
      }

      #researchAiAudit .raa-v2-facts {
        gap: 6px;
      }

      #researchAiAudit .raa-v2-fact {
        padding: 8px;
      }

      #researchAiAudit .raa-v2-name {
        font-size: 17px;
      }
    }
  `;

  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  function table(heads, rows) {
    return `
      <div class="raa-v2-table-wrap">
        <table class="raa-v2-table">
          <thead>
            <tr>
              ${heads.map(h => `<th>${esc(h)}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                ${row.map((c, i) => `
                  <td${i ? ' class="num"' : ''}>${esc(c)}</td>
                `).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function paragraphs(value) {
    if (Array.isArray(value)) {
      return `
        <ul>
          ${value
            .filter(nonempty)
            .map(x => `<li>${esc(str(x))}</li>`)
            .join('')}
        </ul>
      `;
    }

    return `<div class="raa-v2-text">${esc(str(value))}</div>`;
  }

  function section(label, value) {
    if (!nonempty(value) ||
        (Array.isArray(value) && !value.length)) {
      return '';
    }

    return `
      <section class="raa-section">
        <strong>${esc(label)}</strong>
        ${paragraphs(value)}
      </section>
    `;
  }

  function epsTable(items) {
    if (!Array.isArray(items) || !items.length) {
      return '';
    }

    const rows = items.map(x => [
      x.period || x.quarter || x.label || '',
      x.eps ?? x.value ?? '—'
    ]);

    return `
      <section class="raa-section">
        <strong>券商季度 EPS 預估</strong>
        ${table(['季度', 'EPS（元）'], rows)}
      </section>
    `;
  }

  function forecastTable(items) {
    if (!Array.isArray(items) || !items.length) {
      return '';
    }

    const valid = items.filter(
      x => x && typeof x === 'object'
    );

    if (!valid.length) {
      return section('財測調整', items);
    }

    const rows = valid.map(x => [
      x.period || x.year || x.metric || x.item || '財測',
      x.old ?? x.previous ?? '—',
      x.new ?? x.current ?? x.value ?? '—'
    ]);

    return `
      <section class="raa-section">
        <strong>財測調整</strong>
        ${table(
          ['項目／期間', '原預估', '新預估'],
          rows
        )}
      </section>
    `;
  }

  function stockTable(items) {
    if (!Array.isArray(items) || !items.length) {
      return '';
    }

    const rows = items
      .filter(x => x && typeof x === 'object')
      .map(x => [
        `${x.name || ''} ${x.ticker || ''}`.trim(),
        x.rating || '—',
        x.target_price_new ?? x.target_price ?? '—'
      ]);

    if (!rows.length) {
      return '';
    }

    return `
      <section class="raa-section">
        <strong>個股評等與目標價</strong>
        ${table(
          ['公司／代號', '評等', '目標價'],
          rows
        )}
      </section>
    `;
  }

  function card(item, entry) {
    const ai = entry.result || {};

    const company = ai.name || item.company || '';
    const ticker = ai.ticker || item.ticker || '';
    const broker = ai.broker || item.source || '';
    const rating = ai.rating || '';

    const target = ai.target_price_new;
    const old = ai.target_price_old;

    const type = ai.report_type === 'sector'
      ? '產業報告'
      : '個股報告';

    const date = ai.date || item.date || '';

    const fact = (label, value, wide = false) => {
      if (!nonempty(value)) {
        return '';
      }

      return `
        <div class="raa-v2-fact${wide ? ' wide' : ''}">
          <span class="label">${esc(label)}</span>
          <span class="value">${esc(value)}</span>
        </div>
      `;
    };

    const targets = nonempty(target)
      ? `NT$${target}`
      : '';

    const sections = [
      section('核心投資觀點', ai.push_reason),
      section('研究摘要', ai.summary),
      section('研究重點', ai.key_points),
      epsTable(ai.quarterly_eps),
      forecastTable(ai.forecast_changes),
      stockTable(ai.stock_views),
      section('完整研究分析', ai.detail),
      section('風險因素', ai.risks)
    ].filter(Boolean).join('');

    return `
      <div class="raa-v2-header">
        <div>
          <div class="raa-v2-name">
            ${esc(company || ai.title || '研究報告')}
            ${ticker
              ? `<span class="raa-v2-ticker">${esc(ticker)}</span>`
              : ''}
          </div>

          <div class="raa-v2-broker">
            ${esc(broker)} · ${esc(date)} · ${esc(type)}
          </div>
        </div>

        <span class="raa-badge success">AI 已完成</span>
      </div>

      <div class="raa-v2-title">
        ${esc(ai.title || '')}
      </div>

      <div class="raa-v2-facts">
        ${fact('評等', rating)}
        ${fact('目標價', targets)}
        ${fact(
          '原目標價',
          nonempty(old) ? `NT$${old}` : ''
        )}
        ${fact('發布券商', broker)}
        ${fact('報告日期', date)}
      </div>

      ${sections}

      <div class="raa-v2-note">
        來源：已保存的 AI 解析快取 · 本頁不會重新呼叫 API
      </div>
    `;
  }

  let data = null;
  let fetching = null;

  async function load() {
    if (data) {
      return data;
    }

    if (fetching) {
      return fetching;
    }

    fetching = Promise.all([
      './data/research_ai_plan.json',
      './data/research_ai_cache.json'
    ].map(async url => {
      const response = await fetch(url, {
        cache: 'no-store'
      });

      if (!response.ok) {
        throw new Error(
          `${url}: HTTP ${response.status}`
        );
      }

      return response.json();
    })).then(([plan, cache]) => {
      const map = new Map();

      for (const item of plan.items || []) {
        map.set(item.id, item);
      }

      data = { map, cache };

      console.info('[AI_LAYOUT] cache ready', {
        reports: map.size
      });

      return data;
    }).catch(error => {
      fetching = null;

      console.error(
        '[AI_LAYOUT] fetch failed',
        error
      );

      throw error;
    });

    return fetching;
  }

  function refresh() {
    const root = document.getElementById(ROOT);

    if (!root || !data) {
      return;
    }

    for (const element of root.querySelectorAll('.raa-card')) {
      if (element.dataset.raaLayout === 'v2') {
        continue;
      }

      const raw = element.textContent || '';

      const id = raw.match(
        /line-[a-f0-9]{20}/
      )?.[0];

      if (!id) {
        continue;
      }

      const item = data.map.get(id);

      const entry =
        data.cache[id] ||
        data.cache[item?.cache_id];

      if (!item ||
          !entry ||
          entry.status !== 'success' ||
          !entry.result) {
        continue;
      }

      element.innerHTML = card(item, entry);
      element.dataset.raaLayout = 'v2';
    }
  }

  let queued = false;

  function schedule() {
    if (queued) {
      return;
    }

    queued = true;

    requestAnimationFrame(() => {
      queued = false;
      refresh();
    });
  }

  const observer = new MutationObserver(() => {
    schedule();
  });

  function init() {
    const root = document.getElementById(ROOT);

    if (!root) {
      setTimeout(init, 400);
      return;
    }

    observer.observe(root, {
      childList: true,
      subtree: true
    });

    root.addEventListener('click', () => {
      load()
        .then(schedule)
        .catch(() => {});
    });

    load()
      .then(schedule)
      .catch(() => {});

    console.info(
      '[AI_LAYOUT] broker-style compact layout installed (read-only)'
    );
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
