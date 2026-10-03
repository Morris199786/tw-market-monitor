/* =========================================================
   市場熱力圖：族群下拉 + 細分類 + 個股資訊
   個股視窗：5 / 10 / 20 日共用期間
   籌碼：
   - 長條圖依 5 / 10 / 20 日切換
   - 長條圖下方固定顯示近 5 日明細
   - 顯示更多後可看最多 20 日
   - 手機支援上下滑動查看更早資料
   ========================================================= */

(() => {
  "use strict";

  const SECTOR_URL =
    "data/sectors.json";

  const STOCK_DETAIL_URL =
    "data/stock_detail.json";

  let sectorConfig = null;
  let stockDetailData = null;

  let activeSector = "";
  let activeTicker = "";
  let activePeriod = 5;
  let activeDetailTab = "trend";

  let flowExpanded = false;
  let flowTouchStartY = null;

  const PERIODS = [
    5,
    10,
    20
  ];

  function escapeHtml(
    value
  ) {
    return String(
      value ?? ""
    )
      .replaceAll(
        "&",
        "&amp;"
      )
      .replaceAll(
        "<",
        "&lt;"
      )
      .replaceAll(
        ">",
        "&gt;"
      )
      .replaceAll(
        '"',
        "&quot;"
      )
      .replaceAll(
        "'",
        "&#039;"
      );
  }

  function toNumber(
    value
  ) {
    const n =
      Number(value);

    return Number.isFinite(n)
      ? n
      : null;
  }

  function latestValue(
    values
  ) {
    if (
      !Array.isArray(values)
    ) {
      return null;
    }

    for (
      let i =
        values.length - 1;
      i >= 0;
      i -= 1
    ) {
      const n =
        toNumber(
          values[i]
        );

      if (n !== null) {
        return n;
      }
    }

    return null;
  }

  function fmtPct(
    value
  ) {
    const n =
      toNumber(value);

    if (n === null) {
      return "—";
    }

    return (
      (
        n > 0
          ? "+"
          : ""
      ) +
      n.toFixed(2) +
      "%"
    );
  }

  function fmtLots(
    value
  ) {
    const raw =
      toNumber(value);

    if (raw === null) {
      return "—";
    }

    /*
     * 籌碼單位固定「張」
     * 顯示一律四捨五入成整數
     * 不顯示任何小數點
     */
    const n =
      Math.round(raw);

    return (
      (
        n > 0
          ? "+"
          : ""
      ) +
      n.toLocaleString(
        "zh-TW",
        {
          maximumFractionDigits:
            0
        }
      ) +
      " 張"
    );
  }

  function valueClass(
    value
  ) {
    const n =
      toNumber(value);

    if (n === null) {
      return "";
    }

    if (n > 0) {
      return "is-up";
    }

    if (n < 0) {
      return "is-down";
    }

    return "is-flat";
  }

  async function fetchJson(
    url
  ) {
    const res =
      await fetch(
        url,
        {
          cache:
            "no-store"
        }
      );

    if (!res.ok) {
      throw new Error(
        `${url}: ${res.status}`
      );
    }

    return res.json();
  }

  async function loadSectorConfig() {
    if (sectorConfig) {
      return sectorConfig;
    }

    try {
      sectorConfig =
        await fetchJson(
          SECTOR_URL
        );
    } catch (err) {
      console.warn(
        "[Heat Sector]",
        err
      );

      sectorConfig = {
        sectors: []
      };
    }

    return sectorConfig;
  }

  async function loadStockDetail() {
    if (stockDetailData) {
      return stockDetailData;
    }

    try {
      stockDetailData =
        await fetchJson(
          STOCK_DETAIL_URL
        );
    } catch (err) {
      console.warn(
        "[Stock Detail]",
        err
      );

      stockDetailData = {
        stocks: {},
        sectors: {},
        benchmark: {}
      };
    }

    return stockDetailData;
  }

  function directHeatButtons() {
    return [
      ...document.querySelectorAll(
        "#heatGrid .heat-stock"
      )
    ];
  }

  function tickerFromRow(
    row
  ) {
    return String(
      row?.dataset?.ticker ||
      row?.getAttribute(
        "data-ticker"
      ) ||
      ""
    ).trim();
  }

  function sectorFromRow(
    row
  ) {
    const direct =
      String(
        row?.dataset?.sector ||
        row?.getAttribute(
          "data-sector"
        ) ||
        ""
      ).trim();

    if (direct) {
      return direct;
    }

    const card =
      row?.closest?.(
        "[data-sector]"
      );

    const cardSector =
      String(
        card?.dataset?.sector ||
        ""
      ).trim();

    if (cardSector) {
      return cardSector;
    }

    const title =
      row
        ?.closest?.(
          ".heat-sector"
        )
        ?.querySelector?.(
          ".heat-sector-title"
        )
        ?.textContent;

    return String(
      title || ""
    ).trim();
  }

  function decorateHeatStocks() {
    directHeatButtons()
      .forEach(
        row => {
          const ticker =
            tickerFromRow(row);

          if (!ticker) {
            return;
          }

          row.setAttribute(
            "role",
            "button"
          );

          row.setAttribute(
            "tabindex",
            "0"
          );

          row.setAttribute(
            "aria-label",
            `查看 ${ticker} 個股資訊`
          );
        }
      );
  }

  function sectorList() {
    const list =
      sectorConfig?.sectors;

    return Array.isArray(list)
      ? list
      : [];
  }

  function ensureControls() {
    const grid =
      document.querySelector(
        "#heatGrid"
      );

    if (!grid) {
      return;
    }

    if (
      document.querySelector(
        "#heatSectorFilter"
      )
    ) {
      return;
    }

    const wrap =
      document.createElement(
        "div"
      );

    wrap.className =
      "heat-sector-filter";

    wrap.id =
      "heatSectorFilter";

    const select =
      document.createElement(
        "select"
      );

    select.id =
      "heatSectorSelect";

    select.setAttribute(
      "aria-label",
      "選擇族群"
    );

    const all =
      document.createElement(
        "option"
      );

    all.value = "";
    all.textContent =
      "全部族群";

    select.appendChild(all);

    sectorList()
      .forEach(
        sec => {
          const name =
            String(
              sec?.name ||
              ""
            ).trim();

          if (!name) {
            return;
          }

          const option =
            document.createElement(
              "option"
            );

          option.value =
            name;

          option.textContent =
            name;

          select.appendChild(
            option
          );
        }
      );

    select.addEventListener(
      "change",
      () => {
        activeSector =
          select.value;

        applySectorFilter();
      }
    );

    wrap.appendChild(
      select
    );

    grid.parentNode
      ?.insertBefore(
        wrap,
        grid
      );
  }

  function applySectorFilter() {
    const selected =
      document.querySelector(
        "#heatSectorSelect"
      )?.value || "";

    const cards = [
      ...document.querySelectorAll(
        "#heatGrid .heat-sector"
      )
    ];

    if (!cards.length) {
      return;
    }

    cards.forEach(
      card => {
        if (!selected) {
          card.hidden =
            false;

          return;
        }

        const name =
          String(
            card.dataset.sector ||
            card
              .querySelector(
                ".heat-sector-title"
              )
              ?.textContent ||
            ""
          ).trim();

        card.hidden =
          name !== selected;
      }
    );
  }

  function updateStaticLabels() {
    decorateHeatStocks();
  }

  function observeHeatmap() {
    const grid =
      document.querySelector(
        "#heatGrid"
      );

    if (!grid) {
      return;
    }

    const observer =
      new MutationObserver(
        () => {
          ensureControls();
          updateStaticLabels();
          applySectorFilter();
        }
      );

    observer.observe(
      grid,
      {
        childList: true,
        subtree: false
      }
    );
  }

  function ensureStockDetailModal() {
    if (
      document.querySelector(
        "#stockDetailModal"
      )
    ) {
      return;
    }

    const modal =
      document.createElement(
        "div"
      );

    modal.id =
      "stockDetailModal";

    modal.className =
      "stock-detail-modal";

    modal.hidden = true;

    modal.innerHTML = `
      <div
        class="stock-detail-backdrop"
        data-stock-detail-close
      ></div>

      <section
        class="stock-detail-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stockDetailTitle"
      >
        <header
          class="stock-detail-header"
        >
          <div>
            <h2
              id="stockDetailTitle"
            >
              個股資訊
            </h2>

            <div
              class="stock-detail-subtitle"
              id="stockDetailSubtitle"
            ></div>
          </div>

          <button
            type="button"
            class="stock-detail-close"
            data-stock-detail-close
            aria-label="關閉"
          >
            ×
          </button>
        </header>

        <div
          class="stock-detail-body"
          id="stockDetailBody"
        ></div>
      </section>
    `;

    document.body.appendChild(
      modal
    );

    modal.addEventListener(
      "click",
      e => {
        if (
          e.target.closest(
            "[data-stock-detail-close]"
          )
        ) {
          closeStockDetail();
        }
      }
    );
  }

  async function openStockDetail(
    ticker,
    sector
  ) {
    if (!ticker) {
      return;
    }

    activeTicker =
      String(ticker);

    activeSector =
      String(
        sector || ""
      ).trim();

    activePeriod = 5;
    activeDetailTab =
      "trend";

    flowExpanded =
      false;

    await loadStockDetail();

    /*
     * 新增／搬移族群後，
     * DOM 若沒有正確提供族群名稱，
     * 直接由 stock_detail.json
     * 找這檔股票真正的族群
     */
    const stock =
      stockDetailData
        ?.stocks
        ?.[activeTicker];

    if (
      stock &&
      (
        !activeSector ||
        !stockDetailData
          ?.sectors
          ?.[activeSector]
      )
    ) {
      const candidates =
        Array.isArray(
          stock.sectors
        )
          ? stock.sectors
          : [];

      const fallbackSector =
        (
          stock.primary_sector &&
          stockDetailData
            ?.sectors
            ?.[
              stock.primary_sector
            ]
        )
          ? stock.primary_sector
          : candidates.find(
              name =>
                stockDetailData
                  ?.sectors
                  ?.[name]
            );

      if (fallbackSector) {
        activeSector =
          fallbackSector;
      }
    }

    const modal =
      document.querySelector(
        "#stockDetailModal"
      );

    if (!modal) {
      return;
    }

    modal.hidden = false;

    document.body.classList.add(
      "stock-detail-open"
    );

    renderStockDetail();
  }

  function closeStockDetail() {
    const modal =
      document.querySelector(
        "#stockDetailModal"
      );

    if (!modal) {
      return;
    }

    modal.hidden = true;

    document.body.classList.remove(
      "stock-detail-open"
    );

    activeTicker = "";
    activeSector = "";
    activePeriod = 5;
    activeDetailTab =
      "trend";

    flowExpanded =
      false;
  }

  function periodValues(
    item,
    period
  ) {
    if (!item) {
      return [];
    }

    const key =
      String(period);

    const byPeriod =
      item
        .returns_by_period
        ?.[key];

    if (
      Array.isArray(
        byPeriod
      )
    ) {
      return byPeriod;
    }

    if (
      period === 5 &&
      Array.isArray(
        item.returns
      )
    ) {
      return item.returns;
    }

    return [];
  }

  function periodLabels(
    period
  ) {
    const key =
      String(period);

    const labels =
      stockDetailData
        ?.date_labels_by_period
        ?.[key];

    if (
      Array.isArray(labels)
    ) {
      return labels;
    }

    if (
      period === 5 &&
      Array.isArray(
        stockDetailData
          ?.date_labels
      )
    ) {
      return stockDetailData
        .date_labels;
    }

    return [];
  }

  function renderStockDetail() {
    const modal =
      document.querySelector(
        "#stockDetailModal"
      );

    const body =
      document.querySelector(
        "#stockDetailBody"
      );

    const title =
      document.querySelector(
        "#stockDetailTitle"
      );

    const subtitle =
      document.querySelector(
        "#stockDetailSubtitle"
      );

    if (
      !modal ||
      !body ||
      !stockDetailData
    ) {
      return;
    }

    const stock =
      stockDetailData
        ?.stocks
        ?.[activeTicker];

    if (!stock) {
      body.innerHTML = `
        <div
          class="stock-detail-empty"
        >
          找不到 ${escapeHtml(
            activeTicker
          )} 的個股資料
        </div>
      `;

      return;
    }

    /*
     * 每次 render 都再檢查一次族群
     * 避免手機版 DOM 重排後 activeSector 為空
     */
    if (
      !activeSector ||
      !stockDetailData
        ?.sectors
        ?.[activeSector]
    ) {
      const candidates =
        Array.isArray(
          stock.sectors
        )
          ? stock.sectors
          : [];

      const fallbackSector =
        (
          stock.primary_sector &&
          stockDetailData
            ?.sectors
            ?.[
              stock.primary_sector
            ]
        )
          ? stock.primary_sector
          : candidates.find(
              name =>
                stockDetailData
                  ?.sectors
                  ?.[name]
            );

      if (fallbackSector) {
        activeSector =
          fallbackSector;
      }
    }

    if (title) {
      title.textContent =
        `${stock.name || activeTicker} ${activeTicker}`;
    }

    if (subtitle) {
      subtitle.textContent =
        `市場熱力圖｜資料截至 ${
          stockDetailData
            .as_of_date ||
          "—"
        }`;
    }

    body.innerHTML = `
      ${renderPeriodSelector()}

      ${renderDetailTabs()}

      ${
        activeDetailTab ===
        "flow"
          ? renderFlowPanel(
              stock
            )
          : renderTrendPanel(
              stock
            )
      }
    `;

    bindPeriodButtons(
      body
    );

    bindDetailTabs(
      body
    );

    if (
      activeDetailTab ===
      "flow"
    ) {
      bindFlowPull(
        body
      );
    }
  }

  function renderPeriodSelector() {
    return `
      <div
        class="stock-detail-periods"
        role="group"
        aria-label="走勢期間"
      >
        ${PERIODS
          .map(
            period => `
              <button
                type="button"
                class="stock-detail-period ${
                  activePeriod ===
                  period
                    ? "active"
                    : ""
                }"
                data-period="${period}"
              >
                ${period}日
              </button>
            `
          )
          .join("")}
      </div>
    `;
  }

  function bindPeriodButtons(
    body
  ) {
    body
      .querySelectorAll(
        "[data-period]"
      )
      .forEach(
        button => {
          button.addEventListener(
            "click",
            () => {
              const period =
                Number(
                  button.dataset
                    .period
                );

              if (
                !PERIODS.includes(
                  period
                )
              ) {
                return;
              }

              activePeriod =
                period;

              renderStockDetail();
            }
          );
        }
      );
  }

  function renderDetailTabs() {
    return `
      <div
        class="stock-detail-tabs"
      >
        <button
          type="button"
          class="${
            activeDetailTab ===
            "trend"
              ? "active"
              : ""
          }"
          data-detail-tab="trend"
        >
          走勢
        </button>

        <button
          type="button"
          class="${
            activeDetailTab ===
            "flow"
              ? "active"
              : ""
          }"
          data-detail-tab="flow"
        >
          籌碼
        </button>
      </div>
    `;
  }

  function bindDetailTabs(
    body
  ) {
    body
      .querySelectorAll(
        "[data-detail-tab]"
      )
      .forEach(
        button => {
          button.addEventListener(
            "click",
            () => {
              activeDetailTab =
                button.dataset
                  .detailTab;

              flowExpanded =
                false;

              renderStockDetail();
            }
          );
        }
      );
  }

  function renderTrendPanel(
    stock
  ) {
    /*
     * 最重要的修正：
     * activeSector 如果沒有成功從
     * heatmap DOM 傳進來，
     * 改用後端 stock.primary_sector
     */
    if (
      !activeSector ||
      !stockDetailData
        ?.sectors
        ?.[activeSector]
    ) {
      const candidates =
        Array.isArray(
          stock?.sectors
        )
          ? stock.sectors
          : [];

      const fallbackSector =
        (
          stock?.primary_sector &&
          stockDetailData
            ?.sectors
            ?.[
              stock.primary_sector
            ]
        )
          ? stock.primary_sector
          : candidates.find(
              name =>
                stockDetailData
                  ?.sectors
                  ?.[name]
            );

      if (fallbackSector) {
        activeSector =
          fallbackSector;
      }
    }

    const sector =
      stockDetailData
        ?.sectors
        ?.[activeSector] ||
      {};

    const bench =
      stockDetailData
        ?.benchmark ||
      {};

    const stockValues =
      periodValues(
        stock,
        activePeriod
      );

    const sectorValues =
      periodValues(
        sector,
        activePeriod
      );

    const benchValues =
      periodValues(
        bench,
        activePeriod
      );

    const labels =
      periodLabels(
        activePeriod
      );

    const stockLast =
      latestValue(
        stockValues
      );

    const sectorLast =
      latestValue(
        sectorValues
      );

    const benchLast =
      latestValue(
        benchValues
      );

    const vsSector =
      (
        stockLast !== null &&
        sectorLast !== null
      )
        ? (
            stockLast -
            sectorLast
          )
        : null;

    const vsMarket =
      (
        stockLast !== null &&
        benchLast !== null
      )
        ? (
            stockLast -
            benchLast
          )
        : null;

    return `
      <div
        class="stock-detail-section-title"
      >
        <strong>
          近${activePeriod}日相對走勢
        </strong>

        <small>
          前一交易日收盤＝0%
        </small>
      </div>

      <div
        class="stock-detail-kpis"
      >
        <div
          class="stock-detail-kpi"
        >
          <span>
            個股
          </span>

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
          class="stock-detail-kpi"
        >
          <span>
            相對族群
          </span>

          <strong
            class="${
              valueClass(
                vsSector
              )
            }"
          >
            ${
              fmtPct(
                vsSector
              )
            }
          </strong>
        </div>

        <div
          class="stock-detail-kpi"
        >
          <span>
            相對大盤
        function lineChartSvg(
    labels,
    series
  ) {
    const width = 680;
    const height = 300;

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

    if (
      !values.length ||
      !labels.length
    ) {
      return `
        <div
          class="stock-detail-empty"
        >
          目前沒有足夠的走勢資料
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

    if (min === max) {
      min -= 1;
      max += 1;
    }

    const range =
      max - min;

    const margin =
      Math.max(
        1,
        range * 0.12
      );

    min -= margin;
    max += margin;

    const plotW =
      width -
      pad.left -
      pad.right;

    const plotH =
      height -
      pad.top -
      pad.bottom;

    const xAt =
      i =>
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

    const yAt =
      v =>
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
                  pad.left - 8
                }"
                y="${
                  yAt(v) + 4
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
        .map(
          s => {
            let d = "";
            let drawing =
              false;

            (
              s.values ||
              []
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

                drawing = true;
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
          }
        )
        .join("");

    const maxLabels =
      activePeriod >= 20
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
          (
            label,
            i
          ) => {
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
                  height - 15
                }"
                text-anchor="middle"
                fill="currentColor"
                opacity=".55"
                font-size="10"
              >
                ${escapeHtml(
                  label
                )}
              </text>
            `;
          }
        )
        .join("");

    const zero =
      (
        min <= 0 &&
        max >= 0
      )
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
        aria-label="近${activePeriod}日相對走勢"
      >
        ${grid}
        ${zero}
        ${paths}
        ${xLabels}
      </svg>
    `;
  }

  function allFlowRows(
    stock
  ) {
    const rows =
      Array.isArray(
        stock?.institutional
      )
        ? stock.institutional
        : [];

    return rows.slice(
      -20
    );
  }

  function flowTableHtml(
    rows
  ) {
    const newestFirst =
      [...rows]
        .reverse();

    return `
      <table
        class="stock-flow-table"
      >
        <thead>
          <tr>
            <th>日期</th>
            <th>外資</th>
            <th>投信</th>
            <th>自營商</th>
            <th>合計</th>
          </tr>
        </thead>

        <tbody>
          ${
            newestFirst
              .map(
                row => `
                  <tr>
                    <td>
                      ${
                        escapeHtml(
                          row.date_label ||
                          "—"
                        )
                      }
                    </td>

                    <td
                      class="${
                        valueClass(
                          row.foreign_lots
                        )
                      }"
                    >
                      ${
                        fmtLots(
                          row.foreign_lots
                        )
                      }
                    </td>

                    <td
                      class="${
                        valueClass(
                          row.trust_lots
                        )
                      }"
                    >
                      ${
                        fmtLots(
                          row.trust_lots
                        )
                      }
                    </td>

                    <td
                      class="${
                        valueClass(
                          row.dealer_lots
                        )
                      }"
                    >
                      ${
                        fmtLots(
                          row.dealer_lots
                        )
                      }
                    </td>

                    <td
                      class="${
                        valueClass(
                          row.total_lots
                        )
                      }"
                    >
                      ${
                        fmtLots(
                          row.total_lots
                        )
                      }
                    </td>
                  </tr>
                `
              )
              .join("")
          }
        </tbody>
      </table>
    `;
  }

  function renderFlowPanel(
    stock
  ) {
    const allRows =
      allFlowRows(stock);

    if (!allRows.length) {
      return `
        <div
          class="stock-detail-empty"
        >
          目前沒有法人籌碼資料
        </div>
      `;
    }

    /*
     * 長條圖跟上方
     * 5 / 10 / 20 日按鈕連動
     */
    const chartRows =
      allRows.slice(
        -activePeriod
      );

    /*
     * 表格預設固定顯示近5日
     */
    const recent5 =
      allRows.slice(-5);

    /*
     * 張數全部使用整數
     */
    const total =
      Math.round(
        chartRows.reduce(
          (
            sum,
            row
          ) =>
            sum +
            Number(
              row.total_lots ||
              0
            ),
          0
        )
      );

    const tableRows =
      flowExpanded
        ? allRows
        : recent5;

    return `
      <div
        class="stock-detail-section-title"
      >
        <strong>
          近${activePeriod}日法人籌碼
        </strong>

        <small>
          長條圖看合計｜下方固定顯示近5日明細
        </small>
      </div>

      <div
        class="stock-flow-summary"
      >
        <span>
          近${activePeriod}日三大法人合計
        </span>

        <strong
          class="${
            valueClass(
              total
            )
          }"
        >
          ${fmtLots(total)}
        </strong>
      </div>

      <div
        class="stock-flow-stage ${
          flowExpanded
            ? "expanded"
            : ""
        }"
        id="stockFlowStage"
      >
        <div
          class="stock-flow-chart-wrap"
        >
          <div
            class="stock-detail-note"
          >
            長條圖僅顯示外資＋投信＋自營商「合計」買賣超｜單位：張
          </div>

          <div
            class="stock-detail-chart"
          >
            ${
              flowBarChartSvg(
                chartRows
              )
            }
          </div>
        </div>

        <div
          class="stock-flow-table-caption"
        >
          ${
            flowExpanded
              ? `近${
                  allRows.length
                }日籌碼明細｜上下滑動可看更早日期`
              : "近5日籌碼明細"
          }
        </div>

        <div
          class="stock-flow-table-wrap"
        >
          <div
            class="stock-flow-table-scroll"
          >
            ${
              flowTableHtml(
                tableRows
              )
            }
          </div>
        </div>

        ${
          allRows.length > 5
            ? `
              <button
                class="stock-flow-pull"
                id="stockFlowPull"
                type="button"
                aria-expanded="${
                  flowExpanded
                    ? "true"
                    : "false"
                }"
                aria-label="${
                  flowExpanded
                    ? "收回近5日籌碼"
                    : "顯示更多籌碼"
                }"
              >
                <span
                  class="stock-flow-pull-icon"
                ></span>

                <span
                  class="stock-flow-pull-label"
                >
                  ${
                    flowExpanded
                      ? "收回近5日"
                      : "顯示更多"
                  }
                </span>
              </button>
            `
            : ""
        }
      </div>
    `;
  }

  function bindFlowPull(
    body
  ) {
    const stage =
      body.querySelector(
        "#stockFlowStage"
      );

    const pull =
      body.querySelector(
        "#stockFlowPull"
      );

    if (
      !stage ||
      !pull
    ) {
      return;
    }

    const applyState =
      () => {
        stage.classList
          .toggle(
            "expanded",
            flowExpanded
          );

        pull.setAttribute(
          "aria-expanded",
          flowExpanded
            ? "true"
            : "false"
        );

        pull.setAttribute(
          "aria-label",
          flowExpanded
            ? "收回近5日籌碼"
            : "顯示更多籌碼"
        );

        renderStockDetail();
      };

    pull.addEventListener(
      "click",
      () => {
        flowExpanded =
          !flowExpanded;

        applyState();
      }
    );

    pull.addEventListener(
      "touchstart",
      e => {
        flowTouchStartY =
          e.touches?.[0]
            ?.clientY ??
          null;
      },
      {
        passive: true
      }
    );

    pull.addEventListener(
      "touchend",
      e => {
        if (
          flowTouchStartY ===
          null
        ) {
          return;
        }

        const endY =
          e.changedTouches?.[0]
            ?.clientY;

        if (
          endY ===
          undefined
        ) {
          flowTouchStartY =
            null;

          return;
        }

        const delta =
          endY -
          flowTouchStartY;

        if (
          delta < -24 &&
          !flowExpanded
        ) {
          flowExpanded = true;
          applyState();
        } else if (
          delta > 24 &&
          flowExpanded
        ) {
          flowExpanded = false;
          applyState();
        }

        flowTouchStartY =
          null;
      },
      {
        passive: true
      }
    );
  }

  function flowBarChartSvg(
    rows
  ) {
    const width = 680;
    const height = 260;

    const pad = {
      left: 52,
      right: 18,
      top: 22,
      bottom: 44
    };

    /*
     * 圖表也統一使用整數張
     */
    const vals =
      rows.map(
        x =>
          Math.round(
            Number(
              x.total_lots ||
              0
            )
          )
      );

    const maxAbs =
      Math.max(
        1,
        ...vals.map(
          v =>
            Math.abs(v)
        )
      );

    const plotW =
      width -
      pad.left -
      pad.right;

    const plotH =
      height -
      pad.top -
      pad.bottom;

    const zeroY =
      pad.top +
      plotH / 2;

    const yAt = v =>
      zeroY -
      (
        Number(v) /
        maxAbs
      ) *
      (
        plotH / 2 -
        8
      );

    const slot =
      plotW /
      Math.max(
        1,
        rows.length
      );

    const barW =
      Math.max(
        6,
        Math.min(
          44,
          slot * 0.56
        )
      );

    const maxLabels =
      rows.length >= 20
        ? 6
        : rows.length >= 10
          ? 5
          : rows.length;

    const labelStep =
      Math.max(
        1,
        Math.ceil(
          rows.length /
          Math.max(
            1,
            maxLabels
          )
        )
      );

    const bars =
      rows
        .map(
          (
            row,
            i
          ) => {
            const v =
              Math.round(
                Number(
                  row.total_lots ||
                  0
                )
              );

            const x =
              pad.left +
              slot * i +
              (
                slot -
                barW
              ) /
              2;

            const y =
              v >= 0
                ? yAt(v)
                : zeroY;

            const h =
              Math.max(
                1.5,
                Math.abs(
                  yAt(v) -
                  zeroY
                )
              );

            /*
             * 台股習慣：
             * 買超紅
             * 賣超綠
             */
            const color =
              v >= 0
                ? "#dc2626"
                : "#168357";

            const showLabel =
              i === 0 ||
              i ===
                rows.length -
                1 ||
              i %
                labelStep ===
                0;

            return `
              <rect
                x="${x}"
                y="${y}"
                width="${barW}"
                height="${h}"
                rx="4"
                fill="${color}"
              />

              ${
                showLabel
                  ? `
                    <text
                      x="${
                        x +
                        barW / 2
                      }"
                      y="${
                        height -
                        15
                      }"
                      text-anchor="middle"
                      font-size="10"
                      fill="currentColor"
                      opacity=".65"
                    >
                      ${
                        escapeHtml(
                          row.date_label ||
                          ""
                        )
                      }
                    </text>
                  `
                  : ""
              }
            `;
          }
        )
        .join("");

    return `
      <svg
        viewBox="0 0 ${width} ${height}"
        aria-label="近${activePeriod}日三大法人合計買賣超"
      >
        <line
          x1="${pad.left}"
          y1="${zeroY}"
          x2="${
            width -
            pad.right
          }"
          y2="${zeroY}"
          stroke="currentColor"
          opacity=".3"
        />

        <text
          x="${
            pad.left - 8
          }"
          y="${
            pad.top + 4
          }"
          text-anchor="end"
          font-size="10"
          fill="currentColor"
          opacity=".58"
        >
          +${
            Math.round(
              maxAbs
            ).toLocaleString(
              "zh-TW"
            )
          }
        </text>

        <text
          x="${
            pad.left - 8
          }"
          y="${
            height -
            pad.bottom
          }"
          text-anchor="end"
          font-size="10"
          fill="currentColor"
          opacity=".58"
        >
          -${
            Math.round(
              maxAbs
            ).toLocaleString(
              "zh-TW"
            )
          }
        </text>

        ${bars}
      </svg>
    `;
  }

  function injectStockDetailStyles() {
    if (
      document.querySelector(
        "#stockDetailStyles"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "stockDetailStyles";

    style.textContent = `
      body.stock-detail-open {
        overflow: hidden;
      }

      .stock-detail-modal {
        position: fixed;
        inset: 0;
        z-index: 99999;
      }

      .stock-detail-modal[hidden] {
        display: none !important;
      }

      .stock-detail-backdrop {
        position: absolute;
        inset: 0;
        background: rgba(15, 23, 42, .46);
        backdrop-filter: blur(3px);
        -webkit-backdrop-filter: blur(3px);
      }

      .stock-detail-sheet {
        position: absolute;
        left: 50%;
        bottom: 0;
        transform: translateX(-50%);
        width: min(920px, 100%);
        max-height: 90dvh;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        background: var(--card, #f8fafc);
        color: var(--text, #111827);
        border-radius: 30px 30px 0 0;
        box-shadow: 0 -16px 60px rgba(15, 23, 42, .18);
      }

      .stock-detail-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 28px 32px 20px;
        border-bottom: 1px solid rgba(100, 116, 139, .16);
      }

      .stock-detail-header h2 {
        margin: 0;
        font-size: 26px;
        line-height: 1.2;
        font-weight: 800;
      }

      .stock-detail-subtitle {
        margin-top: 7px;
        color: #64748b;
        font-size: 15px;
        font-weight: 700;
      }

      .stock-detail-close {
        width: 52px;
        height: 52px;
        flex: 0 0 auto;
        border: 1px solid rgba(148, 163, 184, .3);
        border-radius: 50%;
        background: rgba(255,255,255,.8);
        color: inherit;
        font-size: 34px;
        line-height: 1;
        cursor: pointer;
      }

      .stock-detail-body {
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
        padding: 24px 24px 34px;
      }

      .stock-detail-periods {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0;
        padding: 3px;
        margin-bottom: 18px;
        border: 1px solid rgba(148,163,184,.28);
        border-radius: 18px;
        background: rgba(255,255,255,.74);
      }

      .stock-detail-period {
        min-height: 54px;
        border: 0;
        border-radius: 15px;
        background: transparent;
        color: #64748b;
        font-size: 18px;
        font-weight: 800;
        cursor: pointer;
      }

      .stock-detail-period.active {
        background: #111827;
        color: #fff;
      }

      .stock-detail-tabs {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-bottom: 22px;
      }

      .stock-detail-tabs button {
        min-height: 58px;
        border: 1px solid rgba(148,163,184,.25);
        border-radius: 18px;
        background: rgba(255,255,255,.7);
        color: #64748b;
        font-size: 18px;
        font-weight: 800;
        cursor: pointer;
      }

      .stock-detail-tabs button.active {
        border: 2px solid #111827;
        color: #111827;
        background: #fff;
      }

      .stock-detail-section-title {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 12px;
        margin: 0 0 18px;
      }

      .stock-detail-section-title strong {
        font-size: 20px;
        font-weight: 900;
      }

      .stock-detail-section-title small {
        color: #64748b;
        font-size: 13px;
        font-weight: 700;
        text-align: right;
      }

      .stock-detail-kpis {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
        margin-bottom: 20px;
      }

      .stock-detail-kpi {
        min-width: 0;
        padding: 18px 16px;
        border: 1px solid rgba(148,163,184,.24);
        border-radius: 18px;
        background: rgba(248,250,252,.9);
      }

      .stock-detail-kpi span {
        display: block;
        margin-bottom: 8px;
        color: #64748b;
        font-size: 13px;
        font-weight: 800;
      }

      .stock-detail-kpi strong {
        display: block;
        white-space: nowrap;
        font-size: 23px;
        line-height: 1.1;
        font-weight: 900;
      }

      .stock-detail-chart {
        width: 100%;
        overflow: hidden;
      }

      .stock-detail-chart svg {
        display: block;
        width: 100%;
        height: auto;
      }

      .stock-detail-legend {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 18px;
        margin-top: 10px;
        color: #64748b;
        font-size: 13px;
        font-weight: 800;
      }

      .stock-detail-legend span {
        display: inline-flex;
        align-items: center;
        gap: 7px;
      }

      .stock-detail-dot {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
      }

      .stock-detail-dot.stock {
        background: #2563eb;
      }

      .stock-detail-dot.sector {
        background: #f59e0b;
      }

      .stock-detail-dot.index {
        background: #64748b;
      }

      .stock-flow-summary {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 16px 18px;
        margin-bottom: 14px;
        border: 1px solid rgba(148,163,184,.24);
        border-radius: 16px;
        background: rgba(255,255,255,.74);
      }

      .stock-flow-summary span {
        color: #64748b;
        font-size: 14px;
        font-weight: 800;
      }

      .stock-flow-summary strong {
        white-space: nowrap;
        font-size: 20px;
        font-weight: 900;
      }

      .stock-detail-note {
        margin-bottom: 8px;
        color: #64748b;
        font-size: 12px;
        line-height: 1.45;
        font-weight: 700;
      }

      .stock-flow-table-caption {
        margin: 12px 0 8px;
        color: #475569;
        font-size: 13px;
        font-weight: 800;
      }

      .stock-flow-table-wrap {
        display: block;
        width: 100%;
        overflow: hidden;
        border: 1px solid rgba(148,163,184,.22);
        border-radius: 16px;
        background: rgba(255,255,255,.76);
      }

      .stock-flow-table-scroll {
        width: 100%;
        overflow: hidden;
      }

      .stock-flow-stage.expanded
      .stock-flow-table-scroll {
        max-height: min(330px, 42vh);
        overflow-y: auto;
        overflow-x: hidden;
        -webkit-overflow-scrolling: touch;
        overscroll-behavior: contain;
        touch-action: pan-y;
      }

      .stock-flow-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
      }

      .stock-flow-table th,
      .stock-flow-table td {
        padding: 12px 6px;
        border-bottom: 1px solid rgba(148,163,184,.14);
        text-align: right;
        white-space: nowrap;
        font-size: 13px;
        font-variant-numeric: tabular-nums;
      }

      .stock-flow-table th {
        position: sticky;
        top: 0;
        z-index: 2;
        background: #f8fafc;
        color: #64748b;
        font-weight: 900;
      }

      .stock-flow-table th:first-child,
      .stock-flow-table td:first-child {
        width: 19%;
        text-align: left;
        padding-left: 12px;
      }

      .stock-flow-table tr:last-child td {
        border-bottom: 0;
      }

      .stock-flow-pull {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 5px;
        width: 100%;
        min-height: 50px;
        margin-top: 8px;
        border: 0;
        background: transparent;
        color: #64748b;
        cursor: pointer;
        touch-action: pan-y;
      }

      .stock-flow-pull-icon {
        width: 38px;
        height: 5px;
        border-radius: 999px;
        background: rgba(100,116,139,.38);
      }

      .stock-flow-pull-label {
        font-size: 12px;
        font-weight: 800;
      }

      .stock-detail-empty {
        padding: 34px 18px;
        text-align: center;
        color: #64748b;
        font-size: 15px;
        font-weight: 700;
      }

      .is-up {
        color: #dc2626 !important;
      }

      .is-down {
        color: #168357 !important;
      }

      .is-flat {
        color: inherit;
      }

      @media (max-width: 640px) {
        .stock-detail-sheet {
          max-height: 88dvh;
          border-radius: 28px 28px 0 0;
        }

        .stock-detail-header {
          padding: 22px 20px 16px;
        }

        .stock-detail-header h2 {
          font-size: 22px;
        }

        .stock-detail-subtitle {
          font-size: 13px;
        }

        .stock-detail-close {
          width: 46px;
          height: 46px;
          font-size: 30px;
        }

        .stock-detail-body {
          padding: 18px 14px 28px;
        }

        .stock-detail-period {
          min-height: 48px;
          font-size: 16px;
        }

        .stock-detail-tabs button {
          min-height: 52px;
          font-size: 16px;
        }

        .stock-detail-section-title strong {
          font-size: 18px;
        }

        .stock-detail-section-title small {
          font-size: 12px;
        }

        .stock-detail-kpis {
          gap: 7px;
        }

        .stock-detail-kpi {
          padding: 14px 10px;
          border-radius: 16px;
        }

        .stock-detail-kpi span {
          font-size: 11px;
        }

        .stock-detail-kpi strong {
          font-size: 18px;
        }

        .stock-detail-legend {
          gap: 12px;
          font-size: 12px;
        }

        .stock-flow-table th,
        .stock-flow-table td {
          padding: 11px 3px;
          font-size: 11px;
        }

        .stock-flow-table th:first-child,
        .stock-flow-table td:first-child {
          padding-left: 7px;
        }

        .stock-flow-stage.expanded
        .stock-flow-table-scroll {
          max-height: min(300px, 40vh);
        }
      }

      @media (min-width: 900px) {
        .stock-detail-sheet {
          bottom: 4vh;
          border-radius: 28px;
          max-height: 92vh;
        }
      }
    `;

    document.head.appendChild(
      style
    );
  }

  function bindStockDetailEvents() {
    document.addEventListener(
      "click",
      e => {
        const row =
          e.target.closest?.(
            "#heatGrid .heat-stock"
          );

        if (!row) {
          return;
        }

        openStockDetail(
          tickerFromRow(row),
          sectorFromRow(row)
        );
      }
    );

    document.addEventListener(
      "keydown",
      e => {
        if (
          e.key !== "Enter" &&
          e.key !== " "
        ) {
          return;
        }

        const row =
          e.target.closest?.(
            "#heatGrid .heat-stock"
          );

        if (!row) {
          return;
        }

        e.preventDefault();

        openStockDetail(
          tickerFromRow(row),
          sectorFromRow(row)
        );
      }
    );
  }

  async function init() {
    injectStockDetailStyles();

    ensureStockDetailModal();

    bindStockDetailEvents();

    await loadSectorConfig();

    ensureControls();

    updateStaticLabels();

    observeHeatmap();

    let tries = 0;

    const wait =
      setInterval(
        () => {
          tries += 1;

          ensureControls();

          updateStaticLabels();

          decorateHeatStocks();

          if (
            directHeatButtons()
              .length
          ) {
            applySectorFilter();

            clearInterval(
              wait
            );
          }

          if (
            tries > 30
          ) {
            clearInterval(
              wait
            );
          }
        },
        150
      );
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      init
    );
  } else {
    init();
  }
})();
