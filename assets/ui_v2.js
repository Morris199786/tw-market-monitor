const featureItems = [
  ["heat", "市場熱力圖", "heat", "red", "19族群・5分鐘"],
  ["selfReports", "自結公布", "earnings", "amber", "每30分鐘"],
  ["flows", "籌碼日報", "flow", "blue", "法人"],
  ["volume", "突然放量", "bolt", "amber", "科技股"],
  ["turnover", "成交排行", "chart", "blue", "TOP30"],
  ["marginLending", "融資／借券", "swap", "violet", "科技股"],
  ["ai", "AI選股", "spark", "green", "每天18:00"],
  ["reports", "券商報告", "report", "amber", "研究報告"],
  ["holders", "大戶籌碼", "holders", "violet", "週更"],
  ["monthlyRevenue", "月營收公布", "revenue", "green", "19族群"],
  ["marketMonitor", "大盤監控", "revenue", "blue", "外資／融資燈號"]
];

let revenueSectorSelected = "all";
let revenueMomSort = false;
let selfReportSearch = "";
let selfReportDate = "";

function taiwanToday() {
  const parts =
    new Intl.DateTimeFormat(
      "en-US",
      {
        timeZone: "Asia/Taipei",
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
      }
    ).formatToParts(
      new Date()
    );

  const get =
    type =>
      parts.find(
        x =>
          x.type === type
      )?.value || "";

  return `${get("year")}-${get("month")}-${get("day")}`;
}

function normalizeSelfReportDate(value) {
  return String(
    value || ""
  )
    .trim()
    .slice(
      0,
      10
    )
    .replace(
      /\//g,
      "-"
    );
}

function featureIcon(name) {
  const icons = {
    heat: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="2"></rect>
      <rect x="14" y="3" width="7" height="7" rx="2"></rect>
      <rect x="3" y="14" width="7" height="7" rx="2"></rect>
      <rect x="14" y="14" width="7" height="7" rx="2"></rect>
    </svg>`,

    earnings: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 20V10"></path>
      <path d="M10 20V4"></path>
      <path d="M15 20v-7"></path>
      <path d="M20 20V7"></path>
      <path d="M3 20h19"></path>
    </svg>`,

    flow: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h12"></path>
      <path d="m13 4 3 3-3 3"></path>
      <path d="M20 17H8"></path>
      <path d="m11 14-3 3 3 3"></path>
    </svg>`,

    bolt: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M13 2 5 14h6l-1 8 9-13h-6z"></path>
    </svg>`,

    chart: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 20V10"></path>
      <path d="M10 20V4"></path>
      <path d="M16 20v-7"></path>
      <path d="M22 20H2"></path>
    </svg>`,

    swap: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 7h12l-3-3"></path>
      <path d="m19 7-3 3"></path>
      <path d="M17 17H5l3 3"></path>
      <path d="m5 17 3-3"></path>
    </svg>`,

    spark: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m12 2 1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8z"></path>
      <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"></path>
    </svg>`,

    report: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 3h9l4 4v14H6z"></path>
      <path d="M15 3v5h5"></path>
      <path d="M9 12h7"></path>
      <path d="M9 16h7"></path>
    </svg>`,

    holders: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="9" cy="8" r="3"></circle>
      <circle cx="17" cy="9" r="2"></circle>
      <path d="M3 20c0-4 2.5-6 6-6s6 2 6 6"></path>
      <path d="M15 15c3 0 5 1.5 5 5"></path>
    </svg>`,

    revenue: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 19V5"></path>
      <path d="M4 19h16"></path>
      <path d="m7 15 4-4 3 2 5-6"></path>
      <path d="M16 7h3v3"></path>
    </svg>`
  };

  return icons[name] || icons.chart;
}

function buildFeatureRail() {
  const box = $("#featureRail");

  if (!box) return;

  box.innerHTML = featureItems.map((x, i) => `
    <button
      class="feature-card"
      data-feature="${x[0]}"
      data-tone="${x[3]}"
      aria-label="${x[1]}"
    >
      <div class="feature-card-top">
        <div class="feature-icon">
          ${featureIcon(x[2])}
        </div>

        <span class="feature-index">
          ${String(i + 1).padStart(2, "0")}
        </span>
      </div>

      <div class="feature-copy">
        <b>${x[1]}</b>
        <small>${x[4]}</small>
      </div>

      <span class="feature-arrow">→</span>
    </button>
  `).join("");

  $$("[data-feature]").forEach(b => {
    b.onclick = () => page(b.dataset.feature);
  });
}

function fmtNum(v, d = 2) {
  if (
    v === null ||
    v === undefined ||
    Number.isNaN(Number(v))
  ) {
    return "—";
  }

  return Number(v).toLocaleString(
    "zh-TW",
    {
      minimumFractionDigits: d,
      maximumFractionDigits: d
    }
  );
}

function selfMetric(label, value, suffix = "") {
  const empty =
    value === null ||
    value === undefined ||
    value === "";

  return `
    <div class="metric-box">
      <small>${label}</small>
      <strong>
        ${empty ? "—" : value}${empty ? "" : suffix}
      </strong>
    </div>
  `;
}

/* -------------------------------------------------
   Browser history
------------------------------------------------- */

