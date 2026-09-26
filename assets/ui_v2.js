const featureItems = [
  ["heat","市場熱力圖","heat","red","19族群・5分鐘"],
  ["selfReports","自結公布","earnings","amber","22:00＋08:00"],
  ["flows","籌碼日報","flow","blue","法人"],
  ["volume","突然放量","bolt","amber","科技股"],
  ["turnover","成交排行","chart","blue","TOP30"],
  ["marginLending","融資／借券","swap","violet","科技股"],
  ["ai","AI選股","spark","green","每天18:00"],
  ["reports","券商報告","report","amber","研究報告"],
  ["holders","大戶籌碼","holders","violet","週更"],
  ["monthlyRevenue","月營收公布","revenue","green","19族群"]
];

let revenueSectorSelected = "all";
let autoRefreshRunning = false;


/* =========================================================
   Feature icons
   ========================================================= */

function featureIcon(name) {
  const icons = {
    heat: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7" rx="2"></rect>
        <rect x="14" y="3" width="7" height="7" rx="2"></rect>
        <rect x="3" y="14" width="7" height="7" rx="2"></rect>
        <rect x="14" y="14" width="7" height="7" rx="2"></rect>
      </svg>
    `,

    earnings: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 20V10"></path>
        <path d="M10 20V4"></path>
        <path d="M15 20v-7"></path>
        <path d="M20 20V7"></path>
        <path d="M3 20h19"></path>
      </svg>
    `,

    flow: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7h12"></path>
        <path d="m13 4 3 3-3 3"></path>
        <path d="M20 17H8"></path>
        <path d="m11 14-3 3 3 3"></path>
      </svg>
    `,

    bolt: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M13 2 5 14h6l-1 8 9-13h-6z"></path>
      </svg>
    `,

    chart: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 20V10"></path>
        <path d="M10 20V4"></path>
        <path d="M16 20v-7"></path>
        <path d="M22 20H2"></path>
      </svg>
    `,

    swap: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 7h12l-3-3"></path>
        <path d="m19 7-3 3"></path>
        <path d="M17 17H5l3 3"></path>
        <path d="m5 17 3-3"></path>
      </svg>
    `,

    spark: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="m12 2 1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8z"></path>
        <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"></path>
      </svg>
    `,

    report: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 3h9l4 4v14H6z"></path>
        <path d="M15 3v5h5"></path>
        <path d="M9 12h7"></path>
        <path d="M9 16h7"></path>
      </svg>
    `,

    holders: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="9" cy="8" r="3"></circle>
        <circle cx="17" cy="9" r="2"></circle>
        <path d="M3 20c0-4 2.5-6 6-6s6 2 6 6"></path>
        <path d="M15 15c3 0 5 1.5 5 5"></path>
      </svg>
    `,

    revenue: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 19V5"></path>
        <path d="M4 19h16"></path>
        <path d="m7 15 4-4 3 2 5-6"></path>
        <path d="M16 7h3v3"></path>
      </svg>
    `
  };

  return icons[name] || icons.chart;
}


/* =========================================================
   Feature rail
   ========================================================= */

function buildFeatureRail() {
  const box = $("#featureRail");

  if (!box) {
    return;
  }

  box.innerHTML = featureItems
    .map(
      (x, i) => `
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
      `
    )
    .join("");

  $$("[data-feature]").forEach(b => {
    b.onclick = () => {
      page(
        b.dataset.feature
      );
    };
  });
}


/* =========================================================
   Helpers
   ========================================================= */

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


function selfMetric(
  label,
  value,
  suffix = ""
) {
  const empty =
    value === null ||
    value === undefined ||
    value === "";

  return `
    <div class="metric-box">
      <small>${label}</small>

      <strong>
        ${
          empty
            ? "—"
            : value
        }${
          empty
            ? ""
            : suffix
        }
      </strong>
    </div>
  `;
}


/* =========================================================
   Browser history
   ========================================================= */

