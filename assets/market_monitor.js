async function loadTaiwanMonitorArchive(kind) {
  const response = await fetch('./data/history/monitor-' + kind + '-2008-2023.json', {cache:'no-cache'});
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

const twRiskNames = ['🟢 綠燈', '🟡 黃燈', '🟠 黃紅燈', '🔴 紅燈'];
let twRiskByDate = new Map();
let twBreadthRequest;
// Display-only inputs for the daily composite table; never used to calculate the signal.
let twCompositeFunds = [];
let twCompositeBreadth = [];

function applyCombinedMargin(funds, otc) {
  const sorted = [...new Map(funds.map(r => [r.date, r])).values()]
    .sort((a, b) => a.date.localeCompare(b.date));
  const valid = n => Number.isSafeInteger(n) && n > 0;
  const combined = [];
  for (const original of sorted) {
    const pair = otc[original.date];
    const prior = Array.isArray(pair) ? pair[0] : null;
    const current = Array.isArray(pair) ? pair[1] : null;
    const r = {...original, twseMargin: original.margin, tpexMargin: current,
      margin: valid(original.margin) && valid(current) ? original.margin + current : null,
      margin_previous: valid(original.margin_previous) && valid(prior) ? original.margin_previous + prior : null,
      relative: null, relative5: null, relative20: null, margin_light: null, intersection: null};
    combined.push(r);
    for (const [days, field] of [[1, 'relative'], [5, 'relative5'], [20, 'relative20']]) {
      const w = combined.slice(-days - 1);
      if (w.length === days + 1 && w.every(x => valid(x.margin) && Number.isFinite(x.index) && x.index > 0)) {
        r[field] = (r.margin / w[0].margin - r.index / w[0].index) * 100;
      }
    }
    if (r.relative5 != null && r.relative20 != null) {
      r.margin_light = r.relative5 >= 5 || r.relative20 >= 9 ? 'red'
        : r.relative5 >= 3.5 || r.relative20 >= 7.5 ? 'yellow' : 'normal';
      const f = r.foreign_light, m = r.margin_light;
      if (['normal', 'yellow', 'red'].includes(f)) {
        r.intersection = f === 'normal' || m === 'normal' ? 'normal'
          : f === 'red' || m === 'red' ? 'red' : 'yellow';
      }
    }
  }
  return combined;
}

function buildTwRisk(funds, breadth) {
  const fundMap = new Map(funds.map(row => [row.date, row]));
  const breadthMap = new Map(breadth.map(row => [row.date, row]));
  const dates = [...new Set([...fundMap.keys(), ...breadthMap.keys()])].sort();
  const validLight = value => ['normal', 'yellow', 'red'].includes(value);
  const validPct = value => Number.isFinite(value) && value >= 0 && value <= 100;
  const results = new Map();
  let level = 0;
  let recoveryDays = 0;
  for (let i = 59; i < dates.length; i++) {
    const date = dates[i];
    const window = dates.slice(i - 59, i + 1);
    const prices = window.map(day => fundMap.get(day)?.index);
    const breadth20 = window.slice(-20).map(day => breadthMap.get(day));
    const lastFive = window.slice(-5).map(day => fundMap.get(day));
    const nets = breadth20.slice(-5).map(row => row?.net);
    const f = fundMap.get(date);
    const b = breadthMap.get(date);
    if (!prices.every(value => Number.isFinite(value) && value > 0)
      || !breadth20.every(row => row?.complete && validPct(row.pct20))
      || !lastFive.every(row => validLight(row?.intersection))
      || !nets.every(Number.isFinite) || !validPct(b.pct60)
      || !validLight(f.foreign_light) || !validLight(f.margin_light)) {
      recoveryDays = 0;
      continue;
    }

    const widths = breadth20.map(row => row.pct20);
    const weakWidth = b.pct20 < 40 || (b.pct20 < 50 && Math.max(...widths.slice(-10)) - b.pct20 >= 15);
    const net = nets.reduce((sum, value) => sum + value, 0);
    const weakAD = net < 0 && nets.filter(value => value < 0).length >= 3;
    const fundRedDays = lastFive.filter(row => row.intersection === 'red').length;
    const fundRed = f.intersection === 'red';
    const foreignRed = f.foreign_light === 'red';
    const red = fundRed && foreignRed && weakWidth && fundRedDays >= 3;
    const orange = fundRed && weakWidth && weakAD && (foreignRed || b.pct60 < 50);
    const high = Math.max(...prices);
    const yellow = f.margin_light !== 'normal' && f.index >= 0.97 * high
      && b.pct20 < 50 && Math.max(...widths) - b.pct20 >= 15;
    const trigger = red ? 3 : orange ? 2 : yellow ? 1 : 0;
    const previous = level;
    const ma10 = prices.slice(-10).reduce((sum, price) => sum + price, 0) / 10;
    let evidence = '';
    if (trigger >= level) {
      level = trigger;
      recoveryDays = 0;
    } else {
      const minWidth = level === 3 ? 35 : 50;
      const needsMediumBreadth = level === 1;
      const unmet = [];
      if (fundRed) unmet.push('資金交集仍紅');
      if (f.index <= ma10) unmet.push('收盤未站上 10 日線');
      if (net <= 0) unmet.push('近 5 日騰落淨值未轉正');
      if (b.pct20 < minWidth) unmet.push('20 日廣度 ' + b.pct20.toFixed(1) + '%，未達 ' + minWidth + '%');
      if (needsMediumBreadth && b.pct60 < 40) unmet.push('60 日廣度 ' + b.pct60.toFixed(1) + '%，未達 40%');
      recoveryDays = unmet.length ? 0 : recoveryDays + 1;
      evidence = '修復進度 ' + recoveryDays + '/3 日。' + (unmet.length ? unmet.join('、') : '本級修復條件全數達標');
      if (recoveryDays === 3) {
        level--;
        recoveryDays = 0;
      }
    }
    let reason = ['未觸發警戒條件', '高檔廣度背離且融資偏熱', '資金與盤面同步轉弱', '資金交集持續亮紅且廣度轉弱'][trigger];
    if (evidence) reason = (level < previous ? '修復確認，降一級。' : '延續前次警戒。') + evidence;
    const transition = (previous === level ? '維持' + twRiskNames[level] : twRiskNames[previous] + ' → ' + twRiskNames[level]);
    const basis = transition + '。當日原始訊號：' + (trigger ? twRiskNames[trigger] : '無新增警報')
      + '。' + reason + '。收盤 ' + f.index.toFixed(2) + '，10 日均線 ' + ma10.toFixed(2)
      + '，20／60 日廣度 ' + b.pct20.toFixed(1) + '%／' + b.pct60.toFixed(1)
      + '%，近 5 日騰落淨值 ' + net.toLocaleString('zh-TW') + '。';
    results.set(date, {level, trigger, reason, basis, fundRedDays, net, pct20:b.pct20, pct60:b.pct60,
      foreign:f.foreign_light, margin:f.margin_light, intersection:f.intersection});
  }
  return results;
}

function paintTwRisk(date) {
  const card = document.querySelector('[data-tw-risk]');
  if (!card) return;
  const r = twRiskByDate.get(date);
  // Presentation metadata only; the level is still produced by buildTwRisk().
  card.dataset.riskLevel = r ? String(r.level) : 'unknown';
  card.classList.add('mm-risk-card');
  card.setAttribute('aria-live', 'polite');
  card.querySelector('strong').textContent = r ? twRiskNames[r.level] : '資料待齊';
  card.querySelector('small').textContent = date || '';
  card.querySelector('[data-summary]').textContent = r
    ? r.reason : '等待同日完整資料與計算期數';
  const labels = {normal:'正常', yellow:'黃燈', red:'紅燈'};
  card.querySelector('[data-factors]').textContent = r
    ? `${r.basis} 外資 ${labels[r.foreign]} ｜ 融資 ${labels[r.margin]} ｜ 站上 20 日線 ${r.pct20.toFixed(1)}%、60 日線 ${r.pct60.toFixed(1)}% ｜ 資金交集 ${labels[r.intersection]}（近 5 日 ${r.fundRedDays} 日紅燈） ｜ 近 5 日累計漲跌淨家數 ${r.net.toLocaleString('zh-TW')}` : '';
  document.dispatchEvent(new Event('tw-market-risk-updated'));
}

function getTwBreadth() {
  twBreadthRequest ||= fetch('./data/market_breadth.json?v='+Date.now(),{cache:'no-store'}).then(async r=>{
          if(!r.ok)throw new Error('HTTP '+r.status);
          const j=await r.json();
          if(j.schema!==1||!Array.isArray(j.series?.twse))throw Error('資料格式不正確');
          try {
            const history = await loadTaiwanMonitorArchive('breadth');
            if (history) {
              const joined = {};
              for (const market of ['twse','tpex','all']) joined[market] = history[market].concat(j.series[market]);
              j.series = joined;
            }
          } catch {
            j.archiveWarning = '｜歷史資料載入失敗，請重新整理';
          }
          return j;
        }).catch(err => { twBreadthRequest = null; throw err; });
  return twBreadthRequest;
}

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
      r => !twRiskByDate.has(r.date)
    ).length;

    const coverage = rows.length
      ? `${year.value}年${Number(month.value)}月 ${rows.length}個交易日｜` +
        (
          incomplete || signals
            ? `原始資料待補 ${incomplete} 日、燈號待補 ${signals} 日`
            : '本月資料與燈號齊全'
        )
      : '本月尚無資料，請確認歷史回補是否完成';

    const categories = [...new Set(rows.map(r => r.foreign_basis).filter(Boolean))];
    const scope = '融資：上市＋上櫃｜基準：加權指數｜外資：上市' + (categories.length ? '（' + categories.join('、') + '）' : '');
    root.querySelector('[data-mm-status]').textContent =
      `資料截至 ${dataset.as_of_date || '尚無資料'}｜${scope || ''}｜${coverage}｜更新 ${dataset.updated_at || '—'}${dataset.archiveWarning || ''}`;

    root.querySelector('.mb-flow-original tbody').innerHTML = rows.length
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
                <details><summary>${r.margin == null ? '待補' : (r.margin / 1e8).toLocaleString('zh-TW', {minimumFractionDigits:2, maximumFractionDigits:2})}</summary>
                  <small>上市 ${r.twseMargin == null ? '—' : (r.twseMargin / 1e8).toFixed(2)}<br>上櫃 ${r.tpexMargin == null ? '—' : (r.tpexMargin / 1e8).toFixed(2)}</small></details>
                <small>增減 ${fmt(marginChange)}</small>
              </td>

              <td class="mm-${r.margin_light || 'missing'}">
                ${fmt(r.relative)}${r.relative == null ? '' : '%'}

                <small>
                  ${light[r.margin_light] || '資料不足'}
                </small>
              </td>

              <td class="mm-composite">
                ${light[r.intersection] ? (r.intersection === 'red' ? '🔴 ' : r.intersection === 'yellow' ? '🟡 ' : '🟢 ') + light[r.intersection] : '資料不足'}
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

        try {
          const history = await loadTaiwanMonitorArchive('funds');
          if (history) dataset.rows = history.concat(dataset.rows);
        } catch {
          dataset.archiveWarning = '｜歷史資料載入失敗，請重新整理';
        }
        let otc = {};
        try {
          const response = await fetch('./data/market_margin_tpex.json', {cache:'no-store'});
          if (!response.ok) throw new Error('上櫃融資資料讀取失敗');
          const saved = await response.json();
          if (saved.unit !== 'TWD' || !saved.rows) throw new Error('融資資料格式錯誤');
          otc = saved.rows;
        } catch {
          dataset.archiveWarning = (dataset.archiveWarning || '') + '｜上櫃融資待補';
        }
        dataset.rows = applyCombinedMargin(dataset.rows, otc);
        twRiskByDate = new Map();
        twBreadthRequest = null;
        const breadth = await getTwBreadth().catch(() => null);
        if (breadth) twRiskByDate = buildTwRisk(dataset.rows, breadth.series.all || []);
        twCompositeFunds = dataset.rows;
        twCompositeBreadth = breadth?.series?.all || [];
        document.dispatchEvent(new Event('tw-composite-data-updated'));
        paintTwRisk([dataset.as_of_date, breadth?.as_of_date].filter(Boolean).sort().at(-1));
        const availableYears = [...new Set(dataset.rows.map(r => r.date.slice(0, 4)))].sort();
        year.replaceChildren(...availableYears.map(y => new Option(y + '年', y)));

        year.value =
          selectedYear ||
          latest.slice(0, 4);

        if (!month.value) {
          month.value = latest.slice(5, 7);
        }

        render();

      } catch (error) {

        twRiskByDate = new Map();
        twCompositeFunds = [];
        twCompositeBreadth = [];
        document.dispatchEvent(new Event('tw-composite-data-updated'));
        paintTwRisk(null);
        root.querySelector('[data-mm-status]').textContent =
          '大盤監控資料讀取失敗，請稍後按重新整理';

      } finally {
        pending = null;
      }
    })();

    return pending;
  }

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


