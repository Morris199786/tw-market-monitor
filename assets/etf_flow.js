/* ETF Flow v2: scoped to existing #etfFlow. Data generated from verified active-equity Sheet. */
(()=>{'use strict';
const root=document.getElementById('etfFlow');if(!root)return;
const state={tab:'etf',region:'TW',code:'00981A',stock:'2330',window:1,range:63,rank:63,filter:'all',logDays:250,selected:{},page:80};
const cache=new Map();let meta,base,stocksIndex,serial=0;
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
const card=(title,body,note='')=>`<section class="ef-card"><h3>${title}</h3>${note?`<p class="ef-note">${note}</p>`:''}${body}</section>`;
const table=(heads,rows,extraClass='')=>`<div class="ef-table-scroll ${extraClass}"><table><thead><tr>${heads.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')||`<tr><td colspan="${heads.length}">沒有符合的紀錄</td></tr>`}</tbody></table></div>`;
const tr=c=>`<tr>${c.map(x=>`<td>${x}</td>`).join('')}</tr>`;
const stockLink=(c,n)=>`<button type="button" class="ef-link" data-stock="${esc(c)}">${esc(c)} ${esc(n)}</button>`;
const fundLink=c=>`<button type="button" class="ef-link" data-fund="${esc(c)}">${esc(c)} ${esc(fund(c)?.name||'')}</button>`;
function header(){return `<div class="ef-heading"><div><small>ACTIVE EQUITY ETF</small><h1>ETF Flow</h1><p>主動式股票 ETF 的持股變化、績效與資金流</p></div><button type="button" data-refresh>重新載入</button></div><p class="ef-source">來源最後成功更新：${esc(meta.sourceUpdated||'未提供')}<br>本頁資料產生：${esc(new Date(meta.generated).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false}))} 台灣時間 · ${meta.funds.length} 檔主動式股票 ETF</p><div class="ef-tabs" role="tablist">${[['etf','ETF視角'],['stock','個股視角'],['ranking','績效排名'],['flows','整體淨申贖']].map(([k,t])=>button(t,'tab',k,state.tab===k)).join('')}</div>${state.tab!=='flows'?`<label class="ef-inline">基金範圍<select id="efRegion">${[['TW','台股主動式'],['GLOBAL','海外股票主動式'],['ALL','全部主動式股票']].map(([k,t])=>`<option value="${k}" ${k===state.region?'selected':''}>${t}</option>`).join('')}</select></label>`:''}`;}
function searchETF(){return `<form id="efFundSearch" class="ef-search"><label>ETF 代號／名稱<span class="ef-input-wrap"><input id="efFundInput" list="efFunds" value="${esc(state.code)}" placeholder="00981A／統一台股增長" autocomplete="off"><button type="button" class="ef-clear-input" data-clear-etf-input aria-label="清除 ETF 搜尋文字" title="清除" ${state.code?'':'hidden'}>×</button></span></label><datalist id="efFunds">${funds().map(f=>`<option value="${esc(f.code)}">${esc(f.name)}</option>`).join('')}</datalist><button>查詢</button></form><div class="ef-buttons">${funds().filter(f=>['00981A','00991A','00410A','00403A'].includes(f.code)).map(f=>button(esc(f.code),'fund',f.code,f.code===state.code)).join('')}</div>`;}
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
 const choices=funds();if(!choices.some(f=>f.code===state.code))state.code=choices.find(f=>f.latest)?.code||choices[0]?.code;if(!state.code)return empty('沒有符合的主動 ETF');
 const e=await get('etfs/'+state.code+'.json');const f=e.fund;
 if(!e.dates.length)return searchETF()+card(esc(f.name),empty('來源尚未提供持股資料，保留基金清單但不補零。'));
 const selectedDays=e.dates.slice(-state.window);const changes=new Map();for(const v of e.events){if(!selectedDays.includes(v.date))continue;const row=changes.get(v.code)||{...v,delta:0};row.delta+=v.delta;changes.set(v.code,row);}
 const changed=[...changes.values()].filter(v=>v.delta!==0).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));const list=positive=>changed.filter(v=>positive?v.delta>0:v.delta<0).map(v=>`<div class="ef-change">${stockLink(v.code,v.name)}<b class="${color(v.delta)}">${signed(v.delta/1000,3)} 張</b></div>`).join('')||empty('沒有持股變動');
 if(!e.holdings.some(v=>v[0]===state.stock)&&!e.events.some(v=>v.code===state.stock))state.stock=e.holdings[0]?.[0]||'';
 const nav=e.nav.slice(-state.range).map(v=>({date:v.date,value:v.deltaK}));
 const selected=e.dates.slice(-state.range);const daily=selected.map(d=>{const ev=e.events.find(v=>v.code===state.stock&&v.date===d);return {date:d,value:d===e.dates[0]?null:ev?.delta/1000||0,close:null};});
 const sp=await stockFile(state.stock);for(const d of daily)d.close=sp?.prices?.[d.date]?.close??null;
 const holdings=e.holdings.map(([code,name,shares,w])=>tr([stockLink(code,name),fmt(shares),w==null?'—':fmt(w,2)+'%']));
 return searchETF()+`<h2>${esc(f.code)} ${esc(f.name)}</h2><div class="ef-stats">${stat('最新持股日',esc(f.latest))}${stat('持股檔數',fmt(f.holdingCount))}${stat('持股最早日期',esc(f.earliest))}</div>`+card('持股增減',`<div class="ef-buttons">${[[1,'當日'],[3,'近3日'],[5,'近5日'],[10,'近10日']].map(([v,t])=>button(t,'window',v,state.window===v)).join('')}</div><p class="ef-note">${esc(selectedDays[0])}～${esc(selectedDays.at(-1))} · ${selectedDays.length} 個 ETF 資料日；首個快照不當作買入。</p><div class="ef-columns"><div><h4>增加持股</h4>${list(true)}</div><div><h4>減少持股</h4>${list(false)}</div></div>`,'持股快照差額包含申贖與公司行動影響，並非實際成交紀錄。')+card('單檔 ETF 每日淨申贖',ranges('range',state.range)+trackedChart('nav','單檔每日淨申贖',nav,v=>v==null?'未提供':signed(v,3)+' 千受益單位'),'直接使用來源的受益權單位日變化，不從個股持股差額推算。')+card(`${esc(state.code)} × ${esc(state.stock)} ${esc(meta.stocks.find(v=>v.code===state.stock)?.name||'')}`,ranges('range',state.range)+trackedChart('stock-flow','ETF對個股每日持股增減',daily,v=>v==null?'首次快照／不可比較':signed(v,3)+' 張',true))+card('最新完整持股',table(['股票','持股（股）','權重'],holdings),'點選股票即可切換上方歷史進出圖。');
}
async function stockView(){
 const s=await stockFile(state.stock);const form=`<form id="efStockSearch" class="ef-search"><label>股票代號／名稱<span class="ef-input-wrap"><input id="efStockInput" list="efStocks" value="${esc(state.stock)}" autocomplete="off"><button type="button" class="ef-clear-input" data-clear-stock-input aria-label="清除股票搜尋文字" title="清除" ${state.stock?'':'hidden'}>×</button></span></label><datalist id="efStocks">${stockOptions()}</datalist><button>查詢</button></form>`;
 if(!s)return form+empty('尚無這檔股票的持股變動紀錄');
 const allowed=new Set(funds().map(f=>f.code));let rows=s.events.filter(v=>allowed.has(v.etf));const calendars=new Map(Object.entries(s.calendars||{}).map(([c,days])=>[c,new Set(days.slice(-state.logDays))]));
 rows=rows.filter(v=>calendars.get(v.etf)?.has(v.date)&&(state.filter==='all'||(state.filter==='buy'?v.delta>0:v.delta<0)));const shown=rows.slice(0,state.page);
 const body=shown.map(v=>tr([esc(v.date),fundLink(v.etf),`<span class="${color(v.delta)}">${signed(v.delta)}</span>`,signed(v.flow5),signed(v.flow10),signed(v.flow30),fmt(v.shares),v.weight==null?'—':fmt(v.weight,2)+'%',v.weightDelta==null?'—':signed(v.weightDelta,2)+'%',v.weight5==null?'—':signed(v.weight5,2)+'%',v.cost==null?'資料不足':fmt(v.cost,2)]));
 return form+card(`${esc(state.stock)} ${esc(meta.stocks.find(x=>x.code===state.stock)?.name||'')} · 每日 Log`,`<div class="ef-buttons">${[['all','全部'],['buy','增加'],['sell','減少']].map(([k,t])=>button(t,'filter',k,state.filter===k)).join('')}</div><p class="ef-note">各 ETF 最近 ${state.logDays} 個資料日，共 ${rows.length} 筆。不同基金分別按自己的資料日期回算。</p>`+table(['日期','ETF','當日增減（股）','近5日','近10日','近30日','剩餘持股（股）','權重','當日權重變化','近5日權重變化','推估成本（元）'],body)+(shown.length<rows.length?`<button type="button" data-more>再顯示80筆</button>`:''),'權重變化以 % 符號顯示（數值為權重比例之差）。成本採全歷史有號股數變化×市場均價／剩餘股數；缺開倉成本或市場均價時不計算，不能當作投信真實成本。');
}
async function rankingView(){
 const data=await get('ranking.json');const allowed=new Set(funds().map(f=>f.code));const all=data.filter(v=>allowed.has(v.code)).sort((a,b)=>(b.returns[state.rank]??-Infinity)-(a.returns[state.rank]??-Infinity));let rank=0;
 const dates=[...new Set(all.filter(v=>v.returns[state.rank]!=null).map(v=>v.date))];const max=dates.sort().at(-1);const rows=all.map(v=>{const ret=v.returns[state.rank],comparable=ret!=null&&v.date===max;return tr([comparable?++rank:'—',fundLink(v.code),esc(v.date||'無行情'),`<span class="${color(ret)}">${ret==null?'歷史不足':signed(ret,2)+'%'}</span>`,!comparable&&ret!=null?'行情日期落後，不列排名':fmt(v.days)+'個資料日']);});
 return card('主動式 ETF 績效排名',ranges('rank',state.rank)+table(['排名','ETF','行情日期','區間報酬','資料狀態'],rows,'ef-ranking-table'),'以還原收盤價計算；5／21／63／126／250／750 個交易日。歷史不足不縮短期間硬算；行情日期不同者不混列名次。');
}
async function flowsView(){
 const all=await get('flows.json');const data=all.slice(-state.range);const complete=data.every(v=>v.amount!=null);const sum=complete?data.reduce((s,v)=>s+v.amount,0):null;
 let selected=data.find(v=>v.date===state.selected.flows)||data.at(-1);if(!selected)return empty('尚無 NAV 與受益權單位資料');
 const rows=selected.funds.map(v=>tr([fundLink(v.code),signed(v.deltaK,3),fmt(v.nav,4),`<span class="${color(v.amount)}">${money(v.amount)}</span>`]));
 return card('台股主動式 ETF 每日推估淨申贖',ranges('range',state.range)+`<div class="ef-stats">${stat('選取日期',selected.date)}${stat('當日完整合計',money(selected.amount))}${stat('區間完整累計',money(sum))}${stat('資料覆蓋',selected.covered+'／'+selected.expected+'檔')}</div>`+trackedChart('flows','台股主動ETF推估資金流',data.map(v=>({date:v.date,value:v.amount==null?null:v.amount/1e8})),v=>v==null?'資料未齊':signed(v,2)+' 億元')+(!complete?'<p class="ef-warning">區間有缺漏，不顯示完整累計。缺資料不是零；不將部分基金加總冒充完整資金流。</p>':'')+table(['ETF','單位變化（千）','當日NAV','推估金額'],rows),'只含當日已上市的台股主動式股票 ETF。推估金額＝受益權單位日變化（千）×1,000×當日NAV，並非實際現金申贖成交額。');
}
async function render(){const seq=++serial;root.innerHTML=header()+'<div id="efContent" aria-live="polite"><p class="ef-note">載入資料…</p></div>';try{const html=await ({etf:etfView,stock:stockView,ranking:rankingView,flows:flowsView}[state.tab])();if(seq===serial)root.querySelector('#efContent').innerHTML=html;}catch(e){if(seq===serial)root.querySelector('#efContent').innerHTML=empty('載入失敗：'+e.message);}}
root.addEventListener('click',e=>{const b=e.target.closest('button');if(b?.hasAttribute('data-clear-etf-input')||b?.hasAttribute('data-clear-stock-input')){const input=root.querySelector(b.hasAttribute('data-clear-etf-input')?'#efFundInput':'#efStockInput');if(input){input.value='';b.hidden=true;input.focus();}return;}if(b){let dirty=true;const d=b.dataset;if(d.tab){state.tab=d.tab;state.page=80;}else if(d.fund){state.code=d.fund;state.region=fund(d.fund)?.region||'TW';state.tab='etf';}else if(d.stock){state.stock=d.stock;}else if(d.window)state.window=+d.window;else if(d.range)state.range=+d.range;else if(d.rank)state.rank=+d.rank;else if(d.filter){state.filter=d.filter;state.page=80;}else if('more'in d)state.page+=80;else if('refresh'in d){location.reload();return;}else dirty=false;if(dirty){render();return;}}
 const svg=e.target.closest('svg[data-chart]');if(svg){const rows=JSON.parse(svg.closest('[data-ef-chart-data]').dataset.efChartData||'[]');if(!rows.length)return;const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;const p=pt.matrixTransform(svg.getScreenCTM().inverse());const i=Math.max(0,Math.min(rows.length-1,Math.floor((p.x-68)/(640-68-14)*rows.length)));state.selected[svg.dataset.chart]=rows[i].date;render();}});
