(() => {
  "use strict";

  /*
   * heatmap_period.js
   *
   * 現在只負責：
   * 1. 當日 / 5日 / 10日 / 20日按鈕樣式
   * 2. 市值加權 / 權重上限按鈕樣式
   * 3. 大盤同期漲幅區塊樣式
   *
   * 熱力圖資料、期間、權重計算、排序
   * 全部由 app.js 統一處理
   *
   * 這支不再：
   * - fetch JSON
   * - 修改熱力圖數值
   * - MutationObserver 重畫
   * - 自己管理期間
   * - 自己管理權重
   */

  if (window.__heatmapPeriodStyleOnlyLoaded) {
    return;
  }

  window.__heatmapPeriodStyleOnlyLoaded = true;
  window.__heatmapPeriodManaged = true;

  const STYLE_ID = "heatmap-period-style";

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement("style");

    style.id = STYLE_ID;

    style.textContent = `

      /* =========================================================
         熱力圖控制區
      ========================================================= */

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


      /* =========================================================
         期間按鈕
         當日 / 5日 / 10日 / 20日
      ========================================================= */

      .heat-period-tabs {
        display: inline-flex;
        align-items: center;
        gap: 6px;

        padding: 4px;

        border:
          1px solid
          var(--line);

        border-radius: 12px;

        background:
          var(--card);

        box-sizing:
          border-box;
      }


      /* =========================================================
         權重模式按鈕
         市值加權 / 權重上限
      ========================================================= */

      .heat-weight-tabs {
        display: inline-flex;
        align-items: center;
        gap: 6px;

        padding: 4px;

        border:
          1px solid
          var(--line);

        border-radius: 12px;

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
        appearance: none;
        -webkit-appearance: none;

        border: 0;
        outline: 0;

        cursor: pointer;

        height: 34px;

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
        min-width: 54px;
      }


      .heat-weight-btn {
        min-width: 82px;
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
         說明 + 大盤漲幅
      ========================================================= */

      .heat-period-meta {
        display: flex;
        align-items: center;
        justify-content: space-between;

        gap: 12px;

        flex-wrap: wrap;

        width: 100%;
        min-width: 0;

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
        min-width: 0;
        flex: 1 1 auto;
      }


      .heat-period-benchmark {
        display: inline-flex;
        align-items: center;

        gap: 5px;

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


      .heat-period-benchmark strong {
        font-size:
          11px;

        font-weight:
          900;
      }


      /*
       * 台股：
       * 紅漲綠跌
       */

      .heat-period-benchmark .up {
        color:
          #dc2626;
      }


      .heat-period-benchmark .down {
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
      .heat-period-benchmark {
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
          gap: 8px;

          margin-bottom:
            12px;
        }


        /*
         * 手機改成兩排：
         *
         * 第一排
         * 當日 5日 10日 20日
         *
         * 第二排
         * 市值加權 權重上限
         */

        .heat-control-row {
          display: grid;

          grid-template-columns:
            minmax(0, 1fr);

          gap: 8px;

          width: 100%;
        }


        .heat-period-tabs {
          display: grid;

          grid-template-columns:
            repeat(
              4,
              minmax(0, 1fr)
            );

          gap: 5px;

          width: 100%;

          box-sizing:
            border-box;
        }


        .heat-weight-tabs {
          display: grid;

          grid-template-columns:
            repeat(
              2,
              minmax(0, 1fr)
            );

          gap: 5px;

          width: 100%;

          box-sizing:
            border-box;
        }


        .heat-period-btn,
        .heat-weight-btn {
          width: 100%;

          min-width: 0;

          padding:
            0 6px;
        }


        .heat-period-meta {
          width: 100%;

          gap: 8px;

          align-items:
            center;
        }


        #heatWeightDescription {
          flex:
            1 1 160px;

          min-width: 0;
        }


        .heat-period-benchmark {
          flex:
            0 0 auto;
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


        .heat-period-benchmark {
          padding:
            5px 7px;
        }


        .heat-period-benchmark strong {
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

        .heat-period-tabs {
          gap:
            3px;

          padding:
            3px;
        }


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

      }

    `;

    document.head.appendChild(
      style
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
      injectStyle,
      {
        once: true
      }
    );
  } else {
    injectStyle();
  }

})();
