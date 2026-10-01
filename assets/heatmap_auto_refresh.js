/* =========================================================
   Heatmap Auto Refresh + 近5日族群強勢股標記
   2026-10-01

   功能：
   1. 每 60 秒檢查 heatmap.json
   2. updated_at 改變才更新熱力圖
   3. iPhone / Safari 從背景切回時立即檢查
   4. 回到 Heatmap 分頁時立即檢查
   5. 不重新整理整個網頁
   6. 每族群依 stock_detail.json 最新近5日累積報酬排名
   7. 第1、2名標示淡金色
   8. 股票名稱旁顯示「近五日漲幅第1／第2」
   9. 標籤不佔用右側當日漲幅區域
   10. 排名隨近5日資料自動更新
   11. 不碰 app.js
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
     樣式
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

      /* 上方說明 */

      .heat-strength-note{
        display:flex;
        align-items:center;
        gap:8px;

        width:max-content;
        max-width:100%;

        margin:0 0 12px;
        padding:7px 10px;

        border:1px solid
          rgba(202,138,4,.26);

        border-radius:10px;

        background:
          rgba(254,243,199,.56);

        color:#765314;

        font-size:10px;
        font-weight:800;
        line-height:1.35
      }

      .heat-strength-swatch{
        width:11px;
        height:11px;

        flex:0 0 11px;

        border:1px solid
          rgba(202,138,4,.42);

        border-radius:4px;

        background:
          linear-gradient(
            180deg,
            rgba(253,230,138,.92),
            rgba(254,243,199,.92)
          )
      }


      /* =========================
         Top 2 金色背景
         ========================= */

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


      /* =========================
         股票名稱左側內容區
         ========================= */

      #heatGrid
      .heat-stock
      .heat-strength-left{
        display:inline-flex;
        align-items:center;
        gap:6px;

        min-width:0;
        max-width:calc(100% - 90px)
      }


      /* =========================
         第1 / 第2 標籤
         ========================= */

      #heatGrid
      .heat-strength-rank{
        display:inline-flex;
        align-items:center;
        justify-content:center;

        flex:0 0 auto;

        padding:3px 6px;

        border:1px solid
          rgba(180,83,9,.24);

        border-radius:999px;

        background:
          rgba(255,251,235,.92);

        color:#92400e;

        font-size:9px;
        font-weight:900;
        line-height:1;

        white-space:nowrap
      }


      /* =========================
         深色模式
         ========================= */

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
      .heat-strength-rank{
        border-color:
          rgba(250,204,21,.28);

        background:
          rgba(66,32,6,.88);

        color:#fde68a
      }


      /* =========================
         手機
         ========================= */

      @media(max-width:720px){

        .heat-strength-note{
          margin-bottom:10px;
          padding:7px 9px;
          font-size:9px
        }

        #heatGrid
        .heat-stock
        .heat-strength-left{
          gap:5px;
          max-width:calc(100% - 82px)
        }

        #heatGrid
        .heat-strength-rank{
          padding:3px 5px;
          font-size:8px
        }
      }


      /* =========================
         特別窄的手機
         ========================= */

      @media(max-width:390px){

        #heatGrid
        .heat-strength-rank{
          padding:2px 4px;
          font-size:7px
        }
      }
    `;

    document.head.appendChild(
      style
    );
  }

  /* =========================================================
     上方金色說明
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
     清除舊標記
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


    document
      .querySelectorAll(
        "#heatGrid .heat-strength-rank"
      )
      .forEach(label => {
        label.remove();
      });


    document
      .querySelectorAll(
        "#heatGrid .heat-strength-left"
      )
      .forEach(wrapper => {

        const parent =
          wrapper.parentNode;

        if (!parent) {
          return;
        }

        while (
          wrapper.firstChild
        ) {
          parent.insertBefore(
            wrapper.firstChild,
            wrapper
          );
        }

        wrapper.remove();
      });
  }

  /* =========================================================
     加入「近五日漲幅第1 / 第2」標籤
     ========================================================= */

  function addRankLabel(
    row,
    rank
  ) {

    /*
      找股票名稱
      原本 heatmap 個股列的名稱元素
    */

    const ticker =
      row.querySelector(".t");

    if (!ticker) {
      return;
    }

    /*
      名稱通常就在 ticker 前面
      找最適合的名稱節點
    */

    let nameElement = null;

    const candidates = [
      ...row.children
    ];

    for (
      const child of candidates
    ) {

      if (
        child === ticker
      ) {
        continue;
      }

      /*
        右邊漲幅通常含 %
        不把它當成名稱
      */

      if (
        child.textContent
          ?.includes("%")
      ) {
        continue;
      }

      if (
        child.querySelector?.(
          ".t"
        )
      ) {
        continue;
      }

      nameElement = child;
      break;
    }


    /*
      如果目前 DOM 結構不是獨立元素，
      就直接把標籤插在 ticker 後面
      仍然不會碰右側漲幅
    */

    const label =
      document.createElement(
        "span"
      );

    label.className =
      "heat-strength-rank";

    label.textContent =
      rank === 1
        ? "近五日漲幅第1"
        : "近五日漲幅第2";


    /*
      優先放在股票代號後
      這樣版面會是：

      新唐 4919 [近五日漲幅第1]     +9.75%
    */

    ticker.insertAdjacentElement(
      "afterend",
      label
    );
  }

  /* =========================================================
     單一族群排名
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

          const rank =
            index + 1;

          item.row.classList.add(
            "heat-stock-top2"
          );

          item.row.setAttribute(
            "data-5d-rank",
            String(rank)
          );

          item.row.setAttribute(
            "data-5d-return",
            String(
              item.return5d
            )
          );

          addRankLabel(
            item.row,
            rank
          );
        }
      );
  }

  /* =========================================================
     全部已展開族群重新排名
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
        ...heatGrid.querySelectorAll(
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
     Heatmap DOM 變化
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
     Heatmap Auto Refresh
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

      if (
        lastUpdatedAt ===
        null
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
        heatmap 沒更新，
        仍重新讀 stock_detail
        讓近5日排名跟著最新資料變動
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
     Safari / iPhone
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
     切回熱力圖
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
