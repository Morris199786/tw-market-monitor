(() => {
  "use strict";

  /*
   * heatmap_period.js
   *
   * 1. 保留熱力圖控制按鈕樣式
   * 2. 修正大盤 / OTC 指數顯示
   * 3. 當日使用 heatmap.json 即時資料
   * 4. 5 / 10 / 20 日使用即時指數與歷史基準價
   * 5. 不修改族群、個股、權重及排序
   * 6. 不修改其他檔案或版本參數
   */

  if (window.__heatmapPeriodStyleOnlyLoaded) {
    return;
  }

  window.__heatmapPeriodStyleOnlyLoaded = true;
  window.__heatmapPeriodManaged = true;

  const STYLE_ID = "heatmap-period-style";

  let detailCache = null;
  let detailPromise = null;
  let detailLoadedAt = 0;

  let heatCache = null;
  let heatPromise = null;
  let heatLoadedAt = 0;

  let renderToken = 0;

  const DETAIL_TTL = 5 * 60 * 1000;
  const HEAT_TTL = 60 * 1000;

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

  function pct(value) {
    const n = valid(value);

    if (n === null) {
      return "—";
    }

    return (
      (n > 0 ? "+" : "") +
      n.toFixed(2) +
      "%"
    );
  }

  function last(values) {
    if (!Array.isArray(values)) {
      return null;
    }

    for (
      let i = values.length - 1;
      i >= 0;
      i--
    ) {
      const n = valid(values[i]);

      if (n !== null) {
        return n;
      }
    }

    return null;
  }

  function activePeriod() {
    if (
      typeof window.getHeatmapActivePeriod ===
      "function"
    ) {
      return String(
        window.getHeatmapActivePeriod() || "1"
      );
    }

    return "1";
  }

  function periodLabel(period) {
    return period === "1"
      ? "當日"
      : `近${period}日`;
  }

  /*
   * 共用資料讀取
   *
   * 優先使用 app.js 的 J()
   * 避免重複請求
   */

  async function getJSON(path, force = false) {
    if (typeof window.J === "function") {
      return window.J(path, { force });
    }

    const url =
      path +
      (path.includes("?") ? "&" : "?") +
      "v=" +
      Date.now();

    const response = await fetch(url, {
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}`
      );
    }

    return response.json();
  }

  async function loadDetail(force = false) {
    const now = Date.now();

    if (
      !force &&
      detailCache &&
      now - detailLoadedAt < DETAIL_TTL
    ) {
      return detailCache;
    }

    if (detailPromise) {
      return detailPromise;
    }

    detailPromise = getJSON(
      "./data/stock_detail.json",
      force
    )
      .then(data => {
        if (
          data &&
          typeof data === "object" &&
          Object.keys(data).length
        ) {
          detailCache = data;
          detailLoadedAt = Date.now();
        }

        return detailCache || {};
      })
      .catch(error => {
        console.warn(
          "[heatmap benchmark detail]",
          error
        );

        return detailCache || {};
      })
      .finally(() => {
        detailPromise = null;
      });

    return detailPromise;
  }

  async function loadHeat(force = false) {
    const now = Date.now();

    if (
      !force &&
      heatCache &&
      now - heatLoadedAt < HEAT_TTL
    ) {
      return heatCache;
    }

    if (heatPromise) {
      return heatPromise;
    }

    heatPromise = getJSON(
      "./data/heatmap.json",
      force
    )
      .then(data => {
        if (
          data &&
          typeof data === "object" &&
          Object.keys(data).length
        ) {
          heatCache = data;
          heatLoadedAt = Date.now();
        }

        return heatCache || {};
      })
      .catch(error => {
        console.warn(
          "[heatmap benchmark live]",
          error
        );

        return heatCache || {};
      })
      .finally(() => {
        heatPromise = null;
      });

    return heatPromise;
  }

  /*
   * 指數計算
   *
   * 當日：
   * heatmap.json.indices
   *
   * 5 / 10 / 20 日：
   * 最新指數 / 歷史基準價 - 1
   *
   * 若盤中有最新指數，
   * 但缺少基準價，
   * 不使用昨日累積報酬率冒充最新數字
   */

  function benchmarkReturn(
    period,
    market,
    heat,
    detail
  ) {
    const live =
      heat?.indices?.[market] ||
      heat?.index_quotes?.[market];

    if (period === "1") {
      return valid(
        live?.change_pct
      );
    }

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
     * 盤中有即時行情，
     * 但缺少對應基準價
     *
     * 不顯示過期數字
     */

    if (
      livePrice !== null &&
      livePrice > 0
    ) {
      return null;
    }

    const historicalChange = valid(
      history?.changes_by_period?.[period]
    );

    if (historicalChange !== null) {
      return historicalChange;
    }

    return last(
      history?.returns_by_period?.[period] ||
      (
        period === "5"
          ? history?.returns
          : null
      )
    );
  }

  function benchmarkChip(
    label,
    value
  ) {
    const n = valid(value);

    const cls =
      n === null
        ? ""
        : n > 0
          ? "up"
          : n < 0
            ? "down"
            : "";

    return `
      <span class="heat-benchmark-chip">
        ${label}
        <strong class="${cls}">
          ${pct(n)}
        </strong>
      </span>
    `;
  }

  /*
   * 大盤與 OTC 顯示
   *
   * app.js 仍負責建立控制列
   *
   * 本檔在切換期間後，
   * 使用同一組正確資料更新指數
   */

  async function renderBenchmarks() {
    const host = document.getElementById(
      "heatPeriodBenchmark"
    );

    if (!host) {
      return;
    }

    const token = ++renderToken;
    const period = activePeriod();

    const [heat, detail] = await Promise.all([
      loadHeat(),
      period === "1"
        ? Promise.resolve({})
        : loadDetail()
    ]);

    /*
     * 避免使用者快速切換期間時，
     * 較慢完成的舊請求覆蓋新畫面
     */

    if (token !== renderToken) {
      return;
    }

    if (
      period !== activePeriod()
    ) {
      return;
    }

    const twse = benchmarkReturn(
      period,
      "twse",
      heat,
      detail
    );

    const tpex = benchmarkReturn(
      period,
      "tpex",
      heat,
      detail
    );

    const label = periodLabel(period);

    const markup = `
      ${benchmarkChip(
        `大盤${label}漲幅`,
        twse
      )}

      ${benchmarkChip(
        `OTC${label}漲幅`,
        tpex
      )}
    `;

    if (host.innerHTML !== markup) {
      host.innerHTML = markup;
    }

    host.title =
      period === "1"
        ? "當日指數：使用 heatmap.json 即時行情"
        : "期間指數：優先使用最新指數與歷史基準價計算";
  }

  /*
   * 保留原本的控制列樣式
   */

  function injectStyle() {
    if (
      document.getElementById(STYLE_ID)
    ) {
      return;
    }

    const style = document.createElement(
      "style"
    );

    style.id = STYLE_ID;

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

      .heat-benchmark-chip {
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

      .heat-benchmark-chip strong {
        font-size: 11px;
        font-weight: 900;
      }

      .heat-benchmark-chip .up {
        color: #dc2626;
      }

      .heat-benchmark-chip .down {
        color: #15803d;
      }

      [data-theme="dark"]
      .heat-period-btn.active,

      [data-theme="dark"]
      .heat-weight-btn.active {
        background: #f8fafc;
        color: #0f172a;
      }

      [data-theme="dark"]
      .heat-period-tabs,

      [data-theme="dark"]
      .heat-weight-tabs,

      [data-theme="dark"]
      .heat-benchmark-chip {
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

        .heat-benchmark-chip {
          justify-content: center;
          min-width: 0;
          padding: 6px 7px;
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

        .heat-benchmark-chip {
          padding: 5px;
          gap: 4px;
        }

        .heat-benchmark-chip strong {
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

        .heat-benchmark-chip {
          font-size: 8px;
        }

      }

    `;

    document.head.appendChild(style);
  }

  /*
   * 延後一個畫面週期，
   * 等 app.js 完成熱力圖渲染
   */

  function refreshSoon() {
    requestAnimationFrame(() => {
      renderBenchmarks();
    });
  }

  /*
   * 啟動
   */

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        injectStyle();
        refreshSoon();
      },
      { once: true }
    );
  } else {
    injectStyle();
    refreshSoon();
  }

  /*
   * 切換期間
   */

  window.addEventListener(
    "heatmap:period-changed",
    refreshSoon
  );

  /*
   * 切換權重
   */

  window.addEventListener(
    "heatmap:weight-changed",
    refreshSoon
  );

  /*
   * 展開族群
   */

  window.addEventListener(
    "heatmap:detail-rendered",
    refreshSoon
  );

  /*
   * 即時行情更新
   */

  window.addEventListener(
    "heatmap:data-updated",
    event => {
      const data = event.detail;

      if (data?.indices && heatCache) {
        heatCache.indices = data.indices;
        heatLoadedAt = Date.now();
      } else {
        heatLoadedAt = 0;
      }

      refreshSoon();
    }
  );

  /*
   * 手機切回前景
   *
   * 重新檢查資料是否過期
   */

  window.addEventListener(
    "focus",
    () => {
      heatLoadedAt = 0;
      refreshSoon();
    }
  );

})();
