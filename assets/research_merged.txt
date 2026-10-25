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
const categories = ['券商報告','法說／訪談','市場情報','美股'];
let category = '券商報告', query = '', rows = [], manifest = null;
let limit = 30, loaded = false, loading = false, searchTimer, readerSerial = 0, scrollY = 0;
const cache = new Map();
const panel = document.createElement('section');
panel.id = 'researchMergedPanel';
panel.innerHTML = `<div class="rm-toolbar"><div class="rm-cats">${categories.map(c => `<button type="button" class="rm-chip" data-category="${esc(c)}">${esc(c)}</button>`).join('')}</div><div class="rm-search"><input id="rmQuery" type="search" placeholder="搜尋公司、代號、標題、來源"><button id="rmClear" type="button">清除</button></div><div class="rm-meta" id="rmMeta">載入研究索引中…</div></div><div id="rmCards"></div><button id="rmMore" type="button" hidden>顯示更多</button>`;
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
#researchMergedPanel .rm-cats{display:flex;gap:7px;overflow-x:auto;padding:3px 0 8px;scrollbar-width:none}
#researchMergedPanel .rm-cats::-webkit-scrollbar{display:none}
#researchMergedPanel button,#researchMergedPanel input{font:inherit}
#researchMergedPanel .rm-chip{flex:none;border:1px solid #d4dce7;background:#fff;color:#273449;border-radius:22px;padding:7px 12px;white-space:nowrap;font-size:13px}
#researchMergedPanel .rm-chip.active{background:#205fcd;border-color:#205fcd;color:#fff}
#researchMergedPanel .rm-search{display:flex;gap:8px}
#researchMergedPanel #rmQuery{min-width:0;flex:1;background:#fff;color:#243246;border:1px solid #d4dce7;border-radius:10px;padding:10px 12px;font-size:14px}
#researchMergedPanel #rmClear,#researchMergedPanel #rmMore{border:1px solid #d4dce7;background:#fff;color:#243246;border-radius:10px;padding:10px 13px}
#researchMergedPanel .rm-meta{font-size:12px;color:#64748b}
#researchMergedPanel .rm-date{font-weight:700;margin:20px 0 8px;font-size:14px}
#researchMergedPanel .rm-card{border:1px solid #dce3eb;background:#fff;border-radius:13px;padding:14px;margin:9px 0;overflow-wrap:anywhere;min-width:0}
#researchMergedPanel .rm-title{font-size:17px;font-weight:750;line-height:1.45}
#researchMergedPanel .rm-sub{color:#64748b;font-size:12px;margin:5px 0 10px}
#researchMergedPanel .rm-story{white-space:pre-line;font-size:14px;line-height:1.7}
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
  if (category === '券商報告') return marketOf(r) === 'TW' && r.source_kind === 'broker';
  if (category === '美股') return marketOf(r) === 'US';
  if (marketOf(r) !== 'TW' || r.source_kind !== 'line') return false;
  if (category === '法說／訪談') return ['法說會','call memo'].includes(originalType(r));
  if (category === '市場情報') return ['小作文','漲停強勢'].includes(originalType(r));
  return false;
}
function heading(r) {return clean(r.title) || clean([r.company,r.ticker].filter(Boolean).join(' ')) || '研究資料';}
function summary(r) {return clean(r.story || r.summary || r.title);}
function matching(r) {
  if (!inCategory(r)) return false;
  const words = query.normalize('NFKC').toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = [r.company,r.ticker,r.title,r.report_title,r.source,r.industry,r.original_type,r.category].map(clean).join(' ').normalize('NFKC').toLocaleLowerCase();
  return words.every(w => hay.includes(w));
}
function render() {
  panel.querySelectorAll('[data-category]').forEach(b => b.classList.toggle('active',b.dataset.category===category));
  const found = rows.filter(matching);
  meta.textContent = `${query?'歷史搜尋':'全部'+category}｜符合 ${found.length} 筆｜資料庫 ${manifest?.count ?? rows.length} 筆`;
  cards.replaceChildren(); let date = '';
  for(const m of found.slice(0,limit)) {
    if(m.date !== date) {date=m.date; const d=document.createElement('div');d.className='rm-date';d.textContent=date||'日期未明';cards.appendChild(d)}
    const card=document.createElement('article');card.className='rm-card';
    card.innerHTML=`<div class="rm-title">${esc(heading(m))}</div><div class="rm-sub">${esc([m.company,m.ticker].filter(Boolean).join(' '))}<br>${esc(m.date)} ${esc(m.source)} ${esc(m.original_type || m.category)}</div><div class="rm-story">${esc(summary(m))}</div><button type="button" class="rm-open">閱讀全文 →</button>`;
    card.querySelector('button').addEventListener('click',()=>openReader(m));cards.appendChild(card);
  }
  more.hidden=found.length<=limit;
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
async function init(){if(loaded||loading)return;loading=true;try{[manifest,rows]=await Promise.all([fetchJSON('./data/research_manifest.json'),fetchJSON('./data/research_meta.json')]);if(!Array.isArray(rows))throw Error('研究索引格式錯誤');loaded=true;render()}catch(e){meta.textContent='研究索引載入失敗：'+e.message}finally{loading=false}}
function sync(){const rating=document.getElementById('twRatingsPanel');const active=root.classList.contains('active');const ratingOn=Boolean(rating&&!rating.hidden);const brokerMode=active&&!ratingOn&&broker();panel.hidden=!active||ratingOn;legacy.hidden=active&&!ratingOn?!brokerMode:Boolean(ratingOn);cards.hidden=brokerMode;panel.querySelector('.rm-search').hidden=brokerMode;meta.hidden=brokerMode;more.hidden=brokerMode||more.hidden;if(active&&!ratingOn)init()}
const observer=new MutationObserver(sync);observer.observe(root,{attributes:true,attributeFilter:['class']});const rating=document.getElementById('twRatingsPanel');if(rating)observer.observe(rating,{attributes:true,attributeFilter:['hidden']});
panel.querySelectorAll('[data-category]').forEach(b=>b.addEventListener('click',()=>{category=b.dataset.category;limit=30;render();sync()}));
input.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{query=clean(input.value);limit=30;render()},220)});
panel.querySelector('#rmClear').addEventListener('click',()=>{input.value='';query='';clearTimeout(searchTimer);limit=30;render()});
more.addEventListener('click',()=>{limit+=30;render()});
sync();
})();
