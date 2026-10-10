/* AI 選股績效回測：五種策略 + 同期加權／OTC 指數 */
(function () {
  'use strict';

  const $ = s => document.querySelector(s);

  let selectedStrategy = 'baseline';
  let cachedData = null;
  let loadingPromise = null;

  const STRATEGIES = [
    {
      key: 'baseline',
      label: '固定持有',
      description: '固定持有至第 5／10 個交易日收盤',
      summaryKey: 'baseline_summary',
      prefix: 'baseline_'
    },
    {
      key: 'ma10',
      label: '跌破 MA10',
      description: '收盤跌破 10 日均線提前出場',
      summaryKey: 'ma10_summary',
      prefix: ''
    },
    {
      key: 'ma20',
      label: '跌破 MA20',
      description: '收盤跌破 20 日均線提前出場',
      summaryKey: 'ma20_summary',
      prefix: 'ma20_'
    },
    {
      key: 'stop5',
      label: '停損 5%',
      description: '推薦次日起，收盤跌幅達 5% 即提前出場',
      summaryKey: 'stop5_summary',
      prefix: 'stop5_'
    },
    {
      key: 'stop10',
      label: '停損 10%',
      description: '推薦次日起，收盤跌幅達 10% 即提前出場',
      summaryKey: 'stop10_summary',
      prefix: 'stop10_'
    }
  ];

  const esc = v =>
    String(v ?? '').replace(
      /[&<>"']/g,
      c => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[c])
    );

  const finite = v =>
    v !== null &&
    v !== undefined &&
    v !== '' &&
    Number.isFinite(Number(v));

  const fmtPct = v =>
    finite(v)
      ? (Number(v) > 0 ? '+' : '') +
        Number(v).toFixed(2) +
        '%'
      : '—';

  const tone = v =>
    finite(v)
      ? Number(v) >= 0
        ? 'up'
        : 'down'
      : '';

  const info = () =>
    STRATEGIES.find(
      s => s.key === selectedStrategy
    ) || STRATEGIES[0];

  const strategyData = data =>
    data[info().summaryKey] ||
    (selectedStrategy === 'ma10'
      ? data.summary
      : {}) ||
    {};

  /* ========================================
     讀取回測資料
     ======================================== */

  async function loadBacktest() {
    if (cachedData) return cachedData;
    if (loadingPromise) return loadingPromise;

    loadingPromise = (async () => {
      try {
        const response = await fetch(
          './data/ai_backtest.json?v=' + Date.now(),
          { cache: 'no-store' }
        );

        if (!response.ok) {
          throw new Error(
            'HTTP ' + response.status
          );
        }

        cachedData = await response.json();
        return cachedData;

      } catch (e) {
        console.error(
          'AI backtest load failed',
          e
        );
        return {};

      } finally {
        loadingPromise = null;
      }
    })();

    return loadingPromise;
  }

  /* ========================================
     五種策略切換
     ======================================== */

  function strategyButtons() {
    return `
      <div class="ai-bt-strategy-switch">
        ${STRATEGIES.map(s => `
          <button
            type="button"
            class="ai-bt-strategy-btn ${
              selectedStrategy === s.key
                ? 'active'
                : ''
            }"
            data-ai-bt-strategy="${s.key}"
            aria-pressed="${
              selectedStrategy === s.key
            }"
          >
            ${esc(s.label)}
          </button>
        `).join('')}
      </div>
    `;
  }

  /* ========================================
     加權指數／OTC 同期平均漲跌幅

     與 AI 選股使用相同成熟樣本
     不是直接計算回測起日至今漲跌幅
     ======================================== */

  function benchmarkRows(data, days, stockSamples) {
    const period =
      data?.benchmark_summary?.[`${days}d`] || {};

    return `
      <div class="ai-bt-benchmarks">

        ${
          [
            [
              'twse',
              '加權指數同期平均漲跌幅'
            ],
            [
              'tpex',
              'OTC 同期平均漲跌幅'
            ]
          ].map(([market, label]) => {

            const row = period[market] || {};

            const count = Number(
              row.samples || 0
            );

            const complete =
              stockSamples > 0 &&
              count === stockSamples &&
              finite(row.avg_return);

            return `
              <div class="ai-bt-benchmark-row">

                <span>
                  ${label}
                </span>

                <b class="${
                  complete
                    ? tone(row.avg_return)
                    : ''
                }">
                  ${
                    complete
                      ? fmtPct(row.avg_return)
                      : '—'
                  }
                </b>

              </div>
            `;

          }).join('')
        }

      </div>
    `;
  }

  /* ========================================
     5 日／10 日績效卡片
     ======================================== */

  function statCard(title, stat, benchmark, days) {
    const samples = Number(
      stat?.samples || 0
    );

    return `
      <div class="ai-bt-stat">

        <div class="ai-bt-stat-title">
          ${esc(title)}
        </div>

        ${
          samples
            ? `
              <strong class="${
                tone(stat.avg_return)
              }">
                ${fmtPct(stat.avg_return)}
              </strong>

              <div class="ai-bt-stat-sub">

                <span>
                  勝率
                  <b>
                    ${Number(
                      stat.win_rate || 0
                    ).toFixed(1)}%
                  </b>
                </span>

                <span>
                  中位數
                  <b class="${
                    tone(stat.median_return)
                  }">
                    ${fmtPct(stat.median_return)}
                  </b>
                </span>

                <span>
                  樣本
                  <b>${samples}</b>
                </span>

              </div>
            `
            : `
              <div class="ai-bt-pending">
                尚無已滿期樣本
              </div>
            `
        }

        ${
          benchmarkRows(
            benchmark,
            days,
            samples
          )
        }

      </div>
    `;
  }

  /* ========================================
     Top 5／10／20
     ======================================== */

  function bucketRow(label, data) {
    return `
      <div class="ai-bt-bucket-row">

        <b>${esc(label)}</b>

        <span class="${
          tone(data?.['5d']?.avg_return)
        }">
          ${
            fmtPct(
              data?.['5d']?.avg_return
            )
          }
        </span>

        <span class="${
          tone(data?.['10d']?.avg_return)
        }">
          ${
            fmtPct(
              data?.['10d']?.avg_return
            )
          }
        </span>

      </div>
    `;
  }

  /* ========================================
     最近三個選股日
     ======================================== */

  function latestRecords(records) {
    const dates = [
      ...new Set(
        records
          .map(r => r.selection_date)
          .filter(Boolean)
      )
    ]
      .sort()
      .reverse()
      .slice(0, 3);

    return records
      .filter(
        r => dates.includes(
          r.selection_date
        )
      )
      .sort((a, b) =>
        String(b.selection_date).localeCompare(
          String(a.selection_date)
        ) ||
        String(a.market).localeCompare(
          String(b.market)
        ) ||
        Number(a.rank || 999) -
        Number(b.rank || 999)
      );
  }

  /* ========================================
     個股策略績效
     ======================================== */

  function recordPerformance(record, days) {
    const prefix = info().prefix;

    return {
      value: record[
        `${prefix}return_${days}d`
      ],
      status: record[
        `${prefix}status_${days}d`
      ]
    };
  }

  function recordRow(record) {
    const market =
      record.market === 'twse'
        ? '上市'
        : '上櫃';

    const p5 = recordPerformance(
      record,
      5
    );

    const p10 = recordPerformance(
      record,
      10
    );

    return `
      <div class="ai-bt-record-row">

        <div class="ai-bt-record-name">

          <small>
            ${esc(record.selection_date)}
            · ${market}
            · #${esc(record.rank)}
          </small>

          <b>
            ${esc(
              record.name ||
              record.ticker ||
              '—'
            )}
          </b>

          <span>
            ${esc(record.ticker)}
          </span>

        </div>

        <div>
          <small>5日</small>

          <b class="${tone(p5.value)}">
            ${
              p5.status === 'complete'
                ? fmtPct(p5.value)
                : '進行中'
            }
          </b>
        </div>

        <div>
          <small>10日</small>

          <b class="${tone(p10.value)}">
            ${
              p10.status === 'complete'
                ? fmtPct(p10.value)
                : '進行中'
            }
          </b>
        </div>

      </div>
    `;
  }

  /* ========================================
     主畫面
     ======================================== */

  async function render() {
    const aiCards = $('#aiCards');

    if (!aiCards) return;

    let panel = $('#aiBacktestPanel');

    if (!panel) {
      panel = document.createElement(
        'section'
      );

      panel.id = 'aiBacktestPanel';
      panel.className = 'ai-backtest-panel';

      aiCards.parentNode.insertBefore(
        panel,
        aiCards
      );
    }

    const data = await loadBacktest();

    const summary =
      strategyData(data).all || {};

    const buckets =
      strategyData(data).rank_buckets || {};

    const records = latestRecords(
      data.records || []
    );

    panel.innerHTML = `

      <style>

        #aiBacktestPanel
        .ai-bt-strategy-switch {
          display: grid;
          grid-template-columns:
            repeat(3, minmax(0, 1fr));
          gap: 8px;
          margin: 16px 0;
          width: 100%;
        }

        #aiBacktestPanel
        .ai-bt-strategy-btn {
          appearance: none;
          min-width: 0;
          padding: 12px 5px;
          border: 1px solid
            var(--line, #dce3ec);
          border-radius: 12px;
          background:
            var(--card, #f5f7fa);
          color:
            var(--text, #334155);
          font-size: 13px;
          font-weight: 700;
          line-height: 1.4;
          text-align: center;
          cursor: pointer;
          transition:
            background .15s,
            border-color .15s,
            color .15s;
        }

        #aiBacktestPanel
        .ai-bt-strategy-btn.active {
          background: #2563eb;
          border-color: #2563eb;
          color: #fff;
        }

        #aiBacktestPanel
        .ai-bt-strategy-btn:focus-visible {
          outline: 2px solid #60a5fa;
          outline-offset: 2px;
        }

        #aiBacktestPanel
        .ai-bt-strategy-desc {
          margin: 0 0 15px;
          color:
            var(--muted, #64748b);
          font-size: 13px;
          line-height: 1.5;
        }

        #aiBacktestPanel
        .ai-bt-benchmarks {
          margin-top: 14px;
          padding-top: 12px;
          border-top: 1px solid
            var(--line, #dce3ec);
          display: grid;
          gap: 8px;
        }

        #aiBacktestPanel
        .ai-bt-benchmark-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          font-size: 12px;
          line-height: 1.45;
          color:
            var(--muted, #64748b);
        }

        #aiBacktestPanel
        .ai-bt-benchmark-row span {
          min-width: 0;
          flex: 1;
        }

        #aiBacktestPanel
        .ai-bt-benchmark-row b {
          white-space: nowrap;
          font-size: 13px;
          color:
            var(--text, #334155);
        }

        #aiBacktestPanel
        .ai-bt-benchmark-row b.up {
          color: #dc2626;
        }

        #aiBacktestPanel
        .ai-bt-benchmark-row b.down {
          color: #059669;
        }

        @media (max-width: 400px) {

          #aiBacktestPanel
          .ai-bt-strategy-switch {
            gap: 6px;
          }

          #aiBacktestPanel
          .ai-bt-strategy-btn {
            padding: 11px 3px;
            font-size: 12px;
          }

          #aiBacktestPanel
          .ai-bt-benchmark-row {
            font-size: 11px;
          }

          #aiBacktestPanel
          .ai-bt-benchmark-row b {
            font-size: 12px;
          }

        }

      </style>

      <div class="ai-bt-head">

        <div>

          <span class="kicker">
            PERFORMANCE BACKTEST
          </span>

          <h2>
            AI 選股績效回測
          </h2>

          <p>
            ${
              data.start_date
                ? '自 ' +
                  esc(data.start_date) +
                  ' 起累積'
                : '尚未開始累積'
            }
            ｜以選股基準日收盤價計算
          </p>

        </div>

        <span class="badge">
          交易日制
        </span>

      </div>

      ${strategyButtons()}

      <div class="ai-bt-strategy-desc">
        ${esc(info().description)}
      </div>

      <div class="ai-bt-stats">

        ${
          statCard(
            '5日績效',
            summary['5d'],
            data,
            5
          )
        }

        ${
          statCard(
            '10日績效',
            summary['10d'],
            data,
            10
          )
        }

      </div>

      <div class="ai-bt-rank-card">

        <div class="ai-bt-rank-head">

          <b>
            排名分組平均績效
          </b>

          <span>
            5日 / 10日
          </span>

        </div>

        ${
          bucketRow(
            'Top 5',
            buckets.top5
          )
        }

        ${
          bucketRow(
            'Top 10',
            buckets.top10
          )
        }

        ${
          bucketRow(
            'Top 20',
            buckets.top20
          )
        }

      </div>

      <details class="ai-bt-history">

        <summary>
          最近選股紀錄

          <span>
            查看明細 ▾
          </span>
        </summary>

        <div class="ai-bt-history-body">

          ${
            records.length
              ? records
                  .map(recordRow)
                  .join('')
              : `
                <div class="empty">
                  第一次執行更新後會開始累積回測紀錄
                </div>
              `
          }

        </div>

      </details>

      <div class="ai-bt-note">

        5日／10日皆指推薦後第5／10個交易日，
        不含週末及休市日

        <br><br>

        五種策略使用相同已滿期樣本

        <br><br>

        加權指數與 OTC 同期平均漲跌幅：
        逐筆依推薦日收盤至第5／10個交易日收盤計算，
        並依相同成熟選股訊號權重平均；
        官方指數資料未齊全時顯示 —

        <br><br>

        MA10／MA20從推薦次一交易日開始檢查，
        收盤跌破均線即按當日收盤價模擬出場

        <br><br>

        停損 5%／10% 同樣從推薦次一交易日開始檢查，
        收盤跌幅達停損門檻時按當日收盤價模擬出場

        <br><br>

        提前出場的報酬仍須等觀察期滿才納入統計

      </div>
    `;

    panel
      .querySelectorAll(
        '[data-ai-bt-strategy]'
      )
      .forEach(button => {

        button.addEventListener(
          'click',
          () => {
            const next =
              button.dataset.aiBtStrategy;

            if (
              !next ||
              next === selectedStrategy
            ) {
              return;
            }

            selectedStrategy = next;
            render();
          }
        );

      });
  }

  /* ========================================
     初始化
     ======================================== */

  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      render
    );
  } else {
    render();
  }

  setTimeout(render, 1200);

})();