function setupPageHistory() {
  if (typeof page !== "function") {
    return;
  }

  const originalPage = page;
  let fromPopState = false;

  page = function(id) {
    originalPage(id);

    if (!fromPopState) {
      const nextHash =
        id === "home"
          ? "#home"
          : `#${id}`;

      const current =
        history.state?.twPage;

      if (current !== id) {
        history.pushState(
          {
            twPage: id
          },
          "",
          nextHash
        );
      }
    }
  };

  const initial =
    location.hash.replace("#", "") ||
    "home";

  history.replaceState(
    {
      twPage: initial
    },
    "",
    `#${initial}`
  );

  if (
    initial &&
    document.getElementById(initial)
  ) {
    originalPage(initial);
  }

  window.addEventListener(
    "popstate",
    e => {
      fromPopState = true;

      const target =
        e.state?.twPage ||
        location.hash.replace("#", "") ||
        "home";

      originalPage(
        document.getElementById(target)
          ? target
          : "home"
      );

      fromPopState = false;
    }
  );
}

/* -------------------------------------------------
   首頁 Market Pulse
------------------------------------------------- */

function ensureMarketPulse() {
  const rail = $("#featureRail");

  if (!rail) {
    return null;
  }

  let pulse = $("#marketPulse");

  if (pulse) {
    return pulse;
  }

  pulse = document.createElement("section");

  pulse.id = "marketPulse";

  pulse.className =
    "market-pulse market-pulse-pro";

  pulse.innerHTML = `
    <div class="pulse-head">
      <div>
        <span class="pulse-kicker">
          MARKET PULSE
        </span>

        <h2>
          今日市場快照
        </h2>
      </div>

      <span class="pulse-live">
        <i></i>
        LIVE
      </span>
    </div>

    <div class="market-overview-grid">

      <button
        class="market-leader-card"
        data-pulse-target="heat"
      >

        <div class="market-card-label">
          <span class="market-mini-icon">
            ▲
          </span>

          最強族群
        </div>

        <div class="market-leader-main">

          <strong data-pulse-leader-name>
            載入中
          </strong>

          <b data-pulse-leader-pct>
            —
          </b>

        </div>

        <div class="market-leader-foot">

          <span>
            依族群漲跌幅排序
          </span>

          <span>
            查看熱力圖 →
          </span>

        </div>

      </button>

      <button
        class="market-strong-card market-clickable-card"
        data-pulse-target="heat"
      >

        <div class="market-card-label">

          <span class="market-mini-icon">
            ◆
          </span>

          目前強勢族群

        </div>

        <div
          class="strong-sector-list"
          data-pulse-strong
        >
          <div class="strong-sector-empty">
            載入中
          </div>
        </div>

        <div class="market-card-link">
          查看完整熱力圖 →
        </div>

      </button>

      <button
        class="self-monitor-card"
        data-pulse-target="selfReports"
      >

        <div class="market-card-label">

          <span class="market-mini-icon">
            ◎
          </span>

          自結監控

        </div>

        <div class="self-monitor-main">

          <strong data-pulse-self>
            —
          </strong>

          <span>
            筆新公告
          </span>

        </div>

        <div class="self-monitor-foot">
          點擊查看自結公布
          <span>→</span>
        </div>

      </button>

    </div>

    <div class="daily-signal-panel">

      <div class="daily-signal-head">

        <div>
          <span class="pulse-kicker">
            TODAY'S SIGNALS
          </span>

          <h3>
            今日異動
          </h3>
        </div>

        <span class="daily-signal-note">
          點擊直接前往分頁
        </span>

      </div>

      <div class="daily-signal-grid">

        <button
          class="daily-signal-item"
          data-pulse-target="volume"
        >

          <span class="daily-signal-icon signal-volume">
            ⚡
          </span>

          <span>
            <small>
              突然放量
            </small>

            <strong data-pulse-volume>
              —
            </strong>
          </span>

          <i>→</i>

        </button>

        <button
          class="daily-signal-item"
          data-pulse-target="ai"
        >

          <span class="daily-signal-icon signal-ai">
            ✦
          </span>

          <span>
            <small>
              AI 選股
            </small>

            <strong data-pulse-ai>
              —
            </strong>
          </span>

          <i>→</i>

        </button>

        <button
          class="daily-signal-item"
          data-pulse-target="monthlyRevenue"
        >

          <span class="daily-signal-icon signal-revenue">
            ↗
          </span>

          <span>
            <small>
              MoM &gt; 10%
            </small>

            <strong data-pulse-revenue>
              —
            </strong>
          </span>

          <i>→</i>

        </button>

        <button
          class="daily-signal-item"
          data-pulse-target="selfReports"
        >

          <span class="daily-signal-icon signal-self">
            ◎
          </span>

          <span>
            <small>
              自結公告
            </small>

            <strong data-pulse-self-2>
              —
            </strong>
          </span>

          <i>→</i>

        </button>

      </div>

    </div>
  `;

  rail.insertAdjacentElement(
    "afterend",
    pulse
  );

  pulse
    .querySelectorAll(
      "[data-pulse-target]"
    )
    .forEach(
      b => {
        b.onclick =
          () =>
            page(
              b.dataset.pulseTarget
            );
      }
    );

  return pulse;
}