function setupPageHistory() {
  if (
    typeof page !==
    "function"
  ) {
    return;
  }

  const originalPage =
    page;

  let fromPopState =
    false;

  page =
    function(id) {
      originalPage(id);

      if (
        !fromPopState
      ) {
        const nextHash =
          id === "home"
            ? "#home"
            : `#${id}`;

        const current =
          history
            .state
            ?.twPage;

        if (
          current !== id
        ) {
          history.pushState(
            {
              twPage:
                id
            },
            "",
            nextHash
          );
        }
      }
    };

  const initial =
    location.hash
      .replace(
        "#",
        ""
      ) ||
    "home";

  history.replaceState(
    {
      twPage:
        initial
    },
    "",
    `#${initial}`
  );

  if (
    initial &&
    document.getElementById(
      initial
    )
  ) {
    originalPage(
      initial
    );
  }

  window.addEventListener(
    "popstate",
    e => {
      fromPopState =
        true;

      const target =
        e.state
          ?.twPage ||
        location.hash
          .replace(
            "#",
            ""
          ) ||
        "home";

      originalPage(
        document.getElementById(
          target
        )
          ? target
          : "home"
      );

      fromPopState =
        false;
    }
  );
}


/* =========================================================
   返回總覽按鈕
   ========================================================= */

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

    document.body.appendChild(
      btn
    );
  }

  const refresh = () => {
    const active =
      document.querySelector(
        ".page.active"
      );

    const isHome =
      !active ||
      active.id === "home";

    btn.classList.toggle(
      "show",
      !isHome
    );
  };

  btn.onclick = () => {
    if (
      typeof page ===
      "function"
    ) {
      page("home");
    }

    refresh();
  };

  const observer =
    new MutationObserver(
      refresh
    );

  document
    .querySelectorAll(
      ".page"
    )
    .forEach(
      el => {
        observer.observe(
          el,
          {
            attributes:
              true,

            attributeFilter:
              ["class"]
          }
        );
      }
    );

  refresh();
}


/* =========================================================
   首頁 Market Pulse
   ========================================================= */

