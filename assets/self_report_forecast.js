/* 台股市場監測｜自結預測獨立頁（不觸發排程或 API） */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);

  const esc = x =>
    String(x ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[c]));

  let active = false;
  let lastFetch = 0;
  let data = null;

  function install() {
    const tabs = $('#earningsModeTabs');
    const page = $('#selfReports');

    if (!tabs || !page || $('#srForecastTab')) return;

    const btn = document.createElement('button');

    btn.type = 'button';
    btn.className = 'earnings-mode';
    btn.id = 'srForecastTab';
    btn.textContent = '盤後可能公布自結';

    const upcoming = tabs.querySelector(
      '[data-earnings-mode="upcoming"]'
    );

    tabs.insertBefore(btn, upcoming || null);

    const panel = document.createElement('section');

    panel.id = 'srForecastPanel';
    panel.className = 'sr-forecast';
    panel.hidden = true;

    panel.innerHTML = `
      <div class="sr-forecast-head">
        <div>
          <h2>盤後可能公布自結</h2>
          <p>
            注意交易觸發型自結｜
            上市、上櫃分別預測｜
            上市、上櫃各 0～10 檔
          </p>
        </div>

        <span id="srForecastDate">尚未更新</span>
      </div>

      <div
        id="srForecastStatus"
        class="earnings-status">
      </div>

      <div id="srForecastPicks"></div>

      <details class="sr-forecast-history">

        <summary>
          正式預測績效（10/21 起）
          <small>點擊展開</small>
        </summary>

        <div id="srForecastMetrics"></div>

        <p class="sr-forecast-note">

          <b>命中率（Precision）</b>
          ＝命中檔數 ÷ 推薦檔數
          <br>

          → 推薦的股票，有多少真的公布自結。

          <br>

          <b>召回率（Recall）</b>
          ＝命中檔數 ÷ 實際公布檔數
          <br>

          → 真正公布自結的股票，有多少被提前預測到。

          <br>

          <b>統計範圍：</b>
          僅計算注意交易觸發的自結，
          不含自主公告及季報。

        </p>

      </details>
    `;

    const quarterly = $('#quarterlyEarningsPanel');

    (quarterly || tabs).insertAdjacentElement(
      'afterend',
      panel
    );

    btn.addEventListener('click', () => {
      active = true;

      tabs.querySelectorAll('.earnings-mode').forEach(x => {
        x.classList.toggle('active', x === btn);
      });

      const q = $('#quarterlyEarningsPanel');

      if (q) {
        q.hidden = true;
        q.style.setProperty(
          'display',
          'none',
          'important'
        );
      }

      [
        '#selfWeekBadge',
        '#selfWeekTabs',
        '.self-report-search-card',
        '#selfStatus',
        '#selfReportCards'
      ].forEach(s => {
        const e = $(s, page);

        if (e) {
          e.hidden = true;
          e.style.setProperty(
            'display',
            'none',
            'important'
          );
        }
      });

      panel.hidden = false;
      panel.style.display = 'block';

      render();
    });

    tabs.querySelectorAll(
      '[data-earnings-mode]'
    ).forEach(x => {
      x.addEventListener('click', () => {
        active = false;

        btn.classList.remove('active');

        panel.hidden = true;
        panel.style.display = 'none';
      });
    });
  }

  async function render() {
    if (!active) return;

    const status = $('#srForecastStatus');
    const picks = $('#srForecastPicks');
    const metrics = $('#srForecastMetrics');

    if (!status || !picks || !metrics) return;

    try {
      if (!data || Date.now() - lastFetch > 60000) {
        const r = await fetch(
          './data/self_report_forecast.json?v=' + Date.now(),
          {
            cache: 'no-store'
          }
        );

        if (!r.ok) {
          throw Error('HTTP ' + r.status);
        }

        data = await r.json();
        lastFetch = Date.now();
      }

      if (!active) return;

      $('#srForecastDate').textContent =
        data.prediction_date
          ? '預測 ' + data.prediction_date
          : '尚未執行預測';

      const a = Array.isArray(data.picks)
        ? data.picks
        : [];

      status.textContent =
        '資料更新：' +
        (data.updated_at || '尚未更新') +
        '｜' +
        (
          data.prediction_date
            ? '推薦 ' + a.length + ' 檔'
            : '尚未設定自動排程'
        );

      if (!data.prediction_date) {
        picks.innerHTML = `
          <div class="earnings-empty">
            尚未執行最新預測。
            自動更新時間尚未設定，
            不會自行抓取注意交易資料。
          </div>
        `;
      } else if (!a.length) {
        picks.innerHTML = `
          <div class="earnings-empty">
            本次符合條件 0 檔，
            不強制湊滿10檔。
          </div>
        `;
      } else {
        picks.innerHTML = a.map((p, i) => `
          <article class="sr-forecast-pick">

            <div>
              <span>${i + 1}</span>

              <strong>
                ${esc(p.name || p.ticker)}
              </strong>

              <small>
                ${esc(p.ticker)}
                ·
                ${p.market === 'tpex' ? '上櫃' : '上市'}
              </small>
            </div>

          </article>
        `).join('');
      }

      /*
       * 正式績效
       *
       * 僅使用後端輸出的 backtest 欄位。
       * 後端必須確保此欄位只包含
       * 2026/10/21 起的正式預測結果。
       *
       * 不將歷史回測混入正式績效。
       */

      const m = data.backtest || {};

      const fmt = v =>
        typeof v === 'number'
          ? (v * 100).toFixed(1) + '%'
          : '—';

      const row = (name, x) => `
        <tr>
          <th>${name}</th>

          <td>
            ${x?.predictions ?? '—'}
          </td>

          <td>
            ${x?.hits ?? '—'}
          </td>

          <td>
            ${fmt(x?.precision)}
          </td>

          <td>
            ${fmt(x?.recall)}
          </td>
        </tr>
      `;

      metrics.innerHTML = `
        <p>
          正式績效期間：
          ${esc(m.start || '2026-10-21')}
          ～
          ${esc(m.end || '待結算')}

          （僅已完成全市場公告核對之日期）
        </p>

        <div class="sr-forecast-scroll">

          <table>

            <thead>
              <tr>
                <th>市場</th>
                <th>推薦</th>
                <th>命中</th>
                <th>命中率</th>
                <th>召回率</th>
              </tr>
            </thead>

            <tbody>
              ${row('上市', m.twse)}
              ${row('上櫃', m.tpex)}
            </tbody>

          </table>

        </div>
      `;

    } catch (e) {
      status.textContent = '資料讀取失敗';

      picks.innerHTML = `
        <div class="earnings-empty">
          目前沒有可用的預測資料
        </div>
      `;

      console.error(e);
    }
  }

  function boot() {
    install();

    let n = 0;

    const timer = setInterval(() => {
      install();

      if ($('#srForecastTab') || ++n > 30) {
        clearInterval(timer);
      }
    }, 300);
  }

  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      boot,
      { once: true }
    );
  } else {
    boot();
  }

})();
