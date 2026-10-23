(() => {
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const PAGE_SIZE = 30;

let mode = "self";
let cache = null;
let loadedAt = 0;
let loadingPromise = null;
let filter = "all";
let pickedDate = "";
let reportLimit = PAGE_SIZE;
let renderToken = 0;
let earningsQuery = "";
let earningsDate = "";
let selfHistory = null;
let selfHistoryLoading = null;
let selfHistoryQuery = "";
let selfHistoryDate = "";
let selfHistoryLimit = 60;

const esc = v =>
  String(v ?? "").replace(
    /[&<>"']/g,
    c => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[c]
  );

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

function weekRange(off = 0) {
  const d = new Date();
  const day = (d.getDay() + 6) % 7;

  const a = new Date(d);
  a.setDate(d.getDate() - day + off * 7);

  const b = new Date(a);
  b.setDate(a.getDate() + 6);

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
  if (filter === "all") return true;
  if (!d) return false;

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

  const [a, b] =
    weekRange(
      filter === "nextweek"
        ? 1
        : 0
    );

  return d >= a && d <= b;
}


/* =========================================================
   自結區

   這版不再建立 selfLegacyArea
   不搬 DOM
   只控制既有自結元件顯示 / 隱藏
   ========================================================= */

function getSelfNodes() {
  const page =
    $("#selfReports");

  if (!page) return [];

  return [
    $("#selfWeekBadge"),
    $("#selfWeekTabs"),
    $(".self-report-search-card", page),
    $("#selfStatus"),
    $("#selfReportCards")
  ].filter(Boolean);
}


function showSelf(show) {
  getSelfNodes().forEach(el => {

    el.hidden = !show;

    if (show) {
      el.style.removeProperty(
        "display"
      );
    } else {
      el.style.setProperty(
        "display",
        "none",
        "important"
      );
    }

  });
}


function removeOldWrapper() {
  const wrap =
    $("#selfLegacyArea");

  if (!wrap) return;

  const parent =
    wrap.parentNode;

  if (!parent) return;

  while (
    wrap.firstChild
  ) {
    parent.insertBefore(
      wrap.firstChild,
      wrap
    );
  }

  wrap.remove();
}


function removePushoverText() {
  const page =
    $("#selfReports");

  if (!page) return;

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
      (n.nodeValue || "")
        .replace(
          /\s*[·｜]?\s*Pushover\s*已啟用/gi,
          ""
        );

  });
}


/* =========================================================
   財報資料
   只有真正點擊財報頁籤才抓
   ========================================================= */

async function load(force = false) {
  if (
    cache && Date.now() - loadedAt < 60000 &&
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
      `./data/quarterly_earnings.json?v=${Date.now()}`,
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

      cache = d; loadedAt = Date.now();

      return d;

    })
    .finally(() => {

      loadingPromise = null;

    });

  return loadingPromise;
}


/* =========================================================
   即將開財報
   ========================================================= */

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
    Object.keys(groups)
      .sort((a, b) => {

        if (a === "未定")
          return 1;

        if (b === "未定")
          return -1;

        return a.localeCompare(b);

      });

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

        `).join("")}

      </div>

    </section>

  `).join("");
}


/* =========================================================
   財報
   ========================================================= */

function reportItem(x) {
  const estimated = [x.eps_basis, x.prev_eps_basis].includes("cumulative_difference");
  const news = x.eps_basis === "news_reported_single";
  const newsSource = x.eps_news_source || x;
  return `<article class="earnings-report-row">
    <div class="earnings-result-head"><div class="earnings-company"><b>${esc(x.name || x.ticker)}</b><span>${esc(x.ticker)}</span></div>
    <span class="earnings-period">${esc(x.period || "季度未明")} 財報｜公布 ${esc(fmtFull(x.publish_date))}</span></div>
    ${news ? '<p class="earnings-note">新聞備援 EPS｜待官方資料核對</p>' : ''}
    <div class="earnings-detail four">
      <div><small>本季 EPS · ${esc(x.period)}</small><b>${n2(x.eps)} 元</b></div>
      <div><small>本季毛利率 · ${esc(x.period)}</small><b>${pct(x.gross_margin)}</b></div>
      <div><small>上一季 EPS · ${esc(x.prev_period)}</small><b>${n2(x.prev_eps)} 元</b></div>
      <div><small>上一季毛利率 · ${esc(x.prev_period)}</small><b>${pct(x.prev_gross_margin)}</b></div>
    </div>
    ${x.data_status === "pending_financial_data" ? '<p class="earnings-note">已公布財報，部分數值待官方資料補齊；「—」不代表 0</p>' : ''}
    ${x.release_type === "quarterly_preliminary" ? '<p class="earnings-note">季度初步業績（自結／未核閱），非正式核閱財報</p>' : ''}
    ${estimated ? '<p class="earnings-note">EPS 含累計差額推算值，若股本或加權平均股數改變，可能與公告單季 EPS 不同</p>' : ''}
    <details class="earnings-source"><summary>公告內容與資料來源</summary><p>${esc(x.subject)}</p>
    ${news && /^https:\/\/news\.google\.com\//.test(newsSource.source_url || '') ? `<a href="${esc(newsSource.source_url)}" target="_blank" rel="noopener">${esc(newsSource.source_label || "新聞備援來源")} ↗</a>` : ''}
    ${/^https:\/\/(?:(?:mops|mopsov)\.twse\.com\.tw|www\.largan\.com\.tw)\//.test(x.source_url || '') ? `<a href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.source_label || "官方資料來源")} ↗</a>` : ''}</details>
  </article>`;
}