async function buildMarketPulse() {
  const rail =
    $("#featureRail");

  if (
    !rail ||
    $("#marketPulse")
  ) {
    return;
  }

  const [
    heatData,
    selfData,
    revenueData
  ] =
    await Promise.all([
      J(
        "./data/heatmap.json"
      ),
      J(
        "./data/self_reports.json"
      ),
      J(
        "./data/monthly_revenue.json"
      )
    ]);

  const sectors =
    [
      ...(
        heatData
          .sectors ||
        []
      )
    ]
      .filter(
        x =>
          x.change_pct !==
            null &&
          x.change_pct !==
            undefined
      )
      .sort(
        (
          a,
          b
        ) =>
          Number(
            b.change_pct
          ) -
          Number(
            a.change_pct
          )
      );

  const leaders =
    sectors.slice(
      0,
      3
    );

  const selfCount =
    (
      selfData.items ||
      []
    ).length;

  const newHighCount =
    (
      revenueData
        .sectors ||
      []
    )
      .flatMap(
        x =>
          x.stocks ||
          []
      )
      .filter(
        x =>
          x.record_high ===
          true
      )
      .length;

  const pulse =
    document.createElement(
      "section"
    );

  pulse.id =
    "marketPulse";

  pulse.className =
    "market-pulse";

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

    <div class="pulse-grid">
      <button
        class="pulse-main"
        data-pulse-target="heat"
      >
        <span class="pulse-label">
          最強族群
        </span>

        <strong>
          ${
            leaders[0]
              ?.name ||
            "—"
          }
        </strong>

        <b
          class="${
            cl(
              leaders[0]
                ?.change_pct
            )
          }"
        >
          ${
            leaders[0]
              ? pct(
                  leaders[0]
                    .change_pct
                )
              : "—"
          }
        </b>

        <span class="mini-bars">
          ${
            leaders
              .map(
                x => `
                  <i
                    style="
                      --bar:${
                        Math.min(
                          100,
                          Math.max(
                            18,
                            Math.abs(
                              Number(
                                x.change_pct ||
                                0
                              )
                            ) *
                            22
                          )
                        )
                      }%
                    "
                    title="${
                      x.name
                    } ${
                      pct(
                        x.change_pct
                      )
                    }"
                  ></i>
                `
              )
              .join("")
          }
        </span>
      </button>

      <button
        class="pulse-stat"
        data-pulse-target="selfReports"
      >
        <span>
          自結監控
        </span>

        <strong>
          ${selfCount}
        </strong>

        <small>
          累積新公告
        </small>
      </button>

      <button
        class="pulse-stat"
        data-pulse-target="monthlyRevenue"
      >
        <span>
          營收新高
        </span>

        <strong>
          ${newHighCount}
        </strong>

        <small>
          ${
            revenueData
              .month_label ||
            "最新月份"
          }
        </small>
      </button>
    </div>
  `;

  rail.parentNode
    .insertBefore(
      pulse,
      rail
    );

  $$(
    "[data-pulse-target]"
  ).forEach(
    b => {
      b.onclick =
        () =>
          page(
            b.dataset
              .pulseTarget
          );
    }
  );
}


/* =========================================================
   自結頁
   ========================================================= */

async function selfReports() {
  const d =
    await J(
      "./data/self_reports.json"
    );

  const heroP =
    $(
      "#selfReports .hero p"
    );

  if (
    heroP
  ) {
    heroP.textContent =
      "全台股即時監控｜22:00 收盤後檢查｜次日 08:00 盤前複查｜新公告自動推播";
  }

  if (
    $("#selfWeekBadge")
  ) {
    $(
      "#selfWeekBadge"
    ).textContent =
      "22:00＋08:00";
  }

  const tabs =
    $("#selfWeekTabs");

  if (
    tabs
  ) {
    tabs.innerHTML =
      "";

    tabs.style.display =
      "none";
  }

  const status =
    $("#selfStatus");

  if (
    status
  ) {
    const twse =
      d.source_status
        ?.twse;

    const tpex =
      d.source_status
        ?.tpex;

    const sourceText =
      [
        twse?.ok
          ? "上市正常"
          : "上市來源異常",

        tpex?.ok
          ? "上櫃正常"
          : "上櫃來源異常"
      ].join(
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

          <span class="status-divider">
            ·
          </span>

          Pushover 已啟用
        `
        : "尚未開始自結監控";
  }

  const arr =
    d.items ||
    [];

  const box =
    $(
      "#selfReportCards"
    );

  if (
    !box
  ) {
    return;
  }

  if (
    !arr.length
  ) {
    box.innerHTML = `
      <div class="card empty self-empty">
        <div class="empty-icon">
          ${
            featureIcon(
              "earnings"
            )
          }
        </div>

        <b>
          目前尚未偵測到新的自結公告
        </b>

        <span>
          系統會在 22:00 與次日 08:00 自動檢查
        </span>
      </div>
    `;

    return;
  }

  box.innerHTML =
    arr
      .map(
        x => `
          <div class="card data-card self-report-card">
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

            <div class="metric-grid">
              ${
                selfMetric(
                  "EPS",
                  x.eps ===
                    null
                    ? null
                    : fmtNum(
                        x.eps,
                        2
                      ),
                  " 元"
                )
              }

              ${
                selfMetric(
                  "稅前淨利",
                  x.pretax_million ===
                    null
                    ? null
                    : fmtNum(
                        x.pretax_million,
                        0
                      ),
                  " 百萬"
                )
              }

              ${
                selfMetric(
                  "稅後／歸母淨利",
                  x.net_income_million ===
                    null
                    ? null
                    : fmtNum(
                        x.net_income_million,
                        0
                      ),
                  " 百萬"
                )
              }

              ${
                selfMetric(
                  "營業收入",
                  x.revenue_million ===
                    null
                    ? null
                    : fmtNum(
                        x.revenue_million,
                        0
                      ),
                  " 百萬"
                )
              }
            </div>

            <div class="subject">
              ${
                x.subject ||
                "自結財務資訊"
              }
            </div>
          </div>
        `
      )
      .join("");
}


/* =========================================================
   月營收
   ========================================================= */

