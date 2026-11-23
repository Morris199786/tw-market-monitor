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
  marginRelative5:-3,observeDays:10,weakBreadth5:-10,weakScoreRise:15,
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
      const event={date:f.date,weakDate:null,endDate:null,score:r.score,breadth5,marginRelative5:marginEvidence?.relative5??null,marginDate:marginEvidence?.date??null};
      events.push(event);active={index:i,event};lastEventIndex=i;
      states.set(f.date,{status:'confirmed',eventDate:event.date,breadth5,redHistory,marginHistory,
        trigger:true,confirmScore:event.score,signalBreadth5:event.breadth5,signalMarginRelative5:event.marginRelative5,signalMarginDate:event.marginDate});
      continue;
    }
    if(active){
      const event=active.event;
      const weak=Number.isFinite(breadth5)&&(
        breadth5<=TW_RECOVERY_RULE.weakBreadth5||
        (!!r&&r.score-event.score>=TW_RECOVERY_RULE.weakScoreRise&&breadth5<0));
      if(weak&&!event.weakDate)event.weakDate=f.date;
      states.set(f.date,{status:event.weakDate?'weak':'confirmed',eventDate:event.date,
        breadth5,redHistory,marginHistory,trigger:false,weakDate:event.weakDate,
        confirmScore:event.score,scoreRise:r?r.score-event.score:null,signalBreadth5:event.breadth5,signalMarginRelative5:event.marginRelative5,signalMarginDate:event.marginDate});
    }else{
      states.set(f.date,{status:'none',breadth5,redHistory,marginHistory,trigger:false});
    }
  }
  // A separate CURRENT five-session snapshot drives the colored classification.
  // Do not mistake a past-ten-session event for today's financing direction.
  for(let i=0;i<rows.length;i++){
    const st=states.get(rows[i].date);
    if(!st)continue;
    const f=rows[i],previous=i>=5?rows[i-5]:null;
    const valid=Number.isFinite(f.margin)&&f.margin>0&&Number.isFinite(previous?.margin)&&previous.margin>0;
    st.marginCurrent5=valid?100*(f.margin/previous.margin-1):null;
    st.marginRelativeCurrent5=Number.isFinite(f.relative5)?f.relative5:null;
    st.marginRecentEvidence=[...rows.slice(Math.max(0,i-TW_RECOVERY_RULE.marginLookback+1),i+1)]
      .reverse().find(x=>Number.isFinite(x.relative5)&&x.relative5<=TW_RECOVERY_RULE.marginRelative5)?.date||null;
  }
  // Expiry has no special warning; the first day after the 10-session window is neutral.
  return {states,events};
}

