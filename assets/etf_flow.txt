/* ETF Flow v2: scoped to existing #etfFlow. Data generated from verified active-equity Sheet. */
(()=>{'use strict';
const root=document.getElementById('etfFlow');if(!root)return;
const state={tab:'etf',region:'TW',code:'00981A',stock:'2330',window:1,range:63,historyRange:63,rank:63,rankRegion:'ALL',filter:'all',logDays:250,selected:{},page:80};
const cache=new Map();let meta,base,stocksIndex,serial=0,quickRanking=[];
let marketPrices=null;
async function getMarketPrices(){
 if(marketPrices!==null)return marketPrices;
 try{const r=await fetch('./data/etf-flow-v2/market-prices.json',{cache:'no-store'});
  if(!r.ok)throw Error('HTTP '+r.status);const j=await r.json();
  marketPrices=j.schema===1&&j.prices&&typeof j.prices==='object'?j.prices:{};
 }catch(e){console.warn('ETF Flow 當日市場均價暫不可用',e);marketPrices={};}
 return marketPrices;
}
function estimatedTwd(amount){
 if(amount===null||!Number.isFinite(amount))return '金額資料不足';
 const abs=Math.abs(amount),sign=amount>0?'+':amount<0?'−':'';
 return abs>=1e8?`${sign}${fmt(abs/1e8,2)} 億元`:abs>=1e4?`${sign}${fmt(abs/1e4,1)} 萬元`:`${sign}${fmt(abs,0)} 元`;
}

// Reuse the website’s market stock abbreviations. Do not infer names by substring.
let marketStockNames=new Map();
const normalizeStockName=v=>String(v??'').normalize('NFKC').trim().replace(/\s+/g,'').toLocaleLowerCase();
async function loadMarketStockNames(){
 try{
  const res=await fetch('./data/stocks.json',{cache:'no-store'});
  if(!res.ok)throw Error('HTTP '+res.status);
  const json=await res.json();
  marketStockNames=new Map((Array.isArray(json.stocks)?json.stocks:[])
    .filter(v=>v&&v.code&&v.name).map(v=>[String(v.code).trim(),String(v.name).trim()]));
 }catch(e){console.warn('ETF Flow 股票簡稱對照無法載入，保留代號及完整名稱查詢',e);}
}
function stockDisplayName(v){return marketStockNames.get(v.code)||v.name;}
function resolveStock(query){
 const q=normalizeStockName(query);if(!q)return {missing:true};
 const found=meta.stocks.filter(v=>[v.code,v.name,stockDisplayName(v)].some(name=>normalizeStockName(name)===q));
 return found.length===1?{stock:found[0]}:found.length>1?{ambiguous:found}: {missing:true};
}
function stockOptions(){
 const options=[];const seen=new Set();
 const add=(value,label)=>{const key=normalizeStockName(value);if(key&&!seen.has(key)){seen.add(key);options.push(`<option value="${esc(value)}" label="${esc(label)}"></option>`);}};
 for(const v of meta.stocks){
  const short=stockDisplayName(v);
  add(v.code,`${short} / ${v.name}`);
  add(short,`${v.code} ${v.name}`);
  if(v.name!==short)add(v.name,`${v.code} ${short}`);
 }
 return options.join('');
}

const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,n=0)=>v===null||v===undefined||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('zh-TW',{maximumFractionDigits:n});
const signed=(v,n=0)=>v==null?'—':`${v>0?'+':''}${fmt(v,n)}`;
const color=v=>v>0?'ef-positive':v<0?'ef-negative':'';
const money=v=>v==null?'—':signed(v/1e8,2)+' 億';
const funds=()=>meta.funds.filter(f=>state.region==='ALL'||f.region===state.region);
const fund=c=>meta.funds.find(f=>f.code===c);
async function get(file){const key=base+file;if(!cache.has(key))cache.set(key,fetch(key).then(r=>{if(!r.ok)throw Error('HTTP '+r.status+'：'+file);return r.json()}).catch(e=>{cache.delete(key);throw e}));return cache.get(key);}
const stockFile=async c=>{if(!stocksIndex)stocksIndex=await get('stock-index.json');if(!stocksIndex[c])return null;return get('stocks/'+stocksIndex[c]+'.json');};
const button=(label,k,v,active)=>`<button type="button" data-${k}="${esc(v)}" aria-pressed="${active}">${label}</button>`;
const ranges=(key,value)=>`<div class="ef-buttons">${[[5,'1週'],[21,'1個月'],[63,'3個月'],[126,'6個月'],[250,'1年'],[750,'3年']].map(([v,t])=>button(t,key,v,value===v)).join('')}</div>`;
const stat=(title,value)=>`<div class="ef-stat"><small>${title}</small><strong>${value}</strong></div>`;
const empty=t=>`<p class="ef-empty">${esc(t)}</p>`;
const card=(title,body,note='',id='')=>`<section class="ef-card"${id?` id="${esc(id)}"`:''}><h3>${title}</h3>${note?`<p class="ef-note">${note}</p>`:''}${body}</section>`;
const table=(heads,rows,extraClass='')=>`<div class="ef-table-scroll ${extraClass}"><table><thead><tr>${heads.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')||`<tr><td colspan="${heads.length}">沒有符合的紀錄</td></tr>`}</tbody></table></div>`;
const tr=c=>`<tr>${c.map(x=>`<td>${x}</td>`).join('')}</tr>`;
const stockLink=(c,n)=>`<button type="button" class="ef-link" data-stock="${esc(c)}">${esc(c)} ${esc(n)}</button>`;
const fundLink=c=>`<button type="button" class="ef-link" data-fund="${esc(c)}">${esc(c)} ${esc(fund(c)?.name||'')}</button>`;
function header(){return `<div class="ef-heading"><div><small>ACTIVE EQUITY ETF</small><h1>ETF Flow</h1><p>主動式股票 ETF 的持股變化、績效與資金流</p></div><button type="button" data-refresh>重新載入</button></div><p class="ef-source">來源最後成功更新：${esc(meta.sourceUpdated||'未提供')}<br>本頁資料產生：${esc(new Date(meta.generated).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false}))} 台灣時間 · ${meta.funds.length} 檔主動式股票 ETF</p><div class="ef-tabs" role="tablist">${[['etf','ETF視角'],['stock','個股視角'],['ranking','績效排名'],['flows','整體淨申贖']].map(([k,t])=>button(t,'tab',k,state.tab===k)).join('')}</div>${state.tab==='stock'?buyTop5Markup():''}${state.tab!=='flows'?`<label class="ef-inline">基金範圍<select id="efRegion">${[['TW','台股主動式'],['GLOBAL','海外股票主動式'],['ALL','全部主動式股票']].map(([k,t])=>`<option value="${k}" ${k===(state.tab==='ranking'?state.rankRegion:state.region)?'selected':''}>${t}</option>`).join('')}</select></label>`:''}`;}
// Aggregate only the latest global ETF holding-date snapshot. Funds that have no
// snapshot on that date are omitted; never carry forward yesterday's changes.
let topBuySnapshot=null;
let buyTopOpen=true;
async function loadBuyTop5(){
 if(topBuySnapshot)return topBuySnapshot;
 const latest=meta.funds.map(f=>f.latest).filter(Boolean).sort().at(-1);
 if(!latest)return {date:null,covered:0,total:meta.funds.length,leaders:[]};
 const eligible=meta.funds.filter(f=>f.latest===latest);
 const prices=await getMarketPrices();
 // Use the same official daily average prices as the ETF change amounts.
 const responses=await Promise.allSettled(eligible.map(f=>get('etfs/'+f.code+'.json')));
 const succeeded=responses.filter(r=>r.status==='fulfilled').map(r=>r.value);
 const buys=new Map();let covered=0;
 for(const etf of succeeded){
  if(!etf.dates?.includes(latest)||etf.dates[0]===latest)continue;
  covered++;
  for(const event of etf.events||[]){
   if(event.date!==latest||!(event.delta>0))continue;
   const code=String(event.code||'').trim();if(!code)continue;
   const item=buys.get(code)||{code,name:event.name||'',shares:0,etfs:new Set()};
   item.shares+=event.delta;item.etfs.add(etf.fund.code);buys.set(code,item);
  }
 }
 const ranked=[...buys.values()].map(v=>{
  const price=prices[latest]?.[v.code];
  const amount=/^\d{4}$/.test(v.code)&&typeof price==='number'&&Number.isFinite(price)&&price>0?v.shares*price:null;
  return {...v,amount};
 });
 const missing=ranked.filter(v=>v.amount===null).length;
 const leaders=ranked.filter(v=>v.amount!==null).sort((a,b)=>b.amount-a.amount||a.code.localeCompare(b.code)).slice(0,5);
 topBuySnapshot={date:latest,covered,total:meta.funds.length,eligible:eligible.length,failed:eligible.length-covered,missing,leaders};
 return topBuySnapshot;
}
function buyTop5Markup(){
 const d=topBuySnapshot;
 if(!d)return '';
 const crown='<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M2.5 7.5 7.7 12l4.3-7 4.3 7 5.2-4.5-1.7 10.2H4.2L2.5 7.5ZM4.7 20h14.6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 const items=d.leaders.map((v,i)=>{
  const name=marketStockNames.get(v.code)||meta.stocks.find(s=>s.code===v.code)?.name||v.name;
  const mark=i<3?crown+`<b>${i+1}</b>`:`<b>${i+1}</b>`;
  return `<button type="button" class="ef-buy-top-item" data-top-buy-stock="${esc(v.code)}" title="查看 ${esc(v.code)} ${esc(name)} 的 ETF 每日 Log"><span class="ef-buy-top-rank ef-buy-top-rank-${i+1}" aria-label="第${i+1}名">${mark}</span><span class="ef-buy-top-stock"><strong>${esc(v.code)} ${esc(name)}</strong><small>${v.etfs.size} 檔 ETF 增持</small></span><span class="ef-buy-top-lots ef-positive">${estimatedTwd(v.amount)}<small>+${fmt(v.shares/1000,3)} 張</small></span></button>`;
 }).join('');
 const status=d.failed?`<p class="ef-warning">有 ${d.failed} 檔當日 ETF 資料讀取失敗，榜單不完整，請重新載入。</p>`:'';
 return `<section class="ef-buy-top" aria-label="當日主動式 ETF 增持金額前五名"><button type="button" class="ef-buy-top-head ef-buy-top-toggle" data-toggle-buy-top aria-expanded="${buyTopOpen}" aria-controls="efBuyTopBody"><strong>🏆 當日 ETF 增持金額前五名</strong><span>${esc(d.date)}</span><span class="ef-buy-top-action">${buyTopOpen?'收合 ▴':'展開 ▾'}</span></button><div id="efBuyTopBody" ${buyTopOpen?'':'hidden'}><p class="ef-buy-top-desc">彙整全部 ${d.total} 檔主動式股票 ETF；當日有持股快照 ${d.eligible} 檔，未更新者排除。依正向增加股數 × 當日成交均價加總，由金額高至低排序。${d.missing?`另有 ${d.missing} 檔股票缺少當日均價，未列入金額排行。`:''}</p>${status}<div class="ef-buy-top-list">${items||'<p class="ef-note">當日沒有可排名的增持紀錄。</p>'}</div><p class="ef-buy-top-foot">金額為當日均價估算，非實際成交金額。增持股數為持股快照差額，可能含申贖與公司行動影響，並非基金實際買進成交張數。點股票可查看每日 Log。</p></div></section>`;
}
function quickETFChoices(){
 // Three permanent quick picks plus the highest 1-month performers among TW equity ETFs.
 // The ranking uses the same 21-trading-day return and latest common market date as rankingView.
 const fixed=['00981A','00991A','00410A'].filter(code=>!!fund(code));
 const selected=new Set(fixed);
 const eligible=quickRanking.filter(v=>fund(v.code)?.region==='TW'&&Number.isFinite(v.returns?.[21]));
 const latestDate=eligible.map(v=>v.date).filter(Boolean).sort().at(-1);
 const ranked=eligible.filter(v=>v.date===latestDate)
  .sort((a,b)=>b.returns[21]-a.returns[21]||a.code.localeCompare(b.code));
 for(const row of ranked){
  if(selected.has(row.code))continue;
  selected.add(row.code);
  if(selected.size===6)break;
 }
 return [...selected];
}
function searchETF(){return `<form id="efFundSearch" class="ef-search"><label>ETF 代號／名稱<span class="ef-input-wrap"><input id="efFundInput" list="efFunds" value="${esc(state.code)}" placeholder="00981A／統一台股增長" autocomplete="off"><button type="button" class="ef-clear-input" data-clear-etf-input aria-label="清除 ETF 搜尋文字" title="清除" ${state.code?'':'hidden'}>×</button></span></label><datalist id="efFunds">${funds().map(f=>`<option value="${esc(f.code)}">${esc(f.name)}</option>`).join('')}</datalist><button>查詢</button></form><div class="ef-buttons ef-quick-funds" aria-label="固定 ETF 與近一個月績效前三推薦">${quickETFChoices().map(code=>button(code,'fund',code,code===state.code)).join('')}</div>`;}