async function buildMarketPulse(force = false) {
  const pulse =
    ensureMarketPulse();

  if (!pulse) {
    return;
  }

  J(
    "./data/heatmap.json",
    { force }
  )
    .then(
      heatData => {

        const sectors =
          [
            ...(heatData.sectors || [])
          ]
            .filter(
              x =>
                x.change_pct !== null &&
                x.change_pct !== undefined
            )
            .sort(
              (a, b) =>
                Number(
                  b.change_pct
                ) -
                Number(
                  a.change_pct
                )
            );

        const leader =
          sectors[0] ||
          null;

        const strong =
          sectors.slice(
            1,
            5
          );

        const name =
          pulse.querySelector(
            "[data-pulse-leader-name]"
          );

        const value =
          pulse.querySelector(
            "[data-pulse-leader-pct]"
          );

        const list =
          pulse.querySelector(
            "[data-pulse-strong]"
          );

        if (name) {
          name.textContent =
            leader?.name ||
            "—";
        }

        if (value) {
          value.textContent =
            leader
              ? pct(
                  leader.change_pct
                )
              : "—";

          value.className =
            leader
              ? cl(
                  leader.change_pct
                )
              : "";
        }

        if (list) {
          list.innerHTML =
            strong.length
              ? strong
                  .map(
                    (x, i) => `
                      <div class="strong-sector-row">

                        <span class="strong-rank">
                          ${
                            String(
                              i + 2
                            ).padStart(
                              2,
                              "0"
                            )
                          }
                        </span>

                        <span class="strong-name">
                          ${x.name}
                        </span>

                        <b
                          class="${
                            cl(
                              x.change_pct
                            )
                          }"
                        >
                          ${
                            pct(
                              x.change_pct
                            )
                          }
                        </b>

                      </div>
                    `
                  )
                  .join("")
              : `
                <div class="strong-sector-empty">
                  尚無族群資料
                </div>
              `;
        }

      }
    );

  /*
   * 自結：
   * 首頁只計算台灣時間「今天」公告的公司
   */
  J(
    "./data/self_reports.json",
    { force }
  )
    .then(
      d => {

        const today =
          taiwanToday();

        const count =
          (
            d.items ||
            []
          )
            .filter(
              x =>
                normalizeSelfReportDate(
                  x.publish_date
                ) ===
                today
            )
            .length;

        pulse
          .querySelectorAll(
            "[data-pulse-self], [data-pulse-self-2]"
          )
          .forEach(
            el => {
              el.textContent =
                count;
            }
          );

      }
    );

  J(
    "./data/volume.json",
    { force }
  )
    .then(
      d => {

        const el =
          pulse.querySelector(
            "[data-pulse-volume]"
          );

        if (el) {
          el.textContent =
            (
              d.items ||
              []
            ).length;
        }

      }
    );

  J(
    "./data/ai_picks.json",
    { force }
  )
    .then(
      d => {

        const count =
          (
            d.items ||
            d.picks ||
            []
          ).length ||
          (
            (
              d.twse ||
              []
            ).length +
            (
              d.tpex ||
              []
            ).length
          );

        const el =
          pulse.querySelector(
            "[data-pulse-ai]"
          );

        if (el) {
          el.textContent =
            count ||
            "—";
        }

      }
    );

  J(
    "./data/monthly_revenue.json",
    { force }
  )
    .then(
      d => {

        const el =
          pulse.querySelector(
            "[data-pulse-revenue]"
          );

        if (el) {
          el.textContent =
            Number(
              d.mom_gt_10_count ||
              0
            );
        }

      }
    );
}

/* -------------------------------------------------
   自結頁
------------------------------------------------- */

function selfEpsMetric(x, kind, label) {
  const esc =
    value =>
      String(value ?? "")
        .replace(
          /[&<>"']/g,
          c => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
          }[c])
        );

  const value =
    x[kind + "_eps"];

  const growth =
    x[kind + "_eps_yoy"];

  const numeric =
    v =>
      v !== null &&
      v !== undefined &&
      v !== "" &&
      Number.isFinite(
        Number(v)
      );

  const period =
    x[kind + "_period"];

  const yoy =
    numeric(growth)
      ? `${
          Number(growth) > 0
            ? "+"
            : ""
        }${Number(growth).toFixed(2)}%`
      : (
          x[kind + "_eps_yoy_text"] ||
          "未取得"
        );

  return `
    <div
      class="metric-box"
      style="min-width:0"
    >
      <small>
        ${esc(label)}
        ${
          period
            ? `（${esc(period)}）`
            : ""
        }
      </small>

      <strong
        style="
          font-size:clamp(20px,3vw,30px);
          overflow-wrap:anywhere
        "
      >
        ${
          numeric(value)
            ? Number(value).toFixed(2) + " 元"
            : "未取得"
        }
      </strong>

      <small
        style="
          display:block;
          margin-top:8px;
          line-height:1.5
        "
      >
        與去年同期增減
        <br>

        <b>
          ${esc(yoy)}
        </b>
      </small>
    </div>
  `;
}

