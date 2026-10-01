/* =========================================================
   Heatmap Auto Refresh + 近5日族群強勢股標記
   2026-10-01

   功能：
   1. 每 60 秒檢查 heatmap.json
   2. updated_at 改變才更新熱力圖
   3. iPhone / Safari 從背景切回時立即檢查
   4. 回到 Heatmap 分頁時立即檢查
   5. 不重新整理整個網頁
   6. 每個族群依 stock_detail.json 的最新近5日累積報酬重新排名
   7. 每個族群前 2 強個股自動標示淡金色
   8. 金色名單隨近5日滾動資料自動更新，不寫死股票
   9. 網頁自動顯示「金色＝族群近5日漲幅前2強」
   10. 不碰 app.js
   ========================================================= */

(function () {
  const CHECK_INTERVAL = 60 * 1000;
  const TOP_COUNT = 2;

  let lastUpdatedAt = null;
  let checking = false;
  let timer = null;

  let strengthTimer = null;
  let strengthObserver = null;
  let strengthApplying = false;

  function heatmapVisible() {
    const page =
      document.getElementById("heat");

    if (!page) {
      return false;
    }

    return page.classList.contains(
      "active"
    );
  }

  async function fetchHeatmap() {
    const response = await fetch(
      "./data/heatmap.json?v=" +
        Date.now(),
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

  async function fetchStockDetail() {
    const response = await fetch(
      "./data/stock_detail.json?v=" +
        Date.now(),
      {
        cache: "no-store"
      }
    );

    if (!response.ok) {
      throw new Error(
        "stock_detail.json HTTP " +
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

  function latestValidNumber(values) {
    const arr =
      Array.isArray(values)
        ? values
        : [];

    for (
      let i = arr.length - 1;
      i >= 0;
      i -= 1
    ) {
      const value =
        Number(arr[i]);

      if (
        Number.isFinite(value)
      ) {
        return value;
      }
    }

    return null;
  }

  function tickerFromRow(row) {
    return (
      row
        ?.querySelector(".t")
        ?.textContent
        ?.trim() ||
      ""
    );
  }

  function sectorFromDetail(detail) {
    if (!detail) {
      return "";
    }

    const prev =
      detail.previousElementSibling;

    if (
      prev?.matches?.(
        "button.heat[data-sec]"
      )
    ) {
      return (
        prev.dataset.sec ||
        ""
      );
    }

    const head =
      detail.querySelector(
        ".heat-detail-head b"
      );

    if (!head) {
      return "";
    }

    return (
      [...head.childNodes]
        .filter(
          node =>
            node.nodeType ===
            Node.TEXT_NODE
        )
        .map(
          node =>
            node.textContent
        )
        .join(" ")
        .trim()
    );
  }

  /* =========================================================
     金色強勢股樣式
     ========================================================= */

  function injectStrengthStyles() {
    if (
      document.getElementById(
        "heatStrengthStyle"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "heatStrengthStyle";

    style.textContent = `
      .heat-strength-note{
        display:flex;
        align-items:center;
        gap:8px;
        width:max-content;
        max-width:100%;
        margin:0 0 12px;
        padding:7px 10px;
        border:1px solid rgba(202,138,4,.26);
        border-radius:10px;
        background:rgba(254,243,199,.56);
        color:#765314;
        font-size:10px;
        font-weight:800;
        line-height:1.35
      }

      .heat-strength-swatch{
        width:11px;
        height:11px;
        flex:0 0 11px;
        border:1px solid rgba(202,138,4,.42);
        border-radius:4px;
        background:linear-gradient(
          180deg,
          rgba(253,230,138,.92),
          rgba(254,243,199,.92)
        )
      }

      #heatGrid
      .heat-stock.heat-stock-top2{
        position:relative;
        border-color:
          rgba(202,138,4,.42)
          !important;

        background:
          linear-gradient(
            135deg,
            rgba(254,243,199,.88),
            rgba(253,230,138,.58)
          )
          !important;

        box-shadow:
          inset 0 0 0 1px
            rgba(245,158,11,.08),
          0 4px 12px
            rgba(161,98,7,.08)
      }

      #heatGrid
      .heat-stock.heat-stock-top2::after{
        content:"5日強勢";
        position:absolute;
        top:6px;
        right:7px;
        padding:2px 5px;
        border:1px solid
          rgba(180,83,9,.22);
        border-radius:999px;
        background:
          rgba(255,251,235,.90);
        color:#92400e;
        font-size:8px;
        font-weight:900;
        line-height:1.2;
        letter-spacing:.02em;
        pointer-events:none
      }

      html[data-theme="dark"]
      .heat-strength-note{
        border-color:
          rgba(234,179,8,.30);
        background:
          rgba(113,63,18,.26);
        color:#fde68a
      }

      html[data-theme="dark"]
      .heat-strength-swatch{
        border-color:
          rgba(250,204,21,.42);

        background:
          linear-gradient(
            180deg,
            rgba(161,98,7,.72),
            rgba(113,63,18,.72)
          )
      }

      html[data-theme="dark"]
      #heatGrid
      .heat-stock.heat-stock-top2{
        border-color:
          rgba(250,204,21,.42)
          !important;

        background:
          linear-gradient(
            135deg,
            rgba(113,63,18,.62),
            rgba(146,64,14,.44)
          )
          !important;

        box-shadow:
          inset 0 0 0 1px
            rgba(250,204,21,.08),
          0 4px 14px
            rgba(0,0,0,.12)
      }

      html[data-theme="dark"]
      #heatGrid
      .heat-stock.heat-stock-top2::after{
        border-color:
          rgba(250,204,21,.26);
        background:
          rgba(66,32,6,.90);
        color:#fde68a
      }

      @media(max-width:720px){
        .heat-strength-note{
          margin-bottom:10px;
          padding:7px 9px;
          font-size:9px
        }

        #heatGrid
        .heat-stock.heat-stock-top2::after{
          top:5px;
          right:6px;
          font-size:7px
        }
      }
    `;

    document.head.appendChild(
      style
    );
  }

  /* =========================================================
     網頁上的金色說明
     ========================================================= */

  function ensureStrengthNote() {
    const heatGrid =
      document.getElementById(
        "heatGrid"
      );

    if (
      !heatGrid ||
      document.getElementById(
        "heatStrengthNote"
      )
    ) {
      return;
    }

    const note =
      document.createElement(
        "div"
      );

    note.id =
      "heatStrengthNote";

    note.className =
      "heat-strength-note";

    note.innerHTML = `
      <span
        class="heat-strength-swatch"
        aria-hidden="true"
      ></span>

      <span>
        金色＝各族群近5日累積漲幅前2強
      </span>
    `;

    heatGrid.parentNode.insertBefore(
      note,
      heatGrid
    );
  }

  /* =========================================================
     清除舊排名
     ========================================================= */

  function clearStrengthMarks() {
    document
      .querySelectorAll(
        "#heatGrid .heat-stock-top2"
      )
      .forEach(row => {
        row.classList.remove(
          "heat-stock-top2"
        );

        row.removeAttribute(
          "data-5d-rank"
        );

        row.removeAttribute(
          "data-5d-return"
        );
      });
  }

  /* =========================================================
     單一族群：
     依近5日累積報酬排名
     ========================================================= */

  function markTopStocks(
    detail,
    stockDetailData
  ) {
    const sectorName =
      sectorFromDetail(detail);

    if (!sectorName) {
      return;
    }

    const rows = [
      ...detail.querySelectorAll(
        ".heat-stock"
      )
    ];

    if (!rows.length) {
      return;
    }

    const ranked =
      rows
        .map(row => {
          const ticker =
            tickerFromRow(row);

          const stock =
            stockDetailData
              ?.stocks?.[ticker];

          const return5d =
            latestValidNumber(
              stock?.returns
            );

          return {
            row,
            ticker,
            return5d
          };
        })
        .filter(
          item =>
            item.ticker &&
            item.return5d !== null
        )
        .sort(
          (a, b) =>
            b.return5d -
            a.return5d
        );

    ranked
      .slice(
        0,
        TOP_COUNT
      )
      .forEach(
        (item, index) => {
          item.row.classList.add(
            "heat-stock-top2"
          );

          item.row.setAttribute(
            "data-5d-rank",
            String(
              index + 1
            )
          );

          item.row.setAttribute(
            "data-5d-return",
            String(
              item.return5d
            )
          );
        }
      );
  }

  /* =========================================================
     全部目前已展開族群重新計算
     ========================================================= */

  async function applyStrengthMarks() {
    if (strengthApplying) {
      return;
    }

    const heatGrid =
      document.getElementById(
        "heatGrid"
      );

    if (!heatGrid) {
      return;
    }

    strengthApplying = true;

    try {
      injectStrengthStyles();

      ensureStrengthNote();

      const data =
        await fetchStockDetail();

      clearStrengthMarks();

      const details = [
        ...heatGrid
          .querySelectorAll(
            ".heat-detail"
          )
      ];

      details.forEach(
        detail => {
          markTopStocks(
            detail,
            data
          );
        }
      );

    } catch (error) {
      console.error(
        "heatmap 5d strength mark failed:",
        error
      );

    } finally {
      strengthApplying = false;
    }
  }

  function scheduleStrengthMarks(
    delay = 80
  ) {
    if (strengthTimer) {
      clearTimeout(
        strengthTimer
      );
    }

    strengthTimer =
      setTimeout(
        function () {
          applyStrengthMarks();
        },
        delay
      );
  }

  /* =========================================================
     熱力圖展開／重畫時
     自動重新標記
     ========================================================= */

  function observeStrengthRows() {
    const heatGrid =
      document.getElementById(
        "heatGrid"
      );

    if (!heatGrid) {
      return;
    }

    if (strengthObserver) {
      strengthObserver.disconnect();
    }

    strengthObserver =
      new MutationObserver(
        function (mutations) {
          const changed =
            mutations.some(
              mutation =>
                mutation.type ===
                "childList"
            );

          if (changed) {
            scheduleStrengthMarks(
              100
            );
          }
        }
      );

    strengthObserver.observe(
      heatGrid,
      {
        childList: true,
        subtree: true
      }
    );
  }

  /* =========================================================
     原本 Heatmap Auto Refresh
     ========================================================= */

  async function refreshHeatmap() {
    if (
      typeof window.heat ===
      "function"
    ) {
      await window.heat();

      scheduleStrengthMarks(
        120
      );

      return true;
    }

    if (
      typeof heat ===
      "function"
    ) {
      await heat();

      scheduleStrengthMarks(
        120
      );

      return true;
    }

    console.warn(
      "heatmap auto refresh: heat() not found"
    );

    return false;
  }

  async function checkForUpdate(
    force = false
  ) {
    if (checking) {
      return;
    }

    /*
      一般 60 秒輪詢
      只在 Heatmap 畫面執行
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
      */

      if (
        lastUpdatedAt === null
      ) {
        lastUpdatedAt =
          updatedAt;

        console.log(
          "heatmap auto refresh initialized:",
          updatedAt
        );

        scheduleStrengthMarks();

        return;
      }

      /*
        heatmap 本身沒有更新
        仍重新讀 stock_detail
        確保近5日資料如果稍晚更新
        金色排名也能跟著變
      */

      if (
        String(updatedAt) ===
        String(lastUpdatedAt)
      ) {
        scheduleStrengthMarks();

        return;
      }

      console.log(
        "New heatmap detected:",
        lastUpdatedAt,
        "→",
        updatedAt
      );

      lastUpdatedAt =
        updatedAt;

      const refreshed =
        await refreshHeatmap();

      if (refreshed) {
        window.dispatchEvent(
          new CustomEvent(
            "heatmap:data-updated",
            {
              detail: {
                updated_at:
                  updatedAt
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

  /* =========================================================
     60 秒檢查
     ========================================================= */

  function startTimer() {
    if (timer) {
      clearInterval(timer);
    }

    timer =
      setInterval(
        function () {
          /*
            Safari 在背景時
            不浪費 request
          */

          if (
            document.hidden
          ) {
            return;
          }

          checkForUpdate(
            false
          );
        },
        CHECK_INTERVAL
      );
  }

  /* =========================================================
     Safari / 手機前景切換
     ========================================================= */

  function bindVisibilityEvents() {
    document.addEventListener(
      "visibilitychange",
      function () {
        if (
          !document.hidden
        ) {
          checkForUpdate(
            true
          );
        }
      }
    );

    window.addEventListener(
      "pageshow",
      function () {
        checkForUpdate(
          true
        );
      }
    );

    window.addEventListener(
      "focus",
      function () {
        checkForUpdate(
          true
        );
      }
    );

    window.addEventListener(
      "heatmap:data-updated",
      function () {
        scheduleStrengthMarks(
          120
        );
      }
    );
  }

  /* =========================================================
     切換到市場熱力圖時立即更新
     ========================================================= */

  function bindHeatmapNavigation() {
    const heatPage =
      document.getElementById(
        "heat"
      );

    if (!heatPage) {
      return;
    }

    const observer =
      new MutationObserver(
        function () {
          if (
            heatPage
              .classList
              .contains(
                "active"
              )
          ) {
            checkForUpdate(
              true
            );

            scheduleStrengthMarks(
              120
            );
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

  /* =========================================================
     Init
     ========================================================= */

  async function init() {
    injectStrengthStyles();

    ensureStrengthNote();

    observeStrengthRows();

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

    /*
      app.js 與 sector filter
      可能稍晚才完成第一次渲染
    */

    scheduleStrengthMarks(
      250
    );
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
