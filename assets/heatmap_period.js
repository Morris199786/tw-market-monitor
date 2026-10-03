/* 市場熱力圖期間切換：當日 / 5日 / 10日 / 20日 */
(() => {
  "use strict";

  const PERIODS = [
    ["1", "當日"],
    ["5", "5日"],
    ["10", "10日"],
    ["20", "20日"]
  ];

  let activePeriod = "1";
  let heatData = null;
  let detailData = null;
  let promise = null;
  let timer = null;
  let observer = null;
  let applying = false;

  /* =========================================================
     動態個股權重上限

     1檔      100%
     2檔       65%
     3檔       50%
     4檔       40%
     5～6檔    35%
     7～9檔    30%
     10檔以上  25%
  ========================================================= */

  function weightCap(n) {
    if (n <= 1) return 1;
    if (n === 2) return 0.65;
    if (n === 3) return 0.50;
    if (n === 4) return 0.40;
    if (n <= 6) return 0.35;
    if (n <= 9) return 0.30;

    return 0.25;
  }

  /*
   * 先依市值算原始權重
   *
   * 超過上限者固定在上限
   * 剩餘權重再依剩餘股票市值比例重新分配
   *
   * 如果重新分配後又有人超過上限
   * 繼續迭代，直到全部符合上限
   */
  function cappedWeights(items) {
    const valid =
      items.filter(
        x =>
          Number.isFinite(x.cap) &&
          x.cap > 0
      );

    const out =
      new Map();

    if (!valid.length) {
      return out;
    }

    const limit =
      weightCap(
        valid.length
      );

    let rest =
      [...valid];

    let left =
      1;

    while (rest.length) {
      const sum =
        rest.reduce(
          (s, x) =>
            s + x.cap,
          0
        );

      if (!(sum > 0)) {
        const w =
          left /
          rest.length;

        rest.forEach(
          x =>
            out.set(
              x.ticker,
              w
            )
        );

        break;
      }

      const over =
        rest.filter(
          x =>
            (
              left *
              x.cap /
              sum
            ) >
            limit +
            1e-12
        );

      if (!over.length) {
        rest.forEach(
          x =>
            out.set(
              x.ticker,
              left *
              x.cap /
              sum
            )
        );

        break;
      }

      over.forEach(
        x =>
          out.set(
            x.ticker,
            limit
          )
      );

      left -=
        limit *
        over.length;

      rest =
        rest.filter(
          x =>
            !over.includes(x)
        );

      if (
        left <=
        1e-12
      ) {
        break;
      }
    }

    return out;
  }

  /* =========================================================
     報酬資料
  ========================================================= */

  function lastNumber(arr) {
    if (
      !Array.isArray(arr)
    ) {
      return null;
    }

    for (
      let i =
        arr.length - 1;
      i >= 0;
      i -= 1
    ) {
      const n =
        Number(
          arr[i]
        );

      if (
        Number.isFinite(n)
      ) {
        return n;
      }
    }

    return null;
  }

  function stockReturn(
    ticker,
    today
  ) {
    /*
     * 當日直接使用 heatmap.json
     * 原本的即時／收盤漲跌幅
     */
    if (
      activePeriod ===
      "1"
    ) {
      const n =
        Number(today);

      return (
        Number.isFinite(n)
          ? n
          : null
      );
    }

    const stock =
      detailData
        ?.stocks
        ?.[
          String(ticker)
        ];

    if (!stock) {
      return null;
    }

    /*
     * stock_detail.json 已有：
     * returns_by_period["5"]
     * returns_by_period["10"]
     * returns_by_period["20"]
     *
     * returns 保留作 5 日舊欄位 fallback
     */
    const series =
      stock
        .returns_by_period
        ?.[activePeriod] ||
      (
        activePeriod ===
        "5"
          ? stock.returns
          : null
      );

    return (
      lastNumber(
        series
      )
    );
  }

  /* =========================================================
     族群報酬
  ========================================================= */

  function sectorReturn(sec) {
    const usable =
      (
        sec.stocks ||
        []
      )
        .map(
          stock => ({
            ticker:
              String(
                stock.ticker ||
                ""
              ),

            cap:
              Number(
                stock.market_cap
              ),

            value:
              stockReturn(
                stock.ticker,
                stock.change_pct
              )
          })
        )
        .filter(
          x =>
            x.ticker &&
            Number.isFinite(
              x.cap
            ) &&
            x.cap > 0 &&
            Number.isFinite(
              x.value
            )
        );

    if (!usable.length) {
      return null;
    }

    const weights =
      cappedWeights(
        usable
      );

    let total =
      0;

    let used =
      0;

    usable.forEach(
      x => {
        const w =
          Number(
            weights.get(
              x.ticker
            )
          );

        if (
          !Number.isFinite(w) ||
          w <= 0
        ) {
          return;
        }

        total +=
          x.value *
          w;

        used +=
          w;
      }
    );

    return (
      used > 0
        ? total / used
        : null
    );
  }

  /* =========================================================
     顯示工具
  ========================================================= */

  function pct(value) {
    const n =
      Number(value);

    if (
      !Number.isFinite(n)
    ) {
      return "—";
    }

    return (
      `${
        n > 0
          ? "+"
          : ""
      }${n.toFixed(2)}%`
    );
  }

  function heatClass(
    value
  ) {
    const n =
      Number(value);

    if (
      !Number.isFinite(n) ||
      n === 0
    ) {
      return "";
    }

    const a =
      Math.abs(n);

    const prefix =
      n > 0
        ? "up"
        : "dn";

    if (a >= 5) {
      return (
        prefix +
        "5"
      );
    }

    if (a >= 3) {
      return (
        prefix +
        "4"
      );
    }

    if (a >= 2) {
      return (
        prefix +
        "3"
      );
    }

    if (a >= 1) {
      return (
        prefix +
        "2"
      );
    }

    return (
      prefix +
      "1"
    );
  }

  /* =========================================================
     期間按鈕樣式
  ========================================================= */

  function injectStyle() {
    if (
      document.getElementById(
        "heatPeriodStyle"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "heatPeriodStyle";

    style.textContent = `
      .heat-period-wrap{
        display:flex;
        align-items:center;
        gap:8px;
        flex-wrap:wrap;
        margin:0 0 14px;
      }

      .heat-period-tabs{
        display:inline-flex;
        align-items:center;
        gap:4px;

        padding:4px;

        border:1px solid
          var(--line);

        border-radius:12px;

        background:
          var(--card);
      }

      .heat-period-btn{
        appearance:none;

        border:0;

        border-radius:9px;

        padding:
          7px 12px;

        background:
          transparent;

        color:
          var(--muted);

        font:inherit;

        font-size:12px;

        font-weight:800;

        line-height:1;

        cursor:pointer;
      }

      .heat-period-btn.active{
        background:
          var(--ink);

        color:
          var(--card);
      }

      .heat-period-note{
        color:
          var(--muted);

        font-size:11px;

        font-weight:700;
      }

      @media(
        max-width:720px
      ){
        .heat-period-wrap{
          margin-bottom:
            10px;
        }

        .heat-period-tabs{
          width:100%;

          display:grid;

          grid-template-columns:
            repeat(
              4,
              minmax(
                0,
                1fr
              )
            );
        }

        .heat-period-btn{
          width:100%;

          padding:
            8px 5px;
        }

        .heat-period-note{
          width:100%;

          font-size:10px;
        }
      }
    `;

    document.head.appendChild(
      style
    );
  }

  /* =========================================================
     期間按鈕
  ========================================================= */

  function ensureControls() {
    const grid =
      document.getElementById(
        "heatGrid"
      );

    if (!grid) {
      return;
    }

    if (
      document.getElementById(
        "heatPeriodWrap"
      )
    ) {
      return;
    }

    const wrap =
      document.createElement(
        "div"
      );

    wrap.id =
      "heatPeriodWrap";

    wrap.className =
      "heat-period-wrap";

    wrap.innerHTML = `
      <div
        class="heat-period-tabs"
        role="tablist"
        aria-label="熱力圖期間"
      >
        ${
          PERIODS
            .map(
              (
                [
                  key,
                  label
                ]
              ) => `
                <button
                  type="button"
                  class="
                    heat-period-btn
                    ${
                      key ===
                      activePeriod
                        ? "active"
                        : ""
                    }
                  "
                  data-heat-period="${key}"
                >
                  ${label}
                </button>
              `
            )
            .join("")
        }
      </div>

      <span
        class="heat-period-note"
      >
        族群採市值加權｜個股權重上限依族群家數動態調整
      </span>
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
            "[data-heat-period]"
          );

        if (!button) {
          return;
        }

        const next =
          String(
            button.dataset
              .heatPeriod ||
            "1"
          );

        if (
          !PERIODS.some(
            ([key]) =>
              key === next
          )
        ) {
          return;
        }

        activePeriod =
          next;

        wrap
          .querySelectorAll(
            "[data-heat-period]"
          )
          .forEach(
            x => {
              x.classList.toggle(
                "active",
                x.dataset
                  .heatPeriod ===
                  activePeriod
              );
            }
          );

        scheduleApply(
          0
        );
      }
    );
  }

  /* =========================================================
     載入資料
  ========================================================= */

  async function loadData(
    force = false
  ) {
    if (
      promise &&
      !force
    ) {
      return promise;
    }

    const stamp =
      Date.now();

    promise =
      Promise.all([
        fetch(
          "./data/heatmap.json" +
          (
            force
              ? `?v=${stamp}`
              : ""
          ),
          {
            cache:
              force
                ? "no-store"
                : "default"
          }
        )
          .then(
            response => {
              if (
                !response.ok
              ) {
                throw new Error(
                  "heatmap.json HTTP " +
                  response.status
                );
              }

              return (
                response.json()
              );
            }
          ),

        fetch(
          "./data/stock_detail.json" +
          (
            force
              ? `?v=${stamp}`
              : ""
          ),
          {
            cache:
              force
                ? "no-store"
                : "default"
          }
        )
          .then(
            response => {
              if (
                !response.ok
              ) {
                throw new Error(
                  "stock_detail.json HTTP " +
                  response.status
                );
              }

              return (
                response.json()
              );
            }
          )
      ])
        .then(
          (
            [
              heat,
              detail
            ]
          ) => {
            heatData =
              heat;

            detailData =
              detail;
          }
        )
        .finally(
          () => {
            promise =
              null;
          }
        );

    return promise;
  }

  /* =========================================================
     更新族群方塊
  ========================================================= */

  function updateSectorButton(
    button,
    value
  ) {
    const strong =
      button.querySelector(
        "strong"
      );

    if (strong) {
      strong.textContent =
        pct(value);
    }

    [
      "up1",
      "up2",
      "up3",
      "up4",
      "up5",
      "dn1",
      "dn2",
      "dn3",
      "dn4",
      "dn5"
    ]
      .forEach(
        className => {
          button.classList.remove(
            className
          );
        }
      );

    const className =
      heatClass(
        value
      );

    if (className) {
      button.classList.add(
        className
      );
    }

    button.dataset
      .periodReturn =
      Number.isFinite(
        value
      )
        ? String(value)
        : "";
  }

  /* =========================================================
     更新展開後個股
  ========================================================= */

  function updateDetail(
    detail,
    sector,
    sectorValue
  ) {
    if (
      !detail ||
      !sector
    ) {
      return;
    }

    const headValue =
      detail.querySelector(
        ".heat-detail-head b span"
      );

    if (headValue) {
      headValue.textContent =
        pct(
          sectorValue
        );

      headValue.className =
        sectorValue > 0
          ? "up"
          : sectorValue < 0
          ? "dn"
          : "";
    }

    const stockMap =
      new Map(
        (
          sector.stocks ||
          []
        )
          .map(
            stock => [
              String(
                stock.ticker ||
                ""
              ),
              stock
            ]
          )
      );

    const rows =
      [
        ...detail
          .querySelectorAll(
            ".heat-stock"
          )
      ];

    rows.forEach(
      row => {
        const ticker =
          String(
            row
              .querySelector(
                ".t"
              )
              ?.textContent ||
            ""
          )
            .trim();

        const stock =
          stockMap.get(
            ticker
          );

        if (!stock) {
          return;
        }

        const value =
          stockReturn(
            ticker,
            stock.change_pct
          );

        const node =
          row.querySelector(
            ".v"
          );

        if (node) {
          node.textContent =
            pct(value);

          node.className =
            `v ${
              value > 0
                ? "up"
                : value < 0
                ? "dn"
                : ""
            }`;
        }

        row.dataset
          .periodReturn =
          Number.isFinite(
            value
          )
            ? String(value)
            : "";
      }
    );

    /*
     * 個股依目前選擇期間的報酬重新排序
     */
    const list =
      detail.querySelector(
        ".heat-stock-list"
      );

    if (list) {
      rows
        .sort(
          (
            a,
            b
          ) => {
            const av =
              Number(
                a.dataset
                  .periodReturn
              );

            const bv =
              Number(
                b.dataset
                  .periodReturn
              );

            const aa =
              Number.isFinite(av)
                ? av
                : -999999;

            const bb =
              Number.isFinite(bv)
                ? bv
                : -999999;

            return (
              bb -
              aa
            );
          }
        )
        .forEach(
          row =>
            list.appendChild(
              row
            )
        );
    }
  }

  /* =========================================================
     族群依目前期間重新排序
  ========================================================= */

  function reorderGrid() {
    const grid =
      document.getElementById(
        "heatGrid"
      );

    if (!grid) {
      return;
    }

    const groups =
      [];

    const children =
      [
        ...grid.children
      ];

    for (
      let i = 0;
      i < children.length;
      i += 1
    ) {
      const button =
        children[i];

      if (
        !button.matches?.(
          "button.heat[data-sec]"
        )
      ) {
        continue;
      }

      const detail =
        children[
          i + 1
        ]
          ?.matches?.(
            ".heat-detail"
          )
          ? children[
              i + 1
            ]
          : null;

      groups.push({
        button,
        detail,
        value:
          Number(
            button.dataset
              .periodReturn
          )
      });
    }

    groups
      .sort(
        (
          a,
          b
        ) => {
          const av =
            Number.isFinite(
              a.value
            )
              ? a.value
              : -999999;

          const bv =
            Number.isFinite(
              b.value
            )
              ? b.value
              : -999999;

          return (
            bv -
            av
          );
        }
      )
      .forEach(
        group => {
          grid.appendChild(
            group.button
          );

          if (
            group.detail
          ) {
            grid.appendChild(
              group.detail
            );
          }
        }
      );
  }

  /* =========================================================
     套用目前期間
  ========================================================= */

  async function applyPeriod(
    force = false
  ) {
    if (applying) {
      return;
    }

    const grid =
      document.getElementById(
        "heatGrid"
      );

    if (!grid) {
      return;
    }

    applying =
      true;

    try {
      ensureControls();

      if (
        !heatData ||
        !detailData ||
        force
      ) {
        await loadData(
          force
        );
      }

      const sectors =
        new Map(
          (
            heatData
              ?.sectors ||
            []
          )
            .map(
              sector => [
                String(
                  sector.name ||
                  ""
                ),
                sector
              ]
            )
        );

      grid
        .querySelectorAll(
          "button.heat[data-sec]"
        )
        .forEach(
          button => {
            const name =
              String(
                button.dataset
                  .sec ||
                ""
              );

            const sector =
              sectors.get(
                name
              );

            if (!sector) {
              return;
            }

            const value =
              sectorReturn(
                sector
              );

            updateSectorButton(
              button,
              value
            );

            const next =
              button
                .nextElementSibling;

            const detail =
              next
                ?.matches?.(
                  ".heat-detail"
                )
                ? next
                : null;

            if (detail) {
              updateDetail(
                detail,
                sector,
                value
              );
            }
          }
        );

      reorderGrid();

      window.dispatchEvent(
        new CustomEvent(
          "heatmap:period-changed",
          {
            detail: {
              period:
                activePeriod
            }
          }
        )
      );

    } catch (error) {
      console.error(
        "[Heat Period]",
        error
      );

    } finally {
      applying =
        false;
    }
  }

  /* =========================================================
     Debounce
  ========================================================= */

  function scheduleApply(
    delay = 80,
    force = false
  ) {
    if (timer) {
      clearTimeout(
        timer
      );
    }

    timer =
      setTimeout(
        () => {
          timer =
            null;

          applyPeriod(
            force
          );
        },
        delay
      );
  }

  /* =========================================================
     監聽原本 heatmap render
  ========================================================= */

  function observeGrid() {
    const grid =
      document.getElementById(
        "heatGrid"
      );

    if (!grid) {
      return;
    }

    if (observer) {
      observer.disconnect();
    }

    observer =
      new MutationObserver(
        mutations => {
          if (applying) {
            return;
          }

          const changed =
            mutations.some(
              mutation =>
                mutation.type ===
                  "childList" &&
                mutation.target ===
                  grid
            );

          if (changed) {
            scheduleApply(
              100
            );
          }
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
     資料更新事件
  ========================================================= */

  function bindRefresh() {
    window.addEventListener(
      "heatmap:data-updated",
      () => {
        heatData =
          null;

        detailData =
          null;

        scheduleApply(
          150,
          true
        );
      }
    );

    window.addEventListener(
      "tw-market:refreshed",
      event => {
        if (
          event
            ?.detail
            ?.page !==
          "heat"
        ) {
          return;
        }

        heatData =
          null;

        detailData =
          null;

        scheduleApply(
          150,
          true
        );
      }
    );

    window.addEventListener(
      "tw-market:refresh-heatmap",
      () => {
        scheduleApply(
          180,
          false
        );
      }
    );
  }

  /* =========================================================
     初始化
  ========================================================= */

  function init() {
    injectStyle();

    ensureControls();

    observeGrid();

    bindRefresh();

    scheduleApply(
      200
    );

    console.log(
      "[Heat Period] ready"
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
