/* =========================================================
   Heatmap 近5日族群強勢股標記｜效能優化版
   2026-10-02

   重要：
   1. 不再自己每 60 秒抓 heatmap.json
   2. 熱力圖刷新統一交給 refresh_controller.js
   3. stock_detail.json 使用 5 分鐘記憶體快取
   4. DOM 變動只 debounce，不立即重抓資料
   5. 只處理目前已展開的族群
   6. 保留近五日漲幅第1／第2金色標記
   7. 保留 iPhone / Safari 回到頁面後更新標記
   ========================================================= */

(function () {
  "use strict";

  const TOP_COUNT = 2;

  /*
   * stock_detail.json 約 400KB
   *
   * 不需要每次 DOM 有變化就重新下載
   * 5 分鐘內直接使用記憶體資料
   */
  const STOCK_DETAIL_CACHE_MS =
    5 * 60 * 1000;

  /*
   * DOM 連續變化時合併處理
   */
  const APPLY_DEBOUNCE = 180;

  let stockDetailCache = null;
  let stockDetailCacheAt = 0;
  let stockDetailPromise = null;

  let applyTimer = null;
  let applying = false;

  let observer = null;

  /* =========================================================
     基本工具
  ========================================================= */

  function heatmapVisible() {
    const page =
      document.getElementById("heat");

    return !!(
      page &&
      page.classList.contains("active")
    );
  }

  function latestValidNumber(values) {
    const arr =
      Array.isArray(values)
        ? values
        : [];

    for (
      let i = arr.length - 1;
      i >= 0;
      i -= 1
    ) {
      const value =
        Number(arr[i]);

      if (
        Number.isFinite(value)
      ) {
        return value;
      }
    }

    return null;
  }

  function tickerFromRow(row) {
    return (
      row
        ?.querySelector(".t")
        ?.textContent
        ?.trim() ||
      ""
    );
  }

  function sectorFromDetail(detail) {
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
        prev.dataset.sec ||
        ""
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
          node =>
            node.nodeType ===
            Node.TEXT_NODE
        )
        .map(
          node =>
            node.textContent
        )
        .join(" ")
        .trim()
    );
  }

  /* =========================================================
     stock_detail.json 共用快取

     force = true
     才會真的重新下載
  ========================================================= */

  async function getStockDetail(
    force = false
  ) {
    const now =
      Date.now();

    if (
      !force &&
      stockDetailCache &&
      now - stockDetailCacheAt <
        STOCK_DETAIL_CACHE_MS
    ) {
      return stockDetailCache;
    }

    /*
     * 如果已經有人正在下載
     * 直接共用同一個 Promise
     *
     * 避免：
     * MutationObserver
     * + page change
     * + refresh event
     *
     * 同時打三次 stock_detail.json
     */
    if (stockDetailPromise) {
      return stockDetailPromise;
    }

    stockDetailPromise =
      fetch(
        "./data/stock_detail.json?v=" +
          now,
        {
          cache: "no-store"
        }
      )
        .then(response => {
          if (!response.ok) {
            throw new Error(
              "stock_detail.json HTTP " +
                response.status
            );
          }

          return response.json();
        })
        .then(data => {
          stockDetailCache =
            data;

          stockDetailCacheAt =
            Date.now();

          return data;
        })
        .finally(() => {
          stockDetailPromise =
            null;
        });

    return stockDetailPromise;
  }

  /* =========================================================
     樣式
  ========================================================= */

  function injectStyles() {
    if (
      document.getElementById(
        "heatStrengthStyle"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "heatStrengthStyle";

    style.textContent = `

      /* =========================
         上方說明
         ========================= */

      .heat-strength-note{
        display:flex;
        align-items:center;
        gap:8px;

        width:max-content;
        max-width:100%;

        margin:0 0 12px;
        padding:7px 10px;

        border:1px solid
          rgba(202,138,4,.26);

        border-radius:10px;

        background:
          rgba(254,243,199,.56);

        color:#765314;

        font-size:10px;
        font-weight:800;
        line-height:1.35;
      }

      .heat-strength-swatch{
        width:11px;
        height:11px;

        flex:0 0 11px;

        border:1px solid
          rgba(202,138,4,.42);

        border-radius:4px;

        background:
          linear-gradient(
            180deg,
            rgba(253,230,138,.92),
            rgba(254,243,199,.92)
          );
      }


      /* =========================
         Top 2 金色背景
         ========================= */

      #heatGrid
      .heat-stock.heat-stock-top2{
        position:relative;

        border-color:
          rgba(202,138,4,.42)
          !important;

        background:
          linear-gradient(
            135deg,
            rgba(254,243,199,.88),
            rgba(253,230,138,.58)
          )
          !important;

        box-shadow:
          inset 0 0 0 1px
            rgba(245,158,11,.08),
          0 4px 12px
            rgba(161,98,7,.08);
      }


      /* =========================
         排名標籤
         ========================= */

      #heatGrid
      .heat-strength-rank{
        display:inline-flex;
        align-items:center;
        justify-content:center;

        flex:0 0 auto;

        margin-left:6px;
        padding:3px 6px;

        border:1px solid
          rgba(180,83,9,.24);

        border-radius:999px;

        background:
          rgba(255,251,235,.92);

        color:#92400e;

        font-size:9px;
        font-weight:900;
        line-height:1;

        white-space:nowrap;
        vertical-align:middle;
      }


      /* =========================
         深色模式
         ========================= */

      html[data-theme="dark"]
      .heat-strength-note{
        border-color:
          rgba(234,179,8,.30);

        background:
          rgba(113,63,18,.26);

        color:#fde68a;
      }

      html[data-theme="dark"]
      .heat-strength-swatch{
        border-color:
          rgba(250,204,21,.42);

        background:
          linear-gradient(
            180deg,
            rgba(161,98,7,.72),
            rgba(113,63,18,.72)
          );
      }

      html[data-theme="dark"]
      #heatGrid
      .heat-stock.heat-stock-top2{
        border-color:
          rgba(250,204,21,.42)
          !important;

        background:
          linear-gradient(
            135deg,
            rgba(113,63,18,.62),
            rgba(146,64,14,.44)
          )
          !important;

        box-shadow:
          inset 0 0 0 1px
            rgba(250,204,21,.08),
          0 4px 14px
            rgba(0,0,0,.12);
      }

      html[data-theme="dark"]
      #heatGrid
      .heat-strength-rank{
        border-color:
          rgba(250,204,21,.28);

        background:
          rgba(66,32,6,.88);

        color:#fde68a;
      }


      /* =========================
         手機
         ========================= */

      @media(max-width:720px){

        .heat-strength-note{
          margin-bottom:10px;
          padding:7px 9px;
          font-size:9px;
        }

        #heatGrid
        .heat-strength-rank{
          margin-left:4px;
          padding:3px 5px;
          font-size:8px;
        }
      }

      @media(max-width:390px){

        #heatGrid
        .heat-strength-rank{
          padding:2px 4px;
          font-size:7px;
        }
      }
    `;

    document.head.appendChild(
      style
    );
  }

  /* =========================================================
     金色說明
  ========================================================= */

  function ensureStrengthNote() {
    const heatGrid =
      document.getElementById(
        "heatGrid"
      );

    if (!heatGrid) {
      return;
    }

    if (
      document.getElementById(
        "heatStrengthNote"
      )
    ) {
      return;
    }

    const note =
      document.createElement(
        "div"
      );

    note.id =
      "heatStrengthNote";

    note.className =
      "heat-strength-note";

    note.innerHTML = `
      <span
        class="heat-strength-swatch"
        aria-hidden="true"
      ></span>

      <span>
        金色＝各族群近5日累積漲幅前2強
      </span>
    `;

    heatGrid.parentNode.insertBefore(
      note,
      heatGrid
    );
  }

  /* =========================================================
     清除舊標記

     只移除我們自己加的東西
     不碰原熱力圖 DOM
  ========================================================= */

  function clearStrengthMarks() {
    document
      .querySelectorAll(
        "#heatGrid .heat-stock-top2"
      )
      .forEach(row => {
        row.classList.remove(
          "heat-stock-top2"
        );

        row.removeAttribute(
          "data-5d-rank"
        );

        row.removeAttribute(
          "data-5d-return"
        );
      });

    document
      .querySelectorAll(
        "#heatGrid .heat-strength-rank"
      )
      .forEach(label => {
        label.remove();
      });
  }

  /* =========================================================
     加排名標籤
  ========================================================= */

  function addRankLabel(
    row,
    rank
  ) {
    /*
     * 避免重複插入
     */
    if (
      row.querySelector(
        ".heat-strength-rank"
      )
    ) {
      return;
    }

    const ticker =
      row.querySelector(".t");

    if (!ticker) {
      return;
    }

    const label =
      document.createElement(
        "span"
      );

    label.className =
      "heat-strength-rank";

    label.textContent =
      rank === 1
        ? "近五日漲幅第1"
        : "近五日漲幅第2";

    /*
     * 放在股票代號後面
     * 不會蓋到右側漲幅 %
     */
    ticker.insertAdjacentElement(
      "afterend",
      label
    );
  }

  /* =========================================================
     單一族群排名
  ========================================================= */

  function markTopStocks(
    detail,
    stockDetailData
  ) {
    const sectorName =
      sectorFromDetail(detail);

    if (!sectorName) {
      return;
    }

    const rows = [
      ...detail.querySelectorAll(
        ".heat-stock"
      )
    ];

    if (!rows.length) {
      return;
    }

    const ranked =
      rows
        .map(row => {
          const ticker =
            tickerFromRow(row);

          const stock =
            stockDetailData
              ?.stocks?.[ticker];

          const return5d =
            latestValidNumber(
              stock?.returns
            );

          return {
            row,
            ticker,
            return5d
          };
        })
        .filter(
          item =>
            item.ticker &&
            item.return5d !== null
        )
        .sort(
          (a, b) =>
            b.return5d -
            a.return5d
        );

    ranked
      .slice(
        0,
        TOP_COUNT
      )
      .forEach(
        (item, index) => {
          const rank =
            index + 1;

          item.row.classList.add(
            "heat-stock-top2"
          );

          item.row.setAttribute(
            "data-5d-rank",
            String(rank)
          );

          item.row.setAttribute(
            "data-5d-return",
            String(
              item.return5d
            )
          );

          addRankLabel(
            item.row,
            rank
          );
        }
      );
  }

  /* =========================================================
     套用排名

     forceData = true
     只有確認後台資料已更新時才重新下載
  ========================================================= */

  async function applyStrengthMarks(
    forceData = false
  ) {
    if (applying) {
      return;
    }

    if (!heatmapVisible()) {
      return;
    }

    const heatGrid =
      document.getElementById(
        "heatGrid"
      );

    if (!heatGrid) {
      return;
    }

    /*
     * 沒有展開任何族群
     * 根本不需要下載 stock_detail.json
     */
    const details = [
      ...heatGrid.querySelectorAll(
        ".heat-detail"
      )
    ];

    if (!details.length) {
      clearStrengthMarks();
      return;
    }

    applying = true;

    try {
      injectStyles();
      ensureStrengthNote();

      const data =
        await getStockDetail(
          forceData
        );

      clearStrengthMarks();

      details.forEach(
        detail => {
          markTopStocks(
            detail,
            data
          );
        }
      );

    } catch (error) {
      console.error(
        "[Heat Strength]",
        error
      );

    } finally {
      applying = false;
    }
  }

  /* =========================================================
     Debounce

     DOM 一次可能變幾十次
     只執行最後一次
  ========================================================= */

  function scheduleApply(
    delay = APPLY_DEBOUNCE,
    forceData = false
  ) {
    if (applyTimer) {
      clearTimeout(
        applyTimer
      );
    }

    applyTimer =
      setTimeout(
        () => {
          applyTimer = null;

          applyStrengthMarks(
            forceData
          );
        },
        delay
      );
  }

  /* =========================================================
     監聽 Heatmap DOM

     只監聽 heatGrid 第一層
     不再 subtree:true

     這可以大幅降低 MutationObserver 次數
  ========================================================= */

  function observeHeatGrid() {
    const heatGrid =
      document.getElementById(
        "heatGrid"
      );

    if (!heatGrid) {
      return;
    }

    if (observer) {
      observer.disconnect();
    }

    observer =
      new MutationObserver(
        mutations => {
          const meaningful =
            mutations.some(
              mutation =>
                mutation.type ===
                "childList"
            );

          if (!meaningful) {
            return;
          }

          scheduleApply(
            APPLY_DEBOUNCE,
            false
          );
        }
      );

    observer.observe(
      heatGrid,
      {
        childList: true,

        /*
         * 不監聽整棵 subtree
         *
         * 原本加入一個金色標籤
         * MutationObserver 自己又會被觸發
         */
        subtree: false
      }
    );
  }

  /* =========================================================
     熱力圖資料真的更新

     refresh_controller / breadth module
     更新完成後會觸發相關事件

     這時才清掉 stock_detail cache
  ========================================================= */

  function bindRefreshEvents() {
    window.addEventListener(
      "heatmap:data-updated",
      () => {
        stockDetailCache = null;
        stockDetailCacheAt = 0;

        scheduleApply(
          200,
          true
        );
      }
    );

    /*
     * refresh_controller 要求熱力圖更新
     *
     * 先讓 heat() 完成 DOM 更新
     * 再補金色標記
     */
    window.addEventListener(
      "tw-market:refresh-heatmap",
      () => {
        scheduleApply(
          250,
          false
        );
      }
    );

    /*
     * 全站 refresh 完成
     */
    window.addEventListener(
      "tw-market:refreshed",
      event => {
        if (
          event?.detail?.page !==
          "heat"
        ) {
          return;
        }

        scheduleApply(
          250,
          false
        );
      }
    );
  }

  /* =========================================================
     iPhone / Safari

     回到網站時：
     不自己重新抓 heatmap.json

     refresh_controller 已經會處理資料更新

     這裡只補畫金色標記
  ========================================================= */

  function bindResumeEvents() {
    document.addEventListener(
      "visibilitychange",
      () => {
        if (
          document.hidden
        ) {
          return;
        }

        if (
          !heatmapVisible()
        ) {
          return;
        }

        scheduleApply(
          300,
          false
        );
      }
    );

    window.addEventListener(
      "pageshow",
      event => {
        if (
          !event.persisted
        ) {
          return;
        }

        if (
          !heatmapVisible()
        ) {
          return;
        }

        scheduleApply(
          300,
          false
        );
      }
    );

    /*
     * 不監聽 focus
     *
     * iPhone Safari 常常會：
     *
     * visibilitychange
     * + pageshow
     * + focus
     *
     * 一次回網站觸發三輪
     */
  }

  /* =========================================================
     點擊族群

     展開後才需要排名
  ========================================================= */

  function bindSectorClicks() {
    document.addEventListener(
      "click",
      event => {
        const button =
          event.target.closest(
            "#heatGrid [data-sec]"
          );

        if (!button) {
          return;
        }

        scheduleApply(
          220,
          false
        );
      },
      {
        passive: true
      }
    );
  }

  /* =========================================================
     對外 API
  ========================================================= */

  window.refreshHeatStrength =
    function (
      forceData = false
    ) {
      return applyStrengthMarks(
        forceData
      );
    };

  window.clearHeatStrengthCache =
    function () {
      stockDetailCache = null;
      stockDetailCacheAt = 0;
    };

  /* =========================================================
     初始化
  ========================================================= */

  function init() {
    injectStyles();

    ensureStrengthNote();

    observeHeatGrid();

    bindRefreshEvents();

    bindResumeEvents();

    bindSectorClicks();

    /*
     * 第一次不用立刻抓 stock_detail
     *
     * 只有使用者真的展開族群
     * 才會下載
     */
    if (heatmapVisible()) {
      scheduleApply(
        300,
        false
      );
    }

    console.log(
      "[Heat Strength] optimized module ready"
    );
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      init,
      {
        once: true
      }
    );

  } else {
    init();
  }

})();