function revenueCard(
  x
) {
  const isHigh =
    x.record_high ===
    true;

  const high =
    isHigh
      ? `
        <span class="new-high">
          <span class="new-high-icon">
            ★
          </span>

          營收新高
        </span>
      `
      : "";

  return `
    <div
      class="
        revenue-card
        ${
          isHigh
            ? "record-high"
            : ""
        }
      "
    >
      ${
        isHigh
          ? `
            <div class="record-high-glow"></div>
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

        ${high}
      </div>

      <div class="rev">
        ${
          fmtNum(
            x.revenue_100m,
            2
          )
        } 億
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


async function monthlyRevenue() {
  const d =
    await J(
      "./data/monthly_revenue.json"
    );

  if (
    $("#revenueMonthBadge")
  ) {
    $(
      "#revenueMonthBadge"
    ).textContent =
      d.month_label
        ? `目前顯示 ${d.month_label}`
        : "尚無資料";
  }

  if (
    $("#revenueStatus")
  ) {
    $(
      "#revenueStatus"
    ).textContent =
      d.updated_at
        ? `最後更新 ${d.updated_at} · 19個族群 · 營收新高會高亮並自動推播`
        : "尚未產生月營收資料";
  }

  const sectors =
    d.sectors ||
    [];

  const tabs =
    $("#revenueSectorTabs");

  if (
    tabs
  ) {
    tabs.innerHTML = `
      <button
        class="
          week-pill
          ${
            revenueSectorSelected ===
            "all"
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
                    revenueSectorSelected ===
                    s.name
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
    ).forEach(
      b => {
        b.onclick =
          () => {
            revenueSectorSelected =
              b.dataset
                .revSec;

            monthlyRevenue();
          };
      }
    );
  }

  const list =
    revenueSectorSelected ===
    "all"
      ? sectors
      : sectors.filter(
          s =>
            s.name ===
            revenueSectorSelected
        );

  const box =
    $(
      "#revenueSections"
    );

  if (
    !box
  ) {
    return;
  }

  if (
    !list.length
  ) {
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
          const highCount =
            (
              sec.stocks ||
              []
            )
              .filter(
                x =>
                  x.record_high ===
                  true
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
                    highCount
                      ? `
                        <span class="sector-high-count">
                          ${highCount} 檔新高
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
                  } 檔
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


/* =========================================================
   導覽排序
   ========================================================= */

function reorderNavigation() {
  const nav =
    document.querySelector(
      "header nav"
    );

  if (
    nav
  ) {
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

  if (
    select
  ) {
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


/* =========================================================
   自動更新目前頁面
   不需要重新整理 Safari
   ========================================================= */

async function refreshCurrentPageData() {
  if (
    autoRefreshRunning
  ) {
    return;
  }

  autoRefreshRunning =
    true;

  try {
    const activePage =
      document.querySelector(
        ".page.active"
      )?.id ||
      "home";

    switch (
      activePage
    ) {
      case "home":
        await Promise.all([
          home(),
          heat(),
          selfReports(),
          monthlyRevenue()
        ]);

        const oldPulse =
          document.getElementById(
            "marketPulse"
          );

        if (
          oldPulse
        ) {
          oldPulse.remove();
        }

        await buildMarketPulse();

        break;


      case "heat":
        await heat();
        break;


      case "selfReports":
        await selfReports();
        break;


      case "flows":
        await flows();
        break;


      case "volume":
        await volume();
        break;


      case "turnover":
        await turnover();
        break;


      case "marginLending":
        if (
          typeof marginLending ===
          "function"
        ) {
          await marginLending();
        }

        break;


      case "ai":
        await ai();
        break;


      case "reports":
        await reports();
        break;


      case "holders":
        await holders();
        break;


      case "monthlyRevenue":
        await monthlyRevenue();
        break;
    }

    console.log(
      "Auto refreshed:",
      activePage,
      new Date()
        .toLocaleTimeString(
          "zh-TW"
        )
    );

  } catch (
    e
  ) {
    console.error(
      "Auto refresh failed:",
      e
    );

  } finally {
    autoRefreshRunning =
      false;
  }
}


/* =========================================================
   自動更新排程

   每 60 秒：
   重新抓目前所在頁面的最新 JSON

   iPhone Safari 切回前景：
   立刻重新抓

   Safari bfcache 恢復：
   立刻重新抓
   ========================================================= */

setInterval(
  () => {
    refreshCurrentPageData();
  },
  60 * 1000
);


document.addEventListener(
  "visibilitychange",
  () => {
    if (
      document.visibilityState ===
      "visible"
    ) {
      refreshCurrentPageData();
    }
  }
);


window.addEventListener(
  "pageshow",
  event => {
    if (
      event.persisted
    ) {
      refreshCurrentPageData();
    }
  }
);


/* =========================================================
   啟動
   ========================================================= */

setupPageHistory();

reorderNavigation();

buildFeatureRail();

setupBackHomeButton();

buildMarketPulse();

selfReports();

monthlyRevenue();
