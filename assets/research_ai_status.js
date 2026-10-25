/* Temporary Excel AI audit panel. Read-only: no API, no mutation of ledger. */
(() => {
  'use strict';

  const host = document.getElementById('reports');
  if (!host) return;

  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[c]));

  const text = x =>
    Array.isArray(x)
      ? x.map(text).join('\n')
      : typeof x === 'object' && x
        ? JSON.stringify(x, null, 2)
        : String(x ?? '');

  const cls = s => ({
    success: 'success',
    unknown: 'unknown',
    api_reserved: 'unknown',
    new: 'pending',
    cached: 'cached',
    broker_duplicate: 'duplicate',
    excel_duplicate: 'duplicate',
    needs_review: 'review'
  }[s] || 'review');

  const box = document.createElement('section');
  box.id = 'researchAiAudit';

  box.innerHTML = `
    <button type="button" id="raaToggle" aria-expanded="false">
      🧪 AI 處理紀錄（暫時） ▾
    </button>

    <div id="raaPanel" hidden>
      <div class="raa-caption">
        僅供驗證 Excel 報告處理狀態。
        原券商報告不計入；狀態不明禁止自動重跑。
        資料來自最新已提交的 AI 計畫與持久化快取。
      </div>

      <div class="raa-filters"></div>

      <input
        id="raaSearch"
        type="search"
        placeholder="搜尋公司、券商、日期"
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
      font: 14px/1.65 -apple-system, BlinkMacSystemFont,
        'Noto Sans TC', sans-serif;
      color: #243246;
    }

    #researchAiAudit * {
      box-sizing: border-box;
    }

    #raaToggle {
      width: 100%;
      text-align: left;
      background: #e9f0ff;
      border: 1px solid #a8c1eb;
      color: #194f9d;
      padding: 11px 15px;
      border-radius: 12px;
      font-weight: 750;
    }

    #raaPanel {
      padding: 12px 0;
    }

    #raaPanel[hidden] {
      display: none;
    }

    .raa-caption {
      color: #64748b;
      font-size: 12px;
      margin-bottom: 10px;
    }

    .raa-filters {
      display: flex;
      gap: 7px;
      overflow-x: auto;
      padding-bottom: 10px;
    }

    .raa-filters button {
      white-space: nowrap;
      background: #fff;
      color: #263a56;
      border: 1px solid #cbd5e1;
      border-radius: 20px;
      padding: 7px 11px;
    }

    .raa-filters button.active {
      background: #205fcd;
      color: #fff;
      border-color: #205fcd;
    }

    #raaSearch {
      width: 100%;
      background: #fff;
      color: #172033;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      padding: 10px;
      margin-bottom: 8px;
    }

    #raaStats {
      color: #64748b;
      font-size: 12px;
      margin: 7px 0;
    }

    .raa-card {
      background: #fff;
      border: 1px solid #dce3eb;
      border-radius: 14px;
      padding: 14px;
      margin: 10px 0;
      overflow-wrap: anywhere;
    }

    .raa-card h3 {
      font-size: 17px;
      line-height: 1.5;
      margin: 4px 0;
    }

    .raa-card .raa-meta {
      font-size: 12px;
      color: #64748b;
    }

    .raa-card .raa-badge {
      display: inline-block;
      font-size: 12px;
      border-radius: 20px;
      padding: 3px 9px;
      background: #f1f5f9;
    }

    .raa-card .raa-badge.success {
      background: #e5f7eb;
      color: #15703a;
    }

    .raa-card .raa-badge.unknown {
      background: #fff1df;
      color: #9a5400;
    }

    .raa-card .raa-badge.duplicate {
      background: #eaf0fb;
      color: #2650a5;
    }

    .raa-card details {
      margin-top: 10px;
    }

    .raa-card summary {
      cursor: pointer;
      color: #205fcd;
      font-weight: 700;
    }

    .raa-card .raa-section {
      border-top: 1px solid #e2e8f0;
      margin-top: 12px;
      padding-top: 10px;
      white-space: pre-wrap;
      line-height: 1.75;
    }

    .raa-card .raa-section strong {
      display: block;
      margin-bottom: 5px;
      color: #163b6a;
    }

    .raa-card table {
      width: 100%;
      border-collapse: collapse;
    }

    .raa-card td,
    .raa-card th {
      border-bottom: 1px solid #e2e8f0;
      padding: 6px;
      text-align: left;
    }

    #raaMore {
      width: 100%;
      padding: 10px;
      background: #fff;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
    }
  `;

  document.head.appendChild(style);

  const merged = document.getElementById('researchMergedPanel');
  (merged || document.getElementById('reportList')).before(box);

  const $ = q => box.querySelector(q);

  const filters = [
    ['all', '全部'],
    ['success', 'AI 已完成'],
    ['pending', '未執行'],
    ['unknown', '失敗／狀態不明'],
    ['duplicate', '已去重／沿用'],
    ['review', '待確認']
  ];

  let loaded = false;
  let records = [];
  let mode = 'all';
  let term = '';
  let limit = 30;

  const state = (r, cache) => {
    if (r.status === 'cached') {
      return cache?.status === 'success'
        ? 'success'
        : 'unknown';
    }

    return cls(r.status);
  };

  const sections = [
    ['summary', '研究摘要'],
    ['key_points', '研究重點'],
    ['detail', '完整解析'],
    ['forecast_changes', '財測調整'],
    ['risks', '風險'],
    ['push_reason', '核心觀點']
  ];

  function card(r) {
    const s = r._state;
    const ai = r._ai;

    const labels = {
      success: 'AI 已完成',
      pending: '未執行 API',
      unknown: '失敗／狀態不明（禁止自動重跑）',
      duplicate: '已去重／沿用',
      review: '待人工確認'
    };

    const details = ai && s === 'success'
      ? `
        <details>
          <summary>查看原券商格式 AI 解析 ▼</summary>

          ${[
            ['rating', '評等'],
            ['target_price_new', '目標價']
          ]
            .filter(([k]) => ai[k] != null && ai[k] !== '')
            .map(([k, n]) => `
              <div class="raa-section">
                <strong>${n}</strong>
                ${esc(ai[k])}
              </div>
            `)
            .join('')}

          ${sections
            .filter(([k]) =>
              ai[k] &&
              (!Array.isArray(ai[k]) || ai[k].length)
            )
            .map(([k, n]) => `
              <div class="raa-section">
                <strong>${n}</strong>
                ${esc(text(ai[k]))}
              </div>
            `)
            .join('')}

          ${
            Array.isArray(ai.quarterly_eps) &&
            ai.quarterly_eps.length
              ? `
                <div class="raa-section">
                  <strong>券商單季 EPS 預估</strong>

                  <table>
                    ${ai.quarterly_eps.map(x => `
                      <tr>
                        <th>${esc(x.period)}</th>
                        <td>${esc(x.eps)}</td>
                      </tr>
                    `).join('')}
                  </table>
                </div>
              `
              : ''
          }
        </details>
      `
      : '';

    return `
      <article class="raa-card">
        <span class="raa-badge ${s}">
          ${labels[s]}
        </span>

        <h3>
          ${esc(ai?.title || r.company || '研究報告')}
        </h3>

        <div class="raa-meta">
          ${esc(r.company)} ·
          ${esc(r.source)} ·
          ${esc(r.date)}
        </div>

        ${
          ai?.push_reason
            ? `
              <div class="raa-section">
                ${esc(ai.push_reason)}
              </div>
            `
            : ''
        }

        ${
          s === 'unknown'
            ? `
              <div class="raa-section">
                錯誤：
                ${esc(
                  r._cache?.error_type ||
                  r.previous_status ||
                  '未記錄詳細原因'
                )}
                ；不自動重跑
              </div>
            `
            : ''
        }

        ${
          s === 'duplicate'
            ? `
              <div class="raa-section">
                原因：
                ${esc(
                  r.reason ||
                  r.match_reason ||
                  r.evidence ||
                  r.status
                )}
                ；原券商報告優先
              </div>
            `
            : ''
        }

        ${details}
      </article>
    `;
  }

  function render() {
    const counts = Object.fromEntries(
      filters.map(([k]) => [
        k,
        k === 'all'
          ? records.length
          : records.filter(r => r._state === k).length
      ])
    );

    $('.raa-filters').innerHTML = filters
      .map(([k, label]) => `
        <button
          type="button"
          data-mode="${k}"
          class="${mode === k ? 'active' : ''}"
        >
          ${label}（${counts[k]}）
        </button>
      `)
      .join('');

    const match = records.filter(r =>
      (mode === 'all' || r._state === mode) &&
      [
        r.company,
        r.source,
        r.date,
        r.id,
        r._ai?.title
      ]
        .join(' ')
        .toLowerCase()
        .includes(term.toLowerCase())
    );

    $('#raaStats').textContent =
      `符合 ${match.length} 筆` +
      `｜顯示 ${Math.min(limit, match.length)} 筆` +
      `｜資料為最近一次已提交的計畫，` +
      `不代表即時執行中進度`;

    $('#raaRows').innerHTML =
      match.slice(0, limit).map(card).join('') ||
      '<p>沒有符合條件的紀錄。</p>';

    $('#raaMore').hidden = limit >= match.length;
  }

  async function load() {
    $('#raaStats').textContent = '讀取 AI 紀錄中…';

    const [planResp, cacheResp] = await Promise.all([
      fetch('./data/research_ai_plan.json', {
        cache: 'no-store'
      }),
      fetch('./data/research_ai_cache.json', {
        cache: 'no-store'
      })
    ]);

    if (!planResp.ok || !cacheResp.ok) {
      throw Error(
        `計畫 ${planResp.status}，快取 ${cacheResp.status}`
      );
    }

    const plan = await planResp.json();
    const cache = await cacheResp.json();

    if (
      !Array.isArray(plan.items) ||
      !cache ||
      typeof cache !== 'object'
    ) {
      throw Error('AI 紀錄格式錯誤');
    }

    records = plan.items.map(r => {
      const c =
        cache[r.id] ||
        cache[r.cache_id] ||
        null;

      return {
        ...r,
        _cache: c,
        _state: state(r, c),
        _ai: c?.status === 'success'
          ? c.result
          : null
      };
    });

    loaded = true;

    console.info('[RESEARCH_AI_AUDIT] loaded', {
      total: records.length,
      counts: plan.counts
    });

    render();
  }

  $('#raaToggle').addEventListener('click', async () => {
    const p = $('#raaPanel');

    p.hidden = !p.hidden;

    $('#raaToggle').setAttribute(
      'aria-expanded',
      String(!p.hidden)
    );

    if (!p.hidden) {
      try {
        await load();
      } catch (e) {
        console.error(
          '[RESEARCH_AI_AUDIT] load failed',
          e
        );

        $('#raaStats').textContent =
          '載入失敗：' + e.message;
      }
    }
  });

  $('.raa-filters').addEventListener('click', e => {
    const b = e.target.closest('[data-mode]');
    if (!b) return;

    mode = b.dataset.mode;
    limit = 30;
    render();
  });

  $('#raaSearch').addEventListener('input', e => {
    term = e.target.value;
    limit = 30;

    if (loaded) render();
  });

  $('#raaMore').addEventListener('click', () => {
    limit += 30;
    render();
  });

  console.info(
    '[RESEARCH_AI_AUDIT] temporary UI ready; read-only'
  );
})();
