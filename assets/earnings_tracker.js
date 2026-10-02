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
  let reportLimit = PAGE_SIZE;
  let renderToken = 0;

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

  const fmtFull = v => {
    const s = dateOnly(v);

    if (!s) return "—";

    const [y, m, d] = s.split("-");

    return `${y}/${m}/${d}`;
  };

  function addDays(s, n) {
    const d = new Date(`${s}T12:00:00`);

    d.setDate(d.getDate() + n);

    return localISO(d);
  }

  function weekRange(offset = 0) {
    const d = new Date();

    const day =
      (d.getDay() + 6) % 7;

    const a = new Date(d);

    a.setDate(
      d.getDate() -
      day +
      offset * 7
    );

    const b = new Date(a);

    b.setDate(
      a.getDate() + 6
    );

    return [
      localISO(a),
      localISO(b)
    ];
  }

  function reportDate(x) {
    return dateOnly(
      x.publish_date ||
      x.report_date ||
      x.date ||
      x.updated_at ||
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
      return d === addDays(today, 1);
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

    nodes.forEach(
      n => wrap.appendChild(n)
    );

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

  function removePushoverText() {
    const page =
      $("#selfReports");

    if (!page) {
      return;
    }

    const walker =
      document.createTreeWalker(
        page,
        NodeFilter.SHOW_TEXT
      );

    const nodes = [];

    while (walker.nextNode()) {
      if (
        /Pushover/i.test(
          walker.currentNode.nodeValue || ""
        )
      ) {
        nodes.push(
          walker.currentNode
        );
      }
    }

    nodes.forEach(n => {
      n.nodeValue =
        (n.nodeValue || "").replace(
          /\s*[·｜]?\s*Pushover\s*已啟用/gi,
          ""
        );
    });
  }

  async function load(force = false) {
    if (
      cache &&
      !force
    ) {
      return cache;
    }

    if (
      loadingPromise &&
      !force
    ) {
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
        .then(d => {
          cache = d;
          return d;
        })
        .finally(() => {
          loadingPromise = null;
        });

    return loadingPromise;
  }

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

      (
        groups[d || "未定"] ||=
          []
      ).push(x);
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

          ${
            groups[d].map(x => `
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
                      ${esc(x.ticker)}
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
            `).join("")
          }

        </div>

      </section>
    `).join("");
  }

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
              ${esc(x.ticker)}
            </span>

          </div>

          <div class="earnings-report-main">

            <b>
              ${n2(x.eps)} 元
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
              ${n2(x.eps)} 元
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

  function reportHTML(arr) {
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
        reportLimit
      );

    return (
      shown
        .map(reportItem)
        .join("") +

      (
        shown.length <
        filtered.length
          ? `
            <button
              type="button"
              id="earningsLoadMore"
              class="earnings-load-more"
            >
              載入更多
              （${shown.length}/${filtered.length}）
            </button>
          `
          : ""
      )
    );
  }

  function bindLoadMore(arr) {
    const btn =
      $("#earningsLoadMore");

    if (!btn) {
      return;
    }

    btn.onclick = () => {
      reportLimit +=
        PAGE_SIZE;

      const cards =
        $("#quarterlyEarningsCards");

      if (!cards) {
        return;
      }

      cards.innerHTML =
        reportHTML(arr);

      bindLoadMore(arr);
    };
  }

  async function render(
    force = false
  ) {
    if (
      mode === "self"
    ) {
      return;
    }

    const status =
      $("#quarterlyEarningsStatus");

    const cards =
      $("#quarterlyEarningsCards");

    if (
      !status ||
      !cards
    ) {
      return;
    }

    const token =
      ++renderToken;

    if (!cache) {
      status.textContent =
        "讀取中…";
    }

    try {
      const data =
        await load(force);

      if (
        token !== renderToken ||
        mode === "self"
      ) {
        return;
      }

      const arr =
        mode === "upcoming"
          ? (
              data.upcoming ||
              []
            )
          : (
              data.reports ||
              []
            );

      const count =
        mode === "upcoming"
          ? arr.filter(x =>
              passes(
                dateOnly(
                  x.planned_date
                )
              )
            ).length
          : arr.filter(x =>
              passes(
                reportDate(x)
              )
            ).length;

      status.innerHTML = `
        <b>
          ${
            mode === "upcoming"
              ? "即將開財報"
              : "財報"
          }
        </b>

        <span>
          ${count} 檔
        </span>

        <span class="earnings-updated">
          更新
          ${esc(
            String(
              data.updated_at ||
              "—"
            ).replace(
              "T",
              " "
            )
          )}
        </span>
      `;

      cards.innerHTML =
        mode === "upcoming"
          ? upcomingHTML(arr)
          : reportHTML(arr);

      bindLoadMore(arr);

    } catch (e) {
      if (
        token !== renderToken
      ) {
        return;
      }

      status.textContent =
        "財報資料讀取失敗";

      cards.innerHTML = `
        <div class="earnings-empty">
          財報資料讀取失敗
        </div>
      `;

      console.error(e);
    }
  }

  function switchMode(next) {
    /*
     * 已經在同一頁就不重畫
     */
    if (
      mode === next &&
      next !== "self"
    ) {
      return;
    }

    mode = next;

    reportLimit =
      PAGE_SIZE;

    $$(
      "[data-earnings-mode]"
    ).forEach(b => {
      b.classList.toggle(
        "active",
        b.dataset.earningsMode ===
          next
      );
    });

    const panel =
      $("#quarterlyEarningsPanel");

    if (
      next === "self"
    ) {
      if (panel) {
        panel.hidden = true;

        panel.style.setProperty(
          "display",
          "none",
          "important"
        );
      }

      showSelf(true);

      return;
    }

    showSelf(false);

    if (panel) {
      panel.hidden = false;

      panel.style.setProperty(
        "display",
        "block",
        "important"
      );
    }

    render(false);
  }

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

    if (
      !$("#earningsModeTabs")
    ) {
      page
        .querySelector(".hero")
        .insertAdjacentHTML(
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

            <div
              id="quarterlyEarningsStatus"
              class="earnings-status"
            ></div>

            <div
              id="quarterlyEarningsCards"
              class="earnings-list"
            ></div>

          </div>
          `
        );
    }

    ensureSelfWrapper();

    $$(
      "[data-earnings-mode]"
    ).forEach(b => {
      b.onclick = () =>
        switchMode(
          b.dataset.earningsMode
        );
    });

    $$(
      "[data-date-filter]"
    ).forEach(b => {
      b.onclick = () => {
        filter =
          b.dataset.dateFilter;

        pickedDate = "";

        reportLimit =
          PAGE_SIZE;

        const dp =
          $("#earningsDatePicker");

        if (dp) {
          dp.value = "";
        }

        $$(
          "[data-date-filter]"
        ).forEach(x => {
          x.classList.toggle(
            "active",
            x === b
          );
        });

        render(false);
      };
    });

    const dp =
      $("#earningsDatePicker");

    if (dp) {
      dp.onchange = () => {
        pickedDate =
          dp.value;

        filter =
          "date";

        reportLimit =
          PAGE_SIZE;

        $$(
          "[data-date-filter]"
        ).forEach(x => {
          x.classList.remove(
            "active"
          );
        });

        render(false);
      };
    }
  }

  function boot() {
    setup();

    removePushoverText();

    switchMode("self");

    /*
     * 預先下載財報 JSON
     * 但不 render
     */
    const idle =
      window.requestIdleCallback ||
      (
        fn =>
          setTimeout(
            fn,
            400
          )
      );

    idle(() => {
      load(false).catch(
        () => {}
      );
    });

    setTimeout(
      () => {
        ensureSelfWrapper();

        removePushoverText();

        if (
          mode !== "self"
        ) {
          showSelf(false);
        }
      },
      900
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

  /*
   * 給 refresh_controller 呼叫
   */
  window.refreshQuarterlyReports =
    async () => {
      try {
        await load(true);

        if (
          mode !== "self"
        ) {
          render(false);
        }
      } catch (e) {
        console.error(e);
      }
    };

  /*
   * 從 LINE / 其他 App 回來
   * 背景更新，不清畫面
   */
  let lastResumeRefresh = 0;

  function resumeRefresh() {
    if (
      document.hidden
    ) {
      return;
    }

    const now =
      Date.now();

    if (
      now -
        lastResumeRefresh <
      15000
    ) {
      return;
    }

    lastResumeRefresh =
      now;

    load(true)
      .then(() => {
        if (
          mode !== "self"
        ) {
          render(false);
        }
      })
      .catch(() => {});
  }

  window.addEventListener(
    "pageshow",
    resumeRefresh
  );

  document.addEventListener(
    "visibilitychange",
    resumeRefresh
  );

})();
