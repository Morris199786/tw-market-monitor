/* Broker EPS comparison: zero API; only forecasts earlier than or on actual announcement. */
(() => {
  'use strict';

  const esc = x => String(x ?? '').replace(
    /[&<>"']/g,
    c => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[c])
  );

  const n = x =>
    x === null || x === undefined || x === ''
      ? null
      : (Number.isFinite(Number(x)) ? Number(x) : null);

  const cleanDate = x => String(x || '').slice(0, 10);

  const quarter = m => {
    const z = /^(20\d{2})-(0[1-9]|1[0-2])$/.exec(m || '');
    return z
      ? `${z[1]}-Q${Math.ceil(+z[2] / 3)}`
      : '';
  };

  const key = (ticker, period) => `${ticker}|${period}`;

  let forecasts = new Map();
  let actuals = new Map();
  let loading = null;
  let timer = 0;

  function addActual(x, period, kind, value) {
    if (
      !/^\d{4}$/.test(String(x.ticker)) ||
      !/^20\d{2}-Q[1-4]$/.test(period) ||
      n(value) === null
    ) {
      return;
    }

    const k = key(x.ticker, period);

    const row = {
      ...x,
      kind,
      period,
      actual: n(value)
    };

    if (!actuals.has(k)) {
      actuals.set(k, []);
    }

    actuals.get(k).push(row);
  }

  async function load() {
    if (loading) return loading;

    loading = Promise.all(
      [
        'broker_eps_forecasts.json',
        'self_reports.json',
        'quarterly_earnings.json'
      ].map(async file => {
        const res = await fetch(
          `./data/${file}?v=${Math.floor(Date.now() / 60000)}`,
          { cache: 'no-store' }
        );

        if (!res.ok) {
          throw Error(`${file}: ${res.status}`);
        }

        return res.json();
      })
    ).then(([f, s, e]) => {
      forecasts = new Map();
      actuals = new Map();

      for (const x of f.items || []) {
        if (
          !/^\d{4}$/.test(String(x.ticker)) ||
          !/^20\d{2}-Q[1-4]$/.test(x.period || '') ||
          !cleanDate(x.report_date) ||
          n(x.eps) === null ||
          n(x.eps) === 0 ||
          !x.report_id
        ) {
          continue;
        }

        const k = key(x.ticker, x.period);

        if (!forecasts.has(k)) {
          forecasts.set(k, []);
        }

        forecasts.get(k).push(x);
      }

      for (const x of s.items || []) {
        addActual(
          x,
          quarter(x.monthly_period),
          'monthly',
          x.monthly_eps
        );
      }

      for (const x of e.reports || []) {
        addActual(
          x,
          x.period,
          'quarter',
          x.eps
        );
      }

      render();
    })
      .catch(err => console.warn('[Broker EPS]', err))
      .finally(() => {
        loading = null;
      });

    return loading;
  }

  function match(ticker, kind, day, visibleValue) {
    const candidates = [];

    for (const [k, items] of actuals) {
      if (!k.startsWith(`${ticker}|`)) continue;

      for (const x of items) {
        if (
          x.kind !== kind ||
          !cleanDate(x.publish_date) ||
          (day && cleanDate(x.publish_date) !== day)
        ) {
          continue;
        }

        if (
          visibleValue !== null &&
          Math.abs(x.actual - visibleValue) > 0.015
        ) {
          continue;
        }

        candidates.push(x);
      }
    }

    if (candidates.length !== 1) {
      return null;
    }

    const x = candidates[0];
    const seen = new Set();

    const rows = (
      forecasts.get(key(ticker, x.period)) || []
    ).filter(r => {

      // 同一天的券商報告也納入配對。
      // 只有報告日期晚於 EPS 公告日期才排除。
      if (
        cleanDate(r.report_date) > cleanDate(x.publish_date) ||
        !r.report_id
      ) {
        return false;
      }

      const id = String(r.report_id) + '|' + x.period;

      if (seen.has(id)) {
        return false;
      }

      seen.add(id);
      return true;

    }).sort(
      (a, b) =>
        cleanDate(b.report_date).localeCompare(
          cleanDate(a.report_date)
        )
    );

    return { x, rows };
  }

  const numericText = el => {
    const m = String(el?.textContent || '').match(
      /-?\d[\d,]*(?:\.\d+)?\s*元/
    );

    return m
      ? Number(m[0].replace(/[,元\s]/g, ''))
      : null;
  };

  const dateIn = s =>
    String(s || '')
      .match(/20\d{2}[-\/]\d{2}[-\/]\d{2}/)?.[0]
      ?.replaceAll('/', '-') || '';

  function tickerIn(card) {
    const t = card.querySelector('[data-ticker]')?.dataset.ticker;

    if (/^\d{4}$/.test(t || '')) {
      return t;
    }

    return (
      card.textContent || ''
    ).match(
      /(?:^|\s|\u00a0)(\d{4})(?=\s|\u00a0|$)/
    )?.[1] || '';
  }

  function paint(metric, result) {
    const old = metric.querySelector(
      ':scope > .broker-eps-comparison'
    );

    if (!result?.rows.length) {
      old?.remove();
      return;
    }

    const { x, rows } = result;

    const sig = JSON.stringify([
      x.ticker,
      x.period,
      x.actual,
      x.publish_date,
      rows.map(r => [r.report_id, r.eps])
    ]);

    if (old?.dataset.signature === sig) {
      return;
    }

    const panel = old || document.createElement('div');

    panel.className = 'broker-eps-comparison';
    panel.dataset.signature = sig;

    panel.innerHTML = rows.map(r => {
      const pct = x.actual / Number(r.eps) * 100;

      if (!Number.isFinite(pct)) {
        return '';
      }

      const label =
        x.kind === 'monthly'
          ? '單月／季預估比'
          : '季度達成率';

      return `
        <div
          class="broker-eps-entry"
          title="${esc(x.period)} 券商季度預估 ${Number(r.eps).toFixed(2)} 元；實際 EPS ${x.actual.toFixed(2)} 元"
        >
          <span>
            ${esc(cleanDate(r.report_date).slice(5).replace('-', '/'))}
          </span>
          <span>
            ${esc(r.broker)}
          </span>
          <span class="broker-eps-rate">
            ${label} ${pct.toFixed(1)}%
          </span>
        </div>
      `;
    }).join('');

    if (!old) {
      metric.appendChild(panel);
    }
  }

  function render() {
    const root = document.querySelector('#selfReportCards');

    if (root) {
      for (const card of root.children) {
        const ticker = tickerIn(card);

        const day = dateIn(
          card.querySelector('time')?.getAttribute('datetime') ||
          card.textContent
        );

        if (!ticker || !day) {
          continue;
        }

        const candidates = [
          ...card.querySelectorAll('div,section,article')
        ]
          .filter(
            el =>
              el.children.length <= 4 &&
              /當月\s*EPS|單月\s*EPS/.test(
                el.textContent || ''
              ) &&
              /\d/.test(el.textContent || '')
          )
          .sort(
            (a, b) =>
              a.textContent.length - b.textContent.length
          );

        const metric = candidates.find(
          el => numericText(el) !== null
        );

        if (metric) {
          paint(
            metric,
            match(
              ticker,
              'monthly',
              day,
              numericText(metric)
            )
          );
        }
      }
    }

    document.querySelectorAll(
      '#quarterlyEarningsCards .earnings-report-row'
    ).forEach(card => {
      const ticker = card
        .querySelector('.earnings-company span')
        ?.textContent.trim() || '';

      const metric = card.querySelector(
        '.earnings-detail.four > div:first-child'
      );

      const day = dateIn(
        card.querySelector('.earnings-period')?.textContent
      );

      if (ticker && metric && day) {
        paint(
          metric,
          match(
            ticker,
            'quarter',
            day,
            numericText(metric.querySelector('b'))
          )
        );
      }
    });
  }

  function init() {
    const page = document.querySelector('#selfReports');

    if (!page) {
      return;
    }

    new MutationObserver(rs => {
      if (
        rs.every(
          r => r.target.closest?.('.broker-eps-comparison')
        )
      ) {
        return;
      }

      clearTimeout(timer);
      timer = setTimeout(render, 120);

    }).observe(page, {
      subtree: true,
      childList: true
    });

    load();

    document.addEventListener(
      'visibilitychange',
      () => {
        if (!document.hidden) {
          load();
        }
      }
    );

    setInterval(() => {
      if (!document.hidden) {
        load();
      }
    }, 300000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      init
    );
  } else {
    init();
  }
})();
