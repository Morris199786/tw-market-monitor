/* 產業資料庫：Excel 一句話故事列表、全螢幕閱讀、歷史索引搜尋。無 AI 呼叫。 */
(() => {
'use strict';

const root = document.getElementById('reports');
const legacy = document.getElementById('reportList');

if (!root || !legacy) return;

const categories = [
  '個股研究',
  '產業研究',
  '法說／訪談',
  '週報',
  '市場情報',
  '券商報告'
];

const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}[c]));

const clean = s => String(s ?? '')
  .trim()
  .replace(/^(null|none|nan)$/i, '');

const norm = s => clean(s)
  .normalize('NFKC')
  .toLocaleLowerCase();

const panel = document.createElement('section');
panel.id = 'researchMergedPanel';

panel.innerHTML = `
  <div class="rm-toolbar">
    <div class="rm-cats">
      ${categories.map(c => `
        <button class="rm-chip" data-category="${escape(c)}">
          ${escape(c)}
        </button>
      `).join('')}
      <button class="rm-chip" data-market="US">美股</button>
    </div>

    <div class="rm-search">
      <input
        type="search"
        id="rmQuery"
        placeholder="搜尋報告：公司、代號、標題、券商"
        autocomplete="off"
      >
      <button id="rmClear">清除</button>
    </div>

    <div class="rm-meta" id="rmMeta">
      載入研究索引中…
    </div>
  </div>

  <div id="rmCards"></div>
  <button id="rmMore" hidden>顯示更多</button>
`;

legacy.parentNode.insertBefore(panel, legacy);

const dialog = document.createElement('div');
dialog.id = 'rmReader';
dialog.hidden = true;

dialog.innerHTML = `
  <div class="rm-reader-header">
    <div id="rmReaderTitle"></div>
    <button id="rmClose" aria-label="關閉閱讀視窗">✕</button>
  </div>
  <div id="rmReaderContent"></div>
`;

document.body.appendChild(dialog);

const css = document.createElement('style');

