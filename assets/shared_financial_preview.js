/* Shadow adapter only: deliberately not loaded by production index. */
(function(root){
  'use strict';
  const safeRow=r=>r&&typeof r==='object'&&typeof r.metric==='string'&&/^20\d{2}(?:-Q[1-4])?$/.test(r.period)&&typeof r.value==='number'&&Number.isFinite(r.value)&&typeof r.unit==='string'&&typeof r.type==='string'&&typeof r.source==='string'&&typeof r.scope==='string'&&r.needs_review===false;
  function indexCatalog(catalog){
    if(!catalog||catalog.schema!==1||catalog.mode!=='shadow'||!Array.isArray(catalog.items))return null;
    const map=new Map();
    for(const row of catalog.items){
      if(!row||typeof row.report_id!=='string'||!row.report_id)continue;
      if(!map.has(row.report_id))map.set(row.report_id,[]);
      map.get(row.report_id).push(row);
    }
    return map;
  }
  function adapt(report,index){
    if(!report||typeof report!=='object'||!(index instanceof Map))return report;
    const rid=String(report.source_file_id||report.id||'');
    const rows=index.get(rid);
    if(!rows||!rows.length||rows.some(r=>!safeRow(r)))return report;
    // Never mix sources or attach a different company's figures.
    const ticker=String(report.ticker||'');
    if(!ticker||rows.some(r=>String(r.ticker||'')!==ticker))return report;
    const original=Array.isArray(report.financial_forecasts)?report.financial_forecasts:[];
    const key=r=>JSON.stringify([r.period,r.metric,r.metric_name||'',r.type,r.source,r.scope,r.unit,r.value]);
    const available=new Set(rows.map(key));
    if(original.some(r=>!available.has(key(r))))return report;
    return {...report,financial_forecasts:rows.map(r=>({...r})),shared_financial_preview:true};
  }
  root.SharedFinancialPreview={indexCatalog,adapt};
  if(typeof module!=='undefined')module.exports=root.SharedFinancialPreview;
})(typeof globalThis!=='undefined'?globalThis:this);
