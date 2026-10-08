(() => {
  "use strict";

  /*
   * heatmap_period.js
   *
   * 修正：
   * 1. 大盤、OTC 指數統一由 app.js 顯示
   * 2. 避免歷史收盤資料覆蓋當日即時行情
   * 3. 補上 tpex_benchmark 支援
   * 4. 保留期間、權重按鈕及手機版樣式
   */

  if (window.__heatmapPeriodStyleOnlyLoaded) return;

  window.__heatmapPeriodStyleOnlyLoaded = true;
  window.__heatmapPeriodManaged = true;

  function valid(value) {
    if (
      value === null ||
      value === undefined ||
      value === ""
    ) {
      return null;
    }

    const n = Number(value);

    return Number.isFinite(n) ? n : null;
  }

  function last(values) {
    if (!Array.isArray(values)) return null;

    for (let i = values.length - 1; i >= 0; i--) {
      const n = valid(values[i]);

      if (n !== null) return n;
    }

    return null;
  }

  /*
   * 修正 app.js 的指數計算函式
   *
   * 當日：
   * 使用 heatmap.json 的即時指數
   *
   * 5／10／20 日：
   * 優先使用最新指數與歷史基準價
   *
   * OTC：
   * 支援 tpex_benchmark
   *
   * 不再使用昨日漲跌幅冒充盤中行情
   */

  window.heatBenchmarkReturn = function (
    period = "1",
    market = "twse"
  ) {
    period = String(period);

    const live =
      typeof cache !== "undefined"
        ? cache.heat?.indices?.[market]
        : null;

    if (period === "1") {
      return valid(live?.change_pct);
    }

    const detail =
      typeof heatDetailData !== "undefined"
        ? heatDetailData
        : null;

    const history =
      market === "twse"
        ? detail?.benchmark
        : (
            detail?.tpex_benchmark ||
            detail?.otc_benchmark ||
            detail?.benchmark_tpex
          );

    const livePrice = valid(
      live?.price ??
      live?.index ??
      live?.value
    );

    const basePrice = valid(
      history?.base_prices?.[period]
    );

    if (
      livePrice !== null &&
      livePrice > 0 &&
      basePrice !== null &&
      basePrice > 0
    ) {
      return (
        livePrice / basePrice - 1
      ) * 100;
    }

    /*
     * 有即時指數但缺少基準價：
     * 顯示 —，避免誤用昨日歷史報酬率
     */

    if (
      livePrice !== null &&
      livePrice > 0
    ) {
      return null;
    }

    const byPeriod = valid(
      history?.changes_by_period?.[period]
    );

    if (byPeriod !== null) {
      return byPeriod;
    }

    return last(
      history?.returns_by_period?.[period] ||
      (
        period === "5"
          ? history?.returns
          : null
      )
    );
  };

  /*
   * 樣式
   *
   * 本檔不再寫入 heatPeriodBenchmark
   * 避免與 app.js 重複渲染
   */

  function injectStyle() {
    if (
      document.getElementById(
        "heatmap-period-style"
      )
    ) {
      return;
    }

    const style = document.createElement("style");

    style.id = "heatmap-period-style";

    style.textContent = `

      .heat-period-wrap {
        display: flex;
        flex-direction: column;
        gap: 9px;
        margin: 0 0 14px;
        width: 100%;
        box-sizing: border-box;
      }

      .heat-control-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
        width: 100%;
        box-sizing: border-box;
      }

      .heat-period-tabs,
      .heat-weight-tabs {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px;
        border: 1px solid var(--line);
        border-radius: 12px;
        background: var(--card);
        box-sizing: border-box;
      }

      .heat-period-btn,
      .heat-weight-btn {
        appearance: none;
        -webkit-appearance: none;
        border: 0;
        outline: 0;
        cursor: pointer;
        height: 34px;
        padding: 0 13px;
        border-radius: 9px;
        background: transparent;
        color: var(--muted);
        font-size: 12px;
        font-weight: 800;
        line-height: 34px;
        text-align: center;
        white-space: nowrap;
        box-sizing: border-box;

        transition:
          background .15s ease,
          color .15s ease,
          box-shadow .15s ease,
          transform .15s ease;
      }

      .heat-period-btn {
        min-width: 54px;
      }

      .heat-weight-btn {
        min-width: 82px;
      }

      .heat-period-btn:hover,
      .heat-weight-btn:hover {
        color: var(--ink);
      }

      .heat-period-btn:active,
      .heat-weight-btn:active {
        transform: scale(.97);
      }

      .heat-period-btn.active,
      .heat-weight-btn.active {
        background: var(--ink);
        color: var(--card);

        box-shadow:
          0 2px 8px rgba(15, 23, 42, .12);
      }

      .heat-period-meta {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
        width: 100%;
        min-width: 0;
        color: var(--muted);
        font-size: 10px;
        line-height: 1.5;
        box-sizing: border-box;
      }

      #heatWeightDescription {
        min-width: 0;
        flex: 1 1 auto;
      }

      .heat-period-benchmark {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 0;
        border: 0;
        background: transparent;
        white-space: nowrap;
        box-sizing: border-box;
      }

      .heat-period-benchmark > span {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        padding: 6px 9px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--card);
        white-space: nowrap;
        box-sizing: border-box;
      }

      .heat-period-benchmark > span strong {
        font-size: 11px;
        font-weight: 900;
      }

      .heat-period-benchmark .up {
        color: #dc2626;
      }

      .heat-period-benchmark .down {
        color: #15803d;
      }

      [data-theme="dark"] .heat-period-btn.active,
      [data-theme="dark"] .heat-weight-btn.active {
        background: #f8fafc;
        color: #0f172a;
      }

      [data-theme="dark"] .heat-period-tabs,
      [data-theme="dark"] .heat-weight-tabs,
      [data-theme="dark"] .heat-period-benchmark > span {
        background: var(--card);
      }

      @media (max-width: 900px) {

        .heat-control-row {
          align-items: stretch;
        }

        .heat-period-tabs,
        .heat-weight-tabs {
          max-width: 100%;
        }

      }

      @media (max-width: 720px) {

        .heat-period-wrap {
          gap: 8px;
          margin-bottom: 12px;
        }

        .heat-control-row {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          gap: 8px;
          width: 100%;
        }

        .heat-period-tabs {
          display: grid;
          grid-template-columns:
            repeat(4, minmax(0, 1fr));
          gap: 5px;
          width: 100%;
        }

        .heat-weight-tabs {
          display: grid;
          grid-template-columns:
            repeat(2, minmax(0, 1fr));
          gap: 5px;
          width: 100%;
        }

        .heat-period-btn,
        .heat-weight-btn {
          width: 100%;
          min-width: 0;
          padding: 0 6px;
        }

        .heat-period-meta {
          width: 100%;
          gap: 8px;
          align-items: center;
        }

        #heatWeightDescription {
          flex: 1 1 100%;
          min-width: 0;
        }

        .heat-period-benchmark {
          width: 100%;
          display: grid;
          grid-template-columns:
            repeat(2, minmax(0, 1fr));
          gap: 6px;
        }

        .heat-period-benchmark > span {
          justify-content: center;
          min-width: 0;
          padding: 6px 7px;
          margin-left: 0 !important;
        }

      }

      @media (max-width: 430px) {

        .heat-period-btn,
        .heat-weight-btn {
          height: 32px;
          line-height: 32px;
          font-size: 11px;
        }

        .heat-period-meta {
          font-size: 9px;
        }

        .heat-period-benchmark > span {
          padding: 5px;
          gap: 4px;
        }

        .heat-period-benchmark > span strong {
          font-size: 10px;
        }

      }

      @media (max-width: 360px) {

        .heat-period-tabs,
        .heat-weight-tabs {
          gap: 3px;
          padding: 3px;
        }

        .heat-period-btn,
        .heat-weight-btn {
          padding: 0 3px;
          font-size: 10px;
        }

        .heat-period-benchmark > span {
          font-size: 8px;
        }

      }

    `;

    document.head.appendChild(style);
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      injectStyle,
      { once: true }
    );
  } else {
    injectStyle();
  }

})();
