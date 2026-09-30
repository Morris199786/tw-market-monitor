/* =========================================================
   市場熱力圖：族群下拉 + PCB 細分 + 個股近5日資訊
   2026-09-30
   ========================================================= */

(function () {
  const $h = s => document.querySelector(s);

  let sectorConfig = [];
  let selectedSector = "all";
  let selectedSubgroup = "all";
  let applying = false;

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

      sectorConfig =
        d.sectors || [];

      return sectorConfig;
    } catch (e) {
      console.error(
        "sector selector load failed",
        e
      );

      sectorConfig = [];

      return [];
    }
  }

  function findSector(name) {
    return sectorConfig.find(
      x => x.name === name
    );
  }

  function directHeatButtons() {
    const grid =
      $h("#heatGrid");

    if (!grid) {
      return [];
    }

    return [
      ...grid.children
    ].filter(
      el =>
        el.matches?.(
          "button.heat[data-sec]"
        )
    );
  }

  function updateStaticLabels() {
    const count =
      sectorConfig.length;

    const heatHero =
      $h("#heat .hero p");

    if (heatHero) {
      heatHero.textContent =
        `${count} 個自訂族群｜市值加權｜紅漲綠跌｜可直接下拉選族群`;
    }

    const revenueHero =
      $h(
        "#monthlyRevenue .hero p"
      );

    if (revenueHero) {
      revenueHero.textContent =
        `${count} 個科技族群｜最新已公布月份｜營收、MoM、YoY`;
    }

    document
      .querySelectorAll(
        ".feature-card"
      )
      .forEach(card => {
        const title =
          card.querySelector(
            ".feature-copy b"
          )?.textContent
            ?.trim();

        const small =
          card.querySelector(
            ".feature-copy small"
          );

        if (!small) {
          return;
        }

        if (
          title ===
          "市場熱力圖"
        ) {
          small.textContent =
            `${count}族群・5分鐘`;
        }

        if (
          title ===
          "月營收公布"
        ) {
          small.textContent =
            `${count}族群`;
        }
      });
  }

  function ensureControls() {
    const grid =
      $h("#heatGrid");

    if (
      !grid ||
      $h("#heatSectorControl")
    ) {
      return;
    }

    const wrap =
      document.createElement(
        "div"
      );

    wrap.id =
      "heatSectorControl";

    wrap.className =
      "heat-sector-control";

    wrap.innerHTML = `
      <div class="heat-sector-copy">
        <span class="heat-sector-kicker">
          SECTOR FILTER
        </span>

        <strong>
          選擇想看的族群
        </strong>

        <small id="heatSectorMeta">
          ${sectorConfig.length} 個自訂族群
        </small>
      </div>

      <div class="heat-sector-actions">
        <label
          class="heat-sector-select-wrap"
          for="heatSectorSelect"
        >
          <span>
            族群
          </span>

          <select
            id="heatSectorSelect"
            aria-label="選擇熱力圖族群"
          >
            <option value="all">
              全部族群
            </option>

            ${sectorConfig
              .map(
                sec => `
                  <option
                    value="${sec.name}"
                  >
                    ${sec.name}
                  </option>
                `
              )
              .join("")}
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

    grid.parentNode.insertBefore(
      wrap,
      grid
    );

    $h("#heatSectorSelect")
      ?.addEventListener(
        "change",
        e => {
          selectedSector =
            e.target.value;

          selectedSubgroup =
            "all";

          rerenderSelected();
        }
      );

    $h("#heatSectorReset")
      ?.addEventListener(
        "click",
        () => {
          selectedSector =
            "all";

          selectedSubgroup =
            "all";

          const sel =
            $h(
              "#heatSectorSelect"
            );

          if (sel) {
            sel.value =
              "all";
          }

          rerenderSelected();
        }
      );
  }

  function rerenderSelected() {
    try {
      if (
        typeof st !==
        "undefined"
      ) {
        st.openSector =
          selectedSector ===
          "all"
            ? null
            : selectedSector;
      }

      if (
        typeof heat ===
        "function"
      ) {
        Promise
          .resolve(
            heat()
          )
          .finally(
            () => {
              setTimeout(
                () => {
                  applySectorFilter();
                  injectSubgroupControl();
                  decorateHeatStocks();
                },
                20
              );
            }
          );

        return;
      }
    } catch (e) {
      console.warn(
        "heat rerender fallback",
        e
      );
    }

    applySectorFilter();
    injectSubgroupControl();
    decorateHeatStocks();
  }

  function applySectorFilter() {
    if (applying) {
      return;
    }

    applying = true;

    directHeatButtons()
      .forEach(
        btn => {
          btn.hidden =
            selectedSector !==
              "all" &&
            btn.dataset.sec !==
              selectedSector;
        }
      );

    const meta =
      $h(
        "#heatSectorMeta"
      );

    if (meta) {
      meta.textContent =
        selectedSector ===
        "all"
          ? `${sectorConfig.length} 個自訂族群`
          : `目前：${selectedSector}`;
    }

    const reset =
      $h(
        "#heatSectorReset"
      );

    if (reset) {
      reset.classList.toggle(
        "active",
        selectedSector !==
          "all"
      );
    }

    applying = false;
  }

  function injectSubgroupControl() {
    if (
      selectedSector ===
      "all"
    ) {
      return;
    }

    const detail =
      $h(
        "#heatGrid .heat-detail"
      );

    if (!detail) {
      return;
    }

    const sector =
      findSector(
        selectedSector
      );

    const groups =
      sector?.subgroups ||
      [];

    if (!groups.length) {
      return;
    }

    if (
      detail.querySelector(
        ".heat-subgroup-control"
      )
    ) {
      filterSubgroupStocks();

      return;
    }

    const control =
      document.createElement(
        "div"
      );

    control.className =
      "heat-subgroup-control";

    control.innerHTML = `
      <div>
        <span
          class="heat-subgroup-kicker"
        >
          SUB-SECTOR
        </span>

        <b>
          ${sector.name}
        </b>
      </div>

      <label
        class="heat-subgroup-select-wrap"
      >
        <span>
          細分類
        </span>

        <select
          id="heatSubgroupSelect"
          aria-label="選擇細分產業"
        >
          <option value="all">
            全部成分
          </option>

          ${groups
            .map(
              g => `
                <option
                  value="${g.name}"
                >
                  ${g.name}
                </option>
              `
            )
            .join("")}
        </select>
      </label>
    `;

    const list =
      detail.querySelector(
        ".heat-stock-list"
      );

    if (!list) {
      return;
    }

    detail.insertBefore(
      control,
      list
    );

    const select =
      control.querySelector(
        "#heatSubgroupSelect"
      );

    if (select) {
      select.value =
        selectedSubgroup;

      select.addEventListener(
        "change",
        e => {
          selectedSubgroup =
            e.target.value;

          filterSubgroupStocks();
        }
      );
    }

    filterSubgroupStocks();
  }

  function filterSubgroupStocks() {
    const detail =
      $h(
        "#heatGrid .heat-detail"
      );

    const sector =
      findSector(
        selectedSector
      );

    if (
      !detail ||
      !sector
    ) {
      return;
    }

    const group =
      (
        sector.subgroups ||
        []
      ).find(
        g =>
          g.name ===
          selectedSubgroup
      );

    const allowed =
      group
        ? new Set(
            (
              group.tickers ||
              []
            ).map(
              String
            )
          )
        : null;

    const rows = [
      ...detail.querySelectorAll(
        ".heat-stock"
      )
    ];

    let visible = 0;

    rows.forEach(
      row => {
        const ticker =
          row.querySelector(
            ".t"
          )?.textContent
            ?.trim();

        const show =
          !allowed ||
          allowed.has(
            String(
              ticker
            )
          );

        row.hidden =
          !show;

        if (show) {
          visible += 1;
        }
      }
    );

    const meta =
      detail.querySelector(
        ".heat-detail-head > span"
      );

    if (meta) {
      meta.textContent =
        selectedSubgroup ===
          "all"
          ? `${rows.length} 檔｜依漲跌幅排序`
          : `${selectedSubgroup}｜${visible} 檔｜依漲跌幅排序`;
    }
  }

  function observeHeatmap() {
    const grid =
      $h(
        "#heatGrid"
      );

    if (!grid) {
      return;
    }

    const observer =
      new MutationObserver(
        () => {
          if (applying) {
            return;
          }

          applySectorFilter();

          setTimeout(
            () => {
              injectSubgroupControl();
              decorateHeatStocks();
            },
            0
          );
        }
      );

    observer.observe(
      grid,
      {
        childList: true,
        subtree: true
      }
    );
  }

  /* =========================================================
     個股近5日資訊
     ========================================================= */

  let stockDetailData = null;
  let stockDetailPromise = null;
  let activeTicker = null;
  let activeSector = null;
  let activeTab = "trend";

  function injectStockDetailStyles() {
    if (
      document.getElementById(
        "stockDetailStyle"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "stockDetailStyle";

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
        max-height:min(88vh,900px);
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
        z-index:5;
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

      .stock-detail-tabs{
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:8px;
        padding:14px 20px 0
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
        background:linear-gradient(180deg,var(--soft),color-mix(in srgb,var(--soft) 72%,var(--card)));
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

      .stock-flow-table-wrap{
        margin-top:14px;
        overflow:hidden;
        border:1px solid var(--line);
        border-radius:16px;
        background:var(--card)
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
        background:color-mix(in srgb,var(--soft) 55%,transparent)
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
          max-height:91vh;
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

        .stock-detail-tabs{
          padding:11px 14px 0;
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

    document.head.appendChild(
      style
    );
  }

  function ensureStockDetailModal() {
    let overlay =
      document.getElementById(
        "stockDetailOverlay"
      );

    if (overlay) {
      return overlay;
    }

    overlay =
      document.createElement(
        "div"
      );

    overlay.id =
      "stockDetailOverlay";

    overlay.className =
      "stock-detail-overlay";

    overlay.innerHTML = `
      <div
        class="stock-detail-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="個股近五日資訊"
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

        <div class="stock-detail-tabs">
          <button
            class="stock-detail-tab active"
            type="button"
            data-stock-detail-tab="trend"
          >
            近5日走勢
          </button>

          <button
            class="stock-detail-tab"
            type="button"
            data-stock-detail-tab="flow"
          >
            近5日籌碼
          </button>
        </div>

        <div
          id="stockDetailBody"
          class="stock-detail-body"
        ></div>
      </div>
    `;

    document.body.appendChild(
      overlay
    );

    overlay
      .querySelector(
        "#stockDetailClose"
      )
      ?.addEventListener(
        "click",
        closeStockDetail
      );

    overlay.addEventListener(
      "click",
      e => {
        if (
          e.target === overlay
        ) {
          closeStockDetail();
        }
      }
    );

    overlay
      .querySelectorAll(
        "[data-stock-detail-tab]"
      )
      .forEach(btn => {
        btn.addEventListener(
          "click",
          () => {
            activeTab =
              btn.dataset
                .stockDetailTab;

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
          }
        );
      });

    document.addEventListener(
      "keydown",
      e => {
        if (
          e.key === "Escape"
          && overlay.classList
            .contains("open")
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

    stockDetailPromise =
      fetch(
        "./data/stock_detail.json?v="
        + Date.now(),
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
          stockDetailPromise =
            null;
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
          "開啟個股近五日資訊"
        );
      });
  }

  function sectorFromRow(row) {
    const detail =
      row.closest(
        ".heat-detail"
      );

    if (!detail) {
      return "";
    }

    const prev =
      detail.previousElementSibling;

    if (
      prev?.matches?.(
        "button.heat[data-sec]"
      )
    ) {
      return (
        prev.dataset.sec
        || ""
      );
    }

    const head =
      detail.querySelector(
        ".heat-detail-head b"
      );

    if (!head) {
      return "";
    }

    return (
      [...head.childNodes]
        .filter(
          n =>
            n.nodeType ===
            Node.TEXT_NODE
        )
        .map(
          n =>
            n.textContent
        )
        .join(" ")
        .trim()
    );
  }

  function tickerFromRow(row) {
    return (
      row.querySelector(
        ".t"
      )?.textContent
        ?.trim()
      || ""
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
      String(sector || "");

    activeTab =
      "trend";

    const overlay =
      ensureStockDetailModal();

    overlay
      .querySelectorAll(
        "[data-stock-detail-tab]"
      )
      .forEach(btn => {
        btn.classList.toggle(
          "active",
          btn.dataset
            .stockDetailTab
          === "trend"
        );
      });

    overlay.classList.add(
      "open"
    );

    document.body.style
      .overflow = "hidden";

    const body =
      overlay.querySelector(
        "#stockDetailBody"
      );

    body.innerHTML = `
      <div
        class="stock-detail-loading"
      >
        載入近5日資料…
      </div>
    `;

    try {
      await loadStockDetailData();

      renderActiveStockDetail();
    } catch (e) {
      body.innerHTML = `
        <div
          class="stock-detail-empty"
        >
          尚未產生個股近5日資料<br>
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

    overlay?.classList
      .remove("open");

    document.body.style
      .overflow = "";

    activeTicker = null;
  }

  function fmtPct(v) {
    if (
      v === null
      || v === undefined
      || Number.isNaN(
        Number(v)
      )
    ) {
      return "—";
    }

    const n =
      Number(v);

    return (
      (n > 0 ? "+" : "")
      + n.toFixed(2)
      + "%"
    );
  }

  function fmtLots(v) {
    if (
      v === null
      || v === undefined
      || Number.isNaN(
        Number(v)
      )
    ) {
      return "—";
    }

    const n =
      Math.round(
        Number(v)
      );

    return (
      (n > 0 ? "+" : "")
      + n.toLocaleString(
          "zh-TW"
        )
      + " 張"
    );
  }

  function valueClass(v) {
    const n =
      Number(v);

    if (n > 0) {
      return "up";
    }

    if (n < 0) {
      return "down";
    }

    return "";
  }

  function latestValue(arr) {
    const xs =
      (arr || [])
        .filter(
          x =>
            x !== null
            && x !== undefined
            && !Number.isNaN(
              Number(x)
            )
        );

    if (!xs.length) {
      return null;
    }

    return Number(
      xs[xs.length - 1]
    );
  }

  function renderActiveStockDetail() {
    if (
      !stockDetailData
      || !activeTicker
    ) {
      return;
    }

    const overlay =
      ensureStockDetailModal();

    const stock =
      stockDetailData
        .stocks?.[
          activeTicker
        ];

    const sector =
      stockDetailData
        .sectors?.[
          activeSector
        ];

    const bench =
      stockDetailData
        .benchmark || {};

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
        <div
          class="stock-detail-empty"
        >
          這檔目前沒有近5日資料
        </div>
      `;

      return;
    }

    nameBox.textContent =
      `${stock.name || activeTicker} ${activeTicker}`;

    metaBox.textContent =
      `${activeSector || "—"}｜截至 ${
        stockDetailData
          .as_of_date || "—"
      }`;

    if (
      activeTab ===
      "flow"
    ) {
      body.innerHTML =
        renderFlowPanel(
          stock
        );

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
      stockDetailData
        .date_labels || [];

    const sr =
      stock.returns || [];

    const gr =
      sector?.returns || [];

    const ir =
      bench?.returns || [];

    const stockLast =
      latestValue(sr);

    const sectorLast =
      latestValue(gr);

    const indexLast =
      latestValue(ir);

    const vsSector =
      stockLast !== null
      && sectorLast !== null
        ? stockLast - sectorLast
        : null;

    const vsIndex =
      stockLast !== null
      && indexLast !== null
        ? stockLast - indexLast
        : null;

    return `
      <div
        class="stock-detail-section-title"
      >
        <strong>
          近5日相對走勢
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
            ${stock.name || activeTicker}
          </small>

          <strong
            class="${valueClass(stockLast)}"
          >
            ${fmtPct(stockLast)}
          </strong>
        </div>

        <div
          class="stock-detail-metric sector"
        >
          <small>
            ${activeSector || "同族群"}
          </small>

          <strong
            class="${valueClass(sectorLast)}"
          >
            ${fmtPct(sectorLast)}
          </strong>
        </div>

        <div
          class="stock-detail-metric index"
        >
          <small>
            ${bench.name || "上市加權指數"}
          </small>

          <strong
            class="${valueClass(indexLast)}"
          >
            ${fmtPct(indexLast)}
          </strong>
        </div>
      </div>

      <div
        class="stock-detail-note"
      >
        ${stockDetailData.note || "近5個已完成交易日"}
        ${vsSector !== null ? `｜相對族群 ${fmtPct(vsSector)}` : ""}
        ${vsIndex !== null ? `｜相對大盤 ${fmtPct(vsIndex)}` : ""}
      </div>

      <div
        class="stock-detail-chart"
      >
        ${lineChartSvg(
          dates,
          [
            {
              label: stock.name || activeTicker,
              values: sr,
              color: "#dc2626"
            },
            {
              label: activeSector || "同族群",
              values: gr,
              color: "#2563eb"
            },
            {
              label: bench.name || "上市加權指數",
              values: ir,
              color: "#64748b"
            }
          ]
        )}

        <div
          class="stock-detail-legend"
        >
          <span>
            <i class="stock-detail-dot stock"></i>
            個股
          </span>

          <span>
            <i class="stock-detail-dot sector"></i>
            ${activeSector || "同族群"}
          </span>

          <span>
            <i class="stock-detail-dot index"></i>
            ${bench.name || "上市加權指數"}
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
    const height = 310;

    const pad = {
      left: 52,
      right: 22,
      top: 22,
      bottom: 44
    };

    const values =
      series
        .flatMap(s => s.values || [])
        .filter(
          v =>
            v !== null
            && v !== undefined
            && !Number.isNaN(Number(v))
        )
        .map(Number);

    if (!values.length) {
      return `
        <div class="stock-detail-empty">
          暫無完整走勢資料
        </div>
      `;
    }

    let min = Math.min(0, ...values);
    let max = Math.max(0, ...values);

    if (Math.abs(max - min) < 0.5) {
      max += 1;
      min -= 1;
    }

    const span = max - min;
    const extra = span * 0.14;

    max += extra;
    min -= extra;

    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;

    const xAt = i =>
      pad.left + (
        labels.length <= 1
          ? plotW / 2
          : i / (labels.length - 1) * plotW
      );

    const yAt = v =>
      pad.top
      + ((max - Number(v)) / (max - min)) * plotH;

    const ticks = [];

    for (let i = 0; i < 5; i += 1) {
      ticks.push(max - (max - min) * i / 4);
    }

    const grids =
      ticks
        .map(
          v => `
            <line
              x1="${pad.left}"
              y1="${yAt(v)}"
              x2="${width - pad.right}"
              y2="${yAt(v)}"
              stroke="currentColor"
              opacity=".09"
              stroke-dasharray="4 5"
            />

            <text
              x="${pad.left - 9}"
              y="${yAt(v) + 4}"
              text-anchor="end"
              font-size="10"
              fill="currentColor"
              opacity=".52"
            >
              ${v.toFixed(1)}%
            </text>
          `
        )
        .join("");

    const zero =
      min <= 0 && max >= 0
        ? `
          <line
            x1="${pad.left}"
            y1="${yAt(0)}"
            x2="${width - pad.right}"
            y2="${yAt(0)}"
            stroke="currentColor"
            opacity=".28"
            stroke-width="1.2"
          />
        `
        : "";

    const paths =
      series
        .map((s, seriesIndex) => {
          const valid = [];

          (s.values || []).forEach(
            (v, i) => {
              if (
                v === null
                || v === undefined
                || Number.isNaN(Number(v))
              ) {
                return;
              }

              valid.push({
                x: xAt(i),
                y: yAt(v),
                v: Number(v)
              });
            }
          );

          if (valid.length < 2) {
            return "";
          }

          const points =
            valid.map(p => `${p.x},${p.y}`).join(" ");

          const circles =
            valid
              .map((p, i) => `
                <circle
                  cx="${p.x}"
                  cy="${p.y}"
                  r="${i === valid.length - 1 ? 4.2 : 3}"
                  fill="${s.color}"
                  stroke="var(--card)"
                  stroke-width="2"
                />
              `)
              .join("");

          return `
            <polyline
              fill="none"
              stroke="${s.color}"
              stroke-width="${seriesIndex === 0 ? 3.6 : 2.8}"
              stroke-linecap="round"
              stroke-linejoin="round"
              points="${points}"
            />
            ${circles}
          `;
        })
        .join("");

    const xlabels =
      labels
        .map(
          (label, i) => `
            <text
              x="${xAt(i)}"
              y="${height - 15}"
              text-anchor="middle"
              font-size="10"
              font-weight="650"
              fill="currentColor"
              opacity=".62"
            >
              ${label}
            </text>
          `
        )
        .join("");

    return `
      <svg
        viewBox="0 0 ${width} ${height}"
        aria-label="近5日個股、族群與上市加權指數走勢"
      >
        ${grids}
        ${zero}
        ${paths}
        ${xlabels}
      </svg>
    `;
  }


  function renderFlowPanel(
    stock
  ) {
    const rows =
      stock.institutional || [];

    const total =
      Number(
        stock
          .institutional_5d_total_lots
        || 0
      );

    return `
      <div
        class="stock-detail-section-title"
      >
        <strong>
          近5日法人籌碼
        </strong>

        <small>
          長條圖看合計｜下表看法人拆分
        </small>
      </div>

      <div
        class="stock-flow-summary"
      >
        <span>
          近5日三大法人合計
        </span>

        <strong
          class="${valueClass(
            total
          )}"
        >
          ${fmtLots(
            total
          )}
        </strong>
      </div>

      <p
        class="stock-detail-note"
      >
        長條圖僅顯示外資＋投信＋自營商「合計」買賣超｜下表拆開顯示外資、投信、自營商｜單位：張
      </p>

      <div
        class="stock-detail-chart"
      >
        ${barChartSvg(
          rows
        )}
      </div>

      <div
        class="stock-flow-table-wrap"
      >
      <table
        class="stock-flow-table"
      >
        <thead>
          <tr>
            <th>
              日期
            </th>

            <th>
              外資
            </th>

            <th>
              投信
            </th>

            <th>
              自營商
            </th>

            <th>
              合計
            </th>
          </tr>
        </thead>

        <tbody>
          ${rows
            .slice()
            .reverse()
            .map(
              row => `
                <tr>
                  <td>
                    ${row.date_label || "—"}
                  </td>

                  <td
                    class="${valueClass(
                      row.foreign_lots
                    )}"
                  >
                    ${fmtLots(
                      row.foreign_lots
                    )}
                  </td>

                  <td
                    class="${valueClass(
                      row.trust_lots
                    )}"
                  >
                    ${fmtLots(
                      row.trust_lots
                    )}
                  </td>

                  <td
                    class="${valueClass(
                      row.dealer_lots
                    )}"
                  >
                    ${fmtLots(
                      row.dealer_lots
                    )}
                  </td>

                  <td
                    class="${valueClass(
                      row.total_lots
                    )}"
                  >
                    ${fmtLots(
                      row.total_lots
                    )}
                  </td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
      </div>
    `;
  }

  function barChartSvg(rows) {
    const width = 680;
    const height = 280;

    const pad = {
      left: 48,
      right: 18,
      top: 18,
      bottom: 42
    };

    const values =
      rows.map(
        x =>
          Number(
            x.total_lots || 0
          )
      );

    const maxAbs =
      Math.max(
        1,
        ...values.map(
          Math.abs
        )
      );

    const max =
      maxAbs * 1.15;

    const min =
      -max;

    const plotW =
      width
      - pad.left
      - pad.right;

    const plotH =
      height
      - pad.top
      - pad.bottom;

    const yAt =
      v =>
        pad.top
        + (
          (
            max - v
          )
          / (
            max - min
          )
        )
        * plotH;

    const zeroY =
      yAt(0);

    const slot =
      rows.length
        ? plotW
          / rows.length
        : plotW;

    const barW =
      Math.min(
        52,
        slot * 0.52
      );

    const bars =
      rows
        .map(
          (row, i) => {
            const v =
              Number(
                row.total_lots
                || 0
              );

            const x =
              pad.left
              + slot * i
              + (
                slot - barW
              ) / 2;

            const y =
              v >= 0
                ? yAt(v)
                : zeroY;

            const h =
              Math.max(
                1.5,
                Math.abs(
                  yAt(v)
                  - zeroY
                )
              );

            const color =
              v >= 0
                ? "#dc2626"
                : "#168357";

            return `
              <rect
                x="${x}"
                y="${y}"
                width="${barW}"
                height="${h}"
                rx="4"
                fill="${color}"
              />

              <text
                x="${x + barW / 2}"
                y="${height - 15}"
                text-anchor="middle"
                font-size="10"
                fill="currentColor"
                opacity=".65"
              >
                ${row.date_label || ""}
              </text>
            `;
          }
        )
        .join("");

    return `
      <svg
        viewBox="0 0 ${width} ${height}"
        aria-label="近5日三大法人合計買賣超"
      >
        <line
          x1="${pad.left}"
          y1="${zeroY}"
          x2="${width - pad.right}"
          y2="${zeroY}"
          stroke="currentColor"
          opacity=".3"
        />

        <text
          x="${pad.left - 8}"
          y="${pad.top + 4}"
          text-anchor="end"
          font-size="10"
          fill="currentColor"
          opacity=".58"
        >
          +${maxAbs.toLocaleString("zh-TW")}
        </text>

        <text
          x="${pad.left - 8}"
          y="${height - pad.bottom}"
          text-anchor="end"
          font-size="10"
          fill="currentColor"
          opacity=".58"
        >
          -${maxAbs.toLocaleString("zh-TW")}
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
          tickerFromRow(
            row
          ),
          sectorFromRow(
            row
          )
        );
      }
    );

    document.addEventListener(
      "keydown",
      e => {
        if (
          e.key !== "Enter"
          && e.key !== " "
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
          tickerFromRow(
            row
          ),
          sectorFromRow(
            row
          )
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