// Display classification uses CURRENT 5-day financing and breadth readings.
// Only the original three-condition observation uses the rolling 10-day evidence.
const TW_PHASE_RULE=Object.freeze({breadthStrong:15,breadthFlat:3,breadthWeak:-5});
function getTwRecoveryPhase(state){
  const pending={key:'pending',label:'資料待齊',financing:'資料不足',breadth:'資料不足',summary:'等待完整資料'};
  if(!state)return pending;
  const breadth=state.breadth5,relative=state.marginRelativeCurrent5,marginChange=state.marginCurrent5;
  if(!Number.isFinite(breadth)||!Number.isFinite(relative)||!Number.isFinite(marginChange))return pending;
  const actualDeleveraging=marginChange<0&&relative<=TW_RECOVERY_RULE.marginRelative5;
  const relativeCooling=!actualDeleveraging&&relative<=TW_RECOVERY_RULE.marginRelative5;
  const financing=actualDeleveraging?'去槓桿明顯':relativeCooling?'相對大盤收縮':'未明顯去槓桿';
  const strong=breadth>=TW_PHASE_RULE.breadthStrong;
  const down=breadth<=TW_PHASE_RULE.breadthWeak;
  const flat=Math.abs(breadth)<=TW_PHASE_RULE.breadthFlat;
  const breadthLabel=strong?'明顯改善':down?'持續惡化':flat?'變化有限':breadth>0?'逐步改善':'小幅轉弱';
  const make=(key,label,summary)=>({key,label,financing,breadth:breadthLabel,summary});
  if(strong&&actualDeleveraging)return make('sync','融資與廣度同步改善','融資下降且廣度顯著回升');
  if(strong)return make('breadth','廣度率先改善',relativeCooling?'廣度改善，融資相對增幅放緩':'市場參與度顯著回升');
  if(down&&actualDeleveraging)return make('deleveraging','去槓桿中','融資下降，但廣度持續惡化');
  if(flat&&actualDeleveraging)return make('flat','去槓桿＋廣度持平','融資下降，廣度變化有限');
  if(down)return make('risk','廣度持續惡化',relativeCooling?'融資相對降溫，廣度仍惡化':'市場廣度持續下降');
  if(actualDeleveraging)return make('deleveraging','去槓桿中',breadth>0?'融資下降，廣度逐步改善':'融資下降，廣度小幅轉弱');
  if(flat)return make('neutral','廣度持平','融資與廣度未見強烈同步訊號');
  return breadth>0?make('mild','廣度逐步改善','廣度小幅回升'):make('soft','廣度小幅轉弱','廣度小幅下滑');
}
function getTwRecoveryObservationText(state){
  if(!state)return '資料待齊';
  if(state.status==='weak')return '改善條件轉弱';
  if(state.status==='confirmed')return '改善條件成立（觀察中）';
  return '未進入觀察';
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
     // The two-indicator classification is current-day; the V12 alert is unchanged.
     const recovery=twRecoveryByDate.get(date),phase=getTwRecoveryPhase(recovery);
     const observation=document.createElement('section');observation.className='mm-risk-recovery is-'+phase.key;
     const heading=document.createElement('div');heading.className='mm-risk-recovery-heading';
     const name=document.createElement('strong');name.textContent='融資／廣度觀察';
     const pill=document.createElement('span');pill.className='mm-risk-recovery-status';pill.textContent=phase.label;
     heading.append(name,pill);
     const signedPP=v=>Number.isFinite(v)?(v>0?'+':'')+v.toFixed(1)+'pp':'—';
     const signedPct=v=>Number.isFinite(v)?(v>0?'+':'')+v.toFixed(1)+'%':'—';
     const facts=document.createElement('div');facts.className='mm-risk-recovery-breakdown';
     const fact=(label,value,detail)=>{
       const cell=document.createElement('div');cell.className='mm-risk-recovery-fact';
       const a=document.createElement('span');a.className='mm-recovery-fact-label';a.textContent=label;
       const b=document.createElement('b');b.textContent=value;
       const c=document.createElement('small');c.textContent=detail;
       cell.append(a,b,c);return cell;
     };
     facts.append(
       fact('融資',phase.financing,'5日餘額 '+signedPct(recovery?.marginCurrent5)+'｜相對大盤 '+signedPP(recovery?.marginRelativeCurrent5)),
       fact('市場廣度',phase.breadth,'20日廣度・5日變化 '+signedPP(recovery?.breadth5))
     );
     const note=document.createElement('p');note.className='mm-risk-recovery-note';note.textContent=phase.summary;
     observation.append(heading,facts,note);
     if(recovery?.status==='confirmed'||recovery?.status==='weak'){
       const foot=document.createElement('p');foot.className='mm-risk-recovery-foot';
       foot.textContent=getTwRecoveryObservationText(recovery)+'｜首次符合 '+recovery.eventDate+(recovery.weakDate?'｜首次轉弱 '+recovery.weakDate:'');
       observation.append(foot);
     }
     summary.append(observation);

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
  details.querySelector('summary').textContent = 'V12 燈號與融資／廣度觀察｜判斷規則';
  details.insertAdjacentHTML('beforeend', `<p><b>V12 研究候選｜加權風險</b>　風險分數使用 20 日市場廣度變化速度 35%、外資持續性 25%、20 日廣度水準 20%、指數距近 120 日高點回撤 20%，另加 10 日內警訊累積與資金／廣度先後惡化分數。</p><p><b>外資五日 Z-score</b>：五日累計外資淨買賣超相對過去 60 個交易日同指標之標準化異常程度；均值與標準差均排除當日。Z ≤ -2.0 加 3 分。融資單項仍獨立呈現，但不再是綜合燈號的必要條件。</p><p><b>黃燈 38／橘燈 52／紅燈 65 分</b>。紅燈退出門檻 60 分；每日依風險分數升降級，不固定鎖定數天。燈號可跳級，沒有單一外資或融資的必要條件。資料不足顯示待齊而非綠燈。</p><p><b>融資／廣度觀察</b>：彩色分類只看當日可得的五日資料：融資餘額五日確實減少且五日相對大盤 ≤ −3pp 才稱為「去槓桿明顯」；若只有相對大盤收縮，明示「相對大盤收縮」，不誤稱融資餘額下降。20 日廣度五日變化 ≥ +15pp 稱明顯改善、≤ −5pp 稱持續惡化、−3～+3pp 稱變化有限，其餘為逐步改善或小幅轉弱。顏色區分同步改善（綠）、廣度率先改善（藍）、去槓桿中（橘）、去槓桿且廣度持平（土黃）、廣度持續惡化（紅）及中性狀態。</p><p><b>改善條件成立與轉弱</b>：前 15 個交易日曾有 V12 紅燈，且同時滿足廣度 5 日改善至少 15pp 與最近 10 日內融資 5 日相對指數曾 ≤ −3pp 時，記錄「改善條件成立日」，最多觀察其後 10 個交易日；觀察期內若廣度五日變動 ≤ −10pp，或 V12 分數較訊號日增加至少 15 分且廣度五日變動小於 0，列為「改善條件轉弱」。</p><p><b>融資綠色提示</b>：上市櫃合計融資餘額當日確實下降，且融資日報酬率減去加權指數日報酬率 ≤ −2pp。既有融資紅／黃燈優先顯示，避免同格混淆。</p><p>此為研究候選 V12，融資／廣度改善條件亦屬探索性輔助訊號，未證實獨立交易優勢。歷史警示時間軸使用這套公式重算，不沿用舊模型的燈號日期。</p>`);
  riskCard.classList.add('mm-risk-card');
  riskCard.setAttribute('aria-live', 'polite');
  const composite = document.createElement('section');
  composite.className = 'mm-composite-page';
  composite.setAttribute('aria-label', '綜合指標每日監控');
  composite.innerHTML = `
    <div class="mm-composite-intro"><span class="mb-eyebrow">COMPOSITE SIGNAL · V12 RESEARCH</span><h2>綜合指標</h2>
      <p>四級風險評分｜上方卡片顯示融資／廣度改善觀察；點燈號展開加工指標與分數；日期欄固定。</p></div>
    <div class="mm-composite-filters">
      <label>年份 <select data-composite-year aria-label="綜合指標年份"></select></label>
      <label>月份 <select data-composite-month aria-label="綜合指標月份"></select></label>
      <button type="button" data-composite-refresh>重新整理</button>
    </div>
    <div class="mm-composite-status" data-composite-status role="status">資料載入中…</div>
    <p class="mm-table-hint">左右滑動查看更多欄位；日期固定。紅黃為風險警戒，綠色為積極去槓桿觀察。</p>
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
    <p class="mm-composite-footnote">顏色說明：外資與融資沿用原紅／黃警戒；融資當日確實下降且相對加權指數 ≤ −2pp 時，以綠底及明細綠字標示積極去槓桿（紅黃警戒優先）。市場廣度低於 40% 為黃、低於 20% 為紅（僅視覺提示，不影響 V12）。正常值保持中性色。60MA乖離率超過 +15% 標橘色（過熱）、低於 -15% 標藍綠色（超跌），僅供觀察，不影響燈號；上方卡片的融資／廣度觀察採當日五日融資與廣度資料分色顯示，保留獨立的改善條件成立及轉弱歷史；點日期燈號可查看計算依據；缺值顯示 —，不補零。</p>
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
    const recover=group('融資／廣度觀察');
    const state=twRecoveryByDate.get(f.date),phase=getTwRecoveryPhase(state);
    appendMetric(recover,'今日分類',phase.label,false,phase.key==='sync');
    appendMetric(recover,'融資狀態',phase.financing,false,Number.isFinite(state?.marginCurrent5)&&state.marginCurrent5<0);
    appendMetric(recover,'融資 5 日餘額變化',riskNum(state?.marginCurrent5,2,'%'));
    appendMetric(recover,'融資 5 日相對大盤',riskNum(state?.marginRelativeCurrent5,2,' pp'),false,Number.isFinite(state?.marginRelativeCurrent5)&&state.marginRelativeCurrent5<=-3);
    appendMetric(recover,'廣度狀態',phase.breadth,false,Number.isFinite(state?.breadth5)&&state.breadth5>=15);
    appendMetric(recover,'20 日廣度 5 日變化',riskNum(state?.breadth5,1,' pp'));
    appendMetric(recover,'10 日內曾達相對收縮門檻',!state?'—':state.marginHistory?'是':'否');
    appendMetric(recover,'改善觀察狀態',getTwRecoveryObservationText(state));
    if(state?.eventDate){
      appendMetric(recover,'首次符合日期',state.eventDate);
      if(state.weakDate)appendMetric(recover,'首次轉弱日期',state.weakDate);
      if(Number.isFinite(state.scoreRise))appendMetric(recover,'V12 分數相對訊號日',riskNum(state.scoreRise,1,' 分'),state.scoreRise>=15);
    }
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
    compStatus.textContent=compYear.value+'年'+Number(compMonth.value)+'月｜'+selected.length+'個交易日｜可計算燈號 '+calculated+' 日｜資料截至 '+newest+'｜V12（研究候選）';
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
        recoveryLog.append(h('summary','','融資／廣度改善訊號｜'+inPeriod.length+' 次符合'));
        const recoveryList=h('div','mm-history-recovery-list');
        for(const evt of inPeriod){
          const line=h('div','mm-history-recovery-line');
          line.append(h('b','','條件成立 '+evt.date),h('span','',evt.weakDate?'改善條件轉弱 '+evt.weakDate:'觀察期內未觸發轉弱'),
            h('small','','觀察到期 '+(evt.endDate||'尚未到期')));
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