function reportHTML(arr) {
  const query = earningsQuery.trim().toLocaleLowerCase();
  const matched = arr.filter(x =>
    !query || `${x.ticker || ""} ${x.name || ""}`.toLocaleLowerCase().includes(query)
  );
  // 只顯示各公司最新「已公布」季度；相同季度保留較新公告。
  const byCompany = new Map();
  matched.forEach(x => {
    if (!x.period || !/^\d{4}[-/]?Q[1-4]$/i.test(String(x.period))) return;
    const key = String(x.ticker || x.name);
    const old = byCompany.get(key);
    if (!old || String(x.period) > String(old.period) ||
       (String(x.period) === String(old.period) && reportDate(x) > reportDate(old))) byCompany.set(key, x);
  });
  const filtered = [...byCompany.values()].filter(x => !earningsDate || reportDate(x) === earningsDate)
    .sort((a,b) => reportDate(b).localeCompare(reportDate(a)));

  if (!filtered.length) {

    return `
      <div class="earnings-empty">
        ${
          filter === "all"
            ? "目前尚未取得可顯示的季度財報公告"
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
      .join("")
    +
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


/* =========================================================
   Render
   ========================================================= */

async function render(force = false) {
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

    const d =
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
            d.upcoming ||
            []
          )

        : (
            d.reports ||
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
        ? upcomingHTML(arr)
        : reportHTML(arr);

    const errors = [...(d.diagnostics?.source_errors || []), ...(d.diagnostics?.historical_errors || [])];
    const stale = !d.updated_at || Date.now() - Date.parse(d.updated_at) > 36 * 3600000;
    if (errors.length || stale) {
      const warning = document.createElement("p");
      warning.className = "earnings-note";
      warning.textContent = errors.length ? "部分官方來源尚未取得，以下為已確認資料，不能據此判定沒有其他公告" : "資料超過 36 小時未更新，請以最新官方公告為準";
      cards.prepend(warning);
    }
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
        quarterly_earnings.json 讀取失敗
      </div>
    `;

    console.error(e);

  }
}


function bindLoadMore(arr) {
  const more =
    $("#earningsLoadMore");

  if (!more) return;

  more.onclick = () => {

    reportLimit +=
      PAGE_SIZE;

    const cards =
      $("#quarterlyEarningsCards");

    if (!cards) return;

    cards.innerHTML =
      reportHTML(arr);

    bindLoadMore(arr);
  };
}


/* =========================================================
   Mode
   ========================================================= */

function switchMode(next) {
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
    const sh = $("#selfHistorySearch");
    if (sh) sh.hidden = false;
    renderSelfHistory();
    return;
  }

  showSelf(false);
  const sh = $("#selfHistorySearch");
  const sr = $("#selfHistoryResults");
  if (sh) sh.hidden = true;
  if (sr) sr.hidden = true;
  const quick = $("#earningsFilters");
  const search = $("#earningsReportSearch");
  if (quick) quick.hidden = next === "reports";
  if (search) search.hidden = next !== "reports";

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


/* =========================================================
   強制固定三顆按鈕在 HERO 正下方
   ========================================================= */

