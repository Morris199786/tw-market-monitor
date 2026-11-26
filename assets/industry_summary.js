/* Industry PDF reading layout. Pure rendering: no fetch, AI, or state writes. */
(function (root) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const strings = a => Array.isArray(a) ? a.filter(x => typeof x === 'string' && x.trim()) : [];
  const applies = r => ['sector', 'theme'].includes(r?.report_type);
  function render(r, text = esc) {
    if (!applies(r)) return '';
    const para = p => prose(p,v=>emphasisText(v,r.emphasis,text));
    const list = a => `<ul>${strings(a).map(p => `<li>${text(p)}</li>`).join('')}</ul>`;
    const table = b => {
      if (!Array.isArray(b.headers) || !b.headers.length || !b.headers.every(x => typeof x === 'string') || !Array.isArray(b.rows) || !b.rows.length || !b.rows.every(row => Array.isArray(row) && row.length === b.headers.length && row.every(v => v == null || ['string','number'].includes(typeof v)))) return '';
      return `<div class="industry-table" tabindex="0" role="region" aria-label="${esc(b.title || '研究資料表')}"><table>${b.title ? `<caption>${text(b.title)}</caption>` : ''}<thead><tr>${b.headers.map(x => `<th scope="col">${text(x)}</th>`).join('')}</tr></thead><tbody>${b.rows.map(row => `<tr>${row.map(v => `<td>${text(v == null ? '—' : String(v))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${b.note ? `<p class="industry-note">${text(b.note)}</p>` : ''}`;
    };
    const block = b => {
      if (!b || typeof b !== 'object') return '';
      if (b.type === 'paragraph' && typeof b.text === 'string') return para(b.text);
      if (b.type === 'bullets') return list(b.items);
      if (b.type === 'table') return table(b);
      return '';
    };
    const section = (heading, body) => body ? `<section>${heading ? `<h3>${text(heading)}</h3>` : ''}${body}</section>` : '';
    let content = (Array.isArray(r.industry_sections) ? r.industry_sections : []).map(s => section(s?.heading, (Array.isArray(s?.blocks) ? s.blocks : []).map(block).join(''))).join('');
    if (!content) {
      // Legacy detail retains all analysis. Recognize only explicit newline headings;
      // never infer companies, values or new headings from sentences.
      const detail = typeof r.detail === 'string' ? r.detail.trim() : '';
      const chunks = detail.split(/\n\s*\n/).filter(Boolean);
      content = chunks.map(chunk => {
        const lines = chunk.split('\n');
        const heading = lines.length > 1 && lines[0].length <= 60 && !/[。！？；]/.test(lines[0]) ? lines.shift() : '';
        return section(heading, lines.map(para).join(''));
      }).join('');
      if (!content) content = (Array.isArray(r.research_sections) ? r.research_sections : []).map(s => section(s?.heading, strings(s?.paragraphs).map(para).join(''))).join('');
      for (const [key, label] of [['key_points','關鍵數據與依據'],['forecast_changes','財測調整'],['risks','風險與成立條件']]) {
        if (strings(r[key]).length) content += section(label, list(r[key]));
      }
      const tables = (Array.isArray(r.visualizations) ? r.visualizations : []).filter(v => v?.type === 'table').map(table).join('');
      if (tables) content += section('報告資料比較', tables);
    }
    return `<div class="industry-summary">${content || '<p>尚無完整摘要，請查看原始報告。</p>'}</div>`;
  }

  // Pure presentation: retain every sentence, never infer new facts or headings.
  function paragraphs(value) {
    const raw=String(value??'').replace(/\r\n?/g,'\n').trim();
    if(!raw)return [];
    const out=[];
    for(const line of raw.split(/\n+/)){
      const t=line.trim();if(!t)continue;
      const sentences=t.match(/[^。！？]+[。！？]*|[。！？]+/g)||[t];
      let buf='';
      for(const sentence of sentences){
        // Break only at sentence boundaries; decimals and English identifiers stay intact.
        if(buf&&buf.length+sentence.length>145){out.push(buf.trim());buf='';}
        buf+=sentence;
      }
      if(buf.trim())out.push(buf.trim());
    }
    return out;
  }
  function emphasisText(value, phrases, render=esc){
    const t=String(value??'');
    const words=[...new Set(strings(phrases))].sort((a,b)=>b.length-a.length);
    if(!words.length)return render(t);
    const hits=[];
    for(const word of words){let pos=0;while(pos<t.length){const i=t.indexOf(word,pos);if(i<0)break;hits.push([i,i+word.length]);pos=i+word.length;}}
    hits.sort((a,b)=>a[0]-b[0]||b[1]-a[1]);
    let end=0,html='';
    for(const [a,b] of hits){if(a<end)continue;html+=render(t.slice(end,a))+'<strong class="research-prose-emphasis">'+render(t.slice(a,b))+'</strong>';end=b;}
    return html+render(t.slice(end));
  }
  function prose(value,text=esc){
    const ps=paragraphs(value);
    return ps.map(p=>'<p class="research-prose-paragraph">'+text(p)+'</p>').join('');
  }
  function research(r,text=esc){
    const render=v=>emphasisText(v,r.emphasis,text);
    const block=s=>strings(s?.paragraphs).map(p=>prose(p,render)).join('');
    let html=(Array.isArray(r.research_sections)?r.research_sections:[]).map(s=>{
      const body=block(s);return body?'<section class="research-prose-section">'+(s.heading?'<h4>'+render(s.heading)+'</h4>':'')+body+'</section>':'';
    }).join('');
    const detail=typeof r.detail==='string'?r.detail.trim():'';
    if(html&&detail){
      // Preserve legacy detail as a collapsed supplement when not identical to the structured content.
      const compact=v=>String(v??'').replace(/\s+/g,'');
      const structured=(r.research_sections||[]).flatMap(s=>[s?.heading,...strings(s?.paragraphs)]).filter(Boolean).join('');
      if(compact(detail)!==compact(structured))html+='<details class="research-prose-extra"><summary>原有完整分析文字</summary>'+prose(detail,render)+'</details>';
    }else if(!html&&detail){
      // Only recognize headings explicitly separated from the prose; never generate titles.
      html=detail.split(/\n\s*\n/).filter(x=>x.trim()).map(chunk=>{
        const lines=chunk.trim().split('\n');
        const heading=lines.length>1&&lines[0].trim().length<=55&&!/[。！？；]/.test(lines[0])?lines.shift().trim():'';
        return '<section class="research-prose-section">'+(heading?'<h4>'+render(heading)+'</h4>':'')+prose(lines.join('\n'),render)+'</section>';
      }).join('');
    }
    return html?'<div class="research-prose">'+html+'</div>':'';
  }
  root.IndustrySummary = {applies, render, research, prose, emphasisText, paragraphs};
  if (typeof document !== 'undefined') {
    const style = document.createElement('style');
    style.textContent = `.industry-summary{min-width:0}.industry-summary section{margin:1.4em 0}.industry-summary h3{font-size:1.08em!important;line-height:1.5;margin:0 0 .65em!important;font-weight:700}.industry-summary p{white-space:pre-line!important;margin:0 0 .85em!important;line-height:1.75;overflow-wrap:anywhere}.industry-summary li{margin:.5em 0}.industry-table{overflow-x:auto;max-width:100%;margin:1em 0;-webkit-overflow-scrolling:touch}.industry-table table{border-collapse:collapse;width:100%;min-width:420px;font:inherit}.industry-table th,.industry-table td{padding:.65em;border:1px solid var(--line,#dce3eb);text-align:left;vertical-align:top;white-space:normal}.industry-table th{font-weight:700}.industry-table caption{text-align:left;font-weight:700;margin-bottom:.5em}.industry-note{color:var(--muted,#64748b);font-size:.9em}`;
    style.textContent+=".research-prose{min-width:0}.research-prose-section{margin:14px 0}.research-prose-section+.research-prose-section{border-top:1px solid var(--line,#e2e8f0);padding-top:12px}.research-prose-section h4{font-size:1em!important;font-weight:750;margin:0 0 8px!important;line-height:1.5}.research-prose-paragraph{margin:0 0 .85em!important;line-height:1.75;overflow-wrap:anywhere;white-space:pre-wrap}.research-prose-emphasis{font-weight:750;text-decoration:underline;text-decoration-color:#d69b30;text-underline-offset:3px}.research-prose-extra{margin:12px 0}.research-prose-extra>summary{cursor:pointer;font-weight:600;color:var(--muted,#64748b)}";document.head.appendChild(style);
  }
})(typeof window === 'undefined' ? globalThis : window);
