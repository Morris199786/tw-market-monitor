/* =========================================================
   Heatmap 近 5 日強勢股 Top 2 金色標記
   2026-10-06

   規則：
   1. 只有「當日」熱力圖顯示金標
   2. 金標固定代表各族群「近 5 日累積漲幅前 2 強」
   3. 5日 / 10日 / 20日模式不顯示金標
   4. 個股排序仍由 app.js 依目前選擇期間處理
   5. 不改動族群排序、不自行輪詢 heatmap.json
   ========================================================= */

(function () {
  "use strict";

  const TOP_COUNT = 2;
  const RANK_PERIOD = "5";
  const CACHE_MS = 5 * 60 * 1000;
  const APPLY_DEBOUNCE = 180;

  let detailCache = null;
  let detailCacheAt = 0;
  let detailPromise = null;

  let applyTimer = null;
  let applying = false;
  let observer = null;

  /* =========================================================
     Heatmap 是否正在顯示
     ========================================================= */

  function heatmapVisible() {
    const page =
      document.getElementById(
        "heat"
      );

    return !!(
      page &&
      page.classList.contains(
        "active"
      )
    );
  }

  /* =========================================================
     目前熱力圖期間
     ========================================================= */

  function activePeriod() {
    if (
      typeof
        window
          .getHeatmapActivePeriod ===
      "function"
    ) {
      return String(
        window
          .getHeatmapActivePeriod() ||
        "1"
      );
    }

    return "1";
  }

  /* =========================================================
     工具
     ========================================================= */

  function latestValidNumber(
    values
  ) {
    const arr =
      Array.isArray(values)
        ? values
        : [];

    for (
      let i =
        arr.length - 1;
      i >= 0;
      i -= 1
    ) {
      const n =
        Number(
          arr[i]
        );

      if (
        Number.isFinite(n)
      ) {
        return n;
      }
    }

    return null;
  }

  function tickerFromRow(
    row
  ) {
    const candidates = [
      row?.dataset?.ticker,

      row?.getAttribute?.(
        "data-ticker"
      ),

      row
        ?.querySelector?.(
          "[data-ticker]"
        )
        ?.getAttribute?.(
          "data-ticker"
        ),

      row
        ?.querySelector?.(
          ".t"
        )
        ?.textContent,

      row?.textContent
    ];

    for (
      const candidate
      of candidates
    ) {
      const match =
        String(
          candidate ||
          ""
        )
          .match(
            /\b\d{4,6}\b/
          );

      if (match) {
        return match[0];
      }
    }

    return "";
  }

  /* =========================================================
     stock_detail.json
     ========================================================= */

  async function getStockDetail(
    force = false
  ) {
    const now =
      Date.now();

    if (
      !force &&
      detailCache &&
      now -
        detailCacheAt <
        CACHE_MS
    ) {
      return detailCache;
    }

    if (
      detailPromise
    ) {
      return detailPromise;
    }

    detailPromise =
      fetch(
        "./data/stock_detail.json?v=" +
        now,
        {
          cache:
            "no-store"
        }
      )
        .then(
          response => {
            if (
              !response.ok
            ) {
              throw new Error(
                "stock_detail.json HTTP " +
                response.status
              );
            }

            return (
              response.json()
            );
          }
        )
        .then(
          data => {
            detailCache =
              data;

            detailCacheAt =
              Date.now();

            return data;
          }
        )
        .finally(
          () => {
            detailPromise =
              null;
          }
        );

    return detailPromise;
  }

  /* =========================================================
     金標樣式
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
         上方金色說明
         ========================= */

      .heat-strength-note{
        display:flex;
        align-items:center;
        gap:8px;

        width:max-content;
        max-width:100%;

        margin:
          0 0 12px;

        padding:
          7px 10px;

        border:
          1px solid
          rgba(
            202,
            138,
            4,
            .26
          );

        border-radius:
          10px;

        background:
          rgba(
            254,
            243,
            199,
            .56
          );

        color:
          #765314;

        font-size:
          10px;

        font-weight:
          800;

        line-height:
          1.35;
      }

      .heat-strength-swatch{
        width:11px;
        height:11px;

        flex:
          0 0 11px;

        border:
          1px solid
          rgba(
            202,
            138,
            4,
            .42
          );

        border-radius:
          4px;

        background:
          linear-gradient(
            180deg,
            rgba(
              253,
              230,
              138,
              .92
            ),
            rgba(
              254,
              243,
              199,
              .92
            )
          );
      }

      /* =========================
         Top 2 金色背景
         ========================= */

      #heatGrid
      .heat-stock.heat-stock-top2{
        position:relative;

        border-color:
          rgba(
            202,
            138,
            4,
            .42
          )
          !important;

        background:
          linear-gradient(
            135deg,
            rgba(
              254,
              243,
              199,
              .88
            ),
            rgba(
              253,
              230,
              138,
              .58
            )
          )
          !important;

        box-shadow:
          inset
          0 0 0 1px
          rgba(
            245,
            158,
            11,
            .08
          ),
          0 4px 12px
          rgba(
            161,
            98,
            7,
            .08
          );
      }

      /* =========================
         Top 1 / Top 2 標籤
         ========================= */

      #heatGrid
      .heat-strength-rank{
        display:inline-flex;

        align-items:center;
        justify-content:center;

        flex:
          0 0 auto;

        margin-left:
          6px;

        padding:
          3px 6px;

        border:
          1px solid
          rgba(
            180,
            83,
            9,
            .24
          );

        border-radius:
          999px;

        background:
          rgba(
            255,
            251,
            235,
            .92
          );

        color:
          #92400e;

        font-size:
          9px;

        font-weight:
          900;

        line-height:
          1;

        white-space:
          nowrap;

        vertical-align:
          middle;
      }

      /* =========================
         深色模式
         ========================= */

      html[data-theme="dark"]
      .heat-strength-note{
        border-color:
          rgba(
            234,
            179,
            8,
            .30
          );

        background:
          rgba(
            113,
            63,
            18,
            .26
          );

        color:
          #fde68a;
      }

      html[data-theme="dark"]
      .heat-strength-swatch{
        border-color:
          rgba(
            250,
            204,
            21,
            .42
          );

        background:
          linear-gradient(
            180deg,
            rgba(
              161,
              98,
              7,
              .72
            ),
            rgba(
              113,
              63,
              18,
              .72
            )
          );
      }

      html[data-theme="dark"]
      #heatGrid
      .heat-stock.heat-stock-top2{
        border-color:
          rgba(
            250,
            204,
            21,
            .42
          )
          !important;

        background:
          linear-gradient(
            135deg,
            rgba(
              113,
              63,
              18,
              .62
            ),
            rgba(
              146,
              64,
              14,
              .44
            )
          )
          !important;

        box-shadow:
          inset
          0 0 0 1px
          rgba(
            250,
            204,
            21,
            .08
          ),
          0 4px 14px
          rgba(
            0,
            0,
            0,
            .12
          );
      }

      html[data-theme="dark"]
      #heatGrid
      .heat-strength-rank{
        border-color:
          rgba(
            250,
            204,
            21,
            .28
          );

        background:
          rgba(
            66,
            32,
            6,
            .88
          );

        color:
          #fde68a;
      }

      /* =========================
         手機
         ========================= */

      @media(
        max-width:720px
      ){
        .heat-strength-note{
          margin-bottom:
            10px;

          padding:
            7px 9px;

          font-size:
            9px;
        }

        #heatGrid
        .heat-strength-rank{
          margin-left:
            4px;

          padding:
            3px 5px;

          font-size:
            8px;
        }
      }

      @media(
        max-width:390px
      ){
        #heatGrid
        .heat-strength-rank{
          padding:
            2px 4px;

          font-size:
            7px;
        }
      }
    `;

    document.head.appendChild(
      style
    );
  }

  /* =========================================================
     金標說明
     ========================================================= */

  function ensureStrengthNote() {
    const grid =
      document.getElementById(
        "heatGrid"
      );

    if (!grid) {
      return;
    }

    let note =
      document.getElementById(
        "heatStrengthNote"
      );

    if (!note) {
      note =
        document.createElement(
          "div"
        );

      note.id =
        "heatStrengthNote";

      note.className =
        "heat-strength-note";

      grid
        .parentNode
        .insertBefore(
          note,
          grid
        );
    }

    /*
     * 只有「當日」顯示金標說明
     * 5 / 10 / 20 日完全隱藏
     */

    if (
      activePeriod() !==
      "1"
    ) {
      note.style.display =
        "none";

      return;
    }

    note.style.display =
      "";

    note.innerHTML = `
      <span
        class="heat-strength-swatch"
        aria-hidden="true"
      ></span>

      <span>
        金色＝各族群近5日累積漲幅前2強
      </span>
    `;
  }

  /* =========================================================
     清除舊金標
     ========================================================= */

  function clearStrengthMarks() {
    document
      .querySelectorAll(
        "#heatGrid .heat-stock-top2"
      )
      .forEach(
        row => {
          row
            .classList
            .remove(
              "heat-stock-top2"
            );

          row.removeAttribute(
            "data-period-rank"
          );

          row.removeAttribute(
            "data-period-return"
          );

          row.removeAttribute(
            "data-5d-rank"
          );

          row.removeAttribute(
            "data-5d-return"
          );
        }
      );

    document
      .querySelectorAll(
        "#heatGrid .heat-strength-rank"
      )
      .forEach(
        label => {
          label.remove();
        }
      );
  }

  /* =========================================================
     加排名標籤
     ========================================================= */

  function addRankLabel(
    row,
    rank
  ) {
    const ticker =
      row.querySelector(
        ".t"
      );

    if (!ticker) {
      return;
    }

    const old =
      row.querySelector(
        ".heat-strength-rank"
      );

    if (old) {
      old.remove();
    }

    const label =
      document.createElement(
        "span"
      );

    label.className =
      "heat-strength-rank";

    label.textContent =
      `近5日漲幅第${rank}`;

    /*
     * 股票代號後面
     * 不蓋右側當日漲跌幅
     */

    ticker.insertAdjacentElement(
      "afterend",
      label
    );
  }

  /* =========================================================
     固定取得近 5 日累積報酬
     ========================================================= */

  function stock5dReturn(
    ticker,
    detailData
  ) {
    const stock =
      detailData
        ?.stocks
        ?.[ticker];

    const series =
      stock
        ?.returns_by_period
        ?.[RANK_PERIOD] ||
      stock?.returns;

    return (
      latestValidNumber(
        series
      )
    );
  }

  /* =========================================================
     單一族群近 5 日 Top 2
     ========================================================= */

  function markTopStocks(
    detail,
    detailData
  ) {
    /*
     * 非當日模式
     * 不產生任何金標
     */

    if (
      activePeriod() !==
      "1"
    ) {
      return;
    }

    const rows =
      [
        ...detail
          .querySelectorAll(
            ".heat-stock"
          )
      ];

    if (!rows.length) {
      return;
    }

    const ranked =
      rows
        .map(
          row => {
            const ticker =
              tickerFromRow(
                row
              );

            return {
              row,
              ticker,

              value:
                stock5dReturn(
                  ticker,
                  detailData
                )
            };
          }
        )
        .filter(
          item =>
            item.ticker &&
            item.value !==
              null &&
            Number.isFinite(
              item.value
            )
        )
        .sort(
          (
            a,
            b
          ) =>
            b.value -
            a.value
        );

    ranked
      .slice(
        0,
        TOP_COUNT
      )
      .forEach(
        (
          item,
          index
        ) => {
          const rank =
            index + 1;

          item
            .row
            .classList
            .add(
              "heat-stock-top2"
            );

          item
            .row
            .setAttribute(
              "data-period-rank",
              String(rank)
            );

          item
            .row
            .setAttribute(
              "data-period-return",
              String(
                item.value
              )
            );

          /*
           * 保留舊版屬性相容性
           */

          item
            .row
            .setAttribute(
              "data-5d-rank",
              String(rank)
            );

          item
            .row
            .setAttribute(
              "data-5d-return",
              String(
                item.value
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
     套用金標
     ========================================================= */

  async function applyStrengthMarks(
    forceData = false
  ) {
    if (
      applying ||
      !heatmapVisible()
    ) {
      return;
    }

    const grid =
      document.getElementById(
        "heatGrid"
      );

    if (!grid) {
      return;
    }

    injectStyles();

    ensureStrengthNote();

    /*
     * 先清除舊標記
     *
     * 從當日切換到
     * 5 / 10 / 20 日時
     * 金標會立即消失
     */

    clearStrengthMarks();

    if (
      activePeriod() !==
      "1"
    ) {
      ensureStrengthNote();

      return;
    }

    const details =
      [
        ...grid
          .querySelectorAll(
            ".heat-detail"
          )
      ];

    /*
     * 沒有展開族群
     * 不下載 stock_detail
     */

    if (!details.length) {
      return;
    }

    applying =
      true;

    try {
      const detailData =
        await getStockDetail(
          forceData
        );

      /*
       * await 期間如果已經切到
       * 5 / 10 / 20 日
       * 就不要再補金標
       */

      if (
        activePeriod() !==
        "1"
      ) {
        clearStrengthMarks();

        ensureStrengthNote();

        return;
      }

      details.forEach(
        detail => {
          markTopStocks(
            detail,
            detailData
          );
        }
      );

      ensureStrengthNote();

    } catch (error) {
      console.error(
        "[Heat Strength]",
        error
      );

    } finally {
      applying =
        false;
    }
  }

  /* =========================================================
     Debounce
     ========================================================= */

  function scheduleApply(
    delay =
      APPLY_DEBOUNCE,

    forceData =
      false
  ) {
    if (
      applyTimer
    ) {
      clearTimeout(
        applyTimer
      );
    }

    applyTimer =
      setTimeout(
        () => {
          applyTimer =
            null;

          applyStrengthMarks(
            forceData
          );
        },
        delay
      );
  }

  /* =========================================================
     監聽展開 / 收合
     ========================================================= */

  function observeHeatGrid() {
    const grid =
      document.getElementById(
        "heatGrid"
      );

    if (!grid) {
      return;
    }

    if (
      observer
    ) {
      observer.disconnect();
    }

    observer =
      new MutationObserver(
        mutations => {
          if (
            applying
          ) {
            return;
          }

          const meaningful =
            mutations.some(
              mutation =>
                mutation.type ===
                  "childList" &&
                mutation.target ===
                  grid
            );

          if (
            !meaningful
          ) {
            return;
          }

          scheduleApply(
            APPLY_DEBOUNCE,
            false
          );
        }
      );

    observer.observe(
      grid,
      {
        childList:
          true,

        subtree:
          false
      }
    );
  }

  /* =========================================================
     事件
     ========================================================= */

  function bindEvents() {

    /*
     * 切換：
     * 當日 / 5日 / 10日 / 20日
     */

    window.addEventListener(
      "heatmap:period-changed",
      () => {
        clearStrengthMarks();

        ensureStrengthNote();

        scheduleApply(
          40,
          false
        );
      }
    );

    /*
     * Heatmap 資料更新
     */

    window.addEventListener(
      "heatmap:data-updated",
      () => {
        detailCache =
          null;

        detailCacheAt =
          0;

        scheduleApply(
          220,
          true
        );
      }
    );

    /*
     * refresh controller
     */

    window.addEventListener(
      "tw-market:refresh-heatmap",
      () => {
        scheduleApply(
          260,
          false
        );
      }
    );

    /*
     * 全站 refresh
     */

    window.addEventListener(
      "tw-market:refreshed",
      event => {
        if (
          event
            ?.detail
            ?.page ===
          "heat"
        ) {
          scheduleApply(
            260,
            false
          );
        }
      }
    );

    /*
     * 點族群展開後
     * 補近 5 日 Top 2
     */

    document.addEventListener(
      "click",
      event => {
        const button =
          event
            .target
            .closest(
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
        passive:
          true
      }
    );

    /*
     * iPhone / Safari
     */

    document.addEventListener(
      "visibilitychange",
      () => {
        if (
          document.hidden ||
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
          !event.persisted ||
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
  }

  /* =========================================================
     對外 API
     ========================================================= */

  window.refreshHeatStrength =
    function (
      forceData =
        false
    ) {
      return (
        applyStrengthMarks(
          !!forceData
        )
      );
    };

  window.clearHeatStrengthCache =
    function () {
      detailCache =
        null;

      detailCacheAt =
        0;
    };

  /* =========================================================
     初始化
     ========================================================= */

  function init() {
    injectStyles();

    ensureStrengthNote();

    observeHeatGrid();

    bindEvents();

    if (
      heatmapVisible()
    ) {
      scheduleApply(
        300,
        false
      );
    }

    console.log(
      "[Heat Strength] 1D view / fixed 5D Top 2 module ready"
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
        once:
          true
      }
    );

  } else {
    init();
  }

})();