async function selfReports(force = false) {
  const d =
    await J(
      "./data/self_reports.json",
      { force }
    );

  const heroP =
    $("#selfReports .hero p");

  if (heroP) {
    heroP.textContent =
      "全台股即時監控｜每 30 分鐘自動檢查｜僅新公告自動推播";
  }

  if ($("#selfWeekBadge")) {
    $("#selfWeekBadge")
      .textContent =
        "每30分鐘";
  }

  const tabs =
    $("#selfWeekTabs");

  if (tabs) {
    tabs.innerHTML = "";
    tabs.style.display =
      "none";
  }

  const status =
    $("#selfStatus");

  if (status) {
    const twse =
      d.source_status?.twse;

    const tpex =
      d.source_status?.tpex;

    const sourceText =
      [
        twse?.ok
          ? "上市正常"
          : "上市來源異常",

        tpex?.ok
          ? "上櫃正常"
          : "上櫃來源異常"
      ]
        .join(
          " · "
        );

    status.innerHTML =
      d.updated_at
        ? `
          <span class="status-dot"></span>

          最後更新
          ${d.updated_at}

          <span class="status-divider">
            ·
          </span>

          ${sourceText}
        `
        : "尚未開始自結監控";
  }

  const allItems =
    d.items ||
    [];

  /*
   * 所有有資料的公告日期
   * 新日期排在最前面
   */
  const availableDates =
    [
      ...new Set(
        allItems
          .map(
            x =>
              normalizeSelfReportDate(
                x.publish_date
              )
          )
          .filter(
            Boolean
          )
      )
    ]
      .sort(
        (a, b) =>
          b.localeCompare(a)
      );

  /*
   * 第一次進入自結頁：
   * 預設顯示最新一個有資料的日期
   *
   * 例如週日沒有公告，
   * 就會顯示上一個有公告的交易日
   */
  if (
    !selfReportDate ||
    !availableDates.includes(
      selfReportDate
    )
  ) {
    selfReportDate =
      availableDates[0] ||
      "";
  }

  /*
   * 建立日期篩選器
   * 不需要修改 index.html
   */
  const searchInput =
    $("#selfReportSearchInput");

  const searchMeta =
    $("#selfReportSearchMeta");

  let dateWrap =
    $("#selfReportDateFilter");

  if (!dateWrap) {
    dateWrap =
      document.createElement(
        "div"
      );

    dateWrap.id =
      "selfReportDateFilter";

    dateWrap.style.cssText = `
      display:flex;
      align-items:center;
      gap:10px;
      flex-wrap:wrap;
      margin:0 0 12px 0;
      width:100%;
    `;

    /*
     * 優先放在搜尋框上方
     */
    if (
      searchInput &&
      searchInput.parentElement
    ) {
      searchInput
        .parentElement
        .insertAdjacentElement(
          "beforebegin",
          dateWrap
        );
    } else if (
      searchMeta &&
      searchMeta.parentElement
    ) {
      searchMeta
        .parentElement
        .insertBefore(
          dateWrap,
          searchMeta
        );
    }
  }

  if (dateWrap) {
    dateWrap.innerHTML = `
      <label
        for="selfReportDateSelect"
        style="
          font-size:13px;
          font-weight:700;
          color:var(--muted);
          white-space:nowrap;
        "
      >
        公告日期
      </label>

      <select
        id="selfReportDateSelect"
        aria-label="篩選自結公告日期"
        style="
          min-width:160px;
          min-height:42px;
          padding:0 36px 0 12px;
          border:1px solid var(--line);
          border-radius:11px;
          background:var(--card);
          color:inherit;
          font:inherit;
          font-weight:700;
          outline:none;
        "
      >
        ${
          availableDates.length
            ? availableDates
                .map(
                  date => `
                    <option
                      value="${date}"
                      ${
                        date === selfReportDate
                          ? "selected"
                          : ""
                      }
                    >
                      ${date}
                    </option>
                  `
                )
                .join("")
            : `
              <option value="">
                尚無資料
              </option>
            `
        }
      </select>
    `;

    const dateSelect =
      $("#selfReportDateSelect");

    if (dateSelect) {
      dateSelect.onchange =
        () => {
          selfReportDate =
            dateSelect.value;

          selfReports(
            false
          );
        };
    }
  }

  /*
   * 第一層：
   * 先依公告日期篩選
   */
  const dateItems =
    selfReportDate
      ? allItems.filter(
          x =>
            normalizeSelfReportDate(
              x.publish_date
            ) ===
            selfReportDate
        )
      : [];

  const normalizeSearch =
    value =>
      String(
        value ||
        ""
      )
        .trim()
        .toLowerCase()
        .replace(
          /\s+/g,
          ""
        );

  const keyword =
    normalizeSearch(
      selfReportSearch
    );

  /*
   * 第二層：
   * 再在所選日期裡搜尋股票
   */
  const arr =
    !keyword
      ? dateItems
      : dateItems.filter(
          x => {
            const ticker =
              normalizeSearch(
                x.ticker
              );

            const name =
              normalizeSearch(
                x.name
              );

            return (
              ticker.includes(
                keyword
              ) ||
              name.includes(
                keyword
              )
            );
          }
        );

  const input =
    $("#selfReportSearchInput");

  if (
    input &&
    input.value !==
      selfReportSearch
  ) {
    input.value =
      selfReportSearch;
  }

  const clearBtn =
    $("#selfReportSearchClear");

  if (clearBtn) {
    clearBtn.style.display =
      selfReportSearch
        ? "inline-flex"
        : "none";
  }

  const resultMeta =
    $("#selfReportSearchMeta");

  if (resultMeta) {
    if (
      !selfReportDate
    ) {
      resultMeta.textContent =
        "目前沒有自結資料";
    } else if (
      selfReportSearch
    ) {
      resultMeta.textContent =
        `找到 ${arr.length} 筆｜${selfReportDate} 共 ${dateItems.length} 筆自結`;
    } else {
      resultMeta.textContent =
        `${selfReportDate}｜共 ${dateItems.length} 筆自結`;
    }
  }

  const box =
    $("#selfReportCards");

  if (!box) {
    return;
  }

  if (!arr.length) {
    const safe =
      String(
        selfReportSearch
      )
        .replace(
          /[&<>"']/g,
          c => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
          }[c])
        );

    box.innerHTML = `
      <div
        class="
          card
          empty
          self-empty
        "
      >

        <div class="empty-icon">
          ${
            featureIcon(
              "earnings"
            )
          }
        </div>

        <b>
          ${
            selfReportSearch
              ? `找不到「${safe}」的自結資料`
              : selfReportDate
                ? `${selfReportDate} 沒有自結公告`
                : "目前尚未偵測到新的自結公告"
          }
        </b>

        <span>
          ${
            selfReportSearch
              ? `搜尋範圍：${selfReportDate || "目前日期"}`
              : "系統每 30 分鐘自動檢查"
          }
        </span>

      </div>
    `;

    return;
  }

  box.innerHTML =
    arr
      .map(
        x => `
          <div
            class="
              card
              data-card
              self-report-card
            "
          >

            <div class="card-accent"></div>

            <div class="eyebrow">
              ${
                x.publish_date ||
                ""
              }

              ${
                x.publish_time ||
                ""
              }
            </div>

            <div class="titleline">

              <b>
                ${
                  x.name ||
                  x.ticker
                }
              </b>

              <span>
                ${
                  x.ticker ||
                  ""
                }
              </span>

            </div>

            <div
              class="metric-grid"
              style="
                grid-template-columns:
                repeat(2,minmax(0,1fr));
                gap:12px
              "
            >
              ${
                selfEpsMetric(
                  x,
                  "monthly",
                  "當月 EPS"
                )
              }

              ${
                selfEpsMetric(
                  x,
                  "quarter",
                  "上一季 EPS"
                )
              }
            </div>

          </div>
        `
      )
      .join("");
}

