/* 產業資料庫：完整 LINE 研究＋原始券商報告（不更動既有評等／EPS 邏輯） */
(()=>{'use strict';
const $=s=>document.querySelector(s), root=$('#reports'), original=$('#reportList');
if(!root||!original)return;
const labels=[['all','全部'],['個股研究','個股研究'],['產業研究','產業研究'],['法說／訪談','法說／訪談'],['週報','週報'],['市場情報','市場情報']];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=v=>String(v??'').normalize('NFKC').toLocaleLowerCase();
const panel=document.createElement('div');panel.id='researchMergedPanel';panel.hidden=true;
panel.innerHTML=`<div class="research-toolbar"><div id="researchCategories" class="research-categories"></div><div class="research-controls"><div class="research-search"><input id="researchSearch" type="search" placeholder="搜尋公司、代號、券商或全文" aria-label="研究資料全文搜尋"><button id="researchClear" type="button">清除</button></div><select id="researchIndustry"><option value="">全部產業</option></select></div><div id="researchRatings" class="research-categories" hidden></div><div id="researchCount" class="research-count"></div></div><div id="researchItems"></div><button id="researchMore" type="button" hidden>載入更多</button><details class="research-legacy"><summary>原始券商報告完整檢視（保留評等、目標價與 EPS 資料）</summary><div id="researchLegacySlot"></div></details>`;
original.before(panel);
const slot=$('#researchLegacySlot');slot.appendChild(original);
const style=document.createElement('style');style.textContent=`
#researchMergedPanel{max-width:100%;min-width:0}#researchMergedPanel .research-categories{display:flex;gap:8px;overflow-x:auto;white-space:nowrap;padding:6px 0 10px;-webkit-overflow-scrolling:touch}
#researchMergedPanel button,#researchMergedPanel select{font:inherit;cursor:pointer}#researchMergedPanel .research-categories button{border:1px solid var(--line,#cbd5e1);border-radius:20px;padding:8px 14px;background:var(--card,#fff);color:var(--ink,#111827);flex-shrink:0}
#researchMergedPanel .research-categories button.active{background:#2563eb;color:white;border-color:#2563eb}
#researchMergedPanel .research-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}#researchMergedPanel .research-search{display:flex;flex:1 1 260px;gap:8px}
#researchMergedPanel input,#researchMergedPanel select{min-width:0;border:1px solid var(--line,#cbd5e1);border-radius:10px;padding:10px;background:var(--card,#fff);color:var(--ink,#111827)}#researchMergedPanel input{flex:1}
#researchMergedPanel .research-search button,#researchMore{border:1px solid var(--line,#cbd5e1);border-radius:10px;padding:10px 14px;background:var(--card,#fff);color:var(--ink,#111827)}
#researchMergedPanel .research-count{font-size:13px;color:var(--muted,#64748b);margin:12px 0}#researchMergedPanel .research-day{font-weight:800;margin:22px 0 9px;border-bottom:1px solid var(--line,#cbd5e1);padding-bottom:7px}
#researchMergedPanel .research-card{padding:16px;margin:10px 0;border:1px solid var(--line,#cbd5e1);border-radius:12px;background:var(--card,#fff);overflow-wrap:anywhere}
#researchMergedPanel .research-title{font-size:16px;font-weight:750;margin:5px 0}#researchMergedPanel .research-meta{font-size:12px;color:var(--muted,#64748b)}
#researchMergedPanel .research-body{white-space:pre-wrap;line-height:1.7;font-size:14px;margin-top:10px}#researchMergedPanel .research-expand{border:0;background:transparent;color:#2563eb;font-weight:700;padding:9px 0;cursor:pointer}
#researchMergedPanel mark{background:#fde68a;color:#111827}#researchMergedPanel .research-tag{display:inline-block;border-radius:6px;background:#e2e8f0;color:#334155;padding:2px 7px;margin-right:5px}
#researchMergedPanel .research-legacy{margin:24px 0}#researchMergedPanel .research-legacy>summary{cursor:pointer;font-weight:700;padding:12px;background:var(--card,#fff);border:1px solid var(--line,#cbd5e1);border-radius:10px}
#researchMergedPanel .research-legacy #reportList{margin-top:12px}#researchMore{display:block;margin:18px auto}#researchMore[hidden]{display:none}
@media(max-width:700px){#researchMergedPanel .research-controls{display:block}#researchMergedPanel .research-search{margin-bottom:9px}#researchMergedPanel #researchIndustry{width:100%}}
`;document.head.append(style);
const cats=$('#researchCategories'),ratings=$('#researchRatings'),list=$('#researchItems'),count=$('#researchCount'),more=$('#researchMore');
cats.innerHTML=labels.map(([v,l])=>`<button type="button" data-cat="${esc(v)}">${l}</button>`).join('');
const ratingOptions=[['all','全部評等'],['upgrade','上調'],['downgrade','下調'],['initiate','初評'],['maintain','維持'],['none','未評等']];
ratings.innerHTML=ratingOptions.map(([v,l])=>`<button type="button" data-rating="${v}">${l}</button>`).join('');
let rows=[],cat='all',rating='all',industry='',query='',limit=60,loaded=false,loading=null;
function ratingOf(r){if(r.source_kind!=='broker')return 'none';return ['upgrade','downgrade','initiate','maintain'].includes(r.action)?r.action:'none';}
function bodyOf(r){if(r.source_kind==='broker')return [r.title,...(Array.isArray(r.summary)?r.summary:[]),r.detail].filter(Boolean).join('\n');
return ['story','full_text','full_text_2','full_text_3','revenue','eps','inventory','utilization','guidance','trend','rating_target','numbers','dividend_current','dividend_next','dividend_policy'].map(k=>r[k]).filter(v=>v!=null&&String(v).trim()).join('\n\n');}
function searchOf(r){return norm([r.company,r.name,r.ticker,r.source,r.broker,r.industry,r.category,r.original_type,r.title,bodyOf(r)].join(' '));}
function hi(v){const s=String(v??'');if(!query)return esc(s);const n=norm(query),lower=norm(s);if(!n)return esc(s);let result='',pos=0,found;while((found=lower.indexOf(n,pos))!==-1){result+=esc(s.slice(pos,found))+'<mark>'+esc(s.slice(found,found+n.length))+'</mark>';pos=found+n.length;if(result.length>1500000)break;}return result+esc(s.slice(pos));}
function match(r){return (cat==='all'||r.category===cat)&&(!industry||r.industry===industry)&&(cat!=='個股研究'||rating==='all'||ratingOf(r)===rating)&&(!query||searchOf(r).includes(norm(query)));}
function card(r){const body=bodyOf(r),autoExpand=!!query&&norm(body).includes(norm(query)),short=body.length>300&&!autoExpand,preview=short?body.slice(0,300)+'…':body;
const name=r.company||r.name||r.title||'未標示公司';const link=r.source_kind==='broker'&&r.id?`<a href="?page=reports&report=${encodeURIComponent(r.id)}" class="research-original-link">查看原始券商報告</a>`:'';
return `<article class="research-card" data-research-id="${esc(r.id)}"><div class="research-meta"><span class="research-tag">${esc(r.source_kind==='broker'?'券商報告':'LINE資料庫')}</span><span class="research-tag">${esc(r.original_type||r.category)}</span>${r.unverified?'<span class="research-tag">未經證實的小作文</span>':''} ${hi(r.source||r.broker||'')}　${hi(r.industry||'')} ${r.date_source==='sheet'?'　（Excel日期）':''}</div><div class="research-title">${hi(name)} ${hi(r.ticker||'')}</div><div class="research-body">${hi(preview)}</div>${short?'<button type="button" class="research-expand" aria-expanded="false">展開全文 ▼</button>':(body.length>300?'<button type="button" class="research-expand" aria-expanded="true">收合內容 ▲</button>':'')}${link}</article>`;}
function render(){cats.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.cat===cat));ratings.hidden=cat!=='個股研究';ratings.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.rating===rating));
const filtered=rows.filter(match);count.textContent=`符合 ${filtered.length} 筆｜資料庫共 ${rows.length} 筆`;let html='',day='';for(const r of filtered.slice(0,limit)){if(r.date!==day){day=r.date;html+=`<div class="research-day">${esc(day||'日期未提供')}</div>`;}html+=card(r);}list.innerHTML=html||(loaded?'<div class="card">沒有符合條件的資料</div>':'<div class="card">載入中…</div>');more.hidden=filtered.length<=limit;}
function industries(){const opts=[...new Set(rows.map(r=>String(r.industry||'').trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-Hant'));$('#researchIndustry').innerHTML='<option value="">全部產業</option>'+opts.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');}
async function load(){if(loaded)return;if(loading)return loading;loading=(async()=>{try{const res=await fetch('./data/reports_merged.json',{cache:'no-store'});if(!res.ok)throw Error('HTTP '+res.status);const data=await res.json();if(!Array.isArray(data.items))throw Error('Invalid items');rows=data.items.sort((a,b)=>String(b.date||'').localeCompare(String(a.date||'')));loaded=true;industries();}catch(e){count.textContent='整合資料尚未建立，請先執行 LINE research sync';console.error('research database load failed',e);}finally{loading=null;render();}})();return loading;}
function sync(){const isRatings=!$('#twRatingsPanel')?.hidden;panel.hidden=isRatings;if(!isRatings)load();}
root.addEventListener('click',e=>{if(e.target.closest('#reportModeReports,#reportModeRatings'))setTimeout(sync,0);});
const observer=new MutationObserver(()=>{if(root.classList.contains('active'))sync();});observer.observe(root,{attributes:true,attributeFilter:['class']});const ratingsPanel=$('#twRatingsPanel');if(ratingsPanel)observer.observe(ratingsPanel,{attributes:true,attributeFilter:['hidden']});
cats.addEventListener('click',e=>{const b=e.target.closest('[data-cat]');if(b){cat=b.dataset.cat;limit=60;render();}});
ratings.addEventListener('click',e=>{const b=e.target.closest('[data-rating]');if(b){rating=b.dataset.rating;limit=60;render();}});
$('#researchIndustry').addEventListener('change',e=>{industry=e.target.value;limit=60;render();});
$('#researchSearch').addEventListener('input',e=>{query=e.target.value.trim();limit=60;render();});
$('#researchClear').addEventListener('click',()=>{$('#researchSearch').value='';query='';limit=60;render();});
more.addEventListener('click',()=>{limit+=60;render();});
list.addEventListener('click',e=>{const b=e.target.closest('.research-expand');if(!b)return;const cardEl=b.closest('.research-card'),r=rows.find(x=>String(x.id)===cardEl.dataset.researchId);if(!r)return;const expanded=b.getAttribute('aria-expanded')==='true';cardEl.querySelector('.research-body').innerHTML=hi(expanded?bodyOf(r).slice(0,300)+'…':bodyOf(r));b.setAttribute('aria-expanded',String(!expanded));b.textContent=expanded?'展開全文 ▼':'收合內容 ▲';});
const mode=$('#reportModeReports');if(mode)mode.textContent='資料庫';
if(root.classList.contains('active'))sync();
})();
