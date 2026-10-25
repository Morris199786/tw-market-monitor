/* 產業資料庫：券商報告／法說訪談／市場情報／美股；不呼叫 AI API。 */
(() => {
'use strict';
const root = document.getElementById('reports');
const legacy = document.getElementById('reportList');
if (!root || !legacy) return;
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clean = x => {
  if (Array.isArray(x)) return x.map(clean).filter(Boolean).join('\n');
  const v = String(x ?? '').trim();
  return /^(?:null|none|nan)$/i.test(v) ? '' : v;
};
const categories = ['全部','券商報告','法說／訪談','市場情報','美股'];
let category = '全部', query = '', rows = [], manifest = null;
let selectedDay = '', calendarMonth = '', searchSeq = 0, searchHits = null;
let indexRows = []; 
let limit = 30, loaded = false, loading = false, searchTimer, readerSerial = 0, scrollY = 0;
const cache = new Map();
const panel = document.createElement('section');
panel.id = 'researchMergedPanel';
panel.innerHTML = `<div class="rm-toolbar"><div class="rm-cats">${categories.map(c => `<button type="button" class="rm-chip" data-category="${esc(c)}">${esc(c)}</button>`).join('')}</div><div class="rm-search"><input id="rmQuery" type="search" placeholder="搜尋公司、代號、標題、來源"><button id="rmClear" type="button">清除</button></div><div class="rm-meta" id="rmMeta">載入研究索引中…</div><div class="rm-date-tools"><button id="rmDateToggle" type="button">📅 <span id="rmDateLabel">選擇日期</span></button><button id="rmLatest" type="button">最新報告</button></div><div id="rmCalendar" hidden></div></div><div id="rmCards"></div><button id="rmMore" type="button" hidden>顯示更多</button>`;
legacy.parentNode.insertBefore(panel, legacy);
const reader = document.createElement('div');
reader.id = 'rmReader'; reader.hidden = true;
reader.innerHTML = `<header class="rm-reader-header"><strong id="rmReaderTitle"></strong><button type="button" id="rmClose" aria-label="關閉">✕</button></header><main id="rmReaderContent"></main>`;
document.body.appendChild(reader);
const style = document.createElement('style');
style.textContent = `
#researchMergedPanel[hidden],#researchMergedPanel [hidden],#rmReader[hidden]{display:none!important}
#researchMergedPanel{font:14px/1.65 -apple-system,BlinkMacSystemFont,'Noto Sans TC',sans-serif;color:#243246;margin:12px 0 24px}
#researchMergedPanel * ,#rmReader *{box-sizing:border-box}
#researchMergedPanel .rm-toolbar{display:grid;gap:10px;margin-bottom:14px}
#researchMergedPanel .rm-cats{display:flex;flex-wrap:nowrap;align-items:center;gap:8px;padding:2px 0 6px;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;scrollbar-width:none;scroll-snap-type:x proximity}
#researchMergedPanel .rm-cats::-webkit-scrollbar{display:none}
#researchMergedPanel button,#researchMergedPanel input{font:inherit}
#researchMergedPanel .rm-chip{flex:0 0 auto;white-space:nowrap;min-height:40px;border:1px solid #dce1e8;background:#fff;color:#808895;border-radius:999px;padding:7px 14px;font-size:14px;font-weight:750;text-align:center;scroll-snap-align:nearest}
#researchMergedPanel .rm-chip.active{background:#141924;border-color:#141924;color:#fff}
#researchMergedPanel .rm-search{display:flex;gap:8px}
#researchMergedPanel #rmQuery{min-width:0;flex:1;background:#fff;color:#243246;border:1px solid #d4dce7;border-radius:10px;padding:10px 12px;font-size:14px}
#researchMergedPanel #rmClear,#researchMergedPanel #rmMore{border:1px solid #d4dce7;background:#fff;color:#243246;border-radius:10px;padding:10px 13px}
#researchMergedPanel .rm-meta{font-size:12px;color:#64748b}
#researchMergedPanel .rm-date{font-weight:700;margin:20px 0 8px;font-size:14px}
#researchMergedPanel .rm-card{border:1px solid #dce3eb;background:#fff;border-radius:15px;padding:14px;margin:10px 0;overflow-wrap:anywhere;min-width:0}
#researchMergedPanel .rm-title{font-size:17px;font-weight:750;line-height:1.45}
#researchMergedPanel .rm-sub{color:#64748b;font-size:12px;margin:5px 0 10px}
#researchMergedPanel .rm-story{white-space:pre-line;font-size:14px;line-height:1.7;display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden}
#researchMergedPanel .rm-open{margin-top:10px;border:0;border-radius:8px;background:#eaf1ff;color:#2058bb;padding:8px 12px;font-weight:650}
#researchMergedPanel #rmMore{width:100%;margin-top:12px}
#rmReader{position:fixed;inset:0;z-index:2147483000;background:#f7f9fc;color:#243246;overflow:auto;width:100%;font:15px/1.8 -apple-system,BlinkMacSystemFont,'Noto Sans TC',sans-serif;overscroll-behavior:contain}
#rmReader .rm-reader-header{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#fff;border-bottom:1px solid #e1e6ee;padding:calc(12px + env(safe-area-inset-top)) 16px 12px}
#rmReaderTitle{font-size:17px;line-height:1.35;overflow-wrap:anywhere}
#rmClose{flex:0 0 42px;border:1px solid #dce3eb;background:#fff;color:#233247;border-radius:50%;width:38px;height:38px;font-size:21px}
#rmReaderContent{max-width:900px;width:100%;margin:auto;padding:18px 15px calc(28px + env(safe-area-inset-bottom))}
#rmReader .rm-info{color:#64748b;font-size:13px;margin-bottom:10px}
#rmReader .rm-section{background:#fff;border:1px solid #e3e8f0;border-radius:13px;padding:15px;margin:12px 0;overflow-wrap:anywhere}
#rmReader h3{font-size:16px;margin:0 0 10px;color:#1d3554}
#rmReader .rm-original-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.8}
#rmReader .rm-table-wrap{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
#rmReader table{border-collapse:collapse;width:100%;font-size:14px}
#rmReader th,#rmReader td{border-bottom:1px solid #e6ebf2;text-align:left;padding:9px 10px;vertical-align:top}
#rmReader th{background:#f3f6fa;font-weight:650}
#researchAiAudit,#reportList .report-v2-tabs{display:none!important}
#researchMergedPanel .rm-date-group{margin:0 0 10px;border:1px solid #dce3eb;border-radius:17px;background:#f8fafc;overflow:hidden}
#researchMergedPanel .rm-date-group>.report-date-head{min-height:64px;display:flex;align-items:center;justify-content:space-between;padding:12px 16px;cursor:pointer;list-style:none}
#researchMergedPanel .rm-date-group>.report-date-head::-webkit-details-marker{display:none}
#researchMergedPanel .rm-date-group>.report-date-head b{font-size:17px}
#researchMergedPanel .rm-date-group>.report-date-head small{font-size:12px;color:#8a94a3;margin-left:8px}
#researchMergedPanel .rm-date-group>.report-date-body{padding:0 12px 12px}
#researchMergedPanel .rm-date-group[open] .report-date-arrow{transform:rotate(180deg)}
#researchMergedPanel .rm-date-tools{display:flex;gap:9px}
#researchMergedPanel .rm-date-tools button{border:1px solid #d4dce7;border-radius:12px;background:#fff;color:#263344;padding:9px 12px}
#rmCalendar{max-width:440px;border:1px solid #dce3eb;border-radius:18px;padding:15px;background:#fff;box-shadow:0 12px 35px #11182724}
#rmCalendar .rm-cal-head,#rmCalendar .rm-cal-foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:8px 0 14px}
#rmCalendar button{background:transparent;color:#1d293b;border:0;border-radius:10px;min-height:39px;font:inherit}
#rmCalendar .rm-cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;text-align:center}
#rmCalendar .rm-cal-grid>b{padding:8px 0;color:#7a8494}
#rmCalendar .rm-cal-grid>button{position:relative;min-height:45px}
#rmCalendar .rm-cal-grid>button.selected{background:#151b27;color:#fff}
#rmCalendar .rm-cal-grid i{position:absolute;bottom:3px;left:calc(50% - 3px);width:6px;height:6px;border-radius:50%;background:#26b879}
#rmCalendar .rm-cal-foot button{border:1px solid #dce3eb;padding:6px 12px}
#rmCalendar .rm-cal-foot button:last-child{background:#151b27;color:#fff}
#researchMergedPanel mark.rm-hit{background:#ffe17b;color:inherit}
#researchMergedPanel .rm-type{font-weight:750;color:#2563c9}
#researchMergedPanel .rm-empty{padding:20px;text-align:center;color:#64748b}
html[data-theme=dark] #researchMergedPanel .rm-chip,html[data-theme=dark] #rmCalendar,html[data-theme=dark] #researchMergedPanel .rm-date-group{background:#22272e;color:#e5e8ec;border-color:#414a55}
html[data-theme=dark] #researchMergedPanel .rm-chip.active{background:#10151e;color:#fff}
html[data-theme=dark] #researchMergedPanel .rm-card{background:#22272e;color:#e5e8ec;border-color:#414a55}
body.rm-reader-open{overflow:hidden}
@media(max-width:600px){#rmReaderContent{padding:12px 12px 30px}#rmReader .rm-section{padding:12px}}
`;
document.head.appendChild(style);
const cards = panel.querySelector('#rmCards'), meta = panel.querySelector('#rmMeta');
const more = panel.querySelector('#rmMore'), input = panel.querySelector('#rmQuery');
const broker = () => category === '券商報告';
const marketOf = r => String(r.market || 'TW').toUpperCase();
const originalType = r => clean(r.original_type).toLowerCase();
function inCategory(r) {
  if (category === '全部') return marketOf(r) === 'TW' && (r.source_kind === 'broker' || (r.source_kind === 'line' && ['法說會','call memo','小作文','漲停強勢'].includes(originalType(r))));
  if (category === '券商報告') return marketOf(r) === 'TW' && r.source_kind === 'broker';
  if (category === '美股') return marketOf(r) === 'US';
  if (marketOf(r) !== 'TW' || r.source_kind !== 'line') return false;
  if (category === '法說／訪談') return ['法說會','call memo'].includes(originalType(r));
  if (category === '市場情報') return ['小作文','漲停強勢'].includes(originalType(r));
  return false;
}
function heading(r) {return clean(r.title) || clean([r.company,r.ticker].filter(Boolean).join(' ')) || '研究資料';}
function summary(r) {return clean(r.story || r.summary || r.title);}
function classify(r) {
  if (marketOf(r) === 'US') return '美股';
  if (r.source_kind === 'broker') return '券商報告';
  return ['法說會','call memo'].includes(originalType(r)) ? '法說／訪談' : '市場情報';
}
function highlight(t) {
  const str = esc(t);
  if (!query.trim()) return str;
  const parts = query.trim().split(/\s+/).filter(Boolean).map(x => x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
  if (!parts.length) return str;
  try { return str.replace(new RegExp('('+parts.join('|')+')','gi'), '<mark class="rm-hit">$1</mark>'); }
  catch (_) { return str; }
}
function matching(r) {
  if (!inCategory(r)) return false;
  if (!query.trim()) return !selectedDay || r.date === selectedDay;
  if (searchHits && r.source_kind !== 'broker' && !searchHits.has(String(r.id))) return false;
  const words = query.normalize('NFKC').toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const hay = [r.company,r.ticker,r.title,r.report_title,r.source,r.industry,r.original_type,r.category,r.story,r.detail,r.rating,r.broker,...(Array.isArray(r.summary)?r.summary:[]),...(r.key_points||[])].map(clean).join(' ').normalize('NFKC').toLocaleLowerCase();
  return (searchHits && r.source_kind !== 'broker') ? true : words.every(w => hay.includes(w));
}
function render() {
  panel.querySelectorAll('[data-category]').forEach(b => b.classList.toggle('active',b.dataset.category===category));
  const found = rows.filter(matching);
  const counts = Object.fromEntries(categories.slice(1).map(c => [c,found.filter(r => classify(r)===c).length]));
  meta.textContent = `${query ? '搜尋結果' : category}｜${found.length} 筆` + (query ? '｜'+Object.entries(counts).map(([k,v])=>`${k} ${v}`).join('・') : '');
  cards.replaceChildren();
  const grouped = new Map();
  for (const m of found) {const day=m.date||'日期未明';if(!grouped.has(day))grouped.set(day,[]);grouped.get(day).push(m)}
  let n=0;
  for (const [day, group] of grouped) {
    if (n >= limit) break;
    const details=document.createElement('details');details.className='report-date-group rm-date-group';
    if (query || selectedDay || n===0) details.open=true;
    const head=document.createElement('summary');head.className='report-date-head';
    head.innerHTML=`<span><b>${esc(day.replaceAll('-','/'))}</b> <small>${group.length} 份報告</small></span><span class="report-date-arrow">⌄</span>`;
    details.appendChild(head);
    const body=document.createElement('div');body.className='report-date-body';
    for (const m of group) {
      const card=document.createElement('article');card.className='rm-card report-v2-card';
      const story=summary(m);
      if (m.source_kind === 'broker' && m._liveBroker) {
        card.classList.add('rm-broker-card');
        const b=m._liveBroker;
        const bullet=Array.isArray(b.summary)?b.summary:[];
        const target=b.validation_status==='needs_review'?'':(b.target_price_new==null?'':`目標價 ${esc(b.target_price_old!=null?b.target_price_old+' → ':'')}${esc(b.target_price_new)}`);
        card.innerHTML=`<div class="report-broker">${highlight(b.broker||'券商研究')}</div><div class="report-title">${highlight((b.name||b.title||'券商報告')+(b.ticker?' '+b.ticker:''))}</div><div class="report-meta">${b.rating?`<span class="report-chip">${highlight(b.rating)}</span>`:''}${target?`<span class="report-chip report-target">${target}</span>`:''}<span class="report-chip">報告日期 ${esc(m.date)}</span></div>${bullet.length?`<ul class="report-summary">${bullet.map(x=>`<li>${highlight(x)}</li>`).join('')}</ul>`:''}<details class="report-details"><summary>查看完整摘要</summary><div class="report-details-body">${b.detail?`<p>${highlight(b.detail)}</p>`:''}${['key_points','forecast_changes','risks'].map(k=>Array.isArray(b[k])&&b[k].length?`<ul>${b[k].map(x=>`<li>${highlight(x)}</li>`).join('')}</ul>`:'').join('')}${b.source_url?`<a href="${esc(b.source_url)}" target="_blank" rel="noopener">查看原始報告</a>`:''}</div></details>`;
        body.appendChild(card);continue;
      }
      card.innerHTML=`<div class="rm-title">${highlight(heading(m))}</div><div class="rm-sub">${highlight([m.company,m.ticker].filter(Boolean).join(' '))} · ${esc(m.date)} · ${highlight(m.source)} · <span class="rm-type">${esc(classify(m))}</span></div><div class="rm-story">${highlight(story.slice(0,150))}${story.length>150?'…':''}</div><button type="button" class="rm-open">閱讀全文 →</button>`;
      card.querySelector('button').addEventListener('click',()=>openReader(m));body.appendChild(card);
    }
    details.appendChild(body);cards.appendChild(details);n++;
  }
  more.hidden=grouped.size<=limit;
  if (!found.length) cards.innerHTML='<div class="rm-empty">沒有符合條件的報告</div>';
  updateDateLabel();
}
async function fullTextSearch() {
  const serial=++searchSeq;
  searchHits=null;
  if (!query.trim() || query.trim().length<2) {render();return}
  const tokens=query.normalize('NFKC').toLowerCase().split(/\s+/).filter(Boolean);
  const grams=[...new Set(tokens.flatMap(w=>Array.from({length:Math.max(0,w.length-1)},(_,i)=>w.slice(i,i+2))))];
  if(!grams.length){render();return}
  meta.textContent='搜尋歷史報告全文中…';
  try {
    const buckets=[...new Set(grams.map(g=>{let n=0;for(let i=0;i<g.length;i++)n+=(i+1)*g.charCodeAt(i);return String(n%64).padStart(2,'0')}))];
    const loadedBuckets=await Promise.all(buckets.map(x=>fetchJSON(`./data/research_search/${x}.json`)));
    if(serial!==searchSeq)return;
    let ids=null;
    for(const gram of grams){const n=grams.indexOf(gram);let hash=0;for(let i=0;i<gram.length;i++)hash+=(i+1)*gram.charCodeAt(i);const bucket=loadedBuckets[buckets.indexOf(String(hash%64).padStart(2,'0'))];const found=new Set(bucket[gram]||[]);ids=ids===null?found:new Set([...ids].filter(i=>found.has(i)))}
    searchHits=new Set([...ids].map(i=>String(indexRows[i]?.id)).filter(Boolean));
    render();
  } catch(e) {if(serial!==searchSeq)return;searchHits=null;render();meta.textContent+='｜全文索引暫不可用'}
}
function updateDateLabel(){const el=panel.querySelector('#rmDateLabel');if(el)el.textContent=selectedDay||'全部日期'}
function drawCalendar(){
  const host=panel.querySelector('#rmCalendar');if(!host)return;
  const valid=rows.filter(inCategory);const dates=new Set(valid.map(r=>r.date));
  const first=valid.find(r=>/^\d{4}-\d{2}-\d{2}$/.test(r.date));
  if(!calendarMonth)calendarMonth=(first?.date||new Date().toISOString().slice(0,10)).slice(0,7);
  const [y,m]=calendarMonth.split('-').map(Number);const firstDay=new Date(y,m-1,1).getDay();const days=new Date(y,m,0).getDate();
  const cells=Array.from({length:firstDay},()=>'<span></span>');
  for(let d=1;d<=days;d++){const date=`${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`;cells.push(`<button type="button" data-rm-day="${date}" class="${selectedDay===date?'selected':''}">${d}${dates.has(date)?'<i></i>':''}</button>`)}
  host.innerHTML=`<div class="rm-cal-head"><button type="button" data-rm-month="-1">❮</button><strong>${y} 年 ${m} 月</strong><button type="button" data-rm-month="1">❯</button></div><div class="rm-cal-grid">${['日','一','二','三','四','五','六'].map(x=>`<b>${x}</b>`).join('')}${cells.join('')}</div><div class="rm-cal-foot"><button type="button" data-rm-action="today">今天</button><button type="button" data-rm-action="clear">清除</button><button type="button" data-rm-action="done">完成</button></div>`;
}
async function fetchJSON(url) {const r=await fetch(url,{cache:'no-cache'});if(!r.ok)throw Error(`${r.status} ${url}`);return r.json()}
async function shard(file) {
  if(!file) throw Error('缺少原文資料檔案');
  if(!cache.has(file)) {cache.set(file,fetchJSON(`./data/research_shards/${encodeURIComponent(file)}`).then(x=>x.items||[]).catch(e=>{cache.delete(file);throw e}));if(cache.size>5)cache.delete(cache.keys().next().value)}
  return cache.get(file);
}
function section(title,body) {return `<section class="rm-section"><h3>${esc(title)}</h3>${body}</section>`}
function rawTexts(r) {
  const d=r.display||{};
  const list=[d.full_text ?? r.full_text,d.full_text_2 ?? r.full_text_2,d.full_text_3 ?? r.full_text_3].map(clean).filter(Boolean);
  return [...new Set(list)];
}
function detail(r,m) {
  const info=`<div class="rm-info">${esc(r.date||m.date)} · ${esc(r.source||m.source)} · ${esc(r.original_type||m.original_type||'')}</div>`;
  const raw=rawTexts(r);
  if(raw.length) return info+raw.map((t,i)=>section(raw.length>1?`原文 ${i+1}`:'研究原文',`<div class="rm-original-text">${esc(t)}</div>`)).join('');
  const d=r.display||{};
  const fields=[['story','研究重點'],['summary','摘要'],['revenue','營收／成長率'],['eps','EPS／獲利'],['inventory','庫存／出貨'],['utilization','產能利用率'],['guidance','未來展望'],['trend','產業趨勢'],['rating_target','評等／目標價'],['numbers','關鍵數字']];
  let result=info;
  for(const [key,title] of fields) {const value=clean(d[key]??r[key]);if(value)result+=section(title,`<div class="rm-original-text">${esc(value)}</div>`)}
  return result===info ? info+section('研究內容','尚無可顯示的資料') : result;
}
async function openReader(m) {
  const token=++readerSerial;scrollY=window.scrollY;reader.hidden=false;document.body.classList.add('rm-reader-open');reader.scrollTop=0;
  reader.querySelector('#rmReaderTitle').textContent=heading(m);
  const body=reader.querySelector('#rmReaderContent');body.textContent='載入研究內容中…';
  try {const items=await shard(m.file);if(token!==readerSerial||reader.hidden)return;const r=items.find(x=>String(x.id)===String(m.id));if(!r)throw Error('找不到這篇研究');body.innerHTML=detail(r,m)}
  catch(e){if(token===readerSerial)body.textContent='讀取失敗：'+e.message}
}
function closeReader(){++readerSerial;reader.hidden=true;document.body.classList.remove('rm-reader-open');window.scrollTo(0,scrollY)}
reader.querySelector('#rmClose').addEventListener('click',closeReader);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!reader.hidden)closeReader()});
function brokerDay(raw) {
  const m=String(raw||'').match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  return m?`${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`:String(raw||'日期未確認');
}
async function init(){
  if(loaded||loading)return;loading=true;
  try{
    const [mf,idx,live]=await Promise.all([
      fetchJSON('./data/research_manifest.json'),
      fetchJSON('./data/research_meta.json'),
      fetchJSON('./data/reports.json').catch(e=>{console.warn('券商即時資料載入失敗',e);return null})
    ]);
    if(!Array.isArray(idx))throw Error('研究索引格式錯誤');
    manifest=mf;indexRows=idx;
    const brokerItems=Array.isArray(live?.items)?live.items:[];
    // 以券商報告實際使用的 reports.json 為唯一券商清單，避免「全部」漏件。
    // 保留原索引列的順序，以免全文搜尋索引的列號失效。
    if(live && Array.isArray(live.items)) {
      rows=idx.filter(r=>r.source_kind!=='broker');
      rows.push(...brokerItems.map((b,i)=>({
        id:'live-broker-'+String(b.id||i), source_kind:'broker',market:'TW',
        date:brokerDay(b.date),company:b.name||'',ticker:b.ticker||'',
        title:b.title||b.name||'券商報告',source:b.broker||'',broker:b.broker||'',
        story:Array.isArray(b.summary)?b.summary.join(' '):String(b.summary||''),
        detail:b.detail||'',rating:b.rating||'',key_points:b.key_points||[],
        _liveBroker:b
      })));
    } else {rows=idx;}
    rows.sort((a,b)=>String(b.date||'').localeCompare(String(a.date||'')));
    loaded=true;render();drawCalendar();
  }catch(e){meta.textContent='研究索引載入失敗：'+e.message}
  finally{loading=false}
}
function sync(){const rating=document.getElementById('twRatingsPanel');const active=root.classList.contains('active');const ratingOn=Boolean(rating&&!rating.hidden);const brokerMode=active&&!ratingOn&&broker()&&!query.trim();panel.hidden=!active||ratingOn;legacy.hidden=active&&!ratingOn?!brokerMode:Boolean(ratingOn);cards.hidden=brokerMode;panel.querySelector('.rm-search').hidden=brokerMode;meta.hidden=brokerMode;more.hidden=brokerMode || cards.querySelectorAll('.rm-date-group').length < limit;if(active&&!ratingOn)init()}
const observer=new MutationObserver(sync);observer.observe(root,{attributes:true,attributeFilter:['class']});const rating=document.getElementById('twRatingsPanel');if(rating)observer.observe(rating,{attributes:true,attributeFilter:['hidden']});
panel.querySelectorAll('[data-category]').forEach(b=>b.addEventListener('click',()=>{category=(category===b.dataset.category && category!=='全部')?'全部':b.dataset.category;selectedDay='';limit=30;render();drawCalendar();sync();panel.querySelector(`[data-category="${category}"]`)?.scrollIntoView({behavior:'smooth',block:'nearest',inline:'nearest'});}));
input.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{query=clean(input.value);limit=30;fullTextSearch();sync()},250)});
panel.querySelector('#rmClear').addEventListener('click',()=>{input.value='';query='';searchHits=null;searchSeq++;clearTimeout(searchTimer);limit=30;render();sync()});
more.addEventListener('click',()=>{limit+=30;render()});
panel.querySelector('#rmDateToggle').addEventListener('click',()=>{const el=panel.querySelector('#rmCalendar');el.hidden=!el.hidden;if(!el.hidden)drawCalendar()});
panel.querySelector('#rmLatest').addEventListener('click',()=>{selectedDay='';query='';input.value='';searchHits=null;searchSeq++;clearTimeout(searchTimer);limit=30;calendarMonth='';panel.querySelector('#rmCalendar').hidden=true;render();drawCalendar();sync();const target=broker()?document.querySelector('#reportCardsV3 .report-date-group'):cards.querySelector('.rm-date-group');if(target){target.open=true;target.scrollIntoView({behavior:'smooth',block:'start'});}else{panel.querySelector('.rm-date-tools').scrollIntoView({behavior:'smooth',block:'start'});}});
panel.querySelector('#rmCalendar').addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.rmMonth){const [y,m]=calendarMonth.split('-').map(Number);const d=new Date(y,m-1+Number(b.dataset.rmMonth),1);calendarMonth=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;drawCalendar()}
 if(b.dataset.rmDay){selectedDay=b.dataset.rmDay;query='';input.value='';searchHits=null;searchSeq++;render();drawCalendar();sync()}
 if(b.dataset.rmAction==='today'){query='';input.value='';searchHits=null;searchSeq++;const d=new Date();calendarMonth=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;selectedDay=`${calendarMonth}-${String(d.getDate()).padStart(2,'0')}`;render();drawCalendar()}
 if(b.dataset.rmAction==='clear'){selectedDay='';render();drawCalendar()}
 if(b.dataset.rmAction==='done')panel.querySelector('#rmCalendar').hidden=true;
});
sync();
})();
