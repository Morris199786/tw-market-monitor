/* =========================================================
   Heatmap 價 / 量模式
   2026-10-07

   價：
   - 使用 app.js 原本價格熱力圖
   - 保留當日 / 5日 / 10日 / 20日
   - 保留市值加權 / 權重上限
   - 當日模式顯示各族群近5日漲幅 Top 2 金標

   量：
   - 完全獨立成交金額 Treemap
   - 方塊面積 = 當日族群成交金額
   - 顏色 = 當日族群市值漲跌
   - 固定單位 = 億元
   - 顯示：
       成交 XXX 億
       5日均 XXX 億（±XX%）
       市值 ±X.XX%
   - 隱藏價格模式專用控制項
   ========================================================= */

(function () {
  "use strict";

  const CACHE_MS =
    5 * 60 * 1000;

  const state = {
    mode: "price",

    volumeData: null,
    volumeAt: 0,

    detailData: null,
    detailAt: 0,

    renderingVolume: false,
    restoringPrice: false,

    observer: null,
    timer: null
  };

  /* =========================================================
     Helpers
     ========================================================= */

  function $(
    selector,
    root = document
  ) {
    return root.querySelector(
      selector
    );
  }

  function $$(
    selector,
    root = document
  ) {
    return [
      ...root.querySelectorAll(
        selector
      )
    ];
  }

  function number(
    value
  ) {
    const n =
      Number(value);

    return Number.isFinite(n)
      ? n
      : null;
  }

  function heatVisible() {
    const page =
      document.getElementById(
        "heat"
      );

    return !!(
      page &&
      page.classList.contains(
        "active"
      )
    );
  }

  function activePeriod() {
    if (
      typeof
        window
          .getHeatmapActivePeriod ===
      "function"
    ) {
      return String(
        window
          .getHeatmapActivePeriod() ||
        "1"
      );
    }

    return "1";
  }

  /* =========================================================
     JSON
     ========================================================= */

  async function loadJson(
    path,
    force = false
  ) {
    const version =
      force
        ? Date.now()
        : Math.floor(
            Date.now() /
            CACHE_MS
          );

    const response =
      await fetch(
        `${path}?v=${version}`,
        {
          cache:
            "no-store"
        }
      );

    if (!response.ok) {
      throw new Error(
        `${path} HTTP ${response.status}`
      );
    }

    return response.json();
  }

  async function loadVolumeData(
    force = false
  ) {
    if (
      !force &&
      state.volumeData &&
      Date.now() -
        state.volumeAt <
        CACHE_MS
    ) {
      return state.volumeData;
    }

    const data =
      await loadJson(
        "./data/sector_turnover.json",
        force
      );

    state.volumeData =
      data;

    state.volumeAt =
      Date.now();

    return data;
  }

  async function loadDetailData(
    force = false
  ) {
    if (
      !force &&
      state.detailData &&
      Date.now() -
        state.detailAt <
        CACHE_MS
    ) {
      return state.detailData;
    }

    const data =
      await loadJson(
        "./data/stock_detail.json",
        force
      );

    state.detailData =
      data;

    state.detailAt =
      Date.now();

    return data;
  }

  /* =========================================================
     CSS
     ========================================================= */

  function injectStyles() {
    if (
      document.getElementById(
        "heatPriceVolumeStyles"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "heatPriceVolumeStyles";

    style.textContent = `

      /* ========================================
         價 / 量
         ======================================== */

      .heat-pv-switch{
        display:flex;
        align-items:center;

        width:max-content;

        padding:4px;

        margin:
          0 0 18px;

        border:
          1px solid
          rgba(
            148,
            163,
            184,
            .32
          );

        border-radius:
          14px;

        background:
          rgba(
            148,
            163,
            184,
            .08
          );
      }

      .heat-pv-switch button{
        min-width:
          88px;

        padding:
          10px 20px;

        border:0;

        border-radius:
          11px;

        background:
          transparent;

        color:
          inherit;

        font:
          inherit;

        font-size:
          15px;

        font-weight:
          900;

        cursor:
          pointer;

        transition:
          background .15s ease,
          box-shadow .15s ease;
      }

      .heat-pv-switch
      button.active{
        background:
          #ffffff;

        color:
          #111827;

        box-shadow:
          0 2px 8px
          rgba(
            15,
            23,
            42,
            .12
          );
      }

      html[data-theme="dark"]
      .heat-pv-switch
      button.active{
        background:
          #273142;

        color:
          #ffffff;
      }


      /* ========================================
         金色 Top 2
         ======================================== */

      .heat-strength-note{
        display:flex;

        align-items:center;

        gap:7px;

        width:max-content;

        max-width:100%;

        margin:
          0 0 12px;

        padding:
          7px 10px;

        border:
          1px solid
          rgba(
            202,
            138,
            4,
            .26
          );

        border-radius:
          10px;

        background:
          rgba(
            254,
            243,
            199,
            .56
          );

        color:
          #765314;

        font-size:
          10px;

        font-weight:
          800;
      }

      .heat-strength-swatch{
        width:
          11px;

        height:
          11px;

        flex:
          0 0 11px;

        border-radius:
          4px;

        background:
          #f5d76e;
      }

      #heatGrid
      .heat-stock.heat-stock-top2{
        border-color:
          rgba(
            202,
            138,
            4,
            .42
          )
          !important;

        background:
          linear-gradient(
            135deg,
            rgba(
              254,
              243,
              199,
              .88
            ),
            rgba(
              253,
              230,
              138,
              .58
            )
          )
          !important;
      }

      #heatGrid
      .heat-strength-rank{
        display:inline-flex;

        align-items:center;

        margin-left:
          5px;

        padding:
          3px 6px;

        border:
          1px solid
          rgba(
            180,
            83,
            9,
            .24
          );

        border-radius:
          999px;

        background:
          rgba(
            255,
            251,
            235,
            .92
          );

        color:
          #92400e;

        font-size:
          9px;

        font-weight:
          900;

        line-height:
          1;

        white-space:
          nowrap;
      }

      html[data-theme="dark"]
      .heat-strength-note{
        background:
          rgba(
            113,
            63,
            18,
            .26
          );

        color:
          #fde68a;
      }

      html[data-theme="dark"]
      #heatGrid
      .heat-stock.heat-stock-top2{
        background:
          linear-gradient(
            135deg,
            rgba(
              113,
              63,
              18,
              .62
            ),
            rgba(
              146,
              64,
              14,
              .44
            )
          )
          !important;
      }


      /* ========================================
         量模式說明
         ======================================== */

      .turnover-header{
        display:flex;

        align-items:flex-end;

        justify-content:
          space-between;

        gap:
          12px;

        margin:
          0 0 12px;
      }

      .turnover-header-main{
        font-size:
          13px;

        font-weight:
          800;

        color:
          inherit;
      }

      .turnover-header-sub{
        margin-top:
          4px;

        font-size:
          11px;

        color:
          #7c8798;
      }

      .turnover-date{
        flex:
          0 0 auto;

        font-size:
          11px;

        color:
          #8b95a5;
      }


      /* ========================================
         Treemap
         ======================================== */

      #heatGrid
      .turnover-treemap{
        position:relative;

        width:100%;

        height:
          720px;

        overflow:hidden;

        border-radius:
          16px;

        background:
          rgba(
            148,
            163,
            184,
            .08
          );
      }

      #heatGrid
      .turnover-box{
        position:absolute;

        box-sizing:
          border-box;

        padding:
          3px;
      }

      #heatGrid
      .turnover-inner{
        width:
          100%;

        height:
          100%;

        box-sizing:
          border-box;

        overflow:
          hidden;

        display:flex;

        flex-direction:
          column;

        justify-content:
          center;

        padding:
          12px;

        border-radius:
          10px;

        color:
          #ffffff;

        text-align:
          left;

        box-shadow:
          inset
          0 0 0 1px
          rgba(
            255,
            255,
            255,
            .16
          );
      }


      /* 上漲 */

      #heatGrid
      .turnover-inner.r1{
        background:
          #a54d4d;
      }

      #heatGrid
      .turnover-inner.r2{
        background:
          #c84a4a;
      }

      #heatGrid
      .turnover-inner.r3{
        background:
          #dc3838;
      }

      #heatGrid
      .turnover-inner.r4{
        background:
          #e52626;
      }


      /* 下跌 */

      #heatGrid
      .turnover-inner.g1{
        background:
          #557b69;
      }

      #heatGrid
      .turnover-inner.g2{
        background:
          #3d8b65;
      }

      #heatGrid
      .turnover-inner.g3{
        background:
          #25965c;
      }

      #heatGrid
      .turnover-inner.g4{
        background:
          #138348;
      }


      #heatGrid
      .turnover-inner.gray{
        background:
          #687386;
      }


      /* ========================================
         Treemap 字
         ======================================== */

      .turnover-sector{
        overflow:hidden;

        text-overflow:
          ellipsis;

        white-space:
          nowrap;

        font-size:
          clamp(
            12px,
            1.45vw,
            23px
          );

        font-weight:
          900;

        line-height:
          1.08;

        margin-bottom:
          8px;
      }

      .turnover-value{
        overflow:hidden;

        text-overflow:
          ellipsis;

        white-space:
          nowrap;

        font-size:
          clamp(
            12px,
            1.35vw,
            22px
          );

        font-weight:
          900;

        line-height:
          1.1;
      }

      .turnover-average{
        overflow:hidden;

        text-overflow:
          ellipsis;

        white-space:
          nowrap;

        margin-top:
          6px;

        font-size:
          clamp(
            9px,
            .9vw,
            14px
          );

        font-weight:
          800;

        line-height:
          1.2;
      }

      .turnover-market{
        overflow:hidden;

        text-overflow:
          ellipsis;

        white-space:
          nowrap;

        margin-top:
          5px;

        font-size:
          clamp(
            9px,
            .86vw,
            14px
          );

        font-weight:
          750;

        line-height:
          1.2;
      }


      /* ========================================
         Loading / Error
         ======================================== */

      .turnover-status{
        width:100%;

        padding:
          32px 18px;

        border:
          1px solid
          rgba(
            148,
            163,
            184,
            .22
          );

        border-radius:
          14px;

        text-align:
          center;

        color:
          #7c8798;

        font-size:
          13px;

        font-weight:
          700;
      }


      /* ========================================
         手機
         ======================================== */

      @media(
        max-width:720px
      ){

        .heat-pv-switch{
          margin-bottom:
            16px;
        }

        .heat-pv-switch
        button{
          min-width:
            88px;

          padding:
            10px 18px;

          font-size:
            15px;
        }

        .turnover-header{
          align-items:
            flex-start;

          flex-direction:
            column;

          gap:
            4px;
        }

        #heatGrid
        .turnover-treemap{
          height:
            780px;
        }

        #heatGrid
        .turnover-inner{
          padding:
            8px;
        }

        .turnover-sector{
          font-size:
            11px;

          margin-bottom:
            4px;
        }

        .turnover-value{
          font-size:
            11px;
        }

        .turnover-average{
          margin-top:
            4px;

          font-size:
            8px;
        }

        .turnover-market{
          margin-top:
            3px;

          font-size:
            8px;
        }
      }

    `;

    document.head.appendChild(
      style
    );
  }

  /* =========================================================
     找到 heatmap 上方區域
     ========================================================= */

  function heatGrid() {
    return document.getElementById(
      "heatGrid"
    );
  }

  function heatParent() {
    return (
      heatGrid()
        ?.parentElement ||
      null
    );
  }

  /* =========================================================
     價 / 量按鈕
     ========================================================= */

  function ensureModeSwitch() {
    const grid =
      heatGrid();

    if (!grid) {
      return;
    }

    let wrap =
      document.getElementById(
        "heatPriceVolumeSwitch"
      );

    if (!wrap) {
      wrap =
        document.createElement(
          "div"
        );

      wrap.id =
        "heatPriceVolumeSwitch";

      wrap.className =
        "heat-pv-switch";

      wrap.innerHTML = `
        <button
          type="button"
          data-heat-mode="price"
        >
          價
        </button>

        <button
          type="button"
          data-heat-mode="volume"
        >
          量
        </button>
      `;

      grid.parentNode.insertBefore(
        wrap,
        grid
      );

      wrap.addEventListener(
        "click",
        event => {
          const button =
            event.target.closest(
              "[data-heat-mode]"
            );

          if (!button) {
            return;
          }

          const next =
            button.getAttribute(
              "data-heat-mode"
            );

          changeMode(
            next
          );
        }
      );
    }

    $$("#heatPriceVolumeSwitch [data-heat-mode]")
      .forEach(
        button => {
          button.classList.toggle(
            "active",
            button.getAttribute(
              "data-heat-mode"
            ) ===
              state.mode
          );
        }
      );
  }

  /* =========================================================
     價格模式控制項
     ========================================================= */

  function collectPriceControls() {
    const grid =
      heatGrid();

    const parent =
      heatParent();

    if (
      !grid ||
      !parent
    ) {
      return [];
    }

    const controls =
      [];

    /*
     * app.js 建立的期間與權重控制
     * 以文字內容輔助辨識
     */

    [
      ...parent.children
    ].forEach(
      element => {
        if (
          element === grid ||
          element.id ===
            "heatPriceVolumeSwitch" ||
          element.id ===
            "heatStrengthNote"
        ) {
          return;
        }

        const text =
          (
            element.textContent ||
            ""
          )
            .replace(
              /\s+/g,
              " "
            )
            .trim();

        const isPeriod =
          text.includes(
            "當日"
          ) &&
          text.includes(
            "5日"
          ) &&
          text.includes(
            "10日"
          ) &&
          text.includes(
            "20日"
          );

        const isWeight =
          text.includes(
            "市值加權"
          ) &&
          text.includes(
            "權重上限"
          );

        const isWeightNote =
          text.includes(
            "市值加權"
          ) &&
          text.includes(
            "公司實際市值"
          );

        const isBenchmark =
          (
            text.includes(
              "大盤"
            ) &&
            text.includes(
              "OTC"
            )
          ) ||
          text.includes(
            "指數收盤資料"
          );

        if (
          isPeriod ||
          isWeight ||
          isWeightNote ||
          isBenchmark
        ) {
          controls.push(
            element
          );
        }
      }
    );

    return [
      ...new Set(
        controls
      )
    ];
  }

  function hidePriceControls() {
    collectPriceControls()
      .forEach(
        element => {
          if (
            !element.hasAttribute(
              "data-heat-original-display"
            )
          ) {
            element.setAttribute(
              "data-heat-original-display",
              element.style.display ||
                ""
            );
          }

          element.style.display =
            "none";
        }
      );
  }

  function showPriceControls() {
    document
      .querySelectorAll(
        "[data-heat-original-display]"
      )
      .forEach(
        element => {
          element.style.display =
            element.getAttribute(
              "data-heat-original-display"
            ) || "";

          element.removeAttribute(
            "data-heat-original-display"
          );
        }
      );
  }

  /* =========================================================
     金標
     ========================================================= */

  function ensureStrengthNote() {
    const grid =
      heatGrid();

    if (!grid) {
      return;
    }

    let note =
      document.getElementById(
        "heatStrengthNote"
      );

    if (!note) {
      note =
        document.createElement(
          "div"
        );

      note.id =
        "heatStrengthNote";

      note.className =
        "heat-strength-note";

      grid.parentNode.insertBefore(
        note,
        grid
      );
    }

    if (
      state.mode !==
        "price" ||
      activePeriod() !==
        "1"
    ) {
      note.style.display =
        "none";

      return;
    }

    note.style.display =
      "";

    note.innerHTML = `
      <span
        class="heat-strength-swatch"
      ></span>

      <span>
        金色＝各族群近5日累積漲幅前2強
      </span>
    `;
  }

  function clearStrengthMarks() {
    $$("#heatGrid .heat-stock-top2")
      .forEach(
        row => {
          row.classList.remove(
            "heat-stock-top2"
          );
        }
      );

    $$("#heatGrid .heat-strength-rank")
      .forEach(
        label => {
          label.remove();
        }
      );
  }

  function tickerFromRow(
    row
  ) {
    const tickerNode =
      row.querySelector(
        ".t"
      );

    const values = [
      row.dataset?.ticker,
      tickerNode
        ?.textContent,
      row.textContent
    ];

    for (
      const value of values
    ) {
      const match =
        String(
          value || ""
        ).match(
          /\b\d{4,6}\b/
        );

      if (match) {
        return match[0];
      }
    }

    return "";
  }

  function latestNumber(
    values
  ) {
    if (
      !Array.isArray(
        values
      )
    ) {
      return null;
    }

    for (
      let i =
        values.length - 1;
      i >= 0;
      i -= 1
    ) {
      const n =
        number(
          values[i]
        );

      if (
        n !== null
      ) {
        return n;
      }
    }

    return null;
  }

  async function applyStrengthMarks(
    force = false
  ) {
    if (
      state.mode !==
        "price" ||
      activePeriod() !==
        "1" ||
      !heatVisible()
    ) {
      return;
    }

    const details =
      $$("#heatGrid .heat-detail");

    if (
      !details.length
    ) {
      return;
    }

    let data;

    try {
      data =
        await loadDetailData(
          force
        );
    } catch (error) {
      console.error(
        "[heat strength]",
        error
      );

      return;
    }

    if (
      state.mode !==
        "price" ||
      activePeriod() !==
        "1"
    ) {
      return;
    }

    clearStrengthMarks();

    details.forEach(
      detail => {
        const rows =
          $$(".heat-stock", detail);

        const ranked =
          rows
            .map(
              row => {
                const ticker =
                  tickerFromRow(
                    row
                  );

                const stock =
                  data
                    ?.stocks
                    ?.[ticker];

                const value =
                  latestNumber(
                    stock
                      ?.returns_by_period
                      ?.["5"] ||
                    stock
                      ?.returns
                  );

                return {
                  row,
                  ticker,
                  value
                };
              }
            )
            .filter(
              item =>
                item.ticker &&
                item.value !==
                  null
            )
            .sort(
              (
                a,
                b
              ) =>
                b.value -
                a.value
            );

        ranked
          .slice(
            0,
            2
          )
          .forEach(
            (
              item,
              index
            ) => {
              item.row.classList.add(
                "heat-stock-top2"
              );

              const tickerNode =
                item.row.querySelector(
                  ".t"
                );

              if (!tickerNode) {
                return;
              }

              const label =
                document.createElement(
                  "span"
                );

              label.className =
                "heat-strength-rank";

              label.textContent =
                `近5日漲幅第${
                  index + 1
                }`;

              tickerNode.insertAdjacentElement(
                "afterend",
                label
              );
            }
          );
      }
    );
  }

  /* =========================================================
     Format
     ========================================================= */

  function formatYi(
    value
  ) {
    const n =
      number(value);

    if (
      n === null
    ) {
      return "—";
    }

    const yi =
      n /
      100000000;

    if (
      yi >= 10
    ) {
      return (
        Math.round(
          yi
        ).toLocaleString(
          "zh-TW"
        ) +
        " 億"
      );
    }

    return (
      yi.toFixed(1) +
      " 億"
    );
  }

  function formatPct(
    value,
    digits = 2
  ) {
    const n =
      number(value);

    if (
      n === null
    ) {
      return "—";
    }

    return (
      (
        n >= 0
          ? "+"
          : ""
      ) +
      n.toFixed(
        digits
      ) +
      "%"
    );
  }

  function colorClass(
    change
  ) {
    const n =
      number(change);

    if (
      n === null
    ) {
      return "gray";
    }

    const abs =
      Math.abs(n);

    let level = 1;

    if (
      abs >= 3
    ) {
      level = 4;
    } else if (
      abs >= 2
    ) {
      level = 3;
    } else if (
      abs >= 1
    ) {
      level = 2;
    }

    return (
      n >= 0
        ? "r"
        : "g"
    ) + level;
  }

  /* =========================================================
     Treemap layout
     ========================================================= */

  function sumValues(
    items
  ) {
    return items.reduce(
      (
        sum,
        item
      ) =>
        sum +
        Math.max(
          0,
          Number(
            item.value ||
            0
          )
        ),
      0
    );
  }

  function splitItems(
    items
  ) {
    if (
      items.length <=
      1
    ) {
      return [
        items,
        []
      ];
    }

    const total =
      sumValues(
        items
      );

    const half =
      total / 2;

    let running = 0;
    let index = 1;

    for (
      let i = 0;
      i <
        items.length - 1;
      i += 1
    ) {
      running +=
        items[i].value;

      index =
        i + 1;

      if (
        running >=
        half
      ) {
        break;
      }
    }

    return [
      items.slice(
        0,
        index
      ),

      items.slice(
        index
      )
    ];
  }

  function treemapLayout(
    items,
    x = 0,
    y = 0,
    width = 100,
    height = 100,
    output = []
  ) {
    if (
      !items.length
    ) {
      return output;
    }

    if (
      items.length ===
      1
    ) {
      output.push({
        ...items[0],

        x,
        y,

        width,
        height
      });

      return output;
    }

    const [
      first,
      second
    ] =
      splitItems(
        items
      );

    const total =
      sumValues(
        items
      );

    const firstTotal =
      sumValues(
        first
      );

    const ratio =
      total > 0
        ? firstTotal /
          total
        : 0.5;

    if (
      width >=
      height
    ) {
      const firstWidth =
        width *
        ratio;

      treemapLayout(
        first,
        x,
        y,
        firstWidth,
        height,
        output
      );

      treemapLayout(
        second,
        x +
          firstWidth,
        y,
        width -
          firstWidth,
        height,
        output
      );
    } else {
      const firstHeight =
        height *
        ratio;

      treemapLayout(
        first,
        x,
        y,
        width,
        firstHeight,
        output
      );

      treemapLayout(
        second,
        x,
        y +
          firstHeight,
        width,
        height -
          firstHeight,
        output
      );
    }

    return output;
  }

  /* =========================================================
     取得族群市值漲跌
     ========================================================= */

  function sectorChangeMap(
    heatmap
  ) {
    const map =
      new Map();

    (
      heatmap
        ?.sectors ||
      []
    ).forEach(
      sector => {
        let change =
          number(
            sector
              .change_pct
          );

        /*
         * heatmap.json 新版若沒有 change_pct，
         * 嘗試其他常見欄位
         */

        if (
          change === null
        ) {
          change =
            number(
              sector
                .return_pct
            );
        }

        if (
          change === null
        ) {
          change =
            number(
              sector
                .market_return
            );
        }

        if (
          change === null
        ) {
          change =
            number(
              sector
                .returns_by_period
                ?.["1"]
            );
        }

        map.set(
          sector.name,
          change
        );
      }
    );

    return map;
  }

  /* =========================================================
     Render 成交金額 Treemap
     ========================================================= */

  async function renderVolume(
    force = false
  ) {
    if (
      state.mode !==
      "volume"
    ) {
      return;
    }

    const grid =
      heatGrid();

    if (!grid) {
      return;
    }

    state.renderingVolume =
      true;

    hidePriceControls();

    clearStrengthMarks();

    const note =
      document.getElementById(
        "heatStrengthNote"
      );

    if (note) {
      note.style.display =
        "none";
    }

    grid.innerHTML = `
      <div
        class="turnover-status"
      >
        成交金額資料載入中…
      </div>
    `;

    try {
      const [
        volumeData,
        heatmapData
      ] =
        await Promise.all([
          loadVolumeData(
            force
          ),

          loadJson(
            "./data/heatmap.json",
            force
          )
        ]);

      /*
       * await 期間若已切回價，
       * 不可以把量畫面蓋回去
       */

      if (
        state.mode !==
        "volume"
      ) {
        return;
      }

      const changeMap =
        sectorChangeMap(
          heatmapData
        );

      const items =
        (
          volumeData
            ?.sectors ||
          []
        )
          .map(
            sector => {
              const turnover =
                Number(
                  sector
                    .turnover ||
                  0
                );

              return {
                ...sector,

                value:
                  Math.max(
                    0,
                    turnover
                  ),

                change:
                  changeMap.get(
                    sector.name
                  )
              };
            }
          )
          .filter(
            sector =>
              sector.value >
              0
          )
          .sort(
            (
              a,
              b
            ) =>
              b.value -
              a.value
          );

      if (
        !items.length
      ) {
        grid.innerHTML = `
          <div
            class="turnover-status"
          >
            目前沒有成交金額資料
          </div>
        `;

        return;
      }

      const boxes =
        treemapLayout(
          items
        );

      const date =
        volumeData
          ?.date ||
        "";

      const sourceText =
        volumeData
          ?.estimated
          ? "盤中成交金額為即時累積估算"
          : "成交金額為已完成交易資料";

      grid.innerHTML = `

        <div
          class="turnover-header"
        >
          <div>
            <div
              class="turnover-header-main"
            >
              族群成交金額
            </div>

            <div
              class="turnover-header-sub"
            >
              方塊大小＝當日成交金額 ｜ 單位＝億元 ｜ ${sourceText}
            </div>
          </div>

          ${
            date
              ? `
                <div
                  class="turnover-date"
                >
                  ${date}
                </div>
              `
              : ""
          }
        </div>

        <div
          class="turnover-treemap"
        >
          ${
            boxes
              .map(
                box => {
                  const area =
                    box.width *
                    box.height;

                  const showAverage =
                    area >=
                    28;

                  const showMarket =
                    area >=
                    60;

                  const avgChange =
                    number(
                      box
                        .vs_avg5_pct
                    );

                  const avgChangeText =
                    avgChange ===
                      null
                      ? ""
                      : `（${formatPct(
                          avgChange,
                          0
                        )}）`;

                  const title = [
                    box.name,

                    `成交 ${formatYi(
                      box.turnover
                    )}`,

                    `5日均 ${formatYi(
                      box.avg5_turnover
                    )}`,

                    `市值 ${formatPct(
                      box.change
                    )}`
                  ].join(
                    "｜"
                  );

                  return `

                    <div
                      class="turnover-box"

                      style="
                        left:${box.x}%;
                        top:${box.y}%;
                        width:${box.width}%;
                        height:${box.height}%;
                      "
                    >
                      <div
                        class="
                          turnover-inner
                          ${colorClass(
                            box.change
                          )}
                        "

                        title="${title}"
                      >

                        <div
                          class="turnover-sector"
                        >
                          ${box.name}
                        </div>

                        <div
                          class="turnover-value"
                        >
                          成交
                          ${formatYi(
                            box.turnover
                          )}
                        </div>

                        ${
                          showAverage
                            ? `
                              <div
                                class="turnover-average"
                              >
                                5日均
                                ${formatYi(
                                  box.avg5_turnover
                                )}
                                ${avgChangeText}
                              </div>
                            `
                            : ""
                        }

                        ${
                          showMarket
                            ? `
                              <div
                                class="turnover-market"
                              >
                                市值
                                ${formatPct(
                                  box.change
                                )}
                              </div>
                            `
                            : ""
                        }

                      </div>
                    </div>

                  `;
                }
              )
              .join("")
          }
        </div>
      `;

    } catch (error) {
      console.error(
        "[turnover heatmap]",
        error
      );

      if (
        state.mode ===
        "volume"
      ) {
        grid.innerHTML = `
          <div
            class="turnover-status"
          >
            成交金額資料讀取失敗
          </div>
        `;
      }

    } finally {
      state.renderingVolume =
        false;
    }
  }

  /* =========================================================
     Render 價格模式
     ========================================================= */

  function restorePrice() {
    if (
      state.restoringPrice
    ) {
      return;
    }

    state.restoringPrice =
      true;

    showPriceControls();

    const note =
      document.getElementById(
        "heatStrengthNote"
      );

    if (note) {
      note.style.display =
        activePeriod() ===
          "1"
          ? ""
          : "none";
    }

    /*
     * 交回 app.js 原本 renderer
     */

    if (
      typeof
        window
          .renderHeatCurrentPeriod ===
      "function"
    ) {
      window
        .renderHeatCurrentPeriod();
    }

    requestAnimationFrame(
      () => {
        state.restoringPrice =
          false;

        ensureModeSwitch();

        ensureStrengthNote();

        setTimeout(
          () => {
            applyStrengthMarks(
              false
            );
          },
          80
        );
      }
    );
  }

  /* =========================================================
     切換模式
     ========================================================= */

  function changeMode(
    next
  ) {
    if (
      next !==
        "price" &&
      next !==
        "volume"
    ) {
      return;
    }

    if (
      next ===
      state.mode
    ) {
      /*
       * 量模式再點一次時，
       * 仍確保畫面真的是量
       */

      if (
        next ===
        "volume"
      ) {
        renderVolume(
          false
        );
      }

      return;
    }

    state.mode =
      next;

    ensureModeSwitch();

    if (
      next ===
      "volume"
    ) {
      hidePriceControls();

      clearStrengthMarks();

      renderVolume(
        true
      );

    } else {
      restorePrice();
    }
  }

  /* =========================================================
     防止 app.js 在量模式把價格畫面蓋回來
     ========================================================= */

  function protectVolumeMode() {
    const grid =
      heatGrid();

    if (!grid) {
      return;
    }

    if (
      state.observer
    ) {
      state.observer.disconnect();
    }

    state.observer =
      new MutationObserver(
        mutations => {
          /*
           * 我們自己正在 render 量，
           * 不處理自己的 DOM 變化
           */

          if (
            state.renderingVolume
          ) {
            return;
          }

          if (
            state.mode ===
            "volume"
          ) {
            /*
             * app.js 若把價格 heatmap
             * 寫回 #heatGrid，
             * 立刻重新畫成交金額 Treemap
             */

            const hasPriceHeat =
              !!grid.querySelector(
                "button.heat[data-sec]"
              );

            const hasVolumeHeat =
              !!grid.querySelector(
                ".turnover-treemap"
              );

            if (
              hasPriceHeat ||
              !hasVolumeHeat
            ) {
              clearTimeout(
                state.timer
              );

              state.timer =
                setTimeout(
                  () => {
                    if (
                      state.mode ===
                      "volume"
                    ) {
                      hidePriceControls();

                      renderVolume(
                        false
                      );
                    }
                  },
                  20
                );
            }

            return;
          }

          /*
           * 價格模式：
           * 原本 heatmap render 完後
           * 補金標
           */

          const meaningful =
            mutations.some(
              mutation =>
                mutation.type ===
                  "childList"
            );

          if (
            meaningful &&
            state.mode ===
              "price"
          ) {
            clearTimeout(
              state.timer
            );

            state.timer =
              setTimeout(
                () => {
                  ensureModeSwitch();

                  ensureStrengthNote();

                  applyStrengthMarks(
                    false
                  );
                },
                120
              );
          }
        }
      );

    state.observer.observe(
      grid,
      {
        childList:
          true,

        subtree:
          false
      }
    );
  }

  /* =========================================================
     Events
     ========================================================= */

  function bindEvents() {
    /*
     * 原本期間切換
     *
     * 只應該存在於價模式
     */

    window.addEventListener(
      "heatmap:period-changed",
      () => {
        if (
          state.mode ===
          "volume"
        ) {
          /*
           * 理論上量模式控制項已隱藏
           * 即使其他程式觸發事件，
           * 也不允許切回價格畫面
           */

          renderVolume(
            false
          );

          return;
        }

        clearStrengthMarks();

        ensureStrengthNote();

        setTimeout(
          () => {
            applyStrengthMarks(
              false
            );
          },
          80
        );
      }
    );

    /*
     * Heatmap 資料刷新
     */

    window.addEventListener(
      "heatmap:data-updated",
      () => {
        state.volumeData =
          null;

        state.volumeAt =
          0;

        state.detailData =
          null;

        state.detailAt =
          0;

        if (
          state.mode ===
          "volume"
        ) {
          renderVolume(
            true
          );
        } else {
          setTimeout(
            () => {
              applyStrengthMarks(
                true
              );
            },
            120
          );
        }
      }
    );

    /*
     * 點價格族群展開
     */

    document.addEventListener(
      "click",
      event => {
        if (
          state.mode !==
          "price"
        ) {
          return;
        }

        const button =
          event.target.closest(
            "#heatGrid button.heat[data-sec]"
          );

        if (!button) {
          return;
        }

        setTimeout(
          () => {
            applyStrengthMarks(
              false
            );
          },
          160
        );
      },
      {
        passive:
          true
      }
    );

    /*
     * iPhone Safari 返回頁面
     */

    window.addEventListener(
      "pageshow",
      () => {
        if (
          !heatVisible()
        ) {
          return;
        }

        ensureModeSwitch();

        if (
          state.mode ===
          "volume"
        ) {
          hidePriceControls();

          renderVolume(
            false
          );
        } else {
          showPriceControls();

          ensureStrengthNote();

          setTimeout(
            () => {
              applyStrengthMarks(
                false
              );
            },
            100
          );
        }
      }
    );

    document.addEventListener(
      "visibilitychange",
      () => {
        if (
          document.hidden ||
          !heatVisible()
        ) {
          return;
        }

        if (
          state.mode ===
          "volume"
        ) {
          hidePriceControls();

          renderVolume(
            false
          );
        }
      }
    );
  }

  /* =========================================================
     Public API
     ========================================================= */

  window.getHeatmapDisplayMode =
    function () {
      return state.mode;
    };

  window.setHeatmapDisplayMode =
    function (
      mode
    ) {
      changeMode(
        mode
      );
    };

  window.refreshHeatStrength =
    function (
      force = false
    ) {
      if (
        state.mode !==
        "price"
      ) {
        return;
      }

      return applyStrengthMarks(
        !!force
      );
    };

  window.refreshTurnoverHeatmap =
    function (
      force = false
    ) {
      if (
        state.mode !==
        "volume"
      ) {
        return;
      }

      return renderVolume(
        !!force
      );
    };

  /* =========================================================
     Init
     ========================================================= */

  function init() {
    injectStyles();

    ensureModeSwitch();

    ensureStrengthNote();

    protectVolumeMode();

    bindEvents();

    if (
      heatVisible()
    ) {
      setTimeout(
        () => {
          applyStrengthMarks(
            false
          );
        },
        250
      );
    }

    console.log(
      "[Heatmap] price / turnover mode ready"
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
        once:
          true
      }
    );
  } else {
    init();
  }

})();
