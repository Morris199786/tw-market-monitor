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
    const r = {...original, twseMargin: original.margin, twseMarginPrevious: original.margin_previous, tpexMargin: current, tpexMarginPrevious: prior,
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

// Auxiliary breadth-and-relative-margin improvement monitor; NOT confirmation of price rebound. V12 never reads this map.
// Every offset refers to an existing trading-day row, never to a future trough.
const TW_RECOVERY_RULE = Object.freeze({redLookback:15,breadthRise5:15,marginLookback:10,
  marginRelative5:-3,observeDays:10,
  dailyDeleverage:-2});
let twRecoveryByDate=new Map();
let twRecoveryEvents=[];
const isStrongDailyDeleverage=f=>Number.isFinite(f?.relative)&&f.relative<=TW_RECOVERY_RULE.dailyDeleverage
  && Number.isFinite(f.margin)&&Number.isFinite(f.margin_previous)&&f.margin<f.margin_previous;
function buildTwRecovery(funds,breadth,risks){
  const rows=[...funds].sort((a,b)=>a.date.localeCompare(b.date));
  const bmap=new Map(breadth.map(x=>[x.date,x]));
  const states=new Map(),events=[];
  let active=null,lastEventIndex=-Infinity;
  for(let i=0;i<rows.length;i++){
    const f=rows[i],b=bmap.get(f.date),r=risks.get(f.date);
    const prev5=i>=5?bmap.get(rows[i-5].date):null;
    const completeBreadth=!!b?.complete&&!!prev5?.complete&&Number.isFinite(b?.pct20)&&Number.isFinite(prev5?.pct20)
      && rows.slice(Math.max(0,i-5),i+1).every(x=>bmap.get(x.date)?.complete);
    const breadth5=completeBreadth?b.pct20-prev5.pct20:null;
    const redHistory=rows.slice(Math.max(0,i-TW_RECOVERY_RULE.redLookback),i)
      .some(x=>risks.get(x.date)?.level===3);
    const recentMargins=rows.slice(Math.max(0,i-TW_RECOVERY_RULE.marginLookback+1),i+1);
    const marginEvidence=[...recentMargins].reverse().find(x=>Number.isFinite(x.relative5)&&x.relative5<=TW_RECOVERY_RULE.marginRelative5);
    const marginHistory=!!marginEvidence;
    const qualified=!!r&&redHistory&&Number.isFinite(breadth5)
      &&breadth5>=TW_RECOVERY_RULE.breadthRise5&&marginHistory;
    if(active&&i-active.index>TW_RECOVERY_RULE.observeDays){
      active.event.endDate=rows[i-1].date;
      active=null;
    }
    // Do not stack confirmations while the first 10-day observation remains in progress.
    if(!active&&qualified&&i-lastEventIndex>TW_RECOVERY_RULE.observeDays){
      const event={date:f.date,endDate:null,score:r.score,breadth5,marginRelative5:marginEvidence?.relative5??null,marginDate:marginEvidence?.date??null};
      events.push(event);active={index:i,event};lastEventIndex=i;
      states.set(f.date,{status:'confirmed',eventDate:event.date,breadth5,redHistory,marginHistory,
        trigger:true,confirmScore:event.score,signalBreadth5:event.breadth5,signalMarginRelative5:event.marginRelative5,signalMarginDate:event.marginDate});
      continue;
    }
    if(active){
      const event=active.event;
      states.set(f.date,{status:'confirmed',eventDate:event.date,
        breadth5,redHistory,marginHistory,trigger:false,
        confirmScore:event.score,signalBreadth5:event.breadth5,signalMarginRelative5:event.marginRelative5,signalMarginDate:event.marginDate});
    }else{
      states.set(f.date,{status:'none',breadth5,redHistory,marginHistory,trigger:false});
    }
  }
  // Expiry has no special warning; the first day after the 10-session window is neutral.
  return {states,events};
}

// UI-only daily signals. The recovery event model and V12 scores are unchanged.
// The ten-session event window suppresses duplicate trial entries, NOT display on later dates.
function twDailySignal(date){
  const state=twRecoveryByDate.get(date);
  const fund=twCompositeFunds.find(row=>row.date===date);
  const breadth5=Number.isFinite(state?.breadth5)?state.breadth5:null;
  const margin5=Number.isFinite(fund?.relative5)?fund.relative5:null;
  const marginComplete=Number.isSafeInteger(fund?.twseMargin)&&fund.twseMargin>0
    &&Number.isSafeInteger(fund?.tpexMargin)&&fund.tpexMargin>0
    &&Number.isSafeInteger(fund?.twseMarginPrevious)&&fund.twseMarginPrevious>0
    &&Number.isSafeInteger(fund?.tpexMarginPrevious)&&fund.tpexMarginPrevious>0
    &&fund.margin===fund.twseMargin+fund.tpexMargin
    &&fund.margin_previous===fund.twseMarginPrevious+fund.tpexMarginPrevious;
  const marginChange=marginComplete?(fund.margin-fund.margin_previous)/1e8:null;
  const marginChangePct=marginComplete?100*(fund.margin/fund.margin_previous-1):null;
  const deleverage=margin5!==null&&margin5<=-3&&marginChange!==null&&marginChange<0;
  const trial=state?.trigger===true;
  const tags=[];
  if(trial){
    tags.push({name:'試單機會',kind:'trial'});
  }else{
    if(breadth5!==null&&breadth5>=15)tags.push({name:'廣度改善',kind:'positive'});
    else if(breadth5!==null&&breadth5<=-15)tags.push({name:'廣度惡化',kind:'negative'});
    if(deleverage)tags.push({name:'去槓桿加速',kind:'positive'});
    else if(margin5!==null&&margin5>=3)tags.push({name:'槓桿加速',kind:'negative'});
  }
  return {state,trial,breadth5,margin5,marginChange,marginChangePct,deleverage,tags};
}
function twAppendDailyTags(container,date){
  for(const tag of twDailySignal(date).tags){
    const button=document.createElement('button');
    button.type='button';
    button.className='mm-rebound-trigger mm-daily-signal mm-daily-'+tag.kind;
    button.textContent=tag.name;
    button.setAttribute('aria-haspopup','dialog');
    button.setAttribute('aria-label',date+' '+tag.name+'，查看廣度和融資數據');
    button.addEventListener('click',()=>document.dispatchEvent(new CustomEvent('tw-rebound-detail-request',{detail:{date}})));
    container.append(button);
  }
}
// Keep the new visual treatment isolated from existing market-monitor elements.
if(typeof document!=='undefined'&&!document.getElementById('mm-daily-signal-style')){
  const style=document.createElement('style');
  style.id='mm-daily-signal-style';
  style.textContent=`
    #marketMonitor .mm-daily-signal{display:inline-flex;align-items:center;justify-content:center;min-height:27px!important;padding:4px 10px!important;border-radius:999px!important;border:1px solid transparent!important;font-size:11px!important;font-weight:750!important;line-height:1.35!important;white-space:normal;cursor:pointer;margin:2px 3px 0 0;max-width:100%;box-shadow:none!important}
    #marketMonitor .mm-daily-positive,#marketMonitor .mm-daily-trial{background:rgba(26,150,108,.12)!important;color:#14845e!important;border-color:rgba(26,150,108,.26)!important}
    #marketMonitor .mm-daily-negative{background:rgba(202,58,73,.12)!important;color:#c13c4e!important;border-color:rgba(202,58,73,.25)!important}
    #marketMonitor .mm-daily-trial{font-weight:850!important;border-width:1.5px!important}
    #marketMonitor .mm-composite-date .mm-daily-signal{display:flex!important;margin:4px auto 0!important;width:max-content;max-width:94px;padding:3px 6px!important;font-size:10px!important}
    #marketMonitor .mm-risk-trend .mm-daily-signal{margin-top:3px}
    html[data-theme="dark"] #marketMonitor .mm-daily-positive,html[data-theme="dark"] #marketMonitor .mm-daily-trial{color:#7fe0b8!important;background:rgba(29,150,107,.2)!important}
    html[data-theme="dark"] #marketMonitor .mm-daily-negative{color:#ff9ba4!important;background:rgba(202,58,73,.2)!important}
  `;
  document.head.append(style);
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
     // Daily-only labels: never carry an old trial event through its 10-session window.
     twAppendDailyTags(trend,date);

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
      const status = root.querySelector('[data-mm-status]');
      const selectedYear = year.value;
      const selectedMonth = month.value;
      try {
        if(status) status.textContent = '正在讀取台股市場與歷史資料…';
        const response = await fetch('./data/market_monitor.json?v=' + Date.now(), {cache:'no-store'});
        if (!response.ok) throw new Error('market_monitor.json HTTP ' + response.status);
        const next = await response.json();
        if (!Array.isArray(next.rows) || !next.rows.length) throw new Error('market_monitor.json 未提供有效交易日');
        // Publish verified recent rows right away; large history requests must not blank the dashboard.
        dataset={...next,rows:next.rows};
        twCompositeFunds=next.rows;
        twCompositeBreadth=[];
        twRiskByDate=new Map();
        twRecoveryByDate=new Map();twRecoveryEvents=[];
        document.dispatchEvent(new Event('tw-composite-data-updated'));
        const otcPromise = fetch('./data/market_margin_tpex.json?v=' + Date.now(), {cache:'no-store'})
          .then(async r => {
            if(!r.ok) throw Error('上櫃融資 HTTP ' + r.status);
            const json=await r.json();
            if(json.unit!=='TWD' || !json.rows || Array.isArray(json.rows)) throw Error('上櫃融資格式不符');
            return json.rows;
          });
        const bounded = (promise,label) => Promise.race([
          promise,
          new Promise((_,reject)=>setTimeout(()=>reject(new Error(label+'讀取逾時')),20000))
        ]);
        const historicalFundsPromise = bounded(loadTaiwanMonitorArchive('funds'),'歷史資金資料');
        const breadthPromise = bounded(getTwBreadth(),'市場廣度資料');
        // A failed optional historical source must not wipe the latest official records.
        const [otcRes, fundRes, breadthRes] = await Promise.allSettled([otcPromise,historicalFundsPromise,breadthPromise]);
        const warnings = [];
        const otc = otcRes.status==='fulfilled' ? otcRes.value : {};
        if(otcRes.status!=='fulfilled')warnings.push('上櫃融資讀取失敗');
        const archive = fundRes.status==='fulfilled' ? fundRes.value : null;
        if(fundRes.status!=='fulfilled')warnings.push('歷史資金資料讀取失敗');
        const oldRows = Array.isArray(archive) ? archive : Array.isArray(archive?.rows) ? archive.rows : [];
        const allRows = [...new Map([...oldRows,...next.rows].filter(r=>r&&/^20\d{2}-\d{2}-\d{2}$/.test(r.date)).map(r=>[r.date,r])).values()]
          .sort((a,b)=>a.date.localeCompare(b.date));
        dataset = {...next,rows:applyCombinedMargin(allRows,otc)};
        const latest = dataset.as_of_date || dataset.rows.at(-1)?.date || '';
        twCompositeFunds = dataset.rows;
        const breadth = breadthRes.status==='fulfilled' ? breadthRes.value : null;
        if(!breadth)warnings.push('市場廣度讀取失敗');
        twCompositeBreadth = breadth?.series?.all || [];
        try {
          twRiskByDate = breadth ? buildTwRisk(dataset.rows,twCompositeBreadth) : new Map();
          const recovered = breadth ? buildTwRecovery(dataset.rows,twCompositeBreadth,twRiskByDate) : null;
          twRecoveryByDate = recovered?.states || new Map();
          twRecoveryEvents = recovered?.events || [];
        } catch (error) {
          console.error('V12 signal calculation failed',error);
          warnings.push('綜合燈號計算失敗：'+error.message);
          twRiskByDate = new Map();twRecoveryByDate=new Map();twRecoveryEvents=[];
        }
        dataset.archiveWarning = warnings.length ? '｜'+warnings.join('｜') : '';
        const years=[...new Set(dataset.rows.map(r=>r.date.slice(0,4)))].sort();
        year.replaceChildren(...years.map(y=>new Option(y+'年',y)));
        year.value=years.includes(selectedYear)?selectedYear:latest.slice(0,4);
        month.value=selectedMonth || latest.slice(5,7);
        // The signal card must update independently of the hidden legacy finance table.
        // A failure in that table must never strand the top summary at "載入中".
        paintTwRisk(latest);
        try { render(); }
        catch (viewError) {
          console.warn('Legacy finance table render failed; composite V12 remains available:', viewError);
          warnings.push('舊版資金表格顯示異常');
        }
        document.dispatchEvent(new Event('tw-composite-data-updated'));
        if(status && warnings.length)status.textContent += '｜'+warnings.join('｜');
      } catch (error) {
        console.error('TW market dashboard source load failed',error);
        // Retain last successfully loaded data instead of erasing the composite table.
        if(!twCompositeFunds.length){
          twRiskByDate=new Map();
          paintTwRisk(null);
          document.dispatchEvent(new Event('tw-composite-data-updated'));
        }
        if(status)status.textContent='市場資料讀取失敗：'+error.message+'。請檢查網站 JSON 路徑／GitHub Actions。';
      } finally {pending=null;}
    })();
    return pending;
  }
  window.loadTwMonitorData = load;

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

