/* =========================================================
   AI 選股 5日 / 10日績效回測
   ========================================================= */

(function () {
  const $bt = s =>
    document.querySelector(s);

  function fmtPct(v) {
    if (
      v === null ||
      v === undefined ||
      Number.isNaN(Number(v))
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
      Number.isNaN(Number(v))
    ) {
      return "";
    }

    return Number(v) >= 0
      ? "up"
      : "down";
  }

  async function loadBacktest() {
    try {
      const r = await fetch(
        "./data/ai_backtest.json?v=" +
          Date.now(),
        {
          cache: "no-store"
        }
      );

      if (!r.ok) {
        return {};
      }

      return await r.json();
    } catch (e) {
      console.error(
        "AI backtest load failed",
        e
      );

      return {};
    }
  }

  function statCard(
    title,
    stat
  ) {
    const samples =
      Number(
        stat?.samples ||
        0
      );

    return `
      <div
        class="ai-bt-stat"
      >
        <div
          class="ai-bt-stat-title"
        >
          ${title}
        </div>

        ${
          samples
            ? `
              <strong
                class="${tone(
                  stat.avg_return
                )}"
              >
                ${fmtPct(
                  stat.avg_return
                )}
              </strong>

              <div
                class="ai-bt-stat-sub"
              >
                <span>
                  勝率
                  <b>
                    ${
                      Number(
                        stat.win_rate ||
                        0
                      ).toFixed(1)
                    }%
                  </b>
                </span>

                <span>
                  中位數
                  <b
                    class="${tone(
                      stat.median_return
                    )}"
                  >
                    ${fmtPct(
                      stat.median_return
                    )}
                  </b>
                </span>

                <span>
                  樣本
                  <b>
                    ${samples}
                  </b>
                </span>
              </div>
            `
            : `
              <div
                class="ai-bt-pending"
              >
                尚未有滿 ${title.replace(
                  "績效",
                  ""
                )} 的樣本
              </div>
            `
        }
      </div>
    `;
  }

  function bucketRow(
    label,
    d
  ) {
    return `
      <div
        class="ai-bt-bucket-row"
      >
        <b>${label}</b>

        <span
          class="${tone(
            d?.["5d"]
              ?.avg_return
          )}"
        >
          ${fmtPct(
            d?.["5d"]
              ?.avg_return
          )}
        </span>

        <span
          class="${tone(
            d?.["10d"]
              ?.avg_return
          )}"
        >
          ${fmtPct(
            d?.["10d"]
              ?.avg_return
          )}
        </span>
      </div>
    `;
  }

  function latestRecords(
    records
  ) {
    const dates = [
      ...new Set(
        (records || [])
          .map(
            r =>
              r.selection_date
          )
          .filter(Boolean)
      )
    ]
      .sort()
      .reverse()
      .slice(
        0,
        3
      );

    return (
      records ||
      []
    )
      .filter(
        r =>
          dates.includes(
            r.selection_date
          )
      )
      .sort(
        (a, b) => {
          if (
            a.selection_date !==
            b.selection_date
          ) {
            return String(
              b.selection_date
            ).localeCompare(
              String(
                a.selection_date
              )
            );
          }

          if (
            a.market !==
            b.market
          ) {
            return String(
              a.market
            ).localeCompare(
              String(
                b.market
              )
            );
          }

          return (
            Number(
              a.rank ||
              999
            ) -
            Number(
              b.rank ||
              999
            )
          );
        }
      );
  }

  function recordRow(
    r
  ) {
    const market =
      r.market === "twse"
        ? "上市"
        : "上櫃";

    return `
      <div
        class="ai-bt-record-row"
      >
        <div
          class="ai-bt-record-name"
        >
          <small>
            ${
              r.selection_date ||
              ""
            }
            · ${market}
            · #${
              r.rank ||
              "—"
            }
          </small>

          <b>
            ${
              r.name ||
              r.ticker ||
              "—"
            }
          </b>

          <span>
            ${
              r.ticker ||
              ""
            }
          </span>
        </div>

        <div>
          <small>5日</small>

          <b
            class="${tone(
              r.return_5d
            )}"
          >
            ${
              r.status_5d ===
              "complete"
                ? fmtPct(
                    r.return_5d
                  )
                : "進行中"
            }
          </b>
        </div>

        <div>
          <small>10日</small>

          <b
            class="${tone(
              r.return_10d
            )}"
          >
            ${
              r.status_10d ===
              "complete"
                ? fmtPct(
                    r.return_10d
                  )
                : "進行中"
            }
          </b>
        </div>
      </div>
    `;
  }

  async function render() {
    const aiCards =
      $bt("#aiCards");

    if (!aiCards) {
      return;
    }

    let panel =
      $bt("#aiBacktestPanel");

    if (!panel) {
      panel =
        document.createElement(
          "section"
        );

      panel.id =
        "aiBacktestPanel";

      panel.className =
        "ai-backtest-panel";

      aiCards.parentNode
        .insertBefore(
          panel,
          aiCards
        );
    }

    const d =
      await loadBacktest();

    const summary =
      d.summary?.all ||
      {};

    const buckets =
      d.summary
        ?.rank_buckets ||
      {};

    const records =
      latestRecords(
        d.records ||
        []
      );

    panel.innerHTML = `
      <div
        class="ai-bt-head"
      >
        <div>
          <span
            class="kicker"
          >
            PERFORMANCE BACKTEST
          </span>

          <h2>
            AI 選股績效回測
          </h2>

          <p>
            ${
              d.start_date
                ? `自 ${d.start_date} 起累積`
                : "尚未開始累積"
            }
            ｜以選股基準日收盤價計算
          </p>
        </div>

        <span
          class="badge"
        >
          交易日制
        </span>
      </div>

      <div
        class="ai-bt-stats"
      >
        ${statCard(
          "5日績效",
          summary["5d"]
        )}

        ${statCard(
          "10日績效",
          summary["10d"]
        )}
      </div>

      <div
        class="ai-bt-rank-card"
      >
        <div
          class="ai-bt-rank-head"
        >
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

      <details
        class="ai-bt-history"
      >
        <summary>
          最近選股紀錄
          <span>
            查看明細 ▾
          </span>
        </summary>

        <div
          class="ai-bt-history-body"
        >
          ${
            records.length
              ? records
                  .map(
                    recordRow
                  )
                  .join("")
              : `
                <div
                  class="empty"
                >
                  第一次執行更新後會開始累積回測紀錄
                </div>
              `
          }
        </div>
      </details>

      <div
        class="ai-bt-note"
      >
        5日／10日皆指基準日後第 5／10 個交易日，不含週末與休市日
      </div>
    `;
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      render
    );
  } else {
    render();
  }

  /*
    app.js 的 AI 區塊是非同步產生，
    再補一次，確保畫面完成後仍能插入回測區
  */
  setTimeout(
    render,
    1200
  );
})();
