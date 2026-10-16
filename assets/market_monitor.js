(() => {
  'use strict';

  const root = document.getElementById('marketMonitor');
  if (!root) return;

  let dataset = null;
  let pending = null;

  const year = root.querySelector('[data-mm-year]');
  const month = root.querySelector('[data-mm-month]');
  if (!year || !month) return;

  const fmt = (v, d = 2) =>
    v == null
      ? '—'
      : `${v > 0 ? '+' : ''}${v.toLocaleString('zh-TW', {
          minimumFractionDigits: d,
          maximumFractionDigits: d
        })}`;

  const light = {
    red: '紅燈',
    yellow: '黃燈',
    normal: '正常'
  };

  function render() {
    if (!dataset) return;

    // 日期由小到大排列：1號 → 31號
    const rows = dataset.rows
      .filter(r => r.date.slice(0, 7) === `${year.value}-${month.value}`)
      .sort((a, b) => a.date.localeCompare(b.date));

    const incomplete = rows.filter(
      r => r.foreign == null || r.margin == null || r.index == null
    ).length;

    const signals = rows.filter(
      r => r.intersection == null
    ).length;

    const coverage = rows.length
      ? `${year.value}年${Number(month.value)}月 ${rows.length}個交易日｜` +
        (
          incomplete || signals
            ? `原始資料待補 ${incomplete} 日、燈號待補 ${signals} 日`
            : '本月資料與燈號齊全'
        )
      : '本月尚無資料，請確認歷史回補是否完成';

    root.querySelector('[data-mm-status]').textContent =
      `資料截至 ${dataset.as_of_date || '尚無資料'}｜${dataset.scope || ''}｜${coverage}｜更新 ${dataset.updated_at || '—'}`;

    root.querySelector('tbody').innerHTML = rows.length
      ? rows.map(r => {

          // 大盤融資變化（億元）
          // 當日融資餘額－前一交易日融資餘額
          const marginChange =
            Number.isFinite(r.margin) &&
            Number.isFinite(r.margin_previous)
              ? (r.margin - r.margin_previous) / 100000000
              : null;

          return `
            <tr>
              <td>
                ${r.date.slice(5).replace('-', '/')}
              </td>

              <td class="mm-${r.foreign_light || 'missing'}">
                ${fmt(r.foreign)}

                <small>
                  ${light[r.foreign_light] || '資料不足'}
                </small>
              </td>

              <td class="${marginChange == null ? 'mm-missing' : ''}">
                ${fmt(marginChange)}
              </td>

              <td class="mm-${r.margin_light || 'missing'}">
                ${fmt(r.relative)}${r.relative == null ? '' : '%'}

                <small>
                  ${light[r.margin_light] || '資料不足'}
                </small>
              </td>

              <td class="mm-${r.intersection || 'missing'}">
                ${light[r.intersection] || '資料不足'}
              </td>
            </tr>
          `;
        }).join('')
      : `
          <tr>
            <td colspan="5">
              本月尚無已公布交易日資料
            </td>
          </tr>
        `;
  }

  async function load() {
    if (pending) return pending;

    pending = (async () => {
      try {
        const response = await fetch(
          './data/market_monitor.json?v=' + Date.now(),
          {
            cache: 'no-store'
          }
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        dataset = await response.json();

        if (!Array.isArray(dataset.rows)) {
          throw new Error('資料格式錯誤');
        }

        const selectedYear = year.value;

        const latest =
          dataset.as_of_date ||
          new Date().toLocaleDateString(
            'sv-SE',
            {
              timeZone: 'Asia/Taipei'
            }
          );

        const endYear = Math.max(
          2026,
          Number(latest.slice(0, 4)),
          ...dataset.rows.map(
            r => Number(r.date.slice(0, 4))
          )
        );

        year.replaceChildren(
          ...Array.from(
            {
              length: endYear - 2024 + 1
            },
            (_, i) =>
              new Option(
                `${2024 + i}年`,
                String(2024 + i)
              )
          )
        );

        year.value =
          selectedYear ||
          latest.slice(0, 4);

        if (!month.value) {
          month.value = latest.slice(5, 7);
        }

        render();

      } catch (error) {

        root.querySelector('[data-mm-status]').textContent =
          '大盤監控資料讀取失敗，請稍後按重新整理';

      } finally {
        pending = null;
      }
    })();

    return pending;
  }

  year.replaceChildren(
    ...[2024, 2025, 2026].map(
      y => new Option(
        `${y}年`,
        String(y)
      )
    )
  );

  year.value = '';

  month.replaceChildren(
    ...Array.from(
      {
        length: 12
      },
      (_, i) =>
        new Option(
          `${i + 1}月`,
          String(i + 1).padStart(2, '0')
        )
    )
  );

  month.value = '';

  year.addEventListener(
    'change',
    render
  );

  month.addEventListener(
    'change',
    render
  );

  root.querySelector('button').addEventListener(
    'click',
    load
  );

  // 僅監聽本分頁是否開啟，避免整頁監聽與持續輪詢
  new MutationObserver(() => {
    if (
      root.classList.contains('active') &&
      !dataset
    ) {
      load();
    }
  }).observe(
    root,
    {
      attributes: true,
      attributeFilter: ['class']
    }
  );

  if (root.classList.contains('active')) {
    load();
  }

})();

// Separate US panel: existing Taiwan rendering and controls stay intact.
(() => {
  'use strict';
  const root = document.getElementById('marketMonitor');
  if (!root) return;
  const taiwan = document.createElement('div');
  taiwan.id = 'mm-taiwan';
  while (root.firstChild) taiwan.append(root.firstChild);
  const tabs = document.createElement('div');
  tabs.className = 'mm-market-tabs';
  tabs.setAttribute('role', 'group');
  tabs.setAttribute('aria-label', '選擇市場');
  tabs.innerHTML = '<button type="button" aria-pressed="true" aria-controls="mm-taiwan">台股</button><button type="button" aria-pressed="false" aria-controls="mm-us">美股</button>';
  const us = document.createElement('div');
  us.id = 'mm-us';
  us.hidden = true;
  us.innerHTML = `
    <div class="hero"><div><div class="kicker">US MARKET MONITOR</div><h1>美股融資監控</h1><p>FINRA 融資餘額 · 月資料</p></div></div>
    <p class="mm-us-note">通常於次月第三週公布；每日排程檢查是否有新資料。金額單位：億美元。</p>
    <div class="status" data-us-status role="status">開啟後載入資料</div>
    <div class="mm-us-summary"></div>
    <div class="mm-tools"><label>年份 <select aria-label="美股資料年份" data-us-year></select></label><button type="button" data-us-refresh>重新整理</button></div>
    <div class="mm-us-history"></div>
    <details class="mm-us-method"><summary>資料來源與計算方式</summary>
      <p>融資餘額：FINRA 客戶證券融資帳戶借款餘額。月增減比較前一個月，年增率比較去年同月。</p>
      <p>S&amp;P 500 月漲跌幅以相鄰兩個月的最後交易日收盤計算，不含股息。相對增幅＝融資月增率－同月 S&amp;P 500 漲跌幅，單位為百分點；這是比較指標，不是官方風險燈號或買賣訊號。缺少資料顯示「—」。</p>
      <p><a href="https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics" target="_blank" rel="noopener">FINRA 官方資料</a> · <a href="https://fred.stlouisfed.org/series/SP500" target="_blank" rel="noopener">FRED／S&amp;P Dow Jones Indices</a></p>
    </details>`;
  root.append(tabs, taiwan, us);
  let data = null;
  let pending = false;
  const status = us.querySelector('[data-us-status]');
  const year = us.querySelector('[data-us-year]');
  const number = (value, signed = true) => Number.isFinite(value)
    ? (signed && value > 0 ? '+' : '') + value.toLocaleString('zh-TW', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '—';
  const fields = r => [
    ['融資餘額', number(r.margin_million / 100, false), '億美元'],
    ['融資月增減', number(r.change_million == null ? null : r.change_million / 100), '億美元'],
    ['融資月增率', number(r.mom_pct), '%'],
    ['融資年增率', number(r.yoy_pct), '%'],
    ['S&P 500 月漲跌幅', number(r.sp500_return_pct), '%'],
    ['融資相對增幅', number(r.relative_pp), '百分點']
  ];
  function card(r, latest = false) {
    const box = document.createElement('article');
    box.className = 'card mm-us-month';
    const heading = document.createElement('h2');
    heading.textContent = `${r.month}${latest ? ' · 最新公布' : ''}`;
    box.append(heading);
    const list = document.createElement('dl');
    fields(r).forEach(([label, value, unit]) => {
      const pair = document.createElement('div');
      const dt = document.createElement('dt');
      dt.textContent = label;
      const dd = document.createElement('dd');
      dd.textContent = value;
      const small = document.createElement('small');
      small.textContent = value === '—' ? '' : unit;
      dd.append(small);
      pair.append(dt, dd);
      list.append(pair);
    });
    box.append(list);
    return box;
  }
  function render() {
    const rows = data.rows.slice().sort((a,b) => b.month.localeCompare(a.month));
    us.querySelector('.mm-us-summary').replaceChildren(...(rows.length ? [card(rows[0], true)] : []));
    const selected = rows.filter(r => r.month.slice(0,4) === year.value);
    us.querySelector('.mm-us-history').replaceChildren(...selected.map(r => card(r)));
    status.textContent = `資料月份 ${data.as_of_month || '尚無資料'}｜檢查時間 ${data.checked_at || '—'}` +
      (data.errors?.length ? '｜部分來源更新失敗，目前顯示上次可用資料' : '') +
      (!rows.length ? '｜尚無可用資料' : '');
  }
  async function load() {
    if (pending) return;
    pending = true;
    status.textContent = '載入美股資料…';
    try {
      const response = await fetch('./data/us_market_monitor.json?v=' + Date.now(), {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const next = await response.json();
      if (!Array.isArray(next.rows) || next.rows.some(r => !/^\d{4}-(0[1-9]|1[0-2])$/.test(r.month) || !Number.isFinite(r.margin_million))) throw new Error('資料格式錯誤');
      data = next;
      const selected = year.value;
      const years = [...new Set(data.rows.map(r => r.month.slice(0,4)))].sort().reverse();
      year.replaceChildren(...years.map(y => new Option(y + '年', y)));
      year.value = years.includes(selected) ? selected : (years[0] || '');
      render();
    } catch (error) {
      status.textContent = data ? '美股資料讀取失敗，保留本次已載入內容；請稍後重新整理' : '美股資料尚未載入，請確認已執行 Market monitor 更新排程後再重新整理';
    } finally { pending = false; }
  }
  tabs.querySelectorAll('button').forEach((button, index) => button.addEventListener('click', () => {
    taiwan.hidden = index === 1;
    us.hidden = index === 0;
    tabs.querySelectorAll('button').forEach((b, i) => b.setAttribute('aria-pressed', String(i === index)));
    if (index === 1 && !data) load();
  }));
  year.addEventListener('change', () => { if (data) render(); });
  us.querySelector('[data-us-refresh]').addEventListener('click', load);
})();
