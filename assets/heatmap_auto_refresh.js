/* =========================================================
   Heatmap Auto Refresh
   2026-10-01

   功能：
   1. 每 60 秒檢查 heatmap.json
   2. updated_at 改變才更新熱力圖
   3. iPhone / Safari 從背景切回時立即檢查
   4. 回到 Heatmap 分頁時立即檢查
   5. 不重新整理整個網頁
   6. 不碰 app.js
   ========================================================= */

(function () {
  const CHECK_INTERVAL = 60 * 1000;

  let lastUpdatedAt = null;
  let checking = false;
  let timer = null;

  function heatmapVisible() {
    const page = document.getElementById("heat");

    if (!page) {
      return false;
    }

    return page.classList.contains("active");
  }

  async function fetchHeatmap() {
    const response = await fetch(
      "./data/heatmap.json?v=" + Date.now(),
      {
        cache: "no-store"
      }
    );

    if (!response.ok) {
      throw new Error(
        "heatmap.json HTTP " +
        response.status
      );
    }

    return await response.json();
  }

  function getUpdatedAt(data) {
    return (
      data?.updated_at ||
      data?.updatedAt ||
      data?.date ||
      null
    );
  }

  async function refreshHeatmap() {
    /*
      使用 app.js 原本的 heat()
      重新抓資料並重畫 Heatmap

      不 reload 整個網頁
    */

    if (typeof window.heat === "function") {
      await window.heat();
      return true;
    }

    /*
      app.js 的 function heat() 在一般 script
      環境通常可直接存取
    */

    if (typeof heat === "function") {
      await heat();
      return true;
    }

    console.warn(
      "heatmap auto refresh: heat() not found"
    );

    return false;
  }

  async function checkForUpdate(force = false) {
    if (checking) {
      return;
    }

    /*
      一般 60 秒輪詢只在 Heatmap 畫面執行

      force=true：
      Safari 回到前景、pageshow 等情況
      即使剛切回來也立即檢查
    */

    if (
      !force &&
      !heatmapVisible()
    ) {
      return;
    }

    checking = true;

    try {
      const data =
        await fetchHeatmap();

      const updatedAt =
        getUpdatedAt(data);

      if (!updatedAt) {
        console.warn(
          "heatmap auto refresh: updated_at missing"
        );

        return;
      }

      /*
        第一次只記錄版本
        不做多餘 refresh
      */

      if (lastUpdatedAt === null) {
        lastUpdatedAt = updatedAt;

        console.log(
          "heatmap auto refresh initialized:",
          updatedAt
        );

        return;
      }

      /*
        資料沒有改變
      */

      if (
        String(updatedAt) ===
        String(lastUpdatedAt)
      ) {
        return;
      }

      console.log(
        "New heatmap detected:",
        lastUpdatedAt,
        "→",
        updatedAt
      );

      /*
        先記錄新版時間
        避免重複觸發
      */

      lastUpdatedAt = updatedAt;

      const refreshed =
        await refreshHeatmap();

      if (refreshed) {
        /*
          25% 權重插件使用 MutationObserver
          heat() 重畫 DOM 後會自行重新套用

          這裡另外送事件，
          讓其他獨立插件未來也可以監聽
        */

        window.dispatchEvent(
          new CustomEvent(
            "heatmap:data-updated",
            {
              detail: {
                updated_at: updatedAt
              }
            }
          )
        );
      }

    } catch (error) {
      console.error(
        "heatmap auto refresh failed:",
        error
      );

    } finally {
      checking = false;
    }
  }

  function startTimer() {
    if (timer) {
      clearInterval(timer);
    }

    timer = setInterval(
      function () {
        /*
          Safari 在背景時不浪費 request
        */

        if (document.hidden) {
          return;
        }

        checkForUpdate(false);
      },
      CHECK_INTERVAL
    );
  }

  function bindVisibilityEvents() {
    /*
      iPhone Safari：
      從背景切回網站
    */

    document.addEventListener(
      "visibilitychange",
      function () {
        if (!document.hidden) {
          checkForUpdate(true);
        }
      }
    );

    /*
      Safari BFCache：
      返回上一頁時可能不重新載入 JS
    */

    window.addEventListener(
      "pageshow",
      function () {
        checkForUpdate(true);
      }
    );

    /*
      電腦瀏覽器重新 focus
    */

    window.addEventListener(
      "focus",
      function () {
        checkForUpdate(true);
      }
    );
  }

  function bindHeatmapNavigation() {
    /*
      監聽網站 page class 變化

      使用者從其他分頁切到市場熱力圖時
      立即檢查資料
    */

    const heatPage =
      document.getElementById("heat");

    if (!heatPage) {
      return;
    }

    const observer =
      new MutationObserver(
        function () {
          if (
            heatPage.classList.contains(
              "active"
            )
          ) {
            checkForUpdate(true);
          }
        }
      );

    observer.observe(
      heatPage,
      {
        attributes: true,
        attributeFilter: [
          "class"
        ]
      }
    );
  }

  async function init() {
    /*
      先讀目前 heatmap 版本
    */

    try {
      const data =
        await fetchHeatmap();

      lastUpdatedAt =
        getUpdatedAt(data);

      console.log(
        "heatmap auto refresh ready:",
        lastUpdatedAt
      );

    } catch (error) {
      console.error(
        "heatmap auto refresh init failed:",
        error
      );
    }

    bindVisibilityEvents();

    bindHeatmapNavigation();

    startTimer();
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      init
    );

  } else {
    init();
  }
})();
