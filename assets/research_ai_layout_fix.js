/* Unified broker research presentation v4. No AI calls, no writes.
   Replace assets/research_ai_layout_fix.js with this file's contents.
   Works with existing reports_v2.js, research_merged.js and research_ai_status.js.
*/
(() => {
  'use strict';
  if (window.__researchUnifiedV4) return;
  window.__researchUnifiedV4 = true;
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const valid = x => x !== null && x !== undefined && String(x).trim() !== '' && !/^(null|none|nan)$/i.test(String(x).trim());
  const txt = x => Array.isArray(x) ? x.map(txt).join('\n') : typeof x === 'object' && x ? JSON.stringify(x) : String(x ?? '');
  const clean = x => txt(x).replace(/\r/g,'').replace(/\n[ \t]*\n[ \t]*\n+/g,'\n\n').trim();
  const id = x => String(x ?? '').trim();
  const log = (...args) => console.info('[RESEARCH_UI_V4]', ...args);
  const css = `
  .ru-fin{margin:10px 0 13px;max-width:100%;overflow-x:auto;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch}
  .ru-fin table{width:100%;border-collapse:collapse;font-size:12px;line-height:1.45;white-space:nowrap;background:var(--card,#fff);color:var(--ink,#233)}
  .ru-fin th,.ru-fin td{padding:8px 10px;border-bottom:1px solid var(--line,#e2e8f0);text-align:right;font-variant-numeric:tabular-nums}
  .ru-fin th:first-child,.ru-fin td:first-child{text-align:left;position:sticky;left:0;background:var(--card,#fff);font-weight:700}
  .ru-fin thead th{background:var(--card,#f4f7fb);font-weight:800}
  .ru-fin-title{font-size:13px;font-weight:800;margin:13px 0 5px;color:var(--ink,#243246)}
  .ru-modal[hidden]{display:none!important}
  .ru-modal{position:fixed;inset:0;z-index:2147483000;background:var(--card,#fff);color:var(--ink,#172334);display:flex;flex-direction:column;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}
  .ru-modal-head{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid var(--line,#ddd);background:var(--card,#fff)}
  .ru-modal-name{font-weight:850;font-size:16px;line-height:1.3;min-width:0;overflow-wrap:anywhere}
  .ru-modal-sub{font-size:11px;color:var(--muted,#667);margin-top:3px}
  .ru-close{flex:0 0 auto;border:1px solid var(--line,#ccc);background:var(--card,#fff);color:var(--ink,#222);border-radius:10px;padding:8px 13px;font-size:18px;font-weight:800;cursor:pointer}
  .ru-modal-body{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:15px 17px 40px;font-size:14px;line-height:1.65}
  .ru-modal-body h3{font-size:14px;margin:16px 0 6px}.ru-modal-body p{margin:0 0 9px;white-space:pre-line;overflow-wrap:anywhere}
  .ru-modal-body ul{margin:5px 0 12px;padding-left:22px}.ru-modal-body li{margin:0 0 6px}
  .ru-broker-card .report-details{margin-top:9px}
  .ru-broker-card .report-summary{margin-bottom:9px}
  #researchAiAudit .raa-card .raa-v2-section,#researchAiAudit .raa-card .raa-section{white-space:normal!important;min-height:0!important;margin:10px 0 0!important;padding:9px 0 0!important}
  #researchAiAudit .raa-card .raa-v2-text{white-space:pre-line!important;line-height:1.6!important}
  .ru-topic{font-size:12px;color:var(--muted,#64748b);margin:5px 0 9px}
  .ru-reader-link{display:inline-block;margin-top:9px;padding:6px 0;border:0;background:transparent;color:var(--accent,#2861b0);font-weight:800;cursor:pointer}
  `;
  const style = document.createElement('style');style.textContent=css;document.head.appendChild(style);

  // Read-only cache. The processing ledger is never mutated and no OpenAI endpoint is called.
  let cachePromise;
  const loadCache = () => cachePromise ||= Promise.all([
    fetch('./data/research_ai_cache.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('cache '+r.status);return r.json()}),
    fetch('./data/research_ai_plan.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('plan '+r.status);return r.json()})
  ]).then(([cache,plan])=>({cache,plan:new Map((plan.items||[]).map(x=>[x.id,x]))})).catch(e=>{cachePromise=null;console.warn('[RESEARCH_UI_V4] cache unavailable',e);return null});
  const resolve = (data,rid) => {
    if(!data)return null;
    const row=data.plan.get(rid);let key=rid;const seen=new Set();
    for(let n=0;n<12;n++){
      if(!key||seen.has(key))break;seen.add(key);
      const e=data.cache[key];if(!e){key=row?.cache_id;continue}
      if(e.status==='alias'){key=e.cache_id;continue}
      if(e.status==='success'&&e.result)return {result:e.result,row};
      break;
    }
    return null;
  };
  // Conservative extraction: accept only explicitly paired period/metric/value fields.
  const periods = x => {
    const raw=String(x??'').replace(/\s+/g,'').toUpperCase();
    const q=raw.match(/(?:20\d{2}|\d{2})[\-/]?Q[1-4]|Q[1-4][\-/]?(?:20\d{2}|\d{2})|(?:20\d{2}|\d{2})[\-/]?[1-4]Q/);
    if(q){let v=q[0];let yr=(v.match(/20\d{2}|\d{2}/)||[])[0];let quarter=(v.match(/Q[1-4]|[1-4]Q/)||[])[0];if(!yr||!quarter)return null;if(yr.length===2)yr='20'+yr;return {key:`${yr} Q${quarter.replace('Q','')}`,order:Number(yr)*10+Number(quarter.replace('Q','')),type:'quarter'};}
    const y=raw.match(/^(?:20\d{2}|\d{2})(?:E|F|A|年)?$/);
    if(y){let yr=(raw.match(/20\d{2}|\d{2}/)||[])[0];if(yr.length===2)yr='20'+yr;return {key:yr+(raw.endsWith('A')?'':'E'),order:Number(yr),type:'year'};}
    return null;
  };
  const metrics = [
    ['eps','EPS（元）',/^(?:eps|每股(?:盈餘|稅後盈餘|純益))$/i],
    ['revenue','營收',/^(?:營收|營業收入|revenue|sales)$/i],
    ['revenue_yoy','營收 YoY',/^(?:營收年增率|營收yoy|revenue.?yoy)$/i],
    ['revenue_qoq','營收 QoQ',/^(?:營收季增率|營收qoq|revenue.?qoq)$/i],
    ['gross_profit','毛利',/^(?:毛利|gross.?profit)$/i],
    ['gross_margin','毛利率',/^(?:毛利率|gm|gpm|gross.?margin)$/i],
    ['operating_profit','營業利益',/^(?:營業利益|營業淨利|operating.?income|operating.?profit)$/i],
    ['operating_margin','營業利益率',/^(?:營業利益率|營益率|opm|operating.?margin)$/i],
    ['pretax_profit','稅前淨利',/^(?:稅前淨利|pretax.?income)$/i],
    ['pretax_margin','稅前淨利率',/^(?:稅前淨利率|pretax.?margin)$/i],
    ['net_profit','稅後淨利',/^(?:稅後淨利|淨利|net.?income)$/i],
    ['net_margin','稅後淨利率',/^(?:稅後淨利率|淨利率|net.?margin)$/i],
    ['roe','ROE',/^roe$/i],['roa','ROA',/^roa$/i],
    ['operating_cash_flow','營業現金流',/^(?:營業現金流|ocf|operating.?cash.?flow)$/i],
    ['free_cash_flow','自由現金流',/^(?:自由現金流|fcf|free.?cash.?flow)$/i],
    ['capex','資本支出',/^(?:資本支出|capex)$/i]
  ];
  const metricName = k => metrics.find(([key,,re])=>key===k||re.test(k))?.[1]||null;
  const normalizeNumber = v => {
    if(typeof v==='number')return Number.isFinite(v)?String(v):null;
    if(typeof v!=='string')return null;
    const s=v.trim();
    if(!/^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:%|％|元|億(?:元)?|百萬(?:元)?|千元|million|bn)?$/i.test(s))return null;
    return s;
  };
  function financialData(ai){
    const buckets={year:new Map(),quarter:new Map()};
    const add=(p,k,v)=>{
      const period=periods(p),name=metricName(String(k??''));const value=normalizeNumber(v);
      if(!period||!name||value===null)return;
      let map=buckets[period.type];if(!map.has(period.key))map.set(period.key,{order:period.order,values:{}});
      if(!(name in map.get(period.key).values))map.get(period.key).values[name]=value;
    };
    for(const [field,k] of [['quarterly_eps','eps'],['annual_eps','eps']]){
      for(const x of Array.isArray(ai[field])?ai[field]:[]){if(x&&typeof x==='object')add(x.period||x.quarter||x.year||x.label,k,x.eps??x.value);}
    }
    for(const field of ['financial_forecasts','financials','forecasts','quarterly_forecasts','annual_forecasts','quarterly_financials','annual_financials','financial_estimates']){
      const arr=ai[field];
      if(Array.isArray(arr))for(const x of arr){if(!x||typeof x!=='object')continue;const p=x.period||x.quarter||x.year||x.fiscal_period;for(const [k,v] of Object.entries(x)){if(k==='metrics'&&v&&typeof v==='object')for(const [a,b] of Object.entries(v))add(p,a,b);else add(p,k,v)} }
      else if(arr&&typeof arr==='object')for(const [p,row] of Object.entries(arr)){if(row&&typeof row==='object')for(const [k,v] of Object.entries(row))add(p,k,v)}
    }
    // Only deterministic, clearly delimited financial lines from already saved text.
    // Never guess units, years or figures from unrelated prose.
    const text=[ai.detail,ai.summary,ai.key_points].flat().filter(x=>typeof x==='string').join('\n');
    for(const line of text.split(/\n|[；;]/).slice(0,1200)){
      const m=line.trim().match(/^((?:20\d{2}|\d{2})(?:[\-/]?Q[1-4])?[EeFf]?)\s*[:：|,，\s]+(EPS|每股盈餘|毛利率|營業利益率|營益率|淨利率|營收|營業收入|ROE|ROA|CAPEX)\s*[:：=]\s*([+-]?[\d,.]+\s*(?:%|％|元|億元|百萬元)?)(?:\s|$)/i);
      if(m)add(m[1],m[2],m[3]);
    }
    return buckets;
  }
  function financialTable(ai){
    if(!ai||typeof ai!=='object')return '';
    const b=financialData(ai);let out='';
    for(const [type,label] of [['year','券商年度財務預估'],['quarter','券商季度財務預估']]){
      const cols=[...b[type]].sort((a,c)=>a[1].order-c[1].order);
      if(!cols.length)continue;
      const keys=metrics.map(x=>x[1]).filter(k=>cols.some(([,v])=>Object.hasOwn(v.values,k)));
      if(!keys.length)continue;
      out+=`<div class="ru-fin-title">${label}</div><div class="ru-fin" role="region" tabindex="0" aria-label="${label}"><table><thead><tr><th>財務指標</th>${cols.map(([p])=>`<th>${esc(p)}</th>`).join('')}</tr></thead><tbody>${keys.map(k=>`<tr><th>${esc(k)}</th>${cols.map(([,v])=>`<td>${esc(v.values[k]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    }
    return out;
  }
  function topic(title,identity){
    let s=clean(title),n=clean(identity);
    if(!s)return '';
    if(n){s=s.replace(new RegExp('^'+n.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'[\\s:：|｜\\-—]*','i'),'').trim();}
    s=s.replace(/^[\s:：|｜－—-]+|[\s:：|｜－—-]+$/g,'').replace(/(?:[－—\-：:]?\s*(?:摘要|研究報告|報告摘要))$/,'').trim();
    if(!s||s.toLowerCase()===n.toLowerCase())return '';
    if(/座談會/.test(s)&&!/(?:重點|展望|觀點)/.test(s))s=s+'重點';
    return s;
  }
  const modal=document.createElement('div');modal.className='ru-modal';modal.hidden=true;
  modal.innerHTML='<div class="ru-modal-head"><div><div class="ru-modal-name" id="ruModalName"></div><div class="ru-modal-sub" id="ruModalSub"></div></div><button class="ru-close" type="button" aria-label="關閉完整研究分析">✕</button></div><div class="ru-modal-body" id="ruModalBody" tabindex="0"></div>';
  document.body.appendChild(modal);
  let oldOverflow='',returnFocus=null;
  function openModal(name,sub,html){
    returnFocus=document.activeElement;oldOverflow=document.body.style.overflow;document.body.style.overflow='hidden';
    modal.querySelector('#ruModalName').textContent=name||'完整研究分析';
    modal.querySelector('#ruModalSub').textContent=sub||'';
    modal.querySelector('#ruModalBody').innerHTML=html;
    modal.hidden=false;modal.querySelector('#ruModalBody').scrollTop=0;modal.querySelector('.ru-close').focus();
    log('modal opened',name);
  }
  function closeModal(){modal.hidden=true;document.body.style.overflow=oldOverflow;returnFocus?.focus?.({preventScroll:true});log('modal closed');}
  modal.querySelector('.ru-close').addEventListener('click',closeModal);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden){e.preventDefault();closeModal()}});
  function sections(ai){
    let h='';const list=[['研究摘要','summary'],['核心投資觀點','push_reason'],['研究重點','key_points'],['完整研究分析','detail'],['財測調整','forecast_changes'],['風險因素','risks']];
    for(const [label,key] of list){const v=ai[key];if(!valid(v)||Array.isArray(v)&&!v.length)continue;
      const body=Array.isArray(v)?`<ul>${v.map(x=>`<li>${esc(clean(x))}</li>`).join('')}</ul>`:`<p>${esc(clean(v))}</p>`;
      h+=`<h3>${label}</h3>${body}`;
    }
    return h;
  }
  function findDataId(el){return el.dataset.reportId||el.id?.replace(/^report-/,'')||'';}
  async function enhanceAudit(){
    const root=document.getElementById('researchAiAudit');if(!root)return;
    const elements=[...root.querySelectorAll('.raa-card[data-report-id]')].filter(x=>x.dataset.ruV4!=='1');if(!elements.length)return;
    const data=await loadCache();if(!data)return;
    for(const el of elements){const rid=findDataId(el);const entry=resolve(data,rid);if(!entry){el.dataset.ruV4='1';continue}
      const ai=entry.result,row=entry.row||{};const name=ai.name||row.company||'研究報告';const ticker=ai.ticker||row.ticker||'';const broker=ai.broker||row.source||'';
      const header=el.querySelector('.raa-v2-header,.raa-v2-name');
      // Use the ORIGINAL broker card's class names, not a new big-tile design.
      const action=ai.rating?`<span class="report-chip">評等 ${esc(ai.rating)}</span>`:'';
      const old=ai.target_price_old,newer=ai.target_price_new;
      const target=valid(newer)?`<span class="report-chip">目標價 ${valid(old)?esc(old)+' → ':''}${esc(newer)}</span>`:'';
      const up=ai.implied_upside_pct,basis=ai.upside_basis;
      const upside=valid(up)&&valid(basis)&&Number.isFinite(Number(up))?`<span class="report-chip">隱含${Number(up)>=0?'漲':'跌'}幅 ${Number(up)>=0?'+':''}${Number(up).toFixed(1)}%</span>`:'';
      const financial=financialTable(ai);
      el.innerHTML=`<div class="report-v2-top"><div><div class="report-broker">${esc(broker)}</div><div class="report-title">${esc(name)} ${esc(ticker)}</div></div><span class="report-action">AI 已完成</span></div><div class="report-meta">${action}${target}${upside}<span class="report-chip">${esc(ai.date||row.date||'')}</span></div>${topic(ai.title,name)?`<div class="ru-topic">${esc(topic(ai.title,name))}</div>`:''}${Array.isArray(ai.summary)?`<ul class="report-summary">${ai.summary.map(x=>`<li>${esc(clean(x))}</li>`).join('')}</ul>`:valid(ai.summary)?`<p>${esc(clean(ai.summary))}</p>`:''}${financial}<button class="ru-reader-link" type="button" data-ru-open="audit">查看完整研究分析 ↗</button>`;
      el.classList.add('report-v2-card','ru-broker-card');el.dataset.ruV4='1';
      el.querySelector('[data-ru-open]')?.addEventListener('click',()=>openModal(`${name} ${ticker}`,`${broker} · ${row.date||''}`,financial+sections(ai)));
      log('audit upgraded',rid);
    }
  }
  function enhanceBrokers(){
    for(const el of document.querySelectorAll('#reportList .report-v2-card:not([data-ru-v4])')){
      const details=el.querySelector('details.report-details');if(!details){el.dataset.ruV4='1';continue}
      const summary=details.querySelector('summary');if(!summary){el.dataset.ruV4='1';continue}
      const title=el.querySelector('.report-title')?.textContent.trim()||'券商報告';const broker=el.querySelector('.report-broker')?.textContent.trim()||'';
      const original=details.querySelector('.report-details-body')?.innerHTML||'';
      // Preserve the broker's original report markup and styling in the modal.
      summary.textContent='查看完整研究分析 ↗';
      summary.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();details.open=false;openModal(title,broker,original)});
      el.classList.add('ru-broker-card');el.dataset.ruV4='1';
    }
  }
  async function enhanceMerged(){
    // Formal Excel database: add saved AI financial tables to its existing full-screen reader.
    const reader=document.getElementById('rmReader');
    const content=reader?.querySelector('#rmReaderContent');
    if(!content || !content.children.length || content.dataset.ruV4==='1')return;
    const title=reader.querySelector('#rmReaderTitle')?.textContent.trim()||'';
    if(!title)return;
    const data=await loadCache();if(!data)return;
    const candidates=[...data.plan.values()].filter(x=>{
      const name=String(x.company||'').trim();
      return name && (title.includes(name)||name.includes(title)) && (x.status==='cached'||data.cache[x.id]?.status==='success');
    }).map(x=>({x,e:resolve(data,x.id)})).filter(z=>z.e);
    if(candidates.length!==1){if(candidates.length>1)log('reader match ambiguous; no AI data injected',title);return;}
    const {x,e}=candidates[0],ai=e.result;
    const fin=financialTable(ai);
    if(fin){const wrap=document.createElement('div');wrap.innerHTML=fin;content.prepend(wrap);log('formal reader financials',x.company);}
    content.dataset.ruV4='1';
  }
  function tidyMergedCards(){
    for(const el of document.querySelectorAll('#researchMergedPanel .rm-card:not([data-ru-v4])')){
      const title=el.querySelector('.rm-title'),sub=el.querySelector('.rm-sub');
      if(title&&sub){
        const main=title.textContent.trim();
        const html=sub.innerHTML;
        const lines=html.split(/<br\s*\/?\s*>/i);
        if(lines.length>1){
          const first=lines[0].replace(/<[^>]*>/g,'').trim();
          if(first&&main&&(main===first||main.startsWith(first+' ')))sub.innerHTML=lines.slice(1).join('<br>');
        }
      }
      el.dataset.ruV4='1';
    }
  }
  let queued=false;const schedule=()=>{if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;enhanceBrokers();tidyMergedCards();enhanceMerged().catch(e=>console.warn('[RESEARCH_UI_V4] merged',e));enhanceAudit().catch(e=>console.error('[RESEARCH_UI_V4] audit',e))})};
  const observer=new MutationObserver(schedule);
  observer.observe(document.body,{subtree:true,childList:true});
  schedule();log('installed: broker modal + audit broker-style + financial tables; API calls=0');
})();
