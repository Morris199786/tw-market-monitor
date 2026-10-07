/* =========================================================
   Heatmap Auto Refresh / 價量切換
   2026-10-07

   價：
   - 沿用 assets/app.js 原本熱力圖
   - 當日模式標示各族群近5日漲幅前2
   - 5 / 10 / 20 日不顯示金標

   量：
   - 面積 = 今日成交 / 近5日平均成交（資金熱度，3倍封頂）
   - 顏色 = 當日族群市值加權漲跌（相對昨收）
   - 每個族群固定顯示相同四項：族群 / 成交 / 5日均 / 今日漲跌
   - 不再顯示「已達5日均 XX%」
   - 33族群依資金熱度分3組切換：1–11、12–22、23–33；每組重新計算方塊比例
   - 點族群後顯示個股，依今日成交相對5日均增幅排序，前2名金標
   ========================================================= */

(function () {
  "use strict";

  const CACHE_MS = 60 * 1000;

  const state = {
    mode: "price",
    detail: null,
    detailAt: 0,
    turnover: null,
    turnoverAt: 0,
    renderingVolume: false,
    volumeRenderToken: 0,
    observer: null,
    resizeTimer: null,
    goldTimer: null,
    selectedSector: null,
    volumeGroup: 0
  };

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];

  function n(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : null;
  }

  function esc(v) {
    return String(v ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function grid() {
    return document.getElementById("heatGrid");
  }

  function activePeriod() {
    return typeof window.getHeatmapActivePeriod === "function"
      ? String(window.getHeatmapActivePeriod() || "1")
      : "1";
  }

  async function fetchJson(path, force = false) {
    if (typeof window.J === "function") {
      return window.J(path, { force });
    }

    const r = await fetch(
      path + (path.includes("?") ? "&" : "?") + "v=" + Date.now(),
      { cache: "no-store" }
    );

    if (!r.ok) throw new Error(`${path} HTTP ${r.status}`);
    return r.json();
  }

  async function loadDetail(force = false) {
    if (!force && state.detail && Date.now() - state.detailAt < 5 * 60 * 1000) {
      return state.detail;
    }

    state.detail = await fetchJson("./data/stock_detail.json", force);
    state.detailAt = Date.now();
    return state.detail;
  }

  async function loadTurnover(force = false) {
    if (!force && state.turnover && Date.now() - state.turnoverAt < CACHE_MS) {
      return state.turnover;
    }

    state.turnover = await fetchJson("./data/sector_turnover.json", force);
    state.turnoverAt = Date.now();
    return state.turnover;
  }

  function injectStyle() {
    if ($("#heatPvStyle")) return;

    const style = document.createElement("style");
    style.id = "heatPvStyle";
    style.textContent = `
      #heatPvSwitch{
        display:flex;
        width:max-content;
        gap:3px;
        padding:3px;
        margin:0 0 12px;
        border:1px solid var(--line);
        border-radius:12px;
        background:var(--soft);
      }

      #heatPvSwitch button{
        min-width:72px;
        min-height:36px;
        padding:7px 18px;
        border:0;
        border-radius:9px;
        background:transparent;
        color:var(--muted);
        font:inherit;
        font-size:13px;
        font-weight:900;
        cursor:pointer;
      }

      #heatPvSwitch button.active{
        background:var(--card);
        color:var(--ink);
        box-shadow:0 2px 8px rgba(15,23,42,.10);
      }

      #heatStrengthNote{
        display:flex;
        align-items:center;
        gap:7px;
        width:max-content;
        max-width:100%;
        margin:0 0 10px;
        padding:6px 9px;
        border:1px solid rgba(202,138,4,.25);
        border-radius:9px;
        background:rgba(254,243,199,.58);
        color:#765314;
        font-size:10px;
        font-weight:800;
      }

      #heatStrengthNote i{
        display:block;
        width:10px;
        height:10px;
        border-radius:3px;
        background:#f5d76e;
      }

      #heatGrid .heat-stock.heat-stock-top2{
        border-color:rgba(202,138,4,.42)!important;
        background:linear-gradient(135deg,rgba(254,243,199,.90),rgba(253,230,138,.60))!important;
      }

      #heatGrid .heat-strength-rank{
        display:inline-flex;
        margin-left:5px;
        padding:3px 6px;
        border:1px solid rgba(180,83,9,.24);
        border-radius:999px;
        background:rgba(255,251,235,.94);
        color:#92400e;
        font-size:9px;
        font-weight:900;
        line-height:1;
        white-space:nowrap;
      }

      html[data-theme="dark"] #heatStrengthNote{
        background:rgba(113,63,18,.26);
        color:#fde68a;
      }

      html[data-theme="dark"] #heatGrid .heat-stock.heat-stock-top2{
        background:linear-gradient(135deg,rgba(113,63,18,.62),rgba(146,64,14,.44))!important;
      }

      .turnover-head{
        display:flex;
        justify-content:space-between;
        align-items:flex-end;
        gap:10px;
        margin:0 0 10px;
      }

      .turnover-head-main{
        font-size:14px;
        font-weight:900;
      }

      .turnover-head-sub,
      .turnover-date{
        color:var(--muted);
        font-size:11px;
        line-height:1.45;
      }

      .turnover-map{
        position:relative;
        width:100%;
        height:720px;
        overflow:hidden;
        border-radius:14px;
        background:var(--soft);
      }

      .turnover-group-switch{
        display:flex;
        width:100%;
        gap:5px;
        margin:0 0 10px;
      }

      .turnover-group-switch button{
        flex:1 1 0;
        min-width:0;
        min-height:34px;
        padding:7px 5px;
        border:1px solid var(--line);
        border-radius:9px;
        background:var(--soft);
        color:var(--muted);
        font:inherit;
        font-size:11px;
        font-weight:900;
        cursor:pointer;
      }

      .turnover-group-switch button.active{
        background:var(--card);
        color:var(--ink);
        border-color:rgba(100,116,139,.45);
        box-shadow:0 2px 7px rgba(15,23,42,.08);
      }

      .turnover-explain{
        margin:0 0 10px;
        padding:9px 10px;
        border:1px solid var(--line);
        border-radius:10px;
        background:var(--soft);
        color:var(--muted);
        font-size:10px;
        font-weight:800;
        line-height:1.55;
      }

      .turnover-explain b{
        color:var(--ink);
      }

      .turnover-box{
        position:absolute;
        box-sizing:border-box;
        padding:2px;
      }

      .turnover-inner{
        width:100%;
        height:100%;
        box-sizing:border-box;
        display:flex;
        flex-direction:column;
        justify-content:center;
        overflow:hidden;
        padding:10px;
        border:0;
        border-radius:8px;
        color:#fff;
        text-align:left;
        font:inherit;
        cursor:pointer;
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.18);
        -webkit-tap-highlight-color:transparent;
      }

      .turnover-inner:active{
        transform:scale(.99);
      }

      .turnover-inner.r1{background:#a65d5d}
      .turnover-inner.r2{background:#c84e4e}
      .turnover-inner.r3{background:#dc3b3b}
      .turnover-inner.r4{background:#e52626}
      .turnover-inner.g1{background:#5b7f6d}
      .turnover-inner.g2{background:#418c68}
      .turnover-inner.g3{background:#29975e}
      .turnover-inner.g4{background:#138348}
      .turnover-inner.gray{background:#687386}

      .turnover-value,
      .turnover-avg,
      .turnover-market{
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
      }

      .turnover-name{
        display:-webkit-box;
        -webkit-box-orient:vertical;
        -webkit-line-clamp:2;
        overflow:hidden;
        white-space:normal;
        overflow-wrap:anywhere;
        font-size:16px;
        font-weight:950;
        line-height:1.12;
        margin-bottom:5px;
      }

      .turnover-value{
        font-size:14px;
        font-weight:900;
        line-height:1.15;
      }

      .turnover-avg,
      .turnover-market{
        margin-top:3px;
        font-size:12px;
        font-weight:850;
        line-height:1.18;
      }

      .turnover-status{
        padding:28px 16px;
        border:1px solid var(--line);
        border-radius:13px;
        color:var(--muted);
        text-align:center;
        font-size:12px;
        font-weight:800;
      }

      .turnover-detail{
        margin-top:12px;
        border:1px solid var(--line);
        border-radius:14px;
        background:var(--card);
        overflow:hidden;
      }

      .turnover-detail-head{
        display:flex;
        justify-content:space-between;
        align-items:flex-start;
        gap:12px;
        padding:14px 14px 12px;
        border-bottom:1px solid var(--line);
      }

      .turnover-detail-title{
        color:var(--ink);
        font-size:16px;
        font-weight:950;
      }

      .turnover-detail-meta{
        margin-top:4px;
        color:var(--muted);
        font-size:11px;
        font-weight:800;
        line-height:1.45;
      }

      .turnover-detail-close{
        flex:0 0 auto;
        border:1px solid var(--line);
        border-radius:9px;
        background:var(--soft);
        color:var(--ink);
        min-width:34px;
        min-height:34px;
        font-size:18px;
        cursor:pointer;
      }

      .turnover-stock-list{
        display:flex;
        flex-direction:column;
      }

      .turnover-stock{
        display:grid;
        grid-template-columns:minmax(0,1fr) auto;
        gap:10px;
        align-items:center;
        padding:11px 14px;
        border-bottom:1px solid var(--line);
      }

      .turnover-stock.turnover-stock-top2{
        background:linear-gradient(135deg,rgba(254,243,199,.88),rgba(253,230,138,.46));
      }

      .turnover-flow-rank{
        display:inline-flex;
        margin-left:6px;
        padding:3px 6px;
        border:1px solid rgba(180,83,9,.26);
        border-radius:999px;
        background:rgba(255,251,235,.96);
        color:#92400e;
        font-size:9px;
        font-weight:950;
        line-height:1;
        white-space:nowrap;
      }

      .turnover-stock-flow{
        margin-top:2px;
        color:var(--muted);
        font-size:10px;
        font-weight:850;
      }

      html[data-theme="dark"] .turnover-stock.turnover-stock-top2{
        background:linear-gradient(135deg,rgba(113,63,18,.54),rgba(146,64,14,.30));
      }

      .turnover-stock:last-child{
        border-bottom:0;
      }

      .turnover-stock-name{
        min-width:0;
        color:var(--ink);
        font-size:13px;
        font-weight:900;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
      }

      .turnover-stock-name small{
        margin-left:5px;
        color:var(--muted);
        font-size:10px;
        font-weight:800;
      }

      .turnover-stock-right{
        text-align:right;
        white-space:nowrap;
      }

      .turnover-stock-value{
        color:var(--ink);
        font-size:12px;
        font-weight:900;
      }

      .turnover-stock-change{
        margin-top:2px;
        font-size:11px;
        font-weight:900;
      }

      .turnover-stock-change.up{color:var(--up,#dc2626)}
      .turnover-stock-change.down{color:var(--down,#15803d)}
      .turnover-stock-change.flat{color:var(--muted)}

      @media(max-width:720px){
        #heatPvSwitch{
          margin-bottom:10px;
        }

        #heatPvSwitch button{
          min-width:68px;
          min-height:34px;
          padding:6px 16px;
          font-size:12px;
        }

        .turnover-head{
          align-items:flex-start;
          flex-direction:column;
          gap:2px;
        }

        .turnover-map{
          height:auto;
          min-height:0;
        }

        .turnover-inner{
          padding:8px;
          border-radius:7px;
        }

        .turnover-name{
          font-size:14px;
          line-height:1.12;
          margin-bottom:4px;
        }

        .turnover-value{
          font-size:12px;
        }

        .turnover-avg,
        .turnover-market{
          font-size:11px;
        }

        .turnover-group-switch button{
          font-size:10px;
          min-height:36px;
        }

        .turnover-explain{
          font-size:10px;
        }

        .turnover-detail-title{
          font-size:15px;
        }
      }
    `;

    document.head.appendChild(style);
  }

  function ensureSwitch() {
    const g = grid();
    if (!g) return;

    let wrap = $("#heatPvSwitch");

    if (!wrap) {
      wrap = document.createElement("div");
      wrap.id = "heatPvSwitch";
      wrap.innerHTML = `
        <button type="button" data-heat-pv="price">價</button>
        <button type="button" data-heat-pv="volume">量</button>
      `;

      const periodWrap = $("#heatPeriodWrap");

      if (periodWrap && periodWrap.parentNode === g.parentNode) {
        g.parentNode.insertBefore(wrap, periodWrap);
      } else {
        g.parentNode.insertBefore(wrap, g);
      }

      wrap.addEventListener("click", e => {
        const b = e.target.closest("[data-heat-pv]");
        if (!b) return;
        setMode(b.dataset.heatPv);
      });
    }

    $$("[data-heat-pv]", wrap).forEach(b => {
      b.classList.toggle("active", b.dataset.heatPv === state.mode);
    });
  }

  function setPriceControlsVisible(show) {
    const periodWrap = $("#heatPeriodWrap");
    if (periodWrap) periodWrap.style.display = show ? "" : "none";

    const note = $("#heatStrengthNote");
    if (note && !show) note.style.display = "none";
  }

  function ensureStrengthNote() {
    const g = grid();
    if (!g) return;

    let note = $("#heatStrengthNote");

    if (!note) {
      note = document.createElement("div");
      note.id = "heatStrengthNote";
      note.innerHTML = `<i></i><span>金色＝各族群近5日累積漲幅前2強</span>`;
      g.parentNode.insertBefore(note, g);
    }

    note.style.display =
      state.mode === "price" && activePeriod() === "1" ? "" : "none";
  }

  function clearGold() {
    $$("#heatGrid .heat-stock-top2").forEach(el =>
      el.classList.remove("heat-stock-top2")
    );
    $$("#heatGrid .heat-strength-rank").forEach(el => el.remove());
  }

  function latest(arr) {
    if (!Array.isArray(arr)) return null;

    for (let i = arr.length - 1; i >= 0; i--) {
      const value = n(arr[i]);
      if (value !== null) return value;
    }

    return null;
  }

  async function applyGold(force = false) {
    if (state.mode !== "price" || activePeriod() !== "1") {
      clearGold();
      ensureStrengthNote();
      return;
    }

    const details = $$("#heatGrid .heat-detail");
    if (!details.length) {
      ensureStrengthNote();
      return;
    }

    let data;

    try {
      data = await loadDetail(force);
    } catch (err) {
      console.warn("[heat gold]", err);
      return;
    }

    if (state.mode !== "price" || activePeriod() !== "1") return;

    clearGold();

    details.forEach(detail => {
      const ranked = $$(".heat-stock", detail)
        .map(row => {
          const ticker =
            row.dataset.ticker ||
            row.querySelector(".t")?.textContent?.trim() ||
            "";

          const stock = data?.stocks?.[ticker];

          return {
            row,
            value: latest(stock?.returns_by_period?.["5"] || stock?.returns)
          };
        })
        .filter(x => x.value !== null)
        .sort((a, b) => b.value - a.value)
        .slice(0, 2);

      ranked.forEach((item, index) => {
        item.row.classList.add("heat-stock-top2");

        const tickerEl = item.row.querySelector(".t");
        if (!tickerEl) return;

        const tag = document.createElement("span");
        tag.className = "heat-strength-rank";
        tag.textContent = `近5日漲幅第${index + 1}`;
        tickerEl.insertAdjacentElement("afterend", tag);
      });
    });

    ensureStrengthNote();
  }

  function fmtYi(value) {
    const valueN = n(value);
    if (valueN === null) return "—";

    const yi = valueN / 1e8;

    if (yi >= 100) return `${Math.round(yi).toLocaleString("zh-TW")}億`;
    if (yi >= 10) return `${yi.toFixed(0)}億`;
    return `${yi.toFixed(1)}億`;
  }

  function fmtPct(value, digits = 2) {
    const valueN = n(value);
    if (valueN === null) return "—";
    return `${valueN > 0 ? "+" : ""}${valueN.toFixed(digits)}%`;
  }

  function flowRatio(turnover, avg5) {
    const current = n(turnover);
    const avg = n(avg5);
    if (current === null || avg === null || avg <= 0) return null;
    return current / avg;
  }

  function fmtFlowPct(turnover, avg5) {
    const ratio = flowRatio(turnover, avg5);
    if (ratio === null) return "—";
    const pct = (ratio - 1) * 100;
    return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
  }

  function heatColor(change) {
    const value = n(change);
    if (value === null) return "gray";

    const a = Math.abs(value);
    const level = a >= 3 ? 4 : a >= 2 ? 3 : a >= 1 ? 2 : 1;
    return `${value >= 0 ? "r" : "g"}${level}`;
  }

  function sectorMap(heatmap) {
    const out = new Map();
    (heatmap?.sectors || []).forEach(sec => out.set(sec.name, sec));
    return out;
  }

  function sumArea(row) {
    return row.reduce((sum, item) => sum + item._area, 0);
  }

  function worst(row, side) {
    if (!row.length || side <= 0) return Infinity;

    const sum = sumArea(row);
    const max = Math.max(...row.map(x => x._area));
    const positive = row.map(x => x._area).filter(x => x > 0);
    const min = positive.length ? Math.min(...positive) : 0;

    if (!sum || !min) return Infinity;

    const s2 = side * side;
    const sum2 = sum * sum;

    return Math.max((s2 * max) / sum2, sum2 / (s2 * min));
  }

  function layoutRow(row, rect, output) {
    const area = sumArea(row);

    if (!row.length || area <= 0 || rect.w <= 0 || rect.h <= 0) {
      return rect;
    }

    if (rect.w >= rect.h) {
      const stripW = area / rect.h;
      let y = rect.y;

      row.forEach((item, i) => {
        const h =
          i === row.length - 1
            ? rect.y + rect.h - y
            : item._area / stripW;

        output.push({
          ...item,
          xPx: rect.x,
          yPx: y,
          wPx: stripW,
          hPx: Math.max(0, h)
        });

        y += h;
      });

      return {
        x: rect.x + stripW,
        y: rect.y,
        w: Math.max(0, rect.w - stripW),
        h: rect.h
      };
    }

    const stripH = area / rect.w;
    let x = rect.x;

    row.forEach((item, i) => {
      const w =
        i === row.length - 1
          ? rect.x + rect.w - x
          : item._area / stripH;

      output.push({
        ...item,
        xPx: x,
        yPx: rect.y,
        wPx: Math.max(0, w),
        hPx: stripH
      });

      x += w;
    });

    return {
      x: rect.x,
      y: rect.y + stripH,
      w: rect.w,
      h: Math.max(0, rect.h - stripH)
    };
  }

  function squarify(items, width, height) {
    const sorted = [...items]
      .filter(x => Number(x.value || 0) > 0)
      .sort((a, b) => Number(b.value || 0) - Number(a.value || 0));

    if (!sorted.length || width <= 0 || height <= 0) return [];

    const total = sorted.reduce((sum, x) => sum + Number(x.value || 0), 0);
    if (total <= 0) return [];

    const totalArea = width * height;

    const work = sorted.map(x => ({
      ...x,
      _area: (Number(x.value || 0) / total) * totalArea
    }));

    let rect = { x: 0, y: 0, w: width, h: height };
    let row = [];
    let i = 0;
    const output = [];

    while (i < work.length) {
      const item = work[i];
      const side = Math.min(rect.w, rect.h);

      if (!row.length) {
        row.push(item);
        i += 1;
        continue;
      }

      if (worst([...row, item], side) <= worst(row, side)) {
        row.push(item);
        i += 1;
      } else {
        rect = layoutRow(row, rect, output);
        row = [];
      }
    }

    if (row.length) layoutRow(row, rect, output);

    return output.map(x => ({
      ...x,
      x: (x.xPx / width) * 100,
      y: (x.yPx / height) * 100,
      width: (x.wPx / width) * 100,
      height: (x.hPx / height) * 100
    }));
  }

  function chooseMapHeight(items, width) {
    // 每組最多 11 個族群；切換組別後重新用整張畫布計算，
    // 因此 12、23 名不會承接上一組尾端的小方格尺寸
    if (window.innerWidth <= 720) {
      return Math.round(Math.max(500, Math.min(650, width * 1.34)));
    }

    if (window.innerWidth <= 1100) {
      return Math.round(Math.max(560, Math.min(720, width * 0.76)));
    }

    return Math.round(Math.max(600, Math.min(760, width * 0.58)));
  }

  function boxContent(item) {
    return `
      <div class="turnover-name">${esc(item.name)}</div>
      <div class="turnover-value">成交 ${fmtYi(item.turnover)}</div>
      <div class="turnover-avg">5日均 ${fmtYi(item.avg5_turnover)}</div>
      <div class="turnover-market">今日 ${fmtPct(item.change)}</div>
    `;
  }

  function stockTurnoverMap(turnoverData) {
    const out = new Map();

    (turnoverData?.stocks || []).forEach(row => {
      const ticker = String(row?.ticker || "").trim();
      if (ticker) out.set(ticker, row);
    });

    return out;
  }

  function renderSectorDetail(sectorName, turnoverData, heatmapData) {
    const detail = $("#turnoverDetail");
    if (!detail) return;

    const sector = (heatmapData?.sectors || []).find(x => x.name === sectorName);
    const turnoverSector = (turnoverData?.sectors || []).find(x => x.name === sectorName);

    if (!sector || !turnoverSector) {
      detail.hidden = true;
      detail.innerHTML = "";
      return;
    }

    const stockTurnovers = stockTurnoverMap(turnoverData);

    const rows = (sector.stocks || [])
      .map(stock => {
        const ticker = String(stock.ticker || "").trim();
        const trow = stockTurnovers.get(ticker);

        return {
          ticker,
          name: stock.name || ticker,
          turnover: n(trow?.turnover),
          avg5Turnover: n(trow?.avg5_turnover),
          flowPct: n(trow?.vs_avg5_pct),
          change: n(stock.change_pct)
        };
      })
      .filter(x => x.ticker)
      .sort((a, b) => {
        const av = a.flowPct ?? -Infinity;
        const bv = b.flowPct ?? -Infinity;
        if (bv !== av) return bv - av;
        return (b.turnover || 0) - (a.turnover || 0);
      });

    rows.forEach((row, index) => {
      row.flowRank = index < 2 && row.flowPct !== null ? index + 1 : null;
    });

    detail.hidden = false;
    detail.innerHTML = `
      <div class="turnover-detail-head">
        <div>
          <div class="turnover-detail-title">${esc(sectorName)}</div>
          <div class="turnover-detail-meta">
            成交 ${fmtYi(turnoverSector.turnover)}
            ｜5日均 ${fmtYi(turnoverSector.avg5_turnover)}
            ｜今日 ${fmtPct(sector.change_pct)}
          </div>
        </div>
        <button type="button" class="turnover-detail-close" aria-label="關閉">×</button>
      </div>

      <div class="turnover-stock-list">
        ${
          rows.length
            ? rows.map(row => {
                const cls =
                  row.change > 0 ? "up" :
                  row.change < 0 ? "down" : "flat";

                return `
                  <div class="turnover-stock ${row.flowRank ? "turnover-stock-top2" : ""}">
                    <div>
                      <div class="turnover-stock-name">
                        ${esc(row.name)}
                        <small>${esc(row.ticker)}</small>
                        ${row.flowRank ? `<span class="turnover-flow-rank">成交增幅第${row.flowRank}</span>` : ""}
                      </div>
                      <div class="turnover-stock-flow">
                        5日均 ${fmtYi(row.avg5Turnover)}｜成交增幅 ${row.flowPct === null ? "—" : fmtPct(row.flowPct, 1)}
                      </div>
                    </div>
                    <div class="turnover-stock-right">
                      <div class="turnover-stock-value">
                        成交 ${fmtYi(row.turnover)}
                      </div>
                      <div class="turnover-stock-change ${cls}">
                        今日 ${fmtPct(row.change)}
                      </div>
                    </div>
                  </div>
                `;
              }).join("")
            : `<div class="turnover-status">目前沒有個股資料</div>`
        }
      </div>
    `;

    $(".turnover-detail-close", detail)?.addEventListener("click", () => {
      state.selectedSector = null;
      detail.hidden = true;
      detail.innerHTML = "";
    });

    requestAnimationFrame(() => {
      detail.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  async function renderVolume(force = false) {
    if (state.mode !== "volume") return;

    const g = grid();
    if (!g) return;

    const token = ++state.volumeRenderToken;
    state.renderingVolume = true;

    setPriceControlsVisible(false);
    clearGold();

    g.style.display = "block";
    g.innerHTML = `<div class="turnover-status">成交金額資料載入中…</div>`;

    try {
      const [turnoverData, heatmapData] = await Promise.all([
        loadTurnover(force),
        fetchJson("./data/heatmap.json", force)
      ]);

      if (state.mode !== "volume" || token !== state.volumeRenderToken) return;

      const sectors = sectorMap(heatmapData);

      const items = (turnoverData?.sectors || [])
        .map(sec => {
          const heatSec = sectors.get(sec.name);

          const ratio = flowRatio(sec.turnover, sec.avg5_turnover);

          return {
            ...sec,
            flowRatio: ratio,
            flowPct: ratio === null ? null : (ratio - 1) * 100,
            // 面積看相對5日均資金熱度；3倍封頂只防極低基期族群吃掉整張圖
            value: ratio === null ? 0 : Math.max(0.05, Math.min(ratio, 3)),
            change: n(heatSec?.change_pct)
          };
        })
        .filter(sec => sec.value > 0)
        .sort((a, b) => b.value - a.value);

      if (!items.length) {
        g.innerHTML = `<div class="turnover-status">目前沒有成交金額資料</div>`;
        return;
      }

      g.innerHTML = `
        <div class="turnover-head">
          <div>
            <div class="turnover-head-main">族群資金熱度</div>
            <div class="turnover-head-sub">依今日成交相對近5日平均成交排序</div>
          </div>
          <div class="turnover-date">
            ${esc(turnoverData?.updated_at || turnoverData?.date || "")}
          </div>
        </div>

        <div class="turnover-explain">
          <b>方塊大小</b>＝今日成交金額 ÷ 近5日平均成交金額，越大代表今日成交相對近期越熱（極端低基期最高以3倍計）
          ｜<b>顏色</b>＝今日族群市值加權漲跌，紅色上漲、綠色下跌
          ｜族群依資金熱度分成3組，每組重新計算方塊比例；點擊族群可查看個股成交增幅，前2名以金色標示
        </div>

        <div class="turnover-group-switch" id="turnoverGroupSwitch"></div>
        <div class="turnover-map" id="turnoverMap"></div>
        <div class="turnover-detail" id="turnoverDetail" hidden></div>
      `;

      const map = $("#turnoverMap", g);
      const groupSwitch = $("#turnoverGroupSwitch", g);
      if (!map || !groupSwitch) return;

      const width = Math.max(
        280,
        Math.floor(map.getBoundingClientRect().width || g.clientWidth || 360)
      );

      // 固定每組 11 個：1–11、12–22、23–33
      // 每次切換都用該組自己的 11 檔重新做 Treemap，
      // 所以 12 名會重新取得大方格，不會從 1–33 一路縮小
      const GROUP_SIZE = 11;
      const groups = [];
      for (let i = 0; i < items.length; i += GROUP_SIZE) {
        groups.push(items.slice(i, i + GROUP_SIZE));
      }

      if (state.volumeGroup >= groups.length) state.volumeGroup = 0;

      function groupLabel(index) {
        const startRank = index * GROUP_SIZE + 1;
        const endRank = Math.min(items.length, startRank + GROUP_SIZE - 1);
        return `${startRank}–${endRank}`;
      }

      function renderGroupSwitch() {
        groupSwitch.innerHTML = groups.map((_, index) => `
          <button
            type="button"
            data-turnover-group="${index}"
            class="${index === state.volumeGroup ? "active" : ""}"
          >資金熱度 ${groupLabel(index)}</button>
        `).join("");
      }

      function renderTreemap() {
        const list = groups[state.volumeGroup] || groups[0] || [];
        const height = chooseMapHeight(list, width);
        map.style.height = `${height}px`;

        const boxes = squarify(list, width, height);

        map.innerHTML = boxes.map(item => {
          const title = [
            item.name,
            `成交 ${fmtYi(item.turnover)}`,
            `5日均 ${fmtYi(item.avg5_turnover)}`,
            `成交增幅 ${item.flowPct === null ? "—" : fmtPct(item.flowPct, 1)}`,
            `今日 ${fmtPct(item.change)}`
          ].join("｜");

          return `
            <div
              class="turnover-box"
              style="
                left:${item.x}%;
                top:${item.y}%;
                width:${item.width}%;
                height:${item.height}%;
              "
            >
              <button
                type="button"
                class="turnover-inner ${heatColor(item.change)}"
                data-turnover-sector="${esc(item.name)}"
                title="${esc(title)}"
              >
                ${boxContent(item)}
              </button>
            </div>
          `;
        }).join("");
      }

      renderGroupSwitch();
      renderTreemap();

      groupSwitch.addEventListener("click", e => {
        const btn = e.target.closest("[data-turnover-group]");
        if (!btn) return;

        const next = Number(btn.dataset.turnoverGroup);
        if (!Number.isInteger(next) || next < 0 || next >= groups.length) return;

        state.volumeGroup = next;
        state.selectedSector = null;

        const detail = $("#turnoverDetail", g);
        if (detail) {
          detail.hidden = true;
          detail.innerHTML = "";
        }

        renderGroupSwitch();
        renderTreemap();
      });

      map.addEventListener("click", e => {
        const btn = e.target.closest("[data-turnover-sector]");
        if (!btn) return;

        const sectorName = btn.dataset.turnoverSector;
        state.selectedSector = sectorName;
        renderSectorDetail(sectorName, turnoverData, heatmapData);
      });

      if (state.selectedSector) {
        renderSectorDetail(state.selectedSector, turnoverData, heatmapData);
      }
    } catch (err) {
      console.error("[turnover heatmap]", err);

      if (state.mode === "volume" && token === state.volumeRenderToken) {
        g.innerHTML = `<div class="turnover-status">成交金額資料讀取失敗</div>`;
      }
    } finally {
      state.renderingVolume = false;
    }
  }

  function restorePrice() {
    state.volumeRenderToken += 1;
    state.selectedSector = null;
    setPriceControlsVisible(true);

    const g = grid();
    if (g) g.style.display = "";

    if (typeof window.renderHeatCurrentPeriod === "function") {
      window.renderHeatCurrentPeriod();
    }

    requestAnimationFrame(() => {
      ensureSwitch();
      ensureStrengthNote();

      clearTimeout(state.goldTimer);
      state.goldTimer = setTimeout(() => applyGold(false), 80);
    });
  }

  function setMode(mode) {
    if (mode !== "price" && mode !== "volume") return;

    state.mode = mode;
    ensureSwitch();

    if (mode === "volume") {
      setPriceControlsVisible(false);
      renderVolume(true);
    } else {
      restorePrice();
    }
  }

  function observeGrid() {
    const g = grid();
    if (!g) return;

    state.observer?.disconnect();

    state.observer = new MutationObserver(() => {
      if (state.renderingVolume) return;

      if (state.mode === "volume") {
        if (!g.querySelector(".turnover-map")) renderVolume(false);
        return;
      }

      clearTimeout(state.goldTimer);
      state.goldTimer = setTimeout(() => applyGold(false), 80);
    });

    state.observer.observe(g, { childList: true, subtree: true });
  }

  function bind() {
    injectStyle();
    ensureSwitch();
    ensureStrengthNote();
    observeGrid();

    window.addEventListener("heatmap:period-changed", () => {
      if (state.mode !== "price") return;
      clearGold();
      ensureStrengthNote();
      setTimeout(() => applyGold(false), 60);
    });

    window.addEventListener("heatmap:weight-changed", () => {
      if (state.mode !== "price") return;
      setTimeout(() => applyGold(false), 60);
    });

    window.addEventListener("heatmap:detail-rendered", () => {
      if (state.mode !== "price") return;
      setTimeout(() => applyGold(false), 60);
    });

    window.addEventListener("heatmap:data-updated", () => {
      state.detail = null;
      state.detailAt = 0;
      state.turnover = null;
      state.turnoverAt = 0;

      if (state.mode === "volume") {
        renderVolume(true);
      } else {
        setTimeout(() => applyGold(true), 80);
      }
    });

    window.addEventListener(
      "resize",
      () => {
        if (state.mode !== "volume") return;
        clearTimeout(state.resizeTimer);
        state.resizeTimer = setTimeout(() => renderVolume(false), 180);
      },
      { passive: true }
    );

    setInterval(() => {
      if (state.mode !== "volume") return;
      state.turnover = null;
      state.turnoverAt = 0;
      renderVolume(true);
    }, 60 * 1000);

    setTimeout(() => {
      ensureSwitch();
      ensureStrengthNote();
      applyGold(false);
    }, 200);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind, { once: true });
  } else {
    bind();
  }

  window.getHeatmapDisplayMode = () => state.mode;
  window.setHeatmapDisplayMode = setMode;
  window.refreshTurnoverHeatmap = force => renderVolume(!!force);
  window.refreshHeatStrength = force => applyGold(!!force);
})();
