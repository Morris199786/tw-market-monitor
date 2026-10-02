/* =========================================================
   台股市場監測｜全站即時更新控制器 V1
   ---------------------------------------------------------
   目的：
   1. iPhone 主畫面 App 從背景回到前景 → 立即更新
   2. Safari / PWA pageshow 恢復 → 立即更新
   3. window focus → 立即更新
   4. 網站內切換分頁 → 立即更新該頁
   5. 一直停留在同一頁 → 每 60 秒保底更新
   6. 不重新整理整個網頁，不影響目前操作位置
   ========================================================= */

(function () {
  "use strict";

  const FALLBACK_INTERVAL = 60 * 1000;
  const RESUME_DEBOUNCE = 500;
  const MIN_REFRESH_GAP = 1000;

  let lastRefreshAt = 0;
  let running = false;
  let queued = false;
  let resumeTimer = null;

  /* =========================================================
     目前正在看的分頁
     ========================================================= */

  function getActivePage() {
    return (
      document.querySelector(
        ".page.active"
      )?.id || "home"
    );
  }

  /* =========================================================
     安全呼叫既有更新函式
     ========================================================= */

  async function callFunction(name) {
    const fn = window[name];

    if (typeof fn !== "function") {
      return false;
    }

    try {
      await fn();
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
    /*
      app.js 的首頁資料
      包含：
      - 最強族群
      - 強勢族群
      - AI 選股數量
      - 大戶資料狀態
    */

    await callFunction("home");

    /*
      ui_v2.js 的新版市場快照

      原本 buildMarketPulse() 發現
      #marketPulse 已存在就會直接 return。

      因此刷新前先移除舊的，
      再重新建立最新市場快照。
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
  }

  /* =========================================================
     依目前頁面刷新
     ========================================================= */

  async function refreshPage(
    pageId
  ) {
    switch (pageId) {
      case "home":
        await refreshHome();
        break;

      case "heat":
        /*
          熱力圖本身另外還有
          heatmap_auto_refresh.js。

          這裡再呼叫一次 heat()
          是為了確保切回 App 時
          畫面一定是最新資料。
        */
        await callFunction("heat");
        break;

      case "flows":
        await callFunction("flows");
        break;

      case "volume":
        await callFunction("volume");
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
        await callFunction("ai");
        break;

      case "holders":
        await callFunction(
          "holders"
        );
        break;

      case "selfReports":
        await callFunction(
          "selfReports"
        );
        break;

      case "monthlyRevenue":
        await callFunction(
          "monthlyRevenue"
        );
        break;

      case "reports":
        /*
          券商報告與台股評等
          是獨立 JS 模組。

          用事件通知它們重新抓資料。
        */

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
      頁面上的資料更新時間
      如果 ui_v2.js 有此函式，
      一併重新整理。
    */

    await callFunction(
      "setupPageUpdateMeta"
    );
  }

  /* =========================================================
     執行刷新
     ========================================================= */

  async function refreshNow(
    reason = "manual",
    force = false
  ) {
    /*
      App 在背景時不要浪費請求。
    */

    if (document.hidden) {
      return;
    }

    const now = Date.now();

    /*
      visibilitychange、focus、pageshow
      在 iPhone 上可能幾乎同時觸發。

      避免同一秒連續抓 3 次資料。
    */

    if (
      !force &&
      now - lastRefreshAt <
        MIN_REFRESH_GAP
    ) {
      return;
    }

    /*
      前一輪還在抓資料時，
      不同時再開第二輪。

      記錄 queued，
      前一輪完成後再補一次。
    */

    if (running) {
      queued = true;
      return;
    }

    running = true;
    lastRefreshAt = now;

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

      /*
        讓其他模組知道
        這次更新已經完成。
      */

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

      /*
        更新期間如果又收到
        回前景 / focus 等事件，
        補做一次即可。
      */

      if (queued) {
        queued = false;

        setTimeout(
          () => {
            refreshNow(
              "queued",
              true
            );
          },
          120
        );
      }
    }
  }

  /* =========================================================
     合併 iPhone 同時觸發的事件
     ========================================================= */

  function scheduleRefresh(
    reason,
    force = true
  ) {
    if (resumeTimer) {
      clearTimeout(
        resumeTimer
      );
    }

    resumeTimer =
      setTimeout(
        () => {
          refreshNow(
            reason,
            force
          );
        },
        RESUME_DEBOUNCE
      );
  }

  /* =========================================================
     偵測網站內切換分頁
     ========================================================= */

  function bindPageChanges() {
    const pages =
      document.querySelectorAll(
        ".page"
      );

    pages.forEach(page => {
      const observer =
        new MutationObserver(
          mutations => {
            const becameActive =
              mutations.some(
                mutation =>
                  mutation
                    .attributeName ===
                    "class" &&
                  page.classList
                    .contains(
                      "active"
                    )
              );

            if (
              becameActive
            ) {
              scheduleRefresh(
                "page-change",
                true
              );
            }
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
     iPhone / PWA 回前景
     ========================================================= */

  function bindResumeEvents() {
    /*
      最重要：
      從 Telegram / LINE / Safari /
      其他 App 回到台股 App。
    */

    document.addEventListener(
      "visibilitychange",
      () => {
        if (
          !document.hidden
        ) {
          scheduleRefresh(
            "visibilitychange",
            true
          );
        }
      }
    );

    /*
      iOS Safari / 主畫面 App
      從 BFCache 恢復。
    */

    window.addEventListener(
      "pageshow",
      () => {
        scheduleRefresh(
          "pageshow",
          true
        );
      }
    );

    /*
      App / 視窗重新取得焦點。
    */

    window.addEventListener(
      "focus",
      () => {
        scheduleRefresh(
          "focus",
          true
        );
      }
    );

    /*
      網路斷線後恢復。
    */

    window.addEventListener(
      "online",
      () => {
        scheduleRefresh(
          "online",
          true
        );
      }
    );
  }

  /* =========================================================
     60 秒保底
     ========================================================= */

  function startFallbackTimer() {
    setInterval(
      () => {
        /*
          App 在背景不抓。

          只有使用者真的停留在
          台股 App 前景時才執行。
        */

        if (
          document.hidden
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
     允許其他程式手動要求更新
     ========================================================= */

  window.addEventListener(
    "tw-market:refresh",
    () => {
      scheduleRefresh(
        "custom",
        true
      );
    }
  );

  /*
    也提供一個全域函式，
    方便之後除錯或其他 JS 使用。

    可直接：
    window.refreshMarketNow()
  */

  window.refreshMarketNow =
    function () {
      return refreshNow(
        "manual",
        true
      );
    };

  /* =========================================================
     啟動
     ========================================================= */

  function init() {
    bindResumeEvents();
    bindPageChanges();
    startFallbackTimer();

    /*
      第一次開啟網站也抓一次，
      避免 PWA 從舊頁面狀態恢復。
    */

    scheduleRefresh(
      "controller-init",
      true
    );

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
      init,
      {
        once: true
      }
    );
  } else {
    init();
  }
})();
