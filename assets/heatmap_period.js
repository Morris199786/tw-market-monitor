/* 市場熱力圖期間切換：當日 / 5日 / 10日 / 20日 */
(() => {
  "use strict";

  const PERIODS = [
    ["1", "當日"],
    ["5", "5日"],
    ["10", "10日"],
    ["20", "20日"]
  ];

  const PERIOD_LABEL = {
    "1": "當日",
    "5": "近5日",
    "10": "近10日",
    "20": "近20日"
  };

  let activePeriod = "1";
  let heatData = null;
  let detailData = null;
  let dataPromise = null;
  let applying = false;
  let observer = null;
  let timer = null;

  window.__heatmapPeriodManaged = true;

  window.getHeatmapActivePeriod =
    () => activePeriod;


  /* =========================================================
     動態個股權重上限
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
      weightCap(valid.length);

    let rest =
      [...valid];

    let left =
      1;

    while (
      rest.length &&
      left > 1e-12
    ) {
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
        Number(arr[i]);

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
        ?.[String(ticker)];

    if (!stock) {
      return null;
    }

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
      lastNumber(series)
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
     大盤同期報酬
     ========================================================= */

  function benchmarkReturn() {
    const benchmark =
      detailData
        ?.benchmark;

    if (!benchmark) {
      return null;
    }

    /*
     * 5 / 10 / 20 日
     * 直接使用 stock_detail.json
     * 已經算好的上市加權指數累積報酬
     */
    if (
      activePeriod !==
      "1"
    ) {
      return (
        lastNumber(
          benchmark
            .returns_by_period
            ?.[activePeriod] ||
          (
            activePeriod ===
            "5"
              ? benchmark.returns
              : null
          )
        )
      );
    }

    /*
     * 當日：
     * stock_detail 的 5 日 benchmark
     * 是從同一基準日開始累積
     *
     * 用最後兩個累積報酬
     * 反推最後一個交易日漲跌幅
     */
    const arr =
      benchmark
        .returns_by_period
        ?.["5"] ||
      benchmark.returns ||
      [];

    const nums =
      arr
        .map(Number)
        .filter(
          Number.isFinite
        );

    if (
      nums.length < 2
    ) {
      return null;
    }

    const prev =
      nums[
        nums.length - 2
      ] / 100;

    const curr =
      nums[
        nums.length - 1
      ] / 100;

    return (
      (
        (
          1 + curr
        ) /
        (
          1 + prev
        ) -
        1
      ) *
      100
    );
  }


  /* =========================================================
     顯示
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


  /*
   * 不同期間使用不同色階
   *
   * 避免 10 / 20 日
   * 全部 +5% 以上都變成同一個最深色
   */

  function periodThresholds() {
    if (
      activePeriod ===
      "1"
    ) {
      return [
        0.5,
        1,
        2,
        3,
        5
      ];
    }

    if (
      activePeriod ===
      "5"
    ) {
      return [
        1,
        2.5,
        5,
        8,
        12
      ];
    }

    if (
      activePeriod ===
      "10"
    ) {
      return [
        2,
        5,
        10,
        15,
        22
      ];
    }

    return [
      3,
      7,
      14,
      22,
      32
    ];
  }


  /*
   * 台股：
   * 紅 = 漲
   * 綠 = 跌
   */

  function heatTone(value) {
    const n =
      Number(value);

    if (
      !Number.isFinite(n) ||
      n === 0
    ) {
      return {
        bg: "",
        fg: ""
      };
    }

    const a =
      Math.abs(n);

    const t =
      periodThresholds();

    let level =
      1;

    if (
      a >= t[4]
    ) {
      level = 5;

    } else if (
      a >= t[3]
    ) {
      level = 4;

    } else if (
      a >= t[2]
    ) {
      level = 3;

    } else if (
      a >= t[1]
    ) {
      level = 2;
    }

    const up = [
      "rgba(220,38,38,.72)",
      "rgba(220,38,38,.80)",
      "rgba(220,38,38,.88)",
      "rgba(185,28,28,.92)",
      "rgba(127,29,29,.96)"
    ];

    const down = [
      "rgba(22,163,74,.70)",
      "rgba(21,128,61,.78)",
      "rgba(21,128,61,.86)",
      "rgba(22,101,52,.92)",
      "rgba(20,83,45,.96)"
    ];

    return {
      bg:
        (
          n > 0
            ? up
            : down
        )[level - 1],

      fg:
        "#fff"
    };
  }


  /* =========================================================
     樣式
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
        margin:0 0 8px;
      }

      .heat-period-tabs{
        display:grid;
        grid-template-columns:
          repeat(
            4,
            minmax(0,1fr)
          );

        width:100%;
        padding:4px;

        border:
          1px solid
          var(--line);

        border-radius:14px;

        background:
          var(--card);
      }

      .heat-period-btn{
        appearance:none;

        border:0;
        border-radius:11px;

        padding:
          10px 8px;

        background:
          transparent;

        color:
          var(--muted);

        font:inherit;

        font-size:13px;
        font-weight:900;
        line-height:1;

        cursor:pointer;
      }

      .heat-period-btn.active{
        background:#111827;
        color:#fff;
      }

      html[data-theme="dark"]
      .heat-period-btn.active{
        background:#f8fafc;
        color:#111827;
      }

      .heat-period-meta{
        display:flex;
        align-items:center;
        justify-content:
          space-between;

        gap:12px;

        width:100%;
        min-height:28px;

        margin:
          0 0 4px;

        font-size:11px;
        font-weight:800;

        color:
          var(--muted);
      }

      .heat-period-benchmark{
        display:inline-flex;
        align-items:center;

        gap:6px;

        white-space:
          nowrap;
      }

      .heat-period-benchmark
      strong{
        font-size:13px;
      }

      .heat-period-benchmark
      .up{
        color:#dc2626;
      }

      .heat-period-benchmark
      .dn{
        color:#15803d;
      }

      @media(
        max-width:720px
      ){
        .heat-period-wrap{
          margin-bottom:6px;
        }

        .heat-period-btn{
          padding:
            10px 4px;

          font-size:12px;
        }

        .heat-period-meta{
          align-items:
            flex-start;

          flex-direction:
            column;

          gap:4px;

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

    let wrap =
      document.getElementById(
        "heatPeriodWrap"
      );

    if (!wrap) {
      wrap =
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

        <div
          class="heat-period-meta"
        >
          <span>
            族群採市值加權｜個股權重上限依族群家數動態調整
          </span>

          <span
            id="heatPeriodBenchmark"
            class="heat-period-benchmark"
          ></span>
        </div>
      `;

      grid
        .parentNode
        .insertBefore(
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
              button
                .dataset
                .heatPeriod ||
              "1"
            );

          if (
            !PERIODS.some(
              ([key]) =>
                key === next
            ) ||
            next ===
              activePeriod
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

          /*
           * 只有切換期間
           * 才重新排序
           */
          applyPeriod({
            reorder: true,
            force: false,
            reason: "period"
          });
        }
      );
    }
  }


  /* =========================================================
     大盤同期漲幅
     ========================================================= */

  function updateBenchmark() {
    const box =
      document.getElementById(
        "heatPeriodBenchmark"
      );

    if (!box) {
      return;
    }

    const value =
      benchmarkReturn();

    const cls =
      value > 0
        ? "up"
        : value < 0
        ? "dn"
        : "";

    const label =
      activePeriod ===
      "1"
        ? "大盤當日漲幅"
        : `大盤近${activePeriod}日漲幅`;

    box.innerHTML = `
      ${label}

      <strong
        class="${cls}"
      >
        ${pct(value)}
      </strong>
    `;
  }


  /* =========================================================
     載入資料
     ========================================================= */

  async function loadData(
    force = false
  ) {
    if (
      dataPromise &&
      !force
    ) {
      return dataPromise;
    }

    const stamp =
      Date.now();

    dataPromise =
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
            dataPromise =
              null;
          }
        );

    return dataPromise;
  }


  /* =========================================================
     更新族群卡片
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

    /*
     * 移除舊熱力圖色階 class
     *
     * 避免出現：
     * +18% 卻顯示綠色
     */

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
          button
            .classList
            .remove(
              className
            );
        }
      );

    const tone =
      heatTone(value);

    if (tone.bg) {
      button.style.setProperty(
        "background",
        tone.bg,
        "important"
      );

      button.style.setProperty(
        "color",
        tone.fg,
        "important"
      );

    } else {
      button.style.removeProperty(
        "background"
      );

      button.style.removeProperty(
        "color"
      );
    }

    button
      .dataset
      .periodReturn =
      Number.isFinite(value)
        ? String(value)
        : "";
  }


  /* =========================================================
     個股
     ========================================================= */

  function tickerFromRow(row) {
    const candidates = [
      row?.dataset?.ticker,

      row?.getAttribute?.(
        "data-ticker"
      ),

      row
        ?.querySelector?.(
          "[data-ticker]"
        )
        ?.getAttribute?.(
          "data-ticker"
        ),

      row
        ?.querySelector?.(
          ".t"
        )
        ?.textContent,

      row?.textContent
    ];

    for (
      const candidate
      of candidates
    ) {
      const match =
        String(
          candidate ||
          ""
        )
          .match(
            /\b\d{4,6}\b/
          );

      if (match) {
        return match[0];
      }
    }

    return "";
  }


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
          tickerFromRow(
            row
          );

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

        row
          .dataset
          .periodReturn =
          Number.isFinite(
            value
          )
            ? String(value)
            : "";
      }
    );

    /*
     * 展開後：
     * 個股依目前期間報酬排序
     *
     * 這只排序族群內個股
     * 不會改變整張族群熱力圖位置
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
                a
                  .dataset
                  .periodReturn
              );

            const bv =
              Number(
                b
                  .dataset
                  .periodReturn
              );

            return (
              (
                Number.isFinite(
                  bv
                )
                  ? bv
                  : -999999
              ) -
              (
                Number.isFinite(
                  av
                )
                  ? av
                  : -999999
              )
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
     族群重新排序
     ========================================================= */

  function reorderGrid() {
    const grid =
      document.getElementById(
        "heatGrid"
      );

    if (!grid) {
      return;
    }

    const children =
      [
        ...grid.children
      ];

    const groups =
      [];

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
            button
              .dataset
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
     套用期間
     ========================================================= */

  async function applyPeriod({
    reorder = false,
    force = false,
    reason = ""
  } = {}) {
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
            const sector =
              sectors.get(
                String(
                  button
                    .dataset
                    .sec ||
                  ""
                )
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

      updateBenchmark();

      /*
       * 最重要的修正：
       *
       * 只有：
       * 1. 第一次載入
       * 2. 切換期間
       * 3. 真正資料更新
       *
       * 才重新排序
       *
       * 點族群展開 / 收合
       * 絕對不重新排序
       */

      if (reorder) {
        reorderGrid();
      }

      /*
       * 通知金標模組：
       * 現在期間已改變
       */

      window.dispatchEvent(
        new CustomEvent(
          "heatmap:period-changed",
          {
            detail: {
              period:
                activePeriod,

              label:
                PERIOD_LABEL[
                  activePeriod
                ],

              reason
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
     展開族群後只補內容
     不重新排序
     ========================================================= */

  function scheduleDetailRefresh(
    delay = 100
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

          applyPeriod({
            reorder: false,
            force: false,
            reason: "detail"
          });
        },
        delay
      );
  }


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
            scheduleDetailRefresh(
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
     真正資料刷新
     ========================================================= */

  function bindRefresh() {
    window.addEventListener(
      "heatmap:data-updated",
      () => {
        heatData =
          null;

        detailData =
          null;

        setTimeout(
          () =>
            applyPeriod({
              reorder: true,
              force: true,
              reason: "data"
            }),
          150
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

        setTimeout(
          () =>
            applyPeriod({
              reorder: true,
              force: true,
              reason: "refresh"
            }),
          150
        );
      }
    );


    window.addEventListener(
      "tw-market:refresh-heatmap",
      () => {
        /*
         * refresh request 本身
         * 不先移動族群
         *
         * 等真的 data-updated
         * 才重新排序
         */

        setTimeout(
          () =>
            applyPeriod({
              reorder: false,
              force: false,
              reason:
                "refresh-request"
            }),
          180
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

    /*
     * 第一次載入
     * 依當日重新排序一次
     */

    setTimeout(
      () =>
        applyPeriod({
          reorder: true,
          force: false,
          reason: "init"
        }),
      200
    );

    console.log(
      "[Heat Period] v3 ready"
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