function forceTabsBelowHero() {
  const page =
    $("#selfReports");

  if (!page) return;

  const hero =
    page.querySelector(
      ".hero"
    );

  const tabs =
    $("#earningsModeTabs");

  const panel =
    $("#quarterlyEarningsPanel");

  if (
    !hero ||
    !tabs
  ) {
    return;
  }

  /*
   * 不管其他 JS 怎麼改 DOM
   * 都重新把 tabs 移到 hero 正後方
   */
  if (
    hero.nextElementSibling !==
    tabs
  ) {

    hero.insertAdjacentElement(
      "afterend",
      tabs
    );

  }

  /*
   * panel 必須緊接在 tabs 後面
   */
  if (
    panel &&
    tabs.nextElementSibling !==
    panel
  ) {

    tabs.insertAdjacentElement(
      "afterend",
      panel
    );

  }
}


/* =========================================================
   Setup
   ========================================================= */

function setup() {
  const page =
    $("#selfReports");

  if (!page) return;

  /*
   * 清掉舊版 wrapper
   */
  removeOldWrapper();


  $$(
    '[data-p="selfReports"]'
  ).forEach(x => {

    x.textContent =
      "財報追蹤";

  });


  const opt =
    $(
      '#mobileNav option[value="selfReports"]'
    );

  if (opt) {
    opt.textContent =
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

  const p =
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

  if (p) {
    p.textContent =
      "自結公布｜即將開財報｜季度財報";
  }


  /*
   * 建立 tabs
   */
  if (
    !$("#earningsModeTabs")
  ) {

    const hero =
      page.querySelector(
        ".hero"
      );

    if (hero) {

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

          <div id="earningsReportSearch" class="earnings-search-bar">
            <input id="earningsCompanySearch" type="search" placeholder="搜尋公司名稱或股票代號（不限日期）" autocomplete="off" aria-label="搜尋財報公司">
            <label>公告日期 <input id="earningsPublishDate" type="date" aria-label="依財報公告日期篩選"></label>
            <button id="earningsSearchClear" type="button">清除</button>
          </div>
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
  }


  /*
   * 再強制校正一次位置
   */
  const q = $("#earningsCompanySearch");
  const dt = $("#earningsPublishDate");
  const clr = $("#earningsSearchClear");
  if (q) q.oninput = () => { earningsQuery = q.value; reportLimit = PAGE_SIZE; render(); };
  if (dt) dt.onchange = () => { earningsDate = dt.value; reportLimit = PAGE_SIZE; render(); };
  if (clr) clr.onclick = () => {
    earningsQuery = earningsDate = "";
    if (q) q.value = "";
    if (dt) dt.value = "";
    reportLimit = PAGE_SIZE;
    render();
  };
  installSelfHistorySearch();

  forceTabsBelowHero();


  $$(
    "[data-earnings-mode]"
  ).forEach(b => {

    b.onclick = () => {

      forceTabsBelowHero();

      switchMode(
        b.dataset.earningsMode
      );

    };

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


/* =========================================================
   防止其他 JS 再把 tabs 推到底部

   監聽 selfReports DOM
   如果位置被改掉就搬回 HERO 下方
   ========================================================= */

function setupPositionGuard() {
  const page =
    $("#selfReports");

  if (!page) return;

  let scheduled = false;

  const observer =
    new MutationObserver(() => {

      if (scheduled) {
        return;
      }

      scheduled = true;

      requestAnimationFrame(() => {

        scheduled = false;

        forceTabsBelowHero();

        if (
          mode !== "self"
        ) {
          showSelf(false);
        }

      });

    });

  observer.observe(
    page,
    {
      childList: true
    }
  );
}


/* =========================================================
   Boot
   ========================================================= */


/* 自結：不受週次限制的完整歷史搜尋，日期使用原生可切換年月月曆。 */
function selfItems(data) {
  if (Array.isArray(data)) return data;
  for (const key of ["items", "reports", "history", "records", "data", "self_reports"]) {
    if (Array.isArray(data?.[key])) return data[key];
  }
  return [];
}
async function loadSelfHistory() {
  if (selfHistory) return selfHistory;
  if (selfHistoryLoading) return selfHistoryLoading;
  selfHistoryLoading = fetch(`./data/self_reports_history.json?v=${Date.now()}`, {cache:"no-store"})
    .then(r => {if(!r.ok) throw Error(`HTTP ${r.status}`);return r.json();})
    .then(d => { selfHistory = selfItems(d); return selfHistory; })
    .finally(() => {selfHistoryLoading = null;});
  return selfHistoryLoading;
}
async function renderSelfHistory() {
  const box = $("#selfHistoryResults");
  if (!box) return;
  const query = selfHistoryQuery.trim().toLocaleLowerCase();
  const active = Boolean(query || selfHistoryDate);
  const legacy = $("#selfReportCards");
  const week = $("#selfWeekTabs");
  const status = $("#selfStatus");
  const oldSearch = $(".self-report-search-card", $("#selfReports"));
  for (const el of [legacy,week,status,oldSearch]) {
    if (el) el.style.display = active ? "none" : "";
  }
  box.hidden = !active || mode !== "self";
  if (!active || mode !== "self") return;
  box.innerHTML = '<div class="earnings-empty">搜尋歷史自結公告中…</div>';
  try {
    const rows = await loadSelfHistory();
    const matches = rows.filter(x => {
      const d = dateOnly(x.publish_date || x.date);
      return (!selfHistoryDate || d === selfHistoryDate) &&
        (!query || `${x.ticker || ""} ${x.name || ""}`.toLocaleLowerCase().includes(query));
    }).sort((a,b) => `${b.publish_date||b.date||""} ${b.publish_time||""}`.localeCompare(`${a.publish_date||a.date||""} ${a.publish_time||""}`));
    const displayed = matches.slice(0,selfHistoryLimit);
    box.innerHTML = `<div class="earnings-history-count">符合 ${matches.length} 筆歷史公告（含無法解析 EPS 的公告）</div>` +
      (matches.length ? displayed.map(x => `<article class="earnings-report-row">
        <div class="earnings-result-head"><div class="earnings-company"><b>${esc(x.name || x.ticker)}</b><span>${esc(x.ticker)}</span></div><span class="earnings-period">${esc(fmtFull(x.publish_date || x.date))} ${esc(x.publish_time || "")}</span></div>
        <div class="earnings-detail"><div><small>單月 EPS</small><b>${n2(x.monthly_eps)} 元</b></div><div><small>單季 EPS</small><b>${n2(x.quarter_eps)} 元</b></div></div>
        ${x.subject ? `<details class="earnings-source"><summary>公告內容</summary><p>${esc(x.subject)}</p></details>` : ""}
      </article>`).join("") : '<div class="earnings-empty">沒有符合的歷史自結公告</div>') +
      (matches.length > displayed.length ? `<button class="earnings-load-more" id="selfHistoryMore">載入更多（${displayed.length}/${matches.length}）</button>` : "");
    const more = $("#selfHistoryMore");
    if (more) more.onclick = () => {selfHistoryLimit += 60;renderSelfHistory();};
  } catch(e) {
    box.innerHTML = '<div class="earnings-empty">歷史自結資料讀取失敗</div>';
    console.error(e);
  }
}
function installSelfHistorySearch() {
  const page = $("#selfReports");
  if (!page || $("#selfHistorySearch")) return;
  const anchor = $("#selfWeekTabs");
  if (!anchor) return;
  anchor.insertAdjacentHTML("beforebegin", `<div id="selfHistorySearch" class="earnings-search-bar">
    <input id="selfHistoryQuery" type="search" placeholder="搜尋歷史自結：公司名稱／代號（不限日期）" aria-label="搜尋歷史自結">
    <label>公告日期 <input id="selfHistoryDate" type="date" aria-label="依自結公告日期篩選"></label>
    <button id="selfHistoryClear" type="button">清除</button>
  </div><div id="selfHistoryResults" class="earnings-list" hidden></div>`);
  $("#selfHistoryQuery").oninput = e => {selfHistoryQuery=e.target.value;selfHistoryLimit=60;renderSelfHistory();};
  $("#selfHistoryDate").onchange = e => {selfHistoryDate=e.target.value;selfHistoryLimit=60;renderSelfHistory();};
  $("#selfHistoryClear").onclick = () => {
    selfHistoryQuery=selfHistoryDate="";
    $("#selfHistoryQuery").value="";
    $("#selfHistoryDate").value="";
    renderSelfHistory();
  };
}
function boot() {
  setup();

  removePushoverText();

  forceTabsBelowHero();

  switchMode("self");

  setupPositionGuard();


  /*
   * ui_v2.js 可能延後建立自結內容
   * 再確認一次位置即可
   *
   * 不 fetch 財報 JSON
   */
  setTimeout(() => {

    removeOldWrapper();

    forceTabsBelowHero();

    removePushoverText();

    if (
      mode === "self"
    ) {
      showSelf(true);
    } else {
      showSelf(false);
    }

  }, 800);
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


/* =========================================================
   refresh_controller.js 使用
   ========================================================= */

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

})();



