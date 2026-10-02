/* =========================================================
   台股市場監測｜全站即時更新控制器 V2
   ========================================================= */

(function () {
  "use strict";

  const FALLBACK_INTERVAL = 60 * 1000;
  const RESUME_DEBOUNCE = 350;
  const MIN_REFRESH_GAP = 1500;

  let lastRefreshAt = 0;
  let running = false;
  let queued = false;
  let resumeTimer = null;

  function getActivePage() {
    return (
      document.querySelector(".page.active")?.id ||
      "home"
    );
  }

  async function callFunction(name, ...args) {
    const fn = window[name];

    if (typeof fn !== "function") {
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

  async function refreshHome() {
    await callFunction("home");

    /*
      Market Pulse 原本建立後不會自己更新
      所以刷新首頁時重新建立
    */

    const oldPulse =
      document.getElementById("marketPulse");

    if (oldPulse) {
      oldPulse.remove();
    }

    await callFunction("buildMarketPulse");

    /*
      首頁券商報告數量也同步刷新
    */

    window.dispatchEvent(
      new CustomEvent(
        "tw-market:refresh-home"
      )
    );
  }

  async function refreshPage(pageId) {
    switch (pageId) {
      case "home":
        await refreshHome();
        break;

      case "heat":
        await callFunction("heat");

        /*
          通知熱力圖附加模組
        */

        window.dispatchEvent(
          new CustomEvent(
            "tw-market:refresh-heatmap"
          )
        );
        break;

      case "flows":
        await callFunction("flows");
        break;

      case "volume":
        await callFunction("volume");
        break;

      case "turnover":
        await callFunction("turnover");
        break;

      case "marginLending":
        await callFunction("marginLending");
        break;

      case "ai":
        await callFunction("ai");
        break;

      case "holders":
        await callFunction("holders");
        break;

      case "selfReports":
        await callFunction("selfReports");
        break;

      case "monthlyRevenue":
        await callFunction("monthlyRevenue");
        break;

      case "reports":
        /*
          reports_v2.js + tw_ratings.js
          由這個事件重新抓資料
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
      只更新目前頁面的「最後更新」
      不要每次切頁又把全站 JSON 抓一輪
    */

    await callFunction(
      "setupPageUpdateMeta",
      pageId
    );
  }

  async function refreshNow(
    reason = "manual",
    force = false
  ) {
    if (document.hidden) {
      return;
    }

    const now = Date.now();

    if (
      !force &&
      now - lastRefreshAt < MIN_REFRESH_GAP
    ) {
      return;
    }

    if (running) {
      queued = true;
      return;
    }

    running = true;
    lastRefreshAt = now;

    const pageId = getActivePage();

    console.log(
      "[Live Refresh]",
      reason,
      "→",
      pageId
    );

    try {
      await refreshPage(pageId);

      window.dispatchEvent(
        new CustomEvent(
          "tw-market:refreshed",
          {
            detail: {
              reason,
              page: pageId,
              at: new Date().toISOString()
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

      if (queued) {
        queued = false;

        setTimeout(
          () => {
            refreshNow(
              "queued",
              true
            );
          },
          150
        );
      }
    }
  }

  function scheduleRefresh(
    reason,
    force = true
  ) {
    if (resumeTimer) {
      clearTimeout(resumeTimer);
    }

    resumeTimer = setTimeout(
      () => {
        refreshNow(
          reason,
          force
        );
      },
      RESUME_DEBOUNCE
    );
  }

  /*
    偵測網站內切換頁面
  */

  function bindPageChanges() {
    document
      .querySelectorAll(".page")
      .forEach(page => {
        let wasActive =
          page.classList.contains("active");

        const observer =
          new MutationObserver(() => {
            const isActive =
              page.classList.contains("active");

            if (
              isActive &&
              !wasActive
            ) {
              scheduleRefresh(
                "page-change",
                true
              );
            }

            wasActive = isActive;
          });

        observer.observe(
          page,
          {
            attributes: true,
            attributeFilter: ["class"]
          }
        );
      });
  }

  /*
    iPhone / Safari / PWA
    從其他 App 回來時立即更新
  */

  function bindResumeEvents() {
    document.addEventListener(
      "visibilitychange",
      () => {
        if (!document.hidden) {
          scheduleRefresh(
            "visibilitychange",
            true
          );
        }
      }
    );

    window.addEventListener(
      "pageshow",
      () => {
        scheduleRefresh(
          "pageshow",
          true
        );
      }
    );

    window.addEventListener(
      "focus",
      () => {
        scheduleRefresh(
          "focus",
          true
        );
      }
    );

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

  /*
    使用者一直停留在同一頁
    每 60 秒保底檢查
  */

  function startFallbackTimer() {
    setInterval(
      () => {
        if (document.hidden) {
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

  /*
    其他模組可以主動要求刷新
  */

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
    Console / 其他 JS
    可直接呼叫
    window.refreshMarketNow()
  */

  window.refreshMarketNow =
    function () {
      return refreshNow(
        "manual",
        true
      );
    };

  function init() {
    bindResumeEvents();
    bindPageChanges();
    startFallbackTimer();

    /*
      第一次開網站
      也重新確認目前頁面資料
    */

    scheduleRefresh(
      "controller-init",
      true
    );

    console.log(
      "[Live Refresh V2] controller ready"
    );
  }

  if (
    document.readyState === "loading"
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
