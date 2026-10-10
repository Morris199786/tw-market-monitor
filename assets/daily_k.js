/* Daily K charts — Taiwan stock market */
(function () {
  'use strict';

  const periods = [5, 10, 20, 60, 120, 240];
  const colors = [
    '#ffd54a',
    '#f574dd',
    '#55e4e8',
    '#f5ae7e',
    '#9e99ff',
    '#eb7582'
  ];

  const volumePeriods = [5, 20, 60];
  const volumeColors = [
    '#ffd54a',
    '#f574dd',
    '#55e4e8'
  ];

  let active = null;
  const cache = new Map();

  function movingAverage(bars, n, gaps = []) {
    let sum = 0;
    let queue = [];

    return bars.map((b, i) => {
      if (
        i &&
        gaps.some(d =>
          d > bars[i - 1].time &&
          d < b.time
        )
      ) {
        sum = 0;
        queue = [];
      }

      sum += b.close;
      queue.push(b.close);

      if (queue.length > n) {
        sum -= queue.shift();
      }

      return queue.length === n ? sum / n : null;
    });
  }

  function validBars(input) {
    if (!Array.isArray(input)) return [];

    let last = '';

    return input.filter(b => {
      const ok =
        /^\d{4}-\d{2}-\d{2}$/.test(b.time) &&
        b.time > last &&
        ['open', 'high', 'low', 'close', 'volume'].every(
          k =>
            typeof b[k] === 'number' &&
            Number.isFinite(b[k])
        ) &&
        b.low > 0 &&
        b.volume >= 0 &&
        b.low <= Math.min(b.open, b.close) &&
        b.high >= Math.max(b.open, b.close);

      if (ok) last = b.time;
      return ok;
    });
  }

  function destroy() {
    if (active) {
      active.cleanup();
      active = null;
    }
  }

  function style() {
    if (document.getElementById('dailyKStyle')) return;

    const el = document.createElement('style');
    el.id = 'dailyKStyle';

    el.textContent = `
      #dailyKHost {
        min-width: 0;
        color: #eef3ff;
        background: #101826;
        border-radius: 12px;
        padding: 6px;
        overflow: hidden;
      }

      #dailyKHost * {
        box-sizing: border-box;
      }

      #dailyKHost .dk-stock-header {
        padding: 8px 10px;
        margin-bottom: 5px;
        border: 1px solid #35445a;
        border-radius: 9px;
        background: #172337;
      }

      #dailyKHost .dk-stock-top {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 5px 10px;
      }

      #dailyKHost .dk-stock-name {
        font-size: 17px;
        font-weight: 700;
        color: #f2f6ff;
      }

      #dailyKHost .dk-stock-code {
        font-size: 12px;
        color: #a9b8ce;
        margin-left: 4px;
      }

      #dailyKHost .dk-price-row {
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 3px 9px;
        font-variant-numeric: tabular-nums;
      }

      #dailyKHost .dk-latest-price {
        font-size: 27px;
        line-height: 1.15;
        font-weight: 750;
      }

      #dailyKHost .dk-price-change {
        font-size: 15px;
        font-weight: 700;
      }

      #dailyKHost .dk-up {
        color: #ff5268;
      }

      #dailyKHost .dk-down {
        color: #43cb8b;
      }

      #dailyKHost .dk-flat {
        color: #d4deeb;
      }

      #dailyKHost .dk-quote-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 4px 7px;
        margin-top: 7px;
        padding-top: 6px;
        border-top: 1px solid #35445a;
      }

      #dailyKHost .dk-quote-item {
        display: flex;
        align-items: baseline;
        gap: 4px;
        min-width: 0;
        white-space: nowrap;
      }

      #dailyKHost .dk-quote-label {
        font-size: 11px;
        color: #9baec5;
        flex-shrink: 0;
      }

      #dailyKHost .dk-quote-value {
        font-size: 12px;
        font-weight: 650;
        font-variant-numeric: tabular-nums;
      }

      #dailyKHost .dk-quote-date {
        margin-top: 5px;
        font-size: 10px;
        color: #9baec5;
      }

      #dailyKHost .dk-info {
        display: none;
        font-size: 11px;
        line-height: 1.45;
        padding: 4px 3px;
        margin-bottom: 3px;
        color: #eef3ff;
        background: #1c2a3d;
        border-radius: 5px;
        font-variant-numeric: tabular-nums;
      }

      #dailyKHost .dk-info.visible {
        display: block;
      }

      #dailyKHost .dk-ma {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 2px 4px;
        font-size: 10px;
        line-height: 1.45;
        margin: 4px 0;
      }

      #dailyKHost .dk-ma label {
        white-space: nowrap;
        overflow: hidden;
      }

      #dailyKHost .dk-ma input {
        accent-color: currentColor;
        vertical-align: middle;
        margin: 0 2px 0 0;
        width: 11px;
        height: 11px;
      }

      #dailyKHost .dk-tools {
        display: grid;
        grid-template-columns:
          1.5fr 1.2fr
          repeat(5, minmax(0, 0.65fr));
        gap: 3px;
        margin: 5px 0 2px;
      }

      #dailyKHost button {
        font: inherit;
        font-size: 11px;
        min-height: 30px;
        border: 1px solid #536078;
        border-radius: 6px;
        padding: 4px 3px;
        background: #202d40;
        color: #fff;
        cursor: pointer;
      }

      #dailyKHost button[aria-pressed="true"] {
        background: #315b88;
        border-color: #8ac4ff;
      }

      #dailyKHost canvas {
        display: block;
        width: 100%;
        height: 350px;
        touch-action: none;
        outline: none;
      }

      #dailyKHost canvas:focus-visible {
        outline: 2px solid #80c9ff;
      }

      #dailyKHost .dk-note {
        font-size: 10px;
        line-height: 1.4;
        color: #b2bfd1;
        margin-top: 3px;
      }

      #dailyKHost .dk-warning {
        color: #ffdc88;
        font-size: 13px;
      }

      #stockDetailBody:has(#dailyKHost)
      .stock-detail-periods {
        display: none;
      }

      #stockDetailBody .stock-detail-tabs {
        grid-template-columns:
          repeat(3, minmax(0, 1fr));
      }

      @media (max-width: 480px) {
        #stockDetailBody:has(#dailyKHost)
        .stock-detail-card {
          padding: 3px;
        }

        #dailyKHost {
          padding: 5px;
        }

        #dailyKHost canvas {
          height: 350px;
        }

        #dailyKHost .dk-stock-header {
          padding: 7px 8px;
        }

        #dailyKHost .dk-latest-price {
          font-size: 25px;
        }

        #dailyKHost .dk-price-change {
          font-size: 14px;
        }

        #dailyKHost .dk-tools {
          gap: 3px;
        }

        #dailyKHost button {
          font-size: 10px;
          padding: 3px 2px;
        }
      }
    `;

    document.head.appendChild(el);
  }

  function fmt(v, d = 2) {
    if (v == null || !Number.isFinite(v)) {
      return '—';
    }

    return v.toLocaleString('zh-TW', {
      minimumFractionDigits: d,
      maximumFractionDigits: d
    });
  }

  function priceFmt(v) {
    if (v == null || !Number.isFinite(v)) {
      return '—';
    }

    return v.toLocaleString('zh-TW', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2
    });
  }

  function resolveStockName(ticker, metadata, host) {
    const candidates = [
      metadata.name,
      metadata.stock_name,
      metadata.company_name,
      metadata.company,
      metadata.short_name,
      metadata.shortName,
      metadata.longName,
      host.dataset.stockName,
      host.dataset.name
    ];

    const name = candidates.find(
      x => typeof x === 'string' && x.trim()
    );

    return name ? name.trim() : String(ticker);
  }

  function renderQuote(host, ticker, metadata, bars) {
    const latest = bars[bars.length - 1];
    const previous =
      bars.length > 1 ? bars[bars.length - 2] : null;

    const change = previous
      ? latest.close - previous.close
      : null;

    const changePct =
      previous && previous.close !== 0
        ? change / previous.close * 100
        : null;

    const direction =
      change == null
        ? 'dk-flat'
        : change > 0
          ? 'dk-up'
          : change < 0
            ? 'dk-down'
            : 'dk-flat';

    const arrow =
      change == null
        ? ''
        : change > 0
          ? '▲'
          : change < 0
            ? '▼'
            : '—';

    const changeText =
      change == null
        ? '漲跌 —'
        : `${arrow} ${priceFmt(Math.abs(change))}`;

    const pctText =
      changePct == null
        ? '—'
        : `${changePct > 0 ? '+' : ''}${fmt(changePct, 2)}%`;

    const stockName =
      resolveStockName(ticker, metadata, host);

    const header = host.querySelector('.dk-stock-header');

    const setText = (selector, value) => {
      const element = header.querySelector(selector);
      if (element) element.textContent = value;
    };

    setText('.dk-stock-name', stockName);
    setText('.dk-stock-code', ticker);

    const priceEl = header.querySelector('.dk-latest-price');
    const changeEl = header.querySelector('.dk-price-change');

    priceEl.textContent = priceFmt(latest.close);
    changeEl.textContent = `${changeText}　${pctText}`;

    priceEl.className = `dk-latest-price ${direction}`;
    changeEl.className = `dk-price-change ${direction}`;

    setText('[data-quote="open"]', priceFmt(latest.open));
    setText('[data-quote="high"]', priceFmt(latest.high));
    setText('[data-quote="low"]', priceFmt(latest.low));
    setText('[data-quote="close"]', priceFmt(latest.close));

    setText(
      '[data-quote="volume"]',
      `${fmt(latest.volume / 1000, 0)} 張`
    );

    setText(
      '[data-quote="previous"]',
      previous ? priceFmt(previous.close) : '—'
    );

    setText(
      '.dk-quote-date',
      `行情日期 ${latest.time}｜收盤日 K，非即時報價`
    );
  }

  async function mount(host, ticker) {
    destroy();
    style();

    const token = {
      dead: false,
      cleanup: () => {
        token.dead = true;
      }
    };

    active = token;

    host.innerHTML =
      '<div class="dk-note">載入日 K 行情…</div>';

    try {
      const cached = cache.get(ticker);

      let result =
        cached && Date.now() - cached.at < 300000
          ? cached.data
          : null;

      if (!result) {
        const response = await fetch(
          './data/daily_k/' +
          encodeURIComponent(ticker) +
          '.json?v=' +
          new Date().toISOString().slice(0, 10),
          { cache: 'no-cache' }
        );

        if (!response.ok) {
          throw new Error('行情檔尚未建立或讀取失敗');
        }

        result = await response.json();

        cache.set(ticker, {
          at: Date.now(),
          data: result
        });
      }

      if (token.dead || !host.isConnected) return;

      if (String(result.ticker) !== String(ticker)) {
        throw new Error('股票代號不符');
      }

      const bars = validBars(result.bars);

      if (
        !bars.length ||
        bars.length !== result.bars.length
      ) {
        throw new Error('開高低收資料不完整');
      }

      create(host, ticker, bars, result, token);

    } catch (e) {
      if (!token.dead && host.isConnected) {
        host.replaceChildren();

        const p = document.createElement('p');
        p.className = 'dk-warning';

        p.textContent =
          '日 K 暫時無法顯示：' +
          e.message +
          '，請確認 Daily K charts 已執行成功';

        host.append(p);
      }
    }
  }

  function create(host, ticker, bars, metadata, token) {
    const ma = Object.fromEntries(
      periods.map(n => [
        n,
        movingAverage(
          bars,
          n,
          metadata.missing_dates || []
        )
      ])
    );

    const volumeBars = bars.map(b => ({
      ...b,
      close: b.volume / 1000
    }));

    const vma = Object.fromEntries(
      volumePeriods.map(n => [
        n,
        movingAverage(
          volumeBars,
          n,
          metadata.missing_dates || []
        )
      ])
    );

    const enabled = new Set(periods);

    let count = Math.min(65, bars.length);
    let end = bars.length;
    let selected = bars.length - 1;
    let crossY = null;
    let mode = 'inspect';
    let inspecting = false;

    let size = {
      w: 400,
      h: 350
    };

    let frame = 0;
    const pointers = new Map();

    let drag = null;
    let pinch = null;

    host.innerHTML = `
      <div class="dk-stock-header">
        <div class="dk-stock-top">
          <div>
            <span class="dk-stock-name"></span>
            <span class="dk-stock-code"></span>
          </div>

          <div class="dk-price-row">
            <span class="dk-latest-price"></span>
            <span class="dk-price-change"></span>
          </div>
        </div>

        <div class="dk-quote-grid">
          <div class="dk-quote-item">
            <span class="dk-quote-label">開</span>
            <span class="dk-quote-value" data-quote="open"></span>
          </div>

          <div class="dk-quote-item">
            <span class="dk-quote-label">高</span>
            <span class="dk-quote-value" data-quote="high"></span>
          </div>

          <div class="dk-quote-item">
            <span class="dk-quote-label">低</span>
            <span class="dk-quote-value" data-quote="low"></span>
          </div>

          <div class="dk-quote-item">
            <span class="dk-quote-label">收</span>
            <span class="dk-quote-value" data-quote="close"></span>
          </div>

          <div class="dk-quote-item">
            <span class="dk-quote-label">量</span>
            <span class="dk-quote-value" data-quote="volume"></span>
          </div>

          <div class="dk-quote-item">
            <span class="dk-quote-label">前收</span>
            <span class="dk-quote-value" data-quote="previous"></span>
          </div>
        </div>

        <div class="dk-quote-date"></div>
      </div>

      <div class="dk-info" aria-live="off"></div>

      <div class="dk-ma">
        ${periods.map((n, i) => `
          <label style="color:${colors[i]}">
            <input
              type="checkbox"
              data-ma="${n}"
              checked
            >
            MA${n}
            <span data-value="${n}">—</span>
          </label>
        `).join('')}
      </div>

      <div class="dk-tools">
        <button data-tool="inspect" aria-pressed="true">
          十字線
        </button>

        <button data-tool="pan" aria-pressed="false">
          平移
        </button>

        <button data-tool="in" aria-label="放大日K">
          ＋
        </button>

        <button data-tool="out" aria-label="縮小日K">
          －
        </button>

        <button data-tool="left" aria-label="較早行情">
          ◀
        </button>

        <button data-tool="right" aria-label="較新行情">
          ▶
        </button>

        <button data-tool="reset">
          最新
        </button>
      </div>

      <canvas
        tabindex="0"
        aria-label="日K及成交量，十字查價、縮放、平移"
      ></canvas>

      <div class="dk-note"></div>
    `;

    renderQuote(host, ticker, metadata, bars);

    const info = host.querySelector('.dk-info');
    const note = host.querySelector('.dk-note');

    note.textContent =
      `資料截至 ${bars.at(-1).time}` +
      `｜${metadata.source || 'Yahoo Finance'}` +
      `｜成交量：張`;

    const canvas = host.querySelector('canvas');
    const ctx = canvas.getContext('2d');

    function bounds() {
      count = Math.max(
        Math.min(10, bars.length),
        Math.min(bars.length, Math.round(count))
      );

      end = Math.max(
        count,
        Math.min(bars.length, Math.round(end))
      );
    }

    function schedule() {
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          draw();
        });
      }
    }

    function niceStep(v) {
      if (!(v > 0)) return 1;

      const exp = Math.pow(
        10,
        Math.floor(Math.log10(v))
      );

      const x = v / exp;

      return (
        x <= 1 ? 1 :
        x <= 2 ? 2 :
        x <= 2.5 ? 2.5 :
        x <= 5 ? 5 : 10
      ) * exp;
    }

    function geometry() {
      const left = 7;
      const right = size.w - 54;
      const top = 10;

      const bottom = Math.round(size.h * 0.68);
      const vtop = bottom + 27;
      const vbottom = size.h - 23;

      const start = end - count;
      const visible = bars.slice(start, end);

      let lo = Math.min(...visible.map(b => b.low));
      let hi = Math.max(...visible.map(b => b.high));

      for (const n of enabled) {
        for (let i = start; i < end; i++) {
          const v = ma[n][i];

          if (v != null) {
            lo = Math.min(lo, v);
            hi = Math.max(hi, v);
          }
        }
      }

      const pad = Math.max(
        (hi - lo) * 0.06,
        hi * 0.003,
        0.01
      );

      lo = Math.max(0, lo - pad);
      hi += pad;

      const tick = niceStep((hi - lo) / 5);

      lo = Math.max(
        0,
        Math.floor(lo / tick) * tick
      );

      hi = Math.ceil(hi / tick) * tick;

      const maxVol = Math.max(
        1,
        ...visible.map(b => b.volume / 1000),
        ...volumePeriods.flatMap(n =>
          vma[n]
            .slice(start, end)
            .filter(Number.isFinite)
        )
      );

      return {
        left,
        right,
        top,
        bottom,
        vtop,
        vbottom,
        start,
        lo,
        hi,
        step: (right - left) / count,
        maxVol,
        tick
      };
    }

    function draw() {
      if (token.dead || !host.isConnected) return;

      bounds();

      const g = geometry();

      const {
        left,
        right,
        top,
        bottom,
        vtop,
        vbottom,
        start,
        lo,
        hi,
        step
      } = g;

      ctx.clearRect(0, 0, size.w, size.h);

      ctx.fillStyle = '#101826';
      ctx.fillRect(0, 0, size.w, size.h);

      ctx.font = '11px system-ui';
      ctx.textBaseline = 'middle';

      const px = i =>
        left + (i - start + 0.5) * step;

      const py = v =>
        bottom -
        (v - lo) / (hi - lo) *
        (bottom - top);

      const vy = v =>
        vbottom -
        v / g.maxVol *
        (vbottom - vtop);

      ctx.strokeStyle = '#334052';
      ctx.fillStyle = '#b2bfd1';
      ctx.lineWidth = 1;

      for (
        let v = Math.ceil(lo / g.tick) * g.tick;
        v <= hi + g.tick * 0.001;
        v += g.tick
      ) {
        const y = py(v);

        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.stroke();

        ctx.fillText(fmt(v, 0), right + 4, y);
      }

      ctx.fillText('成交量（張）', left, vtop - 10);

      ctx.fillText(
        fmt(g.maxVol, 0),
        right + 3,
        vtop
      );

      ctx.save();
      ctx.beginPath();

      ctx.rect(
        left,
        top,
        right - left,
        vbottom - top
      );

      ctx.clip();

      for (let i = start; i < end; i++) {
        const b = bars[i];
        const x = px(i);

        const color =
          b.close >= b.open
            ? '#ff485c'
            : '#45c787';

        const width = Math.max(
          2,
          Math.min(step * 0.82, 13)
        );

        ctx.strokeStyle = color;
        ctx.fillStyle = color;

        ctx.lineWidth = Math.max(
          1,
          Math.min(1.5, step * 0.18)
        );

        ctx.beginPath();
        ctx.moveTo(x, py(b.high));
        ctx.lineTo(x, py(b.low));
        ctx.stroke();

        ctx.fillRect(
          x - width / 2,
          Math.min(py(b.open), py(b.close)),
          width,
          Math.max(
            1,
            Math.abs(
              py(b.open) - py(b.close)
            )
          )
        );

        ctx.fillRect(
          x - width / 2,
          vy(b.volume / 1000),
          width,
          vbottom - vy(b.volume / 1000)
        );
      }

      periods.forEach((n, j) => {
        if (!enabled.has(n)) return;

        ctx.strokeStyle = colors[j];
        ctx.lineWidth = n <= 20 ? 1.8 : 1.45;
        ctx.beginPath();

        let started = false;

        for (let i = start; i < end; i++) {
          if (ma[n][i] == null) {
            started = false;
            continue;
          }

          if (!started) {
            ctx.moveTo(px(i), py(ma[n][i]));
            started = true;
          } else {
            ctx.lineTo(px(i), py(ma[n][i]));
          }
        }

        ctx.stroke();
      });

      volumePeriods.forEach((n, j) => {
        ctx.strokeStyle = volumeColors[j];
        ctx.lineWidth = 1.4;
        ctx.beginPath();

        let started = false;

        for (let i = start; i < end; i++) {
          if (vma[n][i] == null) {
            started = false;
            continue;
          }

          if (!started) {
            ctx.moveTo(px(i), vy(vma[n][i]));
            started = true;
          } else {
            ctx.lineTo(px(i), vy(vma[n][i]));
          }
        }

        ctx.stroke();
      });

      ctx.restore();

      ctx.fillStyle = '#b2bfd1';
      ctx.textAlign = 'center';

      for (let j = 0; j < 4; j++) {
        const i = Math.min(
          end - 1,
          start + Math.round((count - 1) * j / 3)
        );

        ctx.fillText(
          bars[i].time.slice(5),
          px(i),
          size.h - 10
        );
      }

      ctx.textAlign = 'left';

      if (
        inspecting &&
        selected >= start &&
        selected < end
      ) {
        const b = bars[selected];
        const x = px(selected);

        const cy =
          crossY == null
            ? py(b.close)
            : Math.max(top, Math.min(vbottom, crossY));

        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);

        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, vbottom);
        ctx.moveTo(left, cy);
        ctx.lineTo(right, cy);
        ctx.stroke();

        ctx.setLineDash([]);

        const label =
          cy <= bottom
            ? fmt(
                hi -
                (cy - top) /
                (bottom - top) *
                (hi - lo),
                0
              )
            : cy >= vtop
              ? fmt(
                  (vbottom - cy) /
                  (vbottom - vtop) *
                  g.maxVol,
                  0
                )
              : '';

        if (label) {
          ctx.font = '11px system-ui';

          const lw = Math.max(
            54,
            ctx.measureText(label).width + 9
          );

          ctx.fillStyle = '#edf3ff';
          ctx.fillRect(right, cy - 9, lw, 18);

          ctx.fillStyle = '#101826';
          ctx.fillText(label, right + 3, cy);
        }

        ctx.fillStyle = '#edf3ff';

        const tx = Math.max(
          0,
          Math.min(size.w - 90, x - 45)
        );

        ctx.fillRect(tx, size.h - 21, 90, 21);

        ctx.fillStyle = '#101826';
        ctx.fillText(
          b.time,
          tx + 3,
          size.h - 10
        );
      }

      const b = bars[selected];

      if (inspecting) {
        info.classList.add('visible');

        info.textContent =
          `${b.time}　` +
          `開 ${fmt(b.open)}　` +
          `高 ${fmt(b.high)}　` +
          `低 ${fmt(b.low)}　` +
          `收 ${fmt(b.close)}　` +
          `量 ${fmt(b.volume / 1000, 0)} 張`;
      } else {
        info.classList.remove('visible');
      }

      periods.forEach(n => {
        host.querySelector(
          `[data-value="${n}"]`
        ).textContent = fmt(ma[n][selected]);
      });
    }

    function zoom(factor, anchor = 0.5) {
      const old = count;
      const start = end - count;
      const pivot = start + old * anchor;

      count = Math.max(
        Math.min(10, bars.length),
        Math.min(
          bars.length,
          Math.round(old * factor)
        )
      );

      end = Math.round(
        pivot + count * (1 - anchor)
      );

      bounds();
      schedule();
    }

    const local = e => {
      const r = canvas.getBoundingClientRect();

      return {
        x: e.clientX - r.left,
        y: e.clientY - r.top
      };
    };

    function inspect(p) {
      const g = geometry();

      selected = Math.max(
        g.start,
        Math.min(
          end - 1,
          g.start +
          Math.floor((p.x - g.left) / g.step)
        )
      );

      crossY = p.y;
      inspecting = true;

      schedule();
    }

    canvas.onpointerdown = e => {
      e.preventDefault();
      canvas.setPointerCapture(e.pointerId);

      const p = local(e);
      pointers.set(e.pointerId, p);

      if (pointers.size === 1) {
        drag = {
          x: p.x,
          end
        };

        if (mode === 'inspect') {
          inspect(p);
        }
      }

      if (pointers.size === 2) {
        const a = [...pointers.values()];

        pinch = {
          distance: Math.hypot(
            a[0].x - a[1].x,
            a[0].y - a[1].y
          ),
          count,
          end
        };
      }
    };

    canvas.onpointermove = e => {
      const p = local(e);

      if (pointers.has(e.pointerId)) {
        pointers.set(e.pointerId, p);
      }

      if (
        pointers.size >= 2 &&
        pinch
      ) {
        const a = [...pointers.values()];

        const distance = Math.hypot(
          a[0].x - a[1].x,
          a[0].y - a[1].y
        );

        if (distance > 8) {
          count = pinch.count;
          end = pinch.end;

          zoom(
            pinch.distance / distance,
            (a[0].x + a[1].x) /
            2 / size.w
          );
        }

        return;
      }

      if (
        pointers.size === 1 &&
        mode === 'pan' &&
        drag
      ) {
        end =
          drag.end -
          Math.round(
            (p.x - drag.x) /
            geometry().step
          );

        bounds();
        crossY = null;
        inspecting = false;

        schedule();

      } else if (
        mode === 'inspect' &&
        (
          pointers.size === 1 ||
          e.pointerType === 'mouse'
        )
      ) {
        inspect(p);
      }
    };

    const release = e => {
      pointers.delete(e.pointerId);

      pinch = null;
      drag = null;

      if (pointers.size === 1) {
        const p = [...pointers.values()][0];

        drag = {
          x: p.x,
          end
        };
      }
    };

    canvas.onpointerup = release;
    canvas.onpointercancel = release;

    const wheel = e => {
      e.preventDefault();

      zoom(
        e.deltaY > 0 ? 1.15 : 1 / 1.15,
        Math.max(
          0,
          Math.min(1, local(e).x / size.w)
        )
      );
    };

    canvas.addEventListener(
      'wheel',
      wheel,
      { passive: false }
    );

    canvas.onkeydown = e => {
      if (
        [
          'ArrowLeft',
          'ArrowRight',
          '+',
          '-',
          '='
        ].includes(e.key)
      ) {
        e.preventDefault();

        if (
          e.key === '+' ||
          e.key === '='
        ) {
          zoom(0.8);

        } else if (e.key === '-') {
          zoom(1.25);

        } else {
          selected = Math.max(
            0,
            Math.min(
              bars.length - 1,
              selected +
              (e.key === 'ArrowLeft' ? -1 : 1)
            )
          );

          if (selected < end - count) {
            end = selected + count;
          }

          if (selected >= end) {
            end = selected + 1;
          }

          crossY = null;
          inspecting = true;

          schedule();
        }
      }
    };

    host.querySelectorAll(
      '[data-tool]'
    ).forEach(button => {
      button.onclick = () => {
        const t = button.dataset.tool;

        if (
          t === 'inspect' ||
          t === 'pan'
        ) {
          mode = t;

          host.querySelectorAll(
            '[aria-pressed]'
          ).forEach(x => {
            x.setAttribute(
              'aria-pressed',
              String(x.dataset.tool === t)
            );
          });

        } else if (t === 'in') {
          zoom(0.8);

        } else if (t === 'out') {
          zoom(1.25);

        } else {
          if (t === 'reset') {
            count = Math.min(65, bars.length);
            end = bars.length;
            selected = bars.length - 1;
            inspecting = false;

          } else {
            end +=
              (t === 'left' ? -1 : 1) *
              Math.max(1, Math.round(count * 0.5));

            inspecting = false;
          }

          bounds();
          crossY = null;

          schedule();
        }
      };
    });

    host.querySelectorAll(
      '[data-ma]'
    ).forEach(button => {
      button.onchange = () => {
        const n = Number(button.dataset.ma);

        if (button.checked) {
          enabled.add(n);
        } else {
          enabled.delete(n);
        }

        schedule();
      };
    });

    const resize = new ResizeObserver(() => {
      size = {
        w: Math.max(220, canvas.clientWidth),
        h: 350
      };

      const dpr = window.devicePixelRatio || 1;

      canvas.width = Math.round(size.w * dpr);
      canvas.height = Math.round(size.h * dpr);

      ctx.setTransform(
        dpr,
        0,
        0,
        dpr,
        0,
        0
      );

      schedule();
    });

    resize.observe(canvas);

    token.cleanup = () => {
      token.dead = true;

      resize.disconnect();

      if (frame) {
        cancelAnimationFrame(frame);
      }

      canvas.removeEventListener('wheel', wheel);
      pointers.clear();
    };
  }

  window.DailyK = {
    mount,
    destroy,
    movingAverage,
    validBars
  };
})();
