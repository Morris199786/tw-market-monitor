(()=>{"use strict";
const root=document.getElementById("usInsiderRoot"), section=document.getElementById("usInsider");if(!root||!section)return;
const rail=document.getElementById("featureRail"), etf=rail?.querySelector('[data-feature="etfFlow"]');
if(etf&&!rail.querySelector('[data-feature="usInsider"]')){const card=etf.cloneNode(true);card.dataset.feature="usInsider";card.setAttribute("aria-label","美股籌碼追蹤");card.querySelector(".feature-copy b").textContent="美股籌碼追蹤";card.querySelector(".feature-copy small").textContent="內部人／庫藏股／機構";card.onclick=()=>page("usInsider");etf.after(card);rail.querySelectorAll(".feature-index").forEach((n,i)=>n.textContent=String(i+1).padStart(2,"0"));try{const k="tw-feature-order-v4",a=JSON.parse(localStorage.getItem(k)||"null");if(Array.isArray(a)&&!a.includes("usInsider")){a.splice(a.indexOf("etfFlow")+1,0,"usInsider");localStorage.setItem(k,JSON.stringify(a));}}catch(e){}}
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num=(v,d=2)=>v==null?"—":Number(v).toLocaleString("en-US",{maximumFractionDigits:d,minimumFractionDigits:d});
const money=v=>v==null?"—":"$"+(v>=1e6?num(v/1e6)+"M":v>=1e3?num(v/1e3,1)+"K":num(v));
const pct=v=>v==null?"—":(v>=0?"+":"")+num(v)+"%";
const gain=v=>'<span class="uii-return '+(v>0?'up':v<0?'down':'')+'">'+pct(v)+'</span>';
const stamp=v=>v?new Date(v).toLocaleString("zh-TW",{timeZone:"Asia/Taipei",hour12:false,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}):"—";
let data=null,loading=false,tab="rank",ticker="",days=20,threshold=0,search="",role="",purchase="research_buy",chartIndex=-1;
const classNames={confirmed_market:"明確公開市場交易",discretionary_candidate:"一般交易（性質未確認）",scheduled_plan:"10b5-1預定交易",plan_uncertain:"計畫歸屬未確認",employee_plan:"員工購股",private_purchase:"協議／認購交易"};
const securityNames={local_common:"本地普通股",adr:"ADR",listed_equity:"上市股票"};
let rankSort="amount",clusterDays=14,person="",tradeSide="buy",rankDesc=true;
const latest=(rows,key)=>rows.map(r=>r[key]).filter(Boolean).sort().at(-1)||"";
const shortDate=d=>d?d.slice(5).replace("-","/"):"—";
const ownerSet=rows=>new Set(rows.flatMap(r=>Array.isArray(r.owner_ids)&&r.owner_ids.length?r.owner_ids:[r.owner_id||r.owner]).filter(Boolean));
function holdingChange(r){
 const post=r.post_shares,shares=r.raw_shares;
 // Transaction-row change only, not an estimate of total beneficial ownership.
 if(r.joint||r.amendment||!["D","I"].includes(r.ownership)||!Number.isFinite(post)||!Number.isFinite(shares)||shares<=0||post<shares)return null;
 const before=post-shares;
 return {before,post,shares,pct:before>0?shares/before*100:null,newPosition:before===0};
}
function cluster(g){
 const end=data.as_of,start=windowStart(clusterDays);if(!start)return {n:0,amount:0};
 const rr=selectedRows(tradeSide,clusterDays).filter(r=>r.ticker===g.ticker&&r.security_class===g.security_class&&r.security===g.security);
 return {n:ownerSet(rr).size,amount:rr.reduce((a,r)=>a+r.amount,0)};
}
function ownerHistory(g){
 const all=data.transactions.filter(r=>r.ticker===g.ticker&&r.security_class===g.security_class&&r.security===g.security&&r.purchase_class!=="employee_plan");
 const m=new Map();
 for(const r of all){const key=r.owner_id||r.owner;let a=m.get(key);if(!a)m.set(key,a={key,name:r.owner,role:r.role,rows:[],amount:0});a.rows.push(r);a.amount+=r.amount}
 return '<section class="uii-research"><div class="uii-cardhead"><h2>內部人歷史買進</h2></div><p class="uii-note">'+esc(data.start)+' ～ '+esc(data.as_of)+'；不含員工購股。</p>'+[...m.values()].sort((a,b)=>b.amount-a.amount).map(a=>'<details class="uii-person"><summary><span><strong>'+esc(a.name)+'</strong><small>'+esc(a.role)+'</small></span><span><strong>'+money(a.amount)+'</strong><small>'+a.rows.length+'筆</small></span></summary>'+a.rows.slice().sort((x,y)=>y.date.localeCompare(x.date)).map(r=>{const h=holdingChange(r);return '<div class="uii-trade"><div><b>'+esc(r.date)+'</b><small>公告 '+esc(r.filed)+'</small></div><div><b>'+money(r.amount)+'</b><small>'+esc(classNames[r.purchase_class]||"未分類")+'</small></div><div><b>'+num(r.raw_shares,0)+'股</b><small>原始成交 '+money(r.raw_price)+'</small></div><div><b>'+(h?(h.newPosition?"由零增加":pct(h.pct)):"—")+'</b><small>該列持股增加率</small></div>'+(h?'<div class="uii-holding">交易前 '+num(h.before,0)+' → 交易後 '+num(h.post,0)+' 股</div>':"")+'</div>'}).join("")+'</details>').join("")+'<p class="uii-note">僅表示該列申報部位，不等於個人全部持股。</p></section>';
}
let stockDays=20,stockKind="research_buy",stockRole="",stockSide="all";
const sideOf=r=>r.side==="sell"?"sell":"buy";
const sessions=()=>data?.trading_sessions||[];
const windowStart=(n=days)=>{const ss=sessions();return ss.length>=n?ss.at(-n):null};
const validKind=r=>r.purchase_class!=="employee_plan"&&(!purchase||(purchase==="research_buy"?["confirmed_market","discretionary_candidate"].includes(r.purchase_class):r.purchase_class===purchase));
function selectedRows(side=tradeSide,n=days){
 const start=windowStart(n);if(!start)return [];
 const end=data?.as_of||"";
 return [...(data?.transactions||[]),...(data?.sales||[])].filter(r=>r.date>=start&&r.date<=end&&r.filed<=end&&validKind(r)&&(!role||String(r.role).includes(role))&&(side==="all"||sideOf(r)===side));
}
function dailyRows(rr){
 const m=new Map();
 for(const r of rr){const k=JSON.stringify([r.ticker,r.owner_id||r.owner,r.date,sideOf(r),r.purchase_class,r.security_class,r.security,r.ownership]);if(!m.has(k))m.set(k,{...r,parts:[],amount:0,shares:0,raw_shares:0});const g=m.get(k);g.parts.push(r);g.amount+=r.amount;g.shares+=r.shares;g.raw_shares+=r.raw_shares||0}
 return [...m.values()].map(g=>({...g,price:g.shares>0?g.amount/g.shares:null,raw_price:g.raw_shares>0?g.amount/g.raw_shares:null,filed:latest(g.parts,"filed")})).sort((a,b)=>b.date.localeCompare(a.date)||b.amount-a.amount)
}
function groups(side=tradeSide){
 const m=new Map();for(const x of selectedRows(side)){const key=x.ticker+"|"+x.security_class+"|"+x.security;let g=m.get(key);if(!g)m.set(key,g={key,ticker:x.ticker,security:x.security,security_class:x.security_class,comparable:x.price_comparable===true,amount:0,shares:0,buy:0,sell:0,buyShares:0,sellShares:0,people:new Set(),rows:[]});g.amount+=x.amount;g.shares+=x.shares;const k=sideOf(x);g[k]+=x.amount;g[k+"Shares"]+=x.shares;g.people.add(x.owner_id||x.owner);g.rows.push(x)}
 return [...m.values()].map(g=>({...g,cost:g.buyShares?g.buy/g.buyShares:null,sellCost:g.sellShares?g.sell/g.sellShares:null,price:g.comparable?data.prices?.[g.ticker]?.at(-1)?.close:null})).sort((a,b)=>b.amount-a.amount)
}
function holdingMagnitude(g,side){const v=dailyRows(g.rows).filter(r=>side==="all"||sideOf(r)===side).map(dailyHolding).filter(Boolean).map(h=>Math.abs(h.pct)).filter(Number.isFinite);return v.length?Math.max(...v):null}
function dailyHolding(g){
 const rr=g.parts||[g];if(rr.some(r=>r.joint||r.amendment||r.ownership!=="D"||!Number.isFinite(r.post_shares)||!Number.isFinite(r.raw_shares)||r.raw_shares<=0))return null;
 const sign=sideOf(g)==="sell"?-1:1;
 const legs=rr.map(r=>({before:r.post_shares-sign*r.raw_shares,post:r.post_shares}));if(legs.some(x=>x.before<0||x.post<0))return null;
 // Direct holdings only; require an unambiguous chain, never add percentages.
 legs.sort((a,b)=>sign*(a.before-b.before));for(let i=1;i<legs.length;i++)if(Math.abs(legs[i-1].post-legs[i].before)>1e-6)return null;
 const before=legs[0].before,post=legs.at(-1).post;
 return {before,post,pct:before>0?(post/before-1)*100:null,newPosition:before===0&&post>0};
}
function rankValue(g,k){switch(k){case "buy":return g.buy;case "sell":return g.sell;case "net":return g.buy-g.sell;case "holding":return holdingMagnitude(g,tradeSide);case "people":return ownerSet(g.rows).size;case "date":return latest(g.rows,"date");case "filed":return latest(g.rows,"filed");case "return":{const cost=tradeSide==="sell"?g.sellCost:g.cost;return g.price!=null&&cost?100*(g.price/cost-1):null}case "cluster":return cluster(g).n;default:return g.amount}}
function compareRank(a,b){const x=rankValue(a,rankSort),y=rankValue(b,rankSort);if(x==null||y==null)return x==null?(y==null?b.amount-a.amount:1):-1;return (typeof x==="string"?x.localeCompare(y):x-y)*(rankDesc?-1:1)||b.amount-a.amount}
const extra={buybacks:null,institutional:null},extraBusy=new Set();let extraTicker="",extraPeriod="";
async function loadExtra(k){
 if(extra[k]||extraBusy.has(k))return;
 extraBusy.add(k);
 try{const res=await fetch("./data/us_insider/"+k+".json",{cache:"no-store"});if(!res.ok)throw Error(res.status);extra[k]=await res.json()}catch(e){extra[k]={error:true}}
 finally{extraBusy.delete(k);if(tab===k)render()}
}
const institutionCache=new Map(),institutionBusy=new Set();
async function loadInstitution(t,d){
 const entry=d.shards?.[t];if(!entry)return;
 const key=d.updated_at+"|"+t;if(institutionCache.has(key)||institutionBusy.has(key))return;
 institutionBusy.add(key);
 try{const r=await fetch("./data/us_insider/"+entry.file,{cache:"no-store"});if(!r.ok)throw Error(r.status);const v=await r.json();if(v.ticker!==t||v.rows?.length!==entry.count)throw Error("shard mismatch");institutionCache.set(key,v.rows)}
 catch(e){institutionCache.set(key,null)}
 finally{institutionBusy.delete(key);if(tab==="institutional")render()}
}
function institutionRow(x,quarterPrice){
 const pct=x.change_pct==null?(x.previous_shares?100*x.change/x.previous_shares:null):x.change_pct;
 const cls=x.change>0?"uii-inst-up":x.change<0?"uii-inst-down":"";
 return '<tr><td title="CIK '+esc(x.cik)+'">'+esc(x.manager_name||("CIK "+x.cik))+'</td><td>'+millionShares(x.previous_shares)+'</td><td>'+millionShares(x.shares)+'</td><td class="'+cls+'">'+millionShares(x.change,true)+'<small>'+(Number.isFinite(quarterPrice)?signedMoney(x.change*quarterPrice):"—")+'</small><small>'+(pct==null?"—":(pct>0?"+":"")+num(pct,2)+"%")+'</small></td><td><a href="'+esc(x.url)+'" target="_blank" rel="noopener">'+esc(x.filed)+'</a></td></tr>';
}
let instSide="up",instSort="money",instDesc=true;
const quarterLabel=t=>/^\d{4}-\d{2}-\d{2}$/.test(t||"")?t.slice(0,4)+" Q"+Math.ceil(Number(t.slice(5,7))/3):t||"—";
function millionShares(v,signed=false){if(!Number.isFinite(v))return "—";const a=Math.abs(v)/1e6;return (v<0?"-":signed&&v>0?"+":"")+(a>0&&a<.005?"<0.01":a.toFixed(2))+"M"}
function institutionShards(d){
 const names=Object.keys(d.shards||{}).sort(),periods=Object.keys(d.summary||{}).sort().reverse(),period=periods.includes(extraPeriod)?extraPeriod:periods[0];
 const opts='<select data-field="extraTicker"><option value="">全部追蹤股票</option>'+names.map(t=>'<option '+(t===extraTicker?'selected':'')+'>'+esc(t)+'</option>').join("")+'</select>';
 const sel='<select data-field="extraPeriod">'+periods.map(t=>'<option value="'+esc(t)+'" '+(t===period?'selected':'')+'>'+esc(quarterLabel(t))+'</option>').join("")+'</select>';
 const header='<section class="uii-card"><div class="uii-cardhead"><h2>機構持股變動</h2><span>13F · 季末</span></div><div class="uii-rank-controls">'+opts+sel+'</div><details class="uii-stockhelp"><summary>資料範圍說明</summary><p>'+esc(d.note)+'</p></details>'+(d.missing_expected_period?'<p class="uii-warning">最新完整資料尚未補齊 '+esc(d.expected_period)+'；目前 '+esc(d.latest_period)+'</p>':'');
 const groups=(d.summary?.[period]||[]).filter(g=>(!extraTicker||g.ticker===extraTicker)&&(instSide==="all"|| (instSide==="up"?g.change>0:g.change<0))).slice().sort((a,b)=>{const v=g=>instSort==="shares"?g.change:instSort==="pct"?g.change_pct:instSort==="up"?g.up:instSort==="down"?g.down:instSort==="ratio"?(g.up/(g.up+g.down+g.flat||1)):g.estimated_change_usd;const x=v(a),y=v(b);if(x==null||y==null)return x==null?(y==null?0:1):-1;return (instSide==="down"&&["money","shares","pct"].includes(instSort)?x-y:instSide==="all"&&["money","shares","pct"].includes(instSort)?Math.abs(y)-Math.abs(x):y-x)*(instDesc?1:-1)});
 const controls='<div class="uii-side">'+[["up","淨增持"],["down","淨減持"],["all","全部"]].map(([v,t])=>'<button data-inst-side="'+v+'" aria-pressed="'+(instSide===v)+'">'+t+'</button>').join("")+'</div><div class="uii-rank-controls"><select data-field="instSort">'+[["money","估算淨變動金額"],["shares","淨變動股數"],["pct","持股變動率"],["up","增持機構家數"],["down","減持機構家數"],["ratio","增持機構占比"]].map(([v,t])=>'<option value="'+v+'" '+(instSort===v?"selected":"")+'>'+t+'</option>').join("")+'</select><button data-inst-dir>'+(instDesc?"預設順序":"反向排序")+'</button></div>';
 return header+controls+(!(d.summary?.[period]||[]).some(g=>Number.isFinite(g.estimated_change_usd))?'<p class="uii-warning">季末估算金額尚未取得，暫可選擇股數排序。</p>':"")+groups.map(g=>{
 const key=d.updated_at+"|"+g.ticker,loaded=institutionCache.has(key),rr=institutionCache.get(key);
 const cls=g.change>0?"uii-inst-up":g.change<0?"uii-inst-down":"",total=g.up+g.down+g.flat||1;
 const summary='<summary><span><strong>'+esc(g.ticker)+'</strong><small><span class="uii-inst-up">增持 '+num(g.up,0)+'家</span>／<span class="uii-inst-down">減持 '+num(g.down,0)+'家</span>／不變 '+num(g.flat,0)+'家</small><span class="uii-inst-bar"><i style="width:'+100*g.up/total+'%"></i><i style="width:'+100*g.down/total+'%"></i><i style="width:'+100*g.flat/total+'%"></i></span></span><span><strong class="'+cls+'">'+(Number.isFinite(g.estimated_change_usd)?signedMoney(g.estimated_change_usd):"金額未取得")+'</strong><small class="'+cls+'">'+millionShares(g.change,true)+' 股</small><small>估算淨變動</small></span></summary>';
 return '<details class="uii-person" data-institution-stock="'+esc(g.ticker)+'" '+(institutionOpen.has(g.ticker)||extraTicker===g.ticker?'open':'')+'>'+summary+(!loaded?'<p class="uii-note">展開後載入機構明細</p>':rr===null?'<button data-institution-retry="'+esc(g.ticker)+'">重新載入</button>':'<div class="uii-scroll"><table><thead><tr><th>機構名稱</th><th>前季</th><th>本季</th><th>增減股數／幅度</th><th>申報</th></tr></thead><tbody>'+rr.filter(x=>x.period===period).sort((a,b)=>Math.abs(b.change)-Math.abs(a.change)).map(x=>institutionRow(x,g.quarter_price)).join("")+'</tbody></table></div>')+'</details>'
 }).join("")+'</section>'
}
const institutionOpen=new Set();
function extraView(k){
 const d=extra[k];if(!d){loadExtra(k);return '<p class="uii-note">載入 SEC 資料中…</p>'}
 if(d.error)return '<section class="uii-card"><h2>資料尚未建立</h2><p class="uii-note">尚未取得已驗證的 SEC 資料，不代表沒有回購或機構持股。</p><button data-extra-retry>重新載入</button></section>';
 if(k==="institutional"&&d.schema_version===2&&d.shards)return institutionShards(d);
 const rr=d.rows||[],names=[...new Set(rr.map(x=>x.ticker))].sort();
 const rows=rr.filter(x=>!extraTicker||x.ticker===extraTicker);
 const options='<select data-field="extraTicker"><option value="">全部已取得股票</option>'+names.map(t=>'<option '+(t===extraTicker?'selected':'')+'>'+esc(t)+'</option>').join("")+'</select>';
 if(k==="buybacks"){
  const mode=extraPeriod==="history"?"history":"latest";
  const tickers=[...new Set([...Object.keys(d.coverage||{}),...names])].sort();
  const stockSelect='<select data-field="extraTicker" aria-label="股票"><option value="">全部追蹤股票</option>'+tickers.map(t=>'<option '+(t===extraTicker?'selected':'')+'>'+esc(t)+'</option>').join("")+'</select>';
  const periodSelect='<select data-field="extraPeriod" aria-label="回購統計期間"><option value="latest" '+(mode==="latest"?"selected":"")+'>各公司最新一季</option><option value="history" '+(mode==="history"?"selected":"")+'>全部歷史紀錄</option></select>';
  const duration=x=>Math.round((Date.parse(x.end)-Date.parse(x.start))/86400000)+1;
  const quarter=x=>duration(x)>=70&&duration(x)<=110;
  const grouped=new Map();
  for(const x of rows){const key=x.ticker+"|"+x.start+"|"+x.end;if(!grouped.has(key))grouped.set(key,{ticker:x.ticker,start:x.start,end:x.end,items:{}});const items=grouped.get(key).items,prev=items[x.kind];if(!prev||x.filed>prev.filed||(x.filed===prev.filed&&x.unit==="USD"))items[x.kind]=x}
  const groups=[...grouped.values()].sort((a,b)=>b.end.localeCompare(a.end)||a.start.localeCompare(b.start));
  const selected=tickers.filter(t=>!extraTicker||t===extraTicker);
  const value=(x,kind)=>!x?"未取得":kind==="shares"?num(x.value,0)+" 股":(x.unit==="USD"||x.unit==="USD/shares"?"$":esc(x.unit.split("/")[0])+" ")+(kind==="payments"?(x.value>=1e6?num(x.value/1e6)+"M":num(x.value,0)):num(x.value,2));
  const renderGroup=g=>{const a=g.items.payments,b=g.items.shares;const zero=a?.value===0||b?.value===0,positive=a?.value>0||b?.value>0;const state=zero&&positive?"揭露不一致":positive?"已回購":zero?"未回購":"未確認";
   const links=[...new Map(Object.values(g.items).map(x=>[x.url,x])).values()].sort((a,b)=>b.filed.localeCompare(a.filed));
   return '<tr><td><strong>'+esc(g.ticker)+'</strong><small>'+esc(g.end)+'</small><small>'+ (quarter(g)?"單季":"累計／其他")+'</small></td><td><strong>'+value(a,"payments")+'</strong><small>'+value(b,"shares")+'</small></td><td><span class="'+(positive&&!zero?"uii-inst-up":"")+'">'+state+'</span><small>'+links.map(x=>'<a href="'+esc(x.url)+'" target="_blank" rel="noopener">'+esc(x.filed)+'</a>').join(" ／ ")+'</small></td></tr>'};
  const missing=[];let shown=groups;
  if(mode==="latest"){shown=selected.flatMap(t=>{const g=groups.find(x=>x.ticker===t&&quarter(x));if(!g){missing.push(t);return []}return [g]});shown.sort((a,b)=>b.end.localeCompare(a.end)||a.ticker.localeCompare(b.ticker))}
  const body=shown.map(renderGroup).join("");
  return '<section class="uii-card"><div class="uii-cardhead"><h2>公司庫藏股｜實際回購</h2><span>SEC財報</span></div><div class="uii-rank-controls">'+stockSelect+periodSelect+'</div><table class="uii-buyback-table" style="width:100%;table-layout:fixed"><colgroup><col style="width:28%"><col style="width:39%"><col style="width:33%"></colgroup><thead><tr><th style="text-align:left">股票／期末</th><th style="text-align:right">金額／股數</th><th style="text-align:right">狀態／申報日</th></tr></thead><tbody>'+body+'</tbody></table>'+(!body?'<p class="uii-note">未取得符合條件的回購資料</p>':"")+(missing.length?'<details class="uii-status"><summary>未取得單季資料（'+missing.length+'檔）</summary><p>'+esc(missing.join("、"))+'</p></details>':"")+'</section>'
 }
 const periods=[...new Set(rows.map(x=>x.period))].sort().reverse(),period=periods.includes(extraPeriod)?extraPeriod:periods[0];
 const sel='<select data-field="extraPeriod">'+periods.map(t=>'<option '+(t===period?'selected':'')+'>'+esc(t)+'</option>').join("")+'</select>';
 const m=new Map();for(const x of rows.filter(x=>x.period===period)){let g=m.get(x.ticker);if(!g)m.set(x.ticker,g={ticker:x.ticker,up:0,down:0,flat:0,change:0,rows:[]});g[x.change>0?"up":x.change<0?"down":"flat"]++;g.change+=x.change;g.rows.push(x)}
 return '<section class="uii-card"><div class="uii-cardhead"><h2>機構持股變動</h2><span>13F · 季末</span></div><div class="uii-rank-controls">'+options+sel+'</div><p class="uii-note">目前 CUSIP 已核對 '+(d.coverage||[]).length+' 檔；'+esc(d.note)+'</p>'+[...m.values()].sort((a,b)=>b.change-a.change).map(g=>'<details class="uii-person"><summary><span><strong>'+esc(g.ticker)+'</strong><small>增持 '+g.up+'／減持 '+g.down+'／不變 '+g.flat+'</small></span><span><strong>'+num(g.change,0)+' 股</strong><small>配對申報淨變動</small></span></summary><div class="uii-scroll"><table><thead><tr><th>機構名稱</th><th>前季</th><th>本季</th><th>增減股數／幅度</th><th>申報</th></tr></thead><tbody>'+g.rows.slice().sort((a,b)=>Math.abs(b.change)-Math.abs(a.change)).map(x=>institutionRow(x)).join("")+'</tbody></table></div></details>').join("")+'</section>'
}
function overviewStatus(g,items){
 const bit=(label,value)=>'<div><small>'+esc(label)+'</small><strong>'+esc(String(value))+'</strong></div>';
 let bits=[];
 if(tab==="sales")return "";
 if(tab==="buybacks"){
  const d=extra.buybacks;if(!d||d.error)return "";
  const rr=d.rows||[],latest=new Map();
  for(const x of rr){const n=(Date.parse(x.end)-Date.parse(x.start))/86400000+1;if(n<70||n>110)continue;const prev=latest.get(x.ticker);if(!prev||x.end>prev.end)latest.set(x.ticker,{end:x.end,rows:[x]});else if(x.end===prev.end)prev.rows.push(x)}
  const vals=[...latest.values()],positive=vals.filter(v=>v.rows.some(x=>["payments","shares"].includes(x.kind)&&x.value>0)).length;
  bits=[bit("已取得單季紀錄",latest.size+" 家"),bit("最近取得單季有回購",positive+" 家"),bit("最新SEC申報",rr.map(x=>x.filed).sort().at(-1)||"—")];
 }else if(tab==="institutional"){
  const d=extra.institutional;if(!d||d.error)return "";
  const periods=Object.keys(d.summary||{}).sort().reverse(),p=periods.includes(extraPeriod)?extraPeriod:periods[0],v=d.summary?.[p]||[];
  bits=[bit("持股季度",quarterLabel(p)),bit("本季有比較資料",v.length+" 檔"),bit("拆股調整",d.split_adjusted?"已調整":"尚未調整")];
 }else{
  if(!data)return "";
  if(tab==="stock")return "";
  bits=[bit("觀察期間","近"+days+"交易日"),bit("符合條件",items.length+" 組"),bit(tradeSide==="buy"?"買進金額":tradeSide==="sell"?"賣出金額":"交易總額",money(items.reduce((a,x)=>a+x.amount,0)))];
  if(tab==="test")bits=[bit("回測資料起日",data.start||"—"),bit("回測資料迄日",data.as_of||"—")];
 }
 return '<div class="uii-overview uii-context-overview">'+bits.join("")+'</div>';
}
function salesView(){
 if(!data?.classification_version)return '<section class="uii-card"><h2>內部人賣出</h2><p>尚未取得新版賣出資料。</p></section>';
 const start=new Date(Date.parse(data.as_of)-(days-1)*86400000).toISOString().slice(0,10);
 const rr=(data.sales||[]).filter(x=>x.date>=start&&x.date<=data.as_of&&(!role||String(x.role).includes(role))&&(!search||[x.ticker,x.owner].join(" ").toUpperCase().includes(search.toUpperCase()))).sort((a,b)=>b.filed.localeCompare(a.filed)||b.amount-a.amount);
 const total=rr.reduce((a,x)=>a+x.amount,0);
 return '<section class="uii-card"><div class="uii-cardhead"><h2>內部人賣出紀錄</h2><span>Form 4 · S類</span></div><div class="uii-overview"><div><small>累計賣出金額</small><strong>'+money(total)+'</strong></div><div><small>交易筆數</small><strong>'+rr.length+'</strong></div></div><div class="uii-rank-controls"><select data-field="days" aria-label="觀察期間">'+[7,30,90,365].map(n=>'<option value="'+n+'" '+(days===n?"selected":"")+'>近'+n+'日</option>').join("")+'</select><input data-field="search" placeholder="搜尋代號或內部人" value="'+esc(search)+'"></div><div class="uii-scroll"><table><thead><tr><th>股票／內部人</th><th>賣出金額</th><th>交易／申報日</th></tr></thead><tbody>'+rr.map(x=>'<tr><td><strong>'+esc(x.ticker)+'</strong><small>'+esc(x.owner)+'</small><small>'+esc(classNames[x.purchase_class]||"未分類")+'</small></td><td>'+money(x.amount)+'<small>'+num(x.raw_shares,0)+'股</small></td><td>'+esc(x.date)+'<small><a href="'+esc(x.url)+'" target="_blank" rel="noopener">'+esc(x.filed)+'</a></small></td></tr>').join("")+'</tbody></table></div>'+(rr.length?"":'<p>沒有符合篩選條件的已取得賣出紀錄。</p>')+'</section>';
}
function render(){if(tab==="sales"){tab="rank";tradeSide="sell"}const g=groups(tab==="stock"?"all":tradeSide),items=g.filter(x=>x.amount>=threshold&&(!search||[x.ticker,...x.rows.map(r=>r.owner)].join(" ").toUpperCase().includes(search.toUpperCase())));items.sort(compareRank);root.innerHTML='<div class="uii-head"><div><small class="uii-kicker">US OWNERSHIP MONITOR</small><h1>美股籌碼追蹤</h1><p>內部人交易・公司庫藏股・機構持股</p></div></div><div class="uii-meta"><span>更新 '+esc(stamp(data?.updated_at))+'</span><span>行情 '+esc(data?.price_as_of||"—")+'</span></div><div class="uii-tabs">'+[["rank","內部人交易"],["stock","個股追蹤"],["test","績效回測"],["buybacks","公司庫藏股"],["institutional","機構持股"]].map(([k,t])=>'<button data-tab="'+k+'" aria-pressed="'+(tab===k)+'">'+t+'</button>').join("")+ '</div>'+overviewStatus(g,items)+(tab==="rank"?sideControls():"")+(data?.stale_prices?.length?'<p class="uii-warning">部分行情尚未更新至 '+esc(data.expected_price_as_of)+'，報酬以實際行情日期為準。</p>':"")+'<div class="uii-tools" '+(tab!=="rank"?"hidden":"")+'><select data-field="days" aria-label="期間">'+[5,10,20,60,120,240].map(n=>'<option '+(days===n?"selected":"")+' value="'+n+'">近'+n+'交易日</option>').join("")+'</select><select data-field="threshold" aria-label="最低累計交易金額">'+[0,100000,250000,500000,1000000,2000000,5000000,10000000].map(n=>'<option '+(threshold===n?"selected":"")+' value="'+n+'">'+(n?money(n)+"以上":"全部金額")+'</option>').join("")+'</select><select data-field="role" aria-label="職位">'+["","CEO","CFO","董事","高階主管","大股東"].map(n=>'<option '+(role===n?"selected":"")+' value="'+n+'">'+(n||"全部身分")+'</option>').join("")+'</select><div class="uii-purchase-control"><select data-field="purchase" aria-label="交易類型">'+[["research_buy","一般交易"],["scheduled_plan","預定交易"],["private_purchase","協議交易"],["","全部交易"]].map(([v,t])=>'<option '+(purchase===v?"selected":"")+' value="'+v+'">'+t+'</option>').join("")+'</select><button type="button" class="uii-help-toggle" data-purchase-help aria-label="交易類型說明" aria-expanded="false" aria-controls="uiiPurchaseHelp"><span aria-hidden="true">!</span></button></div><div id="uiiPurchaseHelp" class="uii-purchase-help" hidden><div class="uii-help-head"><strong>交易類型說明</strong><button type="button" data-purchase-help-close aria-label="關閉交易類型說明">×</button></div><p><strong>一般交易</strong>：公開市場交易及未發現特殊條件的買賣，不代表已確認投資動機。</p><p><strong>預定交易</strong>：明確依10b5-1計畫執行。</p><p><strong>協議交易</strong>：私募、認購或私人協議交易。</p><p><strong>全部交易</strong>：包含上述及計畫歸屬未確認交易，不含員工購股、獎勵、贈與及抵稅。</p></div><input data-field="search" placeholder="搜尋代號或內部人" value="'+esc(search)+'"></div><div class="uii-content">'+(tab==="rank"?rank(items):tab==="stock"?stock():tab==="test"?backtest():extraView(tab))+'</div>';bind()}
function sideControls(){return '<div class="uii-side">'+[["buy","買進"],["sell","賣出"],["all","全部"]].map(([v,t])=>'<button data-side="'+v+'" aria-pressed="'+(tradeSide===v)+'">'+t+'</button>').join("")+'</div>'}
function rank(items){
 const sortOpts=[["amount","交易總額"],["buy","買進金額"],["sell","賣出金額"],["net","淨買賣額"],["holding",tradeSide==="buy"?"最大增持幅度":tradeSide==="sell"?"最大減持幅度":"最大持股變動幅度"],["date","最近交易日"],["filed","最近申報日"],["people","交易人數"],["cluster","同步交易人數"],["return","成交價相對股價"]];
 const th=(k,t)=>'<th><button class="uii-sort" data-sort="'+k+'">'+t+(rankSort===k?(rankDesc?" ↓":" ↑"):"")+'</button></th>';
 const ready=!!windowStart(),saleReady=!!data?.classification_version;
 const cell=(g,k)=>'<td class="'+(k==="buy"?"uii-inst-up":"uii-inst-down")+'">'+(k==="sell"&&!saleReady?"未取得":money(g[k]))+'</td>';
 const body=items.map((g,i)=>'<tr><td><button class="uii-stocklink" data-stock="'+esc(g.key)+'">'+esc(g.ticker)+'</button><small>'+ownerSet(g.rows).size+'人 · '+new Set(g.rows.map(x=>x.date)).size+'日</small></td>'+(tradeSide!=="sell"?cell(g,"buy"):"")+(tradeSide!=="buy"?cell(g,"sell"):"")+(tradeSide==="all"?'<td>'+(!saleReady?"—":(g.buy-g.sell<0?"-":"+")+money(Math.abs(g.buy-g.sell)))+'</td>':'<td>'+num(tradeSide==="sell"?g.sellCost:g.cost)+'</td>')+'<td>'+shortDate(latest(g.rows,"date"))+'<small>'+shortDate(latest(g.rows,"filed"))+'</small></td></tr>').join("");
 return '<section class="uii-card"><div class="uii-cardhead"><h2>內部人交易排行</h2><span>'+items.length+' 組 · USD</span></div><div class="uii-rank-controls"><label>排序 <select data-field="rankSort">'+sortOpts.map(([v,t])=>'<option value="'+v+'" '+(rankSort===v?"selected":"")+'>'+t+'</option>').join("")+'</select></label><button data-sort-dir>'+ (rankDesc?"由大到小":"由小到大")+'</button></div>'+(!ready?'<p class="uii-warning">尚未取得完整交易日曆，暫不顯示該期間排行。</p>':!saleReady&&tradeSide!=="buy"?'<p class="uii-warning">新版賣出資料尚未建立。</p>':"")+'<div class="uii-scroll uii-rank"><table><thead><tr><th>股票</th>'+(tradeSide!=="sell"?th("buy","買進"):"")+(tradeSide!=="buy"?th("sell","賣出"):"")+(tradeSide==="all"?th("net","淨額"):"<th>成交均價</th>")+th("date","交易／申報")+'</tr></thead><tbody>'+body+'</tbody></table></div>'+(!body&&ready?'<p>沒有符合條件的已取得交易。</p>':"")+'</section>'
}
function stockCatalog(){
 const m=new Map();for(const r of [...(data?.transactions||[]),...(data?.sales||[])]){const k=r.ticker+"|"+r.security_class+"|"+r.security;if(!m.has(k))m.set(k,{key:k,ticker:r.ticker,security:r.security,security_class:r.security_class,comparable:r.price_comparable===true})}
 for(const t of Object.keys(data?.coverage||{})){if(![...m.values()].some(x=>x.ticker===t))m.set(t+"||",{key:t+"||",ticker:t,security:"",comparable:false})}
 return [...m.values()].sort((a,b)=>a.ticker.localeCompare(b.ticker)||a.security.localeCompare(b.security))
}
function stockGroup(n=stockDays){
 const c=stockCatalog().find(x=>x.key===ticker);if(!c)return null;
 const start=windowStart(n),end=data?.as_of||"";
 const rr=start?[...(data.transactions||[]),...(data.sales||[])].filter(r=>r.ticker===c.ticker&&r.security===c.security&&r.security_class===c.security_class&&r.date>=start&&r.date<=end&&r.filed<=end&&r.purchase_class!=="employee_plan"&&(!stockRole||String(r.role).includes(stockRole))&&(!stockKind||(stockKind==="research_buy"?["confirmed_market","discretionary_candidate"].includes(r.purchase_class):r.purchase_class===stockKind))):[];
 const buys=rr.filter(r=>sideOf(r)==="buy"),sells=rr.filter(r=>sideOf(r)==="sell"),sum=(a,k)=>a.reduce((v,r)=>v+(r[k]||0),0),buy=sum(buys,"amount"),sell=sum(sells,"amount"),bs=sum(buys,"shares"),ss=sum(sells,"shares");
 return {...c,rows:rr,buy,sell,amount:buy+sell,cost:bs?buy/bs:null,sellCost:ss?sell/ss:null,price:c.comparable?data.prices?.[c.ticker]?.at(-1)?.close:null,ready:!!start}
}
const signedMoney=v=>(v<0?"-":v>0?"+":"")+money(Math.abs(v));
function stock(){
 const gs=stockCatalog();if(!gs.length)return '<p>尚無可選個股資料。</p>';if(!gs.some(x=>x.key===ticker))ticker=gs[0].key;
 const g=stockGroup(),start=windowStart(stockDays),prices=g.comparable&&start?(data.prices?.[g.ticker]||[]).filter(x=>x.date>=start&&x.date<=data.as_of):[];
 const saleReady=!!data.classification_version,net=g.buy-g.sell,fmtNet=signedMoney(net);
 const select=(field,opts,v)=>'<select data-field="'+field+'">'+opts.map(([k,t])=>'<option value="'+esc(k)+'" '+(String(k)===String(v)?"selected":"")+'>'+esc(t)+'</option>').join("")+'</select>';
 const controls='<div class="uii-stockfilters">'+select("ticker",gs.map(x=>[x.key,x.ticker+(x.security?" · "+x.security:"")]),ticker)+'<div class="uii-side">'+[["buy","買進"],["sell","賣出"],["all","全部"]].map(([v,t])=>'<button data-stock-side="'+v+'" aria-pressed="'+(stockSide===v)+'">'+t+'</button>').join("")+'</div><div class="uii-stockgrid">'+select("stockDays",[5,10,20,60,120,240].map(n=>[n,"近"+n+"交易日"]),stockDays)+select("stockKind",[["research_buy","一般交易"],["scheduled_plan","預定交易"],["private_purchase","協議交易"],["","全部交易"]],stockKind)+select("stockRole",["","CEO","CFO","董事","高階主管","大股東"].map(x=>[x,x||"全部身分"]),stockRole)+'</div><details class="uii-stockhelp"><summary>交易類型說明</summary><p>一般交易：公開市場及性質未確認的一般買賣。預定交易：明確依10b5-1計畫。協議交易：私人協議或認購。全部交易包含計畫歸屬未確認的買賣，不含員工購股、獎勵、贈與及抵稅。</p></details></div>';
 if(!g.ready)return '<section class="uii-card"><h2>個股追蹤</h2>'+controls+'<p class="uii-warning">尚未取得足夠交易日曆，不能判定此期間交易金額。</p></section>';
 const count=side=>{const rr=g.rows.filter(r=>sideOf(r)===side);return ownerSet(rr).size+'人 · '+new Set(rr.map(r=>r.date)).size+'日'};
 const totals='<div class="uii-overview uii-context-overview"><div><small>累計買進</small><strong class="uii-inst-up">'+money(g.buy)+'</strong><small>'+count("buy")+'</small></div><div><small>累計賣出</small><strong class="uii-inst-down">'+(saleReady?money(g.sell):"未取得")+'</strong><small>'+(saleReady?count("sell"):"")+'</small></div><div><small>淨買賣額</small><strong class="'+(net<0?"uii-inst-down":"uii-inst-up")+'">'+(saleReady?fmtNet:"—")+'</strong></div></div>';
 const daily=dailyRows(g.rows.filter(r=>stockSide==="all"||sideOf(r)===stockSide));
 const rows=daily.map(x=>{const h=dailyHolding(x),sell=sideOf(x)==="sell";return '<details class="uii-person"><summary><span><strong>'+esc(x.owner)+'</strong><small>'+esc(x.date)+' · '+esc(x.role)+' · '+esc(classNames[x.purchase_class]||"未分類")+'</small></span><span><strong class="'+(sell?"uii-inst-down":"uii-inst-up")+'">'+(sell?"賣出 ":"買進 ")+money(x.amount)+'</strong><small>'+num(x.raw_shares,0)+'股 · 均價 '+num(x.raw_price)+' · '+x.parts.length+'筆</small></span></summary>'+(h?'<p class="uii-note">直接申報部位 '+num(h.before,0)+' → '+num(h.post,0)+'股 · '+(h.newPosition?"由零增加":pct(h.pct))+'</p>':"")+'<div class="uii-scroll"><table><thead><tr><th>成交價</th><th>股數</th><th>金額</th><th>SEC申報</th></tr></thead><tbody>'+x.parts.map(r=>'<tr><td>'+num(r.raw_price)+'</td><td>'+num(r.raw_shares,0)+'</td><td>'+money(r.amount)+'</td><td><a href="'+esc(r.url)+'" target="_blank" rel="noopener">'+esc(r.filed)+'</a></td></tr>').join("")+'</tbody></table></div></details>'}).join("");
 const flow=g.amount>0&&saleReady?'<div class="uii-flow"><i style="width:'+100*g.buy/g.amount+'%"></i><i style="width:'+100*g.sell/g.amount+'%"></i></div>':"";
 const trend='<div class="uii-research"><div class="uii-cardhead"><h2>跨期間買賣趨勢</h2><span>交易日</span></div><table class="uii-stocktable"><thead><tr><th>期間</th><th>買進</th><th>賣出</th><th>淨額</th></tr></thead><tbody>'+[5,10,20,60,120,240].map(n=>{const x=stockGroup(n);return '<tr><td>'+n+'日</td><td class="uii-inst-up">'+(x.ready?money(x.buy):"—")+'</td><td class="uii-inst-down">'+(x.ready&&saleReady?money(x.sell):"—")+'</td><td>'+(x.ready&&saleReady?signedMoney(x.buy-x.sell):"—")+'</td></tr>'}).join("")+'</tbody></table></div>';
 const owners=new Map();for(const r of g.rows){const k=r.owner_id||r.owner;if(!owners.has(k))owners.set(k,{name:r.owner,role:r.role,buy:0,sell:0,days:new Set(),rows:[]});const x=owners.get(k);x[sideOf(r)]+=r.amount;x.days.add(r.date);x.rows.push(r)}
 const people='<div class="uii-research"><div class="uii-cardhead"><h2>內部人交易統計</h2><span>'+owners.size+'人</span></div>'+[...owners.values()].sort((a,b)=>b.buy+b.sell-a.buy-a.sell).map(x=>'<details class="uii-person"><summary><span><strong>'+esc(x.name)+'</strong><small>'+esc(x.role)+' · '+x.days.size+'交易日</small></span><span><strong class="uii-inst-up">買 '+money(x.buy)+'</strong><small class="uii-inst-down">賣 '+(saleReady?money(x.sell):"—")+'</small></span></summary>'+dailyRows(x.rows).map(r=>'<p class="uii-note">'+esc(r.date)+' · '+(sideOf(r)==="buy"?"買進":"賣出")+' '+money(r.amount)+' · '+num(r.raw_shares,0)+'股</p>').join("")+'</details>').join("")+'</div>';
 const rel=c=>gain(g.price!=null&&c?(g.price/c-1)*100:null);
 return '<section class="uii-card"><div class="uii-cardhead"><h2>個股追蹤</h2></div>'+controls+totals+flow+'<div class="uii-summary"><span>收盤價 '+money(g.price)+'</span><span>買進均價 '+money(g.cost)+'</span><span>賣出均價 '+money(g.sellCost)+'</span><span>相對買進均價 '+rel(g.cost)+'</span><span>相對賣出均價 '+rel(g.sellCost)+'</span></div>'+(g.comparable?chart(prices,g):'<p>尚無可比較的股價資料。</p>')+trend+people+'<div class="uii-research"><div class="uii-cardhead"><h2>按日交易明細</h2><span>'+daily.length+'組</span></div>'+rows+(!rows?'<p>沒有符合條件的已取得交易。</p>':"")+'</div></section>'
}
function chartReadout(p,g,i){
 const v=p[i];if(!v)return "";const rr=g.rows.filter(r=>r.date===v.date);
 return v.date+"　收盤 $"+num(v.close)+["buy","sell"].map(k=>{const q=rr.filter(r=>sideOf(r)===k);const amt=q.reduce((a,r)=>a+r.amount,0),sh=q.reduce((a,r)=>a+r.shares,0);return q.length?"　"+(k==="buy"?"買進 ":"賣出 ")+money(amt)+" · 均價 "+money(sh?amt/sh:null)+" · "+q.length+"筆":""}).join("")+(g.rows.some(r=>r.filed===v.date)?"　SEC申報日":"");
}
function chart(p,g){
 if(p.length<2)return '<p>此期間歷史行情不足。</p>';
 const daily=new Map();
 for(const r of g.rows){const k=r.date+"|"+sideOf(r),v=daily.get(k)||{date:r.date,side:sideOf(r),shares:0,amount:0,n:0};v.shares+=r.shares;v.amount+=r.amount;v.n++;daily.set(k,v)}
 const marks=[...daily.values()].filter(v=>v.shares>0).map(v=>({...v,price:v.amount/v.shares,i:p.findIndex(x=>x.date===v.date)})).filter(v=>v.i>=0);
 const vals=[...p.map(x=>x.close),g.cost,g.sellCost,...marks.map(x=>x.price)].filter(v=>Number.isFinite(v)&&v>0),lo=Math.min(...vals)*.98,hi=Math.max(...vals)*1.02;
 const X=i=>44+i*544/(p.length-1),Y=v=>264-(v-lo)/(hi-lo)*236,idx=chartIndex<0?p.length-1:Math.min(chartIndex,p.length-1);
 const max=Math.max(1,...marks.map(x=>x.amount)),ticks=[...new Set([0,Math.round((p.length-1)/3),Math.round((p.length-1)*2/3),p.length-1])],filing=new Set(g.rows.map(x=>x.filed));
 const color=k=>k==="buy"?"#269b62":"#c53b40";
 return '<div class="uii-chart"><b>股價與內部人成交成本</b><small>藍：收盤價 · 綠：買進 · 紅：賣出 · 虛線：期間加權均價 · 灰線：申報日</small><svg data-price-chart viewBox="0 0 612 310" role="img" aria-label="近'+stockDays+'交易日股價與內部人成本">'+
 [0,1,2,3,4].map(i=>{const v=lo+(hi-lo)*i/4;return '<line x1="44" x2="588" y1="'+Y(v)+'" y2="'+Y(v)+'" stroke="currentColor" opacity=".15"/><text x="38" y="'+Y(v)+'" text-anchor="end" fill="currentColor" font-size="14">'+num(v,0)+'</text>'}).join("")+
 '<polyline fill="none" stroke="#648fcf" stroke-width="2.5" points="'+p.map((v,i)=>X(i)+","+Y(v.close)).join(" ")+'"/>'+
 [["buy",g.cost],["sell",g.sellCost]].filter(x=>Number.isFinite(x[1])&&x[1]>0).map(([k,v])=>'<line x1="44" x2="588" y1="'+Y(v)+'" y2="'+Y(v)+'" stroke="'+color(k)+'" stroke-width="1.5" stroke-dasharray="5 4"/>').join("")+
 p.map((v,i)=>filing.has(v.date)?'<line x1="'+X(i)+'" x2="'+X(i)+'" y1="26" y2="264" stroke="currentColor" opacity=".25" stroke-dasharray="2 5"/>':"").join("")+
 marks.map(v=>'<circle cx="'+X(v.i)+'" cy="'+Y(v.price)+'" r="'+(3+6*Math.sqrt(v.amount/max))+'" fill="'+color(v.side)+'" stroke="white" stroke-width="1"><title>'+esc(v.date+" "+(v.side==="buy"?"買進":"賣出")+" "+money(v.amount)+" · 均價 "+money(v.price))+'</title></circle>').join("")+
 '<line data-crosshair x1="'+X(idx)+'" x2="'+X(idx)+'" y1="26" y2="264" stroke="currentColor" stroke-dasharray="3 3"/>'+
 ticks.map(i=>'<text x="'+X(i)+'" y="291" text-anchor="'+(i===0?'start':i===p.length-1?'end':'middle')+'" fill="currentColor" font-size="14">'+esc(p[i].date.slice(5).replace("-","/"))+'</text>').join("")+
 '</svg><input type="range" data-chart min="0" max="'+(p.length-1)+'" value="'+idx+'" aria-label="查價線"><div class="uii-chart-readout" data-chart-readout>'+esc(chartReadout(p,g,idx))+'</div></div>'
}
let testMetric="mean",testTicker="",testFactor="amount",testDetail=null;
const horizons=[5,10,20,60];
function researchEvents(){
 const m=new Map();
 for(const r of data?.transactions||[]){
  if(!r.research_eligible||!r.owner_id||!r.filed)continue;
  const k=JSON.stringify([r.ticker,r.owner_id,r.filed]);let e=m.get(k);
  if(!e)m.set(k,e={ticker:r.ticker,owner:r.owner,owner_id:r.owner_id,filed:r.filed,amount:0,rows:[]});
  e.amount+=r.amount;e.rows.push(r);
 }
 const events=[...m.values()];
 for(const e of events){
  const p=data.prices?.[e.ticker]||[],i=p.findIndex(x=>x.date>e.filed);
  e.entry=i>=0?p[i]:null;e.outcomes={};
  for(const h of horizons){const q=i>=0?p[i+h-1]:null;e.outcomes[h]=q&&e.entry.open>0?{date:q.date,close:q.close,ret:(q.close/e.entry.open-1)*100}:null}
  const changes=e.rows.map(holdingChange).filter(Boolean).map(x=>x.pct).filter(Number.isFinite);e.holding=changes.length?Math.max(...changes):null;
  const prior=new Date(Date.parse(e.filed)-13*86400000).toISOString().slice(0,10);
  e.cluster=new Set(events.filter(x=>x.ticker===e.ticker&&x.filed>=prior&&x.filed<=e.filed).map(x=>x.owner_id)).size;
  const known=p.filter(x=>x.date<e.filed).slice(-120);e.drawdown=known.length>=20?(1-known.at(-1).close/Math.max(...known.map(x=>x.close)))*100:null;
 }
 return events;
}
function backtest(){
 const all=researchEvents(), events=all.filter(e=>!testTicker||e.ticker===testTicker);
 const defs={amount:[100000,250000,500000,1000000,2000000,5000000,10000000],holding:[5,10,20,50],cluster:[2,3,5],drawdown:[10,20,30]};
 const labels={amount:"買進金額",holding:"單列持股增加率",cluster:"14日公告同步人數",drawdown:"距近120交易日高點跌幅"};
 const metrics=[["mean","平均報酬"],["median","中位數"],["win","勝率"],["n","有效樣本"]];
 const label=t=>testFactor==="amount"?(t>=1e6?"$"+t/1e6+"M":"$"+t/1e3+"K"):t+(testFactor==="cluster"?"人":"%");
 const group=t=>events.filter(e=>e[testFactor]!=null&&e[testFactor]>=t);
 const stats=(g,h)=>{const r=g.map(e=>e.outcomes[h]?.ret).filter(Number.isFinite).sort((a,b)=>a-b),n=r.length;return {n,mean:n?r.reduce((a,b)=>a+b,0)/n:null,median:n?(r[Math.floor((n-1)/2)]+r[Math.floor(n/2)])/2:null,win:n?100*r.filter(x=>x>0).length/n:null}};
 const cell=(t,h,g)=>{const r=stats(g,h),v=r[testMetric];return '<button class="uii-detail-link" data-test-detail="'+t+':'+h+'">'+(testMetric==="n"?num(v,0):v==null?"—":testMetric==="win"?num(v,1)+"%":gain(v))+'</button>'+(testMetric!=="n"&&r.n?'<small>n='+r.n+'</small>':"")};
 const select=(field,values,value)=>'<select data-field="'+field+'">'+values.map(([v,t])=>'<option value="'+esc(v)+'" '+(value===v?"selected":"")+'>'+esc(t)+'</option>').join("")+'</select>';
 let detail="";
 if(testDetail){const [t,h]=testDetail.split(":").map(Number),g=group(t).filter(e=>!h||e.outcomes[h]).sort((a,b)=>b.filed.localeCompare(a.filed));detail='<section class="uii-research" id="uiiEventDetail"><div class="uii-cardhead"><h2>'+esc(label(t))+'以上 · '+(h?h+'日有效樣本':'全部次數')+'</h2><button data-close-detail>收合</button></div>'+g.map(e=>'<details class="uii-person"><summary><span><strong>'+esc(e.ticker)+' · '+esc(e.owner)+'</strong><small>公告 '+esc(e.filed)+'</small></span><span><strong>'+money(e.amount)+'</strong><small>'+(h?gain(e.outcomes[h].ret):e.rows.length+'筆')+'</small></span></summary><div class="uii-person-body"><p>買進日期 '+esc([...new Set(e.rows.map(r=>r.date))].sort().join("、"))+'</p><p>回測進場 '+esc(e.entry?.date||"尚未進場")+' · $'+num(e.entry?.open)+'</p>'+horizons.map(k=>'<p>'+k+'日：'+(e.outcomes[k]?esc(e.outcomes[k].date)+' · $'+num(e.outcomes[k].close)+' · '+gain(e.outcomes[k].ret):"未滿觀察期")+'</p>').join("")+e.rows.map(r=>'<p>'+esc(r.date)+' · '+num(r.raw_shares,0)+'股 · $'+num(r.raw_price)+' · '+money(r.amount)+(String(r.url).startsWith("https://www.sec.gov/")?' · <a href="'+esc(r.url)+'" target="_blank" rel="noopener">SEC</a>':"")+'</p>').join("")+'</div></details>').join("")+(g.length?"":"<p>尚無符合的有效樣本。</p>")+'</section>'}
 return '<section class="uii-card"><div class="uii-cardhead"><h2>買進訊號績效</h2><span>'+esc(data?.start||"—")+' ～ '+esc(data?.as_of||"—")+'</span></div><div class="uii-rank-controls"><label>股票 '+select("testTicker",[["","全部追蹤股票"],...[...new Set(all.map(e=>e.ticker))].sort().map(t=>[t,t])],testTicker)+'</label><label>研究因子 '+select("testFactor",Object.entries(labels),testFactor)+'</label></div><div class="uii-test-tabs">'+metrics.map(([k,t])=>'<button data-test-metric="'+k+'" aria-pressed="'+(testMetric===k)+'">'+t+'</button>').join("")+'</div><div class="uii-scroll uii-matrix"><table><thead><tr><th>門檻</th><th>次數</th>'+horizons.map(h=>'<th>'+h+'日</th>').join("")+'</tr></thead><tbody>'+defs[testFactor].map(t=>{const g=group(t);return '<tr><td><strong>'+label(t)+'</strong></td><td><button class="uii-detail-link" data-test-detail="'+t+':0">'+g.length+'</button></td>'+horizons.map(h=>'<td>'+cell(t,h,g)+'</td>').join("")+'</tr>'}).join("")+'</tbody></table></div><p class="uii-note">點次數或績效可查明細。樣本少僅供探索，門檻重疊。僅使用公告日前已知資料；持股因子取事件內可計算的最大單列增加率，非總持股增加率；跌幅採公告日前最多120個交易日（至少20日）。</p>'+detail+'</section>';
}
function bind(){root.querySelectorAll("[data-inst-side]").forEach(b=>b.onclick=()=>{instSide=b.dataset.instSide;instDesc=true;render()});const instDir=root.querySelector("[data-inst-dir]");if(instDir)instDir.onclick=()=>{instDesc=!instDesc;render()};root.querySelectorAll("[data-stock-side]").forEach(b=>b.onclick=()=>{stockSide=b.dataset.stockSide;render()});root.querySelectorAll("[data-side]").forEach(b=>b.onclick=()=>{tradeSide=b.dataset.side;rankSort=tradeSide==="all"?"amount":tradeSide;rankDesc=true;render()});root.querySelectorAll("[data-sort]").forEach(b=>b.onclick=()=>{rankDesc=rankSort===b.dataset.sort?!rankDesc:true;rankSort=b.dataset.sort;render()});const dir=root.querySelector("[data-sort-dir]");if(dir)dir.onclick=()=>{rankDesc=!rankDesc;render()};if(tab==="institutional"&&extra.institutional?.shards){const d=extra.institutional;root.querySelectorAll("[data-institution-stock]").forEach(el=>{const t=el.dataset.institutionStock;el.ontoggle=()=>{if(el.open){institutionOpen.add(t);loadInstitution(t,d)}else institutionOpen.delete(t)};if(el.open)loadInstitution(t,d)});root.querySelectorAll("[data-institution-retry]").forEach(b=>b.onclick=()=>{const t=b.dataset.institutionRetry;institutionCache.delete(d.updated_at+"|"+t);loadInstitution(t,d)})} const help=root.querySelector("[data-purchase-help]"),panel=root.querySelector("#uiiPurchaseHelp"),helpClose=root.querySelector("[data-purchase-help-close]");if(help&&panel){const toggle=show=>{panel.hidden=!show;help.setAttribute("aria-expanded",String(show))};help.onclick=()=>toggle(panel.hidden);if(helpClose)helpClose.onclick=()=>{toggle(false);help.focus({preventScroll:true})};panel.onkeydown=help.onkeydown=e=>{if(e.key==="Escape"&&!panel.hidden){e.preventDefault();toggle(false);help.focus({preventScroll:true})}};}const retry=root.querySelector("[data-extra-retry]");if(retry)retry.onclick=()=>{extra[tab]=null;render()};root.querySelectorAll("[data-test-detail]").forEach(b=>b.onclick=()=>{if(testDetail!==b.dataset.testDetail)window.StockCrossNav?.recordView();testDetail=b.dataset.testDetail;render();root.querySelector("#uiiEventDetail")?.scrollIntoView({block:"nearest"})});const close=root.querySelector("[data-close-detail]");if(close)close.onclick=()=>{testDetail=null;render()};root.querySelectorAll("[data-test-metric]").forEach(b=>b.onclick=()=>{testMetric=b.dataset.testMetric;render()});root.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{if(tab!==b.dataset.tab)window.StockCrossNav?.recordView();tab=b.dataset.tab;extraTicker="";extraPeriod="";render()});root.querySelectorAll("[data-stock]").forEach(b=>b.onclick=()=>{if(tab!=="stock"||ticker!==b.dataset.stock)window.StockCrossNav?.recordView();ticker=b.dataset.stock;tab="stock";chartIndex=-1;render()});root.querySelectorAll("[data-field]").forEach(el=>el.onchange=()=>{switch(el.dataset.field){case"stockDays":stockDays=+el.value;chartIndex=-1;break;case"stockKind":stockKind=el.value;chartIndex=-1;break;case"stockRole":stockRole=el.value;chartIndex=-1;break;case"extraTicker":extraTicker=el.value;if(tab!=="buybacks")extraPeriod="";break;case"instSort":instSort=el.value;instDesc=true;break;case"extraPeriod":extraPeriod=el.value;break;case"testTicker":testTicker=el.value;testDetail=null;break;case"testFactor":testFactor=el.value;testDetail=null;break;case"rankSort":rankSort=el.value;rankDesc=true;break;case"clusterDays":clusterDays=+el.value;break;case"days":days=+el.value;chartIndex=-1;break;case"threshold":threshold=+el.value;break;case"role":role=el.value;break;case"purchase":purchase=el.value;chartIndex=-1;break;case"search":search=el.value;break;case"ticker":if(ticker!==el.value)window.StockCrossNav?.recordView();ticker=el.value;chartIndex=-1;break}render()});const slider=root.querySelector("[data-chart]");if(slider){slider.oninput=()=>{chartIndex=+slider.value;const g=stockGroup();if(!g)return;const start=windowStart(stockDays),p=(data.prices[g.ticker]||[]).filter(x=>x.date>=start&&x.date<=data.as_of);const v=p[chartIndex];if(!v)return;const x=44+chartIndex*544/(p.length-1),line=root.querySelector("[data-crosshair]");line?.setAttribute("x1",x);line?.setAttribute("x2",x);root.querySelector("[data-chart-readout]").textContent=chartReadout(p,g,chartIndex)};const svg=root.querySelector("[data-price-chart]");let dragging=false;const move=e=>{const b=svg.getBoundingClientRect();slider.value=Math.round(Math.max(0,Math.min(1,((e.clientX-b.left)/b.width*612-44)/544))*Number(slider.max));slider.oninput()};if(svg){svg.onpointerdown=e=>{dragging=true;svg.setPointerCapture?.(e.pointerId);move(e)};svg.onpointermove=e=>{if(dragging)move(e)};svg.onpointerup=svg.onpointercancel=()=>{dragging=false}}}}
async function load(){if(loading||data)return;loading=true;root.textContent="載入內部人交易…";try{let r=await fetch("./data/us_insider/latest.json.gz",{cache:"no-store"});if(r.status===404){r=await fetch("./data/us_insider/latest.json",{cache:"no-store"});if(!r.ok)throw Error(r.status);data=await r.json()}else{if(!r.ok)throw Error(r.status);const b=await r.arrayBuffer(),u=new Uint8Array(b);data=u[0]===31&&u[1]===139?await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream("gzip"))).json():JSON.parse(new TextDecoder().decode(b))}}catch(e){data={coverage_note:"SEC 資料尚未建立或載入失敗，不能判斷增持情況。"}}finally{loading=false;render()}}
window.StockNavInsider={capture:()=>({tab,ticker,days,threshold,search,role,purchase,chartIndex,rankSort,clusterDays,person,testMetric,testTicker,testFactor,testDetail,extraTicker,extraPeriod,tradeSide,rankDesc,stockDays,stockKind,stockRole,stockSide}),restore:v=>{({tab,ticker,days,threshold,search,role,purchase,chartIndex,rankSort,clusterDays,person,testMetric,testTicker,testFactor,testDetail,extraTicker,extraPeriod,tradeSide="buy",rankDesc=true,stockDays=20,stockKind="research_buy",stockRole="",stockSide="all"}=v);if(data)render();}};
new MutationObserver(()=>{if(section.classList.contains("active"))load()}).observe(section,{attributes:true,attributeFilter:["class"]});if(section.classList.contains("active"))load();
})();