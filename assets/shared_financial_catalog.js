/* Additive financial catalog. Missing/stale/invalid input leaves original data unchanged. */
(function(root){
'use strict';
const id=r=>String(r?.source_file_id||r?.id||'');
const day=r=>String(r?.date||r?.report_date||'').slice(0,10).replaceAll('/','-');
const key=r=>[r.period,r.metric].join('|');
const safe=r=>r&&r.type==='forecast'&&r.source==='broker'&&r.scope==='company'&&r.needs_review===false&&typeof r.value==='number'&&Number.isFinite(r.value)&&typeof r.unit==='string'&&r.unit&&typeof r.evidence==='string'&&r.evidence&&/^20\d{2}(?:-Q[1-4])?$/.test(r.period);
function index(j){
 if(j?.schema!==1||j.mode!=='verified_additive'||!Array.isArray(j.items))return null;
 const m=new Map();
 for(const r of j.items){if(!safe(r)||!r.report_id||!r.ticker)continue;if(!m.has(r.report_id))m.set(r.report_id,[]);m.get(r.report_id).push(r);}
 return m;
}
function additions(report,m){
 if(!report||!(m instanceof Map)||report.validation_status!=='verified'||report.report_type!=='company')return [];
 const rows=m.get(id(report))||[];
 const orig=Array.isArray(report.financial_forecasts)?report.financial_forecasts:[];
 const used=new Set(orig.map(key));
 for(const q of report.quarterly_eps||[])used.add(key({...q,metric:'eps'}));
 const grouped=new Map();
 for(const r of rows){
  if(String(r.ticker)!==String(report.ticker)||r.report_date!==day(report)||used.has(key(r)))continue;
  // New fallback rows must carry evidence; do not override existing facts.
  if(r.origin!=='saved_margin_fallback'||!['gross_margin','operating_margin'].includes(r.metric)||r.unit!=='%')continue;
  if(!grouped.has(key(r)))grouped.set(key(r),[]);
  grouped.get(key(r)).push(r);
 }
 return [...grouped.values()].filter(g=>g.every(x=>x.value===g[0].value&&x.unit===g[0].unit)).map(g=>g[0]);
}
function adapt(report,m){const rows=additions(report,m);return rows.length?{...report,financial_forecasts:[...(report.financial_forecasts||[]),...rows]}:report;}
let pending,current=null;
async function load(){if(!pending)pending=(async()=>{try{const res=await fetch('./data/shared_financial_v1.json',{cache:'no-store'});if(!res.ok)return null;current=index(await res.json());return current;}catch(e){return null;}})();return pending;}
function facts(report,m=current){
 if(!report||!(m instanceof Map))return [];
 return (m.get(id(report))||[]).filter(r=>String(r.ticker)===String(report.ticker)&&r.report_date===day(report));
}
root.SharedFinancialCatalog={index,adapt,additions,facts,load,current:()=>current};
if(typeof module!=='undefined')module.exports=root.SharedFinancialCatalog;
})(typeof globalThis!=='undefined'?globalThis:this);
