/* Broker EPS comparison: data-first matching, independent of legacy card CSS. */
(() => {
  'use strict';
  const ROOT = './data/';
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let forecasts = new Map(), actuals = new Map(), loading = null, timer = 0;
  const cleanDate = s => String(s || '').slice(0,10);
  const quarter = m => {const z=/^(20\d{2})-(\d{2})$/.exec(m || ''); return z ? `${z[1]}-Q${Math.ceil(+z[2]/3)}` : '';};
  const n = x => x === null || x === undefined || x === '' ? null : (Number.isFinite(Number(x)) ? Number(x) : null);
  const key = (ticker,period) => `${ticker}|${period}`;
  function putActual(x, period, kind, value) {
    if(!/^\d{4}$/.test(String(x.ticker)) || !/^20\d{2}-Q[1-4]$/.test(period) || n(value) === null) return;
    const k=key(x.ticker,period), row={...x,kind,period,actual:n(value)};
    if(!actuals.has(k)) actuals.set(k,[]);
    actuals.get(k).push(row);
  }
  async function load(){
    if(loading) return loading;
    loading = Promise.all(['broker_eps_forecasts.json','self_reports.json','quarterly_earnings.json'].map(async f => {
      const r=await fetch(`${ROOT}${f}?v=${Math.floor(Date.now()/60000)}`,{cache:'no-store'});
      if(!r.ok) throw new Error(`${f}: ${r.status}`); return r.json();
    })).then(([f,s,e]) => {
      const fi=new Map(), ai=new Map(); forecasts=fi;actuals=ai;
      for(const x of f.items || []){
        if(!/^\d{4}$/.test(String(x.ticker)) || !/^20\d{2}-Q[1-4]$/.test(x.period||'') || n(x.eps)===null || !n(x.eps) || !x.report_date)continue;
        const k=key(x.ticker,x.period);if(!fi.has(k))fi.set(k,[]);fi.get(k).push(x);
      }
      for(const x of s.items || []) putActual(x,quarter(x.monthly_period),'monthly',x.monthly_eps);
      for(const x of e.reports || []) putActual(x,x.period,'quarter',x.eps);
      for(const a of ai.values())a.sort((x,y)=>cleanDate(y.publish_date).localeCompare(cleanDate(x.publish_date)));
      render();
    }).catch(err=>console.warn('[EPS Compare]',err)).finally(()=>loading=null);
    return loading;
  }
  function findActual(ticker,kind,day,visibleValue){
    const candidates=[];
    for(const [k,items] of actuals){if(!k.startsWith(`${ticker}|`))continue;
      for(const x of items){if(x.kind!==kind || (day && cleanDate(x.publish_date)!==day))continue;
        if(visibleValue !== null && Math.abs(x.actual-visibleValue)>.015)continue;
        candidates.push(x);
      }
    }
    return candidates.length===1 ? candidates[0] : null;
  }
  function match(ticker,kind,day,value){
    const x=findActual(ticker,kind,day,value);if(!x)return null;
    const rows=(forecasts.get(key(ticker,x.period))||[]).filter(r=>r.report_date<=cleanDate(x.publish_date));
    return {x,rows};
  }
  function numericText(el){const m=String(el?.textContent||'').match(/-?\d[\d,]*(?:\.\d+)?\s*元/);return m?Number(m[0].replace(/[,元\s]/g,'')):null;}
  function dateIn(s){return String(s||'').match(/20\d{2}[-\/]\d{2}[-\/]\d{2}/)?.[0]?.replaceAll('/','-')||'';}
  function tickerIn(card){
    const t=card.querySelector('[data-ticker]')?.dataset.ticker;
    if(/^\d{4}$/.test(t||''))return t;
    const txt=card.textContent||'';
    const m=txt.match(/(?:^|\s|\u00a0)(\d{4})(?=\s|\u00a0|$)/);
    return m?.[1]||'';
  }
  function paint(metric,result){
    const old=metric.querySelector(':scope > .broker-eps-comparison');
    if(!result?.rows.length){old?.remove();return;}
    const {x,rows}=result;
    const sig=JSON.stringify([x.ticker,x.period,x.actual,x.publish_date,rows.map(r=>[r.report_id,r.eps])]);
    if(old?.dataset.signature===sig)return;
    const panel=old||document.createElement('div');panel.className='broker-eps-comparison';panel.dataset.signature=sig;
    panel.innerHTML=rows.map(r=>{
      const same=cleanDate(r.report_date)===cleanDate(x.publish_date);
      const rate=(x.actual/Number(r.eps))*100;
      return `<div class="broker-eps-entry" title="${esc(x.period)} 券商預估 EPS ${Number(r.eps).toFixed(2)} 元；實際 EPS ${x.actual.toFixed(2)} 元"><span>${esc(r.report_date.slice(5).replace('-','/'))}</span> <span>${esc(r.broker)}</span> <span class="broker-eps-rate">達成率 ${rate.toFixed(1)}%</span>${same?'<small>（同日報告）</small>':''}</div>`;
    }).join('');
    if(!old)metric.appendChild(panel);
  }
  function render(){
    const root=document.querySelector('#selfReportCards');
    if(root){for(const card of root.children){
      const ticker=tickerIn(card), day=dateIn(card.querySelector('time')?.getAttribute('datetime')||card.textContent);
      if(!ticker || !day)continue;
      // Find the visible monthly EPS tile without assuming card class names.
      const candidates=[...card.querySelectorAll('div,section,article')].filter(el=>{
        const text=el.textContent||'';
        return el.children.length<=4 && /當月\s*EPS|單月\s*EPS/.test(text) && /\d/.test(text);
      }).sort((a,b)=>a.textContent.length-b.textContent.length);
      let metric=candidates.find(el=>numericText(el)!==null);
      if(!metric)continue;
      const value=numericText(metric);
      paint(metric,match(ticker,'monthly',day,value));
    }}
    document.querySelectorAll('#quarterlyEarningsCards .earnings-report-row').forEach(card=>{
      const ticker=card.querySelector('.earnings-company span')?.textContent.trim()||'';
      const metric=card.querySelector('.earnings-detail.four > div:first-child');
      const day=dateIn(card.querySelector('.earnings-period')?.textContent);
      const value=numericText(metric?.querySelector('b'));
      if(ticker&&metric&&day)paint(metric,match(ticker,'quarter',day,value));
    });
  }
  function init(){
    const page=document.querySelector('#selfReports');if(!page)return;
    new MutationObserver(rs=>{if(rs.every(r=>r.target.closest?.('.broker-eps-comparison')))return;
      clearTimeout(timer);timer=setTimeout(render,120);
    }).observe(page,{subtree:true,childList:true});
    load();document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
    setInterval(()=>{if(!document.hidden)load();},300000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
