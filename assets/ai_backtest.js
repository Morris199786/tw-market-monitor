/* =========================================================
   AI 選股績效回測
   固定持有 / 跌破 MA10 / 跌破 MA20
   預設：固定持有
   ========================================================= */

(function () {
  "use strict";

  const $bt = s => document.querySelector(s);

  let selectedStrategy = "baseline";
  let cachedData = null;
  let loadingPromise = null;

  const STRATEGIES = [
    {
      key: "baseline",
      label: "固定持有",
      description: "固定持有至第 5／10 個交易日收盤"
    },
    {
      key: "ma10",
      label: "跌破 MA10",
      description: "收盤跌破 10 日均線提前出場"
    },
    {
      key: "ma20",
      label: "跌破 MA20",
      description: "收盤跌破 20 日均線提前出場"
    }
  ];

  function fmtPct(v) {
    if (
      v === null ||
      v === undefined ||
      !Number.isFinite(Number(v))
    ) {
      return "—";
    }

    const n = Number(v);

    return (
      (n > 0 ? "+" : "") +
      n.toFixed(2) +
      "%"
    );
  }

  function tone(v) {
    if (
      v === null ||
      v === undefined ||
      !Number.isFinite(Number(v))
    ) {
      return "";
    }

    return Number(v) >= 0 ? "up" : "down";
  }

  function esc(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      c => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[c])
    );
  }

  function getStrategyData(data) {
    if (selectedStrategy === "baseline") {
      return data.baseline_summary || {};
    }

    if (selectedStrategy === "ma10") {
      return data.ma10_summary || data.summary || {};
    }

    return data.ma20_summary || {};
  }

  function getStrategyInfo() {
    return STRATEGIES.find(
      s => s.key === selectedStrategy
    ) || STRATEGIES[0];
  }

  async function loadBacktest() {
    if (cachedData) {
      return cachedData;
    }

    if (loadingPromise) {
      return loadingPromise;
    }

    loadingPromise = (async () => {
      try {
        const response = await fetch(
          "./data/ai_backtest.json?v=" + Date.now(),
          {
            cache: "no-store"
          }
        );

        if (!response.ok) {
          throw new Error(
            "HTTP " + response.status
          );
        }

        cachedData = await response.json();

        return cachedData;
      } catch (error) {
        console.error(
          "AI backtest load failed",
          error
        );

        return {};
      } finally {
        loadingPromise = null;
      }
    })();

    return loadingPromise;
  }

  /* =========================================================
     策略切換按鈕
     ========================================================= */

  function strategyButtons() {
    return `
      <div class="ai-bt-strategy-switch">
        ${STRATEGIES.map(strategy => `
          <button
            type="button"
            class="ai-bt-strategy-btn ${
              selectedStrategy === strategy.key
                ? "active"
                : ""
            }"
            data-ai-bt-strategy="${strategy.key}"
            aria-pressed="${
              selectedStrategy === strategy.key
                ? "true"
                : "false"
            }"
          >
            ${esc(strategy.label)}
          </button>
        `).join("")}
      </div>
    `;
  }

  /* =========================================================
     績效卡片
     ========================================================= */

  function statCard(title, stat) {
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
              <strong class="${tone(
                stat.avg_return
              )}">
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
                  <b class="${tone(
                    stat.median_return
                  )}">
                    ${fmtPct(
                      stat.median_return
                    )}
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

      </div>
    `;
  }

  /* =========================================================
     Top 5 / 10 / 20
     ========================================================= */

  function bucketRow(label, data) {
    return `
      <div class="ai-bt-bucket-row">

        <b>${esc(label)}</b>

        <span class="${tone(
          data?.["5d"]?.avg_return
        )}">
          ${fmtPct(
            data?.["5d"]?.avg_return
          )}
        </span>

        <span class="${tone(
          data?.["10d"]?.avg_return
        )}">
          ${fmtPct(
            data?.["10d"]?.avg_return
          )}
        </span>

      </div>
    `;
  }

  /* =========================================================
     最近三個選股日
     ========================================================= */

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
      .sort((a, b) => {
        if (
          a.selection_date !==
          b.selection_date
        ) {
          return String(
            b.selection_date
          ).localeCompare(
            String(a.selection_date)
          );
        }

        if (a.market !== b.market) {
          return String(
            a.market
          ).localeCompare(
            String(b.market)
          );
        }

        return (
          Number(a.rank || 999) -
          Number(b.rank || 999)
        );
      });
  }

  /* =========================================================
     根據策略取得個股績效
     ========================================================= */

  function recordPerformance(record, days) {
    let prefix = "";

    if (selectedStrategy === "baseline") {
      prefix = "baseline_";
    } else if (selectedStrategy === "ma20") {
      prefix = "ma20_";
    }

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
      record.market === "twse"
        ? "上市"
        : "上櫃";

    const perf5 = recordPerformance(
      record,
      5
    );

    const perf10 = recordPerformance(
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
              "—"
            )}
          </b>

          <span>
            ${esc(record.ticker)}
          </span>

        </div>

        <div>
          <small>5日</small>

          <b class="${tone(perf5.value)}">
            ${
              perf5.status === "complete"
                ? fmtPct(perf5.value)
                : "進行中"
            }
          </b>
        </div>

        <div>
          <small>10日</small>

          <b class="${tone(perf10.value)}">
            ${
              perf10.status === "complete"
                ? fmtPct(perf10.value)
                : "進行中"
            }
          </b>
        </div>

      </div>
    `;
  }

  /* =========================================================
     主畫面
     ========================================================= */

  async function render() {
    const aiCards = $bt("#aiCards");

    if (!aiCards) {
      return;
    }

    let panel = $bt(
      "#aiBacktestPanel"
    );

    if (!panel) {
      panel = document.createElement(
        "section"
      );

      panel.id = "aiBacktestPanel";
      panel.className =
        "ai-backtest-panel";

      aiCards.parentNode.insertBefore(
        panel,
        aiCards
      );
    }

    const data = await loadBacktest();

    const strategyData =
      getStrategyData(data);

    const strategyInfo =
      getStrategyInfo();

    const summary =
      strategyData.all || {};

    const buckets =
      strategyData.rank_buckets || {};

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
            background 0.15s,
            border-color 0.15s,
            color 0.15s;
        }

        #aiBacktestPanel
        .ai-bt-strategy-btn.active {
          background: #2563eb;
          border-color: #2563eb;
          color: #ffffff;
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
                ? `自 ${esc(
                    data.start_date
                  )} 起累積`
                : "尚未開始累積"
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
        ${esc(strategyInfo.description)}
      </div>

      <div class="ai-bt-stats">

        ${statCard(
          "5日績效",
          summary["5d"]
        )}

        ${statCard(
          "10日績效",
          summary["10d"]
        )}

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

        ${bucketRow(
          "Top 5",
          buckets.top5
        )}

        ${bucketRow(
          "Top 10",
          buckets.top10
        )}

        ${bucketRow(
          "Top 20",
          buckets.top20
        )}

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
                  .join("")
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

        三種策略使用相同已滿期樣本

        <br><br>

        MA10／MA20從推薦次一交易日開始檢查，
        收盤跌破均線即按當日收盤價模擬出場，
        提前出場的報酬仍須等觀察期滿才納入統計

      </div>

    `;

    /* ===============================
       綁定切換按鈕
       =============================== */

    panel
      .querySelectorAll(
        "[data-ai-bt-strategy]"
      )
      .forEach(button => {
        button.addEventListener(
          "click",
          () => {
            const next =
              button.dataset
                .aiBtStrategy;

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

  /* =========================================================
     初始化
     ========================================================= */

  if (
    document.readyState === "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      render
    );
  } else {
    render();
  }

  /*
    app.js 的 AI 區塊可能非同步產生
    補一次確保回測面板顯示
  */

  setTimeout(render, 1200);

})();
