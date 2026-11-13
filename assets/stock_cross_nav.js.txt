/* Additive stock links. No data fetchers, financial calculations or notifications. */
(()=>{'use strict';
const labels={heatmap:'熱力圖',etfFlow:'ETF',reports:'產業資料庫',selfReports:'財報追蹤',chips:'籌碼日報'};
const destinations=[['chart','日K／走勢'],['research','研究報告'],['reports','財報'],['self','自結'],['upcoming','即將公布'],['etf','ETF動向']];
const snapshots=new Map();let sequence=0,token=0,busy=false,scheduled=false;
const activePage=()=>document.querySelector('.page.active')?.id||'home';
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function pageState(){const id=activePage();return {page:id,y:window.scrollY,etf:id==='etfFlow'?window.StockNavETF?.capture():null,research:id==='reports'?window.StockNavResearch?.capture():null,earnings:id==='selfReports'?window.StockNavEarnings?.capture():null,self:id==='selfReports'?window.StockNavSelf?.capture():null,chart:window.StockNavChart?.capture(),details:[...document.querySelectorAll(`#${id} details`)].map(d=>d.open),inputs:[...document.querySelectorAll(`#${id} input[id],#${id} select[id]`)].map(el=>({id:el.id,value:el.value,checked:el.checked})),scrolls:[...document.querySelectorAll(`#${id} .ef-table-scroll,#stockDetailBody,.stock-detail-sheet`)].map(el=>({el,left:el.scrollLeft,top:el.scrollTop})),focus:document.activeElement};}
function saveCurrent(){let id=history.state?.stockNavEntry;if(!id){id='stock-nav-'+(++sequence);history.replaceState({...history.state,stockNavEntry:id},'');}snapshots.set(id,pageState());return id;}
function notice(context,error=''){
 document.querySelectorAll('.stock-cross-return').forEach(el=>el.remove());
 if(!context)return;
 const page=document.getElementById(activePage());if(!page)return;
 const bar=document.createElement('div');bar.className='stock-cross-return';bar.setAttribute('role','region');bar.setAttribute('aria-label','跨頁個股查詢');
 bar.innerHTML=`<button type="button" data-stock-return>← 返回${esc(context.fromLabel||'來源頁')}</button><span>目前個股：<strong>${esc(context.code)} ${esc(context.name)}</strong></span><span class="stock-cross-status" role="status">${esc(error)}</span>${error?'<button type="button" data-stock-retry>重試</button>':''}`;
 const links=document.createElement('div');links.dataset.stockNavCode=context.code;links.dataset.stockNavName=context.name;links.className='stock-cross-context-links';bar.append(links);
 const modal=document.getElementById('stockDetailModal');if(modal?.classList.contains('open'))modal.querySelector('.stock-detail-head')?.after(bar);else{const hero=page.querySelector(':scope>.hero');if(hero)hero.after(bar);else page.prepend(bar);}
}
async function destination(kind,code,requestToken=token){
 const id=kind==='chart'?activePage():kind==='research'?'reports':kind==='etf'?'etfFlow':'selfReports';
 if(kind!=='chart'){if(typeof window.page!=='function')throw Error('頁面導覽尚未載入');window.page(id);}
 if(kind==='research')document.getElementById('reportModeReports')?.click();
 const api=kind==='chart'?'StockNavChart':kind==='research'?'StockNavResearch':kind==='etf'?'StockNavETF':'StockNavEarnings';
 for(let i=0;!window[api]&&i<100;i++)await wait(100);
 if(requestToken!==token)return;if(!window[api])throw Error('此分頁尚未載入，請重試');
 if(kind==='research'||kind==='etf'||kind==='chart')await window[api].open(code);
 else await window[api].open(code,kind);
}
async function navigate(kind,code,name){
 if(busy||!/^\d{4,6}$/.test(code))return;busy=true;const thisToken=++token;
 const from=saveCurrent();const source=snapshots.get(from);const context={kind,code,name,from,fromLabel:labels[source.page]||'來源頁'};
 window.StockNavChart?.hide();
 try{
  const oldURL=location.href;
  // The site's existing page() owns history. Add one entry only when the
  // destination is the current page (e.g. opening a chart over ETF content).
  const target=kind==='chart'?source.page:kind==='research'?'reports':kind==='etf'?'etfFlow':'selfReports';
  if(target===source.page)history.pushState({twPage:target},'',oldURL);
  const destinationId='stock-nav-'+(++sequence);
  const promise=destination(kind,code);
  history.replaceState({...history.state,stockNavEntry:destinationId,stockNavContext:context},'');
  notice(context,'正在載入…');await promise;if(thisToken!==token)return;
  snapshots.set(destinationId,pageState());notice(context);mount();
  if(kind!=='chart'){const bar=document.querySelector('.stock-cross-return');const offset=document.querySelector('body>header')?.getBoundingClientRect().height||0;if(bar)window.scrollTo({top:Math.max(0,window.scrollY+bar.getBoundingClientRect().top-offset-12),behavior:'instant'});}
 }catch(e){if(thisToken===token)notice(context,'資料暫時無法載入：'+e.message);}finally{busy=false;}
}
async function restore(saved,context){
 const thisToken=++token;window.StockNavChart?.hide();
 try{
  if(saved.etf)await window.StockNavETF?.restore(saved.etf);
  if(saved.research)await window.StockNavResearch?.restore(saved.research);
  if(saved.earnings)await window.StockNavEarnings?.restore(saved.earnings);
  if(saved.self)await window.StockNavSelf?.restore(saved.self);
  if(thisToken!==token)return;
  if(saved.chart)await window.StockNavChart?.restore(saved.chart);
  if(thisToken!==token)return;notice(context);mount();
  const apply=()=>{if(thisToken!==token)return;document.querySelectorAll(`#${saved.page} details`).forEach((d,i)=>{if(saved.details[i]!==undefined)d.open=saved.details[i];});saved.inputs?.forEach(v=>{const el=document.getElementById(v.id);if(el){el.value=v.value;if(v.checked!==undefined)el.checked=v.checked;}});saved.scrolls.forEach(v=>{if(v.el.isConnected){v.el.scrollLeft=v.left;v.el.scrollTop=v.top;}});if(saved.focus?.isConnected)saved.focus.focus({preventScroll:true});window.scrollTo({top:saved.y,behavior:'instant'});};
  requestAnimationFrame(()=>requestAnimationFrame(apply));setTimeout(apply,220);setTimeout(apply,550);
 }catch(e){notice(context,'來源頁還原失敗，請重試：'+e.message);}
}
function mount(){
 document.querySelectorAll('[data-stock-nav-code]').forEach(host=>{
  const code=host.dataset.stockNavCode;if(!/^\d{4,6}$/.test(code)||host.querySelector('.stock-cross-links'))return;
  const nav=document.createElement('nav');nav.className='stock-cross-links';nav.setAttribute('aria-label',code+' 跨頁資訊');
  for(const [kind,label]of destinations){const a=document.createElement('a');a.href='#'+(kind==='research'?'reports':kind==='etf'?'etfFlow':kind==='chart'?activePage():'selfReports');a.textContent=label;a.dataset.stockDestination=kind;a.dataset.stockCode=code;a.dataset.stockName=host.dataset.stockNavName||'';nav.append(a);}host.append(nav);
 });
}
document.addEventListener('click',e=>{
 const back=e.target.closest('[data-stock-return]');if(back){e.preventDefault();if(history.state?.stockNavContext?.from)history.back();return;}
 const retry=e.target.closest('[data-stock-retry]');if(retry){const c=history.state?.stockNavContext;if(c){notice(c,'正在重試…');destination(c.kind,c.code).then(()=>{notice(c);mount();}).catch(err=>notice(c,'資料暫時無法載入：'+err.message));}return;}
 const link=e.target.closest('[data-stock-destination]');if(!link||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();navigate(link.dataset.stockDestination,link.dataset.stockCode,link.dataset.stockName);
});
window.addEventListener('popstate',e=>{busy=false;const saved=snapshots.get(e.state?.stockNavEntry);if(saved)restore(saved,e.state?.stockNavContext);else{++token;window.StockNavChart?.hide();notice(null);}});
new MutationObserver(()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;mount();const context=history.state?.stockNavContext,bar=document.querySelector('.stock-cross-return');if(!context&&bar)notice(null);else if(context&&(!bar||(bar.closest('#stockDetailModal')&&!document.getElementById('stockDetailModal')?.classList.contains('open'))))notice(context);});}).observe(document.body,{childList:true,subtree:true});
const style=document.createElement('style');style.textContent=`.stock-cross-links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:10px 0 14px}.stock-cross-links a,.stock-cross-return button{font:inherit;font-size:13px;min-height:42px;display:flex;align-items:center;justify-content:center;padding:8px 6px;border:1px solid #dce3ed;border-radius:9px;background:#fff;color:#285d92;text-decoration:none;text-align:center;overflow-wrap:anywhere}.stock-cross-return{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px;margin:12px 0;background:#edf3fa;border:1px solid #d5e1ef;border-radius:12px;color:#26344a;font-size:13px}.stock-cross-return button{cursor:pointer;flex-shrink:0}.stock-cross-context-links{flex-basis:100%}.stock-cross-context-links .stock-cross-links{margin:0}.stock-cross-status:empty{display:none}.stock-cross-status{flex-basis:100%;color:inherit}.stock-detail-sheet>.stock-cross-return{margin:8px 14px}.stock-detail-sheet .stock-cross-links{margin:0 0 12px}html[data-theme=dark] .stock-cross-links a,html[data-theme=dark] .stock-cross-return button{background:#1b2532;border-color:#374354;color:#a6c7ed}html[data-theme=dark] .stock-cross-return{background:#1b293c;border-color:#374354;color:#dbe5f1}@media(min-width:800px){.stock-cross-links{display:flex;flex-wrap:wrap}.stock-cross-links a{padding:8px 14px}}`;
document.head.append(style);mount();
window.StockCrossNav={navigate};
})();