css.textContent = `
#researchMergedPanel {
  font: 14px/1.65 -apple-system, BlinkMacSystemFont, "Noto Sans TC", sans-serif;
  color: #243246;
  margin: 12px 0 24px;
}

#researchMergedPanel * {
  box-sizing: border-box;
}

#researchMergedPanel .rm-toolbar {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
}

#researchMergedPanel .rm-cats {
  display: flex;
  gap: 7px;
  overflow-x: auto;
  padding: 3px 0 8px;
  scrollbar-width: none;
}

#researchMergedPanel .rm-cats::-webkit-scrollbar {
  display: none;
}

#researchMergedPanel button,
#researchMergedPanel input {
  font: inherit;
}

#researchMergedPanel .rm-chip {
  flex: none;
  border: 1px solid #d4dce7;
  background: #fff;
  color: #273449;
  border-radius: 22px;
  padding: 7px 12px;
  white-space: nowrap;
  font-size: 13px;
}

#researchMergedPanel .rm-chip.active {
  background: #205fcd;
  border-color: #205fcd;
  color: #fff;
}

#researchMergedPanel .rm-search {
  display: flex;
  gap: 8px;
}

#researchMergedPanel #rmQuery {
  min-width: 0;
  flex: 1;
  background: #fff;
  color: #243246;
  border: 1px solid #d4dce7;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
}

#researchMergedPanel #rmClear,
#researchMergedPanel #rmMore {
  border: 1px solid #d4dce7;
  background: #fff;
  color: #243246;
  border-radius: 10px;
  padding: 10px 13px;
}

#researchMergedPanel .rm-meta {
  font-size: 12px;
  color: #64748b;
}

#researchMergedPanel .rm-date {
  font-weight: 700;
  margin: 20px 0 8px;
  font-size: 14px;
}

#researchMergedPanel .rm-card {
  border: 1px solid #dce3eb;
  background: #fff;
  border-radius: 13px;
  padding: 14px;
  margin: 9px 0;
  overflow-wrap: anywhere;
}

#researchMergedPanel .rm-title {
  font-size: 17px;
  font-weight: 750;
  line-height: 1.45;
}

#researchMergedPanel .rm-sub {
  color: #64748b;
  font-size: 12px;
  margin: 5px 0 10px;
}

#researchMergedPanel .rm-story {
  font-size: 14px;
  line-height: 1.7;
  display: block;
  white-space: normal;
}

#researchMergedPanel .rm-open {
  margin-top: 10px;
  border: 0;
  border-radius: 8px;
  background: #eaf1ff;
  color: #2058bb;
  padding: 8px 12px;
  font-weight: 650;
}

#researchMergedPanel #rmMore {
  width: 100%;
  margin-top: 12px;
}

#researchMergedPanel #rmMore[hidden] {
  display: none;
}

#rmReader[hidden] {
  display: none;
}

#rmReader {
  position: fixed;
  inset: 0;
  z-index: 2147483000;
  background: #f7f9fc;
  color: #243246;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  font: 15px/1.8 -apple-system, BlinkMacSystemFont, "Noto Sans TC", sans-serif;
}

#rmReader * {
  box-sizing: border-box;
}

#rmReader .rm-reader-header {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: #fff;
  border-bottom: 1px solid #e1e6ee;
  padding: calc(12px + env(safe-area-inset-top)) 16px 12px;
}

#rmReaderTitle {
  font-size: 17px;
  font-weight: 750;
  line-height: 1.35;
  min-width: 0;
  overflow-wrap: anywhere;
  flex: 1;
}

#rmClose {
  flex: none;
  border: 1px solid #dce3eb;
  background: #fff;
  color: #233247;
  border-radius: 50%;
  width: 44px;
  height: 44px;
  position: relative;
  z-index: 3;
  font-size: 21px;
}

#rmReaderContent {
  max-width: 900px;
  margin: auto;
  padding: 18px 15px calc(28px + env(safe-area-inset-bottom));
}

#rmReader .rm-hero {
  padding: 16px;
  background: #edf4ff;
  border-radius: 13px;
  margin-bottom: 18px;
}

#rmReader .rm-info {
  color: #64748b;
  font-size: 13px;
  margin-bottom: 10px;
}

#rmReader .rm-section {
  background: #fff;
  border: 1px solid #e3e8f0;
  border-radius: 13px;
  padding: 15px;
  margin: 12px 0;
  overflow-wrap: anywhere;
}

#rmReader h3 {
  font-size: 16px;
  margin: 0 0 10px;
  color: #1d3554;
}

#rmReader .rm-paragraph {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
}

#rmReader .rm-table-wrap {
  max-width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

#rmReader table {
  border-collapse: collapse;
  min-width: 260px;
  width: 100%;
  font-size: 14px;
}

#rmReader th,
#rmReader td {
  border-bottom: 1px solid #e6ebf2;
  text-align: left;
  padding: 9px 10px;
  vertical-align: top;
}

#rmReader th {
  background: #f3f6fa;
  width: 36%;
  font-weight: 650;
}

#rmReader .rm-original {
  border: 0;
  background: #edf4ff;
  color: #2058bb;
  padding: 10px 12px;
  border-radius: 8px;
  font: inherit;
}

#rmReader .rm-original-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin-top: 14px;
  font-size: 14px;
}

#rmReader .rm-paragraph, #rmReader .rm-original-text { white-space: normal; }
#rmReader .rm-prose { text-align: left; line-height: 1.75; }
#rmReader .rm-prose p { margin: 0 0 .8em; text-indent: 0; }
#rmReader .rm-prose p:last-child { margin-bottom: 0; }
#rmReader .rm-hero strong { display: block; margin-bottom: 10px; }
#rmReader .rm-financial { width: max-content; min-width: 100%; font-variant-numeric: tabular-nums; }
#rmReader .rm-financial th, #rmReader .rm-financial td { width: auto; white-space: nowrap; padding: 9px 12px; }
#rmReader .rm-financial td { text-align: right; }
#rmReader .rm-financial tbody th { position: sticky; left: 0; max-width: 170px; white-space: normal; min-width: 110px; }
#rmReader .rm-financial tbody tr:nth-child(even) td { background: #f8fafc; }
#rmReader .rm-table-hint { font-size: 12px; color: #64748b; margin: 14px 0 6px; }
#rmReader .rm-unmapped { font-variant-numeric: tabular-nums; padding: 0; white-space: pre-wrap; }
@media (max-width: 600px) {
 #rmReaderContent { padding: 12px 12px 30px; }
 #rmReader .rm-section { padding: 12px; }
 #rmReader .rm-section > .rm-table-wrap > table:not(.rm-financial) th { width: 28%; padding: 8px; }
}

#researchMergedPanel .rm-story, #rmReader .rm-prose { overflow-wrap: anywhere; }
#researchMergedPanel .rm-story p { margin: 0 0 10px; }
#researchMergedPanel .rm-company, #rmReader .rm-company { margin: 14px 0; padding-top: 12px; border-top: 1px solid #dce3eb; }
#researchMergedPanel h4, #rmReader h4 { margin: 0 0 6px; font-size: 15px; }
#researchMergedPanel h4 span, #rmReader h4 span { font-weight: 400; color: #64748b; }
#rmReader .rm-note, #researchMergedPanel .rm-note { color: #64748b; font-size: 13px; }
#rmReader .rm-reader-header { width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) 44px; }
#rmReaderContent, #rmReader .rm-section, #rmReader .rm-hero { min-width: 0; max-width: 100%; }
#rmReader .rm-table-wrap { width: 100%; }
#rmReader .rm-raw { margin-top: 20px; }
#rmReader .rm-raw pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
#researchMergedPanel .rm-table-wrap { max-width: 100%; overflow-x: auto; }
#researchMergedPanel .rm-financial { border-collapse: collapse; font-size: 13px; }
#researchMergedPanel .rm-financial th, #researchMergedPanel .rm-financial td { padding: 5px 10px; border-bottom: 1px solid #dce3eb; }
#researchMergedPanel .rm-financial td { text-align: right; }
#rmReader .rm-financial .rm-uncertain { white-space: normal; color: #64748b; text-align: left; }
body.rm-reader-open {
  overflow: hidden;
}

@media (min-width: 700px) {
  #rmReaderContent {
    padding: 26px 24px;
  }

  #rmReader .rm-section {
    padding: 22px;
  }
}
`;

