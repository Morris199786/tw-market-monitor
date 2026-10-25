/* Temporary research AI status UI.
 * Read-only. Never calls OpenAI or modifies the processing ledger.
 */
(() => {
  'use strict';

  const host = document.getElementById('reports');
  if (!host) {
    console.error('[RESEARCH_AI] #reports not found');
    return;
  }

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

  const box = document.createElement('section');
  box.id = 'researchAiAudit';

  box.innerHTML = `
    <button id="raaToggle" type="button" aria-expanded="false">
      🧪 AI 處理紀錄（暫時） ▾
    </button>

    <div id="raaPanel" hidden>
      <p class="raa-caption">
        顯示 Excel 報告的 AI 處理狀態。
        已完成的報告使用既有 AI 快取，不重新解析。
      </p>

      <div class="raa-filters"></div>

      <input
        id="raaSearch"
        type="search"
        placeholder="搜尋公司、股票代號、券商、日期"
      >

      <div id="raaStats"></div>
      <div id="raaRows"></div>

      <button id="raaMore" type="button" hidden>
        顯示更多
      </button>
    </div>
  `;

  const style = document.createElement('style');

  style.textContent = `
    #researchAiAudit {
      margin: 12px 0 18px;
      font: 14px/1.55 -apple-system, BlinkMacSystemFont,
        "Noto Sans TC", sans-serif;
      color: #243246;
    }

    #researchAiAudit * {
      box-sizing: border-box;
    }

    #raaToggle {
      width: 100%;
      padding: 12px 15px;
      border-radius: 12px;
      border: 1px solid #a8c1eb;
      background: #e9f0ff;
      color: #194f9d;
      text-align: left;
      font-weight: 750;
      cursor: pointer;
    }

    #raaPanel {
      padding: 12px 0;
    }

    #raaPanel[hidden] {
      display: none;
    }

    .raa-caption {
      margin: 0 0 12px;
      color: #64748b;
      font-size: 12px;
    }

    .raa-filters {
      display: flex;
      gap: 7px;
      overflow-x: auto;
      padding-bottom: 10px;
    }

    .raa-filters button {
      flex-shrink: 0;
      padding: 7px 11px;
      border-radius: 20px;
      border: 1px solid #cbd5e1;
      background: #fff;
      color: #263a56;
      cursor: pointer;
    }

    .raa-filters button.active {
      background: #205fcd;
      border-color: #205fcd;
      color: white;
    }

    #raaSearch {
      width: 100%;
      padding: 11px;
      margin-bottom: 8px;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      background: #fff;
      color: #172033;
    }

    #raaStats {
      margin: 8px 0;
      color: #64748b;
      font-size: 12px;
    }

    #researchAiAudit .raa-card {
      margin: 10px 0;
      padding: 15px;
      border: 1px solid #dce3eb;
      border-radius: 14px;
      background: #fff;
      overflow-wrap: anywhere;
    }

    #researchAiAudit .raa-card h3 {
      margin: 5px 0;
      font-size: 18px;
      line-height: 1.4;
    }

    #researchAiAudit .raa-meta {
      margin: 5px 0;
      color: #64748b;
      font-size: 12px;
    }

    #researchAiAudit .raa-badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 20px;
      background: #f1f5f9;
      color: #475569;
      font-size: 12px;
      font-weight: 700;
    }

    #researchAiAudit .raa-badge.success {
      background: #e5f7eb;
      color: #15703a;
    }

    #researchAiAudit .raa-badge.unknown {
      background: #fff1df;
      color: #9a5400;
    }

    #researchAiAudit .raa-badge.duplicate {
      background: #eaf0fb;
      color: #2650a5;
    }

    #researchAiAudit .raa-section {
      margin: 12px 0 0;
      padding: 10px 0 0;
      border-top: 1px solid #e2e8f0;
      line-height: 1.6;
    }

    #researchAiAudit .raa-section strong {
      display: block;
      margin-bottom: 5px;
      color: #163b6a;
    }

    #researchAiAudit .raa-section p {
      margin: 0 0 7px;
    }

    #researchAiAudit details {
      margin-top: 10px;
    }

    #researchAiAudit summary {
      padding: 7px 0;
      color: #205fcd;
      font-weight: 700;
      cursor: pointer;
    }

    #raaMore {
      width: 100%;
      padding: 11px;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      background: #fff;
      cursor: pointer;
    }
  `;

  document.head.appendChild(style);

  const anchor =
    document.getElementById('researchMergedPanel') ||
    document.getElementById('reportList');

  if (anchor) {
    anchor.before(box);
  } else {
    host.prepend(box);
  }

  const $ = selector => box.querySelector(selector);

  const filters = [
    ['all', '全部'],
    ['success', 'AI 已完成'],
    ['pending', '未執行'],
    ['unknown', '失敗／狀態不明'],
    ['duplicate', '已去重／沿用'],
    ['review', '待確認']
  ];

  const labels = {
    success: 'AI 已完成',
    pending: '未執行 API',
    unknown: '狀態不明（禁止自動重跑）',
    duplicate: '已去重／沿用',
    review: '待人工確認'
  };

  let records = [];
  let loaded = false;
  let mode = 'all';
  let term = '';
  let limit = 30;

  function state(record, cache) {
    if (cache?.status === 'success') {
      return 'success';
    }

    if (
      cache?.status === 'unknown' ||
      cache?.status === 'api_reserved'
    ) {
      return 'unknown';
    }

    if (
      record.status === 'broker_duplicate' ||
      record.status === 'excel_duplicate'
    ) {
      return 'duplicate';
    }

    if (record.status === 'cached') {
      return 'unknown';
    }

    if (record.status === 'new') {
      return 'pending';
    }

    return 'review';
  }

  function card(record) {
    const status = record._state;
    const ai = record._ai;

    const name =
      ai?.name ||
      record.company ||
      ai?.title ||
      '研究報告';

    const ticker =
      ai?.ticker ||
      record.ticker ||
      '';

    const broker =
      ai?.broker ||
      record.source ||
      '';

    const title = ai?.title || '';

    const summary = ai?.summary || '';

    const error = record._cache?.error_type ||
      record.previous_status ||
      '未記錄詳細原因';

    /*
     * Important:
     * data-report-id is an internal HTML attribute.
     * It is NOT rendered as visible text.
     *
     * The layout script uses it to find the correct
     * previously saved AI analysis.
     */
    return `
      <article
        class="raa-card"
        data-report-id="${esc(record.id)}"
        data-raa-state="${esc(status)}"
      >
        <span class="raa-badge ${esc(status)}">
          ${esc(labels[status])}
        </span>

        <h3>
          ${esc(name)}
          ${ticker
            ? `<span class="raa-ticker">${esc(ticker)}</span>`
            : ''}
        </h3>

        <div class="raa-meta">
          ${esc(broker)}
          ${record.date ? ` · ${esc(record.date)}` : ''}
        </div>

        ${
          title
            ? `<div class="raa-report-title">${esc(title)}</div>`
            : ''
        }

        ${
          status === 'success'
            ? `
              <div class="raa-ai-placeholder">
                ${esc(summary)}
              </div>
            `
            : ''
        }

        ${
          status === 'unknown'
            ? `
              <div class="raa-section">
                <strong>處理狀態</strong>
                ${esc(error)}。為避免重複消耗 Credit，
                不會自動重新執行。
              </div>
            `
            : ''
        }

        ${
          status === 'duplicate'
            ? `
              <div class="raa-section">
                <strong>去重結果</strong>
                ${esc(
                  record.reason ||
                  record.match_reason ||
                  record.status
                )}
                <br>
                重複報告不重新執行 AI。
              </div>
            `
            : ''
        }
      </article>
    `;
  }

  function render() {
    const counts = {};

    for (const [key] of filters) {
      counts[key] = key === 'all'
        ? records.length
        : records.filter(r => r._state === key).length;
    }

    $('.raa-filters').innerHTML = filters.map(
      ([key, label]) => `
        <button
          type="button"
          data-mode="${esc(key)}"
          class="${mode === key ? 'active' : ''}"
        >
          ${esc(label)}（${counts[key]}）
        </button>
      `
    ).join('');

    const matched = records.filter(record => {
      if (mode !== 'all' && record._state !== mode) {
        return false;
      }

      const searchText = [
        record.company,
        record.ticker,
        record.source,
        record.date,
        record._ai?.title,
        record._ai?.name,
        record._ai?.ticker
      ].join(' ').toLowerCase();

      return searchText.includes(term.toLowerCase());
    });

    $('#raaStats').textContent =
      `符合 ${matched.length} 筆` +
      `｜顯示 ${Math.min(limit, matched.length)} 筆`;

    $('#raaRows').innerHTML =
      matched.slice(0, limit).map(card).join('') ||
      '<p>沒有符合條件的紀錄。</p>';

    $('#raaMore').hidden = limit >= matched.length;

    console.info('[RESEARCH_AI] render', {
      mode,
      matched: matched.length,
      displayed: Math.min(limit, matched.length)
    });
  }

  async function load() {
    $('#raaStats').textContent = '正在讀取 AI 紀錄…';

    const [planResponse, cacheResponse] = await Promise.all([
      fetch('./data/research_ai_plan.json', {
        cache: 'no-store'
      }),
      fetch('./data/research_ai_cache.json', {
        cache: 'no-store'
      })
    ]);

    if (!planResponse.ok || !cacheResponse.ok) {
      throw new Error(
        `資料載入失敗：plan=${planResponse.status}, ` +
        `cache=${cacheResponse.status}`
      );
    }

    const plan = await planResponse.json();
    const cache = await cacheResponse.json();

    if (!Array.isArray(plan.items)) {
      throw new Error('research_ai_plan.json 格式錯誤');
    }

    if (!cache || typeof cache !== 'object') {
      throw new Error('research_ai_cache.json 格式錯誤');
    }

    function resolveCache(record) {
      let id = record.id;
      const visited = new Set();

      for (let i = 0; i < 8; i++) {
        if (!id || visited.has(id)) {
          break;
        }

        visited.add(id);

        const entry = cache[id];

        if (!entry) {
          break;
        }

        if (
          entry.status === 'alias' &&
          entry.cache_id
        ) {
          id = entry.cache_id;
          continue;
        }

        return entry;
      }

      if (
        record.cache_id &&
        !visited.has(record.cache_id)
      ) {
        return cache[record.cache_id] || null;
      }

      return null;
    }

    records = plan.items.map(record => {
      const entry = resolveCache(record);

      return {
        ...record,
        _cache: entry,
        _state: state(record, entry),
        _ai: entry?.status === 'success'
          ? entry.result
          : null
      };
    });

    loaded = true;

    console.info('[RESEARCH_AI] loaded', {
      total: records.length,
      success: records.filter(
        r => r._state === 'success'
      ).length,
      unknown: records.filter(
        r => r._state === 'unknown'
      ).length
    });

    render();
  }

  $('#raaToggle').addEventListener('click', async () => {
    const panel = $('#raaPanel');

    panel.hidden = !panel.hidden;

    $('#raaToggle').setAttribute(
      'aria-expanded',
      String(!panel.hidden)
    );

    if (!panel.hidden) {
      try {
        await load();
      } catch (error) {
        console.error('[RESEARCH_AI] load failed', error);
        $('#raaStats').textContent =
          `載入失敗：${error.message}`;
      }
    }
  });

  $('.raa-filters').addEventListener('click', event => {
    const button = event.target.closest('[data-mode]');
    if (!button) return;

    mode = button.dataset.mode;
    limit = 30;

    if (loaded) render();
  });

  $('#raaSearch').addEventListener('input', event => {
    term = event.target.value;
    limit = 30;

    if (loaded) render();
  });

  $('#raaMore').addEventListener('click', () => {
    limit += 30;
    render();
  });

  console.info(
    '[RESEARCH_AI] temporary status UI installed; zero API'
  );
})();
