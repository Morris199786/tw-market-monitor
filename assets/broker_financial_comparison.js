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
  function paint(host, metric, unit, kind, rows, quarterCell=false) {
    if(!host)return;
    const old=host.querySelector(':scope > .broker-inline');
    if(!rows.length){old?.remove();return;}
    const signature=JSON.stringify(rows);
    if(old?.dataset.signature===signature)return;
    const el=old||document.createElement('div');
    el.className=quarterCell?'broker-inline broker-inline-quarter':'broker-inline broker-inline-self';
    el.dataset.signature=signature;
    const html=rows.map(r=>{
      const actual=Number(r['actual_'+metric]), estimate=Number(r['forecast_'+metric]);
      const delta=actual-estimate, sign=delta>0?'+':'';
      const rate=estimate>0 ? (actual/estimate*100).toFixed(1)+'%' : '';
      const result=rate?'達成率 '+rate:'差 '+sign+delta.toFixed(2)+(metric==='eps'?' 元':'pp');
      const url=String(r.source_url||''), name=esc(r.broker);
      const link=/^https:\/\/(?:drive\.google\.com|docs\.google\.com)\//.test(url)?'<a href="'+esc(url)+'" target="_blank" rel="noopener">'+name+'</a>':name;
      const tone=delta>0?'above':delta<0?'below':'flat';
      const detail=esc(date(r.report_date))+' '+link+'｜預估 '+estimate.toFixed(2)+unit+(metric==='eps'?'':'｜差 '+sign+delta.toFixed(2)+'pp');
      return '<details class="broker-inline-compact"><summary class="broker-inline-rate '+tone+'" title="'+esc(kind==='monthly'?'單月 EPS／整季預估':'實際／預估')+'">'+esc(result)+'</summary><div class="broker-inline-detail">'+detail+'</div></details>';
    }).join('');
    el.innerHTML=html;
    if(!old)host.appendChild(el);
  }
  function render() {
    document.querySelectorAll('#quarterlyEarningsCards .earnings-comparison-card').forEach(card=>{
      const t=card.dataset.brokerTicker,p=card.dataset.brokerPeriod,d=card.dataset.brokerDate;
      card.querySelector(':scope > .broker-financial-panel')?.remove();
      card.querySelectorAll('tr.broker-inline-row').forEach(row=>row.remove());
      specs.forEach(([metric,,label,unit])=>{
        const row=card.querySelector('[data-earnings-metric="'+metric+'"]');
        const cell=row?.querySelector('.ec-current');
        const actual=cell?.querySelector('strong');
        const v=num(actual?.textContent.replace(/元|%|,/g,'').trim());
        paint(cell,metric,unit,'quarterly',lookup(metric,t,p,d,'quarterly',v),true);
      });
    });
    document.querySelectorAll('#selfReportCards .self-report-card').forEach(card=>{
      const t=card.querySelector('.titleline span')?.textContent.trim(),d=date(card.querySelector('.eyebrow')?.textContent);
      card.querySelector(':scope > .broker-financial-panel')?.remove();
      card.querySelectorAll('[data-broker-kind]').forEach(el=>{
        const kind=el.dataset.brokerKind==='monthly'?'monthly':'quarterly';
        paint(el,'eps','元',kind,lookup('eps',t,el.dataset.brokerPeriod,d,kind,num(el.dataset.brokerValue)));
      });
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
      if(changes.every(x=>x.target.closest?.('.broker-inline')))return;
      clearTimeout(timer);timer=setTimeout(render,120);
    }).observe(root,{subtree:true,childList:true});
    load();document.addEventListener('visibilitychange',()=>{if(!document.hidden)load();});
    setInterval(()=>{if(!document.hidden)load();},300000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