document.head.appendChild(css);

const cards = panel.querySelector('#rmCards');
const meta = panel.querySelector('#rmMeta');
const more = panel.querySelector('#rmMore');
const input = panel.querySelector('#rmQuery');

let manifest = null;
let rows = [];
let category = '';
let market = 'TW';
let query = '';
let matches = [];
let limit = 30;
let serial = 0;
let readerSerial = 0;
let initialized = false;
let lastScroll = 0;


const shardCache = new Map();

async function fetchJSON(url) {
  const r = await fetch(url, { cache: 'no-cache' });

  if (!r.ok) {
    throw Error(`${r.status} ${url}`);
  }

  return r.json();
}

const cutoff = () => {
  const d = new Date();

  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - 6);

  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, '0'),
    String(d.getDate()).padStart(2, '0')
  ].join('-');
};

function visible() {
  return matches.filter(i => {
    const row = rows[i];

    if (!row) return false;
    if (row.market !== market) return false;
    if (category && row.category !== category) return false;

    return true;
  });
}

function render() {
  panel.querySelectorAll('[data-category]').forEach(b => {
    b.classList.toggle(
      'active',
      b.dataset.category === category
    );
  });

  panel.querySelector('[data-market]').classList.toggle(
    'active',
    market === 'US'
  );

  const list = visible();

  meta.textContent =
    `${query ? '歷史搜尋' : category === '週報' ? '歷史週報' : market === 'US' ? '近七天美股' : '近七天台股'}` +
    `｜符合 ${list.length} 筆` +
    `｜資料庫 ${manifest?.count ?? rows.length} 筆`;

  cards.replaceChildren();

  let date = '';

  for (const i of list.slice(0, limit)) {
    const m = rows[i];

    if (m.date !== date) {
      date = m.date;

      const d = document.createElement('div');
      d.className = 'rm-date';
      d.textContent = date || '日期未明';

      cards.appendChild(d);
    }

    const card = document.createElement('article');
    card.className = 'rm-card';

    card.innerHTML = `
      <div class="rm-title">
        ${escape(
          reportTitle(m)
        )}
      </div>

      <div class="rm-sub">
        ${escape(m.date)}
        ${escape(m.source)}
        ${escape(m.category)}
      </div>

      <div class="rm-story">
        ${summaryHTML(m, m)}
      </div>

      <button class="rm-open" type="button">
        閱讀全文 →
      </button>
    `;

    card.querySelector('button').addEventListener(
      'click',
      () => openReader(m)
    );

    cards.appendChild(card);
    if (isMulti(m) || contaminated(textValue(m.story))) {
      shard(m.file).then(items => {
        if (!card.isConnected) return;
        const detail = items.find(x => String(x.id) === String(m.id));
        if (detail) card.querySelector('.rm-story').innerHTML = summaryHTML(detail, m);
      }).catch(() => {});
    }
  }

  more.hidden = list.length <= limit;
}

