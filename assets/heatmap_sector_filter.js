/* =========================================================
   市場熱力圖：族群下拉 + 細分類 + 個股資訊
   個股視窗：5 / 10 / 20 日共用期間
   籌碼：圖表預設，支援上拉／點箭頭展開明細
   2026-10-03
   ========================================================= */

(function () {
  const $h = (s, root = document) => root.querySelector(s);

  const PERIODS = [5, 10, 20];
  const DEFAULT_PERIOD = 5;

  let sectorConfig = [];
  let selectedSector = "all";
  let selectedSubgroup = "all";
  let applying = false;

  let stockDetailData = null;
  let stockDetailPromise = null;
  let activeTicker = null;
  let activeSector = null;
  let activeTab = "trend";
  let activePeriod = DEFAULT_PERIOD;
  let flowExpanded = false;
  let flowTouchStartY = null;

  async function loadSectorConfig() {
    try {
      const r = await fetch(
        "./data/sectors.json?v=" + Date.now(),
        { cache: "no-store" }
      );

      if (!r.ok) {
        throw new Error("HTTP " + r.status);
      }

      const d = await r.json();
      sectorConfig = d.sectors || [];
      return sectorConfig;
    } catch (e) {
      console.error("sector selector load failed", e);
      sectorConfig = [];
      return [];
    }
  }

  function findSector(name) {
    return sectorConfig.find(x => x.name === name);
  }

  function directHeatButtons() {
    const grid = $h("#heatGrid");
    if (!grid) return [];

    return [...grid.children].filter(
      el => el.matches?.("button.heat[data-sec]")
    );
  }

  function updateStaticLabels() {
    const count = sectorConfig.length;

    const heatHero = $h("#heat .hero p");
    if (heatHero) {
      heatHero.textContent =
        `${count} 個自訂族群｜市值加權｜紅漲綠跌｜可直接下拉選族群`;
    }

    const revenueHero = $h("#monthlyRevenue .hero p");
    if (revenueHero) {
      revenueHero.textContent =
        `${count} 個科技族群｜最新已公布月份｜營收、MoM、YoY`;
    }

    document.querySelectorAll(".feature-card").forEach(card => {
      const title =
        card.querySelector(".feature-copy b")
          ?.textContent?.trim();

      const small =
        card.querySelector(".feature-copy small");

      if (!small) return;

      if (title === "市場熱力圖") {
        small.textContent = `${count}族群・5分鐘`;
      }

      if (title === "月營收公布") {
        small.textContent = `${count}族群`;
      }
    });
  }

  function ensureControls() {
    const grid = $h("#heatGrid");

    if (!grid || $h("#heatSectorControl")) {
      return;
    }

    const wrap = document.createElement("div");
    wrap.id = "heatSectorControl";
    wrap.className = "heat-sector-control";

    wrap.innerHTML = `
      <div class="heat-sector-copy">
        <span class="heat-sector-kicker">SECTOR FILTER</span>
        <strong>選擇想看的族群</strong>
        <small id="heatSectorMeta">
          ${sectorConfig.length} 個自訂族群
        </small>
      </div>

      <div class="heat-sector-actions">
        <label
          class="heat-sector-select-wrap"
          for="heatSectorSelect"
        >
          <span>族群</span>

          <select
            id="heatSectorSelect"
            aria-label="選擇熱力圖族群"
          >
            <option value="all">全部族群</option>

            ${sectorConfig.map(sec => `
              <option value="${sec.name}">
                ${sec.name}
              </option>
            `).join("")}
          </select>
        </label>

        <button
          id="heatSectorReset"
          class="heat-sector-reset"
          type="button"
        >
          全部
        </button>
      </div>
    `;

    grid.parentNode.insertBefore(wrap, grid);

    $h("#heatSectorSelect")?.addEventListener(
      "change",
      e => {
        selectedSector = e.target.value;
        selectedSubgroup = "all";
        rerenderSelected();
      }
    );

    $h("#heatSectorReset")?.addEventListener(
      "click",
      () => {
        selectedSector = "all";
        selectedSubgroup = "all";

        const sel = $h("#heatSectorSelect");
        if (sel) sel.value = "all";

        rerenderSelected();
      }
    );
  }

  function rerenderSelected() {
    try {
      if (typeof st !== "undefined") {
        st.openSector =
          selectedSector === "all"
            ? null
            : selectedSector;
      }

      if (typeof heat === "function") {
        Promise.resolve(heat()).finally(() => {
          setTimeout(() => {
            applySectorFilter();
            injectSubgroupControl();
            decorateHeatStocks();
          }, 20);
        });

        return;
      }
    } catch (e) {
      console.warn("heat rerender fallback", e);
    }

    applySectorFilter();
    injectSubgroupControl();
    decorateHeatStocks();
  }

  function applySectorFilter() {
    if (applying) return;

    applying = true;

    directHeatButtons().forEach(btn => {
      btn.hidden =
        selectedSector !== "all" &&
        btn.dataset.sec !== selectedSector;
    });

    const meta = $h("#heatSectorMeta");
    if (meta) {
      meta.textContent =
        selectedSector === "all"
          ? `${sectorConfig.length} 個自訂族群`
          : `目前：${selectedSector}`;
    }

    const reset = $h("#heatSectorReset");
    if (reset) {
      reset.classList.toggle(
        "active",
        selectedSector !== "all"
      );
    }

    applying = false;
  }

  function injectSubgroupControl() {
    if (selectedSector === "all") return;

    const detail = $h("#heatGrid .heat-detail");
    if (!detail) return;

    const sector = findSector(selectedSector);
    const groups = sector?.subgroups || [];

    if (!groups.length) return;

    if (detail.querySelector(".heat-subgroup-control")) {
      filterSubgroupStocks();
      return;
    }

    const control = document.createElement("div");
    control.className = "heat-subgroup-control";

    control.innerHTML = `
      <div>
        <span class="heat-subgroup-kicker">SUB-SECTOR</span>
        <b>${sector.name}</b>
      </div>

      <label class="heat-subgroup-select-wrap">
        <span>細分類</span>

        <select
          id="heatSubgroupSelect"
          aria-label="選擇細分產業"
        >
          <option value="all">全部成分</option>

          ${groups.map(g => `
            <option value="${g.name}">
              ${g.name}
            </option>
          `).join("")}
        </select>
      </label>
    `;

    const list = detail.querySelector(".heat-stock-list");
    if (!list) return;

    detail.insertBefore(control, list);

    const select =
      control.querySelector("#heatSubgroupSelect");

    if (select) {
      select.value = selectedSubgroup;

      select.addEventListener("change", e => {
        selectedSubgroup = e.target.value;
        filterSubgroupStocks();
      });
    }

    filterSubgroupStocks();
  }

  function filterSubgroupStocks() {
    const detail = $h("#heatGrid .heat-detail");
    const sector = findSector(selectedSector);

    if (!detail || !sector) return;

    const group = (sector.subgroups || []).find(
      g => g.name === selectedSubgroup
    );

    const allowed = group
      ? new Set((group.tickers || []).map(String))
      : null;

    const rows = [
      ...detail.querySelectorAll(".heat-stock")
    ];

    let visible = 0;

    rows.forEach(row => {
      const ticker =
        row.querySelector(".t")
          ?.textContent?.trim();

      const show =
        !allowed ||
        allowed.has(String(ticker));

      row.hidden = !show;
      if (show) visible += 1;
    });

    const meta =
      detail.querySelector(".heat-detail-head > span");

    if (meta) {
      meta.textContent =
        selectedSubgroup === "all"
          ? `${rows.length} 檔｜依漲跌幅排序`
          : `${selectedSubgroup}｜${visible} 檔｜依漲跌幅排序`;
    }
  }

  function observeHeatmap() {
    const grid = $h("#heatGrid");
    if (!grid) return;

    const observer = new MutationObserver(() => {
      if (applying) return;

      applySectorFilter();

      setTimeout(() => {
        injectSubgroupControl();
        decorateHeatStocks();
      }, 0);
    });

    observer.observe(grid, {
      childList: true,
      subtree: true
    });
  }

  function injectStockDetailStyles() {
    if (document.getElementById("stockDetailStyle")) {
      return;
    }

    const style = document.createElement("style");
    style.id = "stockDetailStyle";

    style.textContent = `
      .heat-stock{
        cursor:pointer;
        transition:transform .14s ease,box-shadow .14s ease,border-color .14s ease
      }

      .heat-stock:hover{
        transform:translateY(-1px);
        box-shadow:0 6px 16px rgba(15,23,42,.08)
      }

      .heat-stock:focus-visible{
        outline:2px solid #64748b;
        outline-offset:2px
      }

      .stock-detail-overlay{
        position:fixed;
        inset:0;
        z-index:1000;
        display:none;
        align-items:flex-end;
        justify-content:center;
        padding:24px;
        background:rgba(7,12,20,.58);
        backdrop-filter:blur(4px)
      }

      .stock-detail-overlay.open{
        display:flex
      }

      .stock-detail-sheet{
        width:min(820px,100%);
        max-height:min(90vh,920px);
        overflow:auto;
        border:1px solid var(--line);
        border-radius:24px;
        background:var(--card);
        color:var(--ink);
        box-shadow:0 28px 80px rgba(2,6,23,.30);
        overscroll-behavior:contain
      }

      .stock-detail-head{
        position:sticky;
        top:0;
        z-index:8;
        display:flex;
        align-items:flex-start;
        justify-content:space-between;
        gap:14px;
        padding:20px 20px 15px;
        border-bottom:1px solid var(--line);
        background:color-mix(in srgb,var(--card) 94%,transparent);
        backdrop-filter:blur(14px)
      }

      .stock-detail-name{
        font-size:22px;
        font-weight:950;
        line-height:1.15;
        letter-spacing:-.02em
      }

      .stock-detail-meta{
        margin-top:6px;
        color:var(--muted);
        font-size:11px;
        font-weight:650
      }

      .stock-detail-close{
        flex:0 0 42px;
        width:42px;
        height:42px;
        border:1px solid var(--line);
        border-radius:13px;
        background:var(--soft);
        color:var(--ink);
        font-size:24px;
        line-height:1;
        cursor:pointer
      }

      .stock-period-wrap{
        padding:13px 20px 0
      }

      .stock-period-switch{
        display:grid;
        grid-template-columns:repeat(3,1fr);
        gap:6px;
        padding:4px;
        border:1px solid var(--line);
        border-radius:14px;
        background:var(--soft)
      }

      .stock-period-btn{
        min-height:38px;
        border:0;
        border-radius:10px;
        background:transparent;
        color:var(--muted);
        font-size:12px;
        font-weight:900;
        cursor:pointer
      }

      .stock-period-btn.active{
        background:var(--card);
        color:var(--ink);
        box-shadow:0 2px 8px rgba(15,23,42,.10)
      }

      .stock-detail-tabs{
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:8px;
        padding:10px 20px 0
      }

      .stock-detail-tab{
        min-height:46px;
        border:1px solid var(--line);
        border-radius:14px;
        background:var(--soft);
        color:var(--muted);
        font-size:13px;
        font-weight:900;
        cursor:pointer;
        transition:all .16s ease
      }

      .stock-detail-tab.active{
        background:#111827;
        color:#fff;
        border-color:#111827;
        box-shadow:0 8px 18px rgba(15,23,42,.16)
      }

      html[data-theme="dark"] .stock-detail-tab.active{
        background:#e7edf5;
        color:#111827;
        border-color:#e7edf5
      }

      .stock-detail-body{
        padding:18px 20px 24px
      }

      .stock-detail-section-title{
        display:flex;
        align-items:flex-end;
        justify-content:space-between;
        gap:12px;
        margin:2px 2px 12px
      }

      .stock-detail-section-title strong{
        font-size:14px;
        font-weight:950
      }

      .stock-detail-section-title small{
        color:var(--muted);
        font-size:10px;
        font-weight:650
      }

      .stock-detail-note{
        margin:0 2px 12px;
        color:var(--muted);
        font-size:10px;
        line-height:1.55
      }

      .stock-detail-metrics{
        display:grid;
        grid-template-columns:repeat(3,1fr);
        gap:10px;
        margin-bottom:16px
      }

      .stock-detail-metric{
        position:relative;
        min-width:0;
        overflow:hidden;
        padding:13px 13px 12px;
        border:1px solid var(--line);
        border-radius:15px;
        background:linear-gradient(180deg,var(--card),var(--soft))
      }

      .stock-detail-metric::before{
        content:"";
        position:absolute;
        left:0;
        top:0;
        bottom:0;
        width:3px;
        background:#94a3b8
      }

      .stock-detail-metric.stock::before{background:#dc2626}
      .stock-detail-metric.sector::before{background:#2563eb}
      .stock-detail-metric.index::before{background:#64748b}

      .stock-detail-metric small{
        display:block;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
        color:var(--muted);
        font-size:10px;
        font-weight:750
      }

      .stock-detail-metric strong{
        display:block;
        margin-top:6px;
        font-size:20px;
        font-variant-numeric:tabular-nums;
        letter-spacing:-.02em
      }

      .stock-detail-chart{
        padding:12px 10px 8px;
        border:1px solid var(--line);
        border-radius:17px;
        background:linear-gradient(
          180deg,
          var(--soft),
          color-mix(in srgb,var(--soft) 72%,var(--card))
        );
        overflow:hidden
      }

      .stock-detail-chart svg{
        display:block;
        width:100%;
        height:auto;
        overflow:visible
      }

      .stock-detail-legend{
        display:flex;
        gap:14px;
        flex-wrap:wrap;
        margin:11px 6px 3px;
        color:var(--muted);
        font-size:10px;
        font-weight:700
      }

      .stock-detail-legend span{
        display:inline-flex;
        align-items:center;
        gap:6px
      }

      .stock-detail-dot{
        width:9px;
        height:9px;
        border-radius:999px
      }

      .stock-detail-dot.stock{background:#dc2626}
      .stock-detail-dot.sector{background:#2563eb}
      .stock-detail-dot.index{background:#64748b}

      .stock-flow-summary{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:12px;
        margin:2px 2px 14px;
        padding:13px 14px;
        border:1px solid var(--line);
        border-radius:15px;
        background:linear-gradient(180deg,var(--card),var(--soft))
      }

      .stock-flow-summary span{
        color:var(--muted);
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
        transition:opacity .18s ease,transform .18s ease
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
        color:var(--ink);
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

      .stock-flow-stage.expanded .stock-flow-pull-icon{
        transform:rotate(225deg)
      }

      .stock-flow-pull-label{
        margin-left:12px;
        color:var(--muted);
        font-size:10px;
        font-weight:800
      }

      .stock-flow-table-wrap{
        display:none;
        margin-top:2px;
        overflow:hidden;
        border:1px solid var(--line);
        border-radius:16px;
        background:var(--card)
      }

      .stock-flow-stage.expanded .stock-flow-chart-wrap{
        display:none
      }

      .stock-flow-stage.expanded .stock-flow-table-wrap{
        display:block
      }

      .stock-flow-table-scroll{
        max-height:52vh;
        overflow:auto;
        overscroll-behavior:contain;
        -webkit-overflow-scrolling:touch
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
        border-bottom:1px solid var(--line);
        text-align:center;
        white-space:nowrap;
        font-size:11px;
        font-variant-numeric:tabular-nums
      }

      .stock-flow-table th{
        position:sticky;
        top:0;
        z-index:2;
        background:var(--soft);
        color:var(--muted);
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

      .stock-flow-table tbody tr:last-child td{
        border-bottom:0
      }

      .stock-flow-table tbody tr:nth-child(even){
        background:color-mix(
          in srgb,
          var(--soft) 55%,
          transparent
        )
      }

      .stock-detail-loading,
      .stock-detail-empty{
        padding:30px 12px;
        color:var(--muted);
        text-align:center;
        font-size:12px
      }

      @media(max-width:720px){
        .stock-detail-overlay{
          padding:0;
          align-items:flex-end
        }

        .stock-detail-sheet{
          width:100%;
          max-height:92vh;
          border-radius:22px 22px 0 0;
          border-left:0;
          border-right:0;
          border-bottom:0
        }

        .stock-detail-head{
          padding:16px 15px 12px
        }

        .stock-detail-name{
          font-size:20px
        }

        .stock-period-wrap{
          padding:11px 14px 0
        }

        .stock-period-btn{
          min-height:36px;
          font-size:11px
        }

        .stock-detail-tabs{
          padding:9px 14px 0;
          gap:7px
        }

        .stock-detail-tab{
          min-height:44px;
          font-size:12px
        }

        .stock-detail-body{
          padding:14px 14px 20px
        }

        .stock-detail-section-title{
          align-items:flex-start;
          flex-direction:column;
          gap:3px
        }

        .stock-detail-metrics{
          gap:7px
        }

        .stock-detail-metric{
          padding:10px 8px
        }

        .stock-detail-metric small{
          font-size:9px
        }

        .stock-detail-metric strong{
          font-size:16px
        }

        .stock-detail-chart{
          padding:8px 5px 6px
        }

        .stock-flow-summary{
          padding:11px 12px
        }

        .stock-flow-summary strong{
          font-size:19px
        }

        .stock-flow-table th,
        .stock-flow-table td{
          padding:11px 2px;
          font-size:10px
        }

        .stock-flow-table th{
          font-size:9px
        }

        .stock-flow-table th:nth-child(1),
        .stock-flow-table td:nth-child(1){
          padding-left:10px
        }

        .stock-flow-table th:nth-child(5),
        .stock-flow-table td:nth-child(5){
          padding-right:6px
        }
      }
    `;

    document.head.appendChild(style);
  }

  function ensureStockDetailModal() {
    let overlay =
      document.getElementById("stockDetailOverlay");

    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "stockDetailOverlay";
    overlay.className = "stock-detail-overlay";

    overlay.innerHTML = `
      <div
        class="stock-detail-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="個股資訊"
      >
        <div class="stock-detail-head">
          <div>
            <div
              id="stockDetailName"
              class="stock-detail-name"
            >
              個股資訊
            </div>

            <div
              id="stockDetailMeta"
              class="stock-detail-meta"
            ></div>
          </div>

          <button
            id="stockDetailClose"
            class="stock-detail-close"
            type="button"
            aria-label="關閉"
          >
            ×
          </button>
        </div>

        <div class="stock-period-wrap">
          <div
            class="stock-period-switch"
            role="tablist"
            aria-label="選擇資料期間"
          >
            ${PERIODS.map(p => `
              <button
                class="stock-period-btn ${
                  p === DEFAULT_PERIOD
                    ? "active"
                    : ""
                }"
                type="button"
                data-stock-period="${p}"
              >
                ${p}日
              </button>
            `).join("")}
          </div>
        </div>

        <div class="stock-detail-tabs">
          <button
            class="stock-detail-tab active"
            type="button"
            data-stock-detail-tab="trend"
          >
            走勢
          </button>

          <button
            class="stock-detail-tab"
            type="button"
            data-stock-detail-tab="flow"
          >
            籌碼
          </button>
        </div>

        <div
          id="stockDetailBody"
          class="stock-detail-body"
        ></div>
      </div>
    `;

    document.body.appendChild(overlay);

    overlay
      .querySelector("#stockDetailClose")
      ?.addEventListener(
        "click",
        closeStockDetail
      );

    overlay.addEventListener("click", e => {
      if (e.target === overlay) {
        closeStockDetail();
      }
    });

    overlay
      .querySelectorAll("[data-stock-period]")
      .forEach(btn => {
        btn.addEventListener("click", () => {
          const p =
            Number(btn.dataset.stockPeriod);

          if (!PERIODS.includes(p)) {
            return;
          }

          activePeriod = p;
          flowExpanded = false;

          overlay
            .querySelectorAll(
              "[data-stock-period]"
            )
            .forEach(x => {
              x.classList.toggle(
                "active",
                Number(
                  x.dataset.stockPeriod
                ) === activePeriod
              );
            });

          renderActiveStockDetail();
        });
      });

    overlay
      .querySelectorAll(
        "[data-stock-detail-tab]"
      )
      .forEach(btn => {
        btn.addEventListener("click", () => {
          activeTab =
            btn.dataset.stockDetailTab;

          flowExpanded = false;

          overlay
            .querySelectorAll(
              "[data-stock-detail-tab]"
            )
            .forEach(x => {
              x.classList.toggle(
                "active",
                x === btn
              );
            });

          renderActiveStockDetail();
        });
      });

    document.addEventListener(
      "keydown",
      e => {
        if (
          e.key === "Escape" &&
          overlay.classList.contains("open")
        ) {
          closeStockDetail();
        }
      }
    );

    return overlay;
  }

  async function loadStockDetailData() {
    if (stockDetailData) {
      return stockDetailData;
    }

    if (stockDetailPromise) {
      return stockDetailPromise;
    }

    stockDetailPromise = fetch(
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
        stockDetailData = d;
        return d;
      })
      .catch(e => {
        console.error(
          "stock detail load failed",
          e
        );
        throw e;
      })
      .finally(() => {
        stockDetailPromise = null;
      });

    return stockDetailPromise;
  }

  function decorateHeatStocks() {
    document
      .querySelectorAll(
        "#heatGrid .heat-stock"
      )
      .forEach(row => {
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
          "開啟個股資訊"
        );
      });
  }

  function sectorFromRow(row) {
    const detail =
      row.closest(".heat-detail");

    if (!detail) return "";

    const prev =
      detail.previousElementSibling;

    if (
      prev?.matches?.(
        "button.heat[data-sec]"
      )
    ) {
      return prev.dataset.sec || "";
    }

    const head =
      detail.querySelector(
        ".heat-detail-head b"
      );

    if (!head) return "";

    return [...head.childNodes]
      .filter(
        n =>
          n.nodeType ===
          Node.TEXT_NODE
      )
      .map(n => n.textContent)
      .join(" ")
      .trim();
  }

  function tickerFromRow(row) {
    return (
      row.querySelector(".t")
        ?.textContent?.trim()
      || ""
    );
  }

  async function openStockDetail(
    ticker,
    sector
  ) {
    if (!ticker) return;

    activeTicker = String(ticker);
    activeSector = String(sector || "");

    activeTab = "trend";
    activePeriod = DEFAULT_PERIOD;
    flowExpanded = false;

    const overlay =
      ensureStockDetailModal();

    overlay
      .querySelectorAll(
        "[data-stock-detail-tab]"
      )
      .forEach(btn => {
        btn.classList.toggle(
          "active",
          btn.dataset.stockDetailTab ===
            "trend"
        );
      });

    overlay
      .querySelectorAll(
        "[data-stock-period]"
      )
      .forEach(btn => {
        btn.classList.toggle(
          "active",
          Number(
            btn.dataset.stockPeriod
          ) === activePeriod
        );
      });

    overlay.classList.add("open");
    document.body.style.overflow =
      "hidden";

    const body =
      overlay.querySelector(
        "#stockDetailBody"
      );

    body.innerHTML = `
      <div class="stock-detail-loading">
        載入資料…
      </div>
    `;

    try {
      await loadStockDetailData();
      renderActiveStockDetail();
    } catch (e) {
      body.innerHTML = `
        <div class="stock-detail-empty">
          尚未產生個股資料<br>
          請先執行一次 Daily close update
        </div>
      `;
    }
  }

  function closeStockDetail() {
    const overlay =
      document.getElementById(
        "stockDetailOverlay"
      );

    overlay?.classList.remove("open");

    document.body.style.overflow = "";

    activeTicker = null;
    activePeriod = DEFAULT_PERIOD;
    flowExpanded = false;
  }

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

  function fmtLots(v) {
    if (
      v === null ||
      v === undefined ||
      Number.isNaN(Number(v))
    ) {
      return "—";
    }

    const n =
      Math.round(Number(v));

    return (
      (n > 0 ? "+" : "") +
      n.toLocaleString("zh-TW") +
      " 張"
    );
  }

  function valueClass(v) {
    const n = Number(v);

    if (n > 0) return "up";
    if (n < 0) return "down";

    return "";
  }

  function latestValue(arr) {
    const xs =
      (arr || []).filter(
        x =>
          x !== null &&
          x !== undefined &&
          !Number.isNaN(Number(x))
      );

    if (!xs.length) {
      return null;
    }

    return Number(
      xs[xs.length - 1]
    );
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

    if (Array.isArray(arr)) {
      return arr;
    }

    if (
      period === 5 &&
      Array.isArray(obj?.returns)
    ) {
      return obj.returns;
    }

    return [];
  }

  function getPeriodLabels(period) {
    const map =
      stockDetailData
        ?.date_labels_by_period ||
      {};

    const arr =
      map[String(period)] ||
      map[period];

    if (Array.isArray(arr)) {
      return arr;
    }

    if (period === 5) {
      return (
        stockDetailData
          ?.date_labels ||
        []
      );
    }

    return [];
  }

  function renderActiveStockDetail() {
    if (
      !stockDetailData ||
      !activeTicker
    ) {
      return;
    }

    const overlay =
      ensureStockDetailModal();

    const stock =
      stockDetailData
        .stocks?.[activeTicker];

    const sector =
      stockDetailData
        .sectors?.[activeSector];

    const bench =
      stockDetailData.benchmark || {};

    const nameBox =
      overlay.querySelector(
        "#stockDetailName"
      );

    const metaBox =
      overlay.querySelector(
        "#stockDetailMeta"
      );

    const body =
      overlay.querySelector(
        "#stockDetailBody"
      );

    if (!stock) {
      nameBox.textContent =
        activeTicker;

      metaBox.textContent =
        activeSector;

      body.innerHTML = `
        <div class="stock-detail-empty">
          這檔目前沒有個股資料
        </div>
      `;

      return;
    }

    nameBox.textContent =
      `${
        stock.name ||
        activeTicker
      } ${activeTicker}`;

    metaBox.textContent =
      `${
        activeSector || "—"
      }｜截至 ${
        stockDetailData
          .as_of_date ||
        "—"
      }`;

    if (activeTab === "flow") {
      body.innerHTML =
        renderFlowPanel(stock);

      bindFlowPull(body);
      return;
    }

    body.innerHTML =
      renderTrendPanel(
        stock,
        sector,
        bench
      );
  }

  function renderTrendPanel(
    stock,
    sector,
    bench
  ) {
    const dates =
      getPeriodLabels(
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
        ? stockLast - sectorLast
        : null;

    const vsIndex =
      stockLast !== null &&
      indexLast !== null
        ? stockLast - indexLast
        : null;

    return `
      <div class="stock-detail-section-title">
        <strong>
          近${activePeriod}日相對走勢
        </strong>

        <small>
          個股 vs 同族群 vs 上市加權指數
        </small>
      </div>

      <div class="stock-detail-metrics">
        <div
          class="stock-detail-metric stock"
        >
          <small>
            ${
              stock.name ||
              activeTicker
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
              activeSector ||
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

      <div class="stock-detail-note">
        近${activePeriod}個已完成交易日；以前一交易日收盤為0%基準
        ${
          vsSector !== null
            ? `｜相對族群 ${
                fmtPct(
                  vsSector
                )
              }`
            : ""
        }
        ${
          vsIndex !== null
            ? `｜相對大盤 ${
                fmtPct(
                  vsIndex
                )
              }`
            : ""
        }
      </div>

      <div class="stock-detail-chart">
        ${
          lineChartSvg(
            dates,
            [
              {
                values: sr,
                color:
                  "#dc2626"
              },
              {
                values: gr,
                color:
                  "#2563eb"
              },
              {
                values: ir,
                color:
                  "#64748b"
              }
            ]
          )
        }

        <div class="stock-detail-legend">
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
              activeSector ||
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
      Math.min(0, ...values);

    let max =
      Math.max(0, ...values);

    if (
      Math.abs(max - min) <
      0.5
    ) {
      max += 1;
      min -= 1;
    }

    const span =
      max - min;

    max += span * 0.14;
    min -= span * 0.14;

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
      ticks.map(v => `
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
      `).join("");

    const paths =
      series.map(s => {
        let d = "";
        let drawing = false;

        (s.values || [])
          .forEach(
            (v, i) => {
              if (
                v === null ||
                v === undefined ||
                Number.isNaN(
                  Number(v)
                )
              ) {
                drawing = false;
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
      }).join("");

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
      labels.map(
        (label, i) => {
          if (
            i !== 0 &&
            i !==
              labels.length - 1 &&
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
              ${label}
            </text>
          `;
        }
      ).join("");

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

  function flowRowsForPeriod(
    stock
  ) {
    const rows =
      Array.isArray(
        stock?.institutional
      )
        ? stock.institutional
        : [];

    return rows.slice(
      -activePeriod
    );
  }

  function renderFlowPanel(
    stock
  ) {
    const rows =
      flowRowsForPeriod(stock);

    if (!rows.length) {
      return `
        <div
          class="stock-detail-empty"
        >
          目前沒有近${activePeriod}日法人籌碼資料
        </div>
      `;
    }

    const total =
      rows.reduce(
        (sum, row) =>
          sum +
          Number(
            row.total_lots ||
            0
          ),
        0
      );

    const newestFirst =
      [...rows].reverse();

    return `
      <div
        class="stock-detail-section-title"
      >
        <strong>
          近${activePeriod}日法人籌碼
        </strong>

        <small>
          長條圖看合計｜上拉看法人拆分
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
            valueClass(total)
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
                rows
              )
            }
          </div>
        </div>

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
              ? "收回籌碼明細"
              : "上拉展開籌碼明細"
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
                ? "收回圖表"
                : "上拉看明細"
            }
          </span>
        </button>

        <div
          class="stock-flow-table-wrap"
        >
          <div
            class="stock-flow-table-scroll"
          >
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
                              row.date_label ||
                              "—"
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
          </div>
        </div>
      </div>
    `;
  }

  function bindFlowPull(body) {
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

    const applyState = () => {
      stage.classList.toggle(
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
          ? "收回籌碼明細"
          : "上拉展開籌碼明細"
      );

      const label =
        pull.querySelector(
          ".stock-flow-pull-label"
        );

      if (label) {
        label.textContent =
          flowExpanded
            ? "收回圖表"
            : "上拉看明細";
      }
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

        flowTouchStartY = null;
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
      activePeriod >= 20
        ? 6
        : activePeriod >= 10
          ? 5
          : activePeriod;

    const labelStep =
      Math.max(
        1,
        Math.ceil(
          rows.length /
          maxLabels
        )
      );

    const bars =
      rows.map(
        (row, i) => {
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
                      row.date_label ||
                      ""
                    }
                  </text>
                `
                : ""
            }
          `;
        }
      ).join("");

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

        if (!row) return;

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

        if (!row) return;

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
            clearInterval(wait);
          }

          if (
            tries > 30
          ) {
            clearInterval(wait);
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
