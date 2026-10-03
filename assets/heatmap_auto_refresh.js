/* =========================================================
   Heatmap 各期間族群強勢股 Top 2 金色標記
   2026-10-03

   功能：
   1. 當日 / 5日 / 10日 / 20日
      都依目前期間重新判斷 Top 2

   2. 切換期間後：
      金色標記跟著更新

   3. 點族群展開：
      只補金色標記
      不改動族群排序

   4. 不自行輪詢 heatmap.json

   5. stock_detail.json
      使用 5 分鐘記憶體快取

   6. 保留 iPhone / Safari
      回到頁面後補標記
   ========================================================= */

(function () {
  "use strict";


  /* =========================================================
     基本設定
     ========================================================= */

  const TOP_COUNT =
    2;

  const CACHE_MS =
    5 * 60 * 1000;

  const APPLY_DEBOUNCE =
    180;


  let detailCache =
    null;

  let detailCacheAt =
    0;

  let detailPromise =
    null;


  let heatCache =
    null;

  let heatCacheAt =
    0;

  let heatPromise =
    null;


  let applyTimer =
    null;

  let applying =
    false;

  let observer =
    null;


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


  function periodText(
    period
  ) {
    if (
      period ===
      "1"
    ) {
      return "當日";
    }

    return (
      `近${period}日`
    );
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


  /*
   * robust ticker parser
   *
   * 避免 ticker 不一定直接在
   * .heat-stock dataset
   */

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
     從展開區塊判斷族群
     ========================================================= */

  function sectorFromDetail(
    detail
  ) {
    if (!detail) {
      return "";
    }


    /*
     * 正常情況：
     *
     * button.heat
     * ↓
     * .heat-detail
     */

    const prev =
      detail
        .previousElementSibling;


    if (
      prev?.matches?.(
        "button.heat[data-sec]"
      )
    ) {
      return String(
        prev.dataset.sec ||
        ""
      );
    }


    /*
     * fallback：
     * 從 detail 標題抓族群名稱
     */

    const head =
      detail.querySelector(
        ".heat-detail-head b"
      );


    if (!head) {
      return "";
    }


    return (
      [
        ...head.childNodes
      ]
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


    /*
     * 共用正在執行中的 Promise
     * 避免同時下載多次
     */

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
     heatmap.json
     ========================================================= */

  async function getHeatmap(
    force = false
  ) {
    const now =
      Date.now();


    if (
      !force &&
      heatCache &&
      now -
        heatCacheAt <
        CACHE_MS
    ) {
      return heatCache;
    }


    if (
      heatPromise
    ) {
      return heatPromise;
    }


    heatPromise =
      fetch(
        "./data/heatmap.json?v=" +
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
                "heatmap.json HTTP " +
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
            heatCache =
              data;

            heatCacheAt =
              Date.now();

            return data;
          }
        )
        .finally(
          () => {
            heatPromise =
              null;
          }
        );


    return heatPromise;
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
      .heat-stock
      .heat-stock-top2{
        position:relative;
      }


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


    const period =
      activePeriod();


    note.innerHTML = `
      <span
        class="heat-strength-swatch"
        aria-hidden="true"
      ></span>

      <span>
        金色＝各族群${periodText(period)}累積漲幅前2強
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


          /*
           * 相容舊版屬性
           */

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
    rank,
    period
  ) {
    const ticker =
      row.querySelector(
        ".t"
      );


    if (!ticker) {
      return;
    }


    /*
     * 避免重複
     */

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
      `${periodText(period)}漲幅第${rank}`;


    /*
     * 股票代號後面
     * 不蓋右側漲幅 %
     */

    ticker.insertAdjacentElement(
      "afterend",
      label
    );
  }


  /* =========================================================
     個股目前期間報酬
     ========================================================= */

  function stockPeriodReturn(
    ticker,
    period,
    detailData,
    heatSector
  ) {
    /*
     * 當日
     */

    if (
      period ===
      "1"
    ) {
      const item =
        (
          heatSector
            ?.stocks ||
          []
        )
          .find(
            x =>
              String(
                x.ticker ||
                ""
              ) ===
              ticker
          );


      const n =
        Number(
          item
            ?.change_pct
        );


      return (
        Number.isFinite(n)
          ? n
          : null
      );
    }


    /*
     * 5 / 10 / 20 日
     */

    const stock =
      detailData
        ?.stocks
        ?.[ticker];


    const series =
      stock
        ?.returns_by_period
        ?.[period] ||
      (
        period ===
        "5"
          ? stock?.returns
          : null
      );


    return (
      latestValidNumber(
        series
      )
    );
  }


  /* =========================================================
     單一族群 Top 2
     ========================================================= */

  function markTopStocks(
    detail,
    detailData,
    heatData
  ) {
    const sectorName =
      sectorFromDetail(
        detail
      );


    if (!sectorName) {
      return;
    }


    const period =
      activePeriod();


    const heatSector =
      (
        heatData
          ?.sectors ||
        []
      )
        .find(
          sector =>
            String(
              sector.name ||
              ""
            ) ===
            sectorName
        );


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
                stockPeriodReturn(
                  ticker,
                  period,
                  detailData,
                  heatSector
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


          addRankLabel(
            item.row,
            rank,
            period
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


    const details =
      [
        ...grid
          .querySelectorAll(
            ".heat-detail"
          )
      ];


    /*
     * 沒有展開族群
     * 不需要下載資料
     */

    if (!details.length) {
      clearStrengthMarks();

      return;
    }


    applying =
      true;


    try {
      const period =
        activePeriod();


      const [
        detailData,
        heatData
      ] =
        await Promise.all([
          getStockDetail(
            forceData
          ),

          /*
           * 當日排名需要
           * heatmap.json 的 change_pct
           *
           * 5/10/20 日不用
           */

          period ===
            "1"
            ? getHeatmap(
                forceData
              )
            : Promise.resolve(
                heatCache
              )
        ]);


      clearStrengthMarks();


      details.forEach(
        detail => {
          markTopStocks(
            detail,
            detailData,
            heatData
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


          /*
           * 只補金標
           *
           * 這裡完全不會呼叫
           * heatmap 的 reorderGrid
           */

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
     * 使用者切換：
     * 當日 / 5 / 10 / 20
     *
     * heatmap_period.js
     * 會送這個事件
     */

    window.addEventListener(
      "heatmap:period-changed",
      () => {
        ensureStrengthNote();


        scheduleApply(
          40,
          false
        );
      }
    );


    /*
     * 後台 Heatmap 資料
     * 真的更新
     */

    window.addEventListener(
      "heatmap:data-updated",
      () => {
        detailCache =
          null;

        detailCacheAt =
          0;


        heatCache =
          null;

        heatCacheAt =
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
     * 點族群
     *
     * 等 app.js 展開後
     * 再補 Top 2
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


      heatCache =
        null;

      heatCacheAt =
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


    /*
     * 第一次不強迫抓資料
     *
     * 沒展開族群時
     * applyStrengthMarks
     * 也不會下載 stock_detail
     */

    if (
      heatmapVisible()
    ) {
      scheduleApply(
        300,
        false
      );
    }


    console.log(
      "[Heat Strength] period-aware module ready"
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
