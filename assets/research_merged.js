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

function clean(s) {
  if (Array.isArray(s)) s = s.join('\n');
  let value = String(s ?? '').trim();
  if (/^(null|none|nan)$/i.test(value)) return '';
  if (value.startsWith('[') && value.endsWith(']')) {
    try {
      let parsed = JSON.parse(value);
      if (Array.isArray(parsed) && parsed.every(x => typeof x === 'string')) value = parsed.join('\n');
    } catch (_) {
      // Python list literals with simple quoted elements.
      if (/^\[\s*['"]/.test(value) && /['"]\s*\]$/.test(value)) {
        value = value.slice(1, -1).replace(/['"]\s*,\s*['"]/g, '\n').replace(/^['"]|['"]$/g, '');
      }
    }
  }
  return value.replace(/【Raw_Inbox\s+row\d+】|【另一來源】/gi, '')
    .split(/\r?\n/).filter(line => !/(?:免責聲明|不構成投資建議|僅供內部|請勿外傳|研究員聯絡|研究員電話|電子郵件|copyright|all rights reserved|important disclosures)/i.test(line))
    .join('\n').trim();
}

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
  min-width: 0;
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
  display: -webkit-box;
  -webkit-line-clamp: unset;
  -webkit-box-orient: vertical;
  overflow: visible;
  white-space: pre-line;
}

#researchMergedPanel .rm-company-line, #rmReader .rm-company-line {
  display: block;
  margin: 0 0 10px;
  line-height: 1.75;
}
#researchMergedPanel .rm-company-line:last-child, #rmReader .rm-company-line:last-child { margin-bottom: 0; }

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
  width: 100%;
  max-width: 100vw;
  overscroll-behavior: contain;
  font: 15px/1.8 -apple-system, BlinkMacSystemFont, "Noto Sans TC", sans-serif;
}

#rmReader * {
  box-sizing: border-box;
}

#rmReader .rm-reader-header {
  position: sticky;
  top: 0;
  z-index: 2147483001;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-width: 0;
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
  word-break: break-word;
}

#rmClose {
  flex: 0 0 42px;
  position: relative;
  z-index: 2147483002;
  border: 1px solid #dce3eb;
  background: #fff;
  color: #233247;
  border-radius: 50%;
  width: 38px;
  height: 38px;
  font-size: 21px;
}

#rmReaderContent {
  max-width: 900px;
  width: 100%;
  min-width: 0;
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
  table-layout: auto;
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
#rmReader .rm-unmapped { font-variant-numeric: tabular-nums; background: #f3f6fa; padding: 8px; }
@media (max-width: 600px) {
 #rmReaderContent { padding: 12px 12px 30px; }
 #rmReader .rm-section { padding: 12px; }
 #rmReader .rm-section > .rm-table-wrap > table:not(.rm-financial) th { width: 28%; padding: 8px; }
}

body.rm-reader-open {
  overflow: hidden;
  max-width: 100vw;
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
let initialized = false;
let lastScroll = 0;
let readerSerial = 0;


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
    if (category === '券商報告' ? row.source_kind !== 'broker' : category && row.category !== category) return false;

    return true;
  });
}

