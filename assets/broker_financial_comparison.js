/* Offline comparison data; stable period/metric identities, not column order. */
(() => {
  'use strict';
  const specs = [
    ['eps','broker_eps_comparisons.json','EPS','元'],
    ['gross_margin','broker_gross_margin_comparisons.json','毛利率','%'],
    ['operating_margin','broker_operating_margin_comparisons.json','OPM','%']
  ];
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date = v => String(v||'').match(/20\d{2}[-/]\d{2}[-/]\d{2}/)?.[0]?.replaceAll('/','-') || '';
  const num = v => v == null || String(v).trim()==='' ? null : Number.isFinite(Number(v)) ? Number(v) : null;
  const key = (t,p,d,k) => [t,p,d,k].join('|');
  let maps = new Map(), timer, loading;
  function lookup(metric,t,p,d,k,value) {
    if (!t || !p || !d || value === null) return [];
    const rows = maps.get(metric)?.get(key(t,p,d,k)) || [];
    const seen=new Set();
    return rows.filter(r => {
      const actual=num(r['actual_'+metric]);
      const estimate=num(r['forecast_'+metric]);
      if(actual===null || estimate===null || Math.abs(actual-value)>(metric==='eps'?0.015:0.06))return false;
      if(date(r.report_date)>d || !date(r.report_date))return false;
      const id=[r.broker,date(r.report_date),estimate].join('|');
      if(seen.has(id))return false;seen.add(id);return true;
    });
  }
  function panel(card, groups) {
    const old=card.querySelector(':scope > .broker-financial-panel');
    groups=groups.filter(g=>g.rows.length);
    if(!groups.length){old?.remove();return;}
    const signature=JSON.stringify(groups);
    if(old?.dataset.signature===signature)return;
    const el=old||document.createElement('details');
    el.className='broker-financial-panel broker-eps-comparison';
    el.dataset.signature=signature;
    const count=groups.reduce((n,g)=>n+g.rows.length,0);
    el.innerHTML='<summary>券商預估比對（'+count+' 筆）</summary>'+groups.map(g=>{
      const eps=g.metric==='eps';
      return '<section style="margin-top:8px"><strong>'+esc(g.label)+'</strong>'+g.rows.map(r=>{
        const actual=Number(r['actual_'+g.metric]), estimate=Number(r['forecast_'+g.metric]);
        const delta=actual-estimate;
        const sign=delta>0?'+':'';
        let result=eps?(estimate>0?(g.kind==='monthly'?'單月／季預估比 ':'季度達成率 ')+(actual/estimate*100).toFixed(1)+'%':'差 '+sign+delta.toFixed(2)+' 元'):'差 '+sign+delta.toFixed(2)+' 個百分點';
        const url=String(r.source_url||'');
        const name=esc(r.broker);
        const link=/^https:\/\/(?:drive\.google\.com|docs\.google\.com)\//.test(url)?'<a href="'+esc(url)+'" target="_blank" rel="noopener">'+name+'</a>':name;
        return '<div class="broker-eps-entry" style="display:flex;flex-wrap:wrap;gap:4px 10px"><span>'+esc(date(r.report_date))+'</span><span>'+link+'</span><span>預估 '+estimate.toFixed(2)+g.unit+'</span><span class="broker-eps-rate">'+esc(result)+'</span></div>';
      }).join('')+'</section>';
    }).join('');
    if(!old)card.appendChild(el);
  }
  function render() {
    document.querySelectorAll('#quarterlyEarningsCards .earnings-comparison-card').forEach(card=>{
      const t=card.dataset.brokerTicker,p=card.dataset.brokerPeriod,d=card.dataset.brokerDate;
      panel(card,specs.map(([metric,,label,unit])=>{
        const cell=card.querySelector('[data-earnings-metric="'+metric+'"] .ec-current strong');
        const v=num(cell?.textContent.replace(/元|%|,/g,'').trim());
        return {metric,label,unit,kind:'quarterly',rows:lookup(metric,t,p,d,'quarterly',v)};
      }));
    });
    document.querySelectorAll('#selfReportCards .self-report-card').forEach(card=>{
      const t=card.querySelector('.titleline span')?.textContent.trim(),d=date(card.querySelector('.eyebrow')?.textContent);
      panel(card,[...card.querySelectorAll('[data-broker-kind]')].map(el=>{
        const kind=el.dataset.brokerKind==='monthly'?'monthly':'quarterly';
        return {metric:'eps',label:kind==='monthly'?'當月 EPS':'上一季 EPS',unit:'元',kind,
          rows:lookup('eps',t,el.dataset.brokerPeriod,d,kind,num(el.dataset.brokerValue))};
      }));
    });
  }
  async function load(){
    if(loading)return loading;
    loading=Promise.allSettled(specs.map(async ([metric,file])=>{
      const res=await fetch('./data/'+file+'?v='+Math.floor(Date.now()/60000),{cache:'no-store'});
      if(!res.ok)throw Error(file+' '+res.status);
      const j=await res.json(), map=new Map();
      for(const r of j.items||[]){
        const k=key(r.ticker,r.actual_period||r.period,r.announcement_date,r.actual_kind);
        if(!map.has(k))map.set(k,[]);map.get(k).push(r);
      }
      for(const rows of map.values())rows.sort((a,b)=>String(b.report_date).localeCompare(String(a.report_date)));
      maps.set(metric,map);
    })).then(results=>{results.forEach(x=>{if(x.status==='rejected')console.warn('[Broker comparison]',x.reason);});render();}).finally(()=>{loading=null;});
    return loading;
  }
  function init(){
    const root=document.querySelector('#selfReports');
    if(!root)return;
    new MutationObserver(changes=>{
      if(changes.every(x=>x.target.closest?.('.broker-financial-panel')))return;
      clearTimeout(timer);timer=setTimeout(render,120);
    }).observe(root,{subtree:true,childList:true});
    load();document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
    setInterval(()=>{if(!document.hidden)load();},300000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
