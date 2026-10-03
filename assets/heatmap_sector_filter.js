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

  const PERIODS = [5, 10, 20];
  const DEFAULT_PERIOD = 5;

  let sectorConfig = null;
  let activeSector = "";
  let activeSubgroup = "";

  let stockDetailData = null;
  let stockDetailPromise = null;

  let activeTicker = "";
  let activePeriod = DEFAULT_PERIOD;
  let activeDetailTab = "trend";

  let flowExpanded = false;
  let flowTouchStartY = null;

  const $ = (
    selector,
    root = document
  ) => root.querySelector(selector);

  const $$ = (
    selector,
    root = document
  ) => Array.from(
    root.querySelectorAll(selector)
  );

  function escapeHtml(value) {
    return String(
      value ?? ""
    )
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function num(value) {
    const n = Number(value);

    return Number.isFinite(n)
      ? n
      : null;
  }

  function fmtPct(value) {
    const n = num(value);

    if (n === null) {
      return "—";
    }

    return `${
      n > 0 ? "+" : ""
    }${n.toFixed(2)}%`;
  }

  function fmtLots(value) {
    const n = num(value);

    if (n === null) {
      return "—";
    }

    const rounded =
      Math.round(n);

    return `${
      rounded > 0 ? "+" : ""
    }${rounded.toLocaleString(
      "zh-TW",
      {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
      }
    )}`;
  }

  function valueClass(value) {
    const n = num(value);

    if (n === null) {
      return "";
    }

    if (n > 0) {
      return "is-up";
    }

    if (n < 0) {
      return "is-down";
    }

    return "";
  }

  function latestValue(arr) {
    if (!Array.isArray(arr)) {
      return null;
    }

    for (
      let i = arr.length - 1;
      i >= 0;
      i -= 1
    ) {
      const n = num(arr[i]);

      if (n !== null) {
        return n;
      }
    }

    return null;
  }

  async function fetchJson(url) {
    const sep =
      url.includes("?")
        ? "&"
        : "?";

    const res =
      await fetch(
        `${url}${sep}v=${Date.now()}`,
        {
          cache: "no-store"
        }
      );

    if (!res.ok) {
      throw new Error(
        `${url} ${res.status}`
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
          "./data/sectors.json"
        );
    } catch (error) {
      console.error(
        "[heatmap sector]",
        error
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

    if (stockDetailPromise) {
      return stockDetailPromise;
    }

    stockDetailPromise =
      fetchJson(
        "./data/stock_detail.json"
      )
        .then(data => {
          stockDetailData = data;
          return data;
        })
        .finally(() => {
          stockDetailPromise = null;
        });

    return stockDetailPromise;
  }

  function sectorList() {
    return Array.isArray(
      sectorConfig?.sectors
    )
      ? sectorConfig.sectors
      : [];
  }

  function sectorByName(name) {
    return sectorList()
      .find(
        sec =>
          String(
            sec?.name || ""
          ) ===
          String(name || "")
      ) || null;
  }

  function stockTickerSet(
    sectorName,
    subgroupName = ""
  ) {
    const sec =
      sectorByName(sectorName);

    if (!sec) {
      return new Set();
    }

    let stocks =
      Array.isArray(sec.stocks)
        ? sec.stocks
        : [];

    if (subgroupName) {
      const subgroup =
        (
          Array.isArray(
            sec.subgroups
          )
            ? sec.subgroups
            : []
        ).find(
          item =>
            String(
              item?.name || ""
            ) ===
            String(subgroupName)
        );

      if (subgroup) {
        stocks =
          Array.isArray(
            subgroup.stocks
          )
            ? subgroup.stocks
            : [];
      }
    }

    return new Set(
      stocks
        .map(
          item =>
            String(
              item?.ticker || ""
            ).trim()
        )
        .filter(Boolean)
    );
  }

  function heatGrid() {
    return $("#heatGrid");
  }

  function directHeatButtons() {
    const grid =
      heatGrid();

    if (!grid) {
      return [];
    }

    return $$(
      ".heat-stock",
      grid
    );
  }

  /*
   * 保留原本可以正常點個股的 ticker 解析
   * 不只讀 row.dataset.ticker
   * 子元素／文字內 ticker 也能抓
   */
  function tickerFromRow(row) {
    if (!row) {
      return "";
    }

    const candidates = [
      row.dataset?.ticker,
      row.getAttribute(
        "data-ticker"
      ),
      row.querySelector(
        "[data-ticker]"
      )?.getAttribute(
        "data-ticker"
      ),
      row.querySelector(
        ".ticker"
      )?.textContent
    ];

    for (
      const candidate
      of candidates
    ) {
      const text =
        String(
          candidate || ""
        ).trim();

      const match =
        text.match(
          /\b\d{4,6}\b/
        );

      if (match) {
        return match[0];
      }
    }

    const text =
      String(
        row.textContent || ""
      );

    const match =
      text.match(
        /\b\d{4,6}\b/
      );

    return match
      ? match[0]
      : "";
  }

  function sectorFromRow(row) {
    if (!row) {
      return activeSector || "";
    }

    return (
      row.dataset?.sector ||
      row.getAttribute(
        "data-sector"
      ) ||
      activeSector ||
      ""
    );
  }

  function ensureControls() {
    const grid =
      heatGrid();

    if (!grid) {
      return;
    }

    let wrap =
      $("#heatSectorControls");

    if (!wrap) {
      wrap =
        document.createElement(
          "div"
        );

      wrap.id =
        "heatSectorControls";

      wrap.className =
        "heat-sector-controls";

      grid.parentNode
        ?.insertBefore(
          wrap,
          grid
        );
    }

    if (!$("#heatSectorSelect")) {
      const select =
        document.createElement(
          "select"
        );

      select.id =
        "heatSectorSelect";

      select.className =
        "heat-sector-select";

      select.setAttribute(
        "aria-label",
        "選擇族群"
      );

      select.innerHTML = `
        <option value="">
          全部族群
        </option>
        ${
          sectorList()
            .map(
              sec => `
                <option
                  value="${
                    escapeHtml(
                      sec.name || ""
                    )
                  }"
                >
                  ${
                    escapeHtml(
                      sec.name || ""
                    )
                  }
                </option>
              `
            )
            .join("")
        }
      `;

      select.addEventListener(
        "change",
        () => {
          activeSector =
            select.value || "";

          activeSubgroup = "";

          renderSubgroupSelect();
          applySectorFilter();
        }
      );

      wrap.appendChild(
        select
      );
    }

    if (!$("#heatSubgroupHost")) {
      const host =
        document.createElement(
          "div"
        );

      host.id =
        "heatSubgroupHost";

      host.className =
        "heat-subgroup-host";

      wrap.appendChild(host);
    }

    renderSubgroupSelect();
  }

  function renderSubgroupSelect() {
    const host =
      $("#heatSubgroupHost");

    if (!host) {
      return;
    }

    host.innerHTML = "";

    if (!activeSector) {
      return;
    }

    const sec =
      sectorByName(
        activeSector
      );

    const subgroups =
      Array.isArray(
        sec?.subgroups
      )
        ? sec.subgroups
        : [];

    if (!subgroups.length) {
      return;
    }

    const select =
      document.createElement(
        "select"
      );

    select.id =
      "heatSubgroupSelect";

    select.className =
      "heat-sector-select heat-subgroup-select";

    select.setAttribute(
      "aria-label",
      "選擇細分類"
    );

    select.innerHTML = `
      <option value="">
        全部細分類
      </option>

      ${
        subgroups
          .map(
            group => `
              <option
                value="${
                  escapeHtml(
                    group.name || ""
                  )
                }"
              >
                ${
                  escapeHtml(
                    group.name || ""
                  )
                }
              </option>
            `
          )
          .join("")
      }
    `;

    select.value =
      activeSubgroup;

    select.addEventListener(
      "change",
      () => {
        activeSubgroup =
          select.value || "";

        applySectorFilter();
      }
    );

    host.appendChild(
      select
    );
  }

  function applySectorFilter() {
    const rows =
      directHeatButtons();

    if (!rows.length) {
      return;
    }

    if (!activeSector) {
      rows.forEach(
        row => {
          row.hidden = false;
        }
      );

      return;
    }

    const allowed =
      stockTickerSet(
        activeSector,
        activeSubgroup
      );

    rows.forEach(
      row => {
        const ticker =
          tickerFromRow(row);

        row.hidden =
          !allowed.has(ticker);
      }
    );
  }

  function decorateHeatStocks() {
    directHeatButtons()
      .forEach(
        row => {
          if (
            row.dataset
              .stockDetailReady ===
            "1"
          ) {
            return;
          }

          row.dataset
            .stockDetailReady =
            "1";

          if (
            !row.hasAttribute(
              "tabindex"
            )
          ) {
            row.tabIndex = 0;
          }

          row.setAttribute(
            "role",
            "button"
          );
        }
      );
  }

  function updateStaticLabels() {
    decorateHeatStocks();
  }

  function observeHeatmap() {
    const grid =
      heatGrid();

    if (
      !grid ||
      grid.dataset
        .sectorObserverReady ===
        "1"
    ) {
      return;
    }

    grid.dataset
      .sectorObserverReady =
      "1";

    const observer =
      new MutationObserver(
        () => {
          decorateHeatStocks();
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

  function injectStockDetailStyles() {
    if ($("#stockDetailStyles")) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "stockDetailStyles";

    style.textContent = `
      .heat-sector-controls{
        display:flex;
        align-items:center;
        gap:8px;
        flex-wrap:wrap;
        margin:0 0 12px
      }

      .heat-sector-select{
        appearance:none;
        min-width:160px;
        max-width:100%;
        min-height:40px;
        padding:0 36px 0 12px;
        border:1px solid var(--line,#d9dee8);
        border-radius:12px;
        background:
          var(--card,#fff)
          url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24'%3E%3Cpath fill='%2364748b' d='m7 10 5 5 5-5z'/%3E%3C/svg%3E")
          no-repeat
          right 12px center;
        color:var(--ink,#111827);
        font-size:13px;
        font-weight:800
      }

      .stock-detail-modal{
        position:fixed;
        inset:0;
        z-index:99999;
        display:none;
        align-items:flex-end;
        justify-content:center;
        background:rgba(15,23,42,.52);
        backdrop-filter:blur(3px)
      }

      .stock-detail-modal.open{
        display:flex
      }

      .stock-detail-sheet{
        width:min(760px,100%);
        max-height:92vh;
        overflow:auto;
        overscroll-behavior:contain;
        -webkit-overflow-scrolling:touch;
        border-radius:24px 24px 0 0;
        background:var(--bg,#f8fafc);
        color:var(--ink,#111827);
        box-shadow:0 -20px 60px rgba(15,23,42,.25)
      }

      .stock-detail-head{
        position:sticky;
        top:0;
        z-index:20;
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        padding:14px 16px 10px;
        border-bottom:1px solid var(--line,#e5e7eb);
        background:color-mix(
          in srgb,
          var(--bg,#f8fafc) 94%,
          transparent
        );
        backdrop-filter:blur(14px)
      }

      .stock-detail-title{
        min-width:0
      }

      .stock-detail-title strong{
        display:block;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
        font-size:17px;
        line-height:1.35
      }

      .stock-detail-title small{
        display:block;
        margin-top:2px;
        color:var(--muted,#64748b);
        font-size:11px;
        font-weight:700
      }

      .stock-detail-close{
        flex:0 0 auto;
        width:38px;
        height:38px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:50%;
        background:var(--card,#fff);
        color:var(--ink,#111827);
        font-size:20px;
        cursor:pointer
      }

      .stock-detail-body{
        padding:14px 14px 28px
      }

      .stock-detail-periods{
        display:grid;
        grid-template-columns:repeat(3,1fr);
        gap:6px;
        margin-bottom:10px;
        padding:4px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:14px;
        background:var(--card,#fff)
      }

      .stock-detail-period{
        min-height:38px;
        border:0;
        border-radius:10px;
        background:transparent;
        color:var(--muted,#64748b);
        font-size:12px;
        font-weight:900;
        cursor:pointer
      }

      .stock-detail-period.active{
        background:var(--ink,#111827);
        color:var(--card,#fff)
      }

      .stock-detail-tabs{
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:6px;
        margin-bottom:14px
      }

      .stock-detail-tab{
        min-height:42px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:13px;
        background:var(--card,#fff);
        color:var(--muted,#64748b);
        font-size:13px;
        font-weight:900;
        cursor:pointer
      }

      .stock-detail-tab.active{
        border-color:var(--ink,#111827);
        color:var(--ink,#111827)
      }

      .stock-detail-card{
        padding:14px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:18px;
        background:var(--card,#fff)
      }

      .stock-detail-section-title{
        display:flex;
        justify-content:space-between;
        align-items:flex-start;
        gap:12px;
        margin-bottom:12px
      }

      .stock-detail-section-title strong{
        font-size:14px
      }

      .stock-detail-section-title small{
        color:var(--muted,#64748b);
        font-size:10px;
        font-weight:750;
        text-align:right
      }

      .stock-detail-kpis{
        display:grid;
        grid-template-columns:repeat(3,1fr);
        gap:8px;
        margin-bottom:14px
      }

      .stock-detail-kpi{
        min-width:0;
        padding:11px 10px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:14px;
        background:var(--soft,#f8fafc)
      }

      .stock-detail-kpi span{
        display:block;
        margin-bottom:5px;
        color:var(--muted,#64748b);
        font-size:9px;
        font-weight:800
      }

      .stock-detail-kpi strong{
        display:block;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
        font-size:17px;
        font-variant-numeric:tabular-nums
      }

      .stock-detail-chart{
        width:100%;
        overflow:hidden
      }

      .stock-detail-chart svg{
        display:block;
        width:100%;
        height:auto
      }

      .stock-detail-note{
        margin:0 0 8px;
        color:var(--muted,#64748b);
        font-size:10px;
        font-weight:700;
        line-height:1.5
      }

      .stock-detail-legend{
        display:flex;
        align-items:center;
        justify-content:center;
        flex-wrap:wrap;
        gap:14px;
        margin-top:8px;
        color:var(--muted,#64748b);
        font-size:10px;
        font-weight:750
      }

      .stock-detail-legend span{
        display:flex;
        align-items:center;
        gap:5px
      }

      .stock-detail-dot{
        display:inline-block;
        width:8px;
        height:8px;
        border-radius:50%
      }

      .stock-detail-dot.stock{
        background:#2563eb
      }

      .stock-detail-dot.sector{
        background:#f59e0b
      }

      .stock-detail-dot.index{
        background:#64748b
      }

      .stock-flow-summary{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:12px;
        margin:2px 2px 14px;
        padding:13px 14px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:15px;
        background:linear-gradient(
          180deg,
          var(--card,#fff),
          var(--soft,#f8fafc)
        )
      }

      .stock-flow-summary span{
        color:var(--muted,#64748b);
        font-size:11px;
        font-weight:750
      }

      .stock-flow-summary strong{
        font-size:22px;
        font-variant-numeric:tabular-nums
      }

      .stock-flow-stage{
        position:relative
      }

      .stock-flow-chart-wrap{
        transition:
          opacity .18s ease,
          transform .18s ease
      }

      .stock-flow-table-caption{
        margin:12px 2px 7px;
        color:var(--muted,#64748b);
        font-size:10px;
        font-weight:850
      }

      .stock-flow-table-wrap{
        display:block;
        margin-top:2px;
        overflow:hidden;
        border:1px solid var(--line,#e5e7eb);
        border-radius:16px;
        background:var(--card,#fff)
      }

      .stock-flow-table-scroll{
        overflow:hidden;
        overscroll-behavior:contain;
        -webkit-overflow-scrolling:touch
      }

      .stock-flow-stage.expanded
      .stock-flow-table-scroll{
        max-height:min(330px,42vh);
        overflow-y:auto;
        touch-action:pan-y
      }

      .stock-flow-table{
        width:100%;
        min-width:0;
        table-layout:fixed;
        border-collapse:separate;
        border-spacing:0
      }

      .stock-flow-table th,
      .stock-flow-table td{
        padding:12px 4px;
        border-bottom:1px solid var(--line,#e5e7eb);
        text-align:center;
        white-space:nowrap;
        font-size:11px;
        font-variant-numeric:tabular-nums
      }

      .stock-flow-table th{
        position:sticky;
        top:0;
        z-index:2;
        background:var(--soft,#f8fafc);
        color:var(--muted,#64748b);
        font-size:10px;
        font-weight:900;
        letter-spacing:.02em
      }

      .stock-flow-table th:nth-child(1),
      .stock-flow-table td:nth-child(1){
        width:16%;
        text-align:left;
        padding-left:12px
      }

      .stock-flow-table th:nth-child(2),
      .stock-flow-table td:nth-child(2){
        width:21%
      }

      .stock-flow-table th:nth-child(3),
      .stock-flow-table td:nth-child(3){
        width:18%
      }

      .stock-flow-table th:nth-child(4),
      .stock-flow-table td:nth-child(4){
        width:21%
      }

      .stock-flow-table th:nth-child(5),
      .stock-flow-table td:nth-child(5){
        width:24%;
        padding-right:8px;
        font-weight:900
      }

      .stock-flow-table tbody
      tr:last-child td{
        border-bottom:0
      }

      .stock-flow-table tbody
      tr:nth-child(even){
        background:color-mix(
          in srgb,
          var(--soft,#f8fafc) 55%,
          transparent
        )
      }

      .stock-flow-pull{
        display:flex;
        align-items:center;
        justify-content:center;
        width:100%;
        min-height:46px;
        margin:8px 0 0;
        border:0;
        background:transparent;
        color:var(--ink,#111827);
        cursor:pointer;
        touch-action:pan-y
      }

      .stock-flow-pull-icon{
        display:block;
        width:16px;
        height:16px;
        border-left:4px solid currentColor;
        border-top:4px solid currentColor;
        transform:rotate(45deg);
        border-radius:2px
      }

      .stock-flow-stage.expanded
      .stock-flow-pull-icon{
        transform:rotate(225deg)
      }

      .stock-flow-pull-label{
        margin-left:12px;
        color:var(--muted,#64748b);
        font-size:10px;
        font-weight:800
      }

      .stock-detail-loading,
      .stock-detail-empty{
        padding:30px 12px;
        color:var(--muted,#64748b);
        text-align:center;
        font-size:12px;
        font-weight:750
      }

      .is-up{
        color:#dc2626!important
      }

      .is-down{
        color:#168357!important
      }

      @media(min-width:700px){
        .stock-detail-modal{
          align-items:center;
          padding:24px
        }

        .stock-detail-sheet{
          border-radius:24px;
          max-height:88vh
        }
      }

      @media(max-width:520px){
        .stock-detail-body{
          padding:
            12px 10px
            calc(
              24px +
              env(
                safe-area-inset-bottom
              )
            )
        }

        .stock-detail-card{
          padding:12px 9px
        }

        .stock-detail-kpis{
          gap:5px
        }

        .stock-detail-kpi{
          padding:10px 7px
        }

        .stock-detail-kpi strong{
          font-size:15px
        }

        .stock-detail-section-title{
          gap:7px
        }

        .stock-flow-table th,
        .stock-flow-table td{
          padding:11px 2px;
          font-size:10px
        }

        .stock-flow-table th:nth-child(1),
        .stock-flow-table td:nth-child(1){
          padding-left:7px
        }

        .stock-flow-table th:nth-child(5),
        .stock-flow-table td:nth-child(5){
          padding-right:5px
        }

        .stock-flow-stage.expanded
        .stock-flow-table-scroll{
          max-height:38vh
        }
      }
    `;

    document.head
      .appendChild(style);
  }

  function ensureStockDetailModal() {
    let modal =
      $("#stockDetailModal");

    if (modal) {
      return modal;
    }

    modal =
      document.createElement(
        "div"
      );

    modal.id =
      "stockDetailModal";

    modal.className =
      "stock-detail-modal";

    modal.setAttribute(
      "aria-hidden",
      "true"
    );

    modal.innerHTML = `
      <section
        class="stock-detail-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="個股詳細資訊"
      >
        <header
          class="stock-detail-head"
        >
          <div
            class="stock-detail-title"
          >
            <strong
              id="stockDetailTitle"
            >
              個股資訊
            </strong>

            <small
              id="stockDetailSubtitle"
            ></small>
          </div>

          <button
            class="stock-detail-close"
            id="stockDetailClose"
            type="button"
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

    document.body
      .appendChild(modal);

    const close = () => {
      modal.classList
        .remove("open");

      modal.setAttribute(
        "aria-hidden",
        "true"
      );

      document.documentElement
        .style.overflow = "";

      activeTicker = "";
      activePeriod =
        DEFAULT_PERIOD;

      activeDetailTab =
        "trend";

      flowExpanded = false;
    };

    $(
      "#stockDetailClose",
      modal
    )?.addEventListener(
      "click",
      close
    );

    modal.addEventListener(
      "click",
      e => {
        if (e.target === modal) {
          close();
        }
      }
    );

    document.addEventListener(
      "keydown",
      e => {
        if (
          e.key === "Escape" &&
          modal.classList
            .contains("open")
        ) {
          close();
        }
      }
    );

    return modal;
  }

  async function openStockDetail(
    ticker,
    sectorName = ""
  ) {
    ticker =
      String(
        ticker || ""
      ).trim();

    if (!ticker) {
      return;
    }

    activeTicker = ticker;

    activeSector =
      sectorName ||
      activeSector ||
      "";

    activePeriod =
      DEFAULT_PERIOD;

    activeDetailTab =
      "trend";

    flowExpanded = false;

    const modal =
      ensureStockDetailModal();

    modal.classList
      .add("open");

    modal.setAttribute(
      "aria-hidden",
      "false"
    );

    document.documentElement
      .style.overflow =
      "hidden";

    const body =
      $("#stockDetailBody");

    const title =
      $("#stockDetailTitle");

    const subtitle =
      $("#stockDetailSubtitle");

    if (title) {
      title.textContent =
        ticker;
    }

    if (subtitle) {
      subtitle.textContent =
        activeSector || "";
    }

    if (body) {
      body.innerHTML = `
        <div
          class="stock-detail-loading"
        >
          載入個股資料中…
        </div>
      `;
    }

    try {
      const data =
        await loadStockDetail();

      if (
        activeTicker !== ticker
      ) {
        return;
      }

      const stock =
        data?.stocks?.[ticker];

      if (!stock) {
        if (body) {
          body.innerHTML = `
            <div
              class="stock-detail-empty"
            >
              目前沒有 ${
                escapeHtml(ticker)
              } 的個股詳細資料
            </div>
          `;
        }

        return;
      }

      /*
       * 如果點擊當下沒有取得族群，
       * 使用後端 primary_sector / sectors
       */
      if (
        !activeSector ||
        !data?.sectors?.[
          activeSector
        ]
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
            data?.sectors?.[
              stock.primary_sector
            ]
          )
            ? stock.primary_sector
            : candidates.find(
                name =>
                  data?.sectors?.[
                    name
                  ]
              );

        if (fallbackSector) {
          activeSector =
            fallbackSector;
        }
      }

      if (title) {
        title.textContent =
          `${
            stock.name ||
            ticker
          } ${ticker}`;
      }

      if (subtitle) {
        subtitle.textContent =
          `${
            activeSector ||
            "市場熱力圖"
          }｜資料截至 ${
            data.as_of_date ||
            "—"
          }`;
      }

      renderStockDetail();
    } catch (error) {
      console.error(
        "[stock detail]",
        error
      );

      if (body) {
        body.innerHTML = `
          <div
            class="stock-detail-empty"
          >
            個股資料載入失敗
          </div>
        `;
      }
    }
  }

  function renderStockDetail() {
    const body =
      $("#stockDetailBody");

    if (
      !body ||
      !stockDetailData ||
      !activeTicker
    ) {
      return;
    }

    const stock =
      stockDetailData
        ?.stocks
        ?.[activeTicker];

    if (!stock) {
      return;
    }

    body.innerHTML = `
      <div
        class="stock-detail-periods"
      >
        ${
          PERIODS
            .map(
              period => `
                <button
                  class="stock-detail-period ${
                    activePeriod ===
                    period
                      ? "active"
                      : ""
                  }"
                  type="button"
                  data-period="${period}"
                >
                  ${period}日
                </button>
              `
            )
            .join("")
        }
      </div>

      <div
        class="stock-detail-tabs"
      >
        <button
          class="stock-detail-tab ${
            activeDetailTab ===
            "trend"
              ? "active"
              : ""
          }"
          type="button"
          data-detail-tab="trend"
        >
          走勢
        </button>

        <button
          class="stock-detail-tab ${
            activeDetailTab ===
            "flow"
              ? "active"
              : ""
          }"
          type="button"
          data-detail-tab="flow"
        >
          籌碼
        </button>
      </div>

      <div
        class="stock-detail-card"
      >
        ${
          activeDetailTab ===
          "trend"
            ? renderTrendPanel(
                stock
              )
            : renderFlowPanel(
                stock
              )
        }
      </div>
    `;

    $$(
      ".stock-detail-period",
      body
    ).forEach(
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

            flowExpanded =
              false;

            renderStockDetail();
          }
        );
      }
    );

    $$(
      ".stock-detail-tab",
      body
    ).forEach(
      button => {
        button.addEventListener(
          "click",
          () => {
            activeDetailTab =
              button.dataset
                .detailTab ===
              "flow"
                ? "flow"
                : "trend";

            flowExpanded =
              false;

            renderStockDetail();
          }
        );
      }
    );

    if (
      activeDetailTab ===
      "flow"
    ) {
      bindFlowPull(body);
    }
  }

  function periodValues(
    object,
    period
  ) {
    const byPeriod =
      object
        ?.returns_by_period;

    if (
      byPeriod &&
      Array.isArray(
        byPeriod[
          String(period)
        ]
      )
    ) {
      return byPeriod[
        String(period)
      ];
    }

    if (
      period === 5 &&
      Array.isArray(
        object?.returns
      )
    ) {
      return object.returns;
    }

    return [];
  }

  function periodLabels(
    period
  ) {
    const byPeriod =
      stockDetailData
        ?.date_labels_by_period;

    if (
      byPeriod &&
      Array.isArray(
        byPeriod[
          String(period)
        ]
      )
    ) {
      return byPeriod[
        String(period)
      ];
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
    function renderTrendPanel(
    stock
  ) {
    /*
     * 點擊當下如果沒有取得正確族群，
     * 使用 stock_detail.json 後端產生的
     * primary_sector / sectors 作為 fallback
     */
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
            ?.[stock.primary_sector]
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
          </span>

          <strong
            class="${
              valueClass(
                vsMarket
              )
            }"
          >
            ${
              fmtPct(
                vsMarket
              )
            }
          </strong>
        </div>
      </div>

      <div
        class="stock-detail-chart"
      >
        ${
          lineChartSvg(
            labels,
            [
              {
                values:
                  stockValues,
                color:
                  "#2563eb"
              },
              {
                values:
                  sectorValues,
                color:
                  "#f59e0b"
              },
              {
                values:
                  benchValues,
                color:
                  "#64748b"
              }
            ]
          )
        }
      </div>

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
            escapeHtml(
              activeSector ||
              "同族群"
            )
          }
        </span>

        <span>
          <i
            class="stock-detail-dot index"
          ></i>
          ${
            escapeHtml(
              bench.name ||
              "上市加權指數"
            )
          }
        </span>
      </div>
    `;
  }

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

    const chartRows =
      allRows.slice(
        -activePeriod
      );

    const recent5 =
      allRows.slice(-5);

    const total =
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

    const vals =
      rows.map(
        x =>
          Number(
            x.total_lots ||
            0
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
              Number(
                row.total_lots ||
                0
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
   
   
