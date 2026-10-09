/* =========================================================
   AI 選股績效回測
   固定持有 / 跌破 MA10 / 跌破 MA20
   5 日與 10 日使用相同成熟樣本
   ========================================================= */

(function () {
  const $ = s => document.querySelector(s);

  const fmt = v =>
    v == null || !Number.isFinite(Number(v))
      ? '—'
      : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(2)}%`;

  const tone = v =>
    v == null
      ? ''
      : Number(v) >= 0
        ? 'up'
        : 'down';

  const esc = s =>
    String(s ?? '').replace(
      /[&<>"']/g,
      c => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[c])
    );

  /* ===============================
     績效卡片
     =============================== */

  const statCard = (title, s) => {
    const n = Number(s?.samples || 0);

    return `
      <div class="ai-bt-stat">

        <div class="ai-bt-stat-title">
          ${esc(title)}
        </div>

        ${
          n
            ? `
              <strong class="${tone(s.avg_return)}">
                ${fmt(s.avg_return)}
              </strong>

              <div class="ai-bt-stat-sub">

                <span>
                  勝率
                  <b>
                    ${Number(s.win_rate || 0).toFixed(1)}%
                  </b>
                </span>

                <span>
                  中位數
                  <b class="${tone(s.median_return)}">
                    ${fmt(s.median_return)}
                  </b>
                </span>

                <span>
                  樣本
                  <b>${n}</b>
                </span>

              </div>
            `
            : `
              <div class="ai-bt-pending">
                尚無已滿期樣本
              </div>
            `
        }

      </div>
    `;
  };

  /* ===============================
     Top 5 / 10 / 20 排名績效
     =============================== */

  const bucketRow = (label, d) => `
    <div class="ai-bt-bucket-row">

      <b>${esc(label)}</b>

      <span class="${tone(d?.['5d']?.avg_return)}">
        ${fmt(d?.['5d']?.avg_return)}
      </span>

      <span class="${tone(d?.['10d']?.avg_return)}">
        ${fmt(d?.['10d']?.avg_return)}
      </span>

    </div>
  `;

  /* ===============================
     最近三個選股日紀錄
     =============================== */

  const latestRecords = records => {
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
      .filter(r => dates.includes(r.selection_date))
      .sort(
        (a, b) =>
          String(b.selection_date).localeCompare(
            String(a.selection_date)
          ) ||
          String(a.market).localeCompare(
            String(b.market)
          ) ||
          Number(a.rank || 999) -
            Number(b.rank || 999)
      );
  };

  /* ===============================
     個股回測紀錄
     =============================== */

  const recordRow = r => `
    <div class="ai-bt-record-row">

      <div class="ai-bt-record-name">

        <small>
          ${esc(r.selection_date)}
          · ${r.market === 'twse' ? '上市' : '上櫃'}
          · #${esc(r.rank)}
        </small>

        <b>
          ${esc(r.name || r.ticker)}
        </b>

        <span>
          ${esc(r.ticker)}
        </span>

      </div>

      <div>

        <small>MA10 5日</small>

        <b class="${tone(r.return_5d)}">
          ${
            r.status_5d === 'complete'
              ? fmt(r.return_5d)
              : '進行中'
          }
        </b>

      </div>

      <div>

        <small>MA20 5日</small>

        <b class="${tone(r.ma20_return_5d)}">
          ${
            r.ma20_status_5d === 'complete'
              ? fmt(r.ma20_return_5d)
              : '進行中'
          }
        </b>

      </div>

    </div>
  `;

  /* ===============================
     主畫面
     =============================== */

  async function render() {
    const aiCards = $('#aiCards');

    if (!aiCards) return;

    let panel = $('#aiBacktestPanel');

    if (!panel) {
      panel = document.createElement('section');

      panel.id = 'aiBacktestPanel';
      panel.className = 'ai-backtest-panel';

      aiCards.parentNode.insertBefore(
        panel,
        aiCards
      );
    }

    /* 讀取最新回測資料 */

    let d = {};

    try {
      const res = await fetch(
        './data/ai_backtest.json?v=' + Date.now(),
        {
          cache: 'no-store'
        }
      );

      if (res.ok) {
        d = await res.json();
      }

    } catch (e) {
      console.error(
        'AI backtest load failed',
        e
      );
    }

    /* 三種回測策略 */

    const strategies = [
      [
        '固定持有',
        d.baseline_summary
      ],
      [
        '跌破 MA10 出場',
        d.ma10_summary || d.summary
      ],
      [
        '跌破 MA20 出場',
        d.ma20_summary
      ]
    ];

    const records = latestRecords(
      d.records || []
    );

    /* 畫面內容 */

    panel.innerHTML = `

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
              d.start_date
                ? `自 ${esc(d.start_date)} 起累積`
                : '尚未開始累積'
            }
            ｜以選股基準日收盤價計算
          </p>

        </div>

        <span class="badge">
          交易日制
        </span>

      </div>

      ${strategies.map(([label, data]) => `

        <div class="ai-bt-rank-card">

          <div class="ai-bt-rank-head">

            <b>
              ${esc(label)}
            </b>

            <span>
              5日 / 10日
            </span>

          </div>

          <div class="ai-bt-stats">

            ${statCard(
              '5日績效',
              data?.all?.['5d']
            )}

            ${statCard(
              '10日績效',
              data?.all?.['10d']
            )}

          </div>

          ${bucketRow(
            'Top 5',
            data?.rank_buckets?.top5
          )}

          ${bucketRow(
            'Top 10',
            data?.rank_buckets?.top10
          )}

          ${bucketRow(
            'Top 20',
            data?.rank_buckets?.top20
          )}

        </div>

      `).join('')}

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
              ? records.map(recordRow).join('')
              : `
                <div class="empty">
                  第一次執行更新後會開始累積回測紀錄
                </div>
              `
          }

        </div>

      </details>

      <div class="ai-bt-note">

        5日／10日皆為推薦後第5／10個交易日，
        三種策略只統計相同已滿期樣本。

        跌破均線從推薦次日開始判斷，
        按當日收盤價模擬出場；

        即使提前賣出，
        仍須等觀察期滿才納入統計。

        MA10／MA20採最近10／20筆有效收盤價

      </div>

    `;
  }

  /* ===============================
     初始化
     =============================== */

  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      render
    );
  } else {
    render();
  }

  /*
    app.js 的 AI 區塊非同步產生
    再補一次，確保回測區塊顯示
  */

  setTimeout(render, 1200);

})();