function chart(id,title,data,valueLabel,series=false){
 const usable=data.filter(d=>d.value!=null);if(!usable.length)return empty('此範圍沒有可繪圖的資料');
 const chosen=state.selected[id]||data.at(-1)?.date;const sel=data.find(d=>d.date===chosen)||data.at(-1);
 if(usable.length===1)return `<p class="ef-note">${esc(usable[0].date)}：${valueLabel(usable[0].value)}，僅一筆資料，不繪製趨勢。</p>`;
 const W=640,H=220,L=68,R=14,T=16,B=34;const vals=usable.map(d=>d.value),low=Math.min(0,...vals),high=Math.max(0,...vals);const span=high-low||1;const x=i=>L+(i+.5)*(W-L-R)/data.length,y=v=>T+(high-v)/span*(H-T-B);const bw=Math.max(1,Math.min(15,(W-L-R)/data.length*.76));
 let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}" data-chart="${id}"><title>${esc(title)}</title>`;
 for(let i=0;i<3;i++){const v=low+span*i/2,yy=y(v);svg+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="currentColor" opacity=".12"/><text x="${L-7}" y="${yy+4}" text-anchor="end">${fmt(v,1)}</text>`;}
 data.forEach((d,i)=>{if(d.value==null)return;svg+=`<rect x="${x(i)-bw/2}" y="${Math.min(y(d.value),y(0))}" width="${bw}" height="${Math.max(1,Math.abs(y(d.value)-y(0)))}" fill="${d.value<0?'#19846d':'#cc4757'}" opacity="${d.date===sel.date?1:.68}"><title>${esc(d.date)} ${esc(valueLabel(d.value))}</title></rect>`;});
 let priceNote='';if(series){const prices=data.map((d,i)=>({i,p:d.close})).filter(d=>d.p!=null);if(prices.length>1){const lo=Math.min(...prices.map(d=>d.p)),hi=Math.max(...prices.map(d=>d.p));let points=[];for(const d of prices){const yy=T+(hi-d.p)/(hi-lo||1)*(H-T-B);points.push(`${x(d.i)},${yy}`);}svg+=`<polyline points="${points.join(' ')}" fill="none" stroke="#327bc0" stroke-width="2"/>`;priceNote=`<p class="ef-note">藍線為還原股價（獨立刻度 ${fmt(lo,2)}～${fmt(hi,2)} 元）。</p>`;}else priceNote='<p class="ef-note">個股還原股價尚未提供，保留持股增減圖，不補畫股價線。</p>';}
 [...new Set([0,Math.floor((data.length-1)/2),data.length-1])].forEach(i=>{svg+=`<text x="${x(i)}" y="${H-8}" text-anchor="${i===0?'start':i===data.length-1?'end':'middle'}">${esc(data[i].date.slice(5))}</text>`;});
 svg+='</svg>';
 return `<div class="ef-chart" data-chart-wrap="${id}"><div class="ef-chart-selection"><label>選取日期<select data-chart-select="${id}">${data.slice().reverse().map(d=>`<option value="${d.date}" ${sel.date===d.date?'selected':''}>${d.date}</option>`).join('')}</select></label><strong class="${color(sel.value)}">${valueLabel(sel.value)}</strong>${sel.close!=null?`<span>還原收盤 ${fmt(sel.close,2)} 元</span>`:''}</div>${svg}<p class="ef-note">點選圖表或選擇日期查看數值；紅色增加、綠色減少。${data.length} 個資料日。</p>${priceNote}</div>`;
}
function trackedChart(id,title,rows,label,series){return `<div data-ef-chart-data="${esc(JSON.stringify(rows))}">${chart(id,title,rows,label,series)}</div>`;}
async function etfView(){
 quickRanking=await get('ranking.json');
 const choices=funds();if(!choices.some(f=>f.code===state.code))state.code=choices.find(f=>f.latest)?.code||choices[0]?.code;if(!state.code)return empty('沒有符合的主動 ETF');
 const e=await get('etfs/'+state.code+'.json');const f=e.fund;
 if(!e.dates.length)return searchETF()+card(esc(f.name),empty('來源尚未提供持股資料，保留基金清單但不補零。'));
 const selectedDays=e.dates.slice(-state.window);const changes=new Map();for(const v of e.events){if(!selectedDays.includes(v.date))continue;const row=changes.get(v.code)||{...v,delta:0};row.delta+=v.delta;changes.set(v.code,row);}
 const prices=await getMarketPrices();
 // Report amounts only if every *changed* day has a valid same-day official average.
 // ETF shares are snapshot differences, not broker executions.
 const sums=new Map();
 for(const event of e.events){
  if(!selectedDays.includes(event.date)||!event.delta)continue;
  const item=sums.get(event.code)||{missing:false,amount:0};
  const price=prices[event.date]?.[event.code];
  if(f.region!=='TW'||!/^\d{4}$/.test(event.code)||typeof price!=='number'||!Number.isFinite(price)||price<=0){item.missing=true;}
  else item.amount+=event.delta*price;
  sums.set(event.code,item);
 }
 const changeAmount=code=>{const item=sums.get(code);return item&&!item.missing?item.amount:null;};
 // Rank buy/sell separately by estimated NT$ magnitude. Missing prices follow valid amounts,
 // then compare share changes, without treating unknown amount as zero.
 const changed=[...changes.values()].filter(v=>v.delta!==0).sort((a,b)=>{
  const am=changeAmount(a.code),bm=changeAmount(b.code);
  if((am===null)!==(bm===null))return am===null?1:-1;
  if(am!==null&&bm!==null&&Math.abs(bm)!==Math.abs(am))return Math.abs(bm)-Math.abs(am);
  return Math.abs(b.delta)-Math.abs(a.delta)||a.code.localeCompare(b.code);
 });
 const list=positive=>changed.filter(v=>positive?v.delta>0:v.delta<0).map(v=>{
    const amount=changeAmount(v.code);
   return `<div class="ef-change">${stockLink(v.code,v.name)}<b class="${color(v.delta)}">${estimatedTwd(amount)} <small>（${signed(v.delta/1000,3)} 張）</small></b></div>`;
 }).join('')||empty('沒有持股變動');
 if(!e.holdings.some(v=>v[0]===state.stock)&&!e.events.some(v=>v.code===state.stock))state.stock=e.holdings[0]?.[0]||'';
 const nav=e.nav.slice(-state.range).map(v=>({date:v.date,value:v.deltaK}));
 // One-click choice of both current holdings and previously exited positions.
 const heldSet=new Set(e.holdings.map(v=>v[0]));
 const nameByCode=new Map(e.holdings.map(v=>[v[0],v[1]]));
 const historyCodes=[...new Set([...heldSet,...e.events.map(v=>v.code)])]
  .filter(c=>meta.stocks.some(v=>v.code===c))
  .sort((a,b)=>Number(heldSet.has(b))-Number(heldSet.has(a))||a.localeCompare(b));
 const historyPicker=`<form id="efHistorySearch" class="ef-search"><label>搜尋股票<span class="ef-input-wrap"><input id="efHistoryInput" list="efHistoryOptions" value="${esc(state.stock+' '+(marketStockNames.get(state.stock)||nameByCode.get(state.stock)||meta.stocks.find(v=>v.code===state.stock)?.name||''))}" placeholder="輸入代號或簡稱，例如 2330、台積電" autocomplete="off" aria-label="搜尋這檔 ETF 曾持有的股票"><button type="button" class="ef-clear-input" data-clear-history-input aria-label="清除股票搜尋文字" title="清除">×</button></span></label><datalist id="efHistoryOptions">${historyCodes.map(c=>{
  const st=meta.stocks.find(v=>v.code===c);
  const label=marketStockNames.get(c)||nameByCode.get(c)||st?.name||c;
  return `<option value="${esc(c+' '+label)}" label="${esc(heldSet.has(c)?'目前持有':'歷史持有')}"></option>`;
 }).join('')}</datalist><button type="submit">查詢</button></form><p class="ef-note">搜尋這檔 ETF 目前或曾經持有的股票，可輸入股票代號、券商常用簡稱或部分名稱。</p>`;
 state.historyCodes=historyCodes;
 const selected=e.dates.slice(-state.historyRange);const daily=selected.map(d=>{const ev=e.events.find(v=>v.code===state.stock&&v.date===d);return {date:d,value:d===e.dates[0]?null:ev?.delta/1000||0,close:null};});
 const sp=await stockFile(state.stock);for(const d of daily)d.close=sp?.prices?.[d.date]?.close??null;
 const comparable=daily.filter(d=>d.value!==null);
 const intervalLots=comparable.reduce((total,d)=>total+d.value,0);
 const selectedDate=state.selected['stock-flow'];
 const chosenDaily=daily.find(d=>d.date===selectedDate)||daily.at(-1);
 const intervalSummary=`<div class="ef-history-summary"><div class="ef-history-metric"><small>區間累計持股增減 · ${selected.length} 個資料日</small><strong class="${color(intervalLots)}">${comparable.length?signed(Math.round(intervalLots*1000)/1000,3)+' 張':'—'}</strong></div><div class="ef-history-metric"><small>${esc(chosenDaily?.date||'—')} 當日增減</small><strong class="${color(chosenDaily?.value)}">${chosenDaily?.value==null?'首次快照／不可比較':signed(chosenDaily.value,3)+' 張'}</strong></div></div>`;
 const holdings=e.holdings.map(([code,name,shares,w])=>tr([stockLink(code,name),fmt(shares/1000,3),w==null?'—':fmt(w,2)+'%']));
 return searchETF()+`<h2>${esc(f.code)} ${esc(f.name)}</h2><div class="ef-stats">${stat('最新持股日',esc(f.latest))}${stat('持股檔數',fmt(f.holdingCount))}${stat('持股最早日期',esc(f.earliest))}</div>`+card('持股增減',`<div class="ef-buttons">${[[1,'當日'],[3,'近3日'],[5,'近5日'],[10,'近10日']].map(([v,t])=>button(t,'window',v,state.window===v)).join('')}</div><p class="ef-note">${esc(selectedDays[0])}～${esc(selectedDays.at(-1))} · ${selectedDays.length} 個 ETF 資料日；首個快照不當作買入。</p><div class="ef-columns"><div><h4>增加持股</h4>${list(true)}</div><div><h4>減少持股</h4>${list(false)}</div></div>`,'增減清單按推估金額絕對值由大到小排列，缺價項目排在後面。推估增減金額＝每日持股增減股數 × 該日官方市場成交均價，再按區間加總；缺任一日均價就顯示資料不足。持股差額包含申贖與公司行動影響，非 ETF 實際成交金額。')+card('單檔 ETF 每日淨申贖',ranges('range',state.range)+trackedChart('nav','單檔每日淨申贖',nav,v=>v==null?'未提供':signed(v,3)+' 千受益單位'),'直接使用來源的受益權單位日變化，不從個股持股差額推算。')+card(`${esc(state.code)} × ${esc(state.stock)} ${esc(marketStockNames.get(state.stock)||meta.stocks.find(v=>v.code===state.stock)?.name||'')}`,historyPicker+ranges('history-range',state.historyRange)+intervalSummary+trackedChart('stock-flow','ETF對個股每日持股增減',daily,v=>v==null?'首次快照／不可比較':signed(v,3)+' 張',true),'','efStockHistoryAnchor')+card('最新完整持股',table(['股票','持股（張）','權重'],holdings),'點選股票即可切換上方歷史進出圖。');
}
async function stockView(){
 await loadBuyTop5();
 const s=await stockFile(state.stock);const form=`<form id="efStockSearch" class="ef-search"><label>股票代號／名稱<span class="ef-input-wrap"><input id="efStockInput" list="efStocks" value="${esc(state.stock)}" autocomplete="off"><button type="button" class="ef-clear-input" data-clear-stock-input aria-label="清除股票搜尋文字" title="清除" ${state.stock?'':'hidden'}>×</button></span></label><datalist id="efStocks">${stockOptions()}</datalist><button>查詢</button></form>`;
 if(!s)return form+empty('尚無這檔股票的持股變動紀錄');
 const allowed=new Set(funds().map(f=>f.code));let rows=s.events.filter(v=>allowed.has(v.etf));const calendars=new Map(Object.entries(s.calendars||{}).map(([c,days])=>[c,new Set(days.slice(-state.logDays))]));
 rows=rows.filter(v=>calendars.get(v.etf)?.has(v.date)&&(state.filter==='all'||(state.filter==='buy'?v.delta>0:v.delta<0)))
  .sort((a,b)=>b.date.localeCompare(a.date)||Math.abs(b.delta)-Math.abs(a.delta)||a.etf.localeCompare(b.etf));
 const shown=rows.slice(0,state.page);
 const body=shown.map(v=>tr([esc(v.date),fundLink(v.etf),`<span class="${color(v.delta)}">${signed(v.delta/1000,3)}</span>`,signed(v.flow5==null?null:v.flow5/1000,3),signed(v.flow10==null?null:v.flow10/1000,3),signed(v.flow30==null?null:v.flow30/1000,3),v.shares==null?'—':fmt(v.shares/1000,3),v.weight==null?'—':fmt(v.weight,2)+'%',v.weightDelta==null?'—':signed(v.weightDelta,2)+'%',v.weight5==null?'—':signed(v.weight5,2)+'%',v.cost==null?'資料不足':fmt(v.cost,2)]));
 return form+card(`${esc(state.stock)} ${esc(meta.stocks.find(x=>x.code===state.stock)?.name||'')} · 每日 Log`,`<div class="ef-buttons">${[['all','全部'],['buy','增加'],['sell','減少']].map(([k,t])=>button(t,'filter',k,state.filter===k)).join('')}</div><p class="ef-note">各 ETF 最近 ${state.logDays} 個資料日，共 ${rows.length} 筆。不同基金分別按自己的資料日期回算。</p>`+table(['日期','ETF','當日增減（張）','近5日（張）','近10日（張）','近30日（張）','剩餘持股（張）','權重','當日權重變化','近5日權重變化','推估成本（元）'],body)+(shown.length<rows.length?`<button type="button" data-more>再顯示80筆</button>`:''),'權重變化以 % 符號顯示（數值為權重比例之差）。成本採全歷史有號股數變化×市場均價／剩餘股數；缺開倉成本或市場均價時不計算，不能當作投信真實成本。');
}
async function rankingView(){
 const data=await get('ranking.json');
 // Ranking defaults to all active equity ETFs, independently of the other tabs' fund filter.
 const allowed=new Set(meta.funds.filter(f=>state.rankRegion==='ALL'||f.region===state.rankRegion).map(f=>f.code));
 const all=data.filter(v=>allowed.has(v.code)).sort((a,b)=>(b.returns[state.rank]??-Infinity)-(a.returns[state.rank]??-Infinity));
 const dates=all.filter(v=>v.returns[state.rank]!=null).map(v=>v.date).filter(Boolean);
 const latest=dates.sort().at(-1);let rank=0;
 const rows=all.map(v=>{
  const ret=v.returns[state.rank],comparable=ret!=null&&v.date===latest;
  const f=fund(v.code),name=f?.name||'';
  const note=ret==null?'歷史不足':!comparable?'行情日期落後，暫不列排名':'';
  const item=`<button type="button" class="ef-link ef-ranking-fund" data-fund="${esc(v.code)}"><strong>${esc(v.code)}</strong><span>${esc(name)}</span></button>${note?`<small class="ef-ranking-status">${note}</small>`:''}`;
  const value=ret==null?'<span class="ef-ranking-na">—</span>':`<span class="ef-ranking-return ${color(ret)}">${signed(ret,2)}%</span>`;
  return tr([comparable?++rank:'—',item,value]);
 });
 return card('主動式 ETF 績效排名',ranges('rank',state.rank)+table(['排名','ETF','區間報酬'],rows,'ef-ranking-table'),'以還原收盤價計算；5／21／63／126／250／750 個交易日。歷史不足不縮短期間硬算；行情日期不同者不混列名次。');
}
async function flowsView(){
 const all=await get('flows.json');const data=all.slice(-state.range);const complete=data.every(v=>v.amount!=null);const sum=complete?data.reduce((s,v)=>s+v.amount,0):null;
 let selected=data.find(v=>v.date===state.selected.flows)||data.at(-1);if(!selected)return empty('尚無 NAV 與受益權單位資料');
 const sortedFunds=[...selected.funds].sort((a,b)=>{
  if((a.amount==null)!==(b.amount==null))return a.amount==null?1:-1;
  return Math.abs(b.amount??0)-Math.abs(a.amount??0)||Math.abs(b.deltaK??0)-Math.abs(a.deltaK??0);
 });
 const rows=sortedFunds.map(v=>tr([fundLink(v.code),signed(v.deltaK,3),fmt(v.nav,4),`<span class="${color(v.amount)}">${money(v.amount)}</span>`]));
 return card('台股主動式 ETF 每日推估淨申贖',ranges('range',state.range)+`<div class="ef-stats">${stat('選取日期',selected.date)}${stat('當日完整合計',money(selected.amount))}${stat('區間完整累計',money(sum))}${stat('資料覆蓋',selected.covered+'／'+selected.expected+'檔')}</div>`+trackedChart('flows','台股主動ETF推估資金流',data.map(v=>({date:v.date,value:v.amount==null?null:v.amount/1e8})),v=>v==null?'資料未齊':signed(v,2)+' 億元')+(!complete?'<p class="ef-warning">區間有缺漏，不顯示完整累計。缺資料不是零；不將部分基金加總冒充完整資金流。</p>':'')+table(['ETF','單位變化（千）','當日NAV','推估金額'],rows),'只含當日已上市的台股主動式股票 ETF。推估金額＝受益權單位日變化（千）×1,000×當日NAV，並非實際現金申贖成交額。');
}
// Keep the existing DOM mounted while data loads. Replacing the whole section with a
// loading placeholder used to collapse its height and snap mobile scroll to page top.
function positionHistory(){
 const target=root.querySelector('#efStockHistoryAnchor');if(!target)return;
 const siteHeader=document.querySelector('body > header');
 const sticky=siteHeader&&/^(fixed|sticky)$/.test(getComputedStyle(siteHeader).position);
 const offset=sticky?Math.max(0,siteHeader.getBoundingClientRect().bottom)+12:12;
 window.scrollTo({top:Math.max(0,window.scrollY+target.getBoundingClientRect().top-offset),behavior:'instant'});
}
async function updateHistory(jump=false){
 if(state.tab!=='etf')return;
 const seq=++serial;
 const previous=root.querySelector('#efStockHistoryAnchor');
 if(!previous){await render(jump?'history':'');return;}
 // Build only the history card. All content above and below remains in the DOM.
 try{
  const html=await etfView();if(seq!==serial)return;
  const scratch=document.createElement('div');scratch.innerHTML=html;
  const next=scratch.querySelector('#efStockHistoryAnchor');if(!next)return;
  const oldY=previous.getBoundingClientRect().top;
  previous.replaceWith(next);
  if(jump)positionHistory();
  else{
   // Preserve the anchor's viewport position if the updated summary changes height.
   const delta=next.getBoundingClientRect().top-oldY;
   if(Math.abs(delta)>1)window.scrollBy({top:delta,behavior:'instant'});
  }
 }catch(e){console.error('ETF history chart update failed',e);}
}
async function render(scrollTarget=''){
 const seq=++serial;
 try{
  const html=await ({etf:etfView,stock:stockView,ranking:rankingView,flows:flowsView}[state.tab])();
  if(seq!==serial)return;
  root.innerHTML=header()+'<div id="efContent" aria-live="polite">'+html+'</div>';
  if(scrollTarget==='history')positionHistory();
 }catch(e){if(seq===serial)root.innerHTML=header()+'<div id="efContent" aria-live="polite">'+empty('載入失敗：'+e.message)+'</div>';}
}
root.addEventListener('click',e=>{
 const b=e.target.closest('button');
 if(b?.hasAttribute('data-clear-etf-input')||b?.hasAttribute('data-clear-stock-input')||b?.hasAttribute('data-clear-history-input')){
  const input=root.querySelector(b.hasAttribute('data-clear-history-input')?'#efHistoryInput':b.hasAttribute('data-clear-etf-input')?'#efFundInput':'#efStockInput');
  if(input){input.value='';b.hidden=true;input.focus();}return;
 }
 if(b){
  const d=b.dataset;
  if('toggleBuyTop'in d){
   buyTopOpen=!buyTopOpen;
   const body=root.querySelector('#efBuyTopBody');if(body)body.hidden=!buyTopOpen;
   b.setAttribute('aria-expanded',String(buyTopOpen));
   b.querySelector('.ef-buy-top-action').textContent=buyTopOpen?'收合 ▴':'展開 ▾';return;
  }
  if(d.topBuyStock&&state.tab==='stock'){state.stock=d.topBuyStock;state.region='ALL';state.page=80;render();return;}
  if(d.stock&&state.tab==='etf'){
   state.stock=d.stock;state.selected['stock-flow']=null;
   // Click from holdings list: one direct move to the selected chart, no top-of-page reset.
   updateHistory(true);return;
  }
  if(d.historyRange&&state.tab==='etf'&&b.closest('#efStockHistoryAnchor')){
   state.historyRange=+d.historyRange;
   // Changing range only updates the chart, not the surrounding page or scroll.
   updateHistory(false);return;
  }
  let dirty=true;
  if(d.tab){state.tab=d.tab;state.page=80;}
  else if(d.fund){state.code=d.fund;state.region=fund(d.fund)?.region||'TW';state.tab='etf';}
  else if(d.window)state.window=+d.window;
  else if(d.range)state.range=+d.range;
  else if(d.rank)state.rank=+d.rank;
  else if(d.filter){state.filter=d.filter;state.page=80;}
  else if('more'in d)state.page+=80;
  else if('refresh'in d){location.reload();return;}
  else dirty=false;
  if(dirty){render();return;}
 }
 const svg=e.target.closest('svg[data-chart]');
 if(svg){
  const rows=JSON.parse(svg.closest('[data-ef-chart-data]').dataset.efChartData||'[]');if(!rows.length)return;
  const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;
  const p=pt.matrixTransform(svg.getScreenCTM().inverse());
  const i=Math.max(0,Math.min(rows.length-1,Math.floor((p.x-68)/(640-68-14)*rows.length)));
  state.selected[svg.dataset.chart]=rows[i].date;
  if(svg.dataset.chart==='stock-flow')updateHistory(false);
  else render();
 }
});
root.addEventListener('input',e=>{if(e.target.id==='efFundInput'||e.target.id==='efStockInput'||e.target.id==='efHistoryInput'){const clear=e.target.closest('.ef-input-wrap')?.querySelector('.ef-clear-input');if(clear)clear.hidden=!e.target.value;}});
root.addEventListener('change',e=>{if(e.target.id==='efRegion'){if(state.tab==='ranking')state.rankRegion=e.target.value;else state.region=e.target.value;state.page=80;render();}else if(e.target.dataset.chartSelect){state.selected[e.target.dataset.chartSelect]=e.target.value;if(e.target.dataset.chartSelect==='stock-flow')updateHistory(false);else render();}});
root.addEventListener('submit',e=>{if(e.target.id==='efHistorySearch'){
 e.preventDefault();const q=root.querySelector('#efHistoryInput')?.value.trim()||'';
 const codes=state.historyCodes||[],norm=normalizeStockName(q);
 if(!norm){root.querySelector('#efHistoryInput')?.focus();return;}
 const candidates=codes.map(code=>{const v=meta.stocks.find(s=>s.code===code);return {code,names:[code,marketStockNames.get(code),v?.name].filter(Boolean)};});
 const exact=candidates.filter(v=>v.names.some(n=>normalizeStockName(n)===norm)||normalizeStockName(v.code+' '+(marketStockNames.get(v.code)||v.names[1]||''))===norm);
 const pref=candidates.filter(v=>v.names.some(n=>normalizeStockName(n).startsWith(norm)));
 const partial=candidates.filter(v=>v.names.some(n=>normalizeStockName(n).includes(norm)));
 const matched=(exact.length?exact:pref.length?pref:partial);
 if(matched.length===1){state.stock=matched[0].code;state.selected['stock-flow']=null;updateHistory(false);}
 else if(matched.length>1){alert('找到多檔符合的股票，請輸入代號或從搜尋建議中選擇：'+matched.slice(0,8).map(v=>v.code+' '+(marketStockNames.get(v.code)||v.names[1]||'')).join('、'));}
 else{alert('這檔 ETF 的持股歷史找不到這個股票，請輸入股票代號或簡稱。');}
 return;
 }if(e.target.id==='efFundSearch'){e.preventDefault();const q=root.querySelector('#efFundInput').value.trim().toLowerCase();const f=funds().find(f=>f.code.toLowerCase()===q||f.name.toLowerCase().includes(q));if(f){state.code=f.code;render();}else alert('找不到符合範圍的主動式 ETF');}if(e.target.id==='efStockSearch'){e.preventDefault();const q=root.querySelector('#efStockInput').value.trim().toLowerCase();const match=resolveStock(q);if(match.stock){state.stock=match.stock.code;state.page=80;render();}else if(match.ambiguous){alert('同名股票不只一檔，請改用股票代號查詢：'+match.ambiguous.map(v=>v.code+' '+stockDisplayName(v)).join('、'));}else alert('找不到符合的股票，請使用股票代號、券商常用簡稱或完整公司名稱');}});
// Lazy load only when the existing navigation opens this section.
let started=false;async function boot(){if(started||!root.classList.contains('active'))return;started=true;root.innerHTML='<p class="ef-note">載入主動式 ETF 資料…</p>';try{const r=await fetch('./data/etf-flow-v2/manifest.json',{cache:'no-store'});if(!r.ok)throw Error('manifest HTTP '+r.status);const m=await r.json();if(m.schema!==2||!/^versions\/[a-f0-9]{12}\/$/.test(m.path))throw Error('不支援的資料版本');base='./data/etf-flow-v2/'+m.path;meta=await get('meta.json');await loadMarketStockNames();render();}catch(e){root.innerHTML=empty('ETF資料尚未就緒：'+e.message+'。請確認已上傳 data/etf-flow-v2 資料夾。');started=false;}}
new MutationObserver(boot).observe(root,{attributes:true,attributeFilter:['class']});boot();
})();