function defaultMatches() {
  const since = cutoff();

  matches = rows
    .map((r, i) => {
      return (
        (category === '週報' || r.date >= since) &&
        r.market === market
      ) ? i : -1;
    })
    .filter(i => i >= 0);

  limit = 30;
  render();
}

// Deliberately exclude story, full text and extracted financial fields.
function reportMatches(row, term) {
  const fields = [row.company, row.ticker, row.title, row.report_title,
    row.source, row.industry, row.category].map(norm);
  return norm(term).split(/\s+/).filter(Boolean).every(word =>
    fields.some(value => /^\d{4,6}$/.test(word)
      ? value.split(/[^a-z0-9]+/).includes(word)
      : value.includes(word)));
}

async function search(term, token) {
  if (token !== serial) return;
  if (!norm(term)) { defaultMatches(); return; }
  matches = rows.map((row, i) => reportMatches(row, term) ? i : -1)
    .filter(i => i >= 0)
    .sort((a, b) => String(rows[b].date).localeCompare(String(rows[a].date)));
  limit = 30;
  render();
}

async function shard(file) {
  if (!shardCache.has(file)) {
    const task = fetchJSON(
      `./data/research_shards/${encodeURIComponent(file)}`
    )
      .then(x => x.items || [])
      .catch(e => {
        shardCache.delete(file);
        throw e;
      });

    shardCache.set(file, task);

    if (shardCache.size > 5) {
      shardCache.delete(
        shardCache.keys().next().value
      );
    }
  }

  return shardCache.get(file);
}

const fields = [
  ['revenue', '營收／成長率'],
  ['eps', 'EPS／獲利'],
  ['inventory', '庫存／出貨'],
  ['utilization', '產能利用率／稼動率'],
  ['guidance', '未來展望'],
  ['trend', '產業趨勢／題材'],
  ['rating_target', '評等／目標價'],
  ['numbers', '關鍵數字'],
  ['dividend_current', '今年現金股利預估'],
  ['dividend_next', '明年現金股利預估'],
  ['dividend_policy', '股利政策']
];

function section(title, html) {
  return `
    <section class="rm-section">
      <h3>${escape(title)}</h3>
      ${html}
    </section>
  `;
}