function setupSelfReportSearch() {
  const input =
    $("#selfReportSearchInput");

  const clearBtn =
    $("#selfReportSearchClear");

  if (!input) {
    return;
  }

  let timer =
    null;

  input.addEventListener(
    "input",
    () => {
      selfReportSearch =
        input.value;

      clearTimeout(
        timer
      );

      timer =
        setTimeout(
          () => {
            selfReports(false);
          },
          120
        );
    }
  );

  input.addEventListener(
    "keydown",
    e => {
      if (
        e.key ===
        "Escape"
      ) {
        selfReportSearch = "";
        input.value = "";

        selfReports(false);

        input.blur();
      }
    }
  );

  if (clearBtn) {
    clearBtn.onclick =
      () => {
        selfReportSearch = "";
        input.value = "";

        selfReports(false);

        input.focus();
      };
  }
}

/* -------------------------------------------------
   月營收卡片
------------------------------------------------- */

function revenueCard(x) {
  const mom =
    Number(
      x.mom
    );

  const isMomHot =
    Number.isFinite(
      mom
    ) &&
    mom > 10;

  return `
    <div
      class="
        revenue-card
        ${
          isMomHot
            ? "mom-hot"
            : ""
        }
      "
    >

      ${
        isMomHot
          ? `
            <div class="mom-hot-glow"></div>
          `
          : ""
      }

      <div class="top">

        <div>

          <span class="stock-name">
            ${
              x.name ||
              x.ticker
            }
          </span>

          <span class="ticker">
            ${
              x.ticker ||
              ""
            }
          </span>

        </div>

        ${
          isMomHot
            ? `
              <span class="mom-hot-badge">
                MoM &gt; 10%
              </span>
            `
            : ""
        }

      </div>

      <div class="rev">
        ${
          fmtNum(
            x.revenue_100m,
            2
          )
        }
        億
      </div>

      <div class="rev-label">
        單月營收
      </div>

      <div class="changes">

        <span>
          <small>
            MoM
          </small>

          <b
            class="${
              cl(
                x.mom
              )
            }"
          >
            ${
              pct(
                x.mom
              )
            }
          </b>
        </span>

        <span>
          <small>
            YoY
          </small>

          <b
            class="${
              cl(
                x.yoy
              )
            }"
          >
            ${
              pct(
                x.yoy
              )
            }
          </b>
        </span>

      </div>

    </div>
  `;
}

function dedupeRevenueStocks(
  sectors
) {
  return [
    ...new Map(
      (sectors || [])
        .flatMap(
          sec =>
            sec.stocks ||
            []
        )
        .map(
          x => [
            x.ticker,
            x
          ]
        )
    ).values()
  ];
}

/* -------------------------------------------------
   月營收頁
------------------------------------------------- */

