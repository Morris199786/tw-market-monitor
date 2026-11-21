async function loadTaiwanMonitorArchive(kind) {
  const response = await fetch('./data/history/monitor-' + kind + '-2008-2023.json', {cache:'no-cache'});
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

const twRiskNames = ['🟢 綠燈', '🟡 黃燈', '🟠 橘燈', '🔴 紅燈'];
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

// V12 candidate implementation. Matches the V7 weight definitions + extreme 5d foreign Z bonus.
// Uses only prior market data in rolling statistics; no future prices or prices from an event trough.
const TW_RISK_MODEL = Object.freeze({name:'V12 研究候選',yellow:38,orange:52,red:65,redExit:60,
  extremeForeignZ:-2, extremeBonus:3});
const riskClamp = x => Math.max(0,Math.min(100,x));
function buildTwRisk(funds,breadth){
  const fundMap=new Map(funds.map(x=>[x.date,x]));
  const breadMap=new Map(breadth.map(x=>[x.date,x]));
  const dates=[...fundMap.keys()].sort();
  const valid=n=>Number.isFinite(n);
  const sum=xs=>xs.reduce((a,x)=>a+x,0);
  const data=[],results=new Map();
  let lastState=0;
  for(let i=0;i<dates.length;i++){
    const date=dates[i],f=fundMap.get(date),b=breadMap.get(date);
    const fWindow=n=>dates.slice(Math.max(0,i-n+1),i+1).map(d=>fundMap.get(d));
    const bWindow=n=>dates.slice(Math.max(0,i-n+1),i+1).map(d=>breadMap.get(d));
    const prices=fWindow(120).map(x=>x?.index);
    const priorForeign=fWindow(5);
    const need=[b?.pct20,b?.pct60,f?.foreign,f?.index];
    if(i<125 || need.some(x=>!valid(x)) || !b?.complete || !['normal','yellow','red'].includes(f?.foreign_light)
      || priorForeign.length!==5 || !priorForeign.every(x=>valid(x?.foreign)&&['normal','yellow','red'].includes(x?.foreign_light))
      || prices.length<120 || prices.some(x=>!valid(x)||x<=0)
      || !bWindow(11).every(x=>x?.complete&&valid(x?.pct20))){
      data.push({date,valid:false});
      // Do not silently fabricate a green day; incomplete sessions also break the rolling signal.
      lastState=0;
      continue;
    }
    const high=Math.max(...prices),dd=100*(1-f.index/high);
    const b5=bWindow(6),b10=bWindow(11);
    const drop5=b5[0].pct20-b.pct20,drop10=b10[0].pct20-b.pct20;
    const foreign5=fWindow(5);
    const foreignWarn5=foreign5.filter(x=>x.foreign_light==='yellow'||x.foreign_light==='red').length;
    const foreignRed5=foreign5.filter(x=>x.foreign_light==='red').length;
    const speed=riskClamp(100*Math.max((drop5-5)/25,(drop10-8)/35));
    const foreignRisk=riskClamp(Math.max(100*(foreignWarn5-1)/4,100*(foreignRed5-.2)/3));
    const breadthRisk=riskClamp(100*(60-b.pct20)/45);
    const priceRisk=riskClamp(100*(dd-1)/13);
    const base=.35*speed+.25*foreignRisk+.2*breadthRisk+.2*priceRisk;
    const earlier=data.slice(Math.max(0,i-10),i);
    const accumulated=Math.min(6,earlier.filter(x=>x.valid&&x.base>=42).length)*2;
    const sequence=earlier.some(x=>x.valid&&x.foreignWarn5>=3) && drop5>=12 ? 4:0;
    // Strict prior 60 observations for the 5-day foreign balance: no current data in baseline.
    const foreignSum5=sum(foreign5.map(x=>x.foreign));
    const prior=[];
    for(let j=i-60;j<i;j++){
      if(j<4){prior.length=0;break;}
      const win=dates.slice(j-4,j+1).map(d=>fundMap.get(d)?.foreign);
      if(win.length!==5 || !win.every(valid)){prior.length=0;break;}
      prior.push(sum(win));
    }
    let z5=null;
    if(prior.length===60 && valid(foreignSum5)){
      const mu=sum(prior)/60;
      const sigma=Math.sqrt(sum(prior.map(n=>(n-mu)**2))/60);
      if(sigma>0)z5=(foreignSum5-mu)/sigma;
    }
    const bonus=z5!==null && z5<=TW_RISK_MODEL.extremeForeignZ?TW_RISK_MODEL.extremeBonus:0;
    const score=base+accumulated+sequence+bonus;
    const trigger=score>=TW_RISK_MODEL.red?3:score>=TW_RISK_MODEL.orange?2:score>=TW_RISK_MODEL.yellow?1:0;
    // Entry 65 / exit 60: hysteresis is based on the current composite score, not a fixed holding period.
    const level=lastState===3 && score>=TW_RISK_MODEL.redExit?3:trigger;
    const ma10=sum(fWindow(10).map(x=>x.index))/10;
    const marginChange=valid(f.margin)&&valid(f.margin_previous)?(f.margin-f.margin_previous)/1e8:null;
    const nets=bWindow(5).map(x=>x?.complete?x.net:null);
    const net5=nets.length===5&&nets.every(valid)?sum(nets):null;
    const components={speed:+(.35*speed).toFixed(2),foreign:+(.25*foreignRisk).toFixed(2),breadth:+(.2*breadthRisk).toFixed(2),price:+(.2*priceRisk).toFixed(2),memory:accumulated,sequence,foreignZBonus:bonus};
    const basis=`${TW_RISK_MODEL.name}｜風險 ${score.toFixed(1)} 分（速度 ${components.speed}、外資 ${components.foreign}、廣度 ${components.breadth}、價格 ${components.price}、累積 ${accumulated}、序列 ${sequence}、極端外資 ${bonus}）。外資五日 Z ${z5===null?'待齊':z5.toFixed(2)}；20 日廣度 ${b.pct20.toFixed(1)}%，5 日下降 ${drop5.toFixed(1)}pp；距 120 日高點 ${dd.toFixed(2)}%；收盤 ${f.index.toFixed(2)}、10 日線 ${ma10.toFixed(2)}。${lastState===3&&score>=60&&score<65?'紅燈維持：分數尚未低於 60。':''}`;
    const reason=level===3?`綜合風險 ${score.toFixed(1)} 分，市場處於高度警戒。`:level===2?`風險累積至 ${score.toFixed(1)} 分，進入橘燈觀察。`:level===1?`風險 ${score.toFixed(1)} 分，出現初步警訊。`:`風險 ${score.toFixed(1)} 分，暫未達警戒門檻。`;
    const prevScore1=data.at(-1)?.valid?data.at(-1).score:null;
    const prevScore5=data[i-5]?.valid?data[i-5].score:null;
    const item={date,valid:true,level,trigger,score,base,foreignWarn5,foreignRed5,prevScore1,prevScore5,reason,basis,dd,
      pct20:b.pct20,pct60:b.pct60,drop5,drop10,net:net5,foreign5:foreignSum5,z5,
      marginChange,margin:f.margin,relative5:f.relative5,relative20:f.relative20,
      index:f.index,ma10,foreign:f.foreign_light,marginLight:f.margin_light,components};
    data.push(item);results.set(date,item);lastState=level;
  }
  return results;
}
function paintTwRisk(date){
 const card=document.querySelector('[data-tw-risk]');if(!card)return;
 const risk=twRiskByDate.get(date);
 card.dataset.riskLevel=risk?String(risk.level):'unknown';
 card.classList.add('mm-risk-card');card.setAttribute('aria-live','polite');
 const strong=card.querySelector('strong'),stamp=card.querySelector('small');
 if(strong)strong.textContent=risk?twRiskNames[risk.level]:'資料待齊';
 if(stamp)stamp.textContent=date||'';
 const summary=card.querySelector('[data-summary]');if(summary){
   summary.replaceChildren();
   summary.append(document.createTextNode(risk?risk.reason:'等待完整的歷史價格、外資及市場廣度資料'));
   if(risk){
     const d1=Number.isFinite(risk.prevScore1)?risk.score-risk.prevScore1:null;
     const d5=Number.isFinite(risk.prevScore5)?risk.score-risk.prevScore5:null;
     const trend=document.createElement('div');trend.className='mm-risk-trend';
     const asText=v=>Number.isFinite(v)?(v>=0?'+':'')+v.toFixed(1)+' 分':'資料不足';
     const diff=(label,v)=>{const el=document.createElement('span');el.textContent=label+' '+asText(v);el.className=Number.isFinite(v)?(v>0?'mm-trend-worse':v<0?'mm-trend-better':'mm-trend-flat'):'mm-trend-flat';return el;};
     trend.append(diff('1 日變化',d1),diff('5 日變化',d5));summary.append(trend);
     const riskSeries=[...twRiskByDate.values()].filter(x=>x.date<=date).sort((a,b)=>a.date.localeCompare(b.date));
     let start=null,maxScore=null,redDays=0,neutralStreak=0;
     for(let i=riskSeries.length-1;i>=0;i--){
       const item=riskSeries[i];
       if(item.level===0){neutralStreak++;if(neutralStreak>=3)break;continue;}
       neutralStreak=0;start=item.date;
       maxScore=Math.max(maxScore===null?0:maxScore,item.score);
       if(item.level===3)redDays++;
     }
     if(start){const episode=document.createElement('p');episode.className='mm-risk-episode';
       episode.textContent='本次連續警戒：'+start+' 起｜最高 '+maxScore.toFixed(1)+' 分｜紅燈 '+redDays+' 日（以連續 3 個綠燈交易日分隔警戒事件）';
       summary.append(episode);
     }
   }
 }
 const factors=card.querySelector('[data-factors]');if(factors)factors.textContent=risk?risk.basis:'';
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
  details.insertAdjacentHTML('beforeend', `<p><b>V12 研究候選｜加權風險</b>　風險分數使用 20 日市場廣度變化速度 35%、外資持續性 25%、20 日廣度水準 20%、指數距近 120 日高點回撤 20%，另加 10 日內警訊累積與資金／廣度先後惡化分數。</p><p><b>外資五日 Z-score</b>：五日累計外資淨買賣超相對過去 60 個交易日同指標之標準化異常程度；均值與標準差均排除當日。Z ≤ -2.0 加 3 分。融資單項仍獨立呈現，但不再是綜合燈號的必要條件。</p><p><b>黃燈 38／橘燈 52／紅燈 65 分</b>。紅燈退出門檻 60 分；每日依風險分數升降級，不固定鎖定數天。燈號可跳級，沒有單一外資或融資的必要條件。資料不足顯示待齊而非綠燈。</p><p>此為研究候選 V12，不是具備樣本外充分驗證的投資建議。歷史警示時間軸使用這套公式重算，不沿用舊模型的燈號日期。</p>`);
  riskCard.classList.add('mm-risk-card');
  riskCard.setAttribute('aria-live', 'polite');
  const composite = document.createElement('section');
  composite.className = 'mm-composite-page';
  composite.setAttribute('aria-label', '綜合指標每日監控');
  composite.innerHTML = `
    <div class="mm-composite-intro"><span class="mb-eyebrow">COMPOSITE SIGNAL · V12 RESEARCH</span><h2>綜合指標</h2>
      <p>四級風險評分｜主表保留原始數據｜點燈號展開加工指標與分數；日期欄固定。</p></div>
    <div class="mm-composite-filters">
      <label>年份 <select data-composite-year aria-label="綜合指標年份"></select></label>
      <label>月份 <select data-composite-month aria-label="綜合指標月份"></select></label>
      <button type="button" data-composite-refresh>重新整理</button>
    </div>
    <div class="mm-composite-status" data-composite-status role="status">資料載入中…</div>
    <p class="mm-table-hint">⇆ 左右滑動查看原始數據；上下使用網頁捲動</p>
    <div class="mm-composite-scroll" tabindex="0" role="region" aria-label="每日綜合原始指標，左右滑動，頁面上下捲動">
      <table class="mm-composite-table"><thead><tr>
        <th scope="col">日期／燈號<br>綜合分數</th>
        <th scope="col">加權指數<br>收盤</th>
        <th scope="col">外資日<br>買賣超（億）</th>
        <th scope="col">融資餘額<br>（億）</th>
        <th scope="col">融資日增減<br>（億）</th>
        <th scope="col">20 日<br>市場廣度</th>
        <th scope="col">60 日<br>市場廣度</th>
        <th scope="col">當日<br>騰落淨家數</th>
      </tr></thead><tbody></tbody></table>
    </div>
    <p class="mm-composite-footnote">主表僅呈現原始數據：日期燈號下顯示分數；點日期燈號可展開外資 Z-score、融資相對強弱、廣度變化、價格回撤與所有風險分數貢獻。缺資料不補零。</p>
    <section class="mm-history" aria-label="歷史重大跌勢燈號回測">
      <div class="mm-history-heading"><div><span class="mb-eyebrow">HISTORICAL DRAWDOWNS</span><h2>歷史重大跌勢｜燈號時間軸</h2><p>按歷史區間自動計算高低點及候選模型首次黃／橘／紅燈；事件名稱是市場背景說明，不代表單一成因。</p></div></div>
      <div class="mm-history-filters"><label>警報分類 <select data-history-filter aria-label="歷史跌勢警報篩選"><option value="all">全部跌勢</option><option value="early">紅燈：回撤 5% 前</option><option value="mid">紅燈：回撤 5～10%</option><option value="late">紅燈：回撤 10% 後</option><option value="miss">未亮紅燈</option></select></label><span data-history-count></span></div>
      <div class="mm-history-list" data-mm-history><p class="mm-history-empty">歷史資料載入後顯示。</p></div>
    </section>`;
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
  // All displayed risk columns are read directly from the same daily model used by the summary card.
  const compYear=composite.querySelector('[data-composite-year]');
  const compMonth=composite.querySelector('[data-composite-month]');
  const compStatus=composite.querySelector('[data-composite-status]');
  const compBody=composite.querySelector('.mm-composite-table tbody');
  const fmtRisk=(v,n=1,suffix='')=>Number.isFinite(v)?v.toLocaleString('zh-TW',{minimumFractionDigits:n,maximumFractionDigits:n})+suffix:'—';
  const riskTone=(v,badBelow)=>Number.isFinite(v)?(badBelow?v<0:v>0)?'mm-cbad':'':'';
  const riskNum=(n,d=1,suffix='')=>Number.isFinite(n)?fmtRisk(n,d,suffix):'—';
  const rawNum=(n,d=1,suffix='')=>Number.isFinite(n)?fmtRisk(n,d,suffix):'—';
  function appendMetric(section,label,value){
    const line=h('div','mm-detail-metric');line.append(h('span','',label),h('b','',value));section.append(line);
  }
  function makeDailyDetails(r,f,b){
    const body=h('div','mm-detail-grid');
    const group=(name)=>{const sect=h('section','mm-detail-group');sect.append(h('h4','',name));body.append(sect);return sect;};
    const money=group('外資買賣超｜加工分析');
    appendMetric(money,'近 5 日累計（億）',riskNum(r.foreign5,2));
    appendMetric(money,'5 日 Z-score（過去 60 日）',riskNum(r.z5,2));
    appendMetric(money,'5 日內黃／紅警戒日數',r.foreignWarn5+'/5');
    appendMetric(money,'5 日內紅燈日數',r.foreignRed5+'/5');
    appendMetric(money,'外資原始燈號',{'red':'紅燈','yellow':'黃燈','normal':'正常'}[f.foreign_light]||'待齊');
    const margin=group('融資｜加工分析');
    appendMetric(margin,'相對指數 5 日強弱',riskNum(r.relative5,2,' pp'));
    appendMetric(margin,'相對指數 20 日強弱',riskNum(r.relative20,2,' pp'));
    appendMetric(margin,'融資原始燈號',{'red':'紅燈','yellow':'黃燈','normal':'正常'}[r.marginLight]||'待齊');
    const breadth=group('市場廣度／騰落｜加工分析');
    appendMetric(breadth,'20 日廣度 5 日變化',riskNum(-r.drop5,1,' pp'));
    appendMetric(breadth,'20 日廣度 10 日變化',riskNum(-r.drop10,1,' pp'));
    appendMetric(breadth,'近 5 日累計騰落淨家數',riskNum(r.net,0));
    appendMetric(breadth,'距近 120 日高點回撤',riskNum(r.dd,2,'%'));
    appendMetric(breadth,'收盤站上 10 日均線',r.index>=r.ma10?'是':'否');
    appendMetric(breadth,'10 日均線',riskNum(r.ma10,2));
    const parts=group('綜合風險｜評分貢獻');
    appendMetric(parts,'當日綜合分數',riskNum(r.score,1,' / 100'));
    const c=r.components;
    for(const [label,val] of [['廣度速度',c.speed],['外資持續性',c.foreign],['廣度絕對水準',c.breadth],['價格回撤',c.price],['警報累積',c.memory],['序列惡化',c.sequence],['極端外資加分',c.foreignZBonus]])appendMetric(parts,label,riskNum(val,2,' 分'));
    const note=h('p','mm-detail-note',r.basis);body.append(note);
    return body;
  }
  function renderComposite(){
    if(!twCompositeFunds.length){compStatus.textContent='資金與市場廣度資料尚未載入。';compBody.replaceChildren();return;}
    const funds=[...twCompositeFunds].sort((a,b)=>a.date.localeCompare(b.date));
    const breadth=new Map(twCompositeBreadth.map(x=>[x.date,x]));
    const years=[...new Set(funds.map(r=>r.date.slice(0,4)))].sort().reverse();
    const newest=funds.at(-1)?.date||'';
    const y=compYear.value,m=compMonth.value;
    compYear.replaceChildren(...years.map(y=>new Option(y+'年',y)));
    compYear.value=years.includes(y)?y:newest.slice(0,4);
    const months=Array.from({length:12},(_,i)=>String(i+1).padStart(2,'0'));
    compMonth.replaceChildren(...months.map(m=>new Option(Number(m)+'月',m)));
    const available=funds.filter(r=>r.date.startsWith(compYear.value)).map(r=>r.date.slice(5,7));
    compMonth.value=(y===compYear.value&&months.includes(m))?m:(available.at(-1)||'01');
    const selected=funds.filter(r=>r.date.startsWith(compYear.value+'-'+compMonth.value));
    const columnCount=composite.querySelectorAll('.mm-composite-table thead th').length;
    compBody.replaceChildren();let calculated=0;
    const cell=(tr,value,digits=1,suffix='',tone='')=>{const td=tr.insertCell();td.textContent=rawNum(value,digits,suffix);if(tone)td.className=tone;return td;};
    for(const f of selected){
      const d=f.date,r=twRiskByDate.get(d),b=breadth.get(d),tr=compBody.insertRow();
      const day=h('th','mm-composite-date',d.slice(5).replace('-','/'));day.scope='row';tr.append(day);
      if(r){
        calculated++;
        const btn=h('button','mm-day-light light-'+r.level,['綠燈','黃燈','橘燈','紅燈'][r.level]);
        btn.type='button';btn.setAttribute('aria-expanded','false');btn.setAttribute('aria-label',d+' '+btn.textContent+'，展開原始數據加工分析及評分');
        day.append(btn,h('small','mm-day-score',fmtRisk(r.score,1)+' 分'));
        cell(tr,r.index,2);cell(tr,f.foreign,2,'',f.foreign<0?'mm-cbad':'');
        cell(tr,Number.isFinite(r.margin)?r.margin/1e8:null,2);
        cell(tr,r.marginChange,2,'',r.marginChange>0?'mm-cwarn':'');
        cell(tr,r.pct20,1,'%',r.pct20<40?'mm-cwarn':'');
        cell(tr,r.pct60,1,'%');
        cell(tr,b?.complete?b.net:null,0);
        const detail=compBody.insertRow();detail.className='mm-day-detail';detail.hidden=true;
        const desc=detail.insertCell();desc.colSpan=columnCount;desc.append(makeDailyDetails(r,f,b));
        btn.setAttribute('aria-controls','mm-detail-'+d);detail.id='mm-detail-'+d;
        btn.addEventListener('click',()=>{
          const opened=detail.hidden;
          for(const e of compBody.querySelectorAll('.mm-day-detail'))e.hidden=true;
          for(const e of compBody.querySelectorAll('[aria-expanded="true"]'))e.setAttribute('aria-expanded','false');
          detail.hidden=!opened;btn.setAttribute('aria-expanded',String(opened));
        });
      }else{
        day.append(h('small','','待齊'));
        cell(tr,f.index,2);cell(tr,f.foreign,2);
        cell(tr,Number.isFinite(f.margin)?f.margin/1e8:null,2);
        cell(tr,Number.isFinite(f.margin)&&Number.isFinite(f.margin_previous)?(f.margin-f.margin_previous)/1e8:null,2);
        cell(tr,b?.complete?b.pct20:null,1,'%');cell(tr,b?.complete?b.pct60:null,1,'%');cell(tr,b?.complete?b.net:null,0);
      }
    }
    if(!selected.length){const tr=compBody.insertRow(),td=tr.insertCell();td.colSpan=columnCount;td.textContent='本月尚無交易日資料';}
    compStatus.textContent=compYear.value+'年'+Number(compMonth.value)+'月｜'+selected.length+'個交易日｜可計算燈號 '+calculated+' 日｜資料截至 '+newest+'｜V12（研究候選）';
  }
  compYear.addEventListener('change',()=>{compMonth.value='';renderComposite();});
  compMonth.addEventListener('change',renderComposite);
  composite.querySelector('[data-composite-refresh]').addEventListener('click',()=>{
    const button=flow.querySelector('.mm-tools button');if(button)button.click();
  });
  document.addEventListener('tw-composite-data-updated',()=>{if(mode===0)renderComposite();renderHistory();});

  // Historical intervals are contextual groupings, not tuned model inputs.
  // Peaks/troughs and lamps are derived from the date-matched source series at runtime.
  const historyEvents=[
    {id:'2008',title:'全球金融海嘯（雷曼危機）',peakStart:'2008-01-02',peakEnd:'2008-06-30',end:'2009-01-30'},
    {id:'2011',title:'歐債危機與美國信評調降',peakStart:'2011-01-03',peakEnd:'2011-07-29',end:'2011-12-30'},
    {id:'2012',title:'歐債危機延燒',peakStart:'2012-02-01',peakEnd:'2012-04-10',end:'2012-06-15'},
    {id:'2015',title:'中國股災與全球股市震盪',peakStart:'2015-03-02',peakEnd:'2015-05-15',end:'2015-09-30'},
    {id:'2018',title:'中美貿易戰與全球升息',peakStart:'2018-05-01',peakEnd:'2018-07-10',end:'2019-01-31'},
    {id:'2020',title:'COVID-19 疫情股災',peakStart:'2020-01-02',peakEnd:'2020-02-21',end:'2020-04-10'},
    {id:'2022',title:'全球通膨與升息衝擊',peakStart:'2021-12-01',peakEnd:'2022-02-15',end:'2022-11-15'},
    {id:'2024',title:'科技股回檔與日圓套利交易平倉',peakStart:'2024-06-03',peakEnd:'2024-07-31',end:'2024-08-30'},
    {id:'2025',title:'美國關稅政策衝擊',peakStart:'2025-01-02',peakEnd:'2025-03-10',end:'2025-04-30'},
    {id:'2026-6',title:'去槓桿',peakStart:'2026-06-22',peakEnd:'2026-06-22',end:'2026-08-07'},
    {id:'2026-11',title:'AI 估值修正＋升息預期',peakStart:'2026-09-01',peakEnd:'2026-10-14',end:null,ongoing:true}
  ];
  const historyHost=composite.querySelector('[data-mm-history]');
  const historyFilter=composite.querySelector('[data-history-filter]');
  const historyCount=composite.querySelector('[data-history-count]');
  let historyRenderedKey='';
  const datePct=(a,b)=>100*(b/a-1);
  const stampFormat=v=>String(v||'').slice(5);
  function renderHistory(){
    const funds=[...twCompositeFunds].filter(x=>Number.isFinite(x.index)).sort((a,b)=>a.date.localeCompare(b.date));
    if(!funds.length)return;
    const filter=historyFilter.value;
    const key=funds.length+'-'+funds.at(-1).date+'-'+funds.at(-1).index+'-'+twRiskByDate.size+'-'+filter;
    if(key===historyRenderedKey)return;historyRenderedKey=key;
    const savedOpen=new Set([...historyHost.querySelectorAll('details[open]')].map(x=>x.dataset.event));
    historyHost.replaceChildren();let count=0;
    for(const event of historyEvents){
      const peaks=funds.filter(x=>x.date>=event.peakStart&&x.date<=event.peakEnd);
      if(!peaks.length)continue;
      const peak=peaks.reduce((a,b)=>b.index>a.index?b:a);
      // Ongoing episodes must never stop at a hard-coded calendar year boundary.
      const endDate=event.ongoing?funds.at(-1).date:(funds.at(-1).date<event.end?funds.at(-1).date:event.end);
      let period=funds.filter(x=>x.date>=peak.date&&x.date<=endDate);
      if(period.length<5)continue;
      // For ongoing events: confirm recovery only when 10 consecutive sessions
      // close within 5% of the episode peak. Do not infer finality from 12/31.
      let recovery=0,closedAt=null;
      if(event.ongoing){
        for(let k=1;k<period.length;k++){
          recovery=datePct(peak.index,period[k].index)>-5?recovery+1:0;
          if(recovery>=10){closedAt=period[k].date;period=period.slice(0,k+1);break;}
        }
      }
      const trough=period.reduce((a,b)=>b.index<a.index?b:a);
      if(trough.date===peak.date)continue;
      const path=period.filter(x=>x.date<=trough.date);
      const drawdown=datePct(peak.index,trough.index);
      if(drawdown>-10)continue;
      const report={};
      for(const [level,name] of [[1,'黃燈'],[2,'橘燈'],[3,'紅燈']]){
        const found=path.find(x=>{const r=twRiskByDate.get(x.date);return r&&r.level>=level;});
        report[level]=found?{date:found.date,drop:datePct(peak.index,found.index),after:datePct(found.index,trough.index),name}:null;
      }
      const red=report[3],classify=!red?'miss':red.drop>=-5?'early':red.drop>=-10?'mid':'late';
      if(filter!=='all'&&filter!==classify)continue;
      count++;
      const card=document.createElement('details');card.className='mm-history-card';card.dataset.event=event.id;
      if(savedOpen.has(event.id))card.open=true;
      const sm=document.createElement('summary');sm.className='mm-history-summary';
      sm.append(h('b','mm-history-year',event.id.startsWith('2026-')?'2026 年':event.id+' 年'),
        h('span','mm-history-title',event.title),h('strong','mm-history-drop',drawdown.toFixed(2)+'%'));
      if(event.ongoing&&!closedAt)sm.append(h('span','mm-history-status','進行中'));
      card.append(sm);
      const body=h('div','mm-history-body');
      body.append(h('p','mm-history-peaks','高點 '+fmtRisk(peak.index,2)+'（'+peak.date+'） → '+(event.ongoing&&!closedAt?'暫定':'')+'低點 '+fmtRisk(trough.index,2)+'（'+trough.date+'）'));
      // Separate signal lanes: points and dates never occupy the same horizontal text row.
      const stage=h('div','mm-timeline');
      const signals=[{name:'高點',date:peak.date,drop:0,after:null,level:'neutral',kind:'peak'},
        ...[1,2,3].filter(level=>report[level]).map(level=>({...report[level],level:['','yellow','orange','red'][level],kind:'signal'})),
        {name:'低點',date:trough.date,drop:drawdown,after:null,level:'neutral',kind:'trough'}];
      for(const signal of signals){
        const i=path.findIndex(x=>x.date===signal.date);
        const lane=h('div','mm-timeline-lane mm-lane-'+signal.level);
        const label=h('span','mm-timeline-name',signal.name);
        const track=h('div','mm-timeline-track');
        const fill=h('div','mm-timeline-fill');fill.style.width=(100*i/Math.max(1,path.length-1))+'%';track.append(fill);
        const dot=h('span','mm-timeline-dot');dot.style.left=(100*i/Math.max(1,path.length-1))+'%';track.append(dot);
        const readout=h('div','mm-timeline-readout');
        readout.append(h('b','',signal.drop.toFixed(2)+'%'),h('small','',stampFormat(signal.date)));
        lane.append(label,track,readout);stage.append(lane);
      }
      body.append(stage);
      const outcomes=h('div','mm-history-outcomes');
      for(const level of [1,2,3]){
        const mark=report[level];const label=['','黃燈','橘燈','紅燈'][level];
        const outcome=h('div','mm-history-outcome');
        outcome.append(h('b','',label),h('span','',mark?mark.date+'｜當時已跌 '+Math.abs(mark.drop).toFixed(2)+'%｜之後至低點再跌 '+Math.abs(mark.after).toFixed(2)+'%':'區間內沒有觸發'));
        body.append(outcome);
      }
      const redDays=red?Math.max(0,path.length-1-path.findIndex(x=>x.date===red.date)):null;
      const quality=h('p','mm-history-quality',red?'首次紅燈距低點 '+redDays+' 個交易日｜'+(classify==='early'?'提前警報':classify==='mid'?'回撤 5～10% 後警報':'回撤 10% 後警報'):'區間內未亮紅燈；需檢查原因');body.append(quality);
      if(event.ongoing&&!closedAt)body.append(h('p','mm-history-pending','進行中：每日更新至最新有效交易日 '+funds.at(-1).date+'；新低會更新低點，反彈不會抹除既有低點。滿足連續 10 日回撤小於 5% 才標示事件結束。'));
      else if(event.ongoing&&closedAt)body.append(h('p','mm-history-pending','已依連續 10 日修復條件在 '+closedAt+' 結束本事件。'));
      else if(event.end>endDate)body.append(h('p','mm-history-pending','此區間尚未走到觀察截止日；目前顯示截至資料最新日的暫定低點。'));
      card.append(body);historyHost.append(card);
    }
    historyCount.textContent='顯示 '+count+' 段跌勢';
    if(!count)historyHost.textContent='沒有符合目前篩選條件的重大跌勢；或歷史原始資料尚未載入。';
  }
  historyFilter.addEventListener('change',renderHistory);
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
