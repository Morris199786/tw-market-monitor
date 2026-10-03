(() => {
  "use strict";

  /*
   * heatmap_period.js
   *
   * 負責：
   * 1. 當日 / 5日 / 10日 / 20日按鈕樣式
   * 2. 市值加權 / 權重上限按鈕樣式
   * 3. 大盤 + OTC 同期漲幅顯示
   *
   * 熱力圖資料、期間、權重計算、排序仍全部由 app.js 處理
   * 本檔不修改任何熱力圖族群或個股數值
   */

  if (window.__heatmapPeriodStyleOnlyLoaded) {
    return;
  }

  window.__heatmapPeriodStyleOnlyLoaded = true;
  window.__heatmapPeriodManaged = true;

  const STYLE_ID = "heatmap-period-style";

  let detailCache = null;
  let detailPromise = null;

  function pct(v) {
    if (
      v === null ||
      v === undefined ||
      !Number.isFinite(Number(v))
    ) {
      return "—";
    }

    const n = Number(v);

    return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
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

  function lastNumber(arr) {
    const nums = (arr || [])
      .map(Number)
      .filter(Number.isFinite);

    return nums.length
      ? nums[nums.length - 1]
      : null;
  }

  /*
   * stock_detail.json 的 benchmark：
   *
   * 5 / 10 / 20 日：
   * returns_by_period 最後一個值
   * 就是該期間截至最新交易日的累積報酬
   *
   * 當日：
   * 利用近5日累積報酬的最後兩點
   * 還原最新一個交易日的單日漲跌幅
   */
  function benchmarkReturn(
    benchmark,
    period
  ) {
    if (!benchmark) {
      return null;
    }

    if (period !== "1") {
      return lastNumber(
        benchmark
          .returns_by_period?.[period] ||
        (
          period === "5"
            ? benchmark.returns
            : null
        )
      );
    }

    const values =
      benchmark
        .returns_by_period?.["5"] ||
      benchmark.returns ||
      [];

    const nums = values
      .map(Number)
      .filter(Number.isFinite);

    if (nums.length < 2) {
      return null;
    }

    const prev =
      nums[nums.length - 2] / 100;

    const curr =
      nums[nums.length - 1] / 100;

    return (
      (
        (1 + curr) /
        (1 + prev)
      ) - 1
    ) * 100;
  }

  async function loadDetail() {
    if (detailCache) {
      return detailCache;
    }

    if (detailPromise) {
      return detailPromise;
    }

    detailPromise = fetch(
      `./data/stock_detail.json?v=${Date.now()}`,
      {
        cache: "no-store"
      }
    )
      .then(r => {
        if (!r.ok) {
          throw new Error(
            `HTTP ${r.status}`
          );
        }

        return r.json();
      })
      .then(d => {
        detailCache = d || {};

        return detailCache;
      })
      .catch(err => {
        console.warn(
          "[OTC benchmark]",
          err
        );

        return {};
      })
      .finally(() => {
        detailPromise = null;
      });

    return detailPromise;
  }

  function benchmarkChip(
    label,
    value,
    extraClass = ""
  ) {
    const cls =
      Number(value) > 0
        ? "up"
        : Number(value) < 0
          ? "down"
          : "";

    return `
      <span
        class="
          heat-benchmark-chip
          ${extraClass}
        "
      >
        ${label}

        <strong class="${cls}">
          ${pct(value)}
        </strong>
      </span>
    `;
  }

  async function renderBenchmarks() {
    const host =
      document.getElementById(
        "heatPeriodBenchmark"
      );

    if (!host) {
      return;
    }

    const d =
      await loadDetail();

    const period =
      activePeriod();

    const label =
      periodLabel(period);

    const taiex =
      benchmarkReturn(
        d.benchmark,
        period
      );

    const otc =
      benchmarkReturn(
        d.tpex_benchmark,
        period
      );

    host.innerHTML = `
      ${benchmarkChip(
        `大盤${label}漲幅`,
        taiex
      )}

      ${benchmarkChip(
        `OTC${label}漲幅`,
        otc,
        "otc"
      )}
    `;
  }

  function injectStyle() {
    if (
      document.getElementById(
        STYLE_ID
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id = STYLE_ID;

    style.textContent = `

      /* =========================================================
         熱力圖控制區
      ========================================================= */

      .heat-period-wrap {
        display: flex;
        flex-direction: column;
        gap: 9px;

        margin:
          0 0 14px;

        width:
          100%;

        box-sizing:
          border-box;
      }


      .heat-control-row {
        display:
          flex;

        align-items:
          center;

        justify-content:
          space-between;

        gap:
          12px;

        flex-wrap:
          wrap;

        width:
          100%;

        box-sizing:
          border-box;
      }


      /* =========================================================
         期間按鈕
      ========================================================= */

      .heat-period-tabs {
        display:
          inline-flex;

        align-items:
          center;

        gap:
          6px;

        padding:
          4px;

        border:
          1px solid
          var(--line);

        border-radius:
          12px;

        background:
          var(--card);

        box-sizing:
          border-box;
      }


      /* =========================================================
         權重模式按鈕
      ========================================================= */

      .heat-weight-tabs {
        display:
          inline-flex;

        align-items:
          center;

        gap:
          6px;

        padding:
          4px;

        border:
          1px solid
          var(--line);

        border-radius:
          12px;

        background:
          var(--card);

        box-sizing:
          border-box;
      }


      /* =========================================================
         共用按鈕
      ========================================================= */

      .heat-period-btn,
      .heat-weight-btn {
        appearance:
          none;

        -webkit-appearance:
          none;

        border:
          0;

        outline:
          0;

        cursor:
          pointer;

        height:
          34px;

        padding:
          0 13px;

        border-radius:
          9px;

        background:
          transparent;

        color:
          var(--muted);

        font-size:
          12px;

        font-weight:
          800;

        line-height:
          34px;

        text-align:
          center;

        white-space:
          nowrap;

        box-sizing:
          border-box;

        transition:
          background .15s ease,
          color .15s ease,
          box-shadow .15s ease,
          transform .15s ease;
      }


      .heat-period-btn {
        min-width:
          54px;
      }


      .heat-weight-btn {
        min-width:
          82px;
      }


      .heat-period-btn:hover,
      .heat-weight-btn:hover {
        color:
          var(--ink);
      }


      .heat-period-btn:active,
      .heat-weight-btn:active {
        transform:
          scale(.97);
      }


      /* =========================================================
         選中狀態
      ========================================================= */

      .heat-period-btn.active,
      .heat-weight-btn.active {
        background:
          var(--ink);

        color:
          var(--card);

        box-shadow:
          0 2px 8px
          rgba(
            15,
            23,
            42,
            .12
          );
      }


      /* =========================================================
         說明 + 大盤 / OTC
      ========================================================= */

      .heat-period-meta {
        display:
          flex;

        align-items:
          center;

        justify-content:
          space-between;

        gap:
          12px;

        flex-wrap:
          wrap;

        width:
          100%;

        min-width:
          0;

        color:
          var(--muted);

        font-size:
          10px;

        line-height:
          1.5;

        box-sizing:
          border-box;
      }


      #heatWeightDescription {
        min-width:
          0;

        flex:
          1 1 auto;
      }


      /*
       * benchmark 外層現在容納兩個框：
       *
       * 大盤近20日漲幅
       * OTC近20日漲幅
       */

      .heat-period-benchmark {
        display:
          inline-flex;

        align-items:
          center;

        gap:
          6px;

        padding:
          0;

        border:
          0;

        background:
          transparent;

        white-space:
          nowrap;

        box-sizing:
          border-box;
      }


      .heat-benchmark-chip {
        display:
          inline-flex;

        align-items:
          center;

        gap:
          5px;

        padding:
          6px 9px;

        border:
          1px solid
          var(--line);

        border-radius:
          8px;

        background:
          var(--card);

        white-space:
          nowrap;

        box-sizing:
          border-box;
      }


      .heat-benchmark-chip strong {
        font-size:
          11px;

        font-weight:
          900;
      }


      /*
       * 台股：
       * 紅漲綠跌
       */

      .heat-benchmark-chip .up {
        color:
          #dc2626;
      }


      .heat-benchmark-chip .down {
        color:
          #15803d;
      }


      /* =========================================================
         深色模式
      ========================================================= */

      [data-theme="dark"]
      .heat-period-btn.active,

      [data-theme="dark"]
      .heat-weight-btn.active {
        background:
          #f8fafc;

        color:
          #0f172a;
      }


      [data-theme="dark"]
      .heat-period-tabs,

      [data-theme="dark"]
      .heat-weight-tabs,

      [data-theme="dark"]
      .heat-benchmark-chip {
        background:
          var(--card);
      }


      /* =========================================================
         iPad / 小尺寸桌面
      ========================================================= */

      @media (
        max-width: 900px
      ) {

        .heat-control-row {
          align-items:
            stretch;
        }


        .heat-period-tabs,
        .heat-weight-tabs {
          max-width:
            100%;
        }

      }


      /* =========================================================
         手機
      ========================================================= */

      @media (
        max-width: 720px
      ) {

        .heat-period-wrap {
          gap:
            8px;

          margin-bottom:
            12px;
        }


        .heat-control-row {
          display:
            grid;

          grid-template-columns:
            minmax(
              0,
              1fr
            );

          gap:
            8px;

          width:
            100%;
        }


        .heat-period-tabs {
          display:
            grid;

          grid-template-columns:
            repeat(
              4,
              minmax(
                0,
                1fr
              )
            );

          gap:
            5px;

          width:
            100%;

          box-sizing:
            border-box;
        }


        .heat-weight-tabs {
          display:
            grid;

          grid-template-columns:
            repeat(
              2,
              minmax(
                0,
                1fr
              )
            );

          gap:
            5px;

          width:
            100%;

          box-sizing:
            border-box;
        }


        .heat-period-btn,
        .heat-weight-btn {
          width:
            100%;

          min-width:
            0;

          padding:
            0 6px;
        }


        .heat-period-meta {
          width:
            100%;

          gap:
            8px;

          align-items:
            center;
        }


        #heatWeightDescription {
          flex:
            1 1 100%;

          min-width:
            0;
        }


        /*
         * 手機上大盤 / OTC 並排
         */

        .heat-period-benchmark {
          width:
            100%;

          display:
            grid;

          grid-template-columns:
            repeat(
              2,
              minmax(
                0,
                1fr
              )
            );

          gap:
            6px;
        }


        .heat-benchmark-chip {
          justify-content:
            center;

          min-width:
            0;

          padding:
            6px 7px;
        }

      }


      /* =========================================================
         小手機
      ========================================================= */

      @media (
        max-width: 430px
      ) {

        .heat-period-btn,
        .heat-weight-btn {
          height:
            32px;

          line-height:
            32px;

          font-size:
            11px;
        }


        .heat-period-meta {
          font-size:
            9px;
        }


        .heat-benchmark-chip {
          padding:
            5px 5px;

          gap:
            4px;
        }


        .heat-benchmark-chip strong {
          font-size:
            10px;
        }

      }


      /* =========================================================
         超小螢幕
      ========================================================= */

      @media (
        max-width: 360px
      ) {

        .heat-period-tabs,
        .heat-weight-tabs {
          gap:
            3px;

          padding:
            3px;
        }


        .heat-period-btn,
        .heat-weight-btn {
          padding:
            0 3px;

          font-size:
            10px;
        }


        .heat-benchmark-chip {
          font-size:
            8px;
        }

      }

    `;

    document.head.appendChild(
      style
    );
  }


  function refreshSoon() {
    requestAnimationFrame(
      () => {
        renderBenchmarks();
      }
    );
  }


  /* =========================================================
     啟動
  ========================================================= */

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        injectStyle();
        refreshSoon();
      },
      {
        once: true
      }
    );
  } else {
    injectStyle();
    refreshSoon();
  }


  /*
   * app.js 切換熱力圖期間時，
   * OTC / 大盤同步切換
   */

  window.addEventListener(
    "heatmap:period-changed",
    refreshSoon
  );


  window.addEventListener(
    "heatmap:weight-changed",
    refreshSoon
  );


  window.addEventListener(
    "heatmap:detail-rendered",
    refreshSoon
  );


  /*
   * 從背景切回網站時重新抓一次，
   * 避免手機 Safari 留著舊 benchmark
   */

  window.addEventListener(
    "focus",
    () => {
      detailCache = null;
      refreshSoon();
    }
  );

})();