// Handle legacy metadata as well as newly synchronized multi-company reports.
function isMultiReport(m) {
  const raw = [m.company, m.title, m.report_title, m.ticker].filter(Boolean).join(' ');
  return Boolean(m.is_multi_company) || /多檔聚合|多股研究整理/.test(raw) ||
    (raw.match(/\b\d{4}\.(?:TW|TWO)\b/gi) || []).length >= 3;
}
function reportHeading(m) {
  if ((m.source_kind === 'broker' || m.ai_processed) && clean(m.title)) return clean(m.title);
  if (!isMultiReport(m)) return [m.company, m.ticker].filter(Boolean).join(' ') || '研究資料';
  const raw = String(m.company || m.title || m.report_title || '');
  let topic = raw.replace(/[（(]?多檔聚合[）)]?/g, '')
    .replace(/(?:[;；,，\s]*\d{4}\.(?:TW|TWO)\b)+/gi, '')
    .replace(/\b\d{4}\.(?:TW|TWO)\b/gi, '')
    .replace(/\s+/g, ' ').trim().replace(/^[\s｜|:：;；-]+|[\s｜|:：;；-]+$/g, '');
  const match = topic.match(/(?:漲停\s*[／/]\s*強勢股說明|強勢股|漲停股)/);
  if (match) {
    const date = (m.date || '').match(/\d{4}-(\d{2})-(\d{2})/);
    return `${date ? `${Number(date[1])}/${Number(date[2])} ` : ''}強勢股觀察`;
  }
  topic = topic.replace(/\b(?:20)?\d{2}[01]\d[0-3]\d\b/g, '').trim();
  return topic && !/^\d+$/.test(topic) ? topic : '多股研究整理';
}
function reportStory(m) {
  let story = punctuate(m.story || '此篇研究尚無一句話摘要');
  if (!isMultiReport(m)) return escape(story);
  story = story.replace(/^\s*(?:漲停[／/]強勢股說明|強勢股說明)[^：:]*[：:]\s*/u, '');
  // Separate each stock only at a semicolon followed by a named stock and four-digit code.
  story = story.replace(/[；;]\s*(?=[\u3400-\u9fffA-Za-z][\u3400-\u9fffA-Za-z\-・]{0,18}[（(]\d{4}[）)])/gu, '\n');
  return story.split(/\n+/).map(x => `<div class="rm-company-line">${escape(x.trim())}</div>`).join('');
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
    `${query ? '歷史搜尋' : market === 'US' ? '全部美股研究' : '全部台股研究'}` +
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
          reportHeading(m)
        )}
      </div>

      <div class="rm-sub">
        ${escape([m.company, m.ticker].filter(Boolean).join(' '))}<br>
        ${escape(m.date)}
        ${escape(m.source)}
        ${escape(m.category)}
      </div>

      <div class="rm-story">
        ${reportStory(m)}
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
  }

  more.hidden = list.length <= limit;
}