function textValue(value) {
  if (Array.isArray(value)) return value.map(textValue).filter(Boolean).join('\n\n');
  const text = clean(value);
  if (!/^\[.*\]$/s.test(text)) return text;
  try { const v = JSON.parse(text); if (Array.isArray(v)) return textValue(v); } catch (_) {}
  // Parse Python-style quoted lists without eval or stripping real quotations.
  const parts = []; let pos = 1;
  while (pos < text.length - 1) {
    while (/\s/.test(text[pos])) pos++;
    const quote = text[pos++]; if (quote !== "'" && quote !== '"') return text;
    let item = '', closed = false;
    while (pos < text.length) {
      const ch = text[pos++];
      if (ch === '\\') { const next = text[pos++]; item += next === 'n' ? '\n' : next === 't' ? '\t' : next; }
      else if (ch === quote) { closed = true; break; } else item += ch;
    }
    if (!closed) return text;
    parts.push(item);
    while (/\s/.test(text[pos])) pos++;
    if (text[pos] === ']') break;
    if (text[pos++] !== ',') return text;
  }
  return parts.join('\n\n');
}
function isMulti(m) { return /多檔|聚合/.test(m.company || '') || /[;；]/.test(m.ticker || ''); }
function reportTitle(m) {
  const title = clean(m.title || m.company).replace(/^[（(]多檔聚合[）)]/, '');
  return isMulti(m) ? title || '多公司研究' : [title, clean(m.ticker).replace(/\.(?:TW|TWO)\b/g, '')].filter(Boolean).join(' ');
}
function contaminated(t) {
  return /著作權|禁止任何形式|金管投顧|IFRS\s+IFRS|Comprehensive Income Statement|前次\s+本次\s+前次|Analyst Certification/i.test(t);
}
function prepareText(t) {
  // Preserve source line breaks. Recover inline headers only at explicit period runs.
  const result = t.replace(/((?:(?:20\d{2}[FEfeAa]?|[1-4]Q\d{2,4}[FEfe]?|FY\d{2,4}[FEfe]?)\s+){2,}(?:20\d{2}[FEfeAa]?|[1-4]Q\d{2,4}[FEfe]?|FY\d{2,4}[FEfe]?))/g, '\n$1\n')
    .replace(/(?:IFRS\s*){2,}/g, '\n');
  if (t.split('\n').length > 8) return result;
  return result.replace(/\s+(?=(?:Net sales|Gross profit|Operating profit|Total non-ope inc\.|Pre-tax profit|Net profit|Net Income|EPS(?: Change)?|Consensus EPS|Dividend \/ Share|Free Cash Flow \/ Share|P\/E|Dividend Yield|EV \/ EBITDA|Free Cash Flow Yield)\b)/gi, '\n');
}
function companyParts(t, m) {
  const codes = new Set((m.ticker || '').match(/\b\d{4,6}(?=\.|\b)/g) || []);
  const re = /([\u3400-\u9fffA-Za-z][\u3400-\u9fffA-Za-z-]{0,15})\s*[（(](\d{4,6})(?:\.(?:TW|TWO|TT))?[）)]|(?:^|[\n;；/])\s*[-•●]?\s*(\d{4,6})\s*([\u3400-\u9fffA-Za-z][\u3400-\u9fffA-Za-z-]{0,12})\s*[:：]/gm;
  const hits = [...t.matchAll(re)].map(x => ({at:x.index,end:x.index+x[0].length,name:x[1] || x[4],code:x[2] || x[3]})).filter(x => !codes.size || codes.has(x.code));
  const result = [];
  for (let i=0;i<hits.length;i++) {
    const h=hits[i]; const body=t.slice(h.end,hits[i+1]?.at ?? t.length).replace(/^[\s:：]+|[;；\s]+$/g,'');
    const existing=result.find(x=>x.code===h.code);
    if (existing) existing.body+='\n'+body; else result.push({...h,body});
  }
  return result;
}
function compactCompany(body) {
  const sentences = punctuate(body).split(/\n+|(?<=[。；])/).map(x=>x.trim()).filter(Boolean);
  const metrics=sentences.filter(x=>/EPS|每股盈餘|獲利預估|目標價|目標價格|評等|降評|升評|\bTP\b/i.test(x) && !contaminated(x));
  return (metrics.length ? metrics : sentences.filter(x=>!contaminated(x)).slice(0,1)).join('\n\n');
}
function epsFromTables(text) {
  const lines=prepareText(text).split('\n').map(x=>x.trim());
  for(let i=0;i<lines.length;i++) {
    const t=tableAt(lines,i);
    if (!t) continue;
    const eps=t.rows.find(r=>!r.unaligned && /^EPS(?:\s|$)/i.test(r.label || ''));
    if (eps && !/Y\/Y|Q\/Q|Margins/i.test(t.heading)) {
      return `<div class="rm-table-wrap"><table class="rm-financial"><thead><tr><th>期間</th><th>EPS（原報告單位）</th></tr></thead><tbody>${t.periods.map((p,j)=>`<tr><th>${escape(p)}${/[FE]$/i.test(p)?'（預估）':''}</th><td>${escape(eps.values[j])}</td></tr>`).join('')}</tbody></table></div>`;
    }
    i=t.end-1;
  }
  return '';
}
function summaryHTML(r, m) {
  const d=r.display || {};
  const story=textValue(d.story || r.story || m.story);
  const full=[d.full_text ?? r.full_text,d.full_text_2 ?? r.full_text_2,d.full_text_3 ?? r.full_text_3].map(textValue).join('\n');
  if (isMulti(m)) {
    const a=companyParts(story,m), b=companyParts(full,m);
    const parts=b.length>a.length ? b : a;
    if (parts.length) {
      const known=new Set(parts.map(p=>p.code));
      const missing=[...new Set((m.ticker || '').match(/\b\d{4,6}(?=\.)/g) || [])].filter(c=>!known.has(c));
      return parts.map(p=>`<div class="rm-company"><h4>${escape(p.name)} <span>${escape(p.code)}</span></h4>${readable(compactCompany(p.body) || '原文未提供可辨識重點，請查看全文。')}</div>`).join('')+
        (missing.length?`<p class="rm-note">其他公司（${escape(missing.join('、'))}）摘要尚無法可靠拆分，請查看全文。</p>`:'');
    }
  }
  if (contaminated(story)) {
    const tableSummary = epsFromTables(full);
    const values=[['eps','EPS／獲利'],['rating_target','評等／目標價']].map(([k,label])=>({label,value:textValue(d[k] ?? r[k])})).filter(x=>x.value && !contaminated(x.value));
    return (tableSummary + values.filter(x=>!tableSummary || x.label !== 'EPS／獲利').map(x=>`<p><strong>${escape(x.label)}</strong></p>${readable(x.value)}`).join('')) || '<p class="rm-note">原摘要混入表格或聲明，暫不作為研究重點。請查看下方完整研究內容與財務資料。</p>';
  }
  return readable(story || '此篇研究尚無摘要，請查看全文。');
}

