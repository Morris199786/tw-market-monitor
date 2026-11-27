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
  function shortBroker(raw) {
    const clean=String(raw||'').replace(/\([^)]*\)|（[^）]*）/g,'').replace(/\s+/g,' ').trim();
    const rules=[
      [/Morgan Stanley|摩根士丹利|大摩/i,'大摩'],
      [/J\.?\s*P\.?\s*Morgan|JPMorgan|摩根大通|小摩/i,'小摩'],
      [/Goldman Sachs|高盛/i,'高盛'],
      [/Merrill Lynch|BofA|Bank of America|美銀|美林/i,'美銀'],
      [/Citi(?:group|bank)?\b|花旗/i,'花旗'],
      [/\bUBS\b|瑞銀/i,'瑞銀'],
      [/Daiwa|大和/i,'大和'],
      [/GF Securities|GFHK|廣發|广发/i,'廣發'],
      [/CLSA|里昂/i,'里昂'],
      [/Nomura|野村/i,'野村'],
      [/Macquarie|麥格理/i,'麥格理'],
      [/Aletheia/i,'Aletheia'],
      [/KGI|凱基/i,'凱基'],
      [/SinoPac|永豐/i,'永豐'],
      [/中國信託|中信(?!保誠)|CTBC/i,'中信'],
      [/Cathay|國泰/i,'國泰'],
      [/中信保誠/i,'中信保誠'],
      [/元大|Yuanta/i,'元大'],
      [/元富|MasterLink/i,'元富'],
      [/富邦|Fubon/i,'富邦'],
      [/統一|President Securities/i,'統一'],
      [/華南|Hua Nan/i,'華南'],
      [/台新|臺新|Taishin/i,'台新'],
      [/宏遠|Horizon Securities/i,'宏遠'],
      [/兆豐|Mega Securities/i,'兆豐'],
      [/國票|IBF Securities/i,'國票'],
      [/玉山|E\.? Sun Securities/i,'玉山'],
      [/福邦/i,'福邦'],
      [/群益|Capital Securities/i,'群益'],
      [/合庫|Taiwan Cooperative Securities/i,'合庫'],
      [/Expert Room/i,'Expert Room']
    ];
    const parts=clean.split(/\s*[／/]\s*/).map(part=>{
      const hit=rules.find(([re])=>re.test(part));
      return hit?hit[1]:part.replace(/(?:證券投資顧問|投資顧問|證券|投顧|期貨|研究部|股份有限公司|有限公司)+$/g,'').replace(/(?:\s+(?:Securities|Brokerage|Research|Limited|Ltd\.?|Inc\.?|Co\.?|Corporation|Corp\.?))+$/i,'').trim();
    }).filter(Boolean);
    return [...new Set(parts)].join('／')||clean||'未標示券商';
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
      const raw=String(r.broker||'');
      const short=shortBroker(raw);
      const source=esc(date(r.report_date).slice(5).replace('-','/')+' '+short);
      const visible=(rate||result)+(r.needs_review?' ※':'');
      const detail=(r.needs_review?'同份報告數值不一致，待確認｜':'')+esc(date(r.report_date))+' '+link+'｜預估 '+estimate.toFixed(2)+unit+(metric==='eps'?'':'｜差 '+sign+delta.toFixed(2)+'pp');
      return '<details class="broker-inline-compact"><summary aria-label="'+esc(raw+' '+date(r.report_date)+' '+result)+'"><span class="broker-compact-source">'+source+'</span><span class="broker-inline-rate '+tone+'">'+esc(visible)+'</span></summary><div class="broker-inline-detail">'+detail+'</div></details>';
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
  // The catalog is authoritative only after an explicit publication-mode switch.
  // A shadow result must never silently replace the live financial comparison.
  function sharedRows(j,metric){
    if(j?.schema!==1||j.comparison_mode!=='production'||!Array.isArray(j.comparisons?.[metric]))return null;
    const rows=j.comparisons[metric];
    if(rows.some(r=>!r||!r.ticker||!date(r.announcement_date)||!date(r.report_date)||!r.actual_kind||!r.actual_period||num(r['actual_'+metric])===null||num(r['forecast_'+metric])===null))return null;
    return rows;
  }
  async function load(){
    if(loading)return loading;
    loading=(async()=>{
      let shared=null;
      try{const res=await fetch('./data/shared_financial_v1.json',{cache:'no-store'});if(res.ok)shared=await res.json();}catch(e){console.warn('[Shared financial catalog unavailable]',e);}
      return Promise.allSettled(specs.map(async ([metric,file])=>{
      let rows=sharedRows(shared,metric);
      if(rows===null){
        const res=await fetch('./data/'+file+'?v='+Math.floor(Date.now()/60000),{cache:'no-store'});
        if(!res.ok)throw Error(file+' '+res.status);
        const j=await res.json();rows=j.items||[];
      }
      const map=new Map();
      for(const r of rows){
        const k=key(r.ticker,r.actual_period||r.period,r.announcement_date,r.actual_kind);
        if(!map.has(k))map.set(k,[]);map.get(k).push(r);
      }
      for(const rows of map.values())rows.sort((a,b)=>String(b.report_date).localeCompare(String(a.report_date)));
      maps.set(metric,map);
    }));})().then(results=>{results.forEach(x=>{if(x.status==='rejected')console.warn('[Broker comparison]',x.reason);});render();}).finally(()=>{loading=null;});
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
