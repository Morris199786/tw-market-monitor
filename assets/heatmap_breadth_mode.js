/* =========================================================
   市場熱力圖：市值加權 / 均衡加權

   均衡加權：
   保留市值權重概念，但依有效成分股數量
   動態限制單一個股最高權重

   動態 Cap：
   2 檔      → 65%
   3 檔      → 50%
   4 檔      → 40%
   5–6 檔    → 35%
   7–9 檔    → 30%
   10 檔以上 → 25%

   族群廣度：
   ↑ 上漲家數 / 有效成分股數 · 上漲比例

   其他：
   1. 保留原本市值加權
   2. 展開族群時停止重新排序
   3. 支援 heatmap_auto_refresh.js
   ========================================================= */

(function () {
  const STORAGE_KEY = "tw_heat_weight_mode";

  let mode =
    localStorage.getItem(STORAGE_KEY) ||
    "market";

  /*
    相容舊版 localStorage
  */
  if (mode === "breadth") {
    mode = "balanced";
    localStorage.setItem(
      STORAGE_KEY,
      mode
    );
  }

  let heatData = null;
  let busy = false;
  let observerBusy = false;

  const $ = selector =>
    document.querySelector(selector);

  const $$ = selector =>
    [...document.querySelectorAll(selector)];


  /* =========================================================
     格式
     ========================================================= */

  function pct(value) {
    if (
      value === null ||
      value === undefined ||
      Number.isNaN(Number(value))
    ) {
      return "—";
    }

    const n = Number(value);

    return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
  }


  /* =========================================================
     依成分股數量決定單股權重上限
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
     權重上限 + 超額權重重新分配
     ========================================================= */

  function cappedWeights(values) {
    const raw = values.map(
      value =>
        Math.max(
          0,
          Number(value) || 0
        )
    );

    const total = raw.reduce(
      (sum, value) =>
        sum + value,
      0
    );

    if (!total) {
      return raw.map(() => 0);
    }

    const count = raw.length;

    const cap =
      getWeightCap(count);

    const base = raw.map(
      value =>
        value / total
    );

    const fixed =
      new Array(base.length)
        .fill(null);

    const active =
      new Set(
        base.map(
          (_, index) => index
        )
      );

    while (active.size) {
      const fixedSum =
        fixed.reduce(
          (sum, value) =>
            sum +
            (
              value === null
                ? 0
                : value
            ),
          0
        );

      const remain =
        Math.max(
          0,
          1 - fixedSum
        );

      const rawSum =
        [...active].reduce(
          (sum, index) =>
            sum + base[index],
          0
        );

      if (!rawSum) {
        const each =
          remain / active.size;

        [...active].forEach(
          index => {
            fixed[index] = each;
          }
        );

        break;
      }

      const trial =
        new Map(
          [...active].map(
            index => [
              index,
              (
                remain *
                base[index] /
                rawSum
              )
            ]
          )
        );

      const over =
        [...active].filter(
          index =>
            trial.get(index) >
            cap + 1e-12
        );

      if (!over.length) {
        [...active].forEach(
          index => {
            fixed[index] =
              trial.get(index);
          }
        );

        break;
      }

      over.forEach(
        index => {
          fixed[index] = cap;
          active.delete(index);
        }
      );
    }

    return fixed.map(
      value =>
        Number(value || 0)
    );
  }


  /* =========================================================
     計算均衡加權 + 族群廣度
     ========================================================= */

  function calcBalanced(sec) {
    const valid =
      (sec?.stocks || [])
        .filter(
          stock =>
            stock &&
            stock.change_pct !== null &&
            stock.change_pct !== undefined &&
            Number.isFinite(
              Number(
                stock.change_pct
              )
            ) &&
            Number(
              stock.market_cap || 0
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
              stock.market_cap || 0
            )
        )
      );

    const change =
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
      change_pct: change,
      up,
      down,
      flat,
      valid: valid.length,
      cap,

      weights:
        valid.map(
          (
            stock,
            index
          ) => ({
            ticker:
              String(
                stock.ticker || ""
              ),

            name:
              stock.name ||
              String(
                stock.ticker || ""
              ),

            raw_weight:
              Number(
                stock.weight || 0
              ),

            capped_weight:
              weights[index]
          })
        )
    };
  }


  /* =========================================================
     讀取 heatmap.json
     ========================================================= */

  async function loadHeatData() {
    try {
      const response =
        await fetch(
          "./data/heatmap.json?v=" +
          Date.now(),
          {
            cache: "no-store"
          }
        );

      if (!response.ok) {
        throw new Error(
          "HTTP " +
          response.status
        );
      }

      heatData =
        await response.json();

      return heatData;

    } catch (error) {
      console.error(
        "balanced heatmap load failed",
        error
      );

      return null;
    }
  }


  /* =========================================================
     熱力圖顏色
     ========================================================= */

  function heatClass(value) {
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
      $("#heatBreadthStyle")
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "heatBreadthStyle";

    style.textContent = `
      .heat-weight-mode {
        display: flex;
        gap: 6px;
        padding: 4px;
        border: 1px solid var(--line);
        border-radius: 14px;
        background: var(--soft);
      }

      .heat-weight-mode button {
        min-height: 36px;
        padding: 0 12px;
        border: 0;
        border-radius: 10px;
        background: transparent;
        color: var(--muted);
        font-size: 11px;
        font-weight: 850;
        cursor: pointer;
        white-space: nowrap;
      }

      .heat-weight-mode button.active {
        background: var(--card);
        color: var(--ink);
        box-shadow:
          0 2px 8px
          rgba(15, 23, 42, .10);
      }

      .heat-breadth-line {
        display: block;
        margin-top: 3px;
        font-size: 9px;
        font-weight: 750;
        opacity: .82;
      }

      .heat-breadth-help {
        margin-top: 7px;
        color: var(--muted);
        font-size: 9px;
        line-height: 1.45;
      }

      .heat-detail-breadth-note {
        margin: 8px 0 10px;
        padding: 9px 11px;
        border: 1px solid var(--line);
        border-radius: 12px;
        background: var(--soft);
        font-size: 10px;
        color: var(--muted);
        font-weight: 700;
      }

      @media(max-width: 720px) {
        .heat-sector-actions {
          flex-wrap: wrap;
        }

        .heat-weight-mode {
          width: 100%;
        }

        .heat-weight-mode button {
          flex: 1;
        }
      }
    `;

    document.head
      .appendChild(style);
  }


  /* =========================================================
     建立切換按鈕
     ========================================================= */

  function ensureToggle() {
    const actions =
      $(".heat-sector-actions");

    if (
      !actions ||
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

    wrap.setAttribute(
      "aria-label",
      "熱力圖權重模式"
    );

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

              await loadHeatData();

              updateToggle();

              await decorate();
            }
          );
        }
      );

    const copy =
      document.createElement(
        "div"
      );

    copy.className =
      "heat-breadth-help";

    copy.id =
      "heatBreadthHelp";

    copy.textContent =
      "均衡加權：依族群成分股數動態限制單一個股最高權重；卡片下方 ↑ x/y 為族群廣度";

    const control =
      $("#heatSectorControl");

    control?.appendChild(
      copy
    );

    updateToggle();
  }


  /* =========================================================
     更新切換按鈕 / 說明
     ========================================================= */

  function updateToggle() {
    $$(
      "[data-heat-weight]"
    ).forEach(
      button => {
        button.classList.toggle(
          "active",
          button.dataset
            .heatWeight === mode
        );
      }
    );

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

    const help =
      $("#heatBreadthHelp");

    if (help) {
      if (
        mode ===
        "balanced"
      ) {
        help.textContent =
          "均衡加權：2檔65%｜3檔50%｜4檔40%｜5–6檔35%｜7–9檔30%｜10檔以上25%；↑ x/y 為實際上漲家數";
      } else {
        help.textContent =
          "市值加權：依個股市值決定族群漲跌幅";
      }
    }
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
          String(sec.name),
          sec
        ]
      )
    );
  }


  /* =========================================================
     是否有 detail 展開
     ========================================================= */

  function hasOpenDetail() {
    return Boolean(
      document.querySelector(
        "#heatGrid .heat-detail"
      )
    );
  }


  /* =========================================================
     修改族群卡片
     ========================================================= */

  function decorateButtons() {
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
          calcBalanced(sec);

        const value =
          mode === "balanced"
            ? balanced.change_pct
            : sec.change_pct;

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
          heatClass(value)
        );

        const strong =
          button.querySelector(
            "strong"
          );

        if (strong) {
          strong.textContent =
            pct(value);
        }

        let line =
          button.querySelector(
            ".heat-breadth-line"
          );

        if (!line) {
          line =
            document.createElement(
              "span"
            );

          line.className =
            "heat-breadth-line";

          button.appendChild(
            line
          );
        }

        /*
          市值加權模式：
          不顯示族群廣度
        */

        if (
          mode !== "balanced"
        ) {
          line.style.display =
            "none";

          return;
        }

        line.style.display =
          "";

        if (balanced.valid) {
          const ratio =
            (
              balanced.up /
              balanced.valid *
              100
            ).toFixed(0);

          line.textContent =
            `↑ ${balanced.up}/${balanced.valid} · ${ratio}%上漲`;
        } else {
          line.textContent =
            "上漲家數 —";
        }
      }
    );

    /*
      detail 展開期間
      不允許重新排序
    */

    if (!hasOpenDetail()) {
      reorderButtons();
    }
  }


  /* =========================================================
     排序族群卡片

     有 detail 展開時禁止搬動 DOM
     ========================================================= */

  function reorderButtons() {
    const grid =
      $("#heatGrid");

    if (!grid) {
      return;
    }

    if (hasOpenDetail()) {
      return;
    }

    const map =
      sectorMap();

    const buttons =
      $$(
        "#heatGrid > button.heat[data-sec]"
      );

    buttons.sort(
      (a, b) => {
        const sectorA =
          map.get(
            String(
              a.dataset.sec
            )
          );

        const sectorB =
          map.get(
            String(
              b.dataset.sec
            )
          );

        const valueA =
          mode === "balanced"
            ? calcBalanced(
                sectorA
              ).change_pct
            : sectorA
                ?.change_pct;

        const valueB =
          mode === "balanced"
            ? calcBalanced(
                sectorB
              ).change_pct
            : sectorB
                ?.change_pct;

        const aNumber =
          valueA === null ||
          valueA === undefined ||
          Number.isNaN(
            Number(valueA)
          )
            ? -999
            : Number(valueA);

        const bNumber =
          valueB === null ||
          valueB === undefined ||
          Number.isNaN(
            Number(valueB)
          )
            ? -999
            : Number(valueB);

        return (
          bNumber -
          aNumber
        );
      }
    );

    buttons.forEach(
      button => {
        grid.appendChild(
          button
        );
      }
    );
  }


  /* =========================================================
     展開族群詳細資料
     ========================================================= */

  function decorateOpenDetail() {
    if (!heatData) {
      return;
    }

    const detail =
      $(
        "#heatGrid .heat-detail"
      );

    if (!detail) {
      return;
    }

    let openButton =
      detail.previousElementSibling;

    if (
      !openButton ||
      !openButton.matches?.(
        "button.heat[data-sec]"
      )
    ) {
      openButton =
        $$(
          "#heatGrid > button.heat[data-sec]"
        ).find(
          button =>
            button.nextElementSibling ===
            detail
        );
    }

    if (!openButton) {
      return;
    }

    const name =
      String(
        openButton.dataset.sec ||
        ""
      );

    const sec =
      (
        heatData.sectors ||
        []
      ).find(
        item =>
          String(
            item.name
          ) === name
      );

    if (!sec) {
      return;
    }

    const balanced =
      calcBalanced(sec);

    const detailValue =
      mode === "balanced"
        ? balanced.change_pct
        : sec.change_pct;

    /*
      修改 detail 原本的族群百分比
    */

    const candidates =
      [
        ...detail.querySelectorAll(
          "b, strong, span"
        )
      ];

    for (
      const element
      of candidates
    ) {
      const text =
        (
          element.textContent ||
          ""
        ).trim();

      if (
        /^[+-]?\d+(?:\.\d+)?%$/.test(
          text
        )
      ) {
        element.textContent =
          pct(detailValue);

        break;
      }
    }

    let note =
      detail.querySelector(
        ".heat-detail-breadth-note"
      );

    /*
      市值加權模式：
      移除均衡加權說明
    */

    if (
      mode !== "balanced"
    ) {
      if (note) {
        note.remove();
      }

      return;
    }

    if (!note) {
      note =
        document.createElement(
          "div"
        );

      note.className =
        "heat-detail-breadth-note";

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

    if (balanced.valid) {
      const capPercent =
        (
          balanced.cap *
          100
        ).toFixed(0);

      const upRatio =
        (
          balanced.up /
          balanced.valid *
          100
        ).toFixed(0);

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

        （${upRatio}%）

        ｜ 單股權重上限
        <b style="color:var(--ink)">
          ${capPercent}%
        </b>
      `;
    } else {
      note.textContent =
        "均衡加權資料不足";
    }
  }


  /* =========================================================
     全部更新
     ========================================================= */

  async function decorate() {
    if (busy) {
      return;
    }

    busy = true;

    try {
      ensureStyles();

      ensureToggle();

      if (!heatData) {
        await loadHeatData();
      }

      updateToggle();

      decorateButtons();

      decorateOpenDetail();

    } finally {
      busy = false;
    }
  }


  /* =========================================================
     監聽 heatGrid DOM

     只監聽第一層，
     避免修改卡片文字後自己觸發自己
     ========================================================= */

  function observe() {
    const grid =
      $("#heatGrid");

    if (!grid) {
      return;
    }

    const observer =
      new MutationObserver(
        mutations => {
          if (observerBusy) {
            return;
          }

          const structuralChange =
            mutations.some(
              mutation => {
                if (
                  mutation.type !==
                  "childList"
                ) {
                  return false;
                }

                const nodes = [
                  ...mutation.addedNodes,
                  ...mutation.removedNodes
                ];

                return nodes.some(
                  node =>
                    node.nodeType === 1 &&
                    (
                      node.matches?.(
                        "button.heat[data-sec]"
                      ) ||
                      node.classList
                        ?.contains(
                          "heat-detail"
                        )
                    )
                );
              }
            );

          if (!structuralChange) {
            return;
          }

          observerBusy = true;

          requestAnimationFrame(
            async () => {
              try {
                await decorate();

              } finally {
                observerBusy = false;
              }
            }
          );
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
     自動刷新

     heatmap_auto_refresh.js
     發出 heatmap:data-updated 後
     重新載入最新資料
     ========================================================= */

  function bindAutoRefresh() {
    window.addEventListener(
      "heatmap:data-updated",
      async () => {
        await loadHeatData();

        await decorate();
      }
    );
  }


  /* =========================================================
     初始化
     ========================================================= */

  async function init() {
    ensureStyles();

    await loadHeatData();

    bindAutoRefresh();

    let tries = 0;

    const timer =
      setInterval(
        async () => {
          tries += 1;

          if (
            $("#heatSectorControl") &&
            $("#heatGrid")
          ) {
            clearInterval(
              timer
            );

            ensureToggle();

            await decorate();

            observe();

          } else if (
            tries > 60
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