async function monthlyRevenue(force = false) {
  const d =
    await J(
      "./data/monthly_revenue.json",
      { force }
    );

  if ($("#revenueMonthBadge")) {
    $("#revenueMonthBadge")
      .textContent =
        d.month_label
          ? `目前顯示 ${d.month_label}`
          : "尚無資料";
  }

  const revenueHeroP =
    $("#monthlyRevenue .hero p");

  if (revenueHeroP) {
    revenueHeroP.textContent =
      "19 個科技族群｜最新已公布月份｜營收、MoM、YoY";
  }

  if ($("#revenueStatus")) {
    $("#revenueStatus")
      .textContent =
        d.updated_at
          ? `最後更新 ${d.updated_at}｜MoM > 10%：金色標示`
          : "尚未產生月營收資料";
  }

  const sectors =
    d.sectors ||
    [];

  const tabs =
    $("#revenueSectorTabs");

  let selector =
    document.querySelector(
      "#revenueSectorPicker"
    );

  if (
    !selector &&
    tabs
  ) {
    selector =
      document.createElement(
        "div"
      );

    selector.id =
      "revenueSectorPicker";

    selector.className =
      "revenue-sector-picker";

    tabs.before(
      selector
    );
  }

  if (selector) {
    selector.innerHTML = `
      <label for="revenueSectorSelect">
        選擇族群
      </label>

      <div class="revenue-select-wrap">

        <select id="revenueSectorSelect">

          <option value="all">
            全部族群
          </option>

          ${
            sectors
              .map(
                s => `
                  <option value="${s.name}">
                    ${s.name}
                  </option>
                `
              )
              .join("")
          }

        </select>

        <span class="revenue-select-arrow">
          ⌄
        </span>

      </div>
    `;

    const sectorSelect =
      selector.querySelector(
        "#revenueSectorSelect"
      );

    if (sectorSelect) {
      sectorSelect.value =
        revenueSectorSelected;

      sectorSelect.onchange =
        () => {
          revenueSectorSelected =
            sectorSelect.value;

          monthlyRevenue(false);
        };
    }
  }

  let sortBox =
    document.querySelector(
      "#revenueMomSort"
    );

  if (
    !sortBox &&
    tabs
  ) {
    sortBox =
      document.createElement(
        "div"
      );

    sortBox.id =
      "revenueMomSort";

    sortBox.className =
      "revenue-sort-row";

    tabs.before(
      sortBox
    );
  }

  if (sortBox) {
    sortBox.innerHTML = `
      <button
        type="button"
        class="
          week-pill
          revenue-sort-pill
          ${
            revenueMomSort
              ? "active"
              : ""
          }
        "
        aria-pressed="${revenueMomSort}"
      >
        ↓ MoM 高→低
      </button>

      <span class="revenue-sort-note">
        ${
          revenueMomSort
            ? "再次點擊恢復族群原排序"
            : "MoM > 10% 個股會以金色標示"
        }
      </span>
    `;

    sortBox
      .querySelector(
        "button"
      )
      .onclick =
      () => {
        revenueMomSort =
          !revenueMomSort;

        monthlyRevenue(false);
      };
  }

  if (tabs) {
    tabs.innerHTML = `

      <button
        class="
          week-pill
          ${
            revenueSectorSelected === "all"
              ? "active"
              : ""
          }
        "
        data-rev-sec="all"
      >
        全部族群
      </button>

      ${
        sectors
          .map(
            s => `
              <button
                class="
                  week-pill
                  ${
                    revenueSectorSelected === s.name
                      ? "active"
                      : ""
                  }
                "
                data-rev-sec="${s.name}"
              >
                ${s.name}
              </button>
            `
          )
          .join("")
      }

    `;

    $$(
      "[data-rev-sec]"
    )
      .forEach(
        b => {
          b.onclick =
            () => {
              revenueSectorSelected =
                b.dataset.revSec;

              monthlyRevenue(false);
            };
        }
      );
  }

  const selectedSectors =
    revenueSectorSelected === "all"
      ? sectors
      : sectors.filter(
          s =>
            s.name ===
            revenueSectorSelected
        );

  let list;

  if (revenueMomSort) {
    let stocks;

    if (
      revenueSectorSelected ===
      "all"
    ) {
      stocks =
        dedupeRevenueStocks(
          selectedSectors
        );
    } else {
      stocks = [
        ...(
          selectedSectors[0]
            ?.stocks ||
          []
        )
      ];
    }

    stocks.sort(
      (a, b) =>
        Number(
          b.mom ||
          0
        ) -
        Number(
          a.mom ||
          0
        )
    );

    list =
      stocks.length
        ? [
            {
              name:
                revenueSectorSelected ===
                "all"
                  ? "MoM 排序"
                  : selectedSectors[0]
                      ?.name ||
                    "MoM 排序",

              stocks
            }
          ]
        : [];

  } else {
    list =
      selectedSectors;
  }

  const box =
    $("#revenueSections");

  if (!box) {
    return;
  }

  if (!list.length) {
    box.innerHTML = `
      <div class="card empty">
        目前沒有月營收資料
      </div>
    `;

    return;
  }

  box.innerHTML =
    list
      .map(
        sec => {

          const hotCount =
            (
              sec.stocks ||
              []
            )
              .filter(
                x =>
                  Number(
                    x.mom
                  ) > 10
              )
              .length;

          return `
            <section class="sector-revenue">

              <div class="sector-revenue-head">

                <div>

                  <h2>
                    ${sec.name}
                  </h2>

                  ${
                    hotCount
                      ? `
                        <span class="sector-mom-count">
                          ${hotCount}
                          檔 MoM &gt; 10%
                        </span>
                      `
                      : ""
                  }

                </div>

                <span>
                  ${
                    (
                      sec.stocks ||
                      []
                    ).length
                  }
                  檔
                </span>

              </div>

              <div class="revenue-grid">

                ${
                  (
                    sec.stocks ||
                    []
                  )
                    .map(
                      revenueCard
                    )
                    .join("")
                }

              </div>

            </section>
          `;
        }
      )
      .join("");
}

/* -------------------------------------------------
   導覽排序
------------------------------------------------- */

