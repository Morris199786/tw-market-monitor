async function loadTaiwanMonitorArchive(kind) {
  const response = await fetch('./data/history/monitor-' + kind + '-2008-2023.json', {cache:'no-cache'});
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

const twRiskNames = ['🟢 綠燈', '🟡 黃燈', '🟠 黃紅燈', '🔴 紅燈'];
let twRiskByDate = new Map();
let twBreadthRequest;

function buildTwRisk(funds, breadth) {
  const fundMap = new Map(funds.map(row => [row.date, row]));
  const breadthMap = new Map(breadth.map(row => [row.date, row]));
  const dates = [...new Set([...fundMap.keys(), ...breadthMap.keys()])].sort();
  const validLight = value => ['normal', 'yellow', 'red'].includes(value);
  const validPct = value => Number.isFinite(value) && value >= 0 && value <= 100;
  const results = new Map();
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
      || !validLight(f.foreign_light) || !validLight(f.margin_light)) continue;

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
    const level = red ? 3 : orange ? 2 : yellow ? 1 : 0;
    results.set(date, {level, fundRedDays, net, pct20:b.pct20, pct60:b.pct60,
      foreign:f.foreign_light, margin:f.margin_light, intersection:f.intersection});
  }
  return results;
}

function paintTwRisk(date) {
  const card = document.querySelector('[data-tw-risk]');
  if (!card) return;
  const r = twRiskByDate.get(date);
  card.querySelector('strong').textContent = r ? twRiskNames[r.level] : '資料待齊';
  card.querySelector('small').textContent = date || '';
  card.querySelector('[data-summary]').textContent = r
    ? ['未觸發警戒條件', '指數接近高點，市場參與度下降且融資偏熱', '資金壓力與盤面弱勢同時出現', '資金交集持續亮紅，市場廣度轉弱'][r.level] : '等待同日完整資料與計算期數';
  const labels = {normal:'正常', yellow:'黃燈', red:'紅燈'};
  card.querySelector('[data-factors]').textContent = r
    ? `外資 ${labels[r.foreign]} ｜ 融資 ${labels[r.margin]} ｜ 站上 20 日線 ${r.pct20.toFixed(1)}%、60 日線 ${r.pct60.toFixed(1)}% ｜ 資金交集 ${labels[r.intersection]}（近 5 日 ${r.fundRedDays} 日紅燈） ｜ 近 5 日累計漲跌淨家數 ${r.net.toLocaleString('zh-TW')}` : '';
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
    const scope = categories.length ? '上市全市場｜官方外資分類：' + categories.join('、') : dataset.scope;
    root.querySelector('[data-mm-status]').textContent =
      `資料截至 ${dataset.as_of_date || '尚無資料'}｜${scope || ''}｜${coverage}｜更新 ${dataset.updated_at || '—'}${dataset.archiveWarning || ''}`;

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

              <td class="mm-composite">
                ${twRiskNames[twRiskByDate.get(r.date)?.level] || '資料待齊'}
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
        twRiskByDate = new Map();
        twBreadthRequest = null;
        const breadth = await getTwBreadth().catch(() => null);
        if (breadth) twRiskByDate = buildTwRisk(dataset.rows, breadth.series.all || []);
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
  tw.append(flow.querySelector('[data-tw-risk]'), nav, flow, panel);
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
  const names = ['資金籌碼','騰落線','市場寬度'];
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
    flow.hidden=i!==0;panel.hidden=i===0;
    if(!i)return;
    panel.querySelector('[data-mb-title]').textContent=names[i];
    panel.querySelector('[data-mb-subtitle]').textContent=i===1?'累計漲跌家數與指數對照，辨識市場廣度背離':'20／60 日均線以上股票占比，追蹤市場參與程度';
    panel.querySelector('.mb-breadth-year-filter').hidden=i!==2;
    panel.querySelector('.mb-window-filter').hidden=i!==2;
    panel.querySelector('.mb-ad-year-filter').hidden=i!==1;
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
    if(!data||!mode)return;
    const rawSource=data.series[market.value]||[];
    const source=mode===1?yearlyAd(rawSource):rawSource;
    const desiredYear=mode===1?adYear.value:breadthYear.value;
    const yearRows=desiredYear?source.filter(r=>r.date?.slice(0,4)===desiredYear):source;
    const last=yearRows.at(-1);
    const key=[mode,market.value,period.value,windowSelect.value,desiredYear].join('/');
    if(key!==lastViewKey){focusIndex=null;lastViewKey=key;}
    if(!last){content.textContent='尚無交易日資料';return;}
    const isBreadth=mode===2;
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



