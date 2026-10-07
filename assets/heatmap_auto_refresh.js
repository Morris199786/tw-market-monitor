/* =========================================================
   Heatmap Auto Refresh / 價量切換
   2026-10-07

   價：
   - 完全沿用 assets/app.js 的原始熱力圖
   - 當日模式標示各族群「近5日漲幅前2」
   - 5 / 10 / 20 日不顯示金標

   量：
   - 方塊面積 = 當日族群累積成交金額
   - 顏色 = 當日族群市值漲跌幅（紅漲綠跌）
   - 統一單位 = 億元
   - 盤中：顯示「已達5日均 XX%」
   - 收盤後：顯示「較5日均 ±XX%」
   - 5日均 = 前5個完整交易日平均成交金額
   - 使用 squarified treemap，依實際容器寬高排版
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
    goldTimer: null
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
    if (
      !force &&
      state.detail &&
      Date.now() - state.detailAt < 5 * 60 * 1000
    ) {
      return state.detail;
    }

    state.detail = await fetchJson("./data/stock_detail.json", force);
    state.detailAt = Date.now();
    return state.detail;
  }

  async function loadTurnover(force = false) {
    if (
      !force &&
      state.turnover &&
      Date.now() - state.turnoverAt < CACHE_MS
    ) {
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
        background:linear-gradient(
          135deg,
          rgba(254,243,199,.90),
          rgba(253,230,138,.60)
        )!important;
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
        background:linear-gradient(
          135deg,
          rgba(113,63,18,.62),
          rgba(146,64,14,.44)
        )!important;
      }

      .turnover-head{
        display:flex;
        justify-content:space-between;
        align-items:flex-end;
        gap:10px;
        margin:0 0 10px;
      }

      .turnover-head-main{
        font-size:13px;
        font-weight:900;
      }

      .turnover-head-sub,
      .turnover-date{
        color:var(--muted);
        font-size:10px;
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
        padding:9px;
        border-radius:8px;
        color:#fff;
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.16);
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

      .turnover-name,
      .turnover-value,
      .turnover-avg,
      .turnover-market{
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
      }

      .turnover-name{
        font-size:clamp(11px,1.25vw,20px);
        font-weight:900;
        line-height:1.1;
        margin-bottom:5px;
      }

      .turnover-value{
        font-size:clamp(10px,1.1vw,18px);
        font-weight:900;
        line-height:1.1;
      }

      .turnover-avg,
      .turnover-market{
        margin-top:4px;
        font-size:clamp(8px,.78vw,12px);
        font-weight:800;
        line-height:1.15;
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
          height:760px;
        }

        .turnover-inner{
          padding:6px;
          border-radius:6px;
        }

        .turnover-name{
          font-size:10px;
          margin-bottom:3px;
        }

        .turnover-value{
          font-size:9px;
        }

        .turnover-avg,
        .turnover-market{
          margin-top:2px;
          font-size:7px;
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
    if (periodWrap) {
      periodWrap.style.display = show ? "" : "none";
    }

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
      state.mode === "price" && activePeriod() === "1"
        ? ""
        : "none";
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
            value: latest(
              stock?.returns_by_period?.["5"] ||
              stock?.returns
            )
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

  function turnoverProgress(turnover, avg5) {
    const a = n(turnover);
    const b = n(avg5);

    if (a === null || b === null || b <= 0) return null;
    return (a / b) * 100;
  }

  function heatColor(change) {
    const value = n(change);
    if (value === null) return "gray";

    const a = Math.abs(value);
    const level = a >= 3 ? 4 : a >= 2 ? 3 : a >= 1 ? 2 : 1;
    return `${value >= 0 ? "r" : "g"}${level}`;
  }

  function sectorChangeMap(heatmap) {
    const out = new Map();

    (heatmap?.sectors || []).forEach(sec => {
      let value = n(sec.change_pct);

      if (value === null) value = n(sec.return_pct);
      if (value === null) value = n(sec.market_return);

      out.set(sec.name, value);
    });

    return out;
  }

  /* =========================================================
     Squarified Treemap
     ========================================================= */

  function sumArea(row) {
    return row.reduce((sum, item) => sum + item._area, 0);
  }

  function worst(row, side) {
    if (!row.length || side <= 0) return Infinity;

    const sum = sumArea(row);
    const max = Math.max(...row.map(x => x._area));
    const min = Math.min(...row.map(x => x._area).filter(x => x > 0));

    if (!sum || !min) return Infinity;

    const s2 = side * side;
    const sum2 = sum * sum;

    return Math.max(
      (s2 * max) / sum2,
      sum2 / (s2 * min)
    );
  }

  function layoutRow(row, rect, output) {
    const area = sumArea(row);

    if (!row.length || area <= 0 || rect.w <= 0 || rect.h <= 0) {
      return rect;
    }

    /*
     * 正統 squarify：
     * 寬 >= 高時，row 沿著「短邊＝高」排列，
     * 因此切出左側直條；反之切上方橫條
     */
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

    if (row.length) {
      layoutRow(row, rect, output);
    }

    return output.map(x => ({
      ...x,
      x: (x.xPx / width) * 100,
      y: (x.yPx / height) * 100,
      width: (x.wPx / width) * 100,
      height: (x.hPx / height) * 100
    }));
  }

  function boxContent(item, estimated) {
    const pixelArea = Math.max(0, item.wPx * item.hPx);
    const minSide = Math.min(item.wPx, item.hPx);

    const progress = turnoverProgress(
      item.turnover,
      item.avg5_turnover
    );

    const comparison = estimated
      ? (
          progress === null
            ? "已達5日均 —"
            : `已達5日均 ${Math.round(progress)}%`
        )
      : (
          n(item.vs_avg5_pct) === null
            ? "較5日均 —"
            : `較5日均 ${fmtPct(item.vs_avg5_pct, 0)}`
        );

    /*
     * 小方塊依可用空間逐級減少文字
     */
    const showValue = pixelArea >= 1200 && minSide >= 34;
    const showAvg = pixelArea >= 3000 && minSide >= 54;
    const showMarket = pixelArea >= 5000 && minSide >= 68;

    return `
      <div class="turnover-name">${esc(item.name)}</div>

      ${
        showValue
          ? `<div class="turnover-value">成交 ${fmtYi(item.turnover)}</div>`
          : ""
      }

      ${
        showAvg
          ? `
            <div class="turnover-avg">
              5日均 ${fmtYi(item.avg5_turnover)}
            </div>
            <div class="turnover-avg">
              ${comparison}
            </div>
          `
          : ""
      }

      ${
        showMarket
          ? `
            <div class="turnover-market">
              市值 ${fmtPct(item.change)}
            </div>
          `
          : ""
      }
    `;
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

      const changes = sectorChangeMap(heatmapData);

      const items = (turnoverData?.sectors || [])
        .map(sec => ({
          ...sec,
          value: Math.max(0, Number(sec.turnover || 0)),
          change: changes.get(sec.name)
        }))
        .filter(sec => sec.value > 0)
        .sort((a, b) => b.value - a.value);

      if (!items.length) {
        g.innerHTML = `<div class="turnover-status">目前沒有成交金額資料</div>`;
        return;
      }

      /*
       * 先放 header + map shell，取得「真正 map 寬度」後再排版
       */
      const estimated = turnoverData?.estimated === true;

      g.innerHTML = `
        <div class="turnover-head">
          <div>
            <div class="turnover-head-main">族群成交金額</div>
            <div class="turnover-head-sub">
              方塊大小＝當日累積成交金額｜單位＝億元｜
              ${
                estimated
                  ? "盤中顯示已達5日均比例"
                  : "收盤後顯示較5日均增減"
              }
            </div>
          </div>

          <div class="turnover-date">
            ${esc(turnoverData?.updated_at || turnoverData?.date || "")}
          </div>
        </div>

        <div class="turnover-map" id="turnoverMap"></div>
      `;

      const map = $("#turnoverMap", g);
      if (!map) return;

      const width = Math.max(
        280,
        Math.floor(map.getBoundingClientRect().width || g.clientWidth || 360)
      );

      const height = Math.max(
        520,
        Math.floor(map.getBoundingClientRect().height || 720)
      );

      const boxes = squarify(items, width, height);

      map.innerHTML = boxes
        .map(item => {
          const progress = turnoverProgress(
            item.turnover,
            item.avg5_turnover
          );

          const comparison = estimated
            ? (
                progress === null
                  ? "已達5日均 —"
                  : `已達5日均 ${Math.round(progress)}%`
              )
            : (
                n(item.vs_avg5_pct) === null
                  ? "較5日均 —"
                  : `較5日均 ${fmtPct(item.vs_avg5_pct, 0)}`
              );

          const title = [
            item.name,
            `成交 ${fmtYi(item.turnover)}`,
            `5日均 ${fmtYi(item.avg5_turnover)}`,
            comparison,
            `市值 ${fmtPct(item.change)}`
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
              <div
                class="turnover-inner ${heatColor(item.change)}"
                title="${esc(title)}"
              >
                ${boxContent(item, estimated)}
              </div>
            </div>
          `;
        })
        .join("");
    } catch (err) {
      console.error("[turnover heatmap]", err);

      if (state.mode === "volume" && token === state.volumeRenderToken) {
        g.innerHTML = `
          <div class="turnover-status">
            成交金額資料讀取失敗
          </div>
        `;
      }
    } finally {
      state.renderingVolume = false;
    }
  }

  function restorePrice() {
    state.volumeRenderToken += 1;
    setPriceControlsVisible(true);

    const g = grid();
    if (g) {
      g.style.display = "";
    }

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
        /*
         * app.js 或其他 heatmap module 若重新畫價格版，
         * 量模式立即恢復自己的 Treemap
         */
        if (!g.querySelector(".turnover-map")) {
          renderVolume(false);
        }
        return;
      }

      clearTimeout(state.goldTimer);
      state.goldTimer = setTimeout(() => applyGold(false), 80);
    });

    state.observer.observe(g, {
      childList: true,
      subtree: true
    });
  }

  function bind() {
    injectStyle();

    /*
     * app.js 是先載入的；若熱力圖尚未 lazy render，
     * 這裡先等 #heatGrid 存在即可
     */
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

    /*
     * 手機旋轉 / 視窗尺寸改變時，
     * 重新以實際寬高做 squarified layout
     */
    window.addEventListener(
      "resize",
      () => {
        if (state.mode !== "volume") return;

        clearTimeout(state.resizeTimer);
        state.resizeTimer = setTimeout(() => renderVolume(false), 180);
      },
      { passive: true }
    );

    /*
     * refresh_controller 可能只更新 JSON，不一定發自訂事件
     * 量模式每分鐘重新讀一次；JSON 本身仍由後端約5分鐘更新
     * 不增加後端 API 呼叫
     */
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
