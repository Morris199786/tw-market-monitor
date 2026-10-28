/* Industry PDF reading layout. Pure rendering: no fetch, AI, or state writes. */
(function (root) {
  'use strict';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const strings = a => Array.isArray(a) ? a.filter(x => typeof x === 'string' && x.trim()) : [];
  const applies = r => ['sector', 'theme'].includes(r?.report_type);
  function render(r, text = esc) {
    if (!applies(r)) return '';
    const para = p => `<p>${text(p)}</p>`;
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
  root.IndustrySummary = {applies, render};
  if (typeof document !== 'undefined') {
    const style = document.createElement('style');
    style.textContent = `.industry-summary{min-width:0}.industry-summary section{margin:1.4em 0}.industry-summary h3{font-size:1.08em!important;line-height:1.5;margin:0 0 .65em!important;font-weight:700}.industry-summary p{white-space:pre-line!important;margin:0 0 .85em!important;line-height:1.75;overflow-wrap:anywhere}.industry-summary li{margin:.5em 0}.industry-table{overflow-x:auto;max-width:100%;margin:1em 0;-webkit-overflow-scrolling:touch}.industry-table table{border-collapse:collapse;width:100%;min-width:420px;font:inherit}.industry-table th,.industry-table td{padding:.65em;border:1px solid var(--line,#dce3eb);text-align:left;vertical-align:top;white-space:normal}.industry-table th{font-weight:700}.industry-table caption{text-align:left;font-weight:700;margin-bottom:.5em}.industry-note{color:var(--muted,#64748b);font-size:.9em}`;
    document.head.appendChild(style);
  }
})(typeof window === 'undefined' ? globalThis : window);
