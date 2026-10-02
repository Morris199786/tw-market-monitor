(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const PAGE_SIZE = 30;

  let mode = "self";
  let cache = null;
  let loadingPromise = null;

  let filter = "all";
  let pickedDate = "";

  let reportsLimit = PAGE_SIZE;

  let upcomingRendered = false;
  let reportsRendered = false;

  const esc = v =>
    String(v ?? "").replace(/[&<>"']/g, c => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[c]));

  const n2 = v =>
    v == null || Number.isNaN(Number(v))
      ? "—"
      : Number(v).toFixed(2);

  const pct = v =>
    v == null || Number.isNaN(Number(v))
      ? "—"
      : `${Number(v).toFixed(2)}%`;

  const dateOnly = v =>
    String(v || "").slice(0, 10);

  const localISO = d =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

  const todayISO = () =>
    localISO(new Date());

  function fmtFull(v) {
    const s = dateOnly(v);

    if (!s) {
      return "—";
    }

    const [y, m, d] =
      s.split("-");

    return `${y}/${m}/${d}`;
  }

  function addDays(s, n) {
    const d =
      new Date(`${s}T12:00:00`);

    d.setDate(
      d.getDate() + n
    );

    return localISO(d);
  }

  function weekRange(offset = 0) {
    const d =
      new Date();

    const day =
      (d.getDay() + 6) % 7;

    const start =
      new Date(d);

    start.setDate(
      d.getDate() -
      day +
      offset * 7
    );

    const end =
      new Date(start);

    end.setDate(
      start.getDate() + 6
    );

    return [
      localISO(start),
      localISO(end)
    ];
  }

  function reportDate(x) {
    return dateOnly(
      x.publish_date ||
      x.report_date ||
      x.date ||
      ""
    );
  }

  function passes(d) {
    if (filter === "all") {
      return true;
    }

    if (!d) {
      return false;
    }

    const today =
      todayISO();

    if (filter === "today") {
      return d === today;
    }

    if (filter === "tomorrow") {
      return d ===
        addDays(today, 1);
    }

    if (filter === "date") {
      return d === pickedDate;
    }

    const [a, b] =
      weekRange(
        filter === "nextweek"
          ? 1
          : 0
      );

    return (
      d >= a &&
      d <= b
    );
  }

  /* =========================================
     原本自結區
  ========================================= */

  function ensureSelfWrapper() {
    const page =
      $("#selfReports");

    if (!page) {
      return null;
    }

    let wrap =
      $("#selfLegacyArea");

    if (wrap) {
      return wrap;
    }

    const nodes = [
      $("#selfWeekBadge"),
      $("#selfWeekTabs"),
      $(".self-report-search-card", page),
      $("#selfStatus"),
      $("#selfReportCards")
    ].filter(Boolean);

    if (!nodes.length) {
      return null;
    }

    wrap =
      document.createElement("div");

    wrap.id =
      "selfLegacyArea";

    nodes[0].parentNode.insertBefore(
      wrap,
      nodes[0]
    );

    nodes.forEach(node => {
      wrap.appendChild(node);
    });

    return wrap;
  }

  function showSelf(show) {
    const wrap =
      ensureSelfWrapper();

    if (!wrap) {
      return;
    }

    wrap.hidden =
      !show;

    wrap.style.setProperty(
      "display",
      show ? "" : "none",
      "important"
    );
  }

  /* =========================================
     JSON

     整個頁面只抓一次
  ========================================= */

  async function loadData(force = false) {
    if (
      cache &&
      !force
    ) {
      return cache;
    }

    if (loadingPromise) {
      return loadingPromise;
    }

    loadingPromise =
      fetch(
        `./data/quarterly_earnings.json?t=${Date.now()}`,
        {
          cache: "no-store"
        }
      )
        .then(r => {
          if (!r.ok) {
            throw new Error(
              `HTTP ${r.status}`
            );
          }

          return r.json();
        })
        .then(data => {
          cache = data;

          return data;
        })
        .finally(() => {
          loadingPromise = null;
        });

    return loadingPromise;
  }

  /* =========================================
     即將開財報 HTML
  ========================================= */

  function upcomingHTML(arr) {
    const groups = {};

    arr.forEach(x => {
      const d =
        dateOnly(
          x.planned_date
        );

      if (!passes(d)) {
        return;
      }

      if (!groups[d || "未定"]) {
        groups[d || "未定"] = [];
      }

      groups[d || "未定"].push(x);
    });

    const keys =
      Object.keys(groups).sort(
        (a, b) => {
          if (a === "未定") {
            return 1;
          }

          if (b === "未定") {
            return -1;
          }

          return a.localeCompare(b);
        }
      );

    if (!keys.length) {
      return `
        <div class="earnings-empty">
          這個日期範圍目前沒有即將開財報的公司
        </div>
      `;
    }

    return keys.map(d => `
      <section class="earnings-day">

        <div class="earnings-day-head">

          <b>
            ${
              d === "未定"
                ? "日期未定"
                : fmtFull(d)
            }
          </b>

          <span>
            ${groups[d].length} 檔
          </span>

        </div>

        <div class="earnings-compact-list">

          ${groups[d].map(x => `
            <details class="earnings-row">

              <summary>

                <div class="earnings-company">

                  <b>
                    ${esc(
                      x.name ||
                      x.ticker
                    )}
                  </b>

                  <span>
                    ${esc(
                      x.ticker
                    )}
                  </span>

                </div>

                <div class="earnings-row-right">

                  <span class="earnings-period">
                    ${esc(
                      x.period ||
                      ""
                    )}
                  </span>

                  <span class="earnings-chevron">
                    ›
                  </span>

                </div>

              </summary>

              <div class="earnings-detail">

                <div>

                  <small>
                    上一季 EPS
                  </small>

                  <b>
                    ${n2(
                      x.prev_eps
                    )} 元
                  </b>

                </div>

                <div>

                  <small>
                    上一季毛利率
                  </small>

                  <b>
                    ${pct(
                      x.prev_gross_margin
                    )}
                  </b>

                </div>

              </div>

            </details>
          `).join("")}

        </div>

      </section>
    `).join("");
  }

  /* =========================================
     財報單列
  ========================================= */

  function reportItem(x) {
    const epsQoQ =
      x.eps != null &&
      x.prev_eps != null &&
      Number(x.prev_eps) !== 0
        ? (
            Number(x.eps) /
            Number(x.prev_eps) -
            1
          ) * 100
        : null;

    const gmQoQ =
      x.gross_margin != null &&
      x.prev_gross_margin != null
        ? Number(x.gross_margin) -
          Number(x.prev_gross_margin)
        : null;

    return `
      <details class="earnings-report-row">

        <summary>

          <div class="earnings-company">

            <b>
              ${esc(
                x.name ||
                x.ticker
              )}
            </b>

            <span>
              ${esc(
                x.ticker
              )}
            </span>

          </div>

          <div class="earnings-report-main">

            <b>
              ${n2(
                x.eps
              )} 元
            </b>

            <span>
              EPS
            </span>

          </div>

          <div class="earnings-row-right">

            <span class="earnings-period">
              ${esc(
                x.period ||
                ""
              )}
            </span>

            <span class="earnings-chevron">
              ›
            </span>

          </div>

        </summary>

        <div class="earnings-detail four">

          <div>

            <small>
              本季 EPS
            </small>

            <b>
              ${n2(
                x.eps
              )} 元
            </b>

            ${
              epsQoQ == null
                ? ""
                : `
                  <em>
                    QoQ
                    ${
                      epsQoQ >= 0
                        ? "+"
                        : ""
                    }${epsQoQ.toFixed(1)}%
                  </em>
                `
            }

          </div>

          <div>

            <small>
              本季毛利率
            </small>

            <b>
              ${pct(
                x.gross_margin
              )}
            </b>

            ${
              gmQoQ == null
                ? ""
                : `
                  <em>
                    QoQ
                    ${
                      gmQoQ >= 0
                        ? "+"
                        : ""
                    }${gmQoQ.toFixed(2)} pct
                  </em>
                `
            }

          </div>

          <div>

            <small>
              上一季 EPS
            </small>

            <b>
              ${n2(
                x.prev_eps
              )} 元
            </b>

          </div>

          <div>

            <small>
              上一季毛利率
            </small>

            <b>
              ${pct(
                x.prev_gross_margin
              )}
            </b>

          </div>

        </div>

      </details>
    `;
  }

  /* =========================================
     財報 HTML
  ========================================= */

  function reportsHTML(arr) {
    const filtered =
      arr.filter(x =>
        passes(
          reportDate(x)
        )
      );

    if (!filtered.length) {
      return `
        <div class="earnings-empty">
          ${
            filter === "all"
              ? "目前沒有財報資料"
              : "這個日期範圍目前沒有財報"
          }
        </div>
      `;
    }

    const shown =
      filtered.slice(
        0,
        reportsLimit
      );

    let html =
      shown
        .map(reportItem)
        .join("");

    if (
      shown.length <
      filtered.length
    ) {
      html += `
        <button
          type="button"
          id="earningsLoadMore"
          class="earnings-load-more"
        >
          載入更多
          （${shown.length}/${filtered.length}）
        </button>
      `;
    }

    return html;
  }

  /* =========================================
     Status
  ========================================= */

  function statusHTML(
    title,
    count
  ) {
    return `
      <b>
        ${title}
      </b>

      <span>
        ${count} 檔
      </span>

      <span class="earnings-updated">
        更新
        ${esc(
          String(
            cache?.updated_at ||
            "—"
          ).replace(
            "T",
            " "
          )
        )}
      </span>
    `;
  }

  /* =========================================
     Render 即將開財報

     只在第一次 / 篩選改變時 render
  ========================================= */

  function renderUpcoming() {
    if (!cache) {
      return;
    }

    const panel =
      $("#earningsUpcomingPanel");

    const status =
      $("#earningsUpcomingStatus");

    const cards =
      $("#earningsUpcomingCards");

    if (
      !panel ||
      !status ||
      !cards
    ) {
      return;
    }

    const arr =
      cache.upcoming || [];

    const count =
      arr.filter(x =>
        passes(
          dateOnly(
            x.planned_date
          )
        )
      ).length;

    status.innerHTML =
      statusHTML(
        "即將開財報",
        count
      );

    cards.innerHTML =
      upcomingHTML(arr);

    upcomingRendered =
      true;
  }

  /* =========================================
     Render 財報

     只在第一次 / 篩選改變時 render
  ========================================= */

  function renderReports() {
    if (!cache) {
      return;
    }

    const status =
      $("#earningsReportsStatus");

    const cards =
      $("#earningsReportsCards");

    if (
      !status ||
      !cards
    ) {
      return;
    }

    const arr =
      cache.reports || [];

    const count =
      arr.filter(x =>
        passes(
          reportDate(x)
        )
      ).length;

    status.innerHTML =
      statusHTML(
        "財報",
        count
      );

    cards.innerHTML =
      reportsHTML(arr);

    bindLoadMore();

    reportsRendered =
      true;
  }

  /* =========================================
     Load More
  ========================================= */

  function bindLoadMore() {
    const btn =
      $("#earningsLoadMore");

    if (!btn) {
      return;
    }

    btn.onclick = () => {
      reportsLimit +=
        PAGE_SIZE;

      renderReports();
    };
  }

  /* =========================================
     第一次載入
  ========================================= */

  async function ensureData() {
    if (cache) {
      return cache;
    }

    const activeStatus =
      mode === "reports"
        ? $("#earningsReportsStatus")
        : $("#earningsUpcomingStatus");

    if (activeStatus) {
      activeStatus.textContent =
        "讀取中…";
    }

    try {
      return await loadData(false);

    } catch (error) {
      console.error(
        "[Earnings Tracker]",
        error
      );

      if (activeStatus) {
        activeStatus.textContent =
          "財報資料讀取失敗";
      }

      throw error;
    }
  }

  /* =========================================
     只做 show / hide

     不重新建立 DOM
  ========================================= */

  function showPanel(next) {
    const root =
      $("#quarterlyEarningsPanel");

    const upcoming =
      $("#earningsUpcomingPanel");

    const reports =
      $("#earningsReportsPanel");

    if (!root) {
      return;
    }

    if (next === "self") {
      root.hidden = true;

      root.style.setProperty(
        "display",
        "none",
        "important"
      );

      showSelf(true);

      return;
    }

    showSelf(false);

    root.hidden = false;

    root.style.setProperty(
      "display",
      "block",
      "important"
    );

    if (upcoming) {
      upcoming.hidden =
        next !== "upcoming";

      upcoming.style.setProperty(
        "display",
        next === "upcoming"
          ? "block"
          : "none",
        "important"
      );
    }

    if (reports) {
      reports.hidden =
        next !== "reports";

      reports.style.setProperty(
        "display",
        next === "reports"
          ? "block"
          : "none",
        "important"
      );
    }
  }

  /* =========================================
     Tab 切換

     第一次才 render
     第二次之後只 show / hide
  ========================================= */

  async function switchMode(next) {
    if (
      next === mode
    ) {
      return;
    }

    mode = next;

    $$(
      "[data-earnings-mode]"
    ).forEach(btn => {
      btn.classList.toggle(
        "active",
        btn.dataset.earningsMode ===
          next
      );
    });

    /*
     * 先切畫面
     *
     * 不等 fetch
     */
    showPanel(next);

    if (
      next === "self"
    ) {
      return;
    }

    try {
      await ensureData();

      /*
       * 使用者在 fetch 完成前
       * 已經切去別頁
       */
      if (
        mode !== next
      ) {
        return;
      }

      if (
        next === "upcoming" &&
        !upcomingRendered
      ) {
        renderUpcoming();
      }

      if (
        next === "reports" &&
        !reportsRendered
      ) {
        renderReports();
      }

    } catch (_) {
      // 錯誤已顯示
    }
  }

  /* =========================================
     日期篩選

     只有篩選改變才重新 render
  ========================================= */

  function rerenderCurrentFilters() {
    reportsLimit =
      PAGE_SIZE;

    upcomingRendered =
      false;

    reportsRendered =
      false;

    /*
     * 只 render 目前正在看的頁
     *
     * 另一頁等使用者點過去
     * 再建立
     */
    if (
      mode === "upcoming"
    ) {
      renderUpcoming();
    }

    if (
      mode === "reports"
    ) {
      renderReports();
    }
  }

  function bindFilters() {
    $$(
      "[data-date-filter]"
    ).forEach(btn => {

      btn.onclick = () => {
        filter =
          btn.dataset.dateFilter;

        pickedDate = "";

        const picker =
          $("#earningsDatePicker");

        if (picker) {
          picker.value = "";
        }

        $$(
          "[data-date-filter]"
        ).forEach(x => {
          x.classList.toggle(
            "active",
            x === btn
          );
        });

        rerenderCurrentFilters();
      };
    });

    const picker =
      $("#earningsDatePicker");

    if (picker) {
      picker.onchange = () => {
        pickedDate =
          picker.value;

        filter =
          "date";

        $$(
          "[data-date-filter]"
        ).forEach(x => {
          x.classList.remove(
            "active"
          );
        });

        rerenderCurrentFilters();
      };
    }
  }

  /* =========================================
     建立 UI
  ========================================= */

  function setup() {
    const page =
      $("#selfReports");

    if (!page) {
      return;
    }

    $$(
      '[data-p="selfReports"]'
    ).forEach(x => {
      x.textContent =
        "財報追蹤";
    });

    const option =
      $(
        '#mobileNav option[value="selfReports"]'
      );

    if (option) {
      option.textContent =
        "財報追蹤";
    }

    const kicker =
      page.querySelector(
        ".kicker"
      );

    const h1 =
      page.querySelector(
        "h1"
      );

    const desc =
      page.querySelector(
        ".hero p"
      );

    if (kicker) {
      kicker.textContent =
        "EARNINGS TRACKER";
    }

    if (h1) {
      h1.textContent =
        "財報追蹤";
    }

    if (desc) {
      desc.textContent =
        "自結公布、財報行事曆與季度財報";
    }

    /*
     * 如果是舊版 earnings UI
     * 先清掉
     */
    const oldTabs =
      $("#earningsModeTabs");

    const oldPanel =
      $("#quarterlyEarningsPanel");

    if (oldTabs) {
      oldTabs.remove();
    }

    if (oldPanel) {
      oldPanel.remove();
    }

    const hero =
      page.querySelector(
        ".hero"
      );

    if (!hero) {
      return;
    }

    hero.insertAdjacentHTML(
      "afterend",
      `
      <div
        id="earningsModeTabs"
        class="earnings-mode-tabs"
      >

        <button
          type="button"
          class="earnings-mode active"
          data-earnings-mode="self"
        >
          自結公布
        </button>

        <button
          type="button"
          class="earnings-mode"
          data-earnings-mode="upcoming"
        >
          即將開財報
        </button>

        <button
          type="button"
          class="earnings-mode"
          data-earnings-mode="reports"
        >
          財報
        </button>

      </div>

      <div
        id="quarterlyEarningsPanel"
        hidden
      >

        <div
          id="earningsFilters"
          class="earnings-filters"
        >

          <div class="earnings-quick">

            <button
              type="button"
              data-date-filter="all"
              class="active"
            >
              全部
            </button>

            <button
              type="button"
              data-date-filter="today"
            >
              今天
            </button>

            <button
              type="button"
              data-date-filter="tomorrow"
            >
              明天
            </button>

            <button
              type="button"
              data-date-filter="week"
            >
              本週
            </button>

            <button
              type="button"
              data-date-filter="nextweek"
            >
              下週
            </button>

          </div>

          <label
            class="earnings-date-picker"
          >

            <span>
              指定日期
            </span>

            <input
              id="earningsDatePicker"
              type="date"
            >

          </label>

        </div>

        <!-- 即將開財報：自己的 DOM -->

        <div
          id="earningsUpcomingPanel"
          hidden
        >

          <div
            id="earningsUpcomingStatus"
            class="earnings-status"
          ></div>

          <div
            id="earningsUpcomingCards"
            class="earnings-list"
          ></div>

        </div>

        <!-- 財報：自己的 DOM -->

        <div
          id="earningsReportsPanel"
          hidden
        >

          <div
            id="earningsReportsStatus"
            class="earnings-status"
          ></div>

          <div
            id="earningsReportsCards"
            class="earnings-list"
          ></div>

        </div>

      </div>
      `
    );

    ensureSelfWrapper();

    $$(
      "[data-earnings-mode]"
    ).forEach(btn => {
      btn.onclick = () => {
        switchMode(
          btn.dataset.earningsMode
        );
      };
    });

    bindFilters();
  }

  /* =========================================
     給 refresh_controller.js 使用

     注意：
     不會自己監聽 pageshow
     不會自己監聽 visibilitychange
  ========================================= */

  window.refreshQuarterlyReports =
    async function () {
      try {
        await loadData(true);

        /*
         * 資料真的更新後
         * 才讓兩個 DOM 下次重建
         */
        upcomingRendered =
          false;

        reportsRendered =
          false;

        if (
          mode === "upcoming"
        ) {
          renderUpcoming();
        }

        if (
          mode === "reports"
        ) {
          renderReports();
        }

      } catch (error) {
        console.error(
          "[Earnings Tracker refresh]",
          error
        );
      }
    };

  /* =========================================
     啟動
  ========================================= */

  function boot() {
    setup();

    /*
     * 初始一定顯示自結
     */
    mode =
      "self";

    showPanel(
      "self"
    );

    /*
     * 背景預抓一次 JSON
     *
     * 只 fetch
     * 不建立財報 DOM
     */
    const idle =
      window.requestIdleCallback ||
      (
        fn =>
          setTimeout(
            fn,
            500
          )
      );

    idle(() => {
      loadData(false)
        .catch(() => {});
    });

    /*
     * ui_v2.js 如果晚一點
     * 才處理自結內容
     *
     * 只確認 wrapper
     * 不碰財報 DOM
     */
    setTimeout(
      () => {
        ensureSelfWrapper();

        if (
          mode !== "self"
        ) {
          showSelf(false);
        }
      },
      1000
    );
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      boot,
      {
        once: true
      }
    );
  } else {
    boot();
  }

})();
