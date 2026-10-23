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
let financialHistory = null;

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
    <span class="earnings-period">公布 ${esc(fmtFull(x.publish_date))}</span></div>
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


async function fetchFinancialHistory() {
  if (financialHistory) return financialHistory;
  const response = await fetch("./data/quarterly_earnings_history.json", {cache:"no-store"});
  if (!response.ok) throw new Error("歷史財報 HTTP " + response.status);
  const json = await response.json();
  financialHistory = Array.isArray(json.rows) ? json.rows : [];
  return financialHistory;
}
function quarterRank(p) {
  const m = String(p||"").match(/^(\d{4})[-/]?Q([1-4])$/i);
  return m ? +m[1]*4 + +m[2] : -1;
}
function currentReportingPeriod() {
  const parts = new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Taipei',year:'numeric',month:'numeric'}).formatToParts(new Date());
  const year = Number(parts.find(x=>x.type==='year').value);
  const month = Number(parts.find(x=>x.type==='month').value);
  return month<=3 ? `${year-1}-Q4` : `${year}-Q${Math.floor((month-1)/3)}`;
}
const knownStockNames = {'2330':'台積電','2317':'鴻海','2454':'聯發科','2308':'台達電','2383':'台光電','6213':'聯茂'};
let stockNamePromise = null;
async function ensureStockNames() {
  if (!stockNamePromise) stockNamePromise = fetch('./data/self_reports_history.json',{cache:'no-store'})
    .then(r=>r.ok?r.json():{items:[]}).then(d=>{for(const x of (d.items||[])) if(x.ticker&&x.name&&!/^\d+$/.test(x.name))knownStockNames[String(x.ticker)]=x.name;})
    .catch(e=>console.warn('公司名稱對照資料讀取失敗',e));
  await stockNamePromise;
}
function displayStockName(x){
  const id=String(x.ticker||'');
  const name=String(x.name||'').trim();
  return name && name!==id && !/^\d+$/.test(name) ? name : (knownStockNames[id]||id);
}
function searchLatestReports(reports, history, term) {
  const period=currentReportingPeriod();
  const query=String(term||'').trim().toLowerCase().replace(/\s+/g,'');
  const matching=(reports||[]).filter(x=>{
    if(String(x.period||'').replace(/\s/g,'').toUpperCase()!==period)return false;
    // 只顯示真正公告的季度財報，歷史累計數字不算。
    if(x.history_financial_only || x.release_type==='quarterly_preliminary')return false;
    if(filter==='date' && pickedDate && dateOnly(reportDate(x))!==pickedDate)return false;
    const name=displayStockName(x);
    return !query || `${x.ticker||''} ${name} ${x.name||''}`.toLowerCase().replace(/\s+/g,'').includes(query);
  });
  const unique=new Map();
  for(const x of matching){const id=String(x.ticker||'');const old=unique.get(id);if(!old||reportDate(x)>reportDate(old))unique.set(id,{...x,name:displayStockName(x)});}
  return [...unique.values()].sort((a,b)=>reportDate(b).localeCompare(reportDate(a)));
}
function searchReportHTML(x) {
  if (!x.history_financial_only) return reportItem(x);
  return `<article class="earnings-report-row"><div class="earnings-result-head"><div class="earnings-company"><b>${esc(x.name)}</b><span>${esc(x.ticker)}</span></div><span class="earnings-period">${esc(x.period)}</span></div>
  <p class="earnings-note">歷史官方累計財務數字（非單季 EPS），資料庫未記錄公告日期。</p>
  <div class="earnings-detail"><div><small>${esc(x.period)} 累計 EPS</small><b>${n2(x.cum_eps)} 元</b></div><div><small>${esc(x.period)} 累計毛利率</small><b>${pct(x.gross_margin)}</b></div></div></article>`;
}
function reportHTML(arr) {
  const filtered = searchLatestReports(arr, [], earningsQuery);

  if (!filtered.length) {

    return `<div class="earnings-empty">${esc(currentReportingPeriod())} 暫無資料</div>`;

  }

  const shown =
    filtered.slice(
      0,
      reportLimit
    );

  return (
    shown
      .map(searchReportHTML)
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

    if (mode === "reports") {
      await ensureStockNames();
      if (token !== renderToken || mode !== "reports") return;
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

        : searchLatestReports(arr,[],earningsQuery).length;

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

    if(mode === 'reports') {
      window.__twReportAnnouncementDates = [...new Set((arr||[]).filter(x=>String(x.period||'').toUpperCase()===currentReportingPeriod()&&!x.history_financial_only&&x.release_type!=='quarterly_preliminary').map(x=>dateOnly(reportDate(x))).filter(x=>/^\d{4}-\d{2}-\d{2}$/.test(x)))];
      document.dispatchEvent(new Event('tw-report-dates-updated'));
    }
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
    const selfDate = $("#selfReportDateFilter");
    if (selfDate) selfDate.hidden = false;
    return;
  }

  showSelf(false);
  const searchBox = $("#earningsCompanySearchWrap");
  const quick = $("#earningsFilters .earnings-quick");
  if(quick) quick.hidden=(mode==='reports');
  const dateRow = $("#earningsFilters .earnings-date-picker") || $("#earningsCompanySearchWrap .earnings-date-picker");
  if(dateRow && searchBox){
    if(mode==='reports' && dateRow.parentElement!==searchBox)searchBox.insertBefore(dateRow,searchBox.firstChild);
    if(mode==='upcoming' && dateRow.parentElement===searchBox)$("#earningsFilters").appendChild(dateRow);
  }
  if (searchBox) searchBox.hidden = next !== "reports";
  // 自結頁面以外，原始自結內容一律不可顯示。
  const selfDate = $("#selfReportDateFilter");
  if (selfDate) selfDate.hidden = true;
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

          <div id="earningsCompanySearchWrap" class="earnings-company-search" hidden>
            <input id="earningsCompanySearch" type="search" placeholder="搜尋公司名稱或股票代號" autocomplete="off" aria-label="搜尋最新財報">
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
                選擇日期
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


  const reportSearch = $("#earningsCompanySearch");
  if (reportSearch && !$("#earningsCompanySearchClear")) {
    reportSearch.insertAdjacentHTML('afterend','<button type="button" id="earningsCompanySearchClear" class="tw-search-clear" hidden>清除</button>');
    $("#earningsCompanySearchClear").onclick=()=>{reportSearch.value='';earningsQuery='';$("#earningsCompanySearchClear").hidden=true;reportLimit=PAGE_SIZE;render(false);reportSearch.focus();};
  }
  if (reportSearch) reportSearch.oninput = () => {
    const clear=$("#earningsCompanySearchClear");if(clear)clear.hidden=!reportSearch.value;

    earningsQuery = reportSearch.value;
    reportLimit = PAGE_SIZE;
    render(false);
  };
  /*
   * 再強制校正一次位置
   */
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




/* 僅擴充原有自結搜尋與公告日期；不新增搜尋區塊或改動卡片容器。 */
(() => {
 "use strict";
 const $ = q => document.querySelector(q);
 let historyPromise = null, searchSerial=0;
 const escape = x => String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const val = n => n==null||!Number.isFinite(Number(n))?"—":Number(n).toFixed(2);
 const quarter = p => {const m=String(p||"").match(/^(\d{4})-(\d{2})$/);return m?m[1]+"-Q"+(Math.floor((+m[2]-1)/3)+1):"";};
 async function history() {
   if (!historyPromise) historyPromise=fetch("./data/self_reports_history.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json();}).then(d=>Array.isArray(d.items)?d.items:[]).catch(e=>{historyPromise=null;throw e;});
   return historyPromise;
 }
 function card(x) {
   // 與原本 self-report-card 相同 DOM 結構；保留既有比較腳本的選取器。
   const date=escape((x.publish_date||"")+" "+(x.publish_time||""));
   const monthly=escape(x.monthly_period||"月份未註明");
   const last=escape(x.quarter_period||x.prev_quarter_period||"上一季");
   const a=x.monthly_eps??x.eps, b=x.quarter_eps;
   return `<div class="card data-card self-report-card" data-quarter-search="1"><div class="card-accent"></div>
     <div class="eyebrow">${date}</div><div class="titleline"><b>${escape(x.name||x.ticker)}</b><span>${escape(x.ticker)}</span></div>
     <div class="metric-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));gap:12px">
     ${typeof selfEpsMetric === "function" ? selfEpsMetric(x,"monthly","當月 EPS") : `<div class="metric"><small>當月 EPS（${monthly}）</small><b>${val(a)} 元</b></div>`}
     ${typeof selfEpsMetric === "function" ? selfEpsMetric(x,"quarter","上一季 EPS") : `<div class="metric"><small>上一季 EPS（${last}）</small><b>${val(b)} 元</b></div>`}</div></div>`;
 }
 async function searchQuarter() {
   const input=$("#selfReportSearchInput"), box=$("#selfReportCards"), meta=$("#selfReportSearchMeta");
   if (!input||!box) return;
   const q=input.value.trim().toLowerCase(), token=++searchSerial;
   if (!q) return; // 沒搜尋時交還原本自結程式。
   try {
     const rows=await history();
     if (token!==searchSerial || input.value.trim().toLowerCase()!==q) return;
     const matching=rows.filter(x=>`${x.ticker||""} ${x.name||""}`.toLowerCase().includes(q)&&quarter(x.monthly_period));
     const groups=new Map();
     for(const x of matching){const key=String(x.ticker||x.name);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(x);}
     const out=[];
     for(const list of groups.values()){
       list.sort((a,b)=>String(b.monthly_period||"").localeCompare(String(a.monthly_period||""))||String(b.publish_date||"").localeCompare(String(a.publish_date||"")));
       const latest=quarter(list[0].monthly_period);
       const used=new Set();
       for(const x of list){if(quarter(x.monthly_period)!==latest||used.has(x.monthly_period))continue;used.add(x.monthly_period);out.push(x);}
     }
     out.sort((a,b)=>String(b.monthly_period).localeCompare(String(a.monthly_period))||String(b.publish_date).localeCompare(String(a.publish_date)));
     box.dataset.quarterWritten="1";
     box.innerHTML=out.length?out.map(card).join(""):'<div class="card empty self-empty">該公司目前沒有可查詢的當季月份自結</div>';
     if(meta)meta.textContent=`當季找到 ${out.length} 個月份的自結公告`;
   }catch(e){console.warn("自結季度搜尋失敗",e);if(meta)meta.textContent="歷史自結資料讀取失敗";}
 }
 function calendar() {
   const wrap=$("#selfReportDateFilter"),select=$("#selfReportDateSelect");
   if(wrap){const label=wrap.querySelector('label[for="selfReportDateSelect"]');if(label&&label.textContent.trim()!=='選擇日期')label.textContent='選擇日期';}
   if(!wrap||!select)return;
   // 原本 ui_v2.js 會更新日期下拉；只替換日期控制本身，不移動搜尋框。
   if(!wrap.querySelector("#selfReportCalendarWidget")){
     const widget=document.createElement("div");widget.id="selfReportCalendarWidget";widget.className="self-cal";
     widget.innerHTML=`<button type="button" class="self-cal-trigger" aria-label="開啟自結公告日期月曆" aria-expanded="false"><span class="self-cal-trigger-date"></span><svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/></svg></button><div class="self-cal-pop" hidden><div class="self-cal-head"><button type="button" class="self-cal-prev" aria-label="上個月">‹</button><button type="button" class="self-cal-month" aria-label="選擇年月"></button><button type="button" class="self-cal-next" aria-label="下個月">›</button></div><div class="self-cal-grid self-cal-week"></div><div class="self-cal-grid self-cal-days"></div><div class="self-cal-foot"><button type="button" class="self-cal-today">今天</button><button type="button" class="self-cal-reset">清除</button><button type="button" class="self-cal-close">完成</button></div></div>`;
     select.insertAdjacentElement("afterend",widget);
     const trigger=widget.querySelector(".self-cal-trigger"),pop=widget.querySelector(".self-cal-pop");
     let cursor=(select.value||new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Taipei'})).slice(0,7);
     const dayKeys=['日','一','二','三','四','五','六'];
     widget.querySelector('.self-cal-week').innerHTML=dayKeys.map(x=>`<span>${x}</span>`).join('');
     function paint(){
       const selected=select.value||'';widget.querySelector('.self-cal-trigger-date').textContent=$('#selfReportSearchInput')?.value.trim()?'不限日期':(selected||'不限日期');
       const [y,m]=cursor.split('-').map(Number);widget.querySelector('.self-cal-month').textContent=`${y} 年 ${m} 月`;
       const first=new Date(y,m-1,1).getDay(),days=new Date(y,m,0).getDate();
       const available=new Set([...select.options].map(o=>o.value));
       const today=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Taipei'});
       let html='';for(let i=0;i<first;i++)html+='<span class="self-cal-blank"></span>';
       for(let d=1;d<=days;d++){
         const iso=`${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
         const classes=['self-cal-day',iso===selected?'is-selected':'',iso===today?'is-today':''].filter(Boolean).join(' ');
         html+=`<button type="button" class="${classes}" data-date="${iso}" aria-label="${iso}" aria-pressed="${iso===selected}">${d}${available.has(iso)?'<i aria-label="有公告"></i>':''}</button>`;
       }
       widget.querySelector('.self-cal-days').innerHTML=html;
     }
     function close(){pop.hidden=true;trigger.setAttribute('aria-expanded','false');}
     function choose(value){
       let opt=[...select.options].find(o=>o.value===value);
       if(!opt){opt=document.createElement('option');opt.value=value;opt.textContent=value;select.add(opt);}
       select.value=value;window.__twSelfChosenDate=value;select.dispatchEvent(new CustomEvent('tw-self-date',{bubbles:true,detail:{date:value}}));paint();close();
     }
     trigger.onclick=()=>{pop.hidden=!pop.hidden;trigger.setAttribute('aria-expanded',String(!pop.hidden));if(!pop.hidden){cursor=(select.value||cursor).slice(0,7);paint();}};
     widget.querySelector('.self-cal-prev').onclick=()=>{const [y,m]=cursor.split('-').map(Number),dt=new Date(y,m-2,1);cursor=`${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}`;paint();};
     widget.querySelector('.self-cal-next').onclick=()=>{const [y,m]=cursor.split('-').map(Number),dt=new Date(y,m,1);cursor=`${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}`;paint();};
     widget.querySelector('.self-cal-month').onclick=()=>{
       const raw=widget.querySelector('.self-cal-month-pick');
       if(raw){raw.hidden=!raw.hidden;return;}
       const picker=document.createElement('div');picker.className='self-cal-month-pick';
       const [yy,mm]=cursor.split('-').map(Number);
       picker.innerHTML=`<select aria-label="年份">${Array.from({length:12},(_,i)=>yy-6+i).map(y=>`<option value="${y}" ${y===yy?'selected':''}>${y} 年</option>`).join('')}</select><select aria-label="月份">${Array.from({length:12},(_,i)=>i+1).map(m=>`<option value="${m}" ${m===mm?'selected':''}>${m} 月</option>`).join('')}</select>`;
       widget.querySelector('.self-cal-head').insertAdjacentElement('afterend',picker);
       picker.onchange=()=>{cursor=`${picker.children[0].value}-${String(picker.children[1].value).padStart(2,'0')}`;paint();};
     };
     widget.querySelector('.self-cal-days').onclick=e=>{const day=e.target.closest('[data-date]');if(day)choose(day.dataset.date);};
     widget.querySelector('.self-cal-today').onclick=()=>choose(new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Taipei'}));
     widget.querySelector('.self-cal-reset').onclick=()=>choose('');
     widget.querySelector('.self-cal-close').onclick=close;
     document.addEventListener('pointerdown',e=>{if(!widget.contains(e.target))close();});
     document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
     widget.sync=paint;paint();
   }
   if(window.__twSelfChosenDate!==undefined && select.value!==window.__twSelfChosenDate){if(window.__twSelfChosenDate){const v=window.__twSelfChosenDate;if(![...select.options].some(o=>o.value===v)){const opt=document.createElement('option');opt.value=v;opt.textContent=v;select.add(opt);}select.value=v;}else{select.value='';}}
   select.style.display='none';
   const widget=wrap.querySelector('#selfReportCalendarWidget');
   if(widget?.sync){
     const signature=select.value+'|'+[...select.options].map(o=>o.value).join(',');
     if(widget.dataset.syncSignature!==signature){widget.dataset.syncSignature=signature;widget.sync();}
   }
 }
 function init(){
   const input=$("#selfReportSearchInput"),clear=$("#selfReportSearchClear"),page=$("#selfReports");
   if(!page)return;
   if(input){let t;input.addEventListener("input",()=>{clearTimeout(t);t=setTimeout(searchQuarter,260);});}
   if(clear)clear.addEventListener("click",()=>{searchSerial++;setTimeout(()=>{const page=$("#selfReports");if(page)page.dispatchEvent(new CustomEvent('tw-self-date',{bubbles:true,detail:{date:window.__twSelfChosenDate??$("#selfReportDateSelect")?.value??''}}));},220);});
   // 日期選擇由自訂月曆單獨管理，避免舊版下拉選單重置日期。
   page.addEventListener('tw-self-date',e=>{
     const selected=e.detail.date;
     const box=$("#selfReportCards"),meta=$("#selfReportSearchMeta");
     if(!box || input?.value.trim())return;
     history().then(rows=>{
       if(input?.value.trim() || window.__twSelfChosenDate!==selected)return;
       const dated=rows.filter(x=>!selected||String(x.publish_date||'').slice(0,10)===selected);
       const unique=new Map();for(const x of dated){const key=`${x.ticker}-${x.monthly_period||x.publish_time}`;if(!unique.has(key))unique.set(key,x);}
       box.dataset.quarterWritten='1';
       box.innerHTML=unique.size?[...unique.values()].map(card).join(''):`<div class="card empty self-empty">${selected?selected+' 沒有自結公告':'目前沒有自結公告'}</div>`;
       if(meta)meta.textContent=`${selected||'不限日期'}｜共 ${unique.size} 筆自結`;
     }).catch(console.warn);
   });
   const observer=new MutationObserver(()=>{calendar();});
   observer.observe(page,{childList:true,subtree:true});
   const box=$("#selfReportCards");
   if(box) new MutationObserver(()=>{
     if(box.dataset.quarterWritten==="1") { delete box.dataset.quarterWritten; return; }
     if(input?.value.trim()) setTimeout(searchQuarter,180);
   }).observe(box,{childList:true});
   calendar();
 }
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});else init();
})();

/* 財報日期：替換 Safari 原生日期面板，不影響原本篩選事件。 */
(() => {
  'use strict';
  function initFinanceCalendar() {
    const input=document.getElementById('earningsDatePicker');
    if(!input||document.getElementById('earningsFinanceCalendar'))return;
    input.style.display='none';
    const wrap=document.createElement('div');wrap.id='earningsFinanceCalendar';wrap.className='self-cal';
    wrap.innerHTML='<button type="button" class="self-cal-trigger"><span>選擇日期</span><span aria-hidden="true">▦</span></button><div class="self-cal-pop" hidden><div class="self-cal-head"><button type="button" class="self-cal-prev" aria-label="上個月">‹</button><button type="button" class="self-cal-month"></button><button type="button" class="self-cal-next" aria-label="下個月">›</button></div><div class="self-cal-month-pick" hidden></div><div class="self-cal-grid self-cal-week">'+['日','一','二','三','四','五','六'].map(x=>`<span>${x}</span>`).join('')+'</div><div class="self-cal-grid self-cal-days"></div><div class="self-cal-foot"><button type="button" class="self-cal-reset">清除</button><button type="button" class="self-cal-close">完成</button></div></div>';
    input.insertAdjacentElement('afterend',wrap);
    const $=s=>wrap.querySelector(s),pop=$('.self-cal-pop'),trigger=$('.self-cal-trigger');
    let cursor=(input.value||new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Taipei'})).slice(0,7);
    function paint(){
      const [y,m]=cursor.split('-').map(Number),start=new Date(y,m-1,1).getDay(),total=new Date(y,m,0).getDate();
      $('.self-cal-month').textContent=`${y} 年 ${m} 月`;
      trigger.firstElementChild.textContent=input.value||'選擇日期';
      const today=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Taipei'});
      $('.self-cal-days').innerHTML='<span class="self-cal-blank"></span>'.repeat(start)+Array.from({length:total},(_,i)=>{
        const date=`${cursor}-${String(i+1).padStart(2,'0')}`;
        return `<button type="button" class="self-cal-day ${date===input.value?'is-selected':''} ${date===today?'is-today':''}" data-date="${date}">${i+1}${(window.__twReportAnnouncementDates||[]).includes(date)?'<i aria-hidden="true"></i>':''}</button>`;
      }).join('');
    }
    function close(){pop.hidden=true;trigger.setAttribute('aria-expanded','false');}
    trigger.onclick=()=>{pop.hidden=!pop.hidden;trigger.setAttribute('aria-expanded',String(!pop.hidden));paint();};
    $('.self-cal-prev').onclick=()=>{const [y,m]=cursor.split('-').map(Number),d=new Date(y,m-2,1);cursor=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;paint();};
    $('.self-cal-next').onclick=()=>{const [y,m]=cursor.split('-').map(Number),d=new Date(y,m,1);cursor=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;paint();};
    $('.self-cal-month').onclick=()=>{
      const pick=$('.self-cal-month-pick');pick.hidden=!pick.hidden;
      const [y,m]=cursor.split('-').map(Number);
      pick.innerHTML=`<select aria-label="年份">${Array.from({length:12},(_,i)=>y-6+i).map(v=>`<option value="${v}" ${v===y?'selected':''}>${v} 年</option>`).join('')}</select><select aria-label="月份">${Array.from({length:12},(_,i)=>i+1).map(v=>`<option value="${v}" ${v===m?'selected':''}>${v} 月</option>`).join('')}</select>`;
      pick.onchange=()=>{cursor=`${pick.children[0].value}-${String(pick.children[1].value).padStart(2,'0')}`;paint();};
    };
    $('.self-cal-days').onclick=e=>{const btn=e.target.closest('[data-date]');if(!btn)return;input.value=btn.dataset.date;input.dispatchEvent(new Event('change',{bubbles:true}));paint();close();};
    $('.self-cal-reset').onclick=()=>{input.value='';input.dispatchEvent(new Event('change',{bubbles:true}));paint();close();};
    $('.self-cal-close').onclick=close;
    document.addEventListener('pointerdown',e=>{if(!wrap.contains(e.target))close();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
    document.addEventListener('tw-report-dates-updated',paint);
    new MutationObserver(paint).observe(input,{attributes:true,attributeFilter:['value']});
    paint();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initFinanceCalendar,{once:true});else initFinanceCalendar();
})();

/* V7: 統一自結與財報搜尋／日期控制版型（不更動資料卡片）。 */
(() => {function align(){
 const self=document.querySelector('.self-report-search-card');if(self)self.classList.add('tw-filter-card');
 const search=document.getElementById('earningsCompanySearchWrap'),date=document.querySelector('#earningsFilters .earnings-date-picker');
 if(search)search.classList.add('tw-filter-card');
 const input=document.getElementById('selfReportSearchInput');if(input){const clear=document.getElementById('selfReportSearchClear');if(clear)clear.classList.add('tw-search-clear');}
 const quick=document.querySelector('#earningsFilters .earnings-quick');if(quick&&document.querySelector('[data-earnings-mode="reports"].active'))quick.hidden=true;
}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',align);else align();})();
