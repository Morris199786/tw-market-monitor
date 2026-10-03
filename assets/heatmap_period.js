(() => {
  "use strict";

  /*
   * heatmap_period.js
   *
   * 熱力圖期間的資料計算、排序、展開與切換，
   * 現在全部由 app.js 統一管理
   *
   * 這支檔案只保留期間選擇器的樣式，
   * 不再：
   * - fetch heatmap.json
   * - fetch stock_detail.json
   * - 修改族群漲跌幅
   * - 修改個股漲跌幅
   * - 重排 heatGrid
   * - 使用 MutationObserver
   *
   * 避免與 app.js 同時 render，
   * 解決：
   * 10日 → 點族群 → 瞬間變當日 → 再變10日
   * 的數字跳動問題
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
      .heat-period-wrap {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 14px;
        flex-wrap: wrap;
        margin: 0 0 14px;
      }

      .heat-period-tabs {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px;
        border: 1px solid var(--line);
        border-radius: 12px;
        background: var(--card);
      }

      .heat-period-btn {
        appearance: none;
        -webkit-appearance: none;
        border: 0;
        outline: 0;
        cursor: pointer;

        min-width: 54px;
        height: 34px;
        padding: 0 13px;

        border-radius: 9px;

        background: transparent;
        color: var(--muted);

        font-size: 12px;
        font-weight: 800;
        line-height: 34px;
        text-align: center;

        transition:
          background .15s ease,
          color .15s ease,
          box-shadow .15s ease,
          transform .15s ease;
      }

      .heat-period-btn:hover {
        color: var(--ink);
      }

      .heat-period-btn:active {
        transform: scale(.97);
      }

      .heat-period-btn.active {
        background: var(--ink);
        color: var(--card);
        box-shadow:
          0 2px 8px
          rgba(15, 23, 42, .12);
      }

      .heat-period-meta {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 12px;
        flex-wrap: wrap;

        min-width: 0;

        color: var(--muted);
        font-size: 10px;
        line-height: 1.5;
      }

      .heat-period-benchmark {
        display: inline-flex;
        align-items: center;
        gap: 5px;

        padding: 6px 9px;

        border: 1px solid var(--line);
        border-radius: 8px;

        background: var(--card);

        white-space: nowrap;
      }

      .heat-period-benchmark strong {
        font-size: 11px;
        font-weight: 900;
      }

      .heat-period-benchmark .up {
        color: #dc2626;
      }

      .heat-period-benchmark .down {
        color: #15803d;
      }

      [data-theme="dark"] .heat-period-btn.active {
        background: #f8fafc;
        color: #0f172a;
      }

      [data-theme="dark"] .heat-period-tabs,
      [data-theme="dark"] .heat-period-benchmark {
        background: var(--card);
      }

      @media (max-width: 720px) {
        .heat-period-wrap {
          display: block;
          margin-bottom: 12px;
        }

        .heat-period-tabs {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          width: 100%;
          box-sizing: border-box;
        }

        .heat-period-btn {
          width: 100%;
          min-width: 0;
          padding: 0 6px;
        }

        .heat-period-meta {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;

          width: 100%;
          margin-top: 8px;
        }

        .heat-period-meta > span:first-child {
          flex: 1 1 auto;
          min-width: 0;
        }

        .heat-period-benchmark {
          flex: 0 0 auto;
        }
      }

      @media (max-width: 430px) {
        .heat-period-btn {
          height: 32px;
          line-height: 32px;
          font-size: 11px;
        }

        .heat-period-meta {
          font-size: 9px;
        }

        .heat-period-benchmark {
          padding: 5px 7px;
        }

        .heat-period-benchmark strong {
          font-size: 10px;
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
