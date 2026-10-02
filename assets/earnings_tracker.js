(() => {
  "use strict";

  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];

  let mode = "self";
  let cache = null;
  let filter = "all";
  let pickedDate = "";

  const esc = v =>
    String(v ?? "").replace(/[&<>"']/g, c => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[c]));

  const val = v =>
    v == null || Number.isNaN(Number(v))
      ? "—"
      : Number(v).toFixed(2);

  const pct = v =>
    v == null || Number.isNaN(Number(v))
      ? "—"
      : `${Number(v).toFixed(2)}%`;

  const dateOnly = v => String(v || "").slice(0, 10);

  const fmtDate = v => {
    const s = dateOnly(v);
    if (!s) return "—";

    const [y, m, d] = s.split("-");
    return `${Number(m)}/${Number(d)}`;
  };

  const fmtFull = v => {
    const s = dateOnly(v);
    if (!s) return "—";

    const [y, m, d] = s.split("-");
    return `${y}/${m}/${d}`;
  };

  const localISO = d =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

  const todayISO = () => localISO(new Date());

  function addDays(s, n) {
    const d = new Date(`${s}T12:00:00`);
    d.setDate(d.getDate() + n);
    return localISO(d);
  }

  function weekRange(offset = 0) {
    const d = new Date();

    const day = (d.getDay() + 6) % 7;

    const mon = new Date(d);
    mon.setDate(d.getDate() - day + offset * 7);

    const sun = new Date(mon);
    sun.setDate(mon.getDate() + 6);

    return [
      localISO(mon),
      localISO(sun)
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

  function setup() {
    const page = $("#selfReports");
    if (!page) return;

    /*
     * 主導覽名稱
     */
    $$('[data-p="selfReports"]').forEach(x => {
      x.textContent = "財報追蹤";
    });

    const opt = $('#mobileNav option[value="selfReports"]');

    if (opt) {
      opt.textContent = "財報追蹤";
    }

    /*
     * Hero
     */
    const kicker = page.querySelector(".kicker");
    const h1 = page.querySelector("h1");
    const p = page.querySelector(".hero p");

    if (kicker) {
      kicker.textContent = "EARNINGS TRACKER";
    }

    if (h1) {
      h1.textContent = "財報追蹤";
    }

    if (p) {
      p.textContent = "自結公布、財報行事曆與季度財報";
    }

    /*
     * 建立三個模式
     */
    if (!$("#earningsModeTabs")) {
      page.querySelector(".hero").insertAdjacentHTML(
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

            <label class="earnings-date-picker">

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

    /*
     * 三個主模式
     */
    $$("[data-earnings-mode]").forEach(b => {
      b.onclick = () => {
        switchMode(
          b.dataset.earningsMode
        );
      };
    });

    /*
     * 日期快速篩選
     */
    $$("[data-date-filter]").forEach(b => {
      b.onclick = () => {

        filter = b.dataset.dateFilter;
        pickedDate = "";

        const dp = $("#earningsDatePicker");

        if (dp) {
          dp.value = "";
        }

        $$("[data-date-filter]").forEach(x => {
          x.classList.toggle(
            "active",
            x === b
          );
        });

        render();
      };
    });

    /*
     * 指定日期
     */
    const dp = $("#earningsDatePicker");

    if (dp) {
      dp.onchange = () => {

        pickedDate = dp.value;
        filter = "date";

        $$("[data-date-filter]").forEach(x => {
          x.classList.remove("active");
        });

        render();
      };
    }
  }

  /*
   * 自結區顯示 / 隱藏
   */
  function showSelf(show) {

    [
      "#selfWeekTabs",
      ".self-report-search-card",
      "#selfStatus",
      "#selfReportCards"
    ].forEach(s => {

      const el = $(s);

      if (el) {
        el.style.display = show
          ? ""
          : "none";
      }
    });

    const badge = $("#selfWeekBadge");

    if (badge) {
      badge.style.display = show
        ? ""
        : "none";
    }
  }

  /*
   * quarterly_earnings.json
   */
  async function load(force = false) {

    if (cache && !force) {
      return cache;
    }

    const r = await fetch(
      `./data/quarterly_earnings.json?v=${Date.now()}`,
      {
        cache: "no-store"
      }
    );

    if (!r.ok) {
      throw new Error(
        `HTTP ${r.status}`
      );
    }

    cache = await r.json();

    return cache;
  }

  /*
   * 日期篩選
   */
  function passes(d) {

    if (filter === "all") {
      return true;
    }

    if (!d) {
      return false;
    }

    const t = todayISO();

    if (filter === "today") {
      return d === t;
    }

    if (filter === "tomorrow") {
      return d === addDays(t, 1);
    }

    if (filter === "date") {
      return d === pickedDate;
    }

    const [a, b] = weekRange(
      filter === "nextweek"
        ? 1
        : 0
    );

    return (
      d >= a &&
      d <= b
    );
  }

  /*
   * 即將開財報
   *
   * 不再把所有公司做成大型卡片
   *
   * 日期
   * ├ 台積電 2330   2026-Q3 >
   * ├ 聯發科 2454   2026-Q3 >
   * └ ...
   *
   * 點公司才展開上一季數字
   */
  function upcomingRows(arr) {

    const groups = {};

    arr.forEach(x => {

      const d = dateOnly(
        x.planned_date
      );

      if (!passes(d)) {
        return;
      }

      (
        groups[d || "未定"] ||= []
      ).push(x);
    });

    const keys = Object
      .keys(groups)
      .sort((a, b) => {

        if (a === "未定") {
          return 1;
        }

        if (b === "未定") {
          return -1;
        }

        return a.localeCompare(b);
      });

    if (!keys.length) {
      return `
        <div class="earnings-empty">
          這個日期範圍目前沒有即將開財報的公司
        </div>
      `;
    }

    return keys.map(d => {

      const rows = groups[d];

      return `
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
              ${rows.length} 檔
            </span>

          </div>

          <div class="earnings-compact-list">

            ${
              rows.map(x => `
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
                        ${val(x.prev_eps)} 元
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
      `;
    }).join("");
  }

  /*
   * 已公布財報
   *
   * 預設只顯示公司 + EPS
   * 點進去才展開完整比較
   */
  function reportRows(arr) {

    const filtered = arr.filter(x =>
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

    return filtered.map(x => {

      const epsQ =
        x.eps != null &&
        x.prev_eps != null &&
        Number(x.prev_eps) !== 0
          ? (
              Number(x.eps) /
              Number(x.prev_eps) -
              1
            ) * 100
          : null;

      const gm =
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
                ${val(x.eps)} 元
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
                ${val(x.eps)} 元
              </b>

              ${
                epsQ == null
                  ? ""
                  : `
                    <em>
                      QoQ
                      ${
                        epsQ >= 0
                          ? "+"
                          : ""
                      }${epsQ.toFixed(1)}%
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
                gm == null
                  ? ""
                  : `
                    <em>
                      QoQ
                      ${
                        gm >= 0
                          ? "+"
                          : ""
                      }${gm.toFixed(2)} pct
                    </em>
                  `
              }

            </div>

            <div>

              <small>
                上一季 EPS
              </small>

              <b>
                ${val(
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
    }).join("");
  }

  /*
   * 重新畫面
   */
  async function render(force = false) {

    if (mode === "self") {
      return;
    }

    const status =
      $("#quarterlyEarningsStatus");

    const cards =
      $("#quarterlyEarningsCards");

    if (!status || !cards) {
      return;
    }

    status.textContent =
      "讀取中…";

    cards.innerHTML = "";

    try {

      const d =
        await load(force);

      const arr =
        mode === "upcoming"
          ? (d.upcoming || [])
          : (d.reports || []);

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
              d.updated_at ||
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
          ? upcomingRows(arr)
          : reportRows(arr);

    } catch (e) {

      status.textContent =
        "財報資料讀取失敗";

      cards.innerHTML = `
        <div class="earnings-empty">
          quarterly_earnings.json 讀取失敗
        </div>
      `;

      console.error(e);
    }
  }

  /*
   * 切換：
   *
   * 自結公布
   * 即將開財報
   * 財報
   */
  async function switchMode(
    next,
    force = false
  ) {

    mode = next;

    $$("[data-earnings-mode]")
      .forEach(b => {

        b.classList.toggle(
          "active",
          b.dataset.earningsMode === next
        );

      });

    const panel =
      $("#quarterlyEarningsPanel");

    if (next === "self") {

      showSelf(true);

      if (panel) {
        panel.hidden = true;
      }

      return;
    }

    /*
     * 切到財報頁時
     * 自結搜尋 / 自結卡片全部隱藏
     */
    showSelf(false);

    if (panel) {
      panel.hidden = false;
    }

    await render(force);
  }

  /*
   * 移除舊版 Pushover 顯示
   *
   * 實際通知仍由後端控制
   * 這裡只處理網頁文字
   */
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

    while (
      walker.nextNode()
    ) {

      if (
        /Pushover/i.test(
          walker.currentNode.nodeValue ||
          ""
        )
      ) {
        nodes.push(
          walker.currentNode
        );
      }
    }

    nodes.forEach(n => {

      n.nodeValue =
        (
          n.nodeValue ||
          ""
        ).replace(
          /\s*[·｜]?\s*Pushover\s*已啟用/gi,
          ""
        );

    });
  }

  /*
   * 啟動
   */
  function boot() {

    setup();

    removePushoverText();

    switchMode("self");

    /*
     * ui_v2.js 可能稍後才完成自結狀態
     * 再清一次 Pushover 字樣
     */
    setTimeout(
      removePushoverText,
      700
    );
  }

  if (
    document.readyState ===
    "loading"
  ) {

    document.addEventListener(
      "DOMContentLoaded",
      boot
    );

  } else {

    boot();

  }

  /*
   * 提供 refresh_controller 呼叫
   */
  window.refreshQuarterlyReports =
    () => {

      cache = null;

      if (
        mode !== "self"
      ) {
        render(true);
      }
    };

  /*
   * 從其他 App 回 Safari
   */
  window.addEventListener(
    "pageshow",
    () => {

      cache = null;

      if (
        mode !== "self"
      ) {
        render(true);
      }
    }
  );

  document.addEventListener(
    "visibilitychange",
    () => {

      if (
        !document.hidden &&
        mode !== "self"
      ) {

        cache = null;

        render(true);
      }
    }
  );

})();