// US dashboard v2: table-first layout with linked price / indicator charts.
(() => {
  'use strict';
  const root = document.getElementById('marketMonitor');
  if (!root) return;
  const taiwan = document.createElement('div');
  taiwan.id = 'mm-taiwan';
  while (root.firstChild) taiwan.append(root.firstChild);
  const tabs = document.createElement('div');
  tabs.className = 'mm-market-tabs';
  tabs.setAttribute('role','group');
  tabs.setAttribute('aria-label','選擇市場');
  tabs.innerHTML = '<button type="button" aria-pressed="true" aria-controls="mm-taiwan">台股</button><button type="button" aria-pressed="false" aria-controls="mm-us">美股</button>';
  const us = document.createElement('section');
  us.id = 'mm-us';
  us.hidden = true;
  us.innerHTML = `
    <div class="us-head">
      <div><span class="us-eyebrow">US MARKET · RISK MONITOR</span><h2>美股市場監測</h2><p>以表格總覽最新指標，並用共用時間軸觀察各指標與股價的連動關係。</p></div>
      <button type="button" class="us-refresh" data-us-refresh aria-label="重新讀取美股資料">↻ 更新資料</button>
    </div>
    <p class="us-status" data-us-status role="status">首次開啟美股分頁後讀取最新資料</p>

    <section class="us-overview-card">
      <div class="us-section-title us-section-title--tight">
        <div><h3>市場指標總覽</h3><p>單一大表格集中比較五項核心指標；不同來源以各自的實際資料日期為準。</p></div>
      </div>
      <div class="us-table-wrap">
        <table class="us-overview-table">
          <thead><tr><th>指標</th><th>最新數值</th><th>變化</th><th>資料日期</th></tr></thead>
          <tbody data-us-overview-rows></tbody>
        </table>
      </div>
      <p class="us-table-note">Fear &amp; Greed / VIX / HY OAS / IG OAS 為每日資料；FINRA 融資為月資料，因此不強制對齊到同一天。</p>
    </section>

    <div class="us-section-title">
      <div><h3>股價 × 指標疊合</h3><p>一張大圖比較股價與所選市場指標，雙 Y 軸、同日期查價線。</p></div>
      <div class="us-periods" role="group" aria-label="圖表觀察區間">
        <button type="button" data-us-range="3m">3M</button><button type="button" data-us-range="6m">6M</button><button type="button" data-us-range="1y" aria-pressed="true">1Y</button><button type="button" data-us-range="3y">3Y</button><button type="button" data-us-range="all">全部</button>
      </div>
    </div>
    <section class="us-main-chart" data-us-chart-container>
      <div class="us-compare-controls">
        <label>比較指標<select data-us-compare-metric aria-label="選擇要與股價比較的市場指標"><option value="cnn_fear_greed">CNN Fear &amp; Greed</option><option value="vix">VIX 恐慌指數</option><option value="hy_oas_pct">HY OAS 高收益債利差</option><option value="ig_oas_pct">IG OAS 投資級債利差</option><option value="cftc_net_pct">CFTC 槓桿基金淨部位占比</option><option value="cftc_net">CFTC 槓桿基金淨部位</option><option value="cftc_long">CFTC 槓桿基金多單</option><option value="cftc_short">CFTC 槓桿基金空單</option></select></label>
        <label>股價指數<select data-us-compare-price aria-label="選擇股價指數"><option value="nasdaq_composite">Nasdaq 綜合指數</option><option value="sp500">S&amp;P 500</option></select></label>
      </div>
      <div data-us-groups></div>
      <p class="us-chart-hint">左軸：股價指數點位｜右軸：所選指標原始數值。雙軸僅供比較時間關係，不代表兩者數值可直接比較；空缺日期不補零。</p>
    </section>

    <section class="us-margin-section"><div class="us-section-title"><div><h3>CFTC｜Nasdaq 100 期貨籌碼</h3><p data-us-cftc-date>持倉統計日（非公布日）</p></div></div><div class="us-table-wrap"><table class="us-overview-table"><thead><tr><th>交易人</th><th>多單</th><th>空單</th><th>淨部位</th><th>較前次</th></tr></thead><tbody data-us-cftc-rows></tbody></table></div><p class="us-table-note" data-us-cftc-note></p><details class="us-month-chart-details"><summary>展開槓桿基金多空歷史圖</summary><div data-us-cftc-chart></div></details></section>
    <section class="us-margin-section">
      <div class="us-section-title"><div><h3>FINRA 融資監控</h3><p>月資料獨立檢視，不與每日情緒或信用利差混合。重點放在與 S&amp;P 500 的月度連動。</p></div></div>
      <div class="us-table-wrap us-table-wrap--margin">
        <table class="us-overview-table us-margin-table">
          <thead><tr><th>欄位</th><th>最新數值</th><th>補充</th></tr></thead>
          <tbody data-us-margin-summary></tbody>
        </table>
      </div>
      <details class="us-month-chart-details"><summary>展開 FINRA 融資與股價月度比較圖</summary><div data-us-month-chart-group></div></details>
      <details class="us-month-details"><summary>查看近 12 個月融資數據</summary>
        <div class="us-month-scroll"><table><thead><tr><th>月份</th><th>餘額（億美元）</th><th>月增率</th><th>年增率</th><th>S&amp;P 500 月報酬</th><th>相對大盤</th></tr></thead><tbody data-us-month-rows></tbody></table></div>
      </details>
    </section>

    <dialog class="us-info-dialog" data-us-info-dialog aria-label="指標說明">
      <div class="us-info-top"><strong data-us-info-title>指標說明</strong><button type="button" data-us-info-close aria-label="關閉說明">×</button></div>
      <div data-us-info-content class="us-info-content"></div>
    </dialog>
    <details class="us-method"><summary>資料來源、更新頻率與計算說明</summary>
      <p><b>Fear &amp; Greed</b>：0～100，數字越低代表市場越恐懼；0–24 為極度恐懼，25–44 為恐懼，45–55 為中性，56–75 為貪婪，76 以上為極度貪婪。</p>
      <p><b>VIX</b>：S&amp;P 500 選擇權隱含的未來 30 天預期波動率；越高通常表示市場不確定性越高。<b>HY / IG OAS</b>：高收益 / 投資級公司債信用利差，單位為百分點；擴大通常表示信用風險溢酬上升。</p>
      <p><b>股價圖</b>：上方價格面板以區間起點 = 100 的相對表現呈現，方便直接對照 Nasdaq 與 S&amp;P 500；不是原始指數點位。情緒與信用圖使用原始數值。所有每日圖表以 2011 年後實際可得資料為準。</p>
      <p><b>FINRA 融資</b>：月資料；相對大盤＝融資月增率 − S&amp;P 500 同月報酬率（百分點）。不把月度槓桿變化視為日內交易訊號。</p>
      <p>來源：<a href="https://www.cnn.com/markets/fear-and-greed" target="_blank" rel="noopener">CNN Fear &amp; Greed</a>、<a href="https://fred.stlouisfed.org/" target="_blank" rel="noopener">FRED</a>、<a href="https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics" target="_blank" rel="noopener">FINRA</a>、Yahoo Finance（市場指數）；歷史快照請以資料檔的來源記錄為準。</p>
    </details>`;
  root.append(tabs, taiwan, us);

  const status = us.querySelector('[data-us-status]');
  const overviewRows = us.querySelector('[data-us-overview-rows]');
  const groups = us.querySelector('[data-us-groups]');
  const marginSummaryBody = us.querySelector('[data-us-margin-summary]');
  const monthChartGroup = us.querySelector('[data-us-month-chart-group]');
  let sentiment = null, margin = null, loading = null, range = '1y';

  const formats = {
    cnn_fear_greed: { label: 'Fear & Greed', digits: 1, unit: '' },
    vix: { label: 'VIX', digits: 2, unit: '' },
    hy_oas_pct: { label: 'HY OAS', digits: 2, unit: '%' },
    ig_oas_pct: { label: 'IG OAS', digits: 2, unit: '%' }
  };
  const chartColors = {
    sp500: '#3279cf', nasdaq_composite: '#15a19b', cnn_fear_greed: '#bc7a22', vix: '#8a70bf',
    hy_oas_pct: '#dc8150', ig_oas_pct: '#397fb8', margin: '#378da6'
  };
  const num = (n,d=2)=>Number.isFinite(n)?n.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
  const signed = (n,d=2,u='')=>Number.isFinite(n)?(n>0?'+':'')+num(n,d)+u:'—';
  const el = (tag,cls,txt)=>{ const x=document.createElement(tag); if(cls) x.className=cls; if(txt!==undefined) x.textContent=txt; return x; };
  const svgEl = (tag,attrs)=>{ const e=document.createElementNS('http://www.w3.org/2000/svg',tag); for(const [k,v] of Object.entries(attrs||{})) e.setAttribute(k,String(v)); return e; };
  const sortedEntries = values => Object.entries(values||{}).filter(([,v])=>Number.isFinite(v)).sort((a,b)=>a[0].localeCompare(b[0]));
  const lastValue = values => { const entries=sortedEntries(values); return entries.length ? { date: entries.at(-1)[0], value: entries.at(-1)[1] } : null; };
  const seriesChange = (values, steps=5) => { const entries=sortedEntries(values); if(entries.length<2) return null; const last=entries.length-1; const prior=Math.max(0,last-steps); return entries[last][1]-entries[prior][1]; };
  const fearLabel = n => n<=24?'極度恐懼':n<=44?'恐懼':n<=55?'中性':n<=75?'貪婪':'極度貪婪';
  const rangeStart = max => {
    if (range === 'all') return '0000-01-01';
    const d = new Date(max + 'T12:00:00Z');
    if (range === '3m') d.setUTCMonth(d.getUTCMonth()-3);
    else if (range === '6m') d.setUTCMonth(d.getUTCMonth()-6);
    else if (range === '1y') d.setUTCFullYear(d.getUTCFullYear()-1);
    else d.setUTCFullYear(d.getUTCFullYear()-3);
    return d.toISOString().slice(0,10);
  };
  const rangeStartMonth = max => rangeStart(max+'-01').slice(0,7);
  const bp = n => Number.isFinite(n) ? signed(n*100,0,'bp') : '—';
  function firstCrossBelow(values, threshold){
    const entries=sortedEntries(values), out=[];
    let prev=null;
    for(const [date,value] of entries){
      if(value<=threshold && !(prev!==null && prev<=threshold)) out.push(date);
      prev=value;
    }
    return out;
  }
  function nearestIndex(dates,target){
    if(!dates.length) return -1;
    let idx=dates.findIndex(d=>d>=target);
    if(idx===-1) return dates.length-1;
    if(dates[idx]===target) return idx;
    return idx>0 ? idx-1 : 0;
  }
  function createSyncGroup(){
    return {
      members: [],
      broadcast(date, source){ this.members.forEach(m=>{ if(m!==source) m.setByDate(date, false); }); },
      register(member){ this.members.push(member); }
    };
  }

  const indicatorInfo={
    'Fear & Greed':{
      title:'CNN Fear & Greed｜恐懼貪婪指數',
      paragraphs:[
        '這是 CNN 用來衡量美股市場整體情緒的 0～100 綜合指標，包含市場動能、股價強弱、股價廣度、選擇權 Put/Call、波動率、避險債券需求與垃圾債需求等面向。',
        '指數越低代表市場越恐懼；越高代表越貪婪。0～24 通常視為極度恐懼，但極度恐懼不一定等於股價已經見底。',
        '研究方式：將情緒指數跌破 10 的日期與 Nasdaq／S&P 500 對照，觀察股價在前後交易日的實際變化。'
      ]
    },
    'VIX':{
      title:'VIX｜恐慌指數',
      paragraphs:[
        'VIX 反映 S&P 500 選擇權價格推估的未來約 30 天年化預期波動率；不是當天實際跌幅，也不直接代表漲跌方向。',
        'VIX 快速上升通常代表避險需求或不確定性升高，常與股價快速下跌同時出現；但也可能在劇烈反彈時保持高檔。',
        '觀察重點：VIX 是否先於股價擴大、股價再創低時 VIX 是否創新高，以及波動率回落時股價的反應。'
      ]
    },
    'HY OAS':{
      title:'HY OAS｜高收益債信用利差',
      paragraphs:[
        'HY = High Yield（高收益債），主要由非投資等級企業發行，常見信評為 BB+／Ba1 以下。這類企業財務體質較脆弱，市場擔心違約或景氣衰退時，投資人往往要求更高的額外收益率。',
        'OAS = Option-Adjusted Spread（選擇權調整後利差），在調整債券內嵌選擇權影響後，估計其相對基準利率的信用風險溢酬。資料以百分點表示：3.52% = 352bp（基點），1bp = 0.01 個百分點。',
        '利差「擴大」往往意味信用環境變緊、風險偏好下降；利差「收斂」代表要求的信用風險溢酬下降。HY 對景氣衰退與融資壓力通常比較敏感，但不能僅憑單日或固定門檻當作買賣訊號。',
        '與股價對照時，關注 HY OAS 是否在股價回落前開始擴大，以及股價反彈時信用利差是否同步收斂；若兩者背離，值得進一步觀察。'
      ]
    },
    'IG OAS':{
      title:'IG OAS｜投資級債信用利差',
      paragraphs:[
        'IG = Investment Grade（投資等級債），一般涵蓋 BBB−／Baa3 以上的企業債，發行人整體信用品質通常比高收益債高。',
        'OAS 同樣是經選擇權因素調整後的信用利差，用來衡量企業債相對基準利率所需的額外信用風險溢酬。0.94% = 94bp，並非企業實際借款利率只有 0.94%。',
        'IG 利差擴大可能反映系統性信用壓力、流動性惡化或市場風險溢酬上升。通常波動幅度小於 HY，因此分析時宜關注 bp 變化與歷史相對位置，不應直接比較 HY 與 IG 的百分比高低。',
        '若 HY 與 IG 同時快速擴大，代表風險可能從弱信評企業擴散到更廣泛信用市場；若僅 HY 擴大，壓力可能較集中於較高風險的借款人。仍需搭配股價與 VIX 判讀。'
      ]
    },
    'FINRA 融資':{
      title:'FINRA 融資餘額｜美股槓桿資金',
      paragraphs:[
        'FINRA 公布的是券商客戶保證金帳戶中的借款餘額，屬於月度資料。餘額上升不一定代表風險立即升高，也可能反映市場總市值與交易規模擴大。',
        '月增率＝本月融資餘額相對前月變化；年增率＝相對去年同月變化；相對大盤（pp）＝融資月增率減去同期 S&P 500 月報酬率。',
        '例如月增 −2.14%、S&P 500 月報酬 −0.93%，相對大盤為 −1.21pp，表示該月融資下降幅度比大盤跌幅多約 1.21 個百分點。這不等同保證後續股價反彈。'
      ]
    }
  };
  const infoDialog=us.querySelector('[data-us-info-dialog]');
  us.querySelector('[data-us-info-close]').addEventListener('click',()=>infoDialog.close());
  infoDialog.addEventListener('click',e=>{if(e.target===infoDialog)infoDialog.close();});
  function showIndicatorInfo(key){
    const detail=indicatorInfo[key];if(!detail)return;
    us.querySelector('[data-us-info-title]').textContent=detail.title;
    us.querySelector('[data-us-info-content]').replaceChildren(...detail.paragraphs.map(t=>el('p','',t)));
    if(infoDialog.open)infoDialog.close();
    if(typeof infoDialog.showModal==='function')infoDialog.showModal();else infoDialog.setAttribute('open','');
  }
  function renderOverviewTable(){
    overviewRows.replaceChildren();
    const entries=[];
    if(sentiment){
      const s=sentiment.series||{};
      const fear=lastValue(s.cnn_fear_greed),vix=lastValue(s.vix),hy=lastValue(s.hy_oas_pct),ig=lastValue(s.ig_oas_pct);
      entries.push(
        {name:'Fear & Greed',value:fear?num(fear.value,1):'—',change:fear?('5日 '+signed(seriesChange(s.cnn_fear_greed,5),1)):'—',date:fear?.date||'—'},
        {name:'VIX',value:vix?num(vix.value,2):'—',change:vix?('5日 '+signed(seriesChange(s.vix,5),2)):'—',date:vix?.date||'—'},
        {name:'HY OAS',value:hy?num(hy.value,2)+'%':'—',change:hy?('5日 '+bp(seriesChange(s.hy_oas_pct,5))):'—',date:hy?.date||'—'},
        {name:'IG OAS',value:ig?num(ig.value,2)+'%':'—',change:ig?('5日 '+bp(seriesChange(s.ig_oas_pct,5))):'—',date:ig?.date||'—'}
      );
    }
    const latest=margin?.rows?.at(-1);
    if(latest){entries.push({name:'FINRA 融資',value:num(latest.margin_million/100,0)+' 億美元',changeLines:[
      ['月增',signed(latest.mom_pct,2,'%')],['年增',signed(latest.yoy_pct,2,'%')],['相對大盤',signed(latest.relative_pp,2,'pp')]
    ],date:latest.month});}
    if(!entries.length){const tr=el('tr'),td=el('td','us-empty','尚未取得美股資料');td.colSpan=4;tr.append(td);overviewRows.append(tr);return;}
    for(const row of entries){
      const tr=el('tr');
      const th=el('th');th.scope='row';
      const button=el('button','us-info-button',row.name);
      button.type='button';button.setAttribute('aria-label','查看 '+row.name+' 指標解釋');
      button.append(el('span','us-info-icon','ⓘ'));
      button.addEventListener('click',()=>showIndicatorInfo(row.name));
      th.append(button,el('small','us-row-date',row.date));tr.append(th);
      tr.append(el('td','us-table-value',row.value));
      const ch=el('td','us-table-change');
      if(row.changeLines){
        for(const [label,value] of row.changeLines){const line=el('div','us-change-line');line.append(el('span','',label),el('b','',value));ch.append(line);}
      }else ch.textContent=row.change;
      tr.append(ch,el('td','us-table-date',row.date));
      overviewRows.append(tr);
    }
  }

  function chartPanel(title, description, series, opts={}){
    const panel=el('article','us-chart-card us-chart-card--compact');
    const head=el('div','us-chart-head');
    const heading=el('div'); heading.append(el('h4','',title), el('small','',description));
    const readout=el('div','us-chart-readout','查價線');
    head.append(heading, readout); panel.append(head);
    const legend=el('div','us-chart-legend');
    for(const it of series){ const item=el('span'); const swatch=el('i'); swatch.style.background=it.color; item.append(swatch, document.createTextNode(it.name)); legend.append(item); }
    panel.append(legend);
    const viewport=el('div','us-chart-viewport');
    const H=opts.compact?190:245;
    const svg=svgEl('svg',{viewBox:`0 0 800 ${H}`,role:'img','aria-label':title+'，可滑動查價線',preserveAspectRatio:'none'});
    viewport.append(svg); panel.append(viewport);
    const cursorLegend=el('div','us-chart-values'); panel.append(cursorLegend);

    const allDates=[...new Set(series.flatMap(it=>Object.keys(it.values||{})))].sort();
    if(!allDates.length){ viewport.append(el('p','us-empty','目前沒有可用歷史資料')); return panel; }
    const lastDate=allDates.at(-1), from=opts.monthly?(range==='all'?'0000-01':rangeStartMonth(lastDate)):rangeStart(lastDate);
    const dates=allDates.filter(d=>d>=from);
    if(dates.length<2){ viewport.append(el('p','us-empty','區間內資料不足')); return panel; }

    const firstBySeries=new Map(series.map(it=>[it.key, dates.map(d=>it.values[d]).find(v=>Number.isFinite(v)&&v!==0)]));
    const mapped=series.map(it=>({ ...it, points: dates.map(d=>{ const v=it.values[d]; if(!Number.isFinite(v)) return null; const base=firstBySeries.get(it.key); return opts.normalize?(Number.isFinite(base)&&base!==0?v/base*100:null):v; }) }));
    const vals=mapped.flatMap(s=>s.points.filter(Number.isFinite));
    if(vals.length<2){ viewport.append(el('p','us-empty','區間內資料不足')); return panel; }
    let min=opts.minY ?? Math.min(...vals), max=opts.maxY ?? Math.max(...vals);
    if(!Number.isFinite(min)||!Number.isFinite(max)) return panel;
    if(max-min<1e-6){ min-=1; max+=1; } else if(opts.minY==null&&opts.maxY==null){ const pad=(max-min)*.12; min-=pad; max+=pad; }

    const W=800, L=54, R=14, T=18, B=32, chartW=W-L-R, chartH=H-T-B;
    const xp=i=>L+chartW*(i/(dates.length-1));
    const yp=v=>T+chartH*(max-v)/(max-min);
    for(let i=0;i<=4;i++){
      const y=T+i*chartH/4; svg.append(svgEl('line',{x1:L,x2:W-R,y1:y,y2:y,class:'us-chart-gridline'}));
      const tick=svgEl('text',{x:L-8,y:y+4,'text-anchor':'end',class:'us-chart-axis'});
      tick.textContent=opts.axisFmt ? opts.axisFmt(max-i*(max-min)/4) : num(max-i*(max-min)/4, opts.normalize?0:1); svg.append(tick);
    }
    for(const ix of [0, Math.floor((dates.length-1)/2), dates.length-1]){
      const tick=svgEl('text',{x:xp(ix), y:H-8, 'text-anchor':ix===0?'start':ix===dates.length-1?'end':'middle', class:'us-chart-axis'});
      tick.textContent=dates[ix].slice(0,7); svg.append(tick);
    }
    if(Array.isArray(opts.eventDates)){
      for(const dt of opts.eventDates){
        const at=nearestIndex(dates, dt); if(at<0) continue;
        const x=xp(at);
        svg.append(svgEl('line',{x1:x,x2:x,y1:T,y2:H-B,class:'us-chart-event'}));
      }
    }
    const pointDots=[];
    for(const s of mapped){
      let p='', drawn=false;
      for(let i=0;i<s.points.length;i++){
        const v=s.points[i]; if(!Number.isFinite(v)){ drawn=false; continue; }
        const x=xp(i).toFixed(2), y=yp(v).toFixed(2); p += (drawn?'L':'M')+x+' '+y+' '; drawn=true;
      }
      svg.append(svgEl('path',{d:p,fill:'none',stroke:s.color,'stroke-width':2.3,'stroke-linecap':'round','stroke-linejoin':'round','vector-effect':'non-scaling-stroke'}));
      const dot=svgEl('circle',{r:4.3,fill:s.color,stroke:'var(--card,white)','stroke-width':2,'vector-effect':'non-scaling-stroke'}); svg.append(dot); pointDots.push(dot);
    }
    const line=svgEl('line',{y1:T,y2:H-B,stroke:'#8092a9','stroke-dasharray':'4 4','stroke-width':1.25,'vector-effect':'non-scaling-stroke'}); svg.append(line);
    const target=svgEl('rect',{x:L,y:T,width:chartW,height:chartH,fill:'transparent',class:'us-chart-hit'}); svg.append(target);

    let selected=-1;
    const api = {
      setByDate(date, emit=true){ const at=nearestIndex(dates, date); if(at>=0) setIndex(at, emit); },
      setLatest(){ setIndex(dates.length-1, false); }
    };
    const setIndex = (i, emit=true) => {
      const at=Math.max(0,Math.min(dates.length-1,i)); if(at===selected) return; selected=at;
      line.setAttribute('x1',xp(at)); line.setAttribute('x2',xp(at));
      readout.textContent=dates[at]; cursorLegend.replaceChildren();
      mapped.forEach((s,k)=>{
        const v=s.points[at], dot=pointDots[k];
        dot.style.display=Number.isFinite(v)?'':'none';
        if(Number.isFinite(v)){ dot.setAttribute('cx',xp(at)); dot.setAttribute('cy',yp(v)); }
        const item=el('span'); const swatch=el('i'); swatch.style.background=s.color;
        item.append(swatch, document.createTextNode(s.name+' '+(Number.isFinite(v)?num(v,opts.normalize?1:s.digits??2)+(opts.unit||''):'—')));
        cursorLegend.append(item);
      });
      if(emit && opts.syncGroup) opts.syncGroup.broadcast(dates[at], api);
    };
    const seek = e => {
      const b=svg.getBoundingClientRect(); if(!b.width) return;
      const nx=(e.clientX-b.left)/b.width*W;
      setIndex(Math.round((nx-L)/chartW*(dates.length-1)), true);
    };
    target.addEventListener('pointerdown', seek); target.addEventListener('pointermove', seek);
    target.addEventListener('keydown', e=>{ if(e.key==='ArrowLeft'||e.key==='ArrowRight'){ e.preventDefault(); setIndex(selected+(e.key==='ArrowLeft'?-1:1), true); } });
    target.setAttribute('tabindex','0'); target.setAttribute('role','slider'); target.setAttribute('aria-label',title+' 日期查價線，左右方向鍵移動');
    if(opts.syncGroup) opts.syncGroup.register(api);
    api.setLatest();
    return panel;
  }

  function linkedCard(title, desc, panels){
    const card=el('section','us-linked-card');
    const head=el('div','us-linked-head');
    const block=el('div'); block.append(el('h3','',title), el('p','',desc));
    head.append(block); card.append(head);
    const stack=el('div','us-linked-stack'); stack.append(...panels); card.append(stack);
    return card;
  }

  function renderGroups(){
    groups.replaceChildren();
    if(!sentiment){groups.append(el('p','us-empty','每日歷史資料尚未載入'));return;}
    const s=sentiment.series||{};
    const priceKey=us.querySelector('[data-us-compare-price]').value;
    const metricKey=us.querySelector('[data-us-compare-metric]').value;
    const cftcField={cftc_net_pct:"leveraged_net_pct",cftc_net:"leveraged_net",cftc_long:"leveraged_long",cftc_short:"leveraged_short"}[metricKey];
    const priceData=s[priceKey]||{},metricData=cftcField?Object.fromEntries((margin?.cftc?.rows||[]).map(r=>[r.date,r[cftcField]])):s[metricKey]||{};
    const priceName=priceKey==='nasdaq_composite'?'Nasdaq':'S&P 500';
    const metricName=({cnn_fear_greed:'CNN Fear & Greed',vix:'VIX',hy_oas_pct:'HY OAS',ig_oas_pct:'IG OAS',cftc_net_pct:'槓桿基金淨部位占比',cftc_net:'槓桿基金淨部位',cftc_long:'槓桿基金多單',cftc_short:'槓桿基金空單'})[metricKey];
    const metricUnit=metricKey==='hy_oas_pct'||metricKey==='ig_oas_pct'||metricKey==='cftc_net_pct'?'%':cftcField?' 口':'';
    const metricDigits=cftcField&&metricKey!=='cftc_net_pct'?0:metricKey==='cnn_fear_greed'?1:2;
    const metricColor=chartColors[metricKey]||'#b77928';
    const latestDates=[...Object.keys(priceData),...Object.keys(metricData)].sort();
    if(!latestDates.length){groups.append(el('p','us-empty','缺少可以疊合的歷史資料'));return;}
    const from=rangeStart(latestDates.at(-1));
    const dates=[...new Set([...Object.keys(priceData),...Object.keys(metricData)].filter(d=>d>=from))].sort();
    if(dates.length<2){groups.append(el('p','us-empty','指定區間內的資料不足'));return;}
    const chart=el('div','us-overlay-chart');
    const legend=el('div','us-overlay-legend');
    const leftLegend=el('span');leftLegend.style.color=chartColors[priceKey];leftLegend.textContent='● '+priceName+'｜左軸（指數點）';
    const rightLegend=el('span');rightLegend.style.color=metricColor;rightLegend.textContent='● '+metricName+'｜右軸'+(metricUnit?'（%）':'');
    legend.append(leftLegend,rightLegend);chart.append(legend);
    const cursor=el('div','us-overlay-cursor');chart.append(cursor);
    const frame=el('div','us-overlay-frame');
    const W=960,H=490,L=75,R=82,T=23,B=46,plotW=W-L-R,plotH=H-T-B;
    const svg=svgEl('svg',{viewBox:`0 0 ${W} ${H}`,preserveAspectRatio:'none',role:'img','aria-label':priceName+' 與 '+metricName+' 雙 Y 軸疊合圖，拖曳可查詢日期'});
    frame.append(svg);chart.append(frame);
    const valsP=dates.map(d=>priceData[d]).filter(v=>Number.isFinite(v));
    const valsM=dates.map(d=>metricData[d]).filter(v=>Number.isFinite(v));
    if(valsP.length<2||valsM.length<2){groups.append(el('p','us-empty','所選指標沒有足夠數據'));return;}
    const bounds=(vals,floorZero=false)=>{let mn=Math.min(...vals),mx=Math.max(...vals);if(floorZero)mn=0;else{const pad=(mx-mn||mx*.02||1)*.1;mn-=pad;mx+=pad;}mx+=(mx-mn||1)*.1;return [mn,mx];};
    const [pMin,pMax]=bounds(valsP),[mMin,mMax]=metricKey==='cnn_fear_greed'?[0,100]:bounds(valsM);
    const xp=i=>L+i*plotW/(dates.length-1);
    const yp=v=>T+(pMax-v)*plotH/(pMax-pMin);
    const ym=v=>T+(mMax-v)*plotH/(mMax-mMin);
    const axisLabel=(v,metric)=>metric?num(v,metricDigits)+(metricUnit||''):num(v,0);
    for(let n=0;n<=5;n++){
      const y=T+n*plotH/5;
      svg.append(svgEl('line',{x1:L,x2:W-R,y1:y,y2:y,class:'us-overlay-gridline'}));
      const pTick=svgEl('text',{x:L-9,y:y+5,'text-anchor':'end',class:'us-overlay-axis'});pTick.textContent=axisLabel(pMax-n*(pMax-pMin)/5,false);svg.append(pTick);
      const mTick=svgEl('text',{x:W-R+10,y:y+5,'text-anchor':'start',class:'us-overlay-axis'});mTick.textContent=axisLabel(mMax-n*(mMax-mMin)/5,true);svg.append(mTick);
    }
    for(const n of [0,1,2,3,4]){
      const ix=Math.round(n*(dates.length-1)/4);
      const tick=svgEl('text',{x:xp(ix),y:H-14,'text-anchor':n===0?'start':n===4?'end':'middle',class:'us-overlay-axis'});
      tick.textContent=dates[ix].slice(0,7);svg.append(tick);
    }
    if(metricKey==='cnn_fear_greed'){
      const y=ym(10);
      svg.append(svgEl('line',{x1:L,x2:W-R,y1:y,y2:y,class:'us-overlay-threshold'}));
      const label=svgEl('text',{x:W-R-5,y:y-6,'text-anchor':'end',class:'us-overlay-threshold-label'});label.textContent='極度恐懼 10';svg.append(label);
    }
    const addPath=(values,yScale,color,connectSparse=false)=>{
      let path='',prevValid=false;
      dates.forEach((date,i)=>{
        const v=values[date];
        if(!Number.isFinite(v)){if(!connectSparse)prevValid=false;return;}
        path+=(prevValid?'L':'M')+xp(i).toFixed(2)+' '+yScale(v).toFixed(2)+' ';prevValid=true;
      });
      svg.append(svgEl('path',{d:path,fill:'none',stroke:color,'stroke-width':2.4,'stroke-linecap':'round','stroke-linejoin':'round','vector-effect':'non-scaling-stroke'}));
    };
    addPath(priceData,yp,chartColors[priceKey]);addPath(metricData,ym,metricColor,!!cftcField);
    const line=svgEl('line',{y1:T,y2:H-B,class:'us-overlay-crosshair'});svg.append(line);
    const dotP=svgEl('circle',{r:5.8,fill:chartColors[priceKey],stroke:'white','stroke-width':2,'vector-effect':'non-scaling-stroke'});
    const dotM=svgEl('circle',{r:5.8,fill:metricColor,stroke:'white','stroke-width':2,'vector-effect':'non-scaling-stroke'});
    svg.append(dotP,dotM);
    const hit=svgEl('rect',{x:L,y:T,width:plotW,height:plotH,fill:'transparent',class:'us-overlay-hit'});svg.append(hit);
    let selected=-1;
    const setAt=i=>{
      const at=Math.max(0,Math.min(dates.length-1,i));if(at===selected)return;selected=at;
      const d=dates[at],pv=priceData[d],mv=metricData[d];
      line.setAttribute('x1',xp(at));line.setAttribute('x2',xp(at));
      for(const [dot,v,fn] of [[dotP,pv,yp],[dotM,mv,ym]]){dot.style.display=Number.isFinite(v)?'':'none';if(Number.isFinite(v)){dot.setAttribute('cx',xp(at));dot.setAttribute('cy',fn(v));}}
      cursor.replaceChildren(el('strong','us-overlay-date',d),el('span','',priceName+'：'+(Number.isFinite(pv)?num(pv,2):'無當日資料')),el('span','',metricName+'：'+(Number.isFinite(mv)?num(mv,metricDigits)+metricUnit:'無當日資料')));
    };
    const seek=e=>{const bounds=svg.getBoundingClientRect();if(!bounds.width)return;const sx=(e.clientX-bounds.left)/bounds.width*W;setAt(Math.round((sx-L)/plotW*(dates.length-1)));};
    hit.addEventListener('pointerdown',e=>{hit.setPointerCapture?.(e.pointerId);seek(e);});
    hit.addEventListener('pointermove',seek);
    hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();setAt(selected+(e.key==='ArrowLeft'?-1:1));}});
    hit.setAttribute('tabindex','0');hit.setAttribute('role','slider');hit.setAttribute('aria-label','日期查價線，左右方向鍵移動');
    setAt(dates.length-1);
    groups.append(chart);
  }

  function renderCftc(){
    const c=margin?.cftc||{}, rows=c.rows||[], x=rows.at(-1), body=us.querySelector('[data-us-cftc-rows]'), chart=us.querySelector('[data-us-cftc-chart]');
    body.replaceChildren();chart.replaceChildren();
    const note=us.querySelector('[data-us-cftc-note]');
    us.querySelector('[data-us-cftc-date]').textContent=x?'持倉統計日 '+x.date+'｜E-mini・口數':'尚未取得官方資料';
    if(!x){note.textContent='等待 CFTC 官方資料更新';return;}
    for(const [k,label] of [['leveraged','槓桿基金'],['asset','資產管理機構'],['small','非申報交易人']]){const tr=el('tr');tr.append(el('th','',label),el('td','',num(x[k+'_long'],0)),el('td','',num(x[k+'_short'],0)),el('td','',signed(x[k+'_net'],0)),el('td','',signed(x[k+'_net_change'],0)));body.append(tr);}
    note.textContent='槓桿基金淨部位占未平倉量 '+signed(x.leveraged_net_pct,2,'%')+'｜近4次淨部位變動 '+signed(x.leveraged_net_4report_change,0,'口')+'｜近260次歷史百分位 '+num(x.leveraged_net_pct_percentile,1)+'%'+(c.status==='failed'?'｜本次來源更新失敗，保留舊資料':'')+'。期貨部位可能包含避險，不等於現貨買賣；日期為持倉統計日，不可直接用於無前視偏誤回測。';
    chart.append(chartPanel('槓桿基金多空部位','CFTC TFF Futures Only・口數',[{key:'long',name:'多單',color:'#258653',digits:0,values:Object.fromEntries(rows.map(r=>[r.date,r.leveraged_long]))},{key:'short',name:'空單',color:'#c54848',digits:0,values:Object.fromEntries(rows.map(r=>[r.date,r.leveraged_short]))}]));
  }
  function renderMargin(){
    marginSummaryBody.replaceChildren();
    const rows=[...(margin?.rows||[])].sort((a,b)=>a.month.localeCompare(b.month));
    if(!rows.length){
      const tr=el('tr'); const td=el('td','us-empty','FINRA 月融資資料尚未取得'); td.colSpan=3; tr.append(td); marginSummaryBody.append(tr);
      monthChartGroup.replaceChildren(); return;
    }
    const x=rows.at(-1);
    [
      ['最近公布', x.month, 'FINRA 月度資料'],
      ['融資餘額', num(x.margin_million/100,0)+' 億美元', '較前月 '+signed(x.change_million/100,0,' 億')],
      ['融資月增率', signed(x.mom_pct,2,'%'), '年增 '+signed(x.yoy_pct,2,'%')],
      ['相對 S&P 500', signed(x.relative_pp,2,'pp'), '當月 S&P 500 '+signed(x.sp500_return_pct,2,'%')]
    ].forEach(row=>{
      const tr=el('tr');
      const th=el('th','',row[0]); th.scope='row'; tr.append(th, el('td','',row[1]), el('td','',row[2]));
      marginSummaryBody.append(tr);
    });

    const plottedMargin={};
    const history=margin.margin_history&&typeof margin.margin_history==='object'?margin.margin_history:{};
    Object.entries(history).filter(([d,v])=>/^\d{4}-\d{2}$/.test(d)&&Number.isFinite(v)).forEach(([d,v])=>plottedMargin[d]=v/100);
    rows.forEach(r=>{ if(Number.isFinite(r.margin_million)) plottedMargin[r.month]=r.margin_million/100; });
    const spMonthlyIndex={};
    let acc=100;
    rows.forEach((r,i)=>{ if(i===0){ spMonthlyIndex[r.month]=100; } else { acc*=1+((Number.isFinite(r.sp500_return_pct)?r.sp500_return_pct:0)/100); spMonthlyIndex[r.month]=acc; } });

    const syncM=createSyncGroup();
    monthChartGroup.replaceChildren(linkedCard('融資槓桿 × S&P 500（月）', '上圖為 S&P 500 月度累積表現，下圖為 FINRA 融資餘額，方便對照槓桿擴張或收縮與市場走勢。', [
      chartPanel('S&P 500 月度累積表現', '區間起點 = 100', [
        {key:'sp500_month',name:'S&P 500',values:spMonthlyIndex,color:chartColors.sp500,digits:1}
      ], {monthly:true, compact:true, syncGroup:syncM, axisFmt:x=>num(x,0)}),
      chartPanel('FINRA 融資餘額', '單位：億美元', [
        {key:'margin',name:'FINRA 融資',values:plottedMargin,color:chartColors.margin,digits:0}
      ], {monthly:true, compact:true, syncGroup:syncM, axisFmt:x=>num(x,0)})
    ]));

    const tbody=us.querySelector('[data-us-month-rows]'); tbody.replaceChildren();
    rows.slice(-12).reverse().forEach(r=>{
      const tr=el('tr');
      [r.month, num(r.margin_million/100,0), signed(r.mom_pct,2,'%'), signed(r.yoy_pct,2,'%'), signed(r.sp500_return_pct,2,'%'), signed(r.relative_pp,2,'pp')].forEach(str=>tr.append(el('td','',str)));
      tbody.append(tr);
    });
  }

  function render(){
    renderOverviewTable(); renderGroups(); renderMargin(); renderCftc();
    const cutoff=lastValue(sentiment?.series?.cnn_fear_greed)?.date || '尚無日資料';
    const month=margin?.as_of_month || '尚無月資料';
    status.textContent='每日市場資料截至 '+cutoff+'｜FINRA 融資截至 '+month+'｜圖表查價線以實際可得資料同步，不同來源可能有 1～數日公布落差。';
    if(!sentiment||!margin) status.textContent += '｜部分資料來源未成功載入';
  }

  const loadJson = async path => { const r=await fetch('./data/'+path+'?v='+Date.now(),{cache:'no-store'}); if(!r.ok) throw Error(path+' HTTP '+r.status); return r.json(); };
  async function load(){
    if(loading) return loading;
    status.textContent='正在讀取美股情緒、波動、信用利差與 FINRA 融資資料…';
    loading = (async()=>{
      const res = await Promise.allSettled([loadJson('us_sentiment_history.json'), loadJson('us_market_monitor.json')]);
      sentiment = res[0].status==='fulfilled' && res[0].value?.series ? res[0].value : null;
      margin = res[1].status==='fulfilled' && Array.isArray(res[1].value?.rows) ? res[1].value : null;
      if(!sentiment && !margin){ status.textContent='美股資料載入失敗，請檢查兩個 JSON 是否已發布'; return; }
      render();
    })().finally(()=>{ loading=null; });
    return loading;
  }

  us.querySelector('[data-us-refresh]').addEventListener('click', load);
  us.querySelectorAll('[data-us-compare-metric],[data-us-compare-price]').forEach(x=>x.addEventListener('change',renderGroups));
  us.querySelectorAll('[data-us-range]').forEach(b=>b.addEventListener('click',()=>{
    range = b.dataset.usRange;
    us.querySelectorAll('[data-us-range]').forEach(x=>x.setAttribute('aria-pressed', String(x===b)));
    renderGroups(); renderMargin(); renderCftc();
  }));
  tabs.querySelectorAll('button').forEach((button,index)=>button.addEventListener('click',()=>{
    taiwan.hidden = index===1; us.hidden = index===0;
    tabs.querySelectorAll('button').forEach((b,i)=>b.setAttribute('aria-pressed', String(index===i)));
    if(index===1 && !sentiment && !margin) load();
  }));
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
  details.querySelector('summary').textContent = 'V12 燈號與每日狀態｜判斷規則';
  details.insertAdjacentHTML('beforeend', `<p><b>V12 研究候選｜加權風險</b>　風險分數使用 20 日市場廣度變化速度 35%、外資持續性 25%、20 日廣度水準 20%、指數距近 120 日高點回撤 20%，另加 10 日內警訊累積與資金／廣度先後惡化分數。</p><p><b>外資五日 Z-score</b>：五日累計外資淨買賣超相對過去 60 個交易日同指標之標準化異常程度；均值與標準差均排除當日。Z ≤ -2.0 加 3 分。融資單項仍獨立呈現，但不再是綜合燈號的必要條件。</p><p><b>黃燈 38／橘燈 52／紅燈 65 分</b>。紅燈退出門檻 60 分；每日依風險分數升降級，不固定鎖定數天。燈號可跳級，沒有單一外資或融資的必要條件。資料不足顯示待齊而非綠燈。</p><p><b>每日狀態</b>：20 日市場廣度五日變化 ≥+15pp 為「廣度改善」，≤−15pp 為「廣度惡化」；融資五日相對大盤 ≤−3pp 且當日上市櫃合計融資餘額確實下降（資料完整）才為「去槓桿加速」，≥+3pp 為「槓桿加速」。未達門檻不顯示。<b>試單機會</b>沿用原模型：前 15 個交易日曾有 V12 紅燈、當日廣度五日改善 ≥15pp、近 10 日曾有融資五日相對指數 ≤−3pp。只顯示首次觸發當日，後續 10 交易日僅用於事件回測及去重，不延續顯示。V12 分數與燈號不變。</p><p><b>融資綠色提示</b>：上市櫃合計融資餘額當日確實下降，且融資日報酬率減去加權指數日報酬率 ≤ −2pp。既有融資紅／黃燈優先顯示，避免同格混淆。</p><p>此為研究候選 V12，融資／廣度改善條件亦屬探索性輔助訊號，未證實獨立交易優勢。歷史警示時間軸使用這套公式重算，不沿用舊模型的燈號日期。</p>`);
  riskCard.classList.add('mm-risk-card');
  riskCard.setAttribute('aria-live', 'polite');
  const composite = document.createElement('section');
  composite.className = 'mm-composite-page';
  composite.setAttribute('aria-label', '綜合指標每日監控');
  composite.innerHTML = `
    <div class="mm-composite-intro"><span class="mb-eyebrow">COMPOSITE SIGNAL · V12 RESEARCH</span><h2>綜合指標</h2>
      <p>四級風險評分｜點燈號查看明細。</p></div>
    <div class="mm-composite-filters">
      <label>年份 <select data-composite-year aria-label="綜合指標年份"></select></label>
      <label>月份 <select data-composite-month aria-label="綜合指標月份"></select></label>
      <button type="button" data-composite-refresh>重新整理</button>
    </div>
    <div class="mm-composite-status" data-composite-status role="status" hidden></div>
    <p class="mm-table-hint">紅黃警戒｜綠色去槓桿觀察</p>
    <div class="mm-composite-scroll" tabindex="0" role="region" aria-label="每日綜合原始指標，左右滑動，頁面上下捲動">
      <table class="mm-composite-table"><thead><tr>
        <th scope="col">日期／燈號<br>綜合分數</th>
        <th scope="col">外資日<br>買賣超（億）</th>
        <th scope="col">融資日增減 <span class="mm-unit">億元</span><small>上市／上櫃、相對大盤</small></th>
        <th scope="col">20 日<br>市場廣度</th>
        <th scope="col">60 日<br>市場廣度</th>
        <th scope="col">60MA<br>乖離率</th>
        <th scope="col">當日<br>騰落淨家數</th>
      </tr></thead><tbody></tbody></table>
    </div>
    <dialog class="mm-details-dialog" data-mm-details-dialog aria-label="單日綜合燈號詳細分析">
      <div class="mm-dialog-head"><div><strong data-mm-dialog-title>當日模型分析</strong><small data-mm-dialog-subtitle></small></div><button type="button" class="mm-dialog-close" data-mm-dialog-close aria-label="關閉明細">✕</button></div>
      <div class="mm-dialog-content" data-mm-dialog-content></div>
    </dialog>
    <p class="mm-composite-footnote">紅／黃底：警戒；綠底：當日融資去槓桿（相對大盤 ≤−2pp）；60MA 橘／藍綠：過熱／超跌。</p>
    <section class="mm-history" aria-label="歷史重大跌勢燈號回測">
      <div class="mm-history-heading"><div><span class="mb-eyebrow">HISTORICAL DRAWDOWNS</span><h2>歷史重大跌勢｜燈號時間軸</h2><p>按歷史區間自動計算高低點、首次黃／橘／紅燈、轉綠及再次警戒；事件名稱為市場背景，不代表單一成因。</p></div></div>
      <div class="mm-history-filters"><label>警報分類 <select data-history-filter aria-label="歷史跌勢警報篩選"><option value="all">全部跌勢</option><option value="early">紅燈：回撤 5% 前</option><option value="mid">紅燈：回撤 5～10%</option><option value="late">紅燈：回撤 10% 後</option><option value="miss">未亮紅燈</option></select></label><span data-history-count></span></div>
      <div class="mm-history-list" data-mm-history><p class="mm-history-empty">歷史資料載入後顯示。</p></div>
    </section>`;
  composite.prepend(riskCard);
  const credit = document.createElement('section');
  credit.className='twd-root';
  credit.hidden = true;
  tw.append(nav, composite, credit, panel);
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
  const names = ['綜合指標','台股儀表板','騰落線','市場寬度'];
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
    flow.hidden=true;
    credit.hidden=i!==1;
    panel.hidden=i<=1;
    if(i===0){ renderComposite(); if(!twCompositeFunds.length && typeof window.loadTwMonitorData==='function')window.loadTwMonitorData(); return; }
    if(i===1){ if(typeof window.loadTwseCreditDashboard==='function')window.loadTwseCreditDashboard(credit);return; }
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
  // Detail alerts are display-only. V12 scoring, inputs and trigger thresholds are unchanged.
  // Only severe deterioration is colored red; ordinary raw balances remain neutral.
  if(!document.getElementById('mm-detail-severe-style')){
    const severeStyle=document.createElement('style');
    severeStyle.id='mm-detail-severe-style';
    severeStyle.textContent=`
      #marketMonitor .mm-details-dialog .mm-detail-metric.mm-detail-severe > b {
        color:#bd3040 !important;
        font-weight:800 !important;
      }
      html[data-theme="dark"] #marketMonitor .mm-details-dialog .mm-detail-metric.mm-detail-severe > b {
        color:#ff8793 !important;
      }
    `;
    document.head.append(severeStyle);
  }
  // Extreme MA60 divergence: amber = stretched upside, teal = deeply oversold.
  // Scope the colors to this column so other warning lights remain unchanged.
  if(!document.getElementById('mm-bias-extreme-style')){
    const biasStyle=document.createElement('style');
    biasStyle.id='mm-bias-extreme-style';
    biasStyle.textContent=`
      #marketMonitor .mm-composite-table td.mm-bias-overheat > .mm-table-value {
        color:#b66a0e !important;
        background:rgba(210,139,35,.12);
        border-radius:6px;
        padding:4px 7px;
        font-weight:800 !important;
      }
      #marketMonitor .mm-composite-table td.mm-bias-oversold > .mm-table-value {
        color:#087d78 !important;
        background:rgba(18,145,139,.11);
        border-radius:6px;
        padding:4px 7px;
        font-weight:800 !important;
      }
      html[data-theme="dark"] #marketMonitor .mm-composite-table td.mm-bias-overheat > .mm-table-value {
        color:#f4bb69 !important;
        background:rgba(238,165,60,.17);
      }
      html[data-theme="dark"] #marketMonitor .mm-composite-table td.mm-bias-oversold > .mm-table-value {
        color:#73ddd3 !important;
        background:rgba(41,179,169,.18);
      }
    `;
    document.head.append(biasStyle);
  }
  function appendMetric(section,label,value,severe=false,positive=false){
    const line=h('div','mm-detail-metric');
    if(severe)line.classList.add('mm-detail-severe');
    else if(positive)line.classList.add('mm-detail-positive');
    line.append(h('span','',label),h('b','',value));
    section.append(line);
  }
  function makeDailyDetails(r,f,b){
    const body=h('div','mm-detail-grid');
    const group=(name)=>{const sect=h('section','mm-detail-group');sect.append(h('h4','',name));body.append(sect);return sect;};
    const money=group('外資買賣超｜加工分析');
    appendMetric(money,'近 5 日累計（億）',riskNum(r.foreign5,2),Number.isFinite(r.foreign5)&&r.foreign5<=-1000);
    appendMetric(money,'5 日 Z-score（過去 60 日）',riskNum(r.z5,2),Number.isFinite(r.z5)&&r.z5<=-2);
    appendMetric(money,'5 日內黃／紅警戒日數',r.foreignWarn5+'/5',r.foreignWarn5>=4);
    appendMetric(money,'5 日內紅燈日數',r.foreignRed5+'/5',r.foreignRed5>=3);
    appendMetric(money,'外資原始燈號',{'red':'紅燈','yellow':'黃燈','normal':'正常'}[f.foreign_light]||'待齊',f.foreign_light==='red');
    const margin=group('融資｜加工分析');
    const strongDeleveraging=isStrongDailyDeleverage(f);
    appendMetric(margin,'上市融資餘額',riskNum(Number.isFinite(f.twseMargin)?f.twseMargin/1e8:null,2,' 億'));
    appendMetric(margin,'上櫃融資餘額',riskNum(Number.isFinite(f.tpexMargin)?f.tpexMargin/1e8:null,2,' 億'));
    appendMetric(margin,'上市融資日增減',riskNum(Number.isFinite(f.twseMargin)&&Number.isFinite(f.twseMarginPrevious)?(f.twseMargin-f.twseMarginPrevious)/1e8:null,2,' 億'),false,strongDeleveraging&&Number.isFinite(f.twseMargin)&&Number.isFinite(f.twseMarginPrevious)&&f.twseMargin<f.twseMarginPrevious);
    appendMetric(margin,'上櫃融資日增減',riskNum(Number.isFinite(f.tpexMargin)&&Number.isFinite(f.tpexMarginPrevious)?(f.tpexMargin-f.tpexMarginPrevious)/1e8:null,2,' 億'),false,strongDeleveraging&&Number.isFinite(f.tpexMargin)&&Number.isFinite(f.tpexMarginPrevious)&&f.tpexMargin<f.tpexMarginPrevious);
    appendMetric(margin,'上市櫃融資合計餘額',riskNum(Number.isFinite(r.margin)?r.margin/1e8:null,2,' 億'));
    appendMetric(margin,'相對指數當日增幅',riskNum(f.relative,2,' pp'),Number.isFinite(f.relative)&&f.relative>=3,strongDeleveraging);
    appendMetric(margin,'當日積極去槓桿',strongDeleveraging?'是｜融資下降且相對 ≤ −2pp':'未達門檻',false,strongDeleveraging);
    appendMetric(margin,'相對指數 5 日強弱',riskNum(r.relative5,2,' pp'),Number.isFinite(r.relative5)&&r.relative5>=5);
    appendMetric(margin,'相對指數 20 日強弱',riskNum(r.relative20,2,' pp'),Number.isFinite(r.relative20)&&r.relative20>=9);
    appendMetric(margin,'融資原始燈號',{'red':'紅燈','yellow':'黃燈','normal':'正常'}[r.marginLight]||'待齊',r.marginLight==='red');
    const breadth=group('市場廣度／騰落｜加工分析');
    appendMetric(breadth,'20 日廣度 5 日變化',riskNum(-r.drop5,1,' pp'),Number.isFinite(r.drop5)&&r.drop5>=15);
    appendMetric(breadth,'20 日廣度 10 日變化',riskNum(-r.drop10,1,' pp'),Number.isFinite(r.drop10)&&r.drop10>=20);
    appendMetric(breadth,'近 5 日累計騰落淨家數',riskNum(r.net,0),Number.isFinite(r.net)&&r.net<=-2500);
    appendMetric(breadth,'距近 120 日高點回撤',riskNum(r.dd,2,'%'),Number.isFinite(r.dd)&&r.dd>=10);
    appendMetric(breadth,'收盤站上 10 日均線',r.index>=r.ma10?'是':'否');
    appendMetric(breadth,'10 日均線',riskNum(r.ma10,2));
    const parts=group('綜合風險｜評分貢獻');
    appendMetric(parts,'當日綜合分數（非機率／不封頂）',riskNum(r.score,1,' 分'),Number.isFinite(r.score)&&r.score>=TW_RISK_MODEL.red);
    const c=r.components;
    for(const [label,val] of [['廣度速度',c.speed],['外資持續性',c.foreign],['廣度絕對水準',c.breadth],['價格回撤',c.price],['警報累積',c.memory],['序列惡化',c.sequence],['極端外資加分',c.foreignZBonus]])appendMetric(parts,label,riskNum(val,2,' 分'),Number.isFinite(val)&&({'廣度速度':25,'外資持續性':20,'廣度絕對水準':16,'價格回撤':16,'警報累積':10,'序列惡化':4,'極端外資加分':3}[label]??Infinity)<=val);
    const note=h('p','mm-detail-note',r.basis);body.append(note);
    return body;
  }
  // One focused dialog for the tested rebound observation; no extra market-phase scoring.
  const reboundDialog=document.createElement('dialog');
  reboundDialog.className='mm-details-dialog mm-rebound-dialog';
  reboundDialog.setAttribute('aria-label','每日廣度與融資訊號明細');
  reboundDialog.innerHTML='<div class="mm-dialog-head"><div><strong data-rebound-title>市場狀態</strong><small data-rebound-subtitle></small></div><button type="button" class="mm-dialog-close" data-rebound-close aria-label="關閉">✕</button></div><div class="mm-dialog-content" data-rebound-content></div>';
  composite.append(reboundDialog);
  const closeRebound=()=>{if(reboundDialog.open)reboundDialog.close();};
  reboundDialog.querySelector('[data-rebound-close]').addEventListener('click',closeRebound);
  reboundDialog.addEventListener('click',e=>{if(e.target===reboundDialog)closeRebound();});
  document.addEventListener('tw-rebound-detail-request',e=>{
    const date=e.detail?.date,info=twDailySignal(date);
    if(!info.tags.length)return;
    const fmtPP=value=>Number.isFinite(value)?(value>0?'+':'')+value.toFixed(1)+'pp':'—';
    reboundDialog.querySelector('[data-rebound-title]').textContent=info.tags.map(x=>x.name).join(' · ');
    reboundDialog.querySelector('[data-rebound-subtitle]').textContent='';
    const content=reboundDialog.querySelector('[data-rebound-content]');
    content.replaceChildren();
    const section=h('section','mm-detail-group mm-rebound-detail-group');
    section.append(h('h4','','廣度與融資'));
    // Always show both current-day raw five-session changes, including neutral values.
    // Label thresholds only determine which chip is shown, not whether a metric is visible.
    appendMetric(section,'廣度 5 日變化',fmtPP(info.breadth5),
      info.breadth5!==null&&info.breadth5<=-15,
      info.breadth5!==null&&info.breadth5>=15);
    const fmtSigned=(value,unit)=>Number.isFinite(value)?(value>0?'+':'')+value.toFixed(2)+unit:'—';
    appendMetric(section,'當日上市櫃融資合計增減',fmtSigned(info.marginChange,' 億'),false,info.deleverage);
    appendMetric(section,'當日融資增減率',fmtSigned(info.marginChangePct,'%'),false,info.deleverage);
    appendMetric(section,'融資 5 日相對大盤',fmtPP(info.margin5),
      info.margin5!==null&&info.margin5>=3,
      info.deleverage);
    // Trial qualification may rely on an earlier day within the 10-session lookback.
    // Show that separate evidence only if it differs from today's financing value.
    if(info.trial && Number.isFinite(info.state?.signalMarginRelative5)
       && (info.margin5===null || Math.abs(info.state.signalMarginRelative5-info.margin5)>0.001)){
      appendMetric(section,'試單條件：近 10 日融資相對大盤',
        fmtPP(info.state.signalMarginRelative5),false,true);
    }
    content.append(section);
    if(typeof reboundDialog.showModal==='function')reboundDialog.showModal();else reboundDialog.setAttribute('open','');
  });
  const detailDialog=composite.querySelector('[data-mm-details-dialog]');
  const detailTitle=composite.querySelector('[data-mm-dialog-title]');
  const detailSubtitle=composite.querySelector('[data-mm-dialog-subtitle]');
  const detailContent=composite.querySelector('[data-mm-dialog-content]');
  const closeDetail=()=>{if(detailDialog.open)detailDialog.close();};
  composite.querySelector('[data-mm-dialog-close]').addEventListener('click',closeDetail);
  detailDialog.addEventListener('click',e=>{if(e.target===detailDialog)closeDetail();});
  function openDailyDetail(date,r,f,b){
    detailTitle.textContent=date+'｜'+['綠燈','黃燈','橘燈','紅燈'][r.level];
    detailSubtitle.textContent='風險 '+fmtRisk(r.score,1)+' 分｜'+TW_RISK_MODEL.name+'｜分數不封頂';
    detailContent.replaceChildren(makeDailyDetails(r,f,b));
    // Dialog is outside the horizontally scrolled table. Its contents are always visible on mobile.
    if(typeof detailDialog.showModal==='function')detailDialog.showModal();else detailDialog.setAttribute('open','');
  }
  const colorLight=x=>x==='red'?'mm-cbad':x==='yellow'?'mm-cwarn':'';
  function rawMarginLabel(value){if(!Number.isFinite(value))return '待齊';return (value>0?'增 ':value<0?'減 ':'持平 ')+fmtRisk(Math.abs(value),2)+' 億';}
  function renderComposite(){
    closeDetail();
    if(!twCompositeFunds.length){
      compStatus.hidden=false;
      compStatus.textContent='資金與市場廣度資料尚未載入。';
      compBody.replaceChildren();
      return;
    }
    const funds=[...twCompositeFunds].sort((a,b)=>a.date.localeCompare(b.date));
    const breadth=new Map(twCompositeBreadth.map(x=>[x.date,x]));
    // 60MA uses the full daily index history, not just the selected month/year.
    // Require 60 actual positive closes; incomplete windows display a dash.
    const bias60ByDate=new Map();
    let rollingClose=0,invalidClose=0;
    for(let i=0;i<funds.length;i++){
      const close=funds[i].index;
      if(Number.isFinite(close)&&close>0)rollingClose+=close;
      else invalidClose++;
      if(i>=60){
        const removed=funds[i-60].index;
        if(Number.isFinite(removed)&&removed>0)rollingClose-=removed;
        else invalidClose--;
      }
      if(i>=59&&invalidClose===0){
        const ma60=rollingClose/60;
        bias60ByDate.set(funds[i].date,ma60>0?(close/ma60-1)*100:null);
      }
    }
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
    const colCount=composite.querySelectorAll('.mm-composite-table thead th').length;
    compBody.replaceChildren();let calculated=0;
    const appendCell=(tr,value,digits=1,suffix='',tone='')=>{
      const td=tr.insertCell();
      if(tone)td.classList.add(tone);
      const val=h('span','mm-table-value',rawNum(value,digits,suffix));
      if(tone)val.classList.add('mm-table-alert-value');
      td.append(val);
      return td;
    };
    const billionChange=(now,prior)=>Number.isFinite(now)&&Number.isFinite(prior)?(now-prior)/1e8:null;
    for(const f of selected){
      const d=f.date,r=twRiskByDate.get(d),b=breadth.get(d),tr=compBody.insertRow();
      const day=h('th','mm-composite-date',d.slice(5).replace('-','/'));day.scope='row';tr.append(day);
      if(r){
        calculated++;
        const btn=h('button','mm-day-light light-'+r.level,['綠燈','黃燈','橘燈','紅燈'][r.level]);
        btn.type='button';btn.setAttribute('aria-haspopup','dialog');btn.setAttribute('aria-label',d+' '+btn.textContent+'，開啟模型加工數據及評分');
        day.append(btn,h('small','mm-day-score',fmtRisk(r.score,1)+' 分'));
        twAppendDailyTags(day,d);
        btn.addEventListener('click',()=>openDailyDetail(d,r,f,b));
      } else day.append(h('small','mm-day-score','資料待齊'));
      appendCell(tr,f.foreign,2,'',colorLight(f.foreign_light));
      const tw=billionChange(f.twseMargin,f.twseMarginPrevious);
      const otc=billionChange(f.tpexMargin,f.tpexMarginPrevious);
      const margin=tr.insertCell();margin.className='mm-margin-raw';
      // Financing warning is an existing relative-to-market signal, not an inference from the sign of daily change.
      const marginTone=colorLight(f.margin_light)||(isStrongDailyDeleverage(f)?'mm-cgood':'');
      if(marginTone)margin.classList.add(marginTone);
      const pair=h('div','mm-margin-pair');
      for(const [marketLabel,num] of [['上市',tw],['上櫃',otc]]){
        const line=h('div','mm-margin-line');
        line.append(h('span','mm-margin-market',marketLabel));
        const span=h('span','mm-margin-num',Number.isFinite(num)?(num>0?'+':'')+fmtRisk(num,2):'—');
        if(!Number.isFinite(num))span.classList.add('mm-num-unavailable');
        line.append(span);pair.append(line);
      }
      margin.append(pair);
      const delta=h('div','mm-margin-relative',Number.isFinite(f.relative)?
        '相對大盤 '+(f.relative>0?'+':'')+fmtRisk(f.relative,2)+'pp':'相對大盤 —');
      if(isStrongDailyDeleverage(f))delta.classList.add('mm-margin-relative-good');
      margin.append(delta);
      // Breadth colors are display-only thresholds. No change to V12 computation.
      const w20=b?.complete?b.pct20:null,w60=b?.complete?b.pct60:null;
      const breadthTone=x=>Number.isFinite(x)?(x<20?'mm-cbad':x<40?'mm-cwarn':''):'';
      appendCell(tr,w20,1,'%',breadthTone(w20));
      appendCell(tr,w60,1,'%',breadthTone(w60));
      const bias60=bias60ByDate.get(d);
      const biasCell=appendCell(tr,bias60,2,'%');
      // Display-only divergence bands; do not feed this into V12 scoring.
      // > +15%: extended/overheated (amber); < -15%: deeply oversold (teal).
      if(Number.isFinite(bias60)){
        if(bias60>0)biasCell.querySelector('.mm-table-value').textContent='+'+fmtRisk(bias60,2)+'%';
        if(bias60>15)biasCell.classList.add('mm-bias-overheat');
        else if(bias60< -15)biasCell.classList.add('mm-bias-oversold');
      }
      appendCell(tr,b?.complete?b.net:null,0);

    }
    if(!selected.length){const tr=compBody.insertRow(),td=tr.insertCell();td.colSpan=colCount;td.textContent='本月尚無交易日資料';}
    compStatus.textContent='';
    compStatus.hidden=true;
    // Source of truth is exactly the model used by rows above. Do not leave initial HTML "載入中".
    paintTwRisk(newest);
  }
  compYear.addEventListener('change',()=>{compMonth.value='';renderComposite();});
  compMonth.addEventListener('change',renderComposite);
  composite.querySelector('[data-composite-refresh]').addEventListener('click',()=>{
    if(typeof window.loadTwMonitorData==='function')window.loadTwMonitorData();
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
  const toneByLevel=['neutral','yellow','orange','red'];
  const levelNames=['綠燈','黃燈','橘燈','紅燈'];
  function eventSignals(period,peak,trough){
    const states=[];
    let prior=null,firstAlert=false;
    for(const row of period){
      const risk=twRiskByDate.get(row.date);
      if(!risk)continue;
      const level=risk.level;
      if(!firstAlert){if(level===0)continue;firstAlert=true;}
      if(level!==prior){
        const priorLevel=prior;
        states.push({date:row.date,index:row.index,level,drop:datePct(peak.index,row.index),after:datePct(row.index,trough.index),
          beforeLow:row.date<=trough.date,kind:level===0?'green':priorLevel===0?'restart':priorLevel===null?'initial':'change'});
      }
      prior=level;
    }
    return states;
  }
  function addTimeline(body,peak,trough,period,report,states){
    const root=h('section','mm-single-timeline mm-timeline-compact');
    const controls=h('div','mm-timeline-controls');
    controls.append(h('strong','','風險演變'));
    const choices=h('div','mm-timeline-choices');
    const dateBtn=h('button','','依日期'),dropBtn=h('button','','依跌幅');
    for(const b of [dateBtn,dropBtn]){b.type='button';choices.append(b);}
    controls.append(choices);root.append(controls);
    // Display only the first warning of each severity before the trough.
    // The full history, including green reversals and renewed warnings, stays below.
    const markers=[{date:peak.date,drop:0,labels:['高點'],level:0,edge:'peak'}];
    for(const level of [1,2,3]){
      const signal=report[level];if(!signal)continue;
      const existing=markers.find(x=>!x.edge&&x.date===signal.date);
      if(existing){existing.labels.push(levelNames[level]);existing.level=Math.max(existing.level,level);}
      else if(signal.date!==peak.date&&signal.date!==trough.date)
        markers.push({date:signal.date,drop:signal.drop,labels:[levelNames[level]],level});
    }
    markers.push({date:trough.date,drop:datePct(peak.index,trough.index),labels:['低點'],level:0,edge:'trough'});
    const chart=h('div','mm-compact-chart');
    const rail=h('div','mm-compact-rail');
    rail.append(h('div','mm-compact-bar'));chart.append(rail);root.append(chart);
    const note=h('p','mm-timeline-foot','節點依日期或高點回撤比例排列；相近警戒點為避免重疊會略作錯位。完整轉綠與再次警戒見下方紀錄。');
    root.append(note);
    const dates=period.map(x=>x.date);
    const highToLow=Math.max(.001,Math.abs(datePct(peak.index,trough.index)));
    function render(mode){
      dateBtn.setAttribute('aria-pressed',String(mode==='date'));
      dropBtn.setAttribute('aria-pressed',String(mode==='drop'));
      rail.querySelectorAll('.mm-compact-node').forEach(el=>el.remove());
      const points=markers.map(x=>{
        const index=dates.indexOf(x.date);
        const raw=mode==='date'?100*Math.max(0,index)/Math.max(1,dates.indexOf(trough.date))
          :100*Math.abs(x.drop)/highToLow;
        return {...x,pos:Math.max(0,Math.min(100,raw))};
      }).sort((a,b)=>a.pos-b.pos||a.date.localeCompare(b.date));
      // Preserve endpoints; enforce minimum marker distance only for legibility.
      // Display labels still contain their true event dates/peak drawdowns.
      const minGap=points.length>=5?18:points.length===4?21:25;
      const positioned=points.map((p,i)=>i===0?0:i===points.length-1?100:p.pos);
      for(let i=1;i<positioned.length-1;i++)positioned[i]=Math.max(positioned[i],positioned[i-1]+minGap);
      for(let i=positioned.length-2;i>0;i--)positioned[i]=Math.min(positioned[i],positioned[i+1]-minGap);
      for(let i=0;i<points.length;i++){
        const x=points[i];
        const node=h('div','mm-compact-node mm-one-'+toneByLevel[x.level]);
        if(x.edge)node.classList.add('mm-node-'+x.edge);
        if(x.labels.length>1)node.classList.add('mm-compact-combined');
        node.style.left=positioned[i]+'%';
        const label=h('strong','mm-node-label',x.labels.join('／'));
        const dot=h('span','mm-node-dot');
        const details=x.edge?h('small','mm-node-value',x.date.slice(5).replace('-','/')):
          h('small','mm-node-value',x.drop.toFixed(2)+'%');
        node.append(label,dot,details);
        node.title=x.labels.join('／')+'｜'+x.date+'｜'+x.drop.toFixed(2)+'%';
        rail.append(node);
      }
    }
    dateBtn.addEventListener('click',()=>render('date'));
    dropBtn.addEventListener('click',()=>render('drop'));
    render('date');body.append(root);
  }
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
      const endDate=event.ongoing?funds.at(-1).date:(funds.at(-1).date<event.end?funds.at(-1).date:event.end);
      let period=funds.filter(x=>x.date>=peak.date&&x.date<=endDate);
      if(period.length<5)continue;
      let recovery=0,closedAt=null;
      if(event.ongoing){
        for(let k=1;k<period.length;k++){
          recovery=datePct(peak.index,period[k].index)>-5?recovery+1:0;
          if(recovery>=10){closedAt=period[k].date;period=period.slice(0,k+1);break;}
        }
      }
      const trough=period.reduce((a,b)=>b.index<a.index?b:a);
      if(trough.date===peak.date)continue;
      const drawdown=datePct(peak.index,trough.index);
      if(drawdown>-10)continue;
      // Only the first early warning before the trough is used for lead-time metrics.
      const path=period.filter(x=>x.date<=trough.date);
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
      const states=eventSignals(period,peak,trough);
      addTimeline(body,peak,trough,period,report,states);
      const inPeriod=twRecoveryEvents.filter(x=>x.date>=peak.date&&x.date<=endDate);
      if(inPeriod.length){
        const recoveryLog=h('details','mm-history-recovery');
        recoveryLog.append(h('summary','','試單機會｜'+inPeriod.length+' 次觸發'));
        const recoveryList=h('div','mm-history-recovery-list');
        for(const evt of inPeriod){
          const line=h('div','mm-history-recovery-line');
          line.append(h('b','','條件成立 '+evt.date),h('small','','觀察到期 '+(evt.endDate||'尚未到期')));
          recoveryList.append(line);
        }
        recoveryLog.append(recoveryList);body.append(recoveryLog);
      }
      const redDays=red?Math.max(0,path.length-1-path.findIndex(x=>x.date===red.date)):null;
      const quality=h('div','mm-history-quality mm-quality-grid');
      const qualityItem=(name,value)=>{const x=h('div','mm-quality-item');x.append(h('small','',name),h('strong','',value));return x;};
      if(red){
        quality.append(qualityItem('紅燈後至低點',Math.abs(red.after).toFixed(2)+'%'),qualityItem('紅燈提前低點',redDays+' 個交易日'));
      }else quality.append(qualityItem('紅燈警戒','區間內未觸發'));
      body.append(quality);
      const full=h('details','mm-history-changes');full.append(h('summary','','完整燈號變化紀錄（含轉綠、再次警戒）'));
      const log=h('div','mm-history-log');
      const greens=states.filter(x=>x.level===0);
      let falseGreen=0,maxAfterGreen=0,restart=0;
      const positions=new Map(period.map((x,i)=>[x.date,i]));
      for(const state of states){
        if(state.level===0 && state.beforeLow){
          const start=positions.get(state.date),end=positions.get(trough.date);
          const fall=Math.min(...period.slice(start,end+1).map(x=>datePct(state.index,x.index)));
          if(fall<0){falseGreen++;maxAfterGreen=Math.max(maxAfterGreen,-fall);}
        }
        if(state.kind==='restart')restart++;
        const line=h('div','mm-history-change mm-change-'+toneByLevel[state.level]);
        line.append(h('b','',state.date),h('span','',levelNames[state.level]),h('span','',state.drop.toFixed(2)+'%'),
          h('small','',state.level===0?(state.beforeLow?'低點前解除｜需追蹤是否再破底':'低點後解除'):(state.kind==='restart'?'轉綠後重新警戒':'警戒變化')));
        log.append(line);
      }
      if(!states.length)log.append(h('p','','區間內沒有有效警戒變化紀錄。'));
      full.append(log);body.append(full);
      const greenSummary=h('p','mm-history-green-summary',
        '轉綠 '+greens.length+' 次 · 低點前轉綠 '+falseGreen+' 次 · 轉綠後再次警戒 '+restart+' 次 · 過早轉綠後最大再跌 '+maxAfterGreen.toFixed(2)+'%');
      body.append(greenSummary);
      if(event.ongoing&&!closedAt)body.append(h('p','mm-history-pending','進行中：資料截至 '+funds.at(-1).date+'；新低會更新。連續 10 日回撤小於 5% 才標示事件結束。'));
      else if(event.ongoing&&closedAt)body.append(h('p','mm-history-pending','本事件已依修復條件於 '+closedAt+' 結束。'));
      else if(event.end>endDate)body.append(h('p','mm-history-pending','此區間尚未到預定觀察終點，暫定低點以最新交易資料為準。'));
      card.append(body);historyHost.append(card);
    }
    historyCount.textContent='顯示 '+count+' 段跌勢';
    if(!count)historyHost.textContent='沒有符合目前篩選條件的重大跌勢；或歷史資料尚未載入。';
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



/* Official TWSE credit dashboard (display only). Never changes V12 calculations. */
(() => {
  'use strict';
  let loading = null, cache = null, chartMetric = 'maintenance_ratio', chartRange = 'all', activeDate = null;
  const FIELDS = [
    {key:'maintenance_ratio',label:'全市場擔保維持率',unit:'%',digits:2,pp:true,negativeRisk:true},
    {key:'credit_accounts',label:'當日信用交易戶數',unit:'戶',digits:0},
    {key:'credit_account_ratio',label:'信用交易戶數占總開戶數比重',unit:'%',digits:2,pp:true},
    {key:'call_accounts',label:'追繳戶數',unit:'戶',digits:0},
    {key:'call_amount',label:'追繳金額',unit:'億元',digits:2},
    {key:'disposal_accounts',label:'處分戶數',unit:'戶',digits:0},
    {key:'disposal_amount',label:'處分金額',unit:'億元',digits:2}
  ];
  const lookup = Object.fromEntries(FIELDS.map(f => [f.key, f]));
  const CHART = Object.freeze({W:720,H:265,L:58,R:700,T:20,B:212});
  const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (x, n = 2) => typeof x === 'number' && Number.isFinite(x)
    ? x.toLocaleString('zh-TW', {minimumFractionDigits:n, maximumFractionDigits:n}) : '—';
  const latest = rows => rows[rows.length - 1];
  const visibleRows = rows => chartRange === 'all' ? rows : rows.slice(-Number(chartRange));
  const validMetricValue = (row, key = chartMetric) => Number.isFinite(row?.[key]);
  function resolveFocusIndex(rows) {
    if (!rows.length) return 0;
    const byDate = rows.findIndex(r => r.date === activeDate && validMetricValue(r));
    if (byDate >= 0) return byDate;
    for (let i = rows.length - 1; i >= 0; i--) if (validMetricValue(rows[i])) return i;
    return rows.length - 1;
  }
  const deltaSuffix = f => f.pp ? ' pp' : f.unit === '戶' ? ' 戶' : ` ${f.unit}`;
  const delta = (v, f) => v == null ? '—' : `${v > 0 ? '+' : ''}${fmt(v, f.digits)}${deltaSuffix(f)}`;
  const direction = (v, f) => v == null ? 'neutral'
    : (f.negativeRisk ? (v < 0 ? 'warn' : v > 0 ? 'cool' : 'neutral') : (v > 0 ? 'warn' : v < 0 ? 'cool' : 'neutral'));
  const chartSeriesLabel = (row, field) => row ? `${row.date} · ${fmt(row[field.key], field.digits)} ${field.unit}` : '—';
  const change = (rows, i, key, n) => {
    if (!cache?.calendar?.length || i < 0 || !Number.isFinite(rows[i]?.[key])) return null;
    const cal = cache.calendar, at = cal.indexOf(rows[i].date), before = cal[at - n];
    if (at < n || !before) return null;
    const map = new Map(rows.map(r => [r.date, r]));
    if (cal.slice(at - n, at + 1).some(d => !Number.isFinite(map.get(d)?.[key]))) return null;
    return rows[i][key] - map.get(before)[key];
  };
  function cards(rows) {
    const last = latest(rows), idx = rows.length - 1;
    const cells = FIELDS.map(f => {
      const d1=change(rows,idx,f.key,1), d5=change(rows,idx,f.key,5);
      return `<button type="button" class="twd-market-row ${chartMetric===f.key?'is-active':''}" data-twd-card-metric="${f.key}" aria-pressed="${chartMetric===f.key}" title="查看${f.label}歷史趨勢">`
        + `<span class="twd-market-label">${f.label}</span>`
        + `<span class="twd-market-number">${fmt(last[f.key],f.digits)}<small>${f.unit}</small></span>`
        + `<span class="twd-market-change ${direction(d1,f)}">${delta(d1,f)}</span>`
        + `<span class="twd-market-change ${direction(d5,f)}">${delta(d5,f)}</span>`
        + `</button>`;
    }).join('');
    return `<section class="twd-market-sheet" aria-label="台股信用風險七項指標">`
      + `<div class="twd-market-sheet-title"><div><span class="twd-market-section-tag">CREDIT RISK · TWSE</span><h3>信用交易監測</h3></div><span class="twd-market-asof">${last.date} <span>收盤資料</span></span></div>`
      + `<div class="twd-market-cols"><span>指標</span><span>最新數值</span><span>1 日變化</span><span>5 日變化</span></div>`
      + `<div class="twd-market-rows">${cells}</div>`
      + `<div class="twd-market-footer">點選任一指標，即可切換下方歷史走勢與查價線</div></section>`;
  }
  function chart(rows) {
    const field = lookup[chartMetric], range = visibleRows(rows), valid = range.filter(r => validMetricValue(r, chartMetric));
    if (valid.length < 2) return '<div class="twd-chart-empty">歷史有效資料不足，暫不繪製走勢</div>';
    const {W,H,L,R,T,B} = CHART;
    let lo = Math.min(...valid.map(x => x[chartMetric])), hi = Math.max(...valid.map(x => x[chartMetric]));
    const pad = (hi - lo || Math.abs(hi) * .02 || 1) * .13;
    lo -= pad; hi += pad;
    const x = i => L + (R - L) * i / Math.max(1, range.length - 1);
    const y = v => B - (v - lo) / (hi - lo) * (B - T);
    const formatAxis = value => `${fmt(value, field.digits)}${field.unit === '%' ? '%' : ''}`;
    let d = '', open = false;
    range.forEach((row, i) => {
      const value = row[chartMetric];
      if (!Number.isFinite(value)) { open = false; return; }
      d += (open ? ' L ' : 'M ') + x(i).toFixed(2) + ' ' + y(value).toFixed(2);
      open = true;
    });
    const focusIndex = resolveFocusIndex(range);
    const focusRow = range[focusIndex];
    activeDate = focusRow?.date ?? activeDate;
    const ticks = [0,1,2,3,4].map(i => {
      const value = lo + (hi - lo) * i / 4, cy = y(value);
      return `<line x1="${L}" x2="${R}" y1="${cy}" y2="${cy}" class="twd-grid-line"/>`
        + `<text x="${L - 9}" y="${cy + 4}" text-anchor="end" class="twd-axis-text">${formatAxis(value)}</text>`;
    }).join('');
    const mid = range[Math.floor((range.length - 1) / 2)]?.date?.slice(5) ?? '';
    return `<div class="twd-chart-caption"><strong data-twd-cross-value>${escape(chartSeriesLabel(focusRow, field))}</strong><span>拖曳 / 滑動查價 · 點上方卡片可切換指標</span></div>`
      + `<svg class="twd-chart-svg" viewBox="0 0 ${W} ${H}" role="img" tabindex="0" aria-label="${field.label}歷史走勢，可滑動查看日期">`
      + `${ticks}`
      + `<path d="${d}" class="twd-line-path"/>`
      + `<line data-twd-cross x1="${x(focusIndex)}" x2="${x(focusIndex)}" y1="${T}" y2="${B}" class="twd-crosshair"/>`
      + `<circle data-twd-cross-point r="5" cx="${x(focusIndex)}" cy="${Number.isFinite(focusRow?.[chartMetric]) ? y(focusRow[chartMetric]) : T}" class="twd-cross-point"/>`
      + `<text x="${L}" y="${H - 12}" class="twd-axis-text">${escape(range[0].date.slice(5))}</text>`
      + `<text x="${(L + R) / 2}" y="${H - 12}" text-anchor="middle" class="twd-axis-text">${escape(mid)}</text>`
      + `<text x="${R}" y="${H - 12}" text-anchor="end" class="twd-axis-text">${escape(latest(range).date.slice(5))}</text>`
      + `</svg>`;
  }
  function render(root) {
    const rows = cache?.rows || [];
    const asof = latest(rows)?.date ?? '尚無已驗證資料';
    root.innerHTML = `<div class="twd-head"><div><span class="twd-eyebrow">TWSE CREDIT RISK</span><h2>台股儀表板</h2><p>信用交易｜官方已驗證資料 · ${escape(asof)}</p></div><button type="button" data-twd-refresh>重新整理</button></div>`
      + (!rows.length
        ? `<div class="twd-pending"><strong>官方資料尚待驗證</strong><p>目前未取得可確認日期與七個欄位的交易所資料。請先執行資料回補／每日更新，不以示意數字或前一日資料冒充最新值。</p><a href="https://www.twse.com.tw/dashboard/zh/credit/margin.html" target="_blank" rel="noopener">開啟 TWSE 官方儀表板</a></div>`
        : `${cards(rows)}<div class="twd-chart-card"><div class="twd-chart-top"><h3>歷史趨勢</h3><label>指標 <select data-twd-metric>${FIELDS.map(f => `<option value="${f.key}" ${f.key === chartMetric ? 'selected' : ''}>${f.label}</option>`).join('')}</select></label><label>區間 <select data-twd-range>${[['20','20 日'],['60','60 日'],['all','全部']].map(([v,t]) => `<option value="${v}" ${v === chartRange ? 'selected' : ''}>${t}</option>`).join('')}</select></label></div><div data-twd-plot>${chart(rows)}</div><p class="twd-chart-note">查價線互動比照騰落線；缺漏日不中途補值，也不跨缺口計算變化。</p></div><section class="twd-table-section"><div class="twd-table-head"><h3>每日明細</h3><span>日期固定 · 左右滑動</span></div><div class="twd-scroller" tabindex="0"><table class="twd-table"><thead><tr><th>日期</th>${FIELDS.map(f => `<th>${f.label}<small>${f.unit}｜1 日／5 日</small></th>`).join('')}</tr></thead><tbody>${[...rows].reverse().map((row, reverse) => { const i = rows.length - 1 - reverse; return `<tr><th>${escape(row.date.slice(5))}</th>${FIELDS.map(f => { const d1 = change(rows, i, f.key, 1), d5 = change(rows, i, f.key, 5); return `<td><b>${fmt(row[f.key], f.digits)}</b><small class="${direction(d1, f)}">日 ${delta(d1, f)}</small><small class="${direction(d5, f)}">5 日 ${delta(d5, f)}</small></td>`; }).join('')}</tr>`; }).join('')}</tbody></table></div></section><p class="twd-source-note">來源：臺灣證券交易所臺股儀表板 BFIJ3U 官方資料。統計值按官方日期保存；前 1／5 日比較前 1／5 個官方交易日。若歷史資料缺漏，不計算跨缺口變化。<a href="https://www.twse.com.tw/dashboard/zh/credit/margin.html" target="_blank" rel="noopener">官方來源</a>。</p>`);

    root.querySelector('[data-twd-refresh]').onclick = () => load(root, true);
    root.querySelector('[data-twd-metric]')?.addEventListener('change', e => { chartMetric = e.target.value; render(root); });
    root.querySelector('[data-twd-range]')?.addEventListener('change', e => { chartRange = e.target.value; render(root); });
    root.querySelectorAll('[data-twd-card-metric]').forEach(card => {
      const activate = () => { chartMetric = card.dataset.twdCardMetric; render(root); };
      card.addEventListener('click', activate);
      // Native button already supports Enter and Space.
    });

    const plot = root.querySelector('[data-twd-plot]');
    const svg = plot?.querySelector('svg');
    if (svg) {
      const range = visibleRows(rows);
      const field = lookup[chartMetric];
      const line = plot.querySelector('[data-twd-cross]');
      const point = plot.querySelector('[data-twd-cross-point]');
      const caption = plot.querySelector('[data-twd-cross-value]');
      const {L,R,T,B} = CHART;
      const valid = range.filter(r => validMetricValue(r));
      let lo = Math.min(...valid.map(r => r[chartMetric])), hi = Math.max(...valid.map(r => r[chartMetric]));
      const pad = (hi - lo || Math.abs(hi) * .02 || 1) * .13;
      lo -= pad; hi += pad;
      const xAt = i => L + (R - L) * i / Math.max(1, range.length - 1);
      const yAt = v => B - (v - lo) / (hi - lo) * (B - T);
      function setFocus(i) {
        const row = range[Math.max(0, Math.min(range.length - 1, i))];
        if (!row) return;
        activeDate = row.date;
        caption.textContent = chartSeriesLabel(row, field);
        const x = xAt(Math.max(0, Math.min(range.length - 1, i)));
        if (line) { line.setAttribute('x1', x); line.setAttribute('x2', x); }
        if (point) {
          if (!Number.isFinite(row[chartMetric])) point.setAttribute('visibility', 'hidden');
          else {
            point.setAttribute('visibility', 'visible');
            point.setAttribute('cx', x);
            point.setAttribute('cy', yAt(row[chartMetric]));
          }
        }
      }
      setFocus(resolveFocusIndex(range));
      svg.style.touchAction = 'pan-y pinch-zoom';
      svg.style.userSelect = 'none';
      let activePointer = null;
      let lastPulse = -Infinity;
      function move(e) {
        const transform = svg.getScreenCTM();
        if (!transform) return;
        const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(transform.inverse());
        const fraction = Math.max(0, Math.min(1, (pt.x - L) / (R - L)));
        setFocus(Math.round(fraction * (range.length - 1)));
        if (activePointer === e.pointerId && e.pointerType !== 'mouse' && typeof navigator.vibrate === 'function' && performance.now() - lastPulse >= 55) {
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
      const release = e => { if (activePointer === e.pointerId) activePointer = null; };
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(name => svg.addEventListener(name, release));
      svg.addEventListener('keydown', e => {
        if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
        e.preventDefault();
        const at = Math.max(0, range.findIndex(r => r.date === activeDate));
        setFocus(at + (e.key === 'ArrowRight' ? 1 : -1));
      });
    }
  }
  async function load(root, force = false) {
    if (loading) return loading;
    if (cache && !force) { render(root); return; }
    loading = (async () => {
      try {
        const res = await fetch('./data/twse_credit_dashboard.json?v=' + Date.now(), {cache:'no-store'});
        if (!res.ok) throw Error('HTTP ' + res.status);
        const doc = await res.json();
        if (!Array.isArray(doc.rows) || doc.rows.some(r => !/^20\d{2}-\d{2}-\d{2}$/.test(r.date) || FIELDS.some(f => r[f.key] !== null && r[f.key] !== undefined && !Number.isFinite(r[f.key])))) throw Error('Invalid schema');
        cache = {...doc, rows:[...new Map(doc.rows.map(r => [r.date, r])).values()].sort((a, b) => a.date.localeCompare(b.date))};
      } catch (err) {
        if (!cache) cache = {rows:[]};
        console.warn('TWSE official credit data:', err.message);
      } finally {
        loading = null;
        render(root);
      }
    })();
    return loading;
  }
  window.loadTwseCreditDashboard = load;
})();