root.addEventListener('input',e=>{if(e.target.id==='efFundInput'||e.target.id==='efStockInput'){const clear=e.target.closest('.ef-input-wrap')?.querySelector('.ef-clear-input');if(clear)clear.hidden=!e.target.value;}});
root.addEventListener('change',e=>{if(e.target.id==='efRegion'){state.region=e.target.value;state.page=80;render();}else if(e.target.dataset.chartSelect){state.selected[e.target.dataset.chartSelect]=e.target.value;render();}});
root.addEventListener('submit',e=>{if(e.target.id==='efFundSearch'){e.preventDefault();const q=root.querySelector('#efFundInput').value.trim().toLowerCase();const f=funds().find(f=>f.code.toLowerCase()===q||f.name.toLowerCase().includes(q));if(f){state.code=f.code;render();}else alert('找不到符合範圍的主動式 ETF');}if(e.target.id==='efStockSearch'){e.preventDefault();const q=root.querySelector('#efStockInput').value.trim().toLowerCase();const match=resolveStock(q);if(match.stock){state.stock=match.stock.code;state.page=80;render();}else if(match.ambiguous){alert('同名股票不只一檔，請改用股票代號查詢：'+match.ambiguous.map(v=>v.code+' '+stockDisplayName(v)).join('、'));}else alert('找不到符合的股票，請使用股票代號、券商常用簡稱或完整公司名稱');}});
// Lazy load only when the existing navigation opens this section.
let started=false;async function boot(){if(started||!root.classList.contains('active'))return;started=true;root.innerHTML='<p class="ef-note">載入主動式 ETF 資料…</p>';try{const r=await fetch('./data/etf-flow-v2/manifest.json',{cache:'no-store'});if(!r.ok)throw Error('manifest HTTP '+r.status);const m=await r.json();if(m.schema!==2||!/^versions\/[a-f0-9]{12}\/$/.test(m.path))throw Error('不支援的資料版本');base='./data/etf-flow-v2/'+m.path;meta=await get('meta.json');await loadMarketStockNames();render();}catch(e){root.innerHTML=empty('ETF資料尚未就緒：'+e.message+'。請確認已上傳 data/etf-flow-v2 資料夾。');started=false;}}
new MutationObserver(boot).observe(root,{attributes:true,attributeFilter:['class']});boot();
})();