function defaultMatches() {
  const since = cutoff();

  matches = rows
    .map((r, i) => {
      return (

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
      ? value.split(/[^a-z0-9]+/).includes(word) || value.startsWith(word + '.') || value === word
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

// Preserve English punctuation and numeric thousands separators.
function punctuate(value) {
  return clean(value).split('\n').map(line => {
    if (!/[\u3400-\u9fff]/.test(line)) return line;
    return line.replace(/,(?!\d{3}(?:\D|$))/g, '，')
      .replace(/，\s+/g, '，').replace(/;/g, '；').replace(/:(?!\/\/|\d{2}\b)/g, '：');
  }).join('\n');
}

const periodPattern = /^(?:[1-4]Q\d{2,4}[FEfe]?|Q[1-4](?:FY)?\d{2,4}[FEfe]?|FY\d{2,4}[FEfe]?|12\/\d{2}[EeFf]?)$/;
const numberPattern = /^(?:\(?[-+−]?\d[\d,]*(?:\.\d+)?\)?%?|[-–—]|N\/?A)$/i;
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
  while (pos < lines.length && /^(?:IFRS\s*)+$/.test(lines[pos])) pos++;
  const rows = [];
  while (pos < lines.length) {
    const rowStart = pos;
    let text = lines[pos], parsed = null;
    // PDF can wrap the label or values over several physical lines.
    for (let n = 0; n < 5 && pos + n < lines.length; n++) {
      if (n) {
        const next = lines[pos + n];
        if (!next || isPeriods(next) || /^(?:Y\/Y|Q\/Q|Fiscal Year)/i.test(next)) break;
        text += ' ' + next;
      }
      const match = text.match(/^(.+?)(\(?[-+−]?\d[\d,]*(?:\.\d+)?\)?%?(?:\s+(?:\(?[-+−]?\d[\d,]*(?:\.\d+)?\)?%?|[-–—]|N\/?A))+)(?:\s*)$/i);
      if (!match) continue;
      const values = match[2].trim().split(/\s+/);
      const label = match[1].trim();
      if (values.length === periods.length && values.every(x => numberPattern.test(x)) && /[a-z\u3400-\u9fff]/i.test(label)) {
        parsed = {label, values, end: pos + n + 1}; break;
      }
      if (values.length > periods.length) break;
    }
    if (!parsed) { pos = rowStart; break; }
    rows.push(parsed); pos = parsed.end;
  }
  if (rows.length < 2) return null;
  return {end: pos, html: `<div class="rm-table-hint">${escape(heading || '財務數據')} · 可左右滑動；F／e 為原報告預估標記，單位依原文</div><div class="rm-table-wrap" tabindex="0" role="region" aria-label="財務數據表"><table class="rm-financial"><thead><tr><th scope="col">項目</th>${periods.map(p => `<th scope="col">${escape(p)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr><th scope="row">${escape(r.label)}</th>${r.values.map(v => `<td>${escape(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`};
}

function readable(value) {
  const lines = clean(value).replace(/\r/g, '').split('\n').map(x => x.trim());
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
      const join = /[\u3400-\u9fff，；、]$/.test(paragraph) || /^[\u3400-\u9fff，。；、,;]/.test(line) ? '' : ' ';
      paragraph += join;
    }
    paragraph += line;
    if (heading || /[。！？.!?]$/.test(line)) flush();
  }
  flush();
  return `<div class="rm-prose">${out.join('')}</div>`;
}

function financialInline(value, key) {
  const s = clean(value);
  // Explicit year/quarter list and exactly matching slash-separated figures.
  const m = s.match(/((?:20\d{2}|\d{2})(?:\/|、|，|\s+)){1,7}(?:20\d{2}|\d{2})[EeFf]?\s*(?:年)?\s*(?:EPS|每股盈餘|營收|Revenue)\s*[:：]?\s*([+-]?\d[\d,]*(?:\.\d+)?(?:\s*[\/、，]\s*[+-]?\d[\d,]*(?:\.\d+)?)+)/i);
  if (!m) return '';
  const years = m[0].split(/EPS|每股盈餘|營收|Revenue/i)[0].match(/20\d{2}|(?<!\d)\d{2}(?!\d)/g) || [];
  const vals = m[1].match(/[+-]?\d[\d,]*(?:\.\d+)?/g) || [];
  if (years.length < 2 || years.length !== vals.length) return '';
  const unit = /EPS|每股盈餘/i.test(m[0]) ? 'EPS（元）' : '營收（單位依原文）';
  const normalized = years.map(y => y.length === 2 ? '20' + y : y);
  return `<div class="rm-table-wrap" tabindex="0" role="region" aria-label="${escape(unit)}"><table class="rm-financial"><thead><tr><th>指標</th>${normalized.map(y=>`<th>${escape(y)}E</th>`).join('')}</tr></thead><tbody><tr><th>${escape(unit)}</th>${vals.map(v=>`<td>${escape(v)}</td>`).join('')}</tr></tbody></table></div>`;
}
function displayText(value, key) {
  // Separate clearly marked company sections, without splitting normal sentences.
  let normalized = clean(value);
  normalized = normalized.replace(/([；;])\s*(?=[\u3400-\u9fffA-Za-z][\u3400-\u9fffA-Za-z・－-]{1,14}[（(]\d{4}[）)][:：])/g, '\n');
  const table = financialInline(normalized, key);
  return table ? table + readable(normalized) : readable(normalized);
}


// BEGIN FINANCIAL FORECAST TABLES V2
const financialLabels={revenue:'營收',revenue_yoy:'營收年增率',revenue_qoq:'營收季增率',gross_profit:'毛利',gross_margin:'毛利率',operating_profit:'營業利益',operating_margin:'營益率',pretax_profit:'稅前淨利',pretax_margin:'稅前淨利率',net_income:'稅後淨利',net_margin:'淨利率',eps:'EPS',roe:'ROE',roa:'ROA',operating_cash_flow:'營業現金流',free_cash_flow:'自由現金流',capex:'資本支出',dividend:'每股現金股利',pe:'本益比',pb:'本淨比'};
// Per-report financial JSON.
const financialCache = new Map();

async function financialForReport(id) {
  const key = String(id || '');
  if (!key) return [];

  if (!financialCache.has(key)) {
    const task = (async () => {
      try {
        const bytes = new TextEncoder().encode(key);
        const hash = await crypto.subtle.digest(
          'SHA-256',
          bytes
        );

        const filename = Array.from(
          new Uint8Array(hash)
        ).map(
          x => x.toString(16).padStart(2, '0')
        ).join('').slice(0, 24) + '.json';

        const response = await fetch(
          './data/research_financial_by_id/' + filename,
          { cache: 'no-cache' }
        );

        if (!response.ok) {
          if (response.status !== 404) {
            console.warn(
              'Financial HTTP',
              response.status,
              key
            );
          }
          return [];
        }

        const record = await response.json();

        if (String(record.id) !== key) {
          return [];
        }

        return Array.isArray(record.forecasts)
          ? record.forecasts
          : [];

      } catch (e) {
        console.warn(
          'Financial data fetch failed',
          key,
          e
        );
        return [];
      }
    })();

    financialCache.set(key, task);
  }

  return financialCache.get(key);
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

function brokerFullDetail(r, financialRecords=[]) {
  const parts=[];
  const prose=value => displayText(Array.isArray(value) ? value.join('\n\n') : String(value || ''));
  const identity=[r.name || r.company,r.ticker].filter(Boolean).join(' ');
  parts.push(`<div class="rm-info">${escape(identity)} · ${escape(r.broker || r.source || '')} · ${escape(r.date || '')}</div>`);
  const metrics=[];
  if (r.rating) metrics.push(['評等',r.rating]);
  if (r.target_price_new != null) metrics.push(['目標價',String(r.target_price_new)]);
  if (metrics.length) parts.push(section('評等與目標價',`<table><tbody>${metrics.map(([k,v])=>`<tr><th>${escape(k)}</th><td>${escape(v)}</td></tr>`).join('')}</tbody></table>`));
  for (const [key,title] of [['summary','研究摘要'],['key_points','研究重點'],['detail','完整解析'],['forecast_changes','財測調整'],['risks','風險']]) {
    if (r[key] && (!Array.isArray(r[key]) || r[key].length)) parts.push(section(title,prose(r[key])));
  }
  if (Array.isArray(r.beneficiaries) && r.beneficiaries.length) parts.push(section('相關公司',r.beneficiaries.map(x=>
    `<div class="rm-company"><h4>${escape(x.name)} ${escape(x.ticker)}</h4>${prose(x.reason)}</div>`).join('')));
  if (Array.isArray(r.quarterly_eps) && r.quarterly_eps.length) parts.push(section('券商單季 EPS 預估',
    `<div class="rm-table-wrap"><table><thead><tr><th>季度</th><th>預估 EPS</th></tr></thead><tbody>${r.quarterly_eps.map(x=>
    `<tr><th>${escape(x.period)}</th><td>${escape(x.eps)}</td></tr>`).join('')}</tbody></table></div>`));
  parts.push(financialTables([...(Array.isArray(r.financial_forecasts)?r.financial_forecasts:[]),...financialRecords]));
  return parts.join('');
}

function showDetail(r, m, financialRecords=[]) {
  if (r.source_kind === 'broker') return brokerFullDetail(r,financialRecords);
  if (r.ai_schema === 'broker-v1' && r.ai_research) return brokerFullDetail({...r.ai_research, date:r.date, source:r.source},financialRecords);
  const d = r.display || {};

  const story = clean(
    d.story || r.story || m.story
  );

  let html = `
    <div class="rm-info">
      ${escape(m.date)}
      ${escape(m.source)}
      ${escape(m.category)}
    </div>
  `;

  if (story) {
    html += `
      <div class="rm-hero">
        <strong>研究重點</strong>
        <div class="rm-paragraph">${isMultiReport(m) ? `<div class="rm-prose">${reportStory({...m, story})}</div>` : displayText(story)}</div>
      </div>
    `;
  }

  // Evidence-based AI analysis, with report-specific sources and no inferred figures.
  const ai = r.ai_research || {};
  const renderEntries = (entries, labels) => Array.isArray(entries) ? entries.map(entry => {
    if (!entry || typeof entry !== 'object') return '';
    const lines = labels.map(([key,label]) => entry[key] == null || entry[key] === '' ? '' :
      `<p><strong>${escape(label)}：</strong>${escape(typeof entry[key] === 'string' ? entry[key] : JSON.stringify(entry[key]))}</p>`).join('');
    return lines ? `<div class="rm-company">${lines}</div>` : '';
  }).join('') : '';
  if (ai.summary && ai.summary !== story) html += section('AI 研究摘要', displayText(ai.summary));
  if (Array.isArray(ai.changes) && ai.changes.length) html += section('歷次預估變動與原因',
    renderEntries(ai.changes, [['metric','指標'],['period','期間'],['previous','前次'],['current','本次'],
      ['change','變動'],['reason','原因'],['evidence','原文證據'],['source_dates','比較日期']]));
  if (Array.isArray(ai.cross_validation) && ai.cross_validation.length) html += section('供應鏈與同業交互驗證',
    renderEntries(ai.cross_validation, [['topic','題材'],['status','驗證狀態'],['evidence','證據'],
      ['contradictions','矛盾訊號'],['missing_evidence','尚缺證據']]));
  if (Array.isArray(ai.uncertainties) && ai.uncertainties.length) html += section('待確認事項',
    `<div class="rm-prose">${ai.uncertainties.map(x=>`<p>${escape(String(x))}</p>`).join('')}</div>`);
  if (Array.isArray(ai.sections) && ai.sections.length) html += section('AI 分項分析',
    ai.sections.map(x=>`<div class="rm-company"><h4>${escape(x.heading || '')}</h4>${displayText(x.body || '')}</div>`).join(''));

  const data = fields
    .map(([k, title]) => ({
      title,
      value: clean(d[k] ?? r[k])
    }))
    .filter(x => x.value);

  if (data.length) {
    html += section(
      '研究數據與分析',
      `
        <div class="rm-table-wrap">
          <table>
            <tbody>
              ${data.map(x => `
                <tr>
                  <th>${escape(x.title)}</th>
                  <td>${displayText(x.value, x.title)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `
    );
  }

  html += financialTables([...(Array.isArray(ai.financial_forecasts)?ai.financial_forecasts:[]),...financialRecords]);

  // Original PDF text stays in source data for auditing, not the reader UI.

  return html || section(
    '研究內容',
    '尚無可顯示的資料'
  );
}

async function openReader(m) {
  const opening = ++readerSerial;
  lastScroll = window.scrollY;

  dialog.hidden = false;
  document.body.classList.add(
    'rm-reader-open'
  );

  dialog.scrollTop = 0;

  dialog.querySelector(
    '#rmReaderTitle'
  ).textContent = reportHeading(m);

  const content = dialog.querySelector(
    '#rmReaderContent'
  );

  content.textContent = '載入研究內容中…';

  try {
    const items = await shard(m.file);

    if (dialog.hidden || opening !== readerSerial) return;

    const r = items.find(
      x => String(x.id) === String(m.id)
    );

    if (!r) {
      throw Error('找不到這篇研究');
    }

    const financialRecords = await financialForReport(r.id);
    if (dialog.hidden || opening !== readerSerial) return;
    content.innerHTML = showDetail(r, m, financialRecords);

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
  ++readerSerial;
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

  /* original-broker-v3-view-v1 */
  // Broker reports must use the original reports_v2.js renderer and its
  // complete AI analysis, rather than the simplified merged reader.
  const brokerMode = active && !ratingOn && category === '券商報告';
  panel.hidden = !active || ratingOn;
  legacy.hidden = active && !ratingOn ? !brokerMode : Boolean(ratingOn);
  cards.hidden = brokerMode;
  panel.querySelector('.rm-search').hidden = brokerMode;
  meta.hidden = brokerMode;
  if (brokerMode) more.hidden = true;

  if (active && !ratingOn) init();
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
    sync();
    console.info('[RESEARCH_VIEW] mode=' + (category === '券商報告' ? 'original_broker_v3' : 'merged_research'));
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


/* Keep hidden elements hidden when switching to the original broker view. */
