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
const categories = ['全部','券商報告','早報','法說／訪談','產業研究','市場情報','美股'];
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
#researchMergedPanel .rm-story{white-space:pre-line;font-size:14px;line-height:1.7;display:block;overflow:visible}
#researchMergedPanel .rm-company-list{margin:8px 0 12px;color:#64748b;font-size:13px}
#researchMergedPanel .rm-company-list>div{padding:3px 0}
#researchMergedPanel .rm-open{margin-top:10px;border:0;border-radius:8px;background:#eaf1ff;color:#2058bb;padding:8px 12px;font-weight:650}
#researchMergedPanel #rmMore{width:100%;margin-top:12px}
#rmReader{position:fixed;inset:0;z-index:2147483000;background:#f7f9fc;color:#243246;overflow:auto;width:100%;font:15px/1.8 -apple-system,BlinkMacSystemFont,'Noto Sans TC',sans-serif;overscroll-behavior:contain}
#rmReader .rm-reader-header{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#fff;border-bottom:1px solid #e1e6ee;padding:calc(12px + env(safe-area-inset-top)) 16px 12px}
#rmReaderTitle{flex:1;min-width:0;font-size:17px;line-height:1.35;overflow-wrap:anywhere}
#rmClose{flex:0 0 42px;border:1px solid #dce3eb;background:#fff;color:#233247;border-radius:50%;width:38px;height:38px;font-size:21px}
#rmReaderContent{max-width:900px;width:100%;margin:auto;padding:18px 15px calc(28px + env(safe-area-inset-bottom))}
#rmReader .rm-info{color:#64748b;font-size:13px;margin-bottom:10px}
#rmReader .rm-section{background:#fff;border:1px solid #e3e8f0;border-radius:13px;padding:15px;margin:12px 0;overflow-wrap:anywhere}
#rmReader h3{font-size:16px;margin:0 0 10px;color:#1d3554}
#rmReader .rm-table-scroll{overflow-x:auto;max-width:100%}
#rmReader table{border-collapse:collapse;width:100%;font-size:13px}
#rmReader th,#rmReader td{padding:10px;border-bottom:1px solid #e1e6ee;text-align:left;vertical-align:top;min-width:95px}
#rmReader .rm-number{font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}
#rmReader td details{min-width:100px;max-width:260px}
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
#researchMergedPanel mark.rm-hit,#rmReader mark.rm-hit{background:#ffe17b;color:#243246;border-radius:2px;padding:0 1px}
#researchMergedPanel .rm-type{font-weight:750;color:#2563c9}
#researchMergedPanel .rm-empty{padding:20px;text-align:center;color:#64748b}
html[data-theme=dark] #researchMergedPanel .rm-chip,html[data-theme=dark] #rmCalendar,html[data-theme=dark] #researchMergedPanel .rm-date-group{background:#22272e;color:#e5e8ec;border-color:#414a55}
html[data-theme=dark] #researchMergedPanel .rm-chip.active{background:#10151e;color:#fff}
html[data-theme=dark] #researchMergedPanel .rm-card{background:#22272e;color:#e5e8ec;border-color:#414a55}
body.rm-reader-open{overflow:hidden}
@media(max-width:600px){#rmReaderContent{padding:12px 12px 30px}#rmReader .rm-section{padding:12px}}
`;
style.textContent += `
#rmReader .rm-ai-heading{font-size:16px;margin:18px 0 8px}
#rmReader .rm-ai-paragraph{margin:10px 0;line-height:1.85;white-space:pre-wrap}
#rmReader .rm-ai-list{padding-left:22px;margin:10px 0}
#rmReader .rm-ai-list li{margin:6px 0}
#rmReader .rm-ai-quote{border-left:3px solid #94a3b8;padding:6px 14px;margin:12px 0;background:#f8fafc;white-space:pre-wrap}
`;
document.head.appendChild(style);
const cards = panel.querySelector('#rmCards'), meta = panel.querySelector('#rmMeta');
const more = panel.querySelector('#rmMore'), input = panel.querySelector('#rmQuery');
const broker = () => category === '券商報告';
const marketOf = r => String(r.market || 'TW').toUpperCase();
const originalType = r => clean(r.original_type).toLowerCase();
function reportCategory(r) {
  if (marketOf(r) === 'US') return '美股';
  if (r.source_kind === 'broker') return '券商報告';
  const c=clean(r.category);
  if (c==='早報') return '早報';
  if (c==='產業研究') return '產業研究';
  if (c==='法說／訪談') return '法說／訪談';
  if (c==='市場情報') return '市場情報';
  // Backward-compatible fallback for older metadata.
  return ['法說會','call memo'].includes(originalType(r))?'法說／訪談':'市場情報';
}
function inCategory(r) {
  const c=reportCategory(r);
  if (category==='全部') return c!=='美股';
  return c===category;
}

function heading(r) {
  const codes=stockCodes(r.ticker);
  const multi=r.is_multi_company || codes.length>1;
  let title=clean(r.title)||clean(r.company);
  title=title.replace(/[（(]多檔聚合[）)]\s*/g,'').trim();
  if(multi){
    title=title.replace(/(?:\s*[;；、]?\s*\d{4,6}\.(?:TWO|TW))+\s*$/i,'').trim();
    const ticker=clean(r.ticker);if(ticker && title.endsWith(ticker))title=title.slice(0,-ticker.length).trim();
    return title || '多公司研究報告';
  }
  if(codes.length===1){
    const name=companyNames.get(codes[0])||clean(r.company);
    if(!title || /^(?:\d{4}|[1-4]Q\d{2})(?:\s+\d{4,6})?$/.test(title))title=name;
    if(title===name)return `${name} ${codes[0]}`;
  }
  return title||'研究資料';
}
function readableText(value,r) {
  let text=clean(value);
  // Parse list serialization, rather than stripping quotation marks from prose.
  if(text.startsWith('[')){try{const v=JSON.parse(text);if(Array.isArray(v)&&v.every(x=>typeof x==='string'))text=v.join('\n\n')}catch(_){}}
  text=text.replace(/\r\n?/g,'\n');
  const codes=stockCodes(r.ticker);
  const names=codes.map(c=>companyNames.get(c)).filter(Boolean);
  const escapeRE=x=>x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const starts=names.map(escapeRE).join('|');
  if(starts){
    text=text.replace(new RegExp('([;；]|[\\n])\\s*(?=(?:📌\\s*)?(?:'+starts+'))','g'),'\n\n');
    text=text.replace(new RegExp('([:：])\\s*(?=(?:'+starts+')[（(]\\d)','g'),'$1\n\n');
  }
  text=text.replace(/\s*📌\s*/g,'\n\n📌 ');
  text=text.split('\n').map(line=>{
    if(!/[\u3400-\u9fff]/.test(line))return line;
    return line.replace(/,/g,(c,i,t)=>/\d/.test(t[i-1]||'')&&/\d/.test(t[i+1]||'')?',':'，').replace(/;/g,'；').replace(/:/g,'：');
  }).join('\n');
  return text.replace(/\n{3,}/g,'\n\n').trim();
}
// Reflow PDF physical line breaks only; keep headings, lists and real paragraphs.
function readableProse(value,r) {
  const raw=String(value||'').replace(/\r\n?/g,'\n');
  const lines=raw.split('\n');
  const wrapped=lines.filter(x=>x.trim().length>=28).length>=3;
  if(!wrapped)return readableText(raw,r);
  const out=[];
  const heading=x=>/^(?:[\-•●📌📍]|\d+[.、]\s|Q&A|重點摘要|營運成果|營運展望|投資建議|評論及分析|重要訊息|【|\|)/.test(x)
    || /^[\u3400-\u9fffA-Za-z\-]+\s*[（(]\d{4}/.test(x)
    || /^(?:\d{4}\s*[\u3400-\u9fff]|[1-4]Q\d{2}(?:\s+[1-4]Q\d{2}){2})/.test(x);
  for(const line of lines){
    const t=line.trim(),prev=out[out.length-1]||'';
    if(t&&prev&&prev.length>=28&&!/[。！？：:]$/.test(prev)&&!heading(t)&&!heading(prev)
      && /[\u3400-\u9fff]/.test(prev)&& !/\t|\s{3,}/.test(line)){
      const sep=/[A-Za-z0-9]$/.test(prev)&&/^[A-Za-z0-9]/.test(t)?' ':'';
      out[out.length-1]=prev+sep+t;
    }else out.push(t);
  }
  return readableText(out.join('\n'),r);
}
let metricsPromise;
function loadReportMetrics(){
  return metricsPromise ||= fetchJSON('./data/research_metrics.json').then(x=>x.items||[]).catch(()=>{metricsPromise=null;return []});
}
function metricTables(items,r){
  const verified=items.filter(x=>x.research_id===r.id&&['editorially_verified','source_verified'].includes(x.review_status));
  const groups=new Map();
  for(const fact of verified){
    const key=JSON.stringify([fact.company,fact.ticker,fact.provider||r.source]);
    if(!groups.has(key))groups.set(key,[]);groups.get(key).push(fact);
  }
  const status={actual:'實績',estimate:'券商預估',guidance:'公司計畫／展望',unknown:'性質待確認'};
  const prefix={approximate:'約 ',at_least:'至少 ',at_most:'不高於 '};
  return [...groups].map(([key,facts])=>{
    const [name,ticker,provider]=JSON.parse(key);
    const body=facts.map(x=>{
      const val=String(x.value??'');
      const qualified=/約|略低|超過|多|至少|不高於|低於/.test(val)?val:(prefix[x.qualifier]||'')+val;
      return `<tr><th>${esc(x.metric)}</th><td>${esc(x.period)}</td><td class="rm-number">${esc(qualified)} ${esc(x.unit||'')}</td><td>${esc(status[x.actual_or_estimate]||'性質待確認')}</td><td><details><summary>原文依據</summary>${highlight(x.evidence||'')}</details></td></tr>`;
    }).join('');
    return section(`${name} ${ticker}｜財務與營運數據`,`<p>${esc(r.date)} · ${esc(provider)} · 已核對來源文字</p><div class="rm-table-scroll" tabindex="0" aria-label="財務數據，可左右捲動"><table><thead><tr><th>指標</th><th>期間／口徑</th><th>數值</th><th>性質</th><th>依據</th></tr></thead><tbody>${body}</tbody></table></div>`);
  }).join('');
}
function companyList(r) {
  const codes=stockCodes(r.ticker);
  if(codes.length<2)return '';
  return `<details class="rm-company-list"><summary>涵蓋 ${codes.length} 家公司</summary>${codes.map(c=>`<div>${highlight((companyNames.get(c)||'')+' '+c)}</div>`).join('')}</details>`;
}
function summary(r) {return clean(r.story || r.summary || r.title);}
function classify(r) { return reportCategory(r); }

function highlight(t) {
  const text=String(t ?? '');
  if (!query.trim()) return esc(text);
  const terms=new Set(searchTerms());
  for(const term of [...terms]) {
    for(const code of companyAliases.get(term)||[]) {
      terms.add(code);
      if(companyNames.get(code))terms.add(companyNames.get(code));
    }
  }
  const patterns=[...terms].filter(Boolean).sort((a,b)=>b.length-a.length).map(term=>{
    const safe=term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    return /^\d+$/.test(term)?`(?<![\\d.,])${safe}(?!\\d|[.,]\\d)`:safe;
  });
  if(!patterns.length)return esc(text);
  const regex=new RegExp(patterns.join('|'),'gi');
  let result='',offset=0;
  for(const match of text.matchAll(regex)) {
    result+=esc(text.slice(offset,match.index))+`<mark class="rm-hit">${esc(match[0])}</mark>`;
    offset=match.index+match[0].length;
  }
  return result+esc(text.slice(offset));
}
const normalizeSearch = x => clean(x).normalize('NFKC').toLowerCase().replace(/臺/g,'台').trim();
const companyAliases = new Map();
const companyNames = new Map();
function stockCodes(value) {
  return [...normalizeSearch(value).matchAll(/(?:^|[^a-z0-9])(\d{4,6})(?:\.(?:tw|two)|\s+tt)?(?=$|[^a-z0-9])/g)].map(m=>m[1]);
}
function registerCompany(code,name,aliases=[]) {
  if (!/^\d{4,6}$/.test(code)) return;
  if (name) companyNames.set(code,clean(name));
  for (const alias of [code,code+'.TW',code+'.TWO',name,...aliases]) {
    const key=normalizeSearch(alias);if (!key) continue;
    if (!companyAliases.has(key)) companyAliases.set(key,new Set());
    companyAliases.get(key).add(code);
  }
}
function buildCompanyAliases(registry) {
  companyAliases.clear();companyNames.clear();
  for (const [code,entry] of Object.entries(registry||{})) registerCompany(code,entry.name,entry.aliases||[]);
  for (const r of rows) {
    const codes=stockCodes(r.ticker);
    if (codes.length===1 && !r.is_multi_company && !/多檔|[、;]/.test(clean(r.company))) {
      registerCompany(codes[0],companyNames.get(codes[0])||r.company,[r.company]);
    }
  }
}
function reportCompanies(r) {
  const result=new Set(stockCodes(r.ticker));
  for (const part of clean(r.company).split(/[、;；]/)) {
    for (const code of companyAliases.get(normalizeSearch(part))||[]) result.add(code);
  }
  return result;
}
function searchTerms() {
  const q=normalizeSearch(query);
  return companyAliases.has(q) ? [q] : q.split(/\s+/).filter(Boolean);
}
function matching(r) {
  if (!inCategory(r) || (selectedDay && r.date!==selectedDay)) return false;
  const subjects=reportCompanies(r);
  const metadata=[r.company,r.ticker,r.title,r.report_title,r.source,r.industry,r.broker].map(normalizeSearch).join(' ');
  return searchTerms().every(term=>{
    const codes=companyAliases.get(term);
    if(codes) return marketOf(r)==='TW' && [...codes].some(code=>subjects.has(code));
    if(/^\d{4,6}(?:\.(?:tw|two))?$/.test(term)) return subjects.has(term.split('.')[0]);
    return metadata.includes(term);
  });
}
function matchedSummary(r) {
  const codes=new Set(searchTerms().flatMap(t=>[...(companyAliases.get(t)||[])]));
  if (!codes.size || !(r.is_multi_company || stockCodes(r.ticker).length>1)) return summary(r);
  const names=[...codes].flatMap(c=>[companyNames.get(c),c]).filter(Boolean);
  const chunks=summary(r).split(/\n+|[；;]/).filter(t=>names.some(n=>t.includes(n)));
  return chunks.length ? chunks.join('\n\n') : '本報告涵蓋 '+[...codes].map(c=>(companyNames.get(c)||'')+' '+c).join('、')+'，請開啟全文查看相關段落。';
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
    head.innerHTML=`<span><b>${esc(dateLabel(day))}</b> <small>${group.length} 份報告</small></span><span class="report-date-arrow">⌄</span>`;
    details.appendChild(head);
    const body=document.createElement('div');body.className='report-date-body';
    for (const m of group) {
      const card=document.createElement('article');card.className='rm-card report-v2-card';
      const story=readableText(matchedSummary(m),m);
      if (m.source_kind === 'broker' && m._liveBroker) {
        card.classList.add('rm-broker-card');
        const b=m._liveBroker;
        const bullet=Array.isArray(b.summary)?b.summary:[];
        const target=b.validation_status==='needs_review'?'':(b.target_price_new==null?'':`目標價 ${esc(b.target_price_old!=null?b.target_price_old+' → ':'')}${esc(b.target_price_new)}`);
        card.innerHTML=`<div class="report-broker">${highlight(b.broker||'券商研究')}</div><div class="report-title">${highlight((b.name||b.title||'券商報告')+(b.ticker?' '+b.ticker:''))}</div><div class="report-meta">${b.rating?`<span class="report-chip">${highlight(b.rating)}</span>`:''}${target?`<span class="report-chip report-target">${target}</span>`:''}<span class="report-chip">報告日期 ${esc(m.date)}</span></div>${bullet.length?`<ul class="report-summary">${bullet.map(x=>`<li>${highlight(x)}</li>`).join('')}</ul>`:''}<details class="report-details"><summary>查看完整摘要</summary><div class="report-details-body">${b.detail?`<p>${highlight(b.detail)}</p>`:''}${['key_points','forecast_changes','risks'].map(k=>Array.isArray(b[k])&&b[k].length?`<ul>${b[k].map(x=>`<li>${highlight(x)}</li>`).join('')}</ul>`:'').join('')}${b.source_url?`<a href="${esc(b.source_url)}" target="_blank" rel="noopener">查看原始報告</a>`:''}</div></details>`;
        body.appendChild(card);continue;
      }
      card.innerHTML=`<div class="rm-title">${highlight(heading(m))}</div><div class="rm-sub">${esc(m.date)} · ${highlight(m.source)} · <span class="rm-type">${esc(classify(m))}</span></div>${companyList(m)}<div class="rm-story">${highlight(story)}</div><button type="button" class="rm-open">閱讀全文 →</button>`;
      card.querySelector('button').addEventListener('click',()=>openReader(m));body.appendChild(card);
    }
    details.appendChild(body);cards.appendChild(details);n++;
  }
  more.hidden=grouped.size<=limit;
  if (!found.length) cards.innerHTML='<div class="rm-empty">沒有符合條件的報告</div>';
  updateDateLabel();
}
function fullTextSearch() {
  // Company search is based on report subjects, never body n-gram hits.
  ++searchSeq;searchHits=null;render();
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
let aiDirectPromise;
function loadAiDirect(){
  return aiDirectPromise ||= fetchJSON('./data/research_ai_render.json').then(x=>x.items||{}).catch(()=>({}));
}
function renderAiDirect(entry){
  const ai=entry?.content;
  if(!ai || typeof ai!=='object')return '';
  const blocks=Array.isArray(ai.blocks)?ai.blocks:null;
  if(blocks){
    const html=blocks.map(b=>{
      if(!b||typeof b!=='object')return '';
      if(b.type==='heading')return `<h3 class="rm-ai-heading">${esc(b.text||'')}</h3>`;
      if(b.type==='paragraph')return `<p class="rm-ai-paragraph">${esc(b.text||'')}</p>`;
      if(b.type==='quote')return `<blockquote class="rm-ai-quote">${esc(b.text||'')}</blockquote>`;
      if(b.type==='bullets')return `<ul class="rm-ai-list">${(Array.isArray(b.items)?b.items:[]).map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`;
      if(b.type==='table'){
        const cols=Array.isArray(b.columns)?b.columns:[];
        const rows=Array.isArray(b.rows)?b.rows:[];
        return `<div class="rm-table-scroll"><table><thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${(Array.isArray(row)?row:[]).map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      }
      return '';
    }).join('');
    return html?section('AI 完整研究整理',html):'';
  }
  // Existing paid AI records used an older JSON schema: show their model-authored
  // narrative directly rather than filtering through Python fact verification.
  const parts=[];
  if(Array.isArray(ai.summary))parts.push(...ai.summary.map(s=>`<p>${esc(s)}</p>`));
  else if(ai.summary)parts.push(`<p>${esc(ai.summary)}</p>`);
  for(const c of Array.isArray(ai.companies)?ai.companies:[]){
    if(!c||typeof c!=='object')continue;
    if(c.name)parts.push(`<h3>${esc(c.name)} ${esc(c.ticker||'')}</h3>`);
    for(const k of ['key_points','unstructured_notes','risks']){
      const values=Array.isArray(c[k])?c[k]:[];
      if(values.length)parts.push(`<ul>${values.map(v=>`<li>${esc(typeof v==='string'?v:JSON.stringify(v))}</li>`).join('')}</ul>`);
    }
    for(const k of ['financials','guidance','operating_metrics','valuations']){
      const facts=Array.isArray(c[k])?c[k]:[];
      if(!facts.length)continue;
      parts.push(`<div class="rm-table-scroll"><table><thead><tr><th>項目</th><th>期間</th><th>內容</th></tr></thead><tbody>${facts.map(f=>`<tr><td>${esc(f.metric||'')}</td><td>${esc(f.period||'')}</td><td>${esc([f.value,f.unit].filter(Boolean).join(' '))}</td></tr>`).join('')}</tbody></table></div>`);
    }
  }
  return parts.length?section('AI 研究資料（舊版解析）',parts.join('')):'';
}
function detail(r,m,metrics=[],direct={}) {
  const info=`<div class="rm-info">${esc(r.date||m.date)} · ${esc(r.source||m.source)} · ${esc(r.original_type||m.original_type||'')}</div>`;
  const raw=rawTexts(r);
  const ai=r.ai_research||{};
  const aiIntro=ai && Object.keys(ai).length ? section('AI 解析重點',`<div class="rm-original-text">${highlight((Array.isArray(ai.summary)?ai.summary.join('\n'):ai.summary)||'')}</div>`) : '';
  const modelHtml=renderAiDirect(direct[r.id]);
  if(raw.length) return info+(modelHtml||metricTables(metrics,r)+aiIntro)+`<details class="rm-source-details"><summary>查看 Excel 研究原文</summary>${raw.map((t,i)=>section(raw.length>1?`原文 ${i+1}`:'研究原文',`<div class="rm-original-text">${highlight(readableProse(t,r))}</div>`)).join('')}</details>`;
  const d=r.display||{};
  const fields=[['story','研究重點'],['summary','摘要'],['revenue','營收／成長率'],['eps','EPS／獲利'],['inventory','庫存／出貨'],['utilization','產能利用率'],['guidance','未來展望'],['trend','產業趨勢'],['rating_target','評等／目標價'],['numbers','關鍵數字']];
  let result=info;
  for(const [key,title] of fields) {const value=clean(d[key]??r[key]);if(value)result+=section(title,`<div class="rm-original-text">${highlight(readableText(value,r))}</div>`)}
  return result===info ? info+section('研究內容','尚無可顯示的資料') : result;
}
async function openReader(m) {
  reader.dataset.reportId=String(m.id);
  const token=++readerSerial;scrollY=window.scrollY;reader.hidden=false;document.body.classList.add('rm-reader-open');reader.scrollTop=0;
  reader.querySelector('#rmReaderTitle').innerHTML=highlight(heading(m));
  const body=reader.querySelector('#rmReaderContent');body.textContent='載入研究內容中…';
  try {const [items,metrics,direct]=await Promise.all([shard(m.file),loadReportMetrics(),loadAiDirect()]);if(token!==readerSerial||reader.hidden)return;const r=items.find(x=>String(x.id)===String(m.id));if(!r)throw Error('找不到這篇研究');body.innerHTML=detail(r,m,metrics,direct)}
  catch(e){if(token===readerSerial)body.textContent='讀取失敗：'+e.message}
}
function closeReader(){++readerSerial;reader.hidden=true;document.body.classList.remove('rm-reader-open');window.scrollTo(0,scrollY)}
reader.querySelector('#rmClose').addEventListener('click',closeReader);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!reader.hidden)closeReader()});
function brokerDay(raw) {
  const text=clean(raw).normalize('NFKC');
  const m=text.match(/^(\d{4})(?:[-/](\d{1,2})[-/](\d{1,2})|(\d{2})(\d{2}))(?:$|[T\s])/);
  if(m){
    const y=+m[1],month=+(m[2]||m[4]),day=+(m[3]||m[5]);
    const d=new Date(Date.UTC(y,month-1,day));
    if(d.getUTCFullYear()===y && d.getUTCMonth()===month-1 && d.getUTCDate()===day)
      return `${y}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
  }
  const month=text.match(/^(\d{4})[-/](\d{1,2})$/);
  if(month && +month[2]>=1 && +month[2]<=12) return `${month[1]}-${month[2].padStart(2,'0')}`;
  return '日期未確認';
}
function dateRank(value) {
  const d=brokerDay(value);
  return /^\d{4}-\d{2}(?:-\d{2})?$/.test(d) ? Number(d.replaceAll('-','').padEnd(8,'0')) : 0;
}
function compareReportDate(a,b) {
  return dateRank(b.date)-dateRank(a.date) || String(a.id||'').localeCompare(String(b.id||''));
}
function dateLabel(day) {
  return day.replaceAll('-','/')+(/^\d{4}-\d{2}$/.test(day)?'（日期未詳）':'');
}
async function init(){
  if(loaded||loading)return;loading=true;
  try{
    const [mf,idx,live,registry]=await Promise.all([
      fetchJSON('./data/research_manifest.json'),
      fetchJSON('./data/research_meta.json'),
      fetchJSON('./data/reports.json').catch(e=>{console.warn('券商即時資料載入失敗',e);return null}),
      fetchJSON('./data/report_company_registry.json').catch(()=>({}))
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
    rows=rows.map(r=>({...r,date:brokerDay(r.date)}));
    rows.sort(compareReportDate);
    buildCompanyAliases(registry);
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