// Preserve English punctuation and numeric thousands separators.
function punctuate(value) {
  return clean(value).split('\n').map(line => {
    if (!/[\u3400-\u9fff]/.test(line)) return line;
    return line.replace(/,(?!\d{3}(?:\D|$))/g, '，')
      .replace(/，\s+/g, '，').replace(/;/g, '；').replace(/:(?!\/\/|\d{2}\b)/g, '：');
  }).join('\n');
}

const periodPattern = /^(?:20\d{2}[FEfeAa]?|[1-4]Q\d{2,4}[FEfe]?|Q[1-4](?:FY)?\d{2,4}[FEfe]?|FY\d{2,4}[FEfe]?|12\/\d{2}[EeFf]?)$/;
const numberPattern = /^(?:\(?[-+−]?\d[\d,]*(?:\.\d+)?\)?[%xX]?|[-–—]|N\/?A)$/i;
function periodTokens(line) {
  return line.trim().split(/\s+/);
}
function isPeriods(line) {
  const t = periodTokens(line);
  return t.length > 0 && t.every(x => periodPattern.test(x));
}

// Build a table only with explicit periods and an exact value count per row.
function tableAt(lines, start) {
  let first = lines[start].replace(/^(?:Fiscal Year Ending|Y\/Y\s*%|Q\/Q\s*%)\s*/i, '');
  if (!isPeriods(first)) return null;
  const heading = lines[start].slice(0, lines[start].length - first.length).trim();
  let periods = periodTokens(first), pos = start + 1;
  while (pos < lines.length && isPeriods(lines[pos])) periods.push(...periodTokens(lines[pos++]));
  if (periods.length < 2) return null;
  while (pos < lines.length && (!lines[pos] || /^(?:IFRS\s*)+$/.test(lines[pos]))) pos++;
  const rows = [];
  while (pos < lines.length) {
    const rowStart = pos;
    if (/^Valuation\s*\(Dec\)$/i.test(lines[pos]) && rows.length) {
      rows.push({section: lines[pos++]}); continue;
    }
    let text = lines[pos], parsed = null;
    // PDF can wrap the label or values over several physical lines.
    for (let n = 0; n < 16 && pos + n < lines.length; n++) {
      if (n) {
        const next = lines[pos + n];
        if (!next || isPeriods(next) || /^(?:Y\/Y|Q\/Q|Fiscal Year)/i.test(next)) break;
        if (/\d(?:[%xX)]?)(?:\s|$)/.test(text) && !next.split(/\s+/).every(x => numberPattern.test(x))) break;
        text += ' ' + next;
      }
      const tokens = text.trim().replace(/\)(?=[-+]?\d)/g, ') ').split(/\s+/);
      let split = tokens.length;
      while (split > 0 && numberPattern.test(tokens[split - 1])) split--;
      const values = tokens.slice(split);
      const label = tokens.slice(0,split).join(' ');
      if (!label || values.length < 2) continue;
      if (values.length === periods.length && values.every(x => numberPattern.test(x)) && /[a-z\u3400-\u9fff]/i.test(label)) {
        parsed = {label, values, end: pos + n + 1}; break;
      }
      if (n === 0 && values.length !== periods.length && /[a-z\u3400-\u9fff]/i.test(label) &&
          !/\d+\s+\d+/.test(label) && !(lines[pos+1] || '').trim().split(/\s+/).every(x=>numberPattern.test(x))) {
        parsed = {label, values, unaligned: true, end: pos+1}; break;
      }
      if (values.length > periods.length) break;
    }
    if (!parsed) { pos = rowStart; break; }
    rows.push(parsed); pos = parsed.end;
  }
  if (rows.length < 2) return null;
  return {end: pos, periods, rows, heading, html: `<div class="rm-table-hint">${escape(heading || '財務數據')} · 可左右滑動；F／e 為原報告預估標記，單位依原文</div><div class="rm-table-wrap" tabindex="0" role="region" aria-label="財務數據表"><table class="rm-financial"><thead><tr><th scope="col">項目</th>${periods.map(p => `<th scope="col">${escape(p)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => r.section ? `<tr><th colspan="${periods.length+1}">${escape(r.section)}</th></tr>` : `<tr><th scope="row">${escape(r.label)}</th>${r.unaligned ? `<td colspan="${periods.length}" class="rm-uncertain">${escape(r.values.join(' ／ '))}（原文欄位不足，未配對年度）</td>` : r.values.map(v => `<td>${escape(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`};
}

function readable(value) {
  const lines = prepareText(textValue(value)).replace(/\r/g, '').split('\n').map(x => x.trim());
  const out = []; let paragraph = '';
  const flush = () => { if (paragraph) out.push(`<p>${escape(punctuate(paragraph))}</p>`); paragraph = ''; };
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    const table = tableAt(lines, i);
    if (table) { flush(); out.push(table.html); i = table.end; continue; }
    i++;
    if (!line) { flush(); continue; }
    // Ambiguous numeric rows remain literal, never assigned to guessed periods.
    if ((line.match(/\b\d+(?:\.\d+)?\b/g) || []).length >= 5) {
      flush(); out.push(`<p class="rm-unmapped">${escape(line)}</p>`); continue;
    }
    const heading = /[：:]$/.test(line) || /^[●⚫■◆•]/.test(line);
    if (heading) flush();
    if (paragraph) {
      const join = /[\u3400-\u9fff，；、]$/.test(paragraph) && /^[\u3400-\u9fff，。；、]/.test(line) || /^[，。；、,;]/.test(line) ? '' : ' ';
      paragraph += join;
    }
    paragraph += line;
    if (heading || /[。！？.!?]$/.test(line)) flush();
  }
  flush();
  return `<div class="rm-prose">${out.join('')}</div>`;
}

function displayText(value) { return readable(value); }

function showDetail(r, m) {
  const d = r.display || {};

  let html = `<div class="rm-info">${escape(m.date)} · ${escape(m.source)} · ${escape(m.category)}</div>`;
  html += `<div class="rm-hero"><strong>研究重點</strong>${summaryHTML(r, m)}</div>`;
  const data = fields
    .map(([k, title]) => ({
      title,
      value: textValue(d[k] ?? r[k])
    }))
    .filter(x => x.value && !contaminated(x.value));

  if (data.length && !isMulti(m)) {
    html += section(
      '研究數據與分析',
      `
        <div class="rm-table-wrap">
          <table>
            <tbody>
              ${data.map(x => `
                <tr>
                  <th>${escape(x.title)}</th>
                  <td>${displayText(x.value)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `
    );
  }

  const full = [
    d.full_text ?? r.full_text,
    d.full_text_2 ?? r.full_text_2,
    d.full_text_3 ?? r.full_text_3
  ]
    .map(textValue)
    .filter(Boolean);

  if (full.length) {
    html += section(
      '原始研究內容',
      `
        <button
          class="rm-original"
          id="rmShowOriginal"
        >
          顯示原始研究全文 ▼
        </button>

        <div
          class="rm-original-text"
          id="rmOriginal"
          hidden
        >${full.map(displayText).join('')}<details class="rm-raw"><summary>查看未整理原文</summary><pre>${escape(full.join('\n\n'))}</pre></details></div>
      `
    );
  }

  return html || section(
    '研究內容',
    '尚無可顯示的資料'
  );
}

async function openReader(m) {
  const readerToken = ++readerSerial;
  lastScroll = window.scrollY;

  dialog.hidden = false;
  document.body.classList.add(
    'rm-reader-open'
  );

  dialog.scrollTop = 0;

  dialog.querySelector(
    '#rmReaderTitle'
  ).textContent = reportTitle(m);

  const content = dialog.querySelector(
    '#rmReaderContent'
  );

  content.textContent = '載入研究內容中…';

  try {
    const items = await shard(m.file);

    if (dialog.hidden || readerToken !== readerSerial) return;

    const r = items.find(
      x => String(x.id) === String(m.id)
    );

    if (!r) {
      throw Error('找不到這篇研究');
    }

    content.innerHTML = showDetail(r, m);

    const toggle = content.querySelector(
      '#rmShowOriginal'
    );

    if (toggle) {
      toggle.addEventListener('click', () => {
        const el = content.querySelector(
          '#rmOriginal'
        );

        el.hidden = !el.hidden;

        toggle.textContent = el.hidden
          ? '顯示原始研究全文 ▼'
          : '收起原始研究全文 ▲';
      });
    }
  } catch (e) {
    content.textContent =
      '讀取失敗：' + e.message;
  }
}

function closeReader() {
  dialog.hidden = true;

  document.body.classList.remove(
    'rm-reader-open'
  );

  window.scrollTo(0, lastScroll);
}

dialog.querySelector(
  '#rmClose'
).addEventListener(
  'click',
  closeReader
);

document.addEventListener(
  'keydown',
  e => {
    if (
      e.key === 'Escape' &&
      !dialog.hidden
    ) {
      closeReader();
    }
  }
);

async function init() {
  if (initialized) return;

  initialized = true;

  try {
    [manifest, rows] = await Promise.all([
      fetchJSON('./data/research_manifest.json'),
      fetchJSON('./data/research_meta.json')
    ]);

    defaultMatches();
  } catch (e) {
    initialized = false;

    meta.textContent =
      '研究索引載入失敗：' + e.message;
  }
}

function sync() {
  const rating = document.getElementById(
    'twRatingsPanel'
  );

  const active = root.classList.contains(
    'active'
  );

  const ratingOn = rating && !rating.hidden;

  panel.hidden = !active || ratingOn;

  if (active && !ratingOn) {
    legacy.hidden = true;
    init();
  } else if (ratingOn) {
    legacy.hidden = true;
  } else {
    legacy.hidden = false;
  }
}

const observer = new MutationObserver(sync);

observer.observe(root, {
  attributes: true,
  attributeFilter: ['class']
});

const rating = document.getElementById(
  'twRatingsPanel'
);

if (rating) {
  observer.observe(rating, {
    attributes: true,
    attributeFilter: ['hidden']
  });
}

panel.querySelectorAll(
  '[data-category]'
).forEach(b => {
  b.addEventListener('click', () => {
    category = category === b.dataset.category
      ? ''
      : b.dataset.category;

    if (!query) {
      defaultMatches();
    } else {
      limit = 30;
      render();
    }
  });
});

panel.querySelector(
  '[data-market]'
).addEventListener('click', () => {
  market = market === 'US' ? 'TW' : 'US';
  category = '';

  if (!query) {
    defaultMatches();
  } else {
    render();
  }
});

let timer;

input.addEventListener('input', () => {
  query = clean(input.value);

  clearTimeout(timer);

  const token = ++serial;

  timer = setTimeout(
    () => search(query, token).catch(e => {
      if (token === serial) {
        meta.textContent =
          '搜尋失敗：' + e.message;
      }
    }),
    220
  );
});

panel.querySelector(
  '#rmClear'
).addEventListener('click', () => {
  input.value = '';
  query = '';

  ++serial;
  clearTimeout(timer);

  defaultMatches();
});

more.addEventListener('click', () => {
  limit += 30;
  render();
});

sync();

})();


