/* Additive stock links. No data fetchers, financial calculations or notifications. */
(()=>{'use strict';
const labels={heatmap:'熱力圖',etfFlow:'ETF',reports:'產業資料庫',selfReports:'財報追蹤',chips:'籌碼日報'};
const destinations=[['chart','日K／走勢'],['research','研究報告'],['reports','財報'],['self','自結'],['upcoming','即將公布'],['etf','ETF動向']];
const snapshots=new Map();let sequence=0,token=0,busy=false,scheduled=false,currentContext=null,restoring=false;const backStack=[];
const activePage=()=>document.querySelector('.page.active')?.id||'home';
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function pageState(){const id=activePage();return {page:id,y:window.scrollY,etf:id==='etfFlow'?window.StockNavETF?.capture():null,research:id==='reports'?window.StockNavResearch?.capture():null,earnings:id==='selfReports'?window.StockNavEarnings?.capture():null,self:id==='selfReports'?window.StockNavSelf?.capture():null,chart:window.StockNavChart?.capture(),details:[...document.querySelectorAll(`#${id} details`)].map(d=>d.open),inputs:[...document.querySelectorAll(`#${id} input[id],#${id} select[id]`)].map(el=>({id:el.id,value:el.value,checked:el.checked})),scrolls:[...document.querySelectorAll(`#${id} .ef-table-scroll,#stockDetailBody,.stock-detail-sheet`)].map(el=>({el,left:el.scrollLeft,top:el.scrollTop})),focus:document.activeElement};}
function saveCurrent(){let id=history.state?.stockNavEntry;if(!id){id='stock-nav-'+(++sequence);history.replaceState({...history.state,stockNavEntry:id},'');}snapshots.set(id,pageState());return id;}
function notice(context,error=''){
 currentContext=context||null;
 document.querySelectorAll('.stock-cross-return').forEach(el=>el.remove());
 updateBackButton();if(!context)return;
 const modal=document.getElementById('stockDetailModal');
 const inside=modal?.classList.contains('open');
 const page=document.getElementById(activePage());if(!page)return;
 // Existing company cards already contain a menu; avoid repeating it above them.
 if(activePage()==='etfFlow'&&!inside&&!error){mount();return;}
 const bar=document.createElement('div');bar.className='stock-cross-return';
 bar.innerHTML=`<span class="stock-cross-company">${esc(context.code)} <strong>${esc(context.name)}</strong></span><span data-stock-nav-code="${esc(context.code)}" data-stock-nav-name="${esc(context.name)}"></span>${error?`<span class="stock-cross-status" role="status">${esc(error)}</span><button type="button" data-stock-retry>重試</button>`:''}`;
 if(inside){if(!modal.querySelector('[data-stock-nav-code]'))modal.querySelector('.stock-detail-head')?.after(bar);}
 else {const hero=page.querySelector(':scope>.hero');if(hero)hero.append(bar);else page.prepend(bar);}
}
function updateBackButton(){const b=document.getElementById('backHomeBtn');if(!b)return;const modalOpen=document.getElementById('stockDetailModal')?.classList.contains('open'),has=backStack.length>0||modalOpen;const frame=backStack.at(-1);b.classList.toggle('show',has||activePage()!=='home');b.setAttribute('aria-label',has?'返回上一頁':'返回總覽');b.title=frame?'返回'+(frame.context?.fromLabel||labels[frame.saved.page]||'上一頁'):modalOpen?'關閉個股資訊，返回原頁':'返回總覽';const spans=b.querySelectorAll('span'),label=has?'上一頁':'總覽';if(spans.length){const span=spans[spans.length-1];if(span.textContent!==label)span.textContent=label;}else if(b.textContent!=='← '+label)b.textContent='← '+label;}
async function goBack(){
 if(restoring)return;if(document.getElementById('stockDetailModal')?.classList.contains('open')&&currentContext?.kind!=='chart'){document.getElementById('stockDetailClose')?.click();updateBackButton();return;}const frame=backStack.pop();
 if(!frame){if(activePage()!=='home'&&typeof window.page==='function'){restoring=true;window.page('home');restoring=false;notice(null);}return;}
 ++token;busy=false;restoring=true;
 try{window.StockNavChart?.hide();
 // Set the page marker before calling the existing router, so its history
 // wrapper does not create another forward entry while restoring a source.
 history.replaceState({...history.state,twPage:frame.saved.page,stockNavEntry:frame.from,stockNavContext:frame.parentContext||null},'', '#'+frame.saved.page);
 if(typeof window.page==='function')window.page(frame.saved.page);
 await restore(frame.saved,frame.parentContext);
 }finally{restoring=false;updateBackButton();}
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
 const from=saveCurrent();const source=snapshots.get(from);const parentContext=currentContext;const context={kind,code,name,from,fromLabel:labels[source.page]||'來源頁'};
 backStack.push({from,saved:source,parentContext,context});
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
  const code=host.dataset.stockNavCode;if(!/^\d{4,6}$/.test(code)||host.querySelector('.stock-cross-menu'))return;
  host.querySelector('.stock-cross-links')?.remove();
  const menu=document.createElement('details');menu.className='stock-cross-menu';
  const trigger=document.createElement('summary');trigger.textContent='相關資訊';trigger.setAttribute('aria-label',code+' 相關資訊');menu.append(trigger);
  const nav=document.createElement('nav');nav.className='stock-cross-options';nav.setAttribute('aria-label',code+' 跨頁資訊');
  for(const [kind,label]of destinations){const a=document.createElement('a');a.href='#'+(kind==='research'?'reports':kind==='etf'?'etfFlow':kind==='chart'?activePage():'selfReports');a.textContent=label;a.dataset.stockDestination=kind;a.dataset.stockCode=code;a.dataset.stockName=host.dataset.stockNavName||'';nav.append(a);}menu.append(nav);host.append(menu);
  if(!host.closest('.stock-cross-return')){
   const chart=host.closest('#stockDetailBody');
   if(chart){const header=document.querySelector('#stockDetailModal .stock-detail-head');if(header){header.querySelector('.stock-cross-title-menu')?.remove();host.classList.add('stock-cross-title-menu');header.insertBefore(host,header.querySelector('.stock-detail-close'));}}
   else{const card=host.closest('.ef-card');if(card){card.classList.add('stock-cross-card');host.classList.add('stock-cross-card-menu');}}
  }
 });updateBackButton();
}
document.addEventListener('click',e=>{
 const back=e.target.closest('#backHomeBtn,[data-stock-return]');if(back){e.preventDefault();e.stopImmediatePropagation();goBack();return;}
 const retry=e.target.closest('[data-stock-retry]');if(retry){const c=history.state?.stockNavContext;if(c){notice(c,'正在重試…');destination(c.kind,c.code).then(()=>{notice(c);mount();}).catch(err=>notice(c,'資料暫時無法載入：'+err.message));}return;}
 const link=e.target.closest('[data-stock-destination]');if(!link||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();link.closest('details')?.removeAttribute('open');navigate(link.dataset.stockDestination,link.dataset.stockCode,link.dataset.stockName);
},true);
window.addEventListener('popstate',e=>{
 busy=false;const saved=snapshots.get(e.state?.stockNavEntry);
 if(saved){const i=backStack.findLastIndex(f=>f.from===e.state?.stockNavEntry);if(i>=0)backStack.splice(i);restore(saved,e.state?.stockNavContext||null);}
 else if(backStack.length){const target=e.state?.twPage||activePage(),i=backStack.findLastIndex(f=>f.saved.page===target);if(i>=0){const f=backStack[i];backStack.splice(i);restore(f.saved,f.parentContext);}else{++token;notice(null);}}
 else{++token;window.StockNavChart?.hide();notice(null);}updateBackButton();
});
// Regular page changes also get a return snapshot. Financial rendering may
// replace history.state; the independent stack keeps the back action available.
if(typeof window.page==='function'){const original=window.page;window.page=function(id){
 if(!busy&&!restoring&&id!==activePage()&&document.getElementById(id)){
  const from=saveCurrent(),saved=snapshots.get(from);backStack.push({from,saved,parentContext:currentContext,context:null});currentContext=null;
 }
 const result=original.apply(this,arguments);if(!busy&&!restoring)notice(currentContext);return result;
};}
new MutationObserver(()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;mount();const bar=document.querySelector('.stock-cross-return');if(currentContext&&!bar&&activePage()!=='etfFlow'&&!document.getElementById('stockDetailModal')?.classList.contains('open'))notice(currentContext);});}).observe(document.body,{childList:true,subtree:true});
document.addEventListener('click',e=>{if(e.target.closest('#stockDetailClose'))setTimeout(updateBackButton,0);document.querySelectorAll('.stock-cross-menu[open]').forEach(menu=>{if(!menu.contains(e.target))menu.open=false;});});
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.stock-cross-menu[open]').forEach(m=>m.open=false);});
const style=document.createElement('style');style.textContent=`
.stock-cross-menu{position:relative;font:13px/1.4 -apple-system,BlinkMacSystemFont,sans-serif;color:#53677f;margin:0}
.stock-cross-menu>summary{display:flex;gap:7px;align-items:center;justify-content:center;min-height:40px;padding:7px 11px;border:1px solid #dce3ed;border-radius:20px;background:#f7f9fc;cursor:pointer;list-style:none;white-space:nowrap;font-weight:500}
.stock-cross-menu>summary:after{content:'⌄';font-size:14px}.stock-cross-menu>summary::-webkit-details-marker{display:none}
.stock-cross-menu[open]>summary{background:#eaf0f8;border-color:#aebed2}
.stock-cross-options{display:block;flex:none;gap:0;overflow-x:hidden;overflow-y:auto;max-height:min(70vh,360px);max-width:calc(100vw - 28px);position:absolute;right:0;top:calc(100% + 6px);z-index:15000;min-width:155px;padding:5px;background:#fff;border:1px solid #dce3ed;border-radius:13px;box-shadow:0 10px 30px #17263b22}
.stock-cross-options a{display:flex;align-items:center;min-height:44px;padding:10px 12px;color:#304b6b;text-decoration:none;border-radius:8px;font-size:14px;white-space:nowrap}
.stock-cross-options a:hover,.stock-cross-options a:focus-visible{background:#edf2f8}
.stock-cross-return{display:flex;align-items:center;justify-content:flex-start;gap:12px;flex-wrap:wrap;margin:8px 0 0;padding:0;color:#64748b;font-size:13px;background:transparent;border:0;box-shadow:none}
.stock-cross-company{font-size:13px;font-weight:400}.stock-cross-company strong{color:#26344a;font-weight:600}
.stock-cross-status{flex-basis:100%;font-size:12px}.stock-cross-return>button{font:inherit;border:1px solid #dce3ed;border-radius:9px;background:#fff;color:#304b6b;min-height:40px;padding:7px 12px}
.stock-cross-card{position:relative!important}.stock-cross-card>h3{padding-right:112px;min-height:40px;display:flex;align-items:center;margin-bottom:12px!important}
.stock-cross-card-menu{position:absolute;right:18px;top:18px;z-index:12}
.stock-cross-title-menu{flex-shrink:0;margin-left:auto;margin-right:10px}.stock-detail-head .stock-detail-title{min-width:0;flex:1}.stock-detail-head .stock-detail-close{flex-shrink:0}
.stock-detail-sheet>.stock-cross-return{margin:5px 14px}.stock-detail-sheet{isolation:isolate}#backHomeBtn{z-index:12050!important}#stockDetailModal.open~#backHomeBtn{z-index:12050!important}
html[data-theme=dark] .stock-cross-menu{color:#b7c6d9}html[data-theme=dark] .stock-cross-menu>summary{background:#202d3f;border-color:#42516a}html[data-theme=dark] .stock-cross-options{background:#1b2738;border-color:#42516a}html[data-theme=dark] .stock-cross-options a{color:#d7e3f3}html[data-theme=dark] .stock-cross-options a:hover{background:#30405a}html[data-theme=dark] .stock-cross-company strong{color:#dbe5f1}
@media(max-width:400px){.stock-cross-title-menu{margin-right:6px}.stock-cross-menu>summary{padding:6px 9px;font-size:12px}.stock-cross-card-menu{right:14px;top:14px}.stock-cross-card>h3{padding-right:105px}}
`;
document.head.append(style);mount();
window.StockCrossNav={navigate,back:goBack};
})();


