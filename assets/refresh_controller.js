/* =========================================================
   台股市場監測｜全站即時更新控制器｜效能版 2026-10-02
   ========================================================= */

(function () {
  "use strict";

  /*
   * iPhone Safari / PWA
   * 從背景回來時合併事件
   */
  const RESUME_DEBOUNCE = 700;

  /*
   * 同一頁短時間內
   * 不要重複 refresh
   */
  const MIN_REFRESH_GAP = 5000;

  /*
   * 不再全站每 60 秒重畫
   *
   * 熱力圖：
   * 使用者停留熱力圖頁面時
   * 每 5 分鐘做一次前端保底更新
   */
  const HEAT_FALLBACK_INTERVAL =
    5 * 60 * 1000;

  let lastRefreshAt = 0;

  let running = false;

  let resumeTimer = null;

  /* =========================================================
     基本工具
  ========================================================= */

  function getActivePage() {
    return (
      document.querySelector(
        ".page.active"
      )?.id ||
      "home"
    );
  }

  /*
   * 財報追蹤子分頁：
   *
   * self
   * upcoming
   * reports
   */
  function getEarningsMode() {
    const active =
      document.querySelector(
        "#earningsModeTabs [data-earnings-mode].active"
      );

    return (
      active?.dataset?.earningsMode ||
      "self"
    );
  }

  async function callFunction(
    name,
    ...args
  ) {
    const fn =
      window[name];

    if (
      typeof fn !==
      "function"
    ) {
      return false;
    }

    try {

      await fn(
        ...args
      );

      return true;

    } catch (error) {

      console.warn(
        "[Live Refresh] refresh failed:",
        name,
        error
      );

      return false;
    }
  }

  /*
   * 清除 app.js
   * 共用 JSON memory cache
   */
  function invalidate(path) {
    if (
      typeof window.invalidateJson ===
      "function"
    ) {
      window.invalidateJson(
        path
      );
    }
  }

  /* =========================================================
     首頁
  ========================================================= */

  async function refreshHome(
    force = true
  ) {

    /*
     * 真的需要重新整理時
     * 才清除相關 cache
     */
    if (force) {

      invalidate(
        "./data/heatmap.json"
      );

      invalidate(
        "./data/ai_picks.json"
      );

      invalidate(
        "./data/holders.json"
      );

      invalidate(
        "./data/self_reports.json"
      );

      invalidate(
        "./data/volume.json"
      );

      invalidate(
        "./data/monthly_revenue.json"
      );
    }

    await callFunction(
      "home",
      force
    );

    /*
     * Market Pulse
     *
     * 不再 remove 整塊 DOM
     * 避免首頁閃爍 / 重排
     *
     * buildMarketPulse()
     * 會直接更新原本區塊
     */
    await callFunction(
      "buildMarketPulse",
      force
    );

    /*
     * 首頁其他模組
     * 若有監聽這個事件
     * 可以自行更新
     */
    window.dispatchEvent(
      new CustomEvent(
        "tw-market:refresh-home"
      )
    );
  }

  /* =========================================================
     財報追蹤
  ========================================================= */

  async function refreshEarningsTracker(
    force = true
  ) {
    const mode =
      getEarningsMode();

    /*
     * 自結公布
     */
    if (
      mode ===
      "self"
    ) {

      if (force) {
        invalidate(
          "./data/self_reports.json"
        );
      }

      await callFunction(
        "selfReports",
        force
      );

      return;
    }

    /*
     * 即將開財報
     * 財報
     *
     * 不執行 selfReports()
     */
    if (
      mode === "upcoming" ||
      mode === "reports"
    ) {

      await callFunction(
        "refreshQuarterlyReports",
        force
      );

      return;
    }
  }

  /* =========================================================
     各分頁 Refresh
  ========================================================= */

  async function refreshPage(
    pageId,
    force = true
  ) {
    switch (pageId) {

      case "home":

        await refreshHome(
          force
        );

        break;

      case "heat":

        if (force) {
          invalidate(
            "./data/heatmap.json"
          );
        }

        await callFunction(
          "heat",
          force
        );

        window.dispatchEvent(
          new CustomEvent(
            "tw-market:refresh-heatmap"
          )
        );

        break;

      case "flows":

        if (force) {
          invalidate(
            "./data/institutional.json"
          );
        }

        await callFunction(
          "flows",
          force
        );

        break;

      case "volume":

        if (force) {

          invalidate(
            "./data/volume.json"
          );

          invalidate(
            "./data/screener.json"
          );
        }

        await callFunction(
          "volume",
          force
        );

        break;

      case "turnover":

        if (force) {
          invalidate(
            "./data/turnover.json"
          );
        }

        await callFunction(
          "turnover",
          force
        );

        break;

      case "marginLending":

        if (force) {
          invalidate(
            "./data/margin_lending.json"
          );
        }

        await callFunction(
          "marginLending",
          force
        );

        break;

      case "ai":

        if (force) {
          invalidate(
            "./data/ai_picks.json"
          );
        }

        await callFunction(
          "ai",
          force
        );

        break;

      case "holders":

        if (force) {
          invalidate(
            "./data/holders.json"
          );
        }

        await callFunction(
          "holders",
          force
        );

        break;

      /*
       * 財報追蹤
       */
      case "selfReports":

        await refreshEarningsTracker(
          force
        );

        break;

      case "monthlyRevenue":

        if (force) {
          invalidate(
            "./data/monthly_revenue.json"
          );
        }

        await callFunction(
          "monthlyRevenue",
          force
        );

        break;

      case "reports":

        if (force) {
          invalidate(
            "./data/reports.json"
          );
        }

        await callFunction(
          "reports",
          force
        );

        window.dispatchEvent(
          new CustomEvent(
            "tw-market:refresh-reports"
          )
        );

        break;

      default:

        break;
    }

    /*
     * 只更新目前頁面的
     * 更新時間資訊
     */
    await callFunction(
      "setupPageUpdateMeta",
      pageId
    );
  }

  /* =========================================================
     真正 Refresh
  ========================================================= */

  async function refreshNow(
    reason = "manual",
    force = false
  ) {

    /*
     * App 在背景
     * 完全不更新
     */
    if (
      document.hidden
    ) {
      return;
    }

    const now =
      Date.now();

    /*
     * 非手動強制更新：
     *
     * 5 秒內不允許
     * 同頁連續 refresh
     */
    if (
      !force &&
      now -
      lastRefreshAt <
      MIN_REFRESH_GAP
    ) {
      return;
    }

    /*
     * 已經有 refresh
     * 正在執行
     *
     * 不 queue 第二輪
     */
    if (
      running
    ) {
      return;
    }

    running = true;

    lastRefreshAt =
      now;

    const pageId =
      getActivePage();

    console.log(
      "[Live Refresh]",
      reason,
      "→",
      pageId
    );

    try {

      await refreshPage(
        pageId,
        force
      );

      window.dispatchEvent(
        new CustomEvent(
          "tw-market:refreshed",
          {
            detail: {
              reason,
              page:
                pageId,
              at:
                new Date()
                  .toISOString()
            }
          }
        )
      );

    } catch (error) {

      console.error(
        "[Live Refresh] error:",
        error
      );

    } finally {

      running = false;

    }
  }

  /* =========================================================
     Debounce
  ========================================================= */

  function scheduleRefresh(
    reason,
    force = false
  ) {

    if (
      resumeTimer
    ) {
      clearTimeout(
        resumeTimer
      );
    }

    resumeTimer =
      setTimeout(
        () => {

          resumeTimer =
            null;

          refreshNow(
            reason,
            force
          );

        },
        RESUME_DEBOUNCE
      );
  }

  /* =========================================================
     網站主頁切換
  ========================================================= */

  function bindPageChanges() {

    /*
     * 舊版：
     *
     * 每一個 .page
     * 都建立 MutationObserver
     *
     * 切頁後：
     * app.js lazy load 一次
     * refresh_controller 又 refresh 一次
     *
     * 造成重複 request / DOM render
     *
     *
     * 新版：
     *
     * app.js / ui_v2.js
     * 負責真正 Lazy Load
     *
     * controller 只補
     * setupPageUpdateMeta()
     */

    document.addEventListener(
      "click",
      e => {

        const btn =
          e.target.closest(
            `
              [data-p],
              [data-feature],
              [data-pulse-target]
            `
          );

        if (!btn) {
          return;
        }

        requestAnimationFrame(
          () => {

            const id =
              getActivePage();

            callFunction(
              "setupPageUpdateMeta",
              id
            );

          }
        );

      },
      {
        passive: true
      }
    );

    /*
     * 手機下拉選單
     */
    const mobile =
      document.getElementById(
        "mobileNav"
      );

    if (mobile) {

      mobile.addEventListener(
        "change",
        () => {

          requestAnimationFrame(
            () => {

              callFunction(
                "setupPageUpdateMeta",
                getActivePage()
              );

            }
          );

        },
        {
          passive: true
        }
      );
    }
  }

  /* =========================================================
     財報追蹤子 Tab
  ========================================================= */

  function bindEarningsTabs() {

    document.addEventListener(
      "click",
      e => {

        const btn =
          e.target.closest(
            "[data-earnings-mode]"
          );

        if (!btn) {
          return;
        }

        /*
         * 不在這裡重新 fetch
         *
         * earnings_tracker.js
         * 使用自己的 cache
         */

      },
      {
        passive: true
      }
    );
  }

  /* =========================================================
     Safari / iPhone / PWA
     從背景回到網站
  ========================================================= */

  function bindResumeEvents() {

    /*
     * visibilitychange
     *
     * 作為主要 resume 事件
     */
    document.addEventListener(
      "visibilitychange",
      () => {

        if (
          !document.hidden
        ) {

          scheduleRefresh(
            "visibilitychange",
            false
          );

        }

      }
    );

    /*
     * Safari BFCache
     */
    window.addEventListener(
      "pageshow",
      event => {

        if (
          event.persisted
        ) {

          scheduleRefresh(
            "pageshow-bfcache",
            false
          );

        }

      }
    );

    /*
     * 不監聽 focus
     *
     * 避免 iPhone：
     *
     * visibilitychange
     * +
     * pageshow
     * +
     * focus
     *
     * 三連發
     */

    /*
     * 網路恢復
     */
    window.addEventListener(
      "online",
      () => {

        scheduleRefresh(
          "online",
          false
        );

      }
    );
  }

  /* =========================================================
     熱力圖 5 分鐘保底更新
  ========================================================= */

  function startFallbackTimer() {

    /*
     * 舊版：
     *
     * 全站每 60 秒
     * refreshNow()
     *
     * 即使資料沒有變
     * 也重新 fetch + render
     *
     * 這是網站長時間開著
     * 越來越卡的重要原因之一
     *
     *
     * 新版：
     *
     * 只有停留在熱力圖頁面
     * 才每 5 分鐘做一次保底更新
     */

    setInterval(
      () => {

        if (
          document.hidden
        ) {
          return;
        }

        const pageId =
          getActivePage();

        if (
          pageId !==
          "heat"
        ) {
          return;
        }

        refreshNow(
          "5m-heat-fallback",
          true
        );

      },
      HEAT_FALLBACK_INTERVAL
    );
  }

  /* =========================================================
     外部模組要求 Refresh
  ========================================================= */

  function bindCustomRefresh() {

    window.addEventListener(
      "tw-market:refresh",
      () => {

        /*
         * 外部模組真的要求更新
         * 才 force
         */
        scheduleRefresh(
          "custom",
          true
        );

      }
    );
  }

  /* =========================================================
     手動 Refresh API
  ========================================================= */

  window.twMarketRefresh =
    function () {

      /*
       * 使用者真的手動要求更新
       *
       * 清 cache
       * 並重新抓目前頁
       */

      lastRefreshAt =
        0;

      return refreshNow(
        "manual",
        true
      );
    };

  /* =========================================================
     啟動
  ========================================================= */

  function boot() {

    bindPageChanges();

    bindEarningsTabs();

    bindResumeEvents();

    bindCustomRefresh();

    startFallbackTimer();

    console.log(
      "[Live Refresh] performance controller ready"
    );
  }

  if (
    document.readyState ===
    "loading"
  ) {

    document.addEventListener(
      "DOMContentLoaded",
      boot,
      {
        once: true
      }
    );

  } else {

    boot();

  }

})();
