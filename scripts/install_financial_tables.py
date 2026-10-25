#!/usr/bin/env python3
"""One-time idempotent website integration. Run at repository root.
Reads data/research_financial_forecasts.json in browser; no AI, no shard rewrite.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JS=ROOT/'assets/research_merged.js'
INDEX=ROOT/'index.html'
START='// BEGIN FINANCIAL FORECAST TABLES V2'
END='// END FINANCIAL FORECAST TABLES V2'
INSERT=r'''
// BEGIN FINANCIAL FORECAST TABLES V2
const financialLabels={revenue:'營收',revenue_yoy:'營收年增率',revenue_qoq:'營收季增率',gross_profit:'毛利',gross_margin:'毛利率',operating_profit:'營業利益',operating_margin:'營益率',pretax_profit:'稅前淨利',pretax_margin:'稅前淨利率',net_income:'稅後淨利',net_margin:'淨利率',eps:'EPS',roe:'ROE',roa:'ROA',operating_cash_flow:'營業現金流',free_cash_flow:'自由現金流',capex:'資本支出',dividend:'每股現金股利',pe:'本益比',pb:'本淨比'};
let financialPromise;
function financialData(){
  if(!financialPromise) financialPromise=fetch('./data/research_financial_forecasts.json',{cache:'no-cache'})
    .then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
    .then(x=>x&&x.reports&&typeof x.reports==='object'?x.reports:{})
    .catch(e=>{console.warn('Financial forecasts unavailable',e);return {}});
  return financialPromise;
}
function financialTables(records){
  if(!Array.isArray(records))return '';
  const data=records.filter(x=>x&&financialLabels[x.metric]&&/^20\d{2}(?:-Q[1-4])?$/.test(String(x.period||''))&&Number.isFinite(Number(x.value))&&x.confidence!=='conflict'&&(!x.segment||x.segment==='company'));
  const render=quarterly=>{
    const rows=data.filter(x=>String(x.period).includes('-Q')===quarterly);
    if(!rows.length)return '';
    const periods=[...new Set(rows.map(x=>String(x.period)))].sort();
    const metrics=Object.keys(financialLabels).filter(k=>rows.some(x=>x.metric===k));
    const lookup=new Map();
    for(const x of rows){const key=x.metric+'|'+x.period;if(!lookup.has(key))lookup.set(key,x)}
    const heads=periods.map(p=>'<th>'+escape(p.replace('-Q',' Q'))+'</th>').join('');
    const body=metrics.map(metric=>'<tr><th>'+escape(financialLabels[metric])+'</th>'+periods.map(p=>{
      const x=lookup.get(metric+'|'+p);
      if(!x)return '<td>—</td>';
      const value=Number(x.value).toLocaleString('en-US',{maximumFractionDigits:4});
      const unit=x.unit?' '+x.unit:'';
      return '<td title="'+escape([x.evidence,x.source_field].filter(Boolean).join(' | '))+'">'+escape(value+unit)+'</td>';
    }).join('')+'</tr>').join('');
    return section(quarterly?'季度財務數字':'年度財務數字','<div class="rm-table-hint">原始報告數字；F/E 為預估，缺漏以 — 顯示。表格可左右滑動。</div><div class="rm-table-wrap" tabindex="0"><table class="rm-financial"><thead><tr><th>指標</th>'+heads+'</tr></thead><tbody>'+body+'</tbody></table></div>');
  };
  return render(false)+render(true);
}
// END FINANCIAL FORECAST TABLES V2
'''

def replace_once(src,old,new):
    if old not in src:raise RuntimeError('找不到預期程式片段，為避免破壞網站已停止：'+old[:75])
    return src.replace(old,new,1)

def main():
    s=JS.read_text(encoding='utf-8')
    if START in s:
        print('Already installed; no changes');return
    s=replace_once(s,'function brokerFullDetail(r) {',INSERT+'\nfunction brokerFullDetail(r, financialRecords=[]) {')
    s=replace_once(s,"  return parts.join('');\n}\n\nfunction showDetail(r, m) {","  parts.push(financialTables([...(Array.isArray(r.financial_forecasts)?r.financial_forecasts:[]),...financialRecords]));\n  return parts.join('');\n}\n\nfunction showDetail(r, m, financialRecords=[]) {")
    s=replace_once(s,"if (r.source_kind === 'broker') return brokerFullDetail(r);","if (r.source_kind === 'broker') return brokerFullDetail(r,financialRecords);")
    s=replace_once(s,"return brokerFullDetail({...r.ai_research, date:r.date, source:r.source});","return brokerFullDetail({...r.ai_research, date:r.date, source:r.source},financialRecords);")
    s=replace_once(s,'  // Original PDF text stays in source data for auditing, not the reader UI.',"  html += financialTables([...(Array.isArray(ai.financial_forecasts)?ai.financial_forecasts:[]),...financialRecords]);\n\n  // Original PDF text stays in source data for auditing, not the reader UI.")
    s=replace_once(s,'    content.innerHTML = showDetail(r, m);',"    const financialRecords = (await financialData())[String(r.id)]?.forecasts || [];\n    if (dialog.hidden || opening !== readerSerial) return;\n    content.innerHTML = showDetail(r, m, financialRecords);")
    if s.count(START)!=1 or s.count(END)!=1:raise RuntimeError('Injection marker count incorrect')
    JS.write_text(s,encoding='utf-8')
    html=INDEX.read_text(encoding='utf-8')
    import re
    html2,n=re.subn(r'(src=["\']\./assets/research_merged\.js\?v=)[^"\']+',r'\g<1>20261025-financial-v2',html)
    if n!=1:raise RuntimeError('Cannot locate website JS version for cache bust')
    INDEX.write_text(html2,encoding='utf-8')
    print('Updated assets/research_merged.js and index.html; no OpenAI calls')
if __name__=='__main__':main()
