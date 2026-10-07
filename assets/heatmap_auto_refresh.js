/* =========================================================
   Heatmap 強勢股金標 + 價 / 量模式
   2026-10-07

   價：
   - 完全保留 app.js 原本熱力圖
   - 當日模式顯示各族群近5日漲幅前2金標

   量：
   - 方塊面積 = 當日族群成交金額
   - 顏色 = 當日族群市值漲跌幅（紅漲綠跌）
   - 固定單位 = 億元
   - 顯示當日成交、5日均、相對5日均變化
   ========================================================= */

(function () {
  "use strict";

  const CACHE_MS =
    5 * 60 * 1000;

  let detailCache = null;
  let detailAt = 0;

  let volumeCache = null;
  let volumeAt = 0;

  let mode = "price";
  let observer = null;
  let applying = false;

  const $ =
    selector =>
      document.querySelector(
        selector
      );

  const num =
    value =>
      Number.isFinite(
        Number(value)
      )
        ? Number(value)
        : null;

  /* =========================================================
     Heatmap 是否顯示
     ========================================================= */

  function visible() {
    return !!(
      $("#heat")
        ?.classList
        .contains("active")
    );
  }

  /* =========================================================
     目前價格熱力圖期間
     ========================================================= */

  function period() {
    return (
      typeof
        window
          .getHeatmapActivePeriod ===
      "function"
    )
      ? String(
          window
            .getHeatmapActivePeriod() ||
          "1"
        )
      : "1";
  }

  /* =========================================================
     JSON
     ========================================================= */

  async function getJson(
    url,
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
        `${url}?v=${version}`,
        {
          cache: "no-store"
        }
      );

    if (!response.ok) {
      throw new Error(
        `${url} HTTP ${response.status}`
      );
    }

    return response.json();
  }

  async function getDetail(
    force = false
  ) {
    if (
      !force &&
      detailCache &&
      Date.now() -
        detailAt <
        CACHE_MS
    ) {
      return detailCache;
    }

    detailCache =
      await getJson(
        "./data/stock_detail.json",
        force
      );

    detailAt =
      Date.now();

    return detailCache;
  }

  async function getVolume(
    force = false
  ) {
    if (
      !force &&
      volumeCache &&
      Date.now() -
        volumeAt <
        CACHE_MS
    ) {
      return volumeCache;
    }

    volumeCache =
      await getJson(
        "./data/sector_turnover.json",
        force
      );

    volumeAt =
      Date.now();

    return volumeCache;
  }

  /* =========================================================
     CSS
     ========================================================= */

  function injectStyle() {
    if (
      $("#heatPriceVolumeStyle")
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "heatPriceVolumeStyle";

    style.textContent = `

      /* =========================
         價 / 量切換
         ========================= */

      .heat-pv-wrap{
        display:flex;
        align-items:center;
        gap:8px;
        margin:0 0 12px;
        flex-wrap:wrap;
      }

      .heat-pv-tabs{
        display:inline-flex;
        padding:3px;

        border:
          1px solid
          rgba(
            148,
            163,
            184,
            .30
          );

        border-radius:12px;

        background:
          rgba(
            148,
            163,
            184,
            .10
          );
      }

      .heat-pv-btn{
        border:0;

        background:
          transparent;

        color:
          inherit;

        font:
          inherit;

        font-size:14px;
        font-weight:800;

        padding:
          8px 18px;

        border-radius:
          9px;

        cursor:pointer;
      }

      .heat-pv-btn.active{
        background:#fff;

        box-shadow:
          0 1px 5px
          rgba(
            15,
            23,
            42,
            .12
          );

        color:#111827;
      }

      html[data-theme="dark"]
      .heat-pv-btn.active{
        background:#29313d;
        color:#f8fafc;
      }

      /* =========================
         金標說明
         ========================= */

      .heat-strength-note{
        display:flex;
        align-items:center;
        gap:8px;

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

        color:#765314;

        font-size:
          10px;

        font-weight:
          800;
      }

      .heat-strength-swatch{
        width:11px;
        height:11px;

        border-radius:
          4px;

        background:
          #f5d76e;
      }

      /* =========================
         近5日 Top 2
         ========================= */

      #heatGrid
      .heat-stock-top2{
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

        margin-left:
          6px;

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
      .heat-stock-top2{
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

      /* =========================
         成交值 Treemap
         ========================= */

      .turnover-treemap{
        position:relative;

        width:100%;
        height:680px;

        border-radius:
          16px;

        overflow:hidden;

        background:
          rgba(
            148,
            163,
            184,
            .08
          );
      }

      .turnover-box{
        position:absolute;

        box-sizing:
          border-box;

        padding:3px;
      }

      .turnover-inner{
        width:100%;
        height:100%;

        box-sizing:
          border-box;

        border-radius:
          10px;

        padding:12px;

        overflow:hidden;

        color:#fff;

        display:flex;

        flex-direction:
          column;

        justify-content:
          center;

        box-shadow:
          inset
          0 0 0 1px
          rgba(
            255,
            255,
            255,
            .18
          );
      }

      /* 漲 */

      .turnover-inner.r4{
        background:#dc2626;
      }

      .turnover-inner.r3{
        background:#e54848;
      }

      .turnover-inner.r2{
        background:#ef6b6b;
      }

      .turnover-inner.r1{
        background:#b76b6b;
      }

      /* 跌 */

      .turnover-inner.g4{
        background:#16834b;
      }

      .turnover-inner.g3{
        background:#29965b;
      }

      .turnover-inner.g2{
        background:#4a9d70;
      }

      .turnover-inner.g1{
        background:#668979;
      }

      .turnover-inner.gray{
        background:#6b7280;
      }

      .turnover-name{
        font-size:
          clamp(
            12px,
            1.35vw,
            22px
          );

        font-weight:
          900;

        line-height:
          1.05;

        margin-bottom:
          7px;
      }

      .turnover-main{
        font-size:
          clamp(
            12px,
            1.2vw,
            20px
          );

        font-weight:
          900;

        line-height:
          1.15;
      }

      .turnover-sub{
        font-size:
          clamp(
            9px,
            .85vw,
            14px
          );

        font-weight:
          750;

        line-height:
          1.35;

        margin-top:
          5px;
      }

      .turnover-note{
        font-size:
          12px;

        opacity:
          .72;

        margin:
          0 0 10px;
      }

      /* =========================
         手機
         ========================= */

      @media(
        max-width:720px
      ){

        .heat-pv-btn{
          font-size:
            13px;

          padding:
            7px 16px;
        }

        .turnover-treemap{
          height:
            760px;
        }

        .turnover-inner{
          padding:
            8px;
        }

        .turnover-name{
          font-size:
            11px;

          margin-bottom:
            4px;
        }

        .turnover-main{
          font-size:
            11px;
        }

        .turnover-sub{
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
     價 / 量按鈕
     ========================================================= */

  function ensureTabs() {
    const grid =
      $("#heatGrid");

    if (!grid) {
      return;
    }

    let wrap =
      $("#heatPriceVolumeWrap");

    if (!wrap) {
      wrap =
        document.createElement(
          "div"
        );

      wrap.id =
        "heatPriceVolumeWrap";

      wrap.className =
        "heat-pv-wrap";

      wrap.innerHTML = `
        <div
          class="heat-pv-tabs"
        >
          <button
            type="button"
            class="
              heat-pv-btn
              active
            "
            data-heat-view="price"
          >
            價
          </button>

          <button
            type="button"
            class="heat-pv-btn"
            data-heat-view="volume"
          >
            量
          </button>
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
            event
              .target
              .closest(
                "[data-heat-view]"
              );

          if (!button) {
            return;
          }

          setMode(
            button.dataset
              .heatView
          );
        }
      );
    }

    wrap
      .querySelectorAll(
        "[data-heat-view]"
      )
      .forEach(
        button => {
          button
            .classList
            .toggle(
              "active",
              button.dataset
                .heatView ===
                mode
            );
        }
      );
  }

  /* =========================================================
     金標說明
     ========================================================= */

  function ensureNote() {
    const grid =
      $("#heatGrid");

    if (!grid) {
      return;
    }

    let note =
      $("#heatStrengthNote");

    if (!note) {
      note =
        document.createElement(
          "div"
        );

      note.id =
        "heatStrengthNote";

      note.className =
        "heat-strength-note";

      grid
        .parentNode
        .insertBefore(
          note,
          grid
        );
    }

    if (
      mode !== "price" ||
      period() !== "1"
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

  /* =========================================================
     金標工具
     ========================================================= */

  function ticker(row) {
    return (
      row?.textContent ||
      ""
    )
      .match(
        /\b\d{4,6}\b/
      )?.[0] || "";
  }

  function last(arr) {
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
      const value =
        num(arr[i]);

      if (
        value !== null
      ) {
        return value;
      }
    }

    return null;
  }

  function clearGold() {
    document
      .querySelectorAll(
        "#heatGrid .heat-stock-top2"
      )
      .forEach(
        element => {
          element
            .classList
            .remove(
              "heat-stock-top2"
            );
        }
      );

    document
      .querySelectorAll(
        "#heatGrid .heat-strength-rank"
      )
      .forEach(
        element => {
          element.remove();
        }
      );
  }

  async function applyGold(
    force = false
  ) {
    if (
      mode !== "price" ||
      period() !== "1" ||
      !visible()
    ) {
      return;
    }

    const details =
      [
        ...document
          .querySelectorAll(
            "#heatGrid .heat-detail"
          )
      ];

    if (!details.length) {
      return;
    }

    const data =
      await getDetail(
        force
      );

    clearGold();

    details.forEach(
      detail => {
        [
          ...detail
            .querySelectorAll(
              ".heat-stock"
            )
        ]
          .map(
            row => {
              const stockTicker =
                ticker(row);

              const stock =
                data
                  ?.stocks
                  ?.[
                    stockTicker
                  ];

              return {
                row,

                value:
                  last(
                    stock
                      ?.returns_by_period
                      ?.["5"] ||
                    stock
                      ?.returns
                  )
              };
            }
          )
          .filter(
            item =>
              item.value !==
              null
          )
          .sort(
            (a, b) =>
              b.value -
              a.value
          )
          .slice(
            0,
            2
          )
          .forEach(
            (
              item,
              index
            ) => {
              item
                .row
                .classList
                .add(
                  "heat-stock-top2"
                );

              const target =
                item
                  .row
                  .querySelector(
                    ".t"
                  );

              if (!target) {
                return;
              }

              const label =
                document
                  .createElement(
                    "span"
                  );

              label.className =
                "heat-strength-rank";

              label.textContent =
                `近5日漲幅第${
                  index + 1
                }`;

              target
                .insertAdjacentElement(
                  "afterend",
                  label
                );
            }
          );
      }
    );
  }

  /* =========================================================
     成交金額格式
     ========================================================= */

  function fmtYi(value) {
    const yi =
      Number(
        value || 0
      ) /
      100000000;

    if (yi >= 10) {
      return (
        Math
          .round(yi)
          .toLocaleString(
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

  function pct(value) {
    const n =
      num(value);

    if (n === null) {
      return "—";
    }

    return (
      (
        n >= 0
          ? "+"
          : ""
      ) +
      n.toFixed(2) +
      "%"
    );
  }

  /* =========================================================
     漲跌顏色
     ========================================================= */

  function heatClass(value) {
    const n =
      num(value);

    if (n === null) {
      return "gray";
    }

    const abs =
      Math.abs(n);

    const level =
      abs >= 3
        ? 4
        : abs >= 2
          ? 3
          : abs >= 1
            ? 2
            : 1;

    return (
      n >= 0
        ? "r"
        : "g"
    ) + level;
  }

  /* =========================================================
     Treemap layout

     面積依成交金額比例
     ========================================================= */

  function layout(
    items,
    x,
    y,
    width,
    height,
    output = []
  ) {
    if (!items.length) {
      return output;
    }

    if (
      items.length === 1
    ) {
      output.push({
        ...items[0],
        x,
        y,
        w: width,
        h: height
      });

      return output;
    }

    const total =
      items.reduce(
        (
          sum,
          item
        ) =>
          sum +
          item.value,
        0
      );

    let accumulated = 0;
    let cut = 1;

    for (
      let i = 0;
      i <
        items.length - 1;
      i += 1
    ) {
      accumulated +=
        items[i].value;

      if (
        accumulated >=
        total / 2
      ) {
        cut =
          i + 1;

        break;
      }
    }

    const first =
      items.slice(
        0,
        cut
      );

    const second =
      items.slice(
        cut
      );

    const firstTotal =
      first.reduce(
        (
          sum,
          item
        ) =>
          sum +
          item.value,
        0
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
      layout(
        first,
        x,
        y,
        width *
          ratio,
        height,
        output
      );

      layout(
        second,
        x +
          width *
            ratio,
        y,
        width *
          (
            1 -
            ratio
          ),
        height,
        output
      );
    } else {
      layout(
        first,
        x,
        y,
        width,
        height *
          ratio,
        output
      );

      layout(
        second,
        x,
        y +
          height *
            ratio,
        width,
        height *
          (
            1 -
            ratio
          ),
        output
      );
    }

    return output;
  }

  /* =========================================================
     量熱力圖
     ========================================================= */

  async function renderVolume(
    force = false
  ) {
    const grid =
      $("#heatGrid");

    if (!grid) {
      return;
    }

    const [
      volumeData,
      heatData
    ] =
      await Promise.all([
        getVolume(force),

        getJson(
          "./data/heatmap.json",
          force
        )
      ]);

    const changes =
      new Map(
        (
          heatData
            .sectors ||
          []
        )
          .map(
            sector => [
              sector.name,
              num(
                sector
                  .change_pct
              )
            ]
          )
      );

    const items =
      (
        volumeData
          .sectors ||
        []
      )
        .map(
          sector => ({
            ...sector,

            value:
              Number(
                sector
                  .turnover ||
                0
              ),

            change:
              changes.get(
                sector.name
              )
          })
        )
        .filter(
          sector =>
            sector.value >
            0
        )
        .sort(
          (a, b) =>
            b.value -
            a.value
        );

    const boxes =
      layout(
        items,
        0,
        0,
        100,
        100,
        []
      );

    const estimate =
      volumeData
        .estimated
        ? "盤中成交金額為即時估算；"
        : "";

    grid.innerHTML = `

      <div
        class="turnover-note"
      >
        ${estimate}
        成交金額與5日均統一使用「億元」
      </div>

      <div
        class="turnover-treemap"
      >

        ${
          boxes
            .map(
              box => {
                const area =
                  box.w *
                  box.h;

                const tiny =
                  area < 80;

                const veryTiny =
                  area < 35;

                const avgChange =
                  box
                    .vs_avg5_pct;

                const avgText =
                  avgChange ===
                    null ||
                  avgChange ===
                    undefined
                    ? ""
                    : `（${
                        avgChange >= 0
                          ? "+"
                          : ""
                      }${
                        Number(
                          avgChange
                        ).toFixed(0)
                      }%）`;

                return `
                  <div
                    class="turnover-box"

                    style="
                      left:${box.x}%;
                      top:${box.y}%;
                      width:${box.w}%;
                      height:${box.h}%;
                    "
                  >
                    <div
                      class="
                        turnover-inner
                        ${
                          heatClass(
                            box.change
                          )
                        }
                      "

                      title="
                        ${box.name}
                        ｜成交 ${fmtYi(
                          box.turnover
                        )}
                        ｜5日均 ${fmtYi(
                          box.avg5_turnover
                        )}
                        ｜市值 ${pct(
                          box.change
                        )}
                      "
                    >

                      <div
                        class="turnover-name"
                      >
                        ${box.name}
                      </div>

                      <div
                        class="turnover-main"
                      >
                        成交
                        ${fmtYi(
                          box.turnover
                        )}
                      </div>

                      ${
                        veryTiny
                          ? ""
                          : `
                            <div
                              class="turnover-sub"
                            >
                              5日均
                              ${fmtYi(
                                box.avg5_turnover
                              )}
                              ${avgText}
                            </div>
                          `
                      }

                      ${
                        tiny
                          ? ""
                          : `
                            <div
                              class="turnover-sub"
                            >
                              市值
                              ${pct(
                                box.change
                              )}
                            </div>
                          `
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
  }

  /* =========================================================
     價 / 量切換
     ========================================================= */

  async function setMode(
    next
  ) {
    if (
      next !== "price" &&
      next !== "volume"
    ) {
      return;
    }

    mode =
      next;

    ensureTabs();
    ensureNote();

    clearGold();

    /*
     * 價
     *
     * 完全交還原本 app.js
     */

    if (
      mode === "price"
    ) {
      if (
        typeof
          window
            .renderHeatCurrentPeriod ===
        "function"
      ) {
        window
          .renderHeatCurrentPeriod();
      }

      setTimeout(
        () => {
          ensureTabs();
          ensureNote();

          applyGold(
            false
          );
        },
        80
      );

      return;
    }

    /*
     * 量
     */

    await renderVolume(
      true
    );

    ensureTabs();
    ensureNote();
  }

  /* =========================================================
     監聽原本熱力圖 render
     ========================================================= */

  function watch() {
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
        () => {
          if (
            applying ||
            mode !== "price"
          ) {
            return;
          }

          setTimeout(
            () => {
              ensureTabs();
              ensureNote();

              applyGold(
                false
              );
            },
            120
          );
        }
      );

    observer.observe(
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
     初始化
     ========================================================= */

  function init() {
    injectStyle();

    ensureTabs();
    ensureNote();

    watch();

    /*
     * 切換當日 / 5 / 10 / 20 日
     *
     * 期間切換屬於價格模式
     */

    window.addEventListener(
      "heatmap:period-changed",
      () => {
        if (
          mode === "volume"
        ) {
          mode =
            "price";

          ensureTabs();
        }

        setTimeout(
          () => {
            ensureNote();

            applyGold(
              false
            );
          },
          80
        );
      }
    );

    /*
     * Heatmap 更新
     */

    window.addEventListener(
      "heatmap:data-updated",
      () => {
        detailCache =
          null;

        volumeCache =
          null;

        detailAt =
          0;

        volumeAt =
          0;

        if (
          mode === "volume"
        ) {
          renderVolume(
            true
          );
        } else {
          setTimeout(
            () => {
              applyGold(
                true
              );
            },
            120
          );
        }
      }
    );

    /*
     * 價格模式展開族群
     */

    document.addEventListener(
      "click",
      event => {
        if (
          mode === "price" &&
          event
            .target
            .closest(
              "#heatGrid [data-sec]"
            )
        ) {
          setTimeout(
            () => {
              applyGold(
                false
              );
            },
            150
          );
        }
      },
      {
        passive:
          true
      }
    );

    /*
     * 初始
     */

    if (
      visible()
    ) {
      setTimeout(
        () => {
          applyGold(
            false
          );
        },
        250
      );
    }
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
