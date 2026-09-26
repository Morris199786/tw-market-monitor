const featureItems = [
  ["selfReports","自結公布","▣","red","即時監控"],
  ["heat","市場熱力圖","▦","red","19族群"],
  ["flows","籌碼日報","▤","blue","法人"],
  ["volume","突然放量","⚡","amber","科技股"],
  ["turnover","成交排行","↗","blue","TOP30"],
  ["marginLending","融資／借券","⇄","violet","科技股"],
  ["ai","AI選股","✦","green","每天18:00"],
  ["reports","券商報告","▧","amber","研究報告"],
  ["holders","大戶籌碼","◎","violet","週更"],
  ["monthlyRevenue","月營收公布","▥","green","19族群"]
];

let revenueSectorSelected = "all";

function buildFeatureRail() {
  const box = $("#featureRail");

  if (!box) {
    return;
  }

  box.innerHTML = featureItems
    .map(
      x => `
        <button
          class="feature-card"
          data-feature="${x[0]}"
          data-tone="${x[3]}"
        >
          <div class="feature-icon">
            ${x[2]}
          </div>

          <b>
            ${x[1]}
          </b>

          <small>
            ${x[4]}
          </small>
        </button>
      `
    )
    .join("");

  $$("[data-feature]").forEach(
    b => {
      b.onclick = () => {
        page(
          b.dataset.feature
        );
      };
    }
  );
}

function fmtNum(v, d = 2) {
  if (
    v === null ||
    v === undefined ||
    Number.isNaN(
      Number(v)
    )
  ) {
    return "—";
  }

  return Number(v)
    .toLocaleString(
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
  return `
    <div class="metric-box">
      <small>
        ${label}
      </small>

      <strong>
        ${
          value === null ||
          value === undefined ||
          value === ""
            ? "—"
            : value
        }
        ${
          value === null ||
          value === undefined ||
          value === ""
            ? ""
            : suffix
        }
      </strong>
    </div>
  `;
}

async function selfReports() {
  const d = await J(
    "./data/self_reports.json"
  );

  if ($("#selfWeekBadge")) {
    $("#selfWeekBadge")
      .textContent =
        "即時監控";
  }

  const tabs =
    $("#selfWeekTabs");

  if (tabs) {
    tabs.innerHTML = "";
    tabs.style.display = "none";
  }

  const status =
    $("#selfStatus");

  if (status) {
    const twse =
      d.source_status?.twse;

    const tpex =
      d.source_status?.tpex;

    const sourceText = [
      twse?.ok
        ? "上市正常"
        : "上市來源異常",
      tpex?.ok
        ? "上櫃正常"
        : "上櫃來源異常"
    ].join(" · ");

    status.textContent =
      d.updated_at
        ? `最後更新 ${d.updated_at} · ${sourceText} · 新公告自動推播`
        : "尚未開始自結監控";
  }

  const arr =
    d.items || [];

  const box =
    $("#selfReportCards");

  if (!box) {
    return;
  }

  if (!arr.length) {
    box.innerHTML = `
      <div class="card empty">
        目前尚未偵測到新的自結公告
      </div>
    `;

    return;
  }

  box.innerHTML =
    arr
      .map(
        x => `
          <div class="card data-card">
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

              ${selfMetric(
                "EPS",
                x.eps === null
                  ? null
                  : fmtNum(
                      x.eps,
                      2
                    ),
                " 元"
              )}

              ${selfMetric(
                "稅前淨利",
                x.pretax_million ===
                null
                  ? null
                  : fmtNum(
                      x.pretax_million,
                      0
                    ),
                " 百萬"
              )}

              ${selfMetric(
                "稅後／歸母淨利",
                x.net_income_million ===
                null
                  ? null
                  : fmtNum(
                      x.net_income_million,
                      0
                    ),
                " 百萬"
              )}

              ${selfMetric(
                "營業收入",
                x.revenue_million ===
                null
                  ? null
                  : fmtNum(
                      x.revenue_million,
                      0
                    ),
                " 百萬"
              )}

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

function revenueCard(x) {
  const high =
    x.record_high === true
      ? `
        <span class="new-high">
          ★ 營收新高
        </span>
      `
      : "";

  return `
    <div class="revenue-card">

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
        ${fmtNum(
          x.revenue_100m,
          2
        )} 億
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
            class="${cl(
              x.mom
            )}"
          >
            ${pct(
              x.mom
            )}
          </b>
        </span>

        <span>
          <small>
            YoY
          </small>

          <b
            class="${cl(
              x.yoy
            )}"
          >
            ${pct(
              x.yoy
            )}
          </b>
        </span>

      </div>

    </div>
  `;
}

async function monthlyRevenue() {
  const d = await J(
    "./data/monthly_revenue.json"
  );

  if (
    $("#revenueMonthBadge")
  ) {
    $("#revenueMonthBadge")
      .textContent =
        d.month_label
          ? `目前顯示 ${d.month_label}`
          : "尚無資料";
  }

  if (
    $("#revenueStatus")
  ) {
    $("#revenueStatus")
      .textContent =
        d.updated_at
          ? `最後更新 ${d.updated_at} · 19個族群 · 新高自動推播`
          : "尚未產生月營收資料";
  }

  const sectors =
    d.sectors || [];

  const tabs =
    $("#revenueSectorTabs");

  if (tabs) {
    tabs.innerHTML = `
      <button
        class="week-pill ${
          revenueSectorSelected ===
          "all"
            ? "active"
            : ""
        }"
        data-rev-sec="all"
      >
        全部族群
      </button>

      ${sectors
        .map(
          s => `
            <button
              class="week-pill ${
                revenueSectorSelected ===
                s.name
                  ? "active"
                  : ""
              }"
              data-rev-sec="${s.name}"
            >
              ${s.name}
            </button>
          `
        )
        .join("")}
    `;

    $$(
      "[data-rev-sec]"
    ).forEach(
      b => {
        b.onclick = () => {
          revenueSectorSelected =
            b.dataset.revSec;

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
        sec => `
          <section class="sector-revenue">

            <div class="sector-revenue-head">

              <h2>
                ${sec.name}
              </h2>

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

              ${(
                sec.stocks ||
                []
              )
                .map(
                  revenueCard
                )
                .join("")}

            </div>

          </section>
        `
      )
      .join("");
}

buildFeatureRail();
selfReports();
monthlyRevenue();
