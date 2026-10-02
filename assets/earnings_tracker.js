(() => {
  "use strict";
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  let mode = "self";
  let cache = null;

  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
  const val = v => v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(2);
  const pct = v => v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : `${Number(v).toFixed(2)}%`;

  function setup() {
    const page = $("#selfReports");
    if (!page) return;

    $$('[data-p="selfReports"]').forEach(x => x.textContent = "財報追蹤");
    const opt = $('#mobileNav option[value="selfReports"]');
    if (opt) opt.textContent = "財報追蹤";

    const kicker = page.querySelector(".kicker");
    const h1 = page.querySelector("h1");
    const p = page.querySelector(".hero p");
    if (kicker) kicker.textContent = "EARNINGS TRACKER";
    if (h1) h1.textContent = "財報追蹤";
    if (p) p.textContent = "自結公布｜即將開財報｜季度財報";

    if (!$("#earningsModeTabs")) {
      page.querySelector(".hero").insertAdjacentHTML("afterend", `
        <div id="earningsModeTabs" class="earnings-mode-tabs">
          <button type="button" class="earnings-mode active" data-earnings-mode="self">自結公布</button>
          <button type="button" class="earnings-mode" data-earnings-mode="upcoming">即將開財報</button>
          <button type="button" class="earnings-mode" data-earnings-mode="reports">財報</button>
        </div>
        <div id="quarterlyEarningsPanel" hidden>
          <div id="quarterlyEarningsStatus" class="status"></div>
          <div id="quarterlyEarningsCards" class="grid three"></div>
        </div>
      `);
    }

    $$("[data-earnings-mode]").forEach(b => b.onclick = () => switchMode(b.dataset.earningsMode));
  }

  function showSelf(show) {
    ["#selfWeekTabs",".self-report-search-card","#selfStatus","#selfReportCards"].forEach(s => {
      const el = $(s);
      if (el) el.hidden = !show;
    });
    const badge = $("#selfWeekBadge");
    if (badge) badge.hidden = !show;
  }

  async function data(force=false) {
    if (cache && !force) return cache;
    const r = await fetch(`./data/quarterly_earnings.json?v=${Date.now()}`, {cache:"no-store"});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    cache = await r.json();
    return cache;
  }

  function upcomingCard(x) {
    return `
      <article class="card earnings-card">
        <div class="earnings-card-head">
          <div><b>${esc(x.name || x.ticker)}</b><span>${esc(x.ticker)}</span></div>
          <strong>${esc(x.period || "")}</strong>
        </div>
        <div class="earnings-date"><span>預計財報日</span><b>${esc(x.planned_date || "—")}</b></div>
        <div class="earnings-numbers">
          <div><small>上一季 EPS</small><b>${val(x.prev_eps)}</b></div>
          <div><small>上一季毛利率</small><b>${pct(x.prev_gross_margin)}</b></div>
        </div>
      </article>`;
  }

  function reportCard(x) {
    const epsQoq = x.eps != null && x.prev_eps != null && Number(x.prev_eps) !== 0
      ? (Number(x.eps) / Number(x.prev_eps) - 1) * 100 : null;
    const gmDiff = x.gross_margin != null && x.prev_gross_margin != null
      ? Number(x.gross_margin) - Number(x.prev_gross_margin) : null;
    return `
      <article class="card earnings-card">
        <div class="earnings-card-head">
          <div><b>${esc(x.name || x.ticker)}</b><span>${esc(x.ticker)}</span></div>
          <strong>${esc(x.period || "")}</strong>
        </div>
        <div class="earnings-numbers four">
          <div><small>本季 EPS</small><b>${val(x.eps)}</b>${epsQoq==null?"":`<em>QoQ ${epsQoq>=0?"+":""}${epsQoq.toFixed(1)}%</em>`}</div>
          <div><small>本季毛利率</small><b>${pct(x.gross_margin)}</b>${gmDiff==null?"":`<em>QoQ ${gmDiff>=0?"+":""}${gmDiff.toFixed(2)} pct</em>`}</div>
          <div><small>上一季 EPS</small><b>${val(x.prev_eps)}</b></div>
          <div><small>上一季毛利率</small><b>${pct(x.prev_gross_margin)}</b></div>
        </div>
      </article>`;
  }

  async function switchMode(next, force=false) {
    mode = next;
    $$("[data-earnings-mode]").forEach(b => b.classList.toggle("active", b.dataset.earningsMode === next));
    const panel = $("#quarterlyEarningsPanel");

    if (next === "self") {
      showSelf(true);
      if (panel) panel.hidden = true;
      return;
    }

    showSelf(false);
    panel.hidden = false;
    const status = $("#quarterlyEarningsStatus");
    const cards = $("#quarterlyEarningsCards");
    status.textContent = "讀取中…";
    cards.innerHTML = "";

    try {
      const d = await data(force);
      const arr = next === "upcoming" ? (d.upcoming || []) : (d.reports || []);
      status.textContent = `${next === "upcoming" ? "即將開財報" : "財報"} ${arr.length} 檔｜最後更新 ${d.updated_at || "—"}`;
      cards.innerHTML = arr.length
        ? arr.map(next === "upcoming" ? upcomingCard : reportCard).join("")
        : `<div class="card empty">目前沒有資料</div>`;
    } catch (e) {
      status.textContent = "財報資料讀取失敗";
      cards.innerHTML = `<div class="card empty">請先執行 Self reports update 產生 quarterly_earnings.json</div>`;
      console.error(e);
    }
  }

  function boot() { setup(); switchMode("self"); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.addEventListener("pageshow", () => {
    cache = null;
    if (mode !== "self") switchMode(mode, true);
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && mode !== "self") { cache = null; switchMode(mode, true); }
  });
})();
