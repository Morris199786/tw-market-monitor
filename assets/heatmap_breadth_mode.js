/* =========================================================
   市場熱力圖：市值加權 / 族群廣度（單一個股權重上限 25%）
   2026-10-01

   功能：
   1. 保留原本「市值加權」
   2. 新增「族群廣度」
   3. 族群廣度單一個股最高權重 25%
   4. 超過 25% 的權重重新分配給其他成分股
   5. 顯示族群上漲家數比例
   6. 切換模式後重新依族群漲跌幅排序
   ========================================================= */

(function () {
  const WEIGHT_CAP = 0.25;
  const STORAGE_KEY = "tw_heat_weight_mode";

  let mode =
    localStorage.getItem(STORAGE_KEY) ||
    "market";

  let heatData = null;
  let busy = false;

  const $ = selector =>
    document.querySelector(selector);

  const $$ = selector =>
    [...document.querySelectorAll(selector)];


  /* =========================================================
     基本格式
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
     25% 權重上限

     原本：
     個股市值 / 族群總市值

     新模式：
     單一個股最高 25%
     超出的權重重新分配
     ========================================================= */

  function cappedWeights(
    values,
    cap = WEIGHT_CAP
  ) {
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
     計算族群廣度模式漲跌幅
     ========================================================= */

  function calcBreadth(sec) {
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
        weights: []
      };
    }

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
        "breadth heatmap load failed",
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
        border:
          1px solid
          var(--line);
        border-radius: 12px;
        background:
          var(--soft);
        font-size: 10px;
        color:
          var(--muted);
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
        data-heat-weight="breadth"
      >
        族群廣度
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
      "族群廣度：單一個股最高權重 25%，超額權重重新分配，並顯示上漲家數";

    const control =
      $("#heatSectorControl");

    control?.appendChild(
      copy
    );

    updateToggle();
  }


  /* =========================================================
     更新切換按鈕狀態
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
        "breadth"
      ) {
        hero.textContent =
          `${count} 個自訂族群｜族群廣度（單股上限25%）｜紅漲綠跌`;
      } else {
        hero.textContent =
          `${count} 個自訂族群｜市值加權｜紅漲綠跌｜可直接下拉選族群`;
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
     修改熱力圖族群卡片
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

        const breadth =
          calcBreadth(sec);

        const value =
          mode === "breadth"
            ? breadth.change_pct
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

        if (breadth.valid) {
          const ratio =
            (
              breadth.up /
              breadth.valid *
              100
            ).toFixed(0);

          line.textContent =
            `↑ ${breadth.up}/${breadth.valid} · ${ratio}%上漲`;
        } else {
          line.textContent =
            "上漲家數 —";
        }
      }
    );

    reorderButtons();
  }


  /* =========================================================
     根據目前模式重新排序
     ========================================================= */

  function reorderButtons() {
    const grid =
      $("#heatGrid");

    if (!grid) {
      return;
    }

    /*
      展開族群詳細資料時，
      不重新搬動 DOM，
      避免 detail 卡片位置跑掉
    */

    if (
      $(
        "#heatGrid .heat-detail"
      )
    ) {
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
          mode === "breadth"
            ? calcBreadth(
                sectorA
              ).change_pct
            : sectorA
                ?.change_pct;

        const valueB =
          mode === "breadth"
            ? calcBreadth(
                sectorB
              ).change_pct
            : sectorB
                ?.change_pct;

        const aNumber =
          valueA === null ||
          valueA === undefined
            ? -999
            : Number(valueA);

        const bNumber =
          valueB === null ||
          valueB === undefined
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
     展開族群時顯示廣度資訊
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

    const openButton =
      $$(
        "#heatGrid > button.heat[data-sec]"
      ).find(
        button =>
          button.nextElementSibling ===
          detail
      );

    const name =
      openButton
        ?.dataset.sec ||
      detail
        .querySelector("b")
        ?.textContent
        ?.trim();

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

    const breadth =
      calcBreadth(sec);

    let note =
      detail.querySelector(
        ".heat-detail-breadth-note"
      );

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

    if (breadth.valid) {
      note.innerHTML = `
        族群廣度
        <b style="color:var(--ink)">
          ${pct(
            breadth.change_pct
          )}
        </b>

        ｜ 上漲
        <b style="color:var(--ink)">
          ${breadth.up}/${breadth.valid}
        </b>

        ｜ 單一個股權重最高 25%
      `;
    } else {
      note.textContent =
        "族群廣度資料不足";
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
     監聽原本熱力圖重新 render
     ========================================================= */

  function observe() {
    const grid =
      $("#heatGrid");

    if (!grid) {
      return;
    }

    const observer =
      new MutationObserver(
        () => {
          setTimeout(
            decorate,
            0
          );
        }
      );

    observer.observe(
      grid,
      {
        childList: true,
        subtree: true
      }
    );
  }


  /* =========================================================
     初始化
     ========================================================= */

  async function init() {
    ensureStyles();

    await loadHeatData();

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
