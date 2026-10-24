/* 產業資料庫 v2：按需載入小分片、全文搜尋、手機一致字級 */
(()=>{'use strict';
const root=document.querySelector('#reports'),legacy=document.querySelector('#reportList');if(!root||!legacy)return;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>String(s??'').toLowerCase().trim();
const txt=s=>String(s??'').trim();
const url='./data/research_manifest.json';
let manifest=null,rows=[],loaded=new Set(),loading=false,query='',category='全部',rating='全部評等',sector='全部產業',limit=30,exhausted=false;
const cats=['全部','個股研究','產業研究','法說／訪談','週報','市場情報'];
const ratings=['全部評等','上調','下調','初評','維持','未評等'];
const css=`
#researchMergedPanel{margin:14px 0 22px;font-family:inherit;color:inherit;font-size:14px}
#researchMergedPanel *{box-sizing:border-box}
#researchMergedPanel .research-toolbar{display:grid;gap:10px;margin-bottom:12px}
#researchMergedPanel .research-cats,#researchMergedPanel .research-ratings{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;padding:2px 0 6px}
#researchMergedPanel .research-cats::-webkit-scrollbar,#researchMergedPanel .research-ratings::-webkit-scrollbar{display:none}
#researchMergedPanel button,#researchMergedPanel input,#researchMergedPanel select{font:inherit}
#researchMergedPanel .research-filter{flex:0 0 auto;border:1px solid #dce2ea;background:#fff;color:#252b36;border-radius:999px;padding:9px 14px;font-size:14px;font-weight:650;line-height:1.3;white-space:nowrap}
#researchMergedPanel .research-filter.active{background:#2563eb;border-color:#2563eb;color:white}
#researchMergedPanel .research-searchrow{display:flex;gap:8px}
#researchMergedPanel .research-search{min-width:0;flex:1;padding:11px 12px;border:1px solid #dce2ea;border-radius:12px;background:#fff;font-size:14px}
#researchMergedPanel .research-clear{padding:9px 13px;border:1px solid #dce2ea;border-radius:12px;background:#fff;color:#252b36;font-size:14px}
#researchMergedPanel .research-sector{width:100%;padding:11px 12px;border:1px solid #dce2ea;border-radius:12px;background:#fff;color:#252b36;font-size:14px}
#researchMergedPanel .research-meta{font-size:13px;color:#687385;line-height:1.5}
#researchMergedPanel .research-card{border:1px solid #dce2ea;border-radius:14px;background:#fff;padding:14px;margin:10px 0;color:#252b36;overflow-wrap:anywhere}
#researchMergedPanel .research-title{font-size:16px;line-height:1.45;font-weight:750;margin:0 0 6px}
#researchMergedPanel .research-sub{font-size:12px;color:#64748b;line-height:1.55;margin-bottom:9px}
#researchMergedPanel .research-body{font-size:14px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}
#researchMergedPanel .research-expand{margin-top:10px;border:0;background:#eef4ff;color:#1d4ed8;border-radius:9px;padding:8px 12px;font-size:13px;font-weight:700}
#researchMergedPanel .research-date{font-size:14px;font-weight:750;margin:20px 0 10px;color:#344256}
#researchMergedPanel mark{background:#fff1a8;color:inherit}
#researchMergedPanel .research-more{display:block;width:100%;margin:14px auto;padding:12px;border:1px solid #dce2ea;border-radius:12px;background:#fff;color:#252b36;font-size:14px}
#researchMergedPanel .research-loading{font-size:14px;color:#64748b;padding:14px 0}
@media(max-width:700px){
#researchMergedPanel{font-size:14px}
#researchMergedPanel .research-filter{font-size:14px;padding:9px 12px}
#researchMergedPanel .research-title{font-size:16px}
#researchMergedPanel .research-body{font-size:14px}
#researchMergedPanel .research-search,#researchMergedPanel .research-clear,#researchMergedPanel .research-sector{font-size:14px}
}`;
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
const panel=document.createElement('div');panel.id='researchMergedPanel';
panel.innerHTML=`<div class="research-toolbar">
<div class="research-cats">${cats.map(x=>`<button type="button" class="research-filter" data-category="${esc(x)}">${esc(x)}</button>`).join('')}</div>
<div class="research-searchrow"><input id="researchSearch" class="research-search" type="search" placeholder="搜尋公司、代號、券商或全文"><button id="researchClear" class="research-clear" type="button">清除</button></div>
<select id="researchSector" class="research-sector"><option>全部產業</option></select>
<div class="research-ratings">${ratings.map(x=>`<button type="button" class="research-filter" data-rating="${esc(x)}">${esc(x)}</button>`).join('')}</div>
<div id="researchMeta" class="research-meta">準備載入資料…</div>
</div><div id="researchCards"></div><button type="button" id="researchMore" class="research-more" hidden>載入更多</button>`;
legacy.parentNode.insertBefore(panel,legacy);
const list=$('#researchCards'),meta=$('#researchMeta'),more=$('#researchMore');
const bodyOf=r=>[r.full_text,r.full_text_2,r.full_text_3,r.story].map(txt).filter(Boolean).filter((x,i,a)=>a.indexOf(x)===i).join('\n\n')||txt(r.summary)||txt(r.source_name);
const dateOf=r=>txt(r.report_date||r.date||r.group_date||r.received_at).slice(0,10)||'日期未明';
const titleOf=r=>[txt(r.company||r.company_name),txt(r.ticker||r.stock_id)].filter(Boolean).join(' ')||txt(r.source_name)||'研究資料';
const categoryOf=r=>txt(r.category||r.research_category)||'市場情報';
const ratingOf=r=>txt(r.rating_change||r.rating_category)||'未評等';
const sectorOf=r=>txt(r.sector||r.industry)||'';
const hay=r=>norm([r.company,r.company_name,r.ticker,r.stock_id,r.source,r.broker,r.source_name,r.summary,r.story,r.full_text,r.full_text_2,r.full_text_3,r.numbers,r.rating_target].join(' '));
const hi=s=>{let h=esc(s);if(!query)return h;const needle=esc(query).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');try{return h.replace(new RegExp(needle,'gi'),m=>`<mark>${m}</mark>`)}catch{return h}};
function matches(r){return(category==='全部'||categoryOf(r)===category)&&(rating==='全部評等'||ratingOf(r)===rating)&&(sector==='全部產業'||sectorOf(r)===sector)&&(!query||hay(r).includes(norm(query)))}
function setActive(){panel.querySelectorAll('[data-category]').forEach(b=>b.classList.toggle('active',b.dataset.category===category));panel.querySelectorAll('[data-rating]').forEach(b=>b.classList.toggle('active',b.dataset.rating===rating))}
function card(r){const b=bodyOf(r),expanded=!!query&&norm(b).includes(norm(query))&&norm(b.slice(0,300)).indexOf(norm(query))<0;const short=b.length>300&&!expanded;return `<article class="research-card" data-research-id="${esc(r.id)}"><div class="research-title">${hi(titleOf(r))}</div><div class="research-sub">${esc(dateOf(r))}　${esc(r.source||r.broker||'')}　${esc(r.type||'')}　${esc(categoryOf(r))}</div><div class="research-body">${hi(short?b.slice(0,300)+'…':b)}</div>${b.length>300?`<button type="button" class="research-expand" aria-expanded="${expanded?'true':'false'}">${expanded?'收合內容 ▲':'展開全文 ▼'}</button>`:''}</article>`}
function render(){setActive();const filtered=rows.filter(matches).sort((a,b)=>dateOf(b).localeCompare(dateOf(a)));const visible=filtered.slice(0,limit);let last='';list.innerHTML=visible.map(r=>{const d=dateOf(r);let header='';if(d!==last){header=`<div class="research-date">${esc(d)}</div>`;last=d}return header+card(r)}).join('')||'<div class="research-loading">目前沒有符合條件的資料</div>';meta.textContent=`符合 ${filtered.length} 筆｜已載入 ${rows.length} 筆${manifest?'｜資料庫共 '+(manifest.total||manifest.total_items||'?')+' 筆':''}`;more.hidden=exhausted&&filtered.length<=limit;more.textContent=loading?'載入中…':filtered.length>limit?'顯示更多':'繼續載入歷史資料'}
async function getJSON(path){const r=await fetch(path,{cache:'no-cache'});if(!r.ok)throw Error(`${r.status} ${path}`);return r.json()}
function shards(){const s=manifest?.shards||manifest?.files||[];return s.map(x=>typeof x==='string'?x:(x.path||x.file||x.url)).filter(Boolean)}
async function loadNext(){if(loading||exhausted)return;loading=true;more.disabled=true;try{const all=shards();const next=all.find(x=>!loaded.has(x));if(!next){exhausted=true;return}loaded.add(next);const data=await getJSON(next.startsWith('./')||next.startsWith('/')?next:'./'+next);const batch=Array.isArray(data)?data:(data.items||[]);rows.push(...batch);if(loaded.size>=all.length)exhausted=true}catch(e){console.error('research shard load failed',e);meta.textContent='資料載入失敗：'+e.message}finally{loading=false;more.disabled=false;render()}}
async function loadAllForSearch(){if(!query)return;const all=shards();for(let i=0;i<all.length;i++){if(!query)return;if(exhausted)break;await loadNext();if(i%4===3)await new Promise(r=>setTimeout(r,0))}}
async function init(){try{manifest=await getJSON(url);await loadNext()}catch(e){meta.textContent='資料庫載入失敗：'+e.message;console.error(e)}}
function sync(){const active=root.classList.contains('active');const ratingsPanel=$('#twRatingsPanel');const isRatings=ratingsPanel&&!ratingsPanel.hidden;panel.hidden=!active||isRatings;if(active&&!isRatings){legacy.hidden=true;if(!manifest)init()}else if(isRatings){legacy.hidden=true}else{legacy.hidden=false}}
panel.querySelectorAll('[data-category]').forEach(b=>b.addEventListener('click',()=>{category=b.dataset.category;limit=30;render()}));
panel.querySelectorAll('[data-rating]').forEach(b=>b.addEventListener('click',()=>{rating=b.dataset.rating;limit=30;render()}));
$('#researchSector').addEventListener('change',e=>{sector=e.target.value;limit=30;render()});
let searchTimer;$('#researchSearch').addEventListener('input',e=>{query=e.target.value.trim();limit=30;clearTimeout(searchTimer);searchTimer=setTimeout(async()=>{render();if(query)await loadAllForSearch()},250)});
$('#researchClear').addEventListener('click',()=>{$('#researchSearch').value='';query='';limit=30;render()});
more.addEventListener('click',async()=>{const n=rows.filter(matches).length;if(n>limit){limit+=30;render()}else await loadNext()});
list.addEventListener('click',e=>{const b=e.target.closest('.research-expand');if(!b)return;const cardEl=b.closest('.research-card'),r=rows.find(x=>String(x.id)===cardEl.dataset.researchId);if(!r)return;const expanded=b.getAttribute('aria-expanded')==='true';cardEl.querySelector('.research-body').innerHTML=hi(expanded?bodyOf(r).slice(0,300)+'…':bodyOf(r));b.setAttribute('aria-expanded',String(!expanded));b.textContent=expanded?'展開全文 ▼':'收合內容 ▲'});
const observer=new MutationObserver(sync);observer.observe(root,{attributes:true,attributeFilter:['class']});const ratingsPanel=$('#twRatingsPanel');if(ratingsPanel)observer.observe(ratingsPanel,{attributes:true,attributeFilter:['hidden']});
if($('#reportModeReports'))$('#reportModeReports').textContent='資料庫';if(root.classList.contains('active'))sync();
})();
