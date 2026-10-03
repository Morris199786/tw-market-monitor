/* =========================================================
   Heatmap stock detail trend periods
   5 / 20 / 60 trading days, default 20
   - Trend metrics and overlay chart switch together
   - Institutional flow remains fixed at 5 days
   ========================================================= */
(function () {
  const PERIODS = [5, 20, 60];
  const DEFAULT_PERIOD = 20;

  let activePeriod = DEFAULT_PERIOD;
  let detailData = null;
  let detailPromise = null;
  let rendering = false;

  const $ = (s, root = document) =>
    root.querySelector(s);

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

  function valueClass(v) {
    const n = Number(v);

    if (n > 0) {
      return "up";
    }

    if (n < 0) {
      return "down";
    }

    return "";
  }

  function latestValue(arr) {
    const xs = (arr || []).filter(
      x =>
        x !== null &&
        x !== undefined &&
        !Number.isNaN(Number(x))
    );

    return xs.length
      ? Number(xs[xs.length - 1])
      : null;
  }

  function loadData() {
    if (detailData) {
      return Promise.resolve(
        detailData
      );
    }

    if (detailPromise) {
      return detailPromise;
    }

    detailPromise = fetch(
      "./data/stock_detail.json?v=" +
        Date.now(),
      {
        cache: "no-store"
      }
    )
      .then(r => {
        if (!r.ok) {
          throw new Error(
            "HTTP " + r.status
          );
        }

        return r.json();
      })
      .then(d => {
        detailData = d;

        return d;
      })
      .finally(() => {
        detailPromise = null;
      });

    return detailPromise;
  }

  function ensureStyles() {
    if (
      $("#stockTrendPeriodStyle")
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "stockTrendPeriodStyle";

    style.textContent = `
      .stock-trend-periods{
        display:flex;
        gap:6px;
        margin:0 0 14px;
        padding:4px;
        border:1px solid var(--line);
        border-radius:13px;
        background:var(--soft)
      }

      .stock-trend-period{
        flex:1;
        min-height:36px;
        border:0;
        border-radius:9px;
        background:transparent;
        color:var(--muted);
        font-size:11px;
        font-weight:900;
        cursor:pointer
      }

      .stock-trend-period.active{
        background:var(--card);
        color:var(--ink);
        box-shadow:
          0 2px 8px
          rgba(15,23,42,.10)
      }

      .stock-trend-chart{
        padding:12px 10px 8px;
        border:1px solid var(--line);
        border-radius:17px;
        background:
          linear-gradient(
            180deg,
            var(--soft),
            color-mix(
              in srgb,
              var(--soft) 72%,
              var(--card)
            )
          );
        overflow:hidden
      }

      .stock-trend-chart svg{
        display:block;
        width:100%;
        height:auto;
        overflow:visible
      }

      @media(max-width:720px){
        .stock-trend-period{
          min-height:34px;
          font-size:10px
        }

        .stock-trend-chart{
          padding:8px 5px 6px
        }
      }
    `;

    document.head.appendChild(
      style
    );
  }

  function getContext() {
    const overlay =
      $("#stockDetailOverlay");

    if (
      !overlay ||
      !overlay.classList.contains(
        "open"
      )
    ) {
      return null;
    }

    const trendTab =
      $(
        '[data-stock-detail-tab="trend"]',
        overlay
      );

    if (
      !trendTab ||
      !trendTab.classList.contains(
        "active"
      )
    ) {
      return null;
    }

    const nameText =
      $(
        "#stockDetailName",
        overlay
      )?.textContent?.trim() || "";

    const ticker =
      nameText
        .split(/\s+/)
        .pop() || "";

    const meta =
      $(
        "#stockDetailMeta",
        overlay
      )?.textContent?.trim() || "";

    const sector =
      meta
        .split("｜")[0]
        ?.trim() || "";

    return {
      overlay,
      ticker,
      sector
    };
  }

  function getPeriodArray(
    obj,
    period
  ) {
    const map =
      obj?.returns_by_period || {};

    const arr =
      map[String(period)] ||
      map[period];

    if (
      Array.isArray(arr)
    ) {
      return arr;
    }

    const fallback =
      obj?.returns || [];

    return fallback.slice(
      -period
    );
  }

  function getLabels(period) {
    const map =
      detailData
        ?.date_labels_by_period ||
      {};

    const arr =
      map[String(period)] ||
      map[period];

    if (
      Array.isArray(arr)
    ) {
      return arr;
    }

    return (
      detailData
        ?.date_labels || []
    ).slice(-period);
  }

  function lineChartSvg(
    labels,
    series
  ) {
    const width = 680;
    const height = 310;

    const pad = {
      left: 52,
      right: 22,
      top: 22,
      bottom: 44
    };

    const values =
      series
        .flatMap(
          s => s.values || []
        )
        .filter(
          v =>
            v !== null &&
            v !== undefined &&
            !Number.isNaN(
              Number(v)
            )
        )
        .map(Number);

    if (!values.length) {
      return `
        <div
          class="stock-detail-empty"
        >
          暫無完整走勢資料
        </div>
      `;
    }

    let min =
      Math.min(
        0,
        ...values
      );

    let max =
      Math.max(
        0,
        ...values
      );

    if (
      Math.abs(
        max - min
      ) < 0.5
    ) {
      max += 1;
      min -= 1;
    }

    const span =
      max - min;

    max +=
      span * 0.14;

    min -=
      span * 0.14;

    const plotW =
      width -
      pad.left -
      pad.right;

    const plotH =
      height -
      pad.top -
      pad.bottom;

    const xAt = i =>
      pad.left +
      (
        labels.length <= 1
          ? plotW / 2
          : (
              i /
              (
                labels.length -
                1
              )
            ) *
            plotW
      );

    const yAt = v =>
      pad.top +
      (
        (
          max -
          Number(v)
        ) /
        (
          max -
          min
        )
      ) *
      plotH;

    const ticks =
      Array.from(
        {
          length: 5
        },
        (_, i) =>
          max -
          (
            (
              max -
              min
            ) *
            i /
            4
          )
      );

    const grid =
      ticks
        .map(
          v => `
            <g>
              <line
                x1="${pad.left}"
                x2="${
                  width -
                  pad.right
                }"
                y1="${yAt(v)}"
                y2="${yAt(v)}"
                stroke="currentColor"
                opacity=".10"
              />

              <text
                x="${
                  pad.left -
                  8
                }"
                y="${
                  yAt(v) +
                  4
                }"
                text-anchor="end"
                fill="currentColor"
                opacity=".55"
                font-size="10"
              >
                ${v.toFixed(1)}%
              </text>
            </g>
          `
        )
        .join("");

    const paths =
      series
        .map(s => {
          let d = "";
          let drawing =
            false;

          (
            s.values || []
          ).forEach(
            (v, i) => {
              if (
                v === null ||
                v === undefined ||
                Number.isNaN(
                  Number(v)
                )
              ) {
                drawing =
                  false;

                return;
              }

              d += `${
                drawing
                  ? " L"
                  : "M"
              } ${
                xAt(i)
                  .toFixed(1)
              } ${
                yAt(v)
                  .toFixed(1)
              }`;

              drawing =
                true;
            }
          );

          return `
            <path
              d="${d}"
              fill="none"
              stroke="${s.color}"
              stroke-width="3"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          `;
        })
        .join("");

    const maxLabels =
      activePeriod >= 60
        ? 7
        : activePeriod >= 20
          ? 6
          : 5;

    const step =
      Math.max(
        1,
        Math.ceil(
          labels.length /
          maxLabels
        )
      );

    const xLabels =
      labels
        .map(
          (label, i) => {
            if (
              i !== 0 &&
              i !==
                labels.length -
                  1 &&
              i % step !== 0
            ) {
              return "";
            }

            return `
              <text
                x="${xAt(i)}"
                y="${
                  height -
                  15
                }"
                text-anchor="middle"
                fill="currentColor"
                opacity=".55"
                font-size="10"
              >
                ${label}
              </text>
            `;
          }
        )
        .join("");

    const zero =
      min <= 0 &&
      max >= 0
        ? `
          <line
            x1="${pad.left}"
            x2="${
              width -
              pad.right
            }"
            y1="${yAt(0)}"
            y2="${yAt(0)}"
            stroke="currentColor"
            opacity=".28"
            stroke-dasharray="4 4"
          />
        `
        : "";

    return `
      <svg
        viewBox="0 0 ${width} ${height}"
        role="img"
        aria-label="近${activePeriod}日相對走勢疊合圖"
      >
        ${grid}
        ${zero}
        ${paths}
        ${xLabels}
      </svg>
    `;
  }

  function render() {
    if (
      rendering ||
      !detailData
    ) {
      return;
    }

    const ctx =
      getContext();

    if (
      !ctx?.ticker
    ) {
      return;
    }

    const stock =
      detailData
        .stocks?.[
          ctx.ticker
        ];

    if (!stock) {
      return;
    }

    const sector =
      detailData
        .sectors?.[
          ctx.sector
        ] || {};

    const bench =
      detailData
        .benchmark || {};

    const body =
      $(
        "#stockDetailBody",
        ctx.overlay
      );

    if (!body) {
      return;
    }

    const labels =
      getLabels(
        activePeriod
      );

    const sr =
      getPeriodArray(
        stock,
        activePeriod
      );

    const gr =
      getPeriodArray(
        sector,
        activePeriod
      );

    const ir =
      getPeriodArray(
        bench,
        activePeriod
      );

    const stockLast =
      latestValue(sr);

    const sectorLast =
      latestValue(gr);

    const indexLast =
      latestValue(ir);

    const vsSector =
      stockLast !== null &&
      sectorLast !== null
        ? stockLast -
          sectorLast
        : null;

    const vsIndex =
      stockLast !== null &&
      indexLast !== null
        ? stockLast -
          indexLast
        : null;

    rendering = true;

    body.innerHTML = `
      <div
        class="stock-trend-periods"
        role="tablist"
        aria-label="走勢期間"
      >
        ${PERIODS
          .map(
            p => `
              <button
                type="button"
                class="
                  stock-trend-period
                  ${
                    p ===
                    activePeriod
                      ? "active"
                      : ""
                  }
                "
                data-trend-period="${p}"
              >
                近${p}日
              </button>
            `
          )
          .join("")}
      </div>

      <div
        class="stock-detail-section-title"
      >
        <strong>
          近${activePeriod}日相對走勢
        </strong>

        <small>
          個股 vs 同族群 vs 上市加權指數
        </small>
      </div>

      <div
        class="stock-detail-metrics"
      >
        <div
          class="stock-detail-metric stock"
        >
          <small>
            ${
              stock.name ||
              ctx.ticker
            }
          </small>

          <strong
            class="${
              valueClass(
                stockLast
              )
            }"
          >
            ${
              fmtPct(
                stockLast
              )
            }
          </strong>
        </div>

        <div
          class="stock-detail-metric sector"
        >
          <small>
            ${
              ctx.sector ||
              "同族群"
            }
          </small>

          <strong
            class="${
              valueClass(
                sectorLast
              )
            }"
          >
            ${
              fmtPct(
                sectorLast
              )
            }
          </strong>
        </div>

        <div
          class="stock-detail-metric index"
        >
          <small>
            ${
              bench.name ||
              "上市加權指數"
            }
          </small>

          <strong
            class="${
              valueClass(
                indexLast
              )
            }"
          >
            ${
              fmtPct(
                indexLast
              )
            }
          </strong>
        </div>
      </div>

      <div
        class="stock-detail-note"
      >
        近${activePeriod}個已完成交易日；以${activePeriod}日前一交易日收盤為0%基準
        ${
          vsSector !== null
            ? `｜相對族群 ${fmtPct(vsSector)}`
            : ""
        }
        ${
          vsIndex !== null
            ? `｜相對大盤 ${fmtPct(vsIndex)}`
            : ""
        }
      </div>

      <div
        class="stock-trend-chart"
      >
        ${
          lineChartSvg(
            labels,
            [
              {
                label:
                  stock.name ||
                  ctx.ticker,
                values: sr,
                color:
                  "#dc2626"
              },
              {
                label:
                  ctx.sector ||
                  "同族群",
                values: gr,
                color:
                  "#2563eb"
              },
              {
                label:
                  bench.name ||
                  "上市加權指數",
                values: ir,
                color:
                  "#64748b"
              }
            ]
          )
        }

        <div
          class="stock-detail-legend"
        >
          <span>
            <i
              class="stock-detail-dot stock"
            ></i>
            個股
          </span>

          <span>
            <i
              class="stock-detail-dot sector"
            ></i>
            ${
              ctx.sector ||
              "同族群"
            }
          </span>

          <span>
            <i
              class="stock-detail-dot index"
            ></i>
            ${
              bench.name ||
              "上市加權指數"
            }
          </span>
        </div>
      </div>
    `;

    rendering = false;
  }

  function bind() {
    ensureStyles();

    document.addEventListener(
      "click",
      e => {
        const p =
          e.target.closest?.(
            "[data-trend-period]"
          );

        if (p) {
          activePeriod =
            Number(
              p.dataset
                .trendPeriod
            ) ||
            DEFAULT_PERIOD;

          render();

          return;
        }

        const tab =
          e.target.closest?.(
            '[data-stock-detail-tab="trend"]'
          );

        if (tab) {
          setTimeout(
            render,
            0
          );
        }

        const stockRow =
          e.target.closest?.(
            "#heatGrid .heat-stock"
          );

        if (stockRow) {
          activePeriod =
            DEFAULT_PERIOD;

          loadData()
            .then(
              () =>
                setTimeout(
                  render,
                  30
                )
            )
            .catch(
              console.error
            );
        }
      }
    );

    const observer =
      new MutationObserver(
        () => {
          if (rendering) {
            return;
          }

          const ctx =
            getContext();

          if (!ctx) {
            return;
          }

          const body =
            $(
              "#stockDetailBody",
              ctx.overlay
            );

          if (
            body &&
            !(
              ".stock-trend-periods",
              body
            )
          ) {
            loadData()
              .then(render)
              .catch(
                console.error
              );
          }

          const trendTab =
            $(
              '[data-stock-detail-tab="trend"]',
              ctx.overlay
            );

          if (trendTab) {
            trendTab.textContent =
              "走勢";
          }
        }
      );

    observer.observe(
      document.body,
      {
        childList: true,
        subtree: true
      }
    );
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      bind
    );
  } else {
    bind();
  }
})();