// 台股市場廣度專業面板：不改原始數據、既有資金籌碼與美股流程。
(() => {
  'use strict';
  const tw = document.querySelector('#mm-taiwan');
  if (!tw) return;
  const flow = document.createElement('div');
  flow.className = 'mb-flow-original';
  while (tw.firstChild) flow.append(tw.firstChild);
  const nav = document.createElement('div');
  nav.className = 'mb-nav';
  nav.setAttribute('role','tablist');
  nav.setAttribute('aria-label','台股市場監控項目');
  const panel = document.createElement('section');
  panel.className = 'mb-panel';
  panel.hidden = true;
  // Keep the existing four-level signal calculation; only ensure the card is rendered.
  let riskCard = flow.querySelector('[data-tw-risk]');
  if (!riskCard) {
    // Fallback for older/cached index.html versions that lack the risk-card markup.
    riskCard = document.createElement('section');
    riskCard.className = 'card mm-risk-card';
    riskCard.setAttribute('data-tw-risk', '');
    riskCard.setAttribute('aria-label', '大盤綜合燈號');
    riskCard.innerHTML = `<div class="mm-risk-heading">大盤綜合燈號　<strong>資料待齊</strong>　<small></small></div>
      <div data-summary>等待同日完整資料與計算期數</div>
      <details><summary>查看判斷依據</summary><p data-factors></p></details>`;
  }
  const details = riskCard.querySelector('details');
  const factors = details.querySelector('[data-factors]');
  details.replaceChildren(details.querySelector('summary'), factors);
  details.querySelector('summary').textContent = '燈號判斷依據與退燈條件';
  details.insertAdjacentHTML('beforeend', `<p>黃燈：融資黃或紅，加權收盤距近 60 日高點不超過 3%，站上 20 日線的占比低於 50%，且比近 20 日高點少至少 15 個百分點。</p><p>黃紅燈：資金交集紅燈、20 日市場廣度轉弱、騰落轉弱，且外資紅燈或站上 60 日線的占比低於 50%。</p><p>紅燈：當日資金交集與外資皆紅、20 日市場廣度轉弱，且近 5 個交易日至少 3 天資金交集亮紅。符合多級時採最高級。</p><p><b>延續、降級與轉綠</b>　當日觸發低於目前警戒才開始累計修復日；同級或升級、任一修復條件未達、資料缺漏都會重算連續天數。資料不足當日顯示待齊。已亮燈後，每次降一級須連續 3 個交易日確認修復：資金交集非紅、收盤站上 10 日線、近 5 日騰落淨值為正。紅降黃紅要求 20 日廣度至少 35%，其餘降級至少 50%；黃轉綠另要求 60 日廣度至少 40%。</p><p>廣度採上市櫃合計。20 日廣度轉弱指占比低於 40%，或低於 50% 且比近 10 日高點少至少 15 個百分點。騰落轉弱指近 5 日累計上漲減下跌家數為負，且至少 3 日為負。</p>`);
  riskCard.classList.add('mm-risk-card');
  riskCard.setAttribute('aria-live', 'polite');
  const composite = document.createElement('section');
  composite.className = 'mm-composite-page';
  composite.setAttribute('aria-label', '綜合指標每日監控');
  composite.innerHTML = `
    <div class="mm-composite-intro"><span class="mb-eyebrow">COMPOSITE SIGNAL</span><h2>綜合指標</h2><p>外資與融資以億元計。底色標示達到警戒條件的指標；點日期下方燈號可看原因。</p></div>
    <div class="mm-composite-filters">
      <label>年份 <select data-composite-year aria-label="綜合指標年份"></select></label>
      <label>月份 <select data-composite-month aria-label="綜合指標月份"></select></label>
      <button type="button" data-composite-refresh>重新整理</button>
    </div>
    <div class="mm-composite-status" data-composite-status role="status">資料載入中…</div>
    <div class="mm-composite-scroll" aria-label="每日綜合指標">
      <table class="mm-composite-table mm-raw-table"><thead><tr>
        <th scope="col">日期<br>燈號</th><th scope="col">外資<br>買賣超</th>
        <th scope="col">融資餘額<br>日增減</th><th scope="col">站上<br>60日線</th>
        <th scope="col">近5日漲跌<br>淨家數</th>
      </tr></thead><tbody></tbody></table>
    </div>
    <p class="mm-composite-footnote">資料不足顯示「—／待齊」，不視為綠燈。燈號計算採全歷史連續交易日，年份與月份僅用於篩選表格。外資與融資底色依各自的多日警戒規則。近5日漲跌淨家數為每日上漲家數減下跌家數，再加總五日。</p>`;
  composite.prepend(riskCard);
  tw.append(nav, composite, flow, panel);
  panel.innerHTML = `
    <div class="mb-topline"><div><span class="mb-eyebrow">MARKET INTERNALS</span><h2 data-mb-title>市場寬度</h2><p data-mb-subtitle>用全市場成分股的參與程度，觀察指數背後的強弱</p></div><div class="mb-asof" data-mb-asof>資料載入中</div></div>
    <div class="mb-filters">
      <label>市場 <select data-mb-market aria-label="市場"><option value="twse">上市</option><option value="tpex">上櫃</option><option value="all">上市櫃合計</option></select></label>
      <label class="mb-ad-year-filter" hidden>統計年度 <select data-mb-ad-year aria-label="騰落線統計年度"></select></label>
      <label class="mb-breadth-year-filter" hidden>統計年度 <select data-mb-breadth-year aria-label="市場寬度統計年度"></select></label>
      <label>時間範圍 <select data-mb-period aria-label="顯示期間"><option value="1">近一個月</option><option value="3">近三個月</option><option value="6" selected>近六個月</option><option value="12">近一年</option><option value="0">全部</option></select></label>
      <label class="mb-window-filter">均線 <select data-mb-window aria-label="市場寬度均線"><option value="both">20 日＋60 日</option><option value="20">只看 20 日</option><option value="60">只看 60 日</option></select></label>
    </div>
    <div class="mb-content" aria-live="polite"></div>`;
  document.addEventListener('tw-market-risk-updated', () => {
    const area = panel.querySelector('[data-risk-date]');
    if (area) area.textContent = area.dataset.riskDate + ' · 大盤綜合 ' + (twRiskNames[twRiskByDate.get(area.dataset.riskDate)?.level] || '資料待齊');
  });
  const names = ['綜合指標','資金籌碼','騰落線','市場寬度'];
  const market = panel.querySelector('[data-mb-market]');
  const period = panel.querySelector('[data-mb-period]');
  const breadthYear = panel.querySelector('[data-mb-breadth-year]');
  const adYear = panel.querySelector('[data-mb-ad-year]');
  const windowSelect = panel.querySelector('[data-mb-window]');
  const content = panel.querySelector('.mb-content');
  const fmt = (n, d=2) => Number.isFinite(n) ? n.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d}) : '—';
  const signed = (n,d=2) => Number.isFinite(n) ? (n>0?'+':'')+fmt(n,d) : '—';
  const h = (tag, cls, txt) => { const e=document.createElement(tag); if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e; };
  let data, loading, mode=0, focusIndex=null;
  let detailsOpen=false;
  let detailBasis=20;
  let lastViewKey='';
  // 每年第一個交易日前歸零：不沿用上一年的累計值。所有市場皆以各自每日淨家數計算。
  // 缺日之後不把未確認的累計值視為有效，直到下一年度才重新開始。
  function yearlyAd(rows){
    let y='', total=0, valid=true;
    return rows.map(r=>{
      const next={...r};
      const rowYear=String(r.date||'').slice(0,4);
      if(rowYear!==y){y=rowYear; total=0; valid=true;}
      if(!r.complete || !Number.isFinite(r.net))valid=false;
      if(valid)total+=r.net;
      next.ad=valid?total:null;
      return next;
    });
  }
  function syncAdYears(){
    if(!data)return;
    const years=[...new Set((data.series[market.value]||[]).map(r=>r.date?.slice(0,4)).filter(Boolean))].sort().reverse();
    const previousBreadth = breadthYear.value;
    breadthYear.replaceChildren(new Option('全部年度',''), ...years.map(y => new Option(y + ' 年', y)));
    breadthYear.value = years.includes(previousBreadth) ? previousBreadth : '';
    const previous=adYear.value;
    adYear.replaceChildren(...years.map(y=>new Option(y+' 年',y)));
    adYear.value=years.includes(previous)?previous:(years[0]||'');
  }
  const change = (rows,index,key,days) => {
    if(index<days)return null;
    const a=rows[index], b=rows[index-days];
    if (!a?.complete || !b?.complete || !Number.isFinite(a[key]) || !Number.isFinite(b[key]))return null;
    if(key==='ad' && a.date.slice(0,4)!==b.date.slice(0,4))return null;
    // Gap-safe: do not span incomplete daily records.
    for(let j=index-days;j<=index;j++)if(!rows[j]?.complete)return null;
    return a[key]-b[key];
  };
  async function select(i){
    mode=i;
    [...nav.children].forEach((b,k)=>{b.setAttribute('aria-selected',String(i===k));b.tabIndex=i===k?0:-1;});
    composite.hidden=i!==0;
    flow.hidden=i!==1;
    panel.hidden=i<=1;
    if(i===0){ renderComposite(); return; }
    if(i===1)return;
    panel.querySelector('[data-mb-title]').textContent=names[i];
    panel.querySelector('[data-mb-subtitle]').textContent=i===2?'累計漲跌家數與指數對照，辨識市場廣度背離':'20／60 日均線以上股票占比，追蹤市場參與程度';
    panel.querySelector('.mb-breadth-year-filter').hidden=i!==3;
    panel.querySelector('.mb-window-filter').hidden=i!==3;
    panel.querySelector('.mb-ad-year-filter').hidden=i!==2;
    if(!data){
      content.textContent='正在讀取市場廣度歷史資料…';
      try{
        loading ||= getTwBreadth();
        data=await loading;
      }catch(err){loading=null;content.textContent='資料讀取失敗，請重新點選此分頁。';return;}
    }
    syncAdYears();
    render();
  }
  // Read-only composite daily table; all final levels come directly from buildTwRisk().
  const compYear = composite.querySelector('[data-composite-year]');
  const compMonth = composite.querySelector('[data-composite-month]');
  const compStatus = composite.querySelector('[data-composite-status]');
  const compBody = composite.querySelector('.mm-composite-table tbody');
  const tone = light => light === 'red' ? 'mm-cbad' : light === 'yellow' ? 'mm-cwarn' : '';
  function renderComposite(){
    if(!twCompositeFunds.length){
      compStatus.textContent='資金與市場廣度資料尚未載入，請稍後重新整理。';
      compBody.replaceChildren();
      return;
    }
    const sortedFunds=[...twCompositeFunds].sort((a,b)=>a.date.localeCompare(b.date));
    const fundMap=new Map(sortedFunds.map(r=>[r.date,r]));
    const breadthMap=new Map(twCompositeBreadth.map(r=>[r.date,r]));
    // Match buildTwRisk(): the union calendar matters for each rolling window.
    const dates=[...new Set([...fundMap.keys(),...breadthMap.keys()])].sort();
    const dateToIndex=new Map(dates.map((d,i)=>[d,i]));
    const years=[...new Set(sortedFunds.map(r=>r.date.slice(0,4)))].sort().reverse();
    const newest=sortedFunds.at(-1)?.date || '';
    const oldYear=compYear.value, oldMonth=compMonth.value;
    compYear.replaceChildren(...years.map(y=>new Option(y+'年',y)));
    compYear.value=years.includes(oldYear)?oldYear:(newest.slice(0,4)||'');
    // 月份選單固定按 1 月 → 12 月排序，包含尚無資料的月份。
    const months=Array.from({length:12},(_,i)=>String(i+1).padStart(2,'0'));
    compMonth.replaceChildren(...months.map(m=>new Option(Number(m)+'月',m)));
    // 首次開啟或切換年份，預設選擇該年最新有資料的月份。
    const availableMonths=sortedFunds.filter(r=>r.date.startsWith(compYear.value)).map(r=>r.date.slice(5,7));
    compMonth.value=oldYear===compYear.value && months.includes(oldMonth)
      ? oldMonth : (availableMonths.at(-1)||'01');
    // 日期按月內交易日由早到晚排列（1 日 → 31 日）。
    const selected=sortedFunds.filter(r=>r.date.startsWith(compYear.value+'-'+compMonth.value));
    compBody.replaceChildren();
    let valid=0;
    for(const fund of selected){
      const d=fund.date, i=dateToIndex.get(d), risk=twRiskByDate.get(d);
      const tr=document.createElement('tr');
      const b = breadthMap.get(d);
      const td = (value, digits, tone = '', suffix = '') => {
        const label = Number.isFinite(value)
          ? value.toLocaleString('zh-TW', {minimumFractionDigits:digits, maximumFractionDigits:digits}) + suffix : '—';
        return h('td', Number.isFinite(value) ? tone : '', label);
      };
      const change = Number.isFinite(fund.margin) && Number.isFinite(fund.margin_previous)
        ? (fund.margin - fund.margin_previous) / 1e8 : null;
      const last = dates.slice(Math.max(0,i-4),i+1).map(x => breadthMap.get(x));
      const nets = last.map(row => row?.complete ? row.net : null);
      const net = nets.length === 5 && nets.every(Number.isFinite) ? nets.reduce((a,n)=>a+n,0) : null;
      const width = b?.complete ? b.pct60 : null;
      const day = h('th','mm-composite-date',d.slice(5).replace('-','/'));
      day.scope='row';
      tr.append(day, td(fund.foreign,2,tone(fund.foreign_light)), td(change,2,tone(fund.margin_light)),
        td(width,1,width < 50 ? 'mm-cwarn' : '', '%'),
        td(net,0,net < 0 ? (nets.filter(n=>n<0).length>=3 ? 'mm-cbad':'mm-cwarn') : ''));
      compBody.append(tr);
      if (!risk) {
        day.append(h('small','','待齊'));
        continue;
      }
      valid++;
      const label = ['綠燈','黃燈','黃紅燈','紅燈'][risk.level];
      const button = h('button','mm-day-light light-'+risk.level,label);
      button.type='button';
      button.setAttribute('aria-label',d+' '+label+'，查看判斷依據');
      button.setAttribute('aria-expanded','false');
      const detail = compBody.insertRow();
      detail.hidden=true;
      detail.id='mm-day-'+d;
      detail.className='mm-day-detail';
      button.setAttribute('aria-controls',detail.id);
      const cell=detail.insertCell();
      cell.colSpan=5;
      cell.textContent=risk.basis.replace(/[🔴🟠🟡🟢]/gu,'').replace(/近 5 日騰落淨值/g,'近5日上漲減下跌家數');
      const prices=dates.slice(Math.max(0,i-59),i+1).map(x=>fundMap.get(x)?.index);
      if (prices.length===60 && prices.every(n=>Number.isFinite(n) && n>0)) {
        const distance=(fund.index / Math.max(...prices)-1)*100;
        cell.append(document.createTextNode(' 距近60日高點 '+distance.toFixed(1)+'%。'));
      }
      day.append(button);
      button.addEventListener('click',()=>{
        const open=detail.hidden;
        for (const row of compBody.querySelectorAll('.mm-day-detail:not([hidden])')) row.hidden=true;
        for (const active of compBody.querySelectorAll('[aria-expanded="true"]')) active.setAttribute('aria-expanded','false');
        detail.hidden=!open;
        button.setAttribute('aria-expanded',String(open));
      });
    }
    if(!selected.length){const r=compBody.insertRow();const c=r.insertCell();c.colSpan=5;c.textContent='本月尚無交易日資料';}
    compStatus.textContent=compYear.value+'年'+Number(compMonth.value||0)+'月｜'+selected.length+'個交易日｜可計算綜合燈號 '+valid+' 日｜最新資料 '+newest;
  }
  compYear.addEventListener('change',()=>{compMonth.value='';renderComposite();});
  compMonth.addEventListener('change',renderComposite);
  composite.querySelector('[data-composite-refresh]').addEventListener('click',()=>{
    const originalRefresh=flow.querySelector('.mm-tools button');
    if(originalRefresh)originalRefresh.click();
  });
  document.addEventListener('tw-composite-data-updated',()=>{if(mode===0)renderComposite();});
  names.forEach((label,i)=>{
    const b=h('button','',label);
    b.type='button';b.setAttribute('role','tab');b.setAttribute('aria-selected',String(i===0));b.tabIndex=i===0?0:-1;
    b.addEventListener('click',()=>select(i));nav.append(b);
  });
  function metric(label,value,note,cls=''){
    const card=h('div','mb-kpi '+cls);
    card.append(h('span','mb-kpi-label',label),h('strong','mb-kpi-value',value),h('small','mb-kpi-note',note));return card;
  }
  function render(){
    if(!data||mode<2)return;
    const rawSource=data.series[market.value]||[];
    const source=mode===2?yearlyAd(rawSource):rawSource;
    const desiredYear=mode===2?adYear.value:breadthYear.value;
    const yearRows=desiredYear?source.filter(r=>r.date?.slice(0,4)===desiredYear):source;
    const last=yearRows.at(-1);
    const key=[mode,market.value,period.value,windowSelect.value,desiredYear].join('/');
    if(key!==lastViewKey){focusIndex=null;lastViewKey=key;}
    if(!last){content.textContent='尚無交易日資料';return;}
    const isBreadth=mode===3;
    const windows=windowSelect.value==='both'?[20,60]:[Number(windowSelect.value)];
    const dateCut=new Date(last.date+'T00:00:00Z');
    if(period.value!=='0')dateCut.setUTCMonth(dateCut.getUTCMonth()-Number(period.value));
    const shown=source.map((r,i)=>({...r,_idx:i})).filter(r=>(!desiredYear||r.date.slice(0,4)===desiredYear)&&(period.value==='0'||r.date>=dateCut.toISOString().slice(0,10)));
    const available=shown.filter(r=>r.complete && (isBreadth?windows.some(n=>Number.isFinite(r['pct'+n])):Number.isFinite(r.ad)));
    panel.querySelector('[data-mb-asof]').textContent=isBreadth?'資料截至 '+(data.as_of_date||last.date):'年度 '+desiredYear+' · 截至 '+last.date;
    if(data.archiveWarning)panel.querySelector('[data-mb-asof]').textContent+=data.archiveWarning;
    detailsOpen=content.querySelector('details')?.open ?? detailsOpen;
    content.replaceChildren();
    if(!available.length){
      const empty=h('div','mb-empty',market.value==='all'?'上市櫃合計資料尚不完整，目前不能計算合計走勢。請先切換「上市」檢視；缺少的上櫃歷史資料需補齊。':'此期間資料尚未補齊，請稍後再試。');
      content.append(empty);return;
    }
    const latest=available.at(-1);
    if(shown.some(r=>!r.complete))content.append(h('div','mb-warning','部分交易日缺少官方行情：圖表會保留缺口，不會以零或前日數字補值。'));
    const active=focusIndex===null?latest:shown.find(r=>r._idx===focusIndex)||latest;
    const overview=h('section','mb-overview');
    const dateArea=h('div','mb-inspect-date');
    overview.append(dateArea);
    const kpis=h('div','mb-kpis');overview.append(kpis);content.append(overview);
    const chartHeading=h('div','mb-chart-heading');
    chartHeading.append(h('div','mb-chart-title',isBreadth?'市場寬度走勢':'騰落線與大盤指數'));
    const hint=h('small','mb-chart-hint','左右滑動，逐日查價');chartHeading.append(hint);
    const chartBox=h('section','mb-chart mb-chart-primary');chartBox.append(chartHeading);
    content.append(chartBox);
    if(!isBreadth)chartBox.append(h('p','mb-index-note','每年首個交易日前歸零，不承接前一年。圖中兩條線另以顯示期間首筆有效資料作比較基準；左軸是家次、右軸是指數漲跌百分比。'));
    if(isBreadth)chartBox.append(h('p','mb-index-note','參考區間：15% 以下為市場廣度偏低、85% 以上為偏高；屬觀察提示，不代表必然見底或見頂。'));
    const bottom=h('div','mb-bottom');content.append(bottom);
    const note=h('div','mb-method');
    note.textContent=isBreadth?'站上比例＝有效普通股中，收盤價高於各自 20／60 日均線的比率；變化以百分點表示。':'騰落線＝本年度每日（上漲家數－下跌家數）累計；每年重新歸零，不受前一年影響。';
    bottom.append(note);
    const details=h('details','mb-details');
    const summary=h('summary','', '每日明細');details.append(summary);
    bottom.append(details);
    function currentIndex(r){return r?source.findIndex(z=>z.date===r.date):-1;}
    const selectedWindow=windows[0];
    function update(r){
      const idx=currentIndex(r); if(idx<0)return;
      focusIndex=idx;
      dateArea.dataset.riskDate=r.date;
      dateArea.textContent=r.date+' · 大盤綜合 '+(twRiskNames[twRiskByDate.get(r.date)?.level] || '資料待齊');
      kpis.replaceChildren();
      if(isBreadth){
        for(const n of windows){
          const v=r['pct'+n];
          const d5=change(source,idx,'pct'+n,5),d10=change(source,idx,'pct'+n,10);
          kpis.append(metric(n+' 日線以上',Number.isFinite(v)?fmt(v)+'%':'—', '5 日 '+signed(d5)+' pp  ·  10 日 '+signed(d10)+' pp',Number.isFinite(v)?v<=15?'mb-low':v>=85?'mb-high':'':''));
        }
        if(windows.length===1)kpis.append(metric('市場廣度方向', Number.isFinite(change(source,idx,'pct'+selectedWindow,5))?(change(source,idx,'pct'+selectedWindow,5)>0?'改善中':change(source,idx,'pct'+selectedWindow,5)<0?'轉弱中':'持平'):'資料不足',selectedWindow+' 日線以上比例 · 最近 5 個交易日'));
      }else{
        const adv=Number.isFinite(r.advances)?r.advances:null;
        const dec=Number.isFinite(r.declines)?r.declines:null;
        const denom=adv!==null&&dec!==null?adv+dec:null;
        kpis.append(metric('累計騰落線',fmt(r.ad,0),r.date.slice(0,4)+' 年累計淨上漲家次'));
        kpis.append(metric('當日淨上漲',signed(r.net,0),'上漲 '+fmt(adv,0)+' ／ 下跌 '+fmt(dec,0)+' 家'));
        kpis.append(metric('上漲家數占比',denom>0?fmt(100*adv/denom)+'%':'—','上漲家數 ÷ (上漲＋下跌家數)'));
        kpis.append(metric('近 5 日淨變化',signed(change(source,idx,'ad',5),0),'近 10 日 '+signed(change(source,idx,'ad',10),0)+' 家次'));
      }
      markers.forEach(f=>f(idx));
    }
    const markers=[];
    function chart(series,config){
      const box=h('div','mb-plot');chartBox.append(box);
      const legend=h('div','mb-legend');box.append(legend);
      for(const line of series){const item=h('span','mb-legend-item',line.label);item.style.setProperty('--series',line.color);if(line.dashed)item.classList.add('mb-dashed');legend.append(item);}
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
      svg.setAttribute('viewBox','0 0 760 288');svg.setAttribute('role','img');svg.setAttribute('tabindex','0');
      svg.setAttribute('aria-label',isBreadth?'20 日與 60 日均線以上比例趨勢，可用左右方向鍵切換日期':'騰落線與加權指數比較，可用左右方向鍵切換日期');box.append(svg);
      const make=(tag,attrs={},label,host=svg)=>{const e=document.createElementNS(svg.namespaceURI,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,String(v));if(label!==undefined)e.textContent=label;host.append(e);return e;};
      const W=760,L=66,R=687,T=22,B=244;
      const x=i=>L+(R-L)*i/Math.max(1,shown.length-1);
      const yFor=(v,bounds)=>B-(v-bounds[0])/(bounds[1]-bounds[0]||1)*(B-T);
      function range(values,hard){
        if(hard)return hard;
        const nums=values.filter(Number.isFinite);
        if(!nums.length)return[0,1];
        let lo=Math.min(...nums),hi=Math.max(...nums);const pad=Math.max(1,(hi-lo)*.13);return[lo-pad,hi+pad];
      }
      const bounds=series.map(line=>range(shown.map(r=>line.value(r)),line.range));
      const primary=bounds[0];
      for(let i=0;i<5;i++){
        const v=primary[0]+(primary[1]-primary[0])*i/4;
        const y=yFor(v,primary);
        make('line',{x1:L,x2:R,y1:y,y2:y,class:'mb-grid-line'});
        make('text',{x:L-10,y:y+4,'text-anchor':'end',class:'mb-axis-text'},config.label(v));
      }
      if(series.length>1 && config.rightAxis){
        const b=bounds[1];for(let i=0;i<5;i++){
          const v=b[0]+(b[1]-b[0])*i/4;
          make('text',{x:R+8,y:yFor(v,b)+4,class:'mb-axis-text'},config.rightAxis(v));
        }
      }
      if(isBreadth){
        [15,85].forEach(v=>{
          const y=yFor(v,primary);
          make('line',{x1:L,x2:R,y1:y,y2:y,class:'mb-threshold-line'});
          make('text',{x:R-6,y:y-6,'text-anchor':'end',class:'mb-threshold-text'},v+'%');
        });
      }
      series.forEach((line,n)=>{
        let d='',open=false;
        shown.forEach((r,i)=>{
          const v=line.value(r);
          if(!r.complete||!Number.isFinite(v)){open=false;return;}
          d+=(open?' L ':'M ')+x(i).toFixed(2)+' '+yFor(v,bounds[n]).toFixed(2);open=true;
        });
        make('path',{d,fill:'none',stroke:line.color,'stroke-width':2.7,'stroke-linejoin':'round','stroke-linecap':'round', ...(line.dashed?{'stroke-dasharray':'7 5'}:{})});
      });
      make('text',{x:L,y:280,class:'mb-axis-text'},shown[0].date.slice(5));
      make('text',{x:(L+R)/2,y:280,'text-anchor':'middle',class:'mb-axis-text'},shown[Math.floor((shown.length-1)/2)].date.slice(5));
      make('text',{x:R,y:280,'text-anchor':'end',class:'mb-axis-text'},shown.at(-1).date.slice(5));
      const cross=make('line',{x1:0,x2:0,y1:T,y2:B,class:'mb-crosshair'});
      const points=series.map(line=>make('circle',{r:4.5,fill:line.color,stroke:'var(--card,#fff)','stroke-width':2}));
      function position(idx){
        const n=shown.findIndex(r=>r._idx===idx);if(n<0)return;
        hint.textContent = shown[n].date + ' · 左右滑動查價';
        cross.setAttribute('x1',x(n));cross.setAttribute('x2',x(n));
        points.forEach((p,k)=>{const v=series[k].value(shown[n]);if(!shown[n].complete||!Number.isFinite(v)){p.setAttribute('visibility','hidden');return;}p.setAttribute('visibility','visible');p.setAttribute('cx',x(n));p.setAttribute('cy',yFor(v,bounds[k]));});
      }
      markers.push(position);
      svg.style.touchAction = 'pan-y pinch-zoom';
      svg.style.userSelect = 'none';
      let activePointer = null;
      let lastPulse = -Infinity;
      function move(e) {
        const transform = svg.getScreenCTM();
        if (!transform) return;
        const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(transform.inverse());
        const fraction = Math.max(0, Math.min(1, (point.x - L) / (R - L)));
        const row = shown[Math.round(fraction * (shown.length - 1))];
        if (row._idx === focusIndex) return;
        update(row);
        if (activePointer === e.pointerId && e.pointerType !== 'mouse' &&
            typeof navigator.vibrate === 'function' && performance.now() - lastPulse >= 55) {
          navigator.vibrate(8);
          lastPulse = performance.now();
        }
      }
      svg.addEventListener('pointerdown', e => {
        if (!e.isPrimary || e.button !== 0) return;
        activePointer = e.pointerId;
        svg.setPointerCapture(e.pointerId);
        move(e);
      });
      svg.addEventListener('pointermove', e => {
        if (e.pointerId === activePointer || (activePointer === null && e.pointerType === 'mouse')) move(e);
      });
      function release(e) {
        if (activePointer === e.pointerId) activePointer = null;
      }
      for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        svg.addEventListener(event, release);
      }
      svg.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const at=Math.max(0,shown.findIndex(r=>r._idx===focusIndex));update(shown[Math.max(0,Math.min(shown.length-1,at+(e.key==='ArrowLeft'?-1:1)))]);}});
    }
    if(isBreadth){
      chart(windows.map(n=>({label:n+' 日線以上',color:n===20?'#1686a3':'#d08b35',dashed:n===60,range:[0,100],value:r=>r['pct'+n]})),{label:v=>fmt(v,0)+'%'});
    }else{
      // Difference chart: index is normalized to first available point, AD shows change from same starting point.
      const indexKey=market.value==='all'?'index_twse':'index';
      const base=shown.find(r=>r.complete && Number.isFinite(r.ad) && Number.isFinite(r[indexKey]) && r[indexKey]>0);
      if(base){
        const labels=market.value==='tpex'?'櫃買指數':'加權指數';
        chart([
          {label:'騰落線變化（家次）',color:'#1686a3',value:r=>Number.isFinite(r.ad)?r.ad-base.ad:null},
          {label:labels+'漲跌幅（%）',color:'#d08b35',dashed:true,value:r=>Number.isFinite(r[indexKey])?100*(r[indexKey]/base[indexKey]-1):null}
        ],{label:v=>fmt(v,0),rightAxis:v=>fmt(v,1)+'%'});
      }else chart([{label:'累計騰落線',color:'#1686a3',value:r=>r.ad}],{label:v=>fmt(v,0)});
    }
    if(isBreadth && windows.length===2){
      const basisLabel=h('label','mb-table-basis','變化依據');
      const basis=h('select','','');basis.setAttribute('aria-label','每日明細變化指標');
      for(const n of [20,60])basis.add(new Option(n+' 日市場寬度',String(n)));
      basis.value=String(detailBasis);
      basis.addEventListener('change',()=>{detailBasis=Number(basis.value);render();});
      basisLabel.append(basis);bottom.insertBefore(basisLabel,details);
    }
    const basisWindow=windows.length===1?windows[0]:detailBasis;
    const pp=(r,i,d)=>{const val=change(source,i,'pct'+basisWindow,d);return val===null?'—':signed(val)+' pp';};
    const columns=isBreadth ? [
      ...windows.map(n=>({label:n+' 日線以上',get:r=>Number.isFinite(r['pct'+n])?fmt(r['pct'+n])+'%':'—'})),
      {label:'5 日變化',get:(r,i)=>pp(r,i,5)},
      {label:'10 日變化',get:(r,i)=>pp(r,i,10)}
    ] : [
      {label:'上漲',get:r=>fmt(r.advances,0)}, {label:'下跌',get:r=>fmt(r.declines,0)},
      {label:'當日淨值',get:r=>signed(r.net,0)}, {label:'累計騰落線',get:r=>fmt(r.ad,0)},
      {label:'5 日變化',get:(r,i)=>signed(change(source,i,'ad',5),0)},
      {label:'10 日變化',get:(r,i)=>signed(change(source,i,'ad',10),0)}
    ];
    // Show only the metrics requested; underlying above/eligible counts remain in source for quality checks.
    const wrap=h('div','mb-scroll');wrap.tabIndex=0;
    const table=h('table','mb-daily-table');
    const thead=table.createTHead().insertRow();
    const th=h('th','', '日期');th.scope='col';thead.append(th);
    for(const c of columns){const th=h('th','',c.label);th.scope='col';thead.append(th);}
    const tbody=table.createTBody();
    for(const r of [...shown].reverse()){
      const tr=tbody.insertRow();
      const day=h('th','',r.date);day.scope='row';tr.append(day);
      for(const c of columns){const td=tr.insertCell();td.textContent=c.get(r,r._idx);if(/^[+-]/.test(td.textContent))td.classList.add(td.textContent[0]==='+'?'mb-positive':'mb-negative');}
    }
    wrap.append(table);details.append(wrap);details.open=detailsOpen;
    details.addEventListener('toggle',()=>{detailsOpen=details.open;});
    update(active);
  }
  market.addEventListener('change',()=>{syncAdYears();render();});
  breadthYear.addEventListener('change',()=>{period.value='0';render();});
  adYear.addEventListener('change',render);
  period.addEventListener('change',render);
  windowSelect.addEventListener('change',render);
  select(0);
})();
