/* =========================================================
   市場熱力圖：市值加權 / 均衡加權

   重要原則：
   1. 不改 app.js
   2. 不搬動 heatGrid 裡任何族群卡片
   3. 不自行排序 DOM
   4. 點開族群完全沿用 app.js 原本 heat() / heatDetail()
   5. 均衡加權只修改「顯示數值、顏色、廣度資訊」
   6. app.js 每次重建 heatGrid 後，再重新套用均衡加權顯示

   動態單股權重上限：
   1 檔      → 100%
   2 檔      → 65%
   3 檔      → 50%
   4 檔      → 40%
   5–6 檔    → 35%
   7–9 檔    → 30%
   10 檔以上 → 25%
   ========================================================= */

(function () {
  const STORAGE_KEY =
    "tw_heat_weight_mode";

  let mode =
    localStorage.getItem(
      STORAGE_KEY
    ) || "market";

  /*
    相容之前的 breadth 模式名稱
  */
  if (mode === "breadth") {
    mode = "balanced";

    localStorage.setItem(
      STORAGE_KEY,
      mode
    );
  }

  let heatData = null;
  let loadingPromise = null;
  let observer = null;
  let applyQueued = false;

  const $ = selector =>
    document.querySelector(
      selector
    );

  const $$ = selector =>
    [
      ...document.querySelectorAll(
        selector
      )
    ];


  /* =========================================================
     百分比格式
     ========================================================= */

  function pct(value) {
    if (
      value === null ||
      value === undefined ||
      Number.isNaN(
        Number(value)
      )
    ) {
      return "—";
    }

    const n =
      Number(value);

    return (
      (n > 0 ? "+" : "") +
      n.toFixed(2) +
      "%"
    );
  }


  /* =========================================================
     動態單股權重上限
     ========================================================= */

  function getWeightCap(count) {
    if (count <= 1) {
      return 1;
    }

    if (count === 2) {
      return 0.65;
    }

    if (count === 3) {
      return 0.50;
    }

    if (count === 4) {
      return 0.40;
    }

    if (count <= 6) {
      return 0.35;
    }

    if (count <= 9) {
      return 0.30;
    }

    return 0.25;
  }


  /* =========================================================
     市值權重套用 Cap

     超過 Cap 的權重會重新分配給其他股票
     ========================================================= */

  function cappedWeights(values) {
    const raw =
      values.map(
        value =>
          Math.max(
            0,
            Number(value) || 0
          )
      );

    const total =
      raw.reduce(
        (sum, value) =>
          sum + value,
        0
      );

    if (!total) {
      return raw.map(
        () => 0
      );
    }

    const cap =
      getWeightCap(
        raw.length
      );

    const base =
      raw.map(
        value =>
          value / total
      );

    const result =
      new Array(
        base.length
      ).fill(null);

    const active =
      new Set(
        base.map(
          (_, index) =>
            index
        )
      );

    while (active.size) {
      const fixedSum =
        result.reduce(
          (sum, value) =>
            sum +
            (
              value === null
                ? 0
                : value
            ),
          0
        );

      const remaining =
        Math.max(
          0,
          1 - fixedSum
        );

      const activeBaseSum =
        [...active]
          .reduce(
            (sum, index) =>
              sum +
              base[index],
            0
          );

      if (!activeBaseSum) {
        const each =
          remaining /
          active.size;

        [...active]
          .forEach(
            index => {
              result[index] =
                each;
            }
          );

        break;
      }

      const trial =
        new Map();

      [...active]
        .forEach(
          index => {
            trial.set(
              index,
              remaining *
              base[index] /
              activeBaseSum
            );
          }
        );

      const over =
        [...active]
          .filter(
            index =>
              trial.get(
                index
              ) >
              cap + 1e-12
          );

      if (!over.length) {
        [...active]
          .forEach(
            index => {
              result[index] =
                trial.get(
                  index
                );
            }
          );

        break;
      }

      over.forEach(
        index => {
          result[index] =
            cap;

          active.delete(
            index
          );
        }
      );
    }

    return result.map(
      value =>
        Number(value || 0)
    );
  }


  /* =========================================================
     計算均衡加權
     ========================================================= */

  function calcBalanced(sec) {
    const valid =
      (sec?.stocks || [])
        .filter(
          stock =>
            stock &&
            stock.change_pct !==
              null &&
            stock.change_pct !==
              undefined &&
            Number.isFinite(
              Number(
                stock.change_pct
              )
            ) &&
            Number(
              stock.market_cap ||
              0
            ) > 0
        );

    if (!valid.length) {
      return {
        change_pct: null,
        up: 0,
        down: 0,
        flat: 0,
        valid: 0,
        cap: null,
        weights: []
      };
    }

    const cap =
      getWeightCap(
        valid.length
      );

    const weights =
      cappedWeights(
        valid.map(
          stock =>
            Number(
              stock.market_cap ||
              0
            )
        )
      );

    const changePct =
      valid.reduce(
        (
          sum,
          stock,
          index
        ) =>
          sum +
          (
            Number(
              stock.change_pct
            ) *
            weights[index]
          ),
        0
      );

    const up =
      valid.filter(
        stock =>
          Number(
            stock.change_pct
          ) > 0
      ).length;

    const down =
      valid.filter(
        stock =>
          Number(
            stock.change_pct
          ) < 0
      ).length;

    const flat =
      valid.length -
      up -
      down;

    return {
      change_pct:
        changePct,

      up,
      down,
      flat,

      valid:
        valid.length,

      cap,

      weights:
        valid.map(
          (
            stock,
            index
          ) => ({
            ticker:
              String(
                stock.ticker ||
                ""
              ),

            name:
              stock.name ||
              String(
                stock.ticker ||
                ""
              ),

            capped_weight:
              weights[index]
          })
        )
    };
  }


  /* =========================================================
     讀取最新 heatmap.json
     ========================================================= */

  async function loadHeatData(
    force = false
  ) {
    if (
      heatData &&
      !force
    ) {
      return heatData;
    }

    if (
      loadingPromise &&
      !force
    ) {
      return loadingPromise;
    }

    loadingPromise =
      fetch(
        "./data/heatmap.json?v=" +
        Date.now(),
        {
          cache: "no-store"
        }
      )
        .then(
          response => {
            if (
              !response.ok
            ) {
              throw new Error(
                "HTTP " +
                response.status
              );
            }

            return response
              .json();
          }
        )
        .then(
          data => {
            heatData =
              data;

            return data;
          }
        )
        .catch(
          error => {
            console.error(
              "balanced heatmap load failed",
              error
            );

            return null;
          }
        )
        .finally(
          () => {
            loadingPromise =
              null;
          }
        );

    return loadingPromise;
  }


  /* =========================================================
     族群 Map
     ========================================================= */

  function sectorMap() {
    return new Map(
      (
        heatData?.sectors ||
        []
      ).map(
        sec => [
          String(
            sec.name
          ),
          sec
        ]
      )
    );
  }


  /* =========================================================
     顏色

     沿用 app.js 原本 heatClass()
     如果找不到才使用 fallback
     ========================================================= */

  function getHeatClass(value) {
    try {
      if (
        typeof heatClass ===
        "function"
      ) {
        return heatClass(
          value
        );
      }
    } catch (_) {}

    if (
      value === null ||
      value === undefined ||
      Number.isNaN(
        Number(value)
      )
    ) {
      return "gray";
    }

    const n =
      Number(value);

    const abs =
      Math.abs(n);

    if (n >= 0) {
      if (abs >= 3) {
        return "r4";
      }

      if (abs >= 2) {
        return "r3";
      }

      if (abs >= 1) {
        return "r2";
      }

      return "r1";
    }

    if (abs >= 3) {
      return "g4";
    }

    if (abs >= 2) {
      return "g3";
    }

    if (abs >= 1) {
      return "g2";
    }

    return "g1";
  }


  /* =========================================================
     CSS
     ========================================================= */

  function ensureStyles() {
    if (
      $("#heatBalancedStyle")
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "heatBalancedStyle";

    style.textContent = `
      .heat-weight-mode {
        display:flex;
        gap:6px;
        padding:4px;
        border:1px solid var(--line);
        border-radius:14px;
        background:var(--soft);
      }

      .heat-weight-mode button {
        flex:1;
        min-height:36px;
        padding:0 12px;
        border:0;
        border-radius:10px;
        background:transparent;
        color:var(--muted);
        font-size:11px;
        font-weight:850;
        cursor:pointer;
        white-space:nowrap;
      }

      .heat-weight-mode button.active {
        background:var(--card);
        color:var(--ink);
        box-shadow:
          0 2px 8px
          rgba(15,23,42,.10);
      }

      .heat-balanced-help {
        margin-top:8px;
        color:var(--muted);
        font-size:9px;
        line-height:1.55;
      }

      .heat-breadth-line {
        display:block;
        margin-top:3px;
        font-size:9px;
        font-weight:800;
        opacity:.86;
      }

      .heat-detail-balanced-note {
        margin:8px 0 10px;
        padding:9px 11px;
        border:1px solid var(--line);
        border-radius:12px;
        background:var(--soft);
        color:var(--muted);
        font-size:10px;
        font-weight:700;
        line-height:1.5;
      }

      @media(max-width:720px) {
        .heat-sector-actions {
          flex-wrap:wrap;
        }

        .heat-weight-mode {
          width:100%;
        }
      }
    `;

    document.head
      .appendChild(
        style
      );
  }


  /* =========================================================
     建立模式切換

     不碰 heatGrid
     ========================================================= */

  function ensureToggle() {
    const actions =
      $(".heat-sector-actions");

    if (!actions) {
      return;
    }

    if (
      $("#heatWeightMode")
    ) {
      return;
    }

    const wrap =
      document.createElement(
        "div"
      );

    wrap.id =
      "heatWeightMode";

    wrap.className =
      "heat-weight-mode";

    wrap.innerHTML = `
      <button
        type="button"
        data-heat-weight="market"
      >
        市值加權
      </button>

      <button
        type="button"
        data-heat-weight="balanced"
      >
        均衡加權
      </button>
    `;

    actions.appendChild(
      wrap
    );

    wrap
      .querySelectorAll(
        "[data-heat-weight]"
      )
      .forEach(
        button => {
          button.addEventListener(
            "click",
            async () => {
              mode =
                button.dataset
                  .heatWeight;

              localStorage.setItem(
                STORAGE_KEY,
                mode
              );

              /*
                只重新套顯示
                不執行 heat()
                不搬動 DOM
              */

              await loadHeatData(
                true
              );

              updateControls();

              applyMode();
            }
          );
        }
      );

    const help =
      document.createElement(
        "div"
      );

    help.id =
      "heatBalancedHelp";

    help.className =
      "heat-balanced-help";

    const control =
      $("#heatSectorControl");

    if (control) {
      control.appendChild(
        help
      );
    }

    updateControls();
  }


  /* =========================================================
     更新按鈕與說明文字
     ========================================================= */

  function updateControls() {
    $$(
      "[data-heat-weight]"
    ).forEach(
      button => {
        button.classList.toggle(
          "active",
          button.dataset
            .heatWeight ===
            mode
        );
      }
    );

    const help =
      $("#heatBalancedHelp");

    if (help) {
      if (
        mode ===
        "balanced"
      ) {
        help.textContent =
          "均衡加權：依成分股數動態限制單股權重｜2檔65%・3檔50%・4檔40%・5–6檔35%・7–9檔30%・10檔以上25%｜↑ x/y 為族群上漲家數";
      } else {
        help.textContent =
          "市值加權：依各成分股市值權重計算族群漲跌幅";
      }
    }

    /*
      heatmap_sector_filter.js
      也會改 hero 文字。

      這裡只在均衡模式覆蓋，
      市值模式使用簡潔正確敘述。
    */

    const hero =
      $("#heat .hero p");

    if (hero) {
      const count =
        (
          heatData?.sectors ||
          []
        ).length;

      if (
        mode ===
        "balanced"
      ) {
        hero.textContent =
          `${count} 個自訂族群｜均衡加權｜動態單股權重上限｜紅漲綠跌`;
      } else {
        hero.textContent =
          `${count} 個自訂族群｜市值加權｜紅漲綠跌｜可直接下拉選族群`;
      }
    }
  }


  /* =========================================================
     移除我們自己加的卡片資訊
     ========================================================= */

  function removeBreadthLines() {
    $$(
      "#heatGrid .heat-breadth-line"
    ).forEach(
      element => {
        element.remove();
      }
    );
  }


  /* =========================================================
     還原 / 修改卡片

     重要：
     只修改卡片本身
     不 appendChild 卡片
     不 insertBefore 卡片
     不排序
     ========================================================= */

  function applyCards() {
    if (!heatData) {
      return;
    }

    const map =
      sectorMap();

    $$(
      "#heatGrid > button.heat[data-sec]"
    ).forEach(
      button => {
        const sec =
          map.get(
            String(
              button.dataset.sec
            )
          );

        if (!sec) {
          return;
        }

        const balanced =
          calcBalanced(
            sec
          );

        const value =
          mode === "balanced"
            ? balanced.change_pct
            : sec.change_pct;

        /*
          顏色
        */

        button.classList.remove(
          "gray",
          "r1",
          "r2",
          "r3",
          "r4",
          "g1",
          "g2",
          "g3",
          "g4"
        );

        button.classList.add(
          getHeatClass(
            value
          )
        );

        /*
          漲跌幅
        */

        const strong =
          button.querySelector(
            "strong"
          );

        if (strong) {
          strong.textContent =
            pct(value);
        }

        /*
          先移除舊廣度文字
        */

        button
          .querySelectorAll(
            ".heat-breadth-line"
          )
          .forEach(
            element =>
              element.remove()
          );

        /*
          市值加權不加廣度資訊
        */

        if (
          mode !==
          "balanced"
        ) {
          return;
        }

        /*
          均衡加權顯示真正 Breadth
        */

        const line =
          document.createElement(
            "span"
          );

        line.className =
          "heat-breadth-line";

        if (
          balanced.valid
        ) {
          const ratio =
            Math.round(
              balanced.up /
              balanced.valid *
              100
            );

          line.textContent =
            `↑ ${balanced.up}/${balanced.valid} · ${ratio}%上漲`;
        } else {
          line.textContent =
            "上漲家數 —";
        }

        button.appendChild(
          line
        );
      }
    );
  }


  /* =========================================================
     修改目前展開的 Detail

     不移動 Detail
     不改 Detail 所在位置
     ========================================================= */

  function applyOpenDetail() {
    const detail =
      $(
        "#heatGrid .heat-detail"
      );

    if (
      !detail ||
      !heatData
    ) {
      return;
    }

    /*
      最可靠方式：
      直接從 detail 標題取得族群名稱

      不再依賴 previousElementSibling，
      因為 Grid / 外掛可能影響 DOM 判斷。
    */

    const head =
      detail.querySelector(
        ".heat-detail-head b"
      );

    if (!head) {
      return;
    }

    const name =
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
        .trim();

    if (!name) {
      return;
    }

    const sec =
      (
        heatData.sectors ||
        []
      ).find(
        item =>
          String(
            item.name
          ) ===
          String(name)
      );

    if (!sec) {
      return;
    }

    const balanced =
      calcBalanced(
        sec
      );

    /*
      app.js 原本：
      .heat-detail-head b span
      就是族群漲跌幅
    */

    const valueSpan =
      detail.querySelector(
        ".heat-detail-head b > span"
      );

    const value =
      mode === "balanced"
        ? balanced.change_pct
        : sec.change_pct;

    if (valueSpan) {
      valueSpan.textContent =
        pct(value);

      /*
        保留 app.js 原本 cl()
        如果可用就同步更新 class
      */

      try {
        if (
          typeof cl ===
          "function"
        ) {
          valueSpan.className =
            cl(value);
        }
      } catch (_) {}
    }

    /*
      移除舊均衡說明
    */

    detail
      .querySelectorAll(
        ".heat-detail-balanced-note, .heat-detail-breadth-note"
      )
      .forEach(
        element =>
          element.remove()
      );

    if (
      mode !==
      "balanced"
    ) {
      return;
    }

    const note =
      document.createElement(
        "div"
      );

    note.className =
      "heat-detail-balanced-note";

    if (
      balanced.valid
    ) {
      const cap =
        Math.round(
          balanced.cap *
          100
        );

      const ratio =
        Math.round(
          balanced.up /
          balanced.valid *
          100
        );

      note.innerHTML = `
        均衡加權
        <b style="color:var(--ink)">
          ${pct(
            balanced.change_pct
          )}
        </b>

        ｜ 上漲
        <b style="color:var(--ink)">
          ${balanced.up}/${balanced.valid}
        </b>

        （${ratio}%）

        ｜ 單股權重上限
        <b style="color:var(--ink)">
          ${cap}%
        </b>
      `;

    } else {
      note.textContent =
        "均衡加權資料不足";
    }

    const list =
      detail.querySelector(
        ".heat-stock-list"
      );

    if (list) {
      detail.insertBefore(
        note,
        list
      );
    } else {
      detail.appendChild(
        note
      );
    }
  }


  /* =========================================================
     套用目前模式

     完全不排序 DOM
     ========================================================= */

  function applyMode() {
    if (!heatData) {
      return;
    }

    updateControls();

    applyCards();

    applyOpenDetail();
  }


  /* =========================================================
     排程重新套用

     app.js 點族群時：
     heat() → box.innerHTML = html

     我們等它重建完成後，
     再修改數字。

     不再自己重新 render heat()
     ========================================================= */

  function queueApply() {
    if (applyQueued) {
      return;
    }

    applyQueued = true;

    requestAnimationFrame(
      () => {
        applyQueued = false;

        applyMode();
      }
    );
  }


  /* =========================================================
     監聽 app.js 重建 heatGrid

     只監聽第一層 childList。

     app.js 每次點卡片會直接：
     box.innerHTML = html

     所以這裡會收到變化，
     然後重新套用均衡顯示。

     不修改卡片位置。
     ========================================================= */

  function observeHeatGrid() {
    const grid =
      $("#heatGrid");

    if (!grid) {
      return;
    }

    if (observer) {
      observer.disconnect();
    }

    observer =
      new MutationObserver(
        mutations => {
          const relevant =
            mutations.some(
              mutation =>
                mutation.type ===
                "childList" &&
                mutation.target ===
                grid
            );

          if (!relevant) {
            return;
          }

          queueApply();
        }
      );

    observer.observe(
      grid,
      {
        childList: true,
        subtree: false
      }
    );
  }


  /* =========================================================
     heatmap_auto_refresh.js

     有新資料時重新讀 heatmap.json
     ========================================================= */

  function bindAutoRefresh() {
    window.addEventListener(
      "heatmap:data-updated",
      async () => {
        await loadHeatData(
          true
        );

        queueApply();
      }
    );
  }


  /* =========================================================
     Page / visibility

     回到頁面時補一次
     ========================================================= */

  function bindPageEvents() {
    document.addEventListener(
      "visibilitychange",
      () => {
        if (
          !document.hidden
        ) {
          queueApply();
        }
      }
    );

    window.addEventListener(
      "pageshow",
      () => {
        queueApply();
      }
    );
  }


  /* =========================================================
     初始化
     ========================================================= */

  async function init() {
    ensureStyles();

    await loadHeatData(
      true
    );

    let tries = 0;

    const timer =
      setInterval(
        () => {
          tries += 1;

          const grid =
            $("#heatGrid");

          const actions =
            $(".heat-sector-actions");

          if (
            grid &&
            actions
          ) {
            clearInterval(
              timer
            );

            ensureToggle();

            updateControls();

            applyMode();

            observeHeatGrid();

            bindAutoRefresh();

            bindPageEvents();

            return;
          }

          if (
            tries >= 80
          ) {
            clearInterval(
              timer
            );
          }
        },
        150
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
