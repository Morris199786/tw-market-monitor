/* 市場熱力圖：族群篩選、個股走勢、日K與法人籌碼｜2026-10-13 large-trend */
(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const esc = x => String(x ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[c]));

  const num = x =>
    x == null || x === "" ? null :
    Number.isFinite(Number(x)) ? Number(x) : null;

  const pct = x =>
    num(x) == null ? "—" :
    `${x > 0 ? "+" : ""}${Number(x).toFixed(2)}%`;

  const lots = x =>
    num(x) == null ? "待補" :
    `${x > 0 ? "+" : ""}${Math.round(x).toLocaleString("zh-TW")}`;

  const cls = x =>
    num(x) > 0 ? "is-up" :
    num(x) < 0 ? "is-down" : "";

  const last = a =>
    Array.isArray(a)
      ? [...a].reverse().map(num).find(x => x !== null) ?? null
      : null;

  const PERIODS = [5, 10, 20];

  let cfg = null;
  let data = null;
  let promise = null;
  let ticker = "";
  let sector = "";
  let subgroup = "";
  let origin = "heatmap";
  let period = 5;
  let tab = "trend";
  let expanded = false;
  let token = 0;

  async function getJSON(url) {
    const r = await fetch(
      url + (url.includes("?") ? "&" : "?") + "v=" + Date.now(),
      { cache: "no-store" }
    );

    if (!r.ok) throw Error(url + " " + r.status);
    return r.json();
  }

  async function load() {
    if (data) return data;

    if (!promise) {
      promise = getJSON("./data/stock_detail.json")
        .then(x => (data = x, x))
        .finally(() => promise = null);
    }

    return promise;
  }

  function sectorList() {
    return Array.isArray(cfg?.sectors) ? cfg.sectors : [];
  }

  function controls() {
    const grid = $("#heatGrid");
    if (!grid) return;

    let host = $("#heatSectorControls");

    if (!host) {
      host = document.createElement("div");
      host.id = "heatSectorControls";
      host.className = "heat-sector-controls";
      grid.before(host);
    }

    if (!$("#heatSectorSelect")) {
      const sel = document.createElement("select");
      sel.id = "heatSectorSelect";
      sel.className = "heat-sector-select";
      sel.setAttribute("aria-label", "選擇族群");

      sel.innerHTML =
        '<option value="">全部族群</option>' +
        sectorList().map(x =>
          `<option value="${esc(x.name)}">${esc(x.name)}</option>`
        ).join("");

      sel.onchange = () => {
        sector = sel.value;
        subgroup = "";
        subSelect();
      };

      host.append(sel);
    }

    if (!$("#heatSubgroupHost")) {
      const h = document.createElement("div");
      h.id = "heatSubgroupHost";
      host.append(h);
    }

    subSelect();
  }

  function subSelect() {
    const h = $("#heatSubgroupHost");
    if (!h) return;

    h.replaceChildren();

    const groups = sectorList()
      .find(x => x.name === sector)?.subgroups;

    if (!Array.isArray(groups) || !groups.length) return;

    const sel = document.createElement("select");
    sel.id = "heatSubgroupSelect";
    sel.className = "heat-sector-select heat-subgroup-select";

    sel.innerHTML =
      '<option value="">全部細分類</option>' +
      groups.map(x =>
        `<option value="${esc(x.name)}">${esc(x.name)}</option>`
      ).join("");

    sel.value = subgroup;
    sel.onchange = () => subgroup = sel.value;

    h.append(sel);
  }

  function tickerOf(row) {
    for (const x of [
      row.dataset.ticker,
      row.querySelector("[data-ticker]")?.dataset.ticker,
      row.querySelector(".ticker")?.textContent,
      row.textContent
    ]) {
      const m = String(x || "").match(/\b\d{4,6}\b/);
      if (m) return m[0];
    }

    return "";
  }

  function decorate() {
    $$("#heatGrid .heat-stock").forEach(r => {
      if (!r.hasAttribute("tabindex")) r.tabIndex = 0;
      r.setAttribute("role", "button");
    });
  }

  function styles() {
    if ($("#stockDetailStyles")) return;

    const el = document.createElement("style");
    el.id = "stockDetailStyles";

    el.textContent = `
      .heat-sector-controls{
        display:flex;
        gap:8px;
        flex-wrap:wrap;
        margin:0 0 12px
      }

      .heat-sector-select{
        min-height:40px;
        max-width:100%;
        min-width:160px;
        padding:0 12px;
        border:1px solid var(--line,#d9dee8);
        border-radius:12px;
        background:var(--card,#fff);
        color:var(--ink,#111827);
        font-weight:800
      }

      .stock-detail-modal{
        position:fixed;
        inset:0;
        z-index:99999;
        display:none;
        align-items:flex-end;
        justify-content:center;
        background:rgba(15,23,42,.6);
        backdrop-filter:blur(3px)
      }

      .stock-detail-modal.open{
        display:flex
      }

      .stock-detail-sheet{
        width:min(1100px,100%);
        max-height:97dvh;
        overflow:auto;
        overscroll-behavior:contain;
        -webkit-overflow-scrolling:touch;
        border-radius:20px 20px 0 0;
        background:var(--bg,#f8fafc);
        color:var(--ink,#111827);
        box-shadow:0 -20px 60px #0004
      }

      .stock-detail-head{
        position:sticky;
        top:0;
        z-index:20;
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        padding:12px 16px;
        border-bottom:1px solid var(--line,#e5e7eb);
        background:var(--bg,#f8fafc)
      }

      .stock-detail-title{
        min-width:0
      }

      .stock-detail-title strong{
        display:block;
        font-size:18px;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap
      }

      .stock-detail-title small{
        display:block;
        margin-top:3px;
        color:var(--muted,#64748b);
        font-size:12px
      }

      .stock-detail-close{
        width:40px;
        height:40px;
        flex-shrink:0;
        border:1px solid var(--line,#e5e7eb);
        border-radius:50%;
        background:var(--card,#fff);
        color:var(--ink,#111827);
        font-size:22px
      }

      .stock-detail-body{
        padding:12px 14px 24px
      }

      .stock-detail-periods{
        display:grid;
        grid-template-columns:repeat(3,1fr);
        gap:6px;
        padding:4px;
        margin-bottom:10px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:14px;
        background:var(--card,#fff)
      }

      .stock-detail-period{
        min-height:40px;
        border:0;
        border-radius:10px;
        background:transparent;
        color:var(--muted,#64748b);
        font-weight:900
      }

      .stock-detail-period.active{
        background:var(--ink,#111827);
        color:var(--card,#fff)
      }

      .stock-detail-tabs{
        display:grid;
        grid-template-columns:repeat(3,1fr);
        gap:6px;
        margin-bottom:12px
      }

      .stock-detail-tab{
        min-height:42px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:12px;
        background:var(--card,#fff);
        color:var(--muted,#64748b);
        font-weight:900
      }

      .stock-detail-tab.active{
        border-color:var(--ink,#111827);
        color:var(--ink,#111827)
      }

      .stock-detail-card{
        padding:14px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:16px;
        background:var(--card,#fff)
      }

      .stock-detail-section-title{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:12px;
        margin-bottom:14px
      }

      .stock-detail-section-title strong{
        font-size:16px
      }

      .stock-detail-section-title small{
        font-size:12px;
        color:var(--muted,#64748b)
      }

      .stock-detail-kpis{
        display:grid;
        grid-template-columns:repeat(3,minmax(0,1fr));
        gap:8px;
        margin-bottom:12px
      }

      .stock-detail-kpi{
        min-width:0;
        padding:11px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:12px;
        background:var(--soft,#f8fafc)
      }

      .stock-detail-kpi span{
        display:block;
        font-size:12px;
        font-weight:800;
        color:var(--muted,#64748b);
        margin-bottom:5px
      }

      .stock-detail-kpi strong{
        display:block;
        font-size:20px;
        white-space:nowrap;
        font-variant-numeric:tabular-nums
      }

      .stock-detail-chart{
        width:100%;
        overflow:visible
      }

      .stock-detail-chart svg{
        display:block;
        width:100%;
        height:auto;
        overflow:visible
      }

      .stock-detail-trend-chart{
        width:100%;
        min-height:clamp(320px,55dvh,660px);
        display:flex;
        align-items:stretch
      }

      .stock-detail-trend-chart svg{
        width:100%;
        height:clamp(320px,55dvh,660px);
        min-height:320px;
        max-height:660px
      }

      .stock-detail-legend{
        display:flex;
        justify-content:center;
        flex-wrap:wrap;
        gap:14px;
        margin:16px 0 5px;
        font-size:13px;
        font-weight:800;
        color:var(--muted,#64748b)
      }

      .stock-detail-legend span{
        display:flex;
        align-items:center;
        gap:6px
      }

      .stock-detail-dot{
        display:inline-block;
        width:11px;
        height:11px;
        border-radius:50%
      }

      .stock-detail-dot.stock{
        background:#2563eb
      }

      .stock-detail-dot.sector{
        background:#f59e0b
      }

      .stock-detail-dot.index{
        background:#64748b
      }

      .stock-detail-note,
      .stock-flow-table-caption{
        font-size:12px;
        color:var(--muted,#64748b);
        margin:10px 0
      }

      .stock-flow-summary{
        display:flex;
        justify-content:space-between;
        align-items:center;
        padding:14px;
        border:1px solid var(--line,#e5e7eb);
        border-radius:14px;
        margin-bottom:12px
      }

      .stock-flow-summary strong{
        font-size:22px
      }

      .stock-flow-table-wrap{
        border:1px solid var(--line,#e5e7eb);
        border-radius:14px;
        overflow:hidden
      }

      .stock-flow-table-scroll{
        overflow:hidden
      }

      .stock-flow-stage.expanded .stock-flow-table-scroll{
        max-height:min(330px,42vh);
        overflow-y:auto;
        -webkit-overflow-scrolling:touch;
        touch-action:pan-y
      }

      .stock-flow-table{
        width:100%;
        table-layout:fixed;
        border-collapse:collapse
      }

      .stock-flow-table th,
      .stock-flow-table td{
        padding:12px 4px;
        text-align:center;
        border-bottom:1px solid var(--line,#e5e7eb);
        font-size:12px;
        white-space:nowrap
      }

      .stock-flow-table th{
        position:sticky;
        top:0;
        background:var(--soft,#f8fafc);
        color:var(--muted,#64748b)
      }

      .stock-flow-table td:first-child,
      .stock-flow-table th:first-child{
        text-align:left;
        padding-left:10px
      }

      .stock-flow-pull{
        width:100%;
        min-height:46px;
        border:0;
        background:transparent;
        color:var(--ink,#111827);
        font-weight:800
      }

      .stock-detail-loading,
      .stock-detail-empty{
        padding:32px 12px;
        text-align:center;
        color:var(--muted,#64748b)
      }

      .is-up{
        color:#dc2626!important
      }

      .is-down{
        color:#168357!important
      }

      @media(min-width:700px){
        .stock-detail-modal{
          align-items:center;
          padding:20px
        }

        .stock-detail-sheet{
          border-radius:22px;
          max-height:94dvh
        }
      }

      @media(max-width:520px){
        .stock-detail-sheet{
          max-height:calc(100dvh - env(safe-area-inset-top));
          border-radius:17px 17px 0 0
        }

        .stock-detail-head{
          padding:10px 12px
        }

        .stock-detail-body{
          padding:10px 10px calc(18px + env(safe-area-inset-bottom))
        }

        .stock-detail-card{
          padding:10px 8px
        }

        .stock-detail-section-title strong{
          font-size:14px
        }

        .stock-detail-section-title small{
          font-size:11px
        }

        .stock-detail-kpis{
          gap:5px
        }

        .stock-detail-kpi{
          padding:9px 5px
        }

        .stock-detail-kpi span{
          font-size:10px
        }

        .stock-detail-kpi strong{
          font-size:16px
        }

        .stock-detail-trend-chart{
          min-height:clamp(350px,57dvh,650px)
        }

        .stock-detail-trend-chart svg{
          height:clamp(350px,57dvh,650px);
          min-height:350px
        }

        .stock-flow-table th,
        .stock-flow-table td{
          font-size:10px;
          padding:10px 2px
        }
      }
    `;

    document.head.append(el);
  }

  function modal() {
    let m = $("#stockDetailModal");
    if (m) return m;

    m = document.createElement("div");
    m.id = "stockDetailModal";
    m.className = "stock-detail-modal";
    m.setAttribute("aria-hidden", "true");

    m.innerHTML = `
      <section class="stock-detail-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="個股詳細資訊">

        <header class="stock-detail-head">
          <div class="stock-detail-title">
            <strong id="stockDetailTitle">個股資訊</strong>
            <small id="stockDetailSubtitle"></small>
          </div>

          <button class="stock-detail-close"
            id="stockDetailClose"
            type="button"
            aria-label="關閉">×</button>
        </header>

        <div class="stock-detail-body"
          id="stockDetailBody"></div>
      </section>
    `;

    document.body.append(m);

    const close = () => {
      window.DailyK?.destroy();
      m.classList.remove("open");
      m.setAttribute("aria-hidden", "true");
      document.documentElement.style.overflow = "";
      ticker = "";
      period = 5;
      tab = "trend";
      expanded = false;
      token++;
    };

    $("#stockDetailClose", m).onclick = close;

    m.onclick = e => {
      if (e.target === m) close();
    };

    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && m.classList.contains("open")) {
        close();
      }
    });

    return m;
  }

  async function open(t, s = "", o = "heatmap") {
    t = String(t || "").trim();
    if (!t) return;

    ticker = t;
    sector = s || "";
    origin = o;
    period = o === "chips" ? 20 : 5;
    tab = "kline";
    expanded = o === "chips";

    const id = ++token;
    const m = modal();

    m.classList.add("open");
    m.setAttribute("aria-hidden", "false");
    document.documentElement.style.overflow = "hidden";

    $("#stockDetailTitle").textContent = t;
    $("#stockDetailSubtitle").textContent = sector;
    $("#stockDetailBody").innerHTML =
      '<div class="stock-detail-loading">載入個股資料中…</div>';

    try {
      const d = await load();

      if (id !== token || ticker !== t) return;

      const st = d?.stocks?.[t];

      if (!st) {
        $("#stockDetailBody").innerHTML =
          '<div class="stock-detail-empty">目前沒有 ' +
          esc(t) + " 的個股詳細資料</div>";
        return;
      }

      if (!d?.sectors?.[sector]) {
        sector = [
          st.primary_sector,
          ...(st.sectors || [])
        ].find(x => d?.sectors?.[x]) || sector;
      }

      $("#stockDetailTitle").textContent =
        `${st.name || t} ${t}`;

      $("#stockDetailSubtitle").textContent =
        `${sector || (o === "chips" ? "籌碼日報" : "市場熱力圖")}｜資料截至 ${d.as_of_date || "—"}`;

      render();

    } catch (e) {
      console.error("[stock detail]", e);

      if (id === token) {
        $("#stockDetailBody").innerHTML =
          '<div class="stock-detail-empty">個股資料載入失敗</div>';
      }
    }
  }

  function vals(obj, p) {
    return obj?.returns_by_period?.[String(p)] ||
      (p === 5 ? obj?.returns : []) || [];
  }

  function labels(p) {
    return data?.date_labels_by_period?.[String(p)] ||
      (p === 5 ? data?.date_labels : []) || [];
  }

  function render() {
    const body = $("#stockDetailBody");
    const st = data?.stocks?.[ticker];

    if (!body || !st) return;

    window.DailyK?.destroy();

    const chips = origin === "chips";

    if (chips && tab === "trend") tab = "flow";

    body.innerHTML = `
      <div class="stock-detail-periods"
        ${chips ? 'hidden style="display:none"' : ""}>
        ${PERIODS.map(p => `
          <button class="stock-detail-period ${period === p ? "active" : ""}"
            data-period="${p}" type="button">${p}日</button>
        `).join("")}
      </div>

      <div class="stock-detail-tabs"
        ${chips ? 'style="grid-template-columns:repeat(2,minmax(0,1fr))"' : ""}>

        <button class="stock-detail-tab ${tab === "kline" ? "active" : ""}"
          data-detail-tab="kline">日 K</button>

        ${chips ? "" : `
          <button class="stock-detail-tab ${tab === "trend" ? "active" : ""}"
            data-detail-tab="trend">走勢</button>
        `}

        <button class="stock-detail-tab ${tab === "flow" ? "active" : ""}"
          data-detail-tab="flow">
          ${chips ? "20日法人籌碼" : "籌碼"}
        </button>
      </div>

      <div class="stock-detail-card">
        ${
          tab === "kline"
            ? '<div id="dailyKHost"></div>'
            : tab === "trend"
              ? trend(st)
              : flow(st)
        }
      </div>
    `;

    $$("[data-period]", body).forEach(b => {
      b.onclick = () => {
        period = Number(b.dataset.period);
        expanded = chips;
        render();
      };
    });

    $$("[data-detail-tab]", body).forEach(b => {
      b.onclick = () => {
        tab = b.dataset.detailTab;
        expanded = chips;
        render();
      };
    });

    if (tab === "kline") {
      const host = $("#dailyKHost", body);

      if (window.DailyK) {
        window.DailyK.mount(host, ticker);
      } else {
        host.textContent = "日 K 元件未載入，請重新整理";
      }
    }

    if (tab === "flow" && !chips) {
      const b = $("#stockFlowPull", body);

      if (b) {
        b.onclick = () => {
          expanded = !expanded;
          render();
        };
      }
    }
  }

  function trend(st) {
    if (!data?.sectors?.[sector]) {
      sector = [
        st.primary_sector,
        ...(st.sectors || [])
      ].find(x => data?.sectors?.[x]) || sector;
    }

    const sec = data?.sectors?.[sector] || {};
    const bench = data?.benchmark || {};

    const a = vals(st, period);
    const b = vals(sec, period);
    const c = vals(bench, period);

    const al = last(a);
    const bl = last(b);
    const cl = last(c);

    const diff = (x, y) =>
      x == null || y == null ? null : x - y;

    return `
      <div class="stock-detail-section-title">
        <strong>近${period}日相對走勢</strong>
        <small>前一交易日收盤＝0%</small>
      </div>

      <div class="stock-detail-kpis">
        ${[
          ["個股", al],
          ["相對族群", diff(al, bl)],
          ["相對大盤", diff(al, cl)]
        ].map(([name, value]) => `
          <div class="stock-detail-kpi">
            <span>${name}</span>
            <strong class="${cls(value)}">${pct(value)}</strong>
          </div>
        `).join("")}
      </div>

      <div class="stock-detail-chart stock-detail-trend-chart">
        ${chart(labels(period), [
          { values: a, color: "#2563eb" },
          { values: b, color: "#f59e0b" },
          { values: c, color: "#64748b" }
        ])}
      </div>

      <div class="stock-detail-legend">
        <span><i class="stock-detail-dot stock"></i>個股</span>
        <span><i class="stock-detail-dot sector"></i>${esc(sector || "同族群")}</span>
        <span><i class="stock-detail-dot index"></i>${esc(bench.name || "上市加權指數")}</span>
      </div>
    `;
  }

  function chart(l, series) {
    const w = 900;
    const h = 520;

    const p = {
      left: 83,
      right: 36,
      top: 32,
      bottom: 74
    };

    const all = series
      .flatMap(s => s.values || [])
      .map(num)
      .filter(x => x !== null);

    if (!all.length || !l.length) {
      return '<div class="stock-detail-empty">暫無完整走勢資料</div>';
    }

    let min = Math.min(0, ...all);
    let max = Math.max(0, ...all);

    if (max - min < 0.5) {
      max += 1;
      min -= 1;
    }

    const extra = (max - min) * 0.13;
    max += extra;
    min -= extra;

    const pw = w - p.left - p.right;
    const ph = h - p.top - p.bottom;

    const x = i =>
      p.left + (l.length <= 1
        ? pw / 2
        : i / (l.length - 1) * pw);

    const y = v =>
      p.top + (max - v) / (max - min) * ph;

    const grid = Array.from({ length: 6 }, (_, i) => {
      const v = max - (max - min) * i / 5;

      return `
        <g>
          <line x1="${p.left}" x2="${w - p.right}"
            y1="${y(v)}" y2="${y(v)}"
            stroke="currentColor" opacity=".13"/>

          <text x="${p.left - 12}" y="${y(v) + 5}"
            text-anchor="end"
            fill="currentColor"
            opacity=".75"
            font-size="17"
            font-weight="600">${v.toFixed(1)}%</text>
        </g>
      `;
    }).join("");

    const paths = series.map(s => {
      let d = "";
      let draw = false;

      (s.values || []).forEach((v, i) => {
        const n = num(v);

        if (n === null) {
          draw = false;
          return;
        }

        d += `${draw ? " L" : "M"} ${x(i).toFixed(1)} ${y(n).toFixed(1)}`;
        draw = true;
      });

      return `
        <path d="${d}"
          fill="none"
          stroke="${s.color}"
          stroke-width="4"
          stroke-linecap="round"
          stroke-linejoin="round"/>
      `;
    }).join("");

    const maxLabels =
      period >= 20 ? 6 :
      period >= 10 ? 5 : l.length;

    const step = Math.max(
      1,
      Math.ceil((l.length - 1) / Math.max(1, maxLabels - 1))
    );

    let inds = l.map((_, i) => i).filter(i =>
      i === 0 ||
      i === l.length - 1 ||
      i % step === 0
    );

    if (
      inds.length > 1 &&
      inds[inds.length - 1] - inds[inds.length - 2] <
      Math.max(1, step * 0.7)
    ) {
      inds.splice(inds.length - 2, 1);
    }

    const dates = inds.map(i => `
      <text x="${x(i)}" y="${h - 27}"
        text-anchor="${i === 0 ? "start" : i === l.length - 1 ? "end" : "middle"}"
        fill="currentColor"
        opacity=".8"
        font-size="17"
        font-weight="600">${esc(l[i])}</text>
    `).join("");

    const zero = min <= 0 && max >= 0
      ? `<line x1="${p.left}" x2="${w - p.right}"
          y1="${y(0)}" y2="${y(0)}"
          stroke="currentColor"
          opacity=".35"
          stroke-dasharray="6 5"/>`
      : "";

    return `
      <svg viewBox="0 0 ${w} ${h}"
        preserveAspectRatio="none"
        role="img"
        aria-label="近${period}日相對走勢">
        ${grid}
        ${zero}
        ${paths}
        ${dates}
      </svg>
    `;
  }

  function flowRows(st) {
    return (
      Array.isArray(st?.institutional) ? st.institutional : []
    ).slice(-20);
  }

  function table(rows) {
    return `
      <table class="stock-flow-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>外資</th>
            <th>投信</th>
            <th>自營商</th>
            <th>合計</th>
          </tr>
        </thead>

        <tbody>
          ${[...rows].reverse().map(r => `
            <tr>
              <td>${esc(r.date_label || "—")}</td>
              ${[
                "foreign_lots",
                "trust_lots",
                "dealer_lots",
                "total_lots"
              ].map(k => `
                <td class="${cls(r[k])}">${lots(r[k])}</td>
              `).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function flow(st) {
    const rows = flowRows(st);

    if (!rows.length) {
      return '<div class="stock-detail-empty">目前沒有法人籌碼資料</div>';
    }

    const recent = rows.slice(-period);

    const ok =
      recent.length === period &&
      recent.every(r =>
        r.available !== false &&
        num(r.total_lots) !== null
      );

    const total = ok
      ? recent.reduce((s, r) => s + Number(r.total_lots), 0)
      : null;

    return `
      <div class="stock-detail-section-title">
        <strong>近${period}日法人籌碼</strong>
        <small>
          ${ok
            ? "長條圖看合計｜下方可查看每日明細"
            : `資料待補：已取得 ${recent.filter(r =>
                r.available !== false &&
                num(r.total_lots) !== null
              ).length}/${period} 日`
          }
        </small>
      </div>

      <div class="stock-flow-summary">
        <span>近${period}日三大法人合計</span>
        <strong class="${cls(total)}">${lots(total)}</strong>
      </div>

      <div class="stock-flow-stage ${expanded ? "expanded" : ""}"
        id="stockFlowStage">

        <div class="stock-detail-note">
          長條圖僅顯示外資＋投信＋自營商「合計」買賣超｜單位：張
        </div>

        <div class="stock-detail-chart">
          ${bars(recent)}
        </div>

        <div class="stock-flow-table-caption">
          ${expanded
            ? `近${rows.length}日籌碼明細｜上下滑動可看更早日期`
            : "近5日籌碼明細"
          }
        </div>

        <div class="stock-flow-table-wrap">
          <div class="stock-flow-table-scroll">
            ${table(expanded ? rows : rows.slice(-5))}
          </div>
        </div>

        ${rows.length > 5 && origin !== "chips"
          ? `<button id="stockFlowPull"
              class="stock-flow-pull"
              aria-expanded="${expanded}">
              ${expanded ? "⌄　收回近5日" : "⌃　顯示更多"}
            </button>`
          : ""
        }
      </div>
    `;
  }

  function bars(rows) {
    const w = 680;
    const h = 260;

    const p = {
      left: 58,
      right: 18,
      top: 24,
      bottom: 46
    };

    const v = rows.map(r => num(r.total_lots) || 0);
    const max = Math.max(1, ...v.map(Math.abs));

    const pw = w - p.left - p.right;
    const ph = h - p.top - p.bottom;
    const zero = p.top + ph / 2;

    const yy = x =>
      zero - x / max * (ph / 2 - 8);

    const slot = pw / Math.max(1, rows.length);
    const bw = Math.max(6, Math.min(44, slot * 0.56));

    const step = Math.max(
      1,
      Math.ceil(
        rows.length /
        (rows.length >= 20 ? 6 : rows.length >= 10 ? 5 : rows.length)
      )
    );

    return `
      <svg viewBox="0 0 ${w} ${h}"
        aria-label="近${period}日三大法人合計買賣超">

        <line x1="${p.left}" y1="${zero}"
          x2="${w - p.right}" y2="${zero}"
          stroke="currentColor" opacity=".3"/>

        <text x="${p.left - 8}" y="${p.top + 4}"
          text-anchor="end" font-size="11" fill="currentColor">
          +${Math.round(max).toLocaleString("zh-TW")}
        </text>

        <text x="${p.left - 8}" y="${h - p.bottom}"
          text-anchor="end" font-size="11" fill="currentColor">
          -${Math.round(max).toLocaleString("zh-TW")}
        </text>

        ${rows.map((r, i) => {
          const n = num(r.total_lots);

          if (r.available === false || n === null) return "";

          const x = p.left + slot * i + (slot - bw) / 2;
          const y = n >= 0 ? yy(n) : zero;
          const hh = Math.max(1.5, Math.abs(yy(n) - zero));

          return `
            <rect x="${x}" y="${y}"
              width="${bw}" height="${hh}"
              rx="4"
              fill="${n >= 0 ? "#dc2626" : "#168357"}"/>

            ${i === 0 || i === rows.length - 1 || i % step === 0
              ? `<text x="${x + bw / 2}" y="${h - 15}"
                  text-anchor="middle"
                  font-size="10"
                  fill="currentColor">
                  ${esc(r.date_label || "")}
                </text>`
              : ""
            }
          `;
        }).join("")}
      </svg>
    `;
  }

  function bind() {
    document.addEventListener("click", e => {
      const chip = e.target.closest?.(
        "#buyRows [data-chip-ticker],#sellRows [data-chip-ticker]"
      );

      if (chip) {
        open(chip.dataset.chipTicker, "", "chips");
        return;
      }

      const row = e.target.closest?.("#heatGrid .heat-stock");

      if (row) {
        open(tickerOf(row), row.dataset.sector || sector);
      }
    });

    document.addEventListener("keydown", e => {
      if (!["Enter", " "].includes(e.key)) return;

      const chip = e.target.closest?.(
        "#buyRows [data-chip-ticker],#sellRows [data-chip-ticker]"
      );

      const row = e.target.closest?.("#heatGrid .heat-stock");

      if (chip || row) {
        e.preventDefault();

        if (chip) {
          open(chip.dataset.chipTicker, "", "chips");
        } else {
          open(tickerOf(row), row.dataset.sector || sector);
        }
      }
    });
  }

  async function init() {
    styles();
    modal();
    bind();

    try {
      cfg = await getJSON("./data/sectors.json");
    } catch (e) {
      console.error("[heatmap sector]", e);
      cfg = { sectors: [] };
    }

    controls();
    decorate();

    const grid = $("#heatGrid");

    if (grid) {
      new MutationObserver(decorate).observe(grid, {
        childList: true,
        subtree: false
      });
    }

    let tries = 0;

    const timer = setInterval(() => {
      controls();
      decorate();

      if (
        $$("#heatGrid .heat-stock").length ||
        ++tries > 30
      ) {
        clearInterval(timer);
      }
    }, 150);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