function reorderNavigation() {
  const nav =
    document.querySelector(
      "header nav"
    );

  if (nav) {
    const heatBtn =
      nav.querySelector(
        '[data-p="heat"]'
      );

    const selfBtn =
      nav.querySelector(
        '[data-p="selfReports"]'
      );

    if (
      heatBtn &&
      selfBtn
    ) {
      nav.insertBefore(
        heatBtn,
        selfBtn
      );
    }
  }

  const select =
    $("#mobileNav");

  if (select) {
    const heatOption =
      select.querySelector(
        'option[value="heat"]'
      );

    const selfOption =
      select.querySelector(
        'option[value="selfReports"]'
      );

    if (
      heatOption &&
      selfOption
    ) {
      select.insertBefore(
        heatOption,
        selfOption
      );
    }
  }
}

/* -------------------------------------------------
   固定返回總覽按鈕
------------------------------------------------- */

function setupBackHomeButton() {
  let btn =
    document.getElementById(
      "backHomeBtn"
    );

  if (!btn) {
    btn =
      document.createElement(
        "button"
      );

    btn.id =
      "backHomeBtn";

    btn.type =
      "button";

    btn.setAttribute(
      "aria-label",
      "返回總覽"
    );

    btn.innerHTML = `
      <span class="back-home-icon">
        ←
      </span>

      <span>
        總覽
      </span>
    `;

    document.body
      .appendChild(
        btn
      );
  }

  const refresh =
    () => {
      const active =
        document.querySelector(
          ".page.active"
        );

      const isHome =
        !active ||
        active.id ===
          "home";

      btn.classList.toggle(
        "show",
        !isHome
      );
    };

  btn.onclick =
    () => {
      if (
        typeof page ===
        "function"
      ) {
        page(
          "home"
        );
      }

      refresh();
    };

  const observer =
    new MutationObserver(
      refresh
    );

  const main =
    document.querySelector(
      "main"
    ) ||
    document.body;

  observer.observe(
    main,
    {
      subtree: true,
      attributes: true,
      attributeFilter: [
        "class"
      ]
    }
  );

  refresh();
}

/* -------------------------------------------------
   各分頁更新資訊
------------------------------------------------- */

const pageUpdateConfig = {
  heat: {
    label:
      "交易日每 5 分鐘",

    file:
      "./data/heatmap.json"
  },

  selfReports: {
    label:
      "每 30 分鐘",

    file:
      "./data/self_reports.json"
  },

  flows: {
    label:
      "交易日收盤後",

    file:
      "./data/institutional.json"
  },

  volume: {
    label:
      "交易日收盤後",

    file:
      "./data/volume.json"
  },

  turnover: {
    label:
      "交易日收盤後",

    file:
      "./data/turnover.json"
  },

  marginLending: {
    label:
      "交易日收盤後",

    file:
      "./data/margin_lending.json"
  },

  ai: {
    label:
      "每日 18:00",

    file:
      "./data/ai_picks.json"
  },

  reports: {
    label:
      "有新報告時更新",

    file:
      "./data/reports.json"
  },

  holders: {
    label:
      "週六 15:00",

    file:
      "./data/holders.json"
  },

  monthlyRevenue: {
    label:
      "每月 1–15 日定時檢查",

    file:
      "./data/monthly_revenue.json"
  }
};

function formatUpdateTime(
  raw
) {
  if (!raw) {
    return "尚無更新紀錄";
  }

  return String(raw)
    .replace(
      "T",
      " "
    )
    .replace(
      "+08:00",
      ""
    );
}

async function setupPageUpdateMeta(
  pageId
) {
  const id =
    pageId ||
    document.querySelector(
      ".page.active"
    )?.id;

  const cfg =
    pageUpdateConfig[id];

  if (!cfg) {
    return;
  }

  const section =
    document.getElementById(
      id
    );

  if (!section) {
    return;
  }

  const hero =
    section.querySelector(
      ".hero"
    );

  if (!hero) {
    return;
  }

  let data =
    {};

  try {
    data =
      await J(
        cfg.file
      );
  } catch (e) {
    data = {};
  }

  const actual =
    data.updated_at ||
    data.date ||
    data.month_label ||
    "";

  let meta =
    section.querySelector(
      ".page-update-meta"
    );

  if (!meta) {
    meta =
      document.createElement(
        "div"
      );

    meta.className =
      "page-update-meta";

    hero.insertAdjacentElement(
      "afterend",
      meta
    );
  }

  meta.innerHTML = `
    <span class="page-update-dot"></span>

    <span>
      <b>
        更新頻率
      </b>

      ${cfg.label}
    </span>

    <span class="page-update-separator">
      ·
    </span>

    <span>
      <b>
        最後更新
      </b>

      ${
        formatUpdateTime(
          actual
        )
      }
    </span>
  `;
}

/* -------------------------------------------------
   字體大小控制
------------------------------------------------- */

const FONT_LEVELS = [
  0.95,
  1,
  1.1,
  1.2
];

function applyFontScale(
  scale
) {
  const safeScale =
    FONT_LEVELS.includes(
      scale
    )
      ? scale
      : 1;

  document.documentElement
    .style.setProperty(
      "--user-font-scale",
      safeScale
    );

  localStorage.setItem(
    "tw-font-scale",
    String(
      safeScale
    )
  );

  const value =
    document.querySelector(
      "#fontScaleValue"
    );

  if (value) {
    value.textContent =
      `${
        Math.round(
          safeScale *
          100
        )
      }%`;
  }
}

