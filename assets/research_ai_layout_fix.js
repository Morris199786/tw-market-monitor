/* Broker-style presentation for completed Excel AI reports.
 * Uses existing cache only. No OpenAI API calls.
 */
(() => {
  'use strict';

  const ROOT_ID = 'researchAiAudit';

  const esc = value => String(value ?? '').replace(
    /[&<>"']/g,
    char => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[char])
  );

  const exists = value =>
    value !== null &&
    value !== undefined &&
    String(value).trim() !== '';

  const asText = value => {
    if (Array.isArray(value)) {
      return value.map(asText).join('\n');
    }

    if (value && typeof value === 'object') {
      return JSON.stringify(value, null, 2);
    }

    return String(value ?? '');
  };

  const style = document.createElement('style');

  style.textContent = `
    #researchAiAudit .raa-card {
      padding: 15px !important;
      margin: 10px 0 !important;
      min-height: 0 !important;
      line-height: 1.55 !important;
    }

    #researchAiAudit .raa-card * {
      box-sizing: border-box !important;
    }

    #researchAiAudit .raa-v2-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 9px;
    }

    #researchAiAudit .raa-v2-name {
      color: #142d4e;
      font-size: 19px;
      font-weight: 800;
      line-height: 1.4;
    }

    #researchAiAudit .raa-v2-ticker {
      margin-left: 6px;
      color: #526d89;
      font-size: 16px;
      font-weight: 750;
    }

    #researchAiAudit .raa-v2-broker {
      margin-top: 5px;
      color: #64748b;
      font-size: 12px;
    }

    #researchAiAudit .raa-v2-title {
      margin: 8px 0 12px;
      color: #344b68;
      font-size: 14px;
      font-weight: 650;
      line-height: 1.5;
    }

    #researchAiAudit .raa-v2-facts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin: 10px 0 14px;
    }

    #researchAiAudit .raa-v2-fact {
      min-width: 0;
      padding: 10px;
      border: 1px solid #e1eaf5;
      border-radius: 10px;
      background: #f3f7fc;
    }

    #researchAiAudit .raa-v2-fact-label {
      display: block;
      margin-bottom: 3px;
      color: #64748b;
      font-size: 11px;
    }

    #researchAiAudit .raa-v2-fact-value {
      color: #193c68;
      font-size: 16px;
      font-weight: 800;
      overflow-wrap: anywhere;
    }

    #researchAiAudit .raa-v2-section {
      margin: 12px 0 0 !important;
      padding: 11px 0 0 !important;
      border-top: 1px solid #e2e8f0;
      min-height: 0 !important;
      line-height: 1.6 !important;
    }

    #researchAiAudit .raa-v2-section-title {
      margin: 0 0 7px !important;
      color: #163b6a;
      font-size: 14px;
      font-weight: 800;
    }

    #researchAiAudit .raa-v2-text {
      margin: 0 !important;
      padding: 0 !important;
      white-space: pre-line !important;
      line-height: 1.65 !important;
      overflow-wrap: anywhere;
    }

    #researchAiAudit .raa-v2-list {
      margin: 5px 0 0 !important;
      padding-left: 21px !important;
    }

    #researchAiAudit .raa-v2-list li {
      margin: 0 0 6px !important;
      padding: 0 !important;
      line-height: 1.6 !important;
    }

    #researchAiAudit .raa-v2-table-wrap {
      max-width: 100%;
      overflow-x: auto;
      margin: 8px 0;
    }

    #researchAiAudit .raa-v2-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    #researchAiAudit .raa-v2-table th {
      background: #edf3fa;
      color: #365170;
      font-weight: 750;
    }

    #researchAiAudit .raa-v2-table th,
    #researchAiAudit .raa-v2-table td {
      padding: 9px 8px !important;
      border-bottom: 1px solid #e1e8f1 !important;
      text-align: left;
      vertical-align: middle;
    }

    #researchAiAudit .raa-v2-table td.num {
      text-align: right;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }

    #researchAiAudit .raa-v2-table tr:nth-child(even) td {
      background: #f9fbfe;
    }

    #researchAiAudit .raa-v2-details {
      margin-top: 10px !important;
    }

    #researchAiAudit .raa-v2-details summary {
      padding: 8px 0 !important;
      color: #205fcd;
      font-weight: 750;
      cursor: pointer;
    }

    #researchAiAudit .raa-v2-note {
      margin-top: 10px;
      color: #8290a2;
      font-size: 11px;
    }

    @media (max-width: 500px) {
      #researchAiAudit .raa-card {
        padding: 12px !important;
      }

      #researchAiAudit .raa-v2-name {
        font-size: 17px;
      }

      #researchAiAudit .raa-v2-facts {
        gap: 6px;
      }

      #researchAiAudit .raa-v2-fact {
        padding: 8px;
      }

      #researchAiAudit .raa-v2-fact-value {
        font-size: 15px;
      }
    }
  `;

  document.head.appendChild(style);

  function section(title, value) {
    if (
      !exists(value) ||
      (Array.isArray(value) && !value.length)
    ) {
      return '';
    }

    let body;

    if (Array.isArray(value)) {
      body = `
        <ul class="raa-v2-list">
          ${value.map(item => `
            <li>${esc(asText(item))}</li>
          `).join('')}
        </ul>
      `;
    } else {
      body = `
        <div class="raa-v2-text">
          ${esc(asText(value))}
        </div>
      `;
    }

    return `
      <section class="raa-v2-section">
        <div class="raa-v2-section-title">
          ${esc(title)}
        </div>
        ${body}
      </section>
    `;
  }

  function table(headers, rows) {
    if (!rows.length) return '';

    return `
      <div class="raa-v2-table-wrap">
        <table class="raa-v2-table">
          <thead>
            <tr>
              ${headers.map(header =>
                `<th>${esc(header)}</th>`
              ).join('')}
            </tr>
          </thead>

          <tbody>
            ${rows.map(row => `
              <tr>
                ${row.map((value, index) => `
                  <td${index ? ' class="num"' : ''}>
                    ${esc(value)}
                  </td>
                `).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function epsTable(items) {
    if (!Array.isArray(items) || !items.length) {
      return '';
    }

    const rows = items
      .filter(item => item && typeof item === 'object')
      .map(item => [
        item.period || item.quarter || item.label || '—',
        item.eps ?? item.value ?? '—'
      ]);

    if (!rows.length) return '';

    return `
      <section class="raa-v2-section">
        <div class="raa-v2-section-title">
          券商季度 EPS 預估
        </div>

        ${table(['季度', 'EPS（元）'], rows)}
      </section>
    `;
  }

  function forecastTable(items) {
    if (!Array.isArray(items) || !items.length) {
      return '';
    }

    const rows = items
      .filter(item => item && typeof item === 'object')
      .map(item => [
        item.period ||
          item.year ||
          item.metric ||
          item.item ||
          '財測',
        item.old ?? item.previous ?? '—',
        item.new ?? item.current ?? item.value ?? '—'
      ]);

    if (!rows.length) {
      return section('財測調整', items);
    }

    return `
      <section class="raa-v2-section">
        <div class="raa-v2-section-title">
          財測調整
        </div>

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
      .filter(item => item && typeof item === 'object')
      .map(item => [
        `${item.name || ''} ${item.ticker || ''}`.trim(),
        item.rating || '—',
        item.target_price_new ??
          item.target_price ??
          '—'
      ]);

    if (!rows.length) return '';

    return `
      <section class="raa-v2-section">
        <div class="raa-v2-section-title">
          個股評等與目標價
        </div>

        ${table(
          ['公司／代號', '評等', '目標價'],
          rows
        )}
      </section>
    `;
  }

  function fact(label, value) {
    if (!exists(value)) return '';

    return `
      <div class="raa-v2-fact">
        <span class="raa-v2-fact-label">
          ${esc(label)}
        </span>

        <span class="raa-v2-fact-value">
          ${esc(value)}
        </span>
      </div>
    `;
  }

  function reportCard(item, entry) {
    const ai = entry.result || {};

    const company =
      ai.name ||
      item.company ||
      '';

    const ticker =
      ai.ticker ||
      item.ticker ||
      '';

    const broker =
      ai.broker ||
      item.source ||
      '';

    const rating = ai.rating || '';

    const target = ai.target_price_new;
    const oldTarget = ai.target_price_old;

    const date = ai.date || item.date || '';

    const reportType =
      ai.report_type === 'sector'
        ? '產業報告'
        : '個股報告';

    const targetText = exists(target)
      ? `NT$${target}`
      : '';

    const oldTargetText = exists(oldTarget)
      ? `NT$${oldTarget}`
      : '';

    const details = [
      section('研究摘要', ai.summary),
      section('核心投資觀點', ai.push_reason),
      section('研究重點', ai.key_points),
      epsTable(ai.quarterly_eps),
      forecastTable(ai.forecast_changes),
      stockTable(ai.stock_views),
      section('風險因素', ai.risks)
    ].filter(Boolean).join('');

    const fullAnalysis = section(
      '完整研究分析',
      ai.detail
    );

    return `
      <div class="raa-v2-header">
        <div>
          <div class="raa-v2-name">
            ${esc(company || ai.title || '研究報告')}

            ${
              ticker
                ? `
                  <span class="raa-v2-ticker">
                    ${esc(ticker)}
                  </span>
                `
                : ''
            }
          </div>

          <div class="raa-v2-broker">
            ${esc(broker)}
            ${date ? ` · ${esc(date)}` : ''}
            · ${esc(reportType)}
          </div>
        </div>

        <span class="raa-badge success">
          AI 已完成
        </span>
      </div>

      ${
        ai.title
          ? `
            <div class="raa-v2-title">
              ${esc(ai.title)}
            </div>
          `
          : ''
      }

      <div class="raa-v2-facts">
        ${fact('評等', rating)}
        ${fact('目標價', targetText)}
        ${fact('原目標價', oldTargetText)}
        ${fact('發布券商', broker)}
      </div>

      ${details}

      ${
        fullAnalysis
          ? `
            <details class="raa-v2-details">
              <summary>展開完整研究分析 ▼</summary>
              ${fullAnalysis}
            </details>
          `
          : ''
      }

      <div class="raa-v2-note">
        來源：既有 AI 解析結果，不重新執行 API
      </div>
    `;
  }

  let data = null;
  let loading = null;
  let queued = false;

  async function load() {
    if (data) return data;
    if (loading) return loading;

    loading = Promise.all([
      fetch('./data/research_ai_plan.json', {
        cache: 'no-store'
      }),
      fetch('./data/research_ai_cache.json', {
        cache: 'no-store'
      })
    ]).then(async ([planResponse, cacheResponse]) => {
      if (!planResponse.ok || !cacheResponse.ok) {
        throw new Error(
          `AI layout data unavailable: ` +
          `${planResponse.status}/${cacheResponse.status}`
        );
      }

      const plan = await planResponse.json();
      const cache = await cacheResponse.json();

      const map = new Map();

      for (const item of plan.items || []) {
        map.set(item.id, item);
      }

      data = { map, cache };

      console.info('[AI_LAYOUT] data loaded', {
        reports: map.size
      });

      return data;
    }).catch(error => {
      loading = null;
      console.error('[AI_LAYOUT] load failed', error);
      throw error;
    });

    return loading;
  }

  function resolveEntry(id, item) {
    if (!data) return null;

    const cache = data.cache;

    let current = id;
    const visited = new Set();

    for (let i = 0; i < 8; i++) {
      if (!current || visited.has(current)) {
        break;
      }

      visited.add(current);

      const entry = cache[current];

      if (!entry) break;

      if (
        entry.status === 'alias' &&
        entry.cache_id
      ) {
        current = entry.cache_id;
        continue;
      }

      return entry;
    }

    if (
      item?.cache_id &&
      !visited.has(item.cache_id)
    ) {
      return cache[item.cache_id] || null;
    }

    return null;
  }

  function refresh() {
    const root = document.getElementById(ROOT_ID);

    if (!root || !data) return;

    let updated = 0;

    for (const element of root.querySelectorAll(
      '.raa-card[data-report-id]'
    )) {
      if (element.dataset.raaLayout === 'v3') {
        continue;
      }

      const id = element.dataset.reportId;

      if (!id) continue;

      const item = data.map.get(id);

      if (!item) {
        console.warn(
          '[AI_LAYOUT] report missing from plan',
          id
        );
        continue;
      }

      const entry = resolveEntry(id, item);

      if (
        !entry ||
        entry.status !== 'success' ||
        !entry.result
      ) {
        continue;
      }

      element.innerHTML = reportCard(item, entry);
      element.dataset.raaLayout = 'v3';

      updated++;
    }

    if (updated) {
      console.info(
        '[AI_LAYOUT] upgraded completed reports',
        updated
      );
    }
  }

  function schedule() {
    if (queued) return;

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
    const root = document.getElementById(ROOT_ID);

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
        .catch(error => {
          console.error(
            '[AI_LAYOUT] refresh failed',
            error
          );
        });
    });

    load()
      .then(schedule)
      .catch(error => {
        console.error(
          '[AI_LAYOUT] initialization failed',
          error
        );
      });

    console.info(
      '[AI_LAYOUT] v3 installed; cache-only, zero API'
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
