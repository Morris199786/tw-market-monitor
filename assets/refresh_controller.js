/* =========================================================
   台股市場監測｜全站即時更新控制器
   ========================================================= */

(function () {
  "use strict";

  const FALLBACK_INTERVAL = 60 * 1000;

  /*
   * iPhone Safari / PWA 從背景回來時，
   * visibilitychange、pageshow、focus
   * 很可能連續一起觸發
   *
   * 拉長 debounce，合併成一次 refresh
   */
  const RESUME_DEBOUNCE = 700;

  /*
   * 同一頁短時間內不要一直刷新
   */
  const MIN_REFRESH_GAP = 5000;

  let lastRefreshAt = 0;
  let running = false;
  let queued = false;
  let resumeTimer = null;

  /* =========================================================
     基本工具
  ========================================================= */

  function getActivePage() {
    return (
      document.querySelector(".page.active")?.id ||
      "home"
    );
  }

  /*
   * 財報追蹤裡面有三個子分頁：
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
      typeof fn !== "function"
    ) {
      return false;
    }

    try {
      await fn(...args);

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

  /* =========================================================
     首頁
  ========================================================= */

  async function refreshHome() {
    await callFunction(
      "home"
    );

    /*
     * Market Pulse
     */

    const oldPulse =
      document.getElementById(
        "marketPulse"
      );

    if (oldPulse) {
      oldPulse.remove();
    }

    await callFunction(
      "buildMarketPulse"
    );

    /*
     * 首頁券商報告數量
     */

    window.dispatchEvent(
      new CustomEvent(
        "tw-market:refresh-home"
      )
    );
  }

  /* =========================================================
     財報追蹤

     這裡是這次最重要的修正
  ========================================================= */

  async function refreshEarningsTracker() {
    const mode =
      getEarningsMode();

    console.log(
      "[Live Refresh] earnings mode →",
      mode
    );

    /*
     * 自結公布
     *
     * 只有真的停在「自結公布」
     * 才允許執行 selfReports()
     */
    if (
      mode === "self"
    ) {
      await callFunction(
        "selfReports"
      );

      return;
    }

    /*
     * 即將開財報
     * 財報
     *
     * 不准執行 selfReports()
     *
     * 只更新 quarterly earnings
     */
    if (
      mode === "upcoming" ||
      mode === "reports"
    ) {
      await callFunction(
        "refreshQuarterlyReports"
      );

      return;
    }
  }

  /* =========================================================
     各頁 Refresh
  ========================================================= */

  async function refreshPage(
    pageId
  ) {
    switch (pageId) {

      case "home":

        await refreshHome();

        break;

      case "heat":

        await callFunction(
          "heat"
        );

        window.dispatchEvent(
          new CustomEvent(
            "tw-market:refresh-heatmap"
          )
        );

        break;

      case "flows":

        await callFunction(
          "flows"
        );

        break;

      case "volume":

        await callFunction(
          "volume"
        );

        break;

      case "turnover":

        await callFunction(
          "turnover"
        );

        break;

      case "marginLending":

        await callFunction(
          "marginLending"
        );

        break;

      case "ai":

        await callFunction(
          "ai"
        );

        break;

      case "holders":

        await callFunction(
          "holders"
        );

        break;

      /*
       * 財報追蹤
       */
      case "selfReports":

        await refreshEarningsTracker();

        break;

      case "monthlyRevenue":

        await callFunction(
          "monthlyRevenue"
        );

        break;

      case "reports":

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
     * 更新目前頁面
     * 最後更新時間
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
     * 即使 force
     *
     * iPhone 回前景時，
     * 5 秒內仍只允許刷新一次
     *
     * 避免：
     *
     * pageshow
     * visibilitychange
     * focus
     *
     * 三連發
     */
    if (
      now -
      lastRefreshAt <
      MIN_REFRESH_GAP
    ) {
      return;
    }

    /*
     * 已經有 refresh 在跑
     *
     * 不再 queue 第二輪
     *
     * 這是另一個卡頓來源
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
        pageId
      );

      window.dispatchEvent(
        new CustomEvent(
          "tw-market:refreshed",
          {
            detail: {
              reason,
              page: pageId,
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
      queued = false;

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
    document
      .querySelectorAll(
        ".page"
      )
      .forEach(page => {

        let wasActive =
          page.classList.contains(
            "active"
          );

        const observer =
          new MutationObserver(
            () => {

              const isActive =
                page.classList.contains(
                  "active"
                );

              if (
                isActive &&
                !wasActive
              ) {
                scheduleRefresh(
                  "page-change",
                  false
                );
              }

              wasActive =
                isActive;
            }
          );

        observer.observe(
          page,
          {
            attributes: true,
            attributeFilter: [
              "class"
            ]
          }
        );
      });
  }

  /* =========================================================
     財報追蹤子 Tab

     自結 / 即將開財報 / 財報
     切換時不做網路 refresh

     earnings_tracker.js 已有 cache
     所以只讓它自己瞬間切畫面
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
         * 很重要：
         *
         * 不在這裡 refresh
         *
         * earnings_tracker.js
         * 自己會從 cache render
         */
        console.log(
          "[Live Refresh] earnings tab →",
          btn.dataset.earningsMode
        );

      },
      {
        passive: true
      }
    );
  }

  /* =========================================================
     Safari / iPhone / PWA
     回到網站
  ========================================================= */

  function bindResumeEvents() {

    /*
     * visibilitychange
     *
     * 這個當主要事件
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
     * pageshow
     *
     * Safari BFCache 才需要
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
     * 不再監聽 focus
     *
     * 原本 iPhone 很容易：
     *
     * visibilitychange
     * +
     * pageshow
     * +
     * focus
     *
     * 一次觸發三輪
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
     60 秒保底刷新

     財報 / 即將開財報：
     不需要每分鐘抓一次

     自結：
     原本資料源本身 30 分鐘更新，
     網頁沒必要每 60 秒重畫
  ========================================================= */

  function startFallbackTimer() {

    setInterval(
      () => {

        if (
          document.hidden
        ) {
          return;
        }

        const pageId =
          getActivePage();

        /*
         * 財報追蹤整頁
         *
         * 不跑 60 秒 fallback
         *
         * 避免閱讀財報時
         * 背景突然重畫
         */
        if (
          pageId ===
          "selfReports"
        ) {
          return;
        }

        refreshNow(
          "60s-fallback",
          false
        );

      },
      FALLBACK_INTERVAL
    );
  }

  /* =========================================================
     外部模組要求 Refresh
  ========================================================= */

  function bindCustomRefresh() {

    window.addEventListener(
      "tw-market:refresh",
      () => {

        scheduleRefresh(
          "custom",
          false
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
       * 使用者真的手動要求更新時
       * 才直接執行
       */

      lastRefreshAt = 0;

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
      "[Live Refresh] controller ready"
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