function setupFontScaleControl() {
  const headerActions =
    document.querySelector(
      ".header-actions"
    );

  if (!headerActions) {
    return;
  }

  if (
    document.getElementById(
      "fontScaleControl"
    )
  ) {
    return;
  }

  const saved =
    Number(
      localStorage.getItem(
        "tw-font-scale"
      ) ||
      1
    );

  applyFontScale(
    FONT_LEVELS.includes(
      saved
    )
      ? saved
      : 1
  );

  const wrap =
    document.createElement(
      "div"
    );

  wrap.id =
    "fontScaleControl";

  wrap.className =
    "font-scale-control";

  wrap.innerHTML = `
    <button
      type="button"
      id="fontScaleToggle"
      class="font-scale-toggle"
      aria-label="調整字體大小"
    >
      Aa
    </button>

    <div
      id="fontScaleMenu"
      class="font-scale-menu"
    >

      <button
        type="button"
        data-font-action="minus"
        aria-label="縮小字體"
      >
        A−
      </button>

      <span id="fontScaleValue">
        100%
      </span>

      <button
        type="button"
        data-font-action="plus"
        aria-label="放大字體"
      >
        A+
      </button>

    </div>
  `;

  headerActions.prepend(
    wrap
  );

  const toggle =
    wrap.querySelector(
      "#fontScaleToggle"
    );

  const menu =
    wrap.querySelector(
      "#fontScaleMenu"
    );

  toggle.onclick =
    e => {
      e.stopPropagation();

      menu.classList.toggle(
        "show"
      );
    };

  wrap
    .querySelector(
      '[data-font-action="minus"]'
    )
    .onclick =
      e => {
        e.stopPropagation();

        const current =
          Number(
            localStorage.getItem(
              "tw-font-scale"
            ) ||
            1
          );

        const index =
          Math.max(
            0,
            FONT_LEVELS.indexOf(
              current
            )
          );

        applyFontScale(
          FONT_LEVELS[
            Math.max(
              0,
              index - 1
            )
          ]
        );
      };

  wrap
    .querySelector(
      '[data-font-action="plus"]'
    )
    .onclick =
      e => {
        e.stopPropagation();

        const current =
          Number(
            localStorage.getItem(
              "tw-font-scale"
            ) ||
            1
          );

        const index =
          Math.max(
            0,
            FONT_LEVELS.indexOf(
              current
            )
          );

        applyFontScale(
          FONT_LEVELS[
            Math.min(
              FONT_LEVELS.length -
              1,
              index + 1
            )
          ]
        );
      };

  document.addEventListener(
    "click",
    e => {
      if (
        !wrap.contains(
          e.target
        )
      ) {
        menu.classList.remove(
          "show"
        );
      }
    }
  );

  applyFontScale(
    FONT_LEVELS.includes(
      saved
    )
      ? saved
      : 1
  );
}

/* -------------------------------------------------
   首頁版面順序
------------------------------------------------- */

function setupHomeOrder() {
  const home =
    document.getElementById(
      "home"
    );

  const hero =
    home?.querySelector(
      ".hero"
    );

  const rail =
    document.getElementById(
      "featureRail"
    );

  if (
    !home ||
    !hero ||
    !rail
  ) {
    return;
  }

  home.insertBefore(
    rail,
    hero
  );

  const homeCards =
    document.getElementById(
      "homeCards"
    );

  const topSectors =
    document.getElementById(
      "topSectors"
    );

  if (homeCards) {
    homeCards.style.display =
      "none";
  }

  if (topSectors) {
    topSectors.style.display =
      "none";

    const oldSection =
      topSectors
        .previousElementSibling;

    if (
      oldSection &&
      oldSection.classList.contains(
        "section"
      )
    ) {
      oldSection.style.display =
        "none";
    }
  }
}

/* -------------------------------------------------
   自結 / 月營收 Lazy Load
------------------------------------------------- */

const extraLoading =
  new Map();

function loadExtraPage(id) {
  let fn =
    null;

  if (
    id ===
    "selfReports"
  ) {
    fn =
      selfReports;
  }

  if (
    id ===
    "monthlyRevenue"
  ) {
    fn =
      monthlyRevenue;
  }

  if (!fn) {
    return;
  }

  if (
    extraLoading.has(
      id
    )
  ) {
    return extraLoading.get(
      id
    );
  }

  const promise =
    Promise.resolve()
      .then(
        () =>
          fn(false)
      )
      .finally(
        () => {
          extraLoading.delete(
            id
          );
        }
      );

  extraLoading.set(
    id,
    promise
  );

  return promise;
}

function bindExtraLazyPages() {
  if (
    typeof page !==
    "function"
  ) {
    return;
  }

  const originalPage =
    page;

  page =
    function(id) {

      originalPage(id);

      requestAnimationFrame(
        () => {

          loadExtraPage(id);

          setupPageUpdateMeta(
            id
          );

        }
      );
    };
}

/* -------------------------------------------------
   啟動
------------------------------------------------- */

setupPageHistory();

reorderNavigation();

buildFeatureRail();

setupHomeOrder();

/*
 * 首頁先直接建立 Market Pulse 外框
 * 不等任何 JSON
 */
ensureMarketPulse();

/*
 * 下一個 frame 再背景抓資料
 */
requestAnimationFrame(
  () => {
    buildMarketPulse(false);
  }
);

setupSelfReportSearch();

setupFontScaleControl();

setupBackHomeButton();

bindExtraLazyPages();

/*
 * 只處理目前真的正在看的分頁
 */
requestAnimationFrame(
  () => {

    const id =
      document.querySelector(
        ".page.active"
      )?.id ||
      "home";

    loadExtraPage(
      id
    );

    setupPageUpdateMeta(
      id
    );

  }
);

console.log(
  "[UI] performance module ready"
);
