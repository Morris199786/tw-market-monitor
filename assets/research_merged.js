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
        placeholder="搜尋歷史：公司、代號、券商、全文"
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
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
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
}

#rmClose {
  flex: none;
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
let initialized = false;
let lastScroll = 0;

const bucketCache = new Map();
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

function bucket(g) {
  return Array.from(g).reduce(
    (v, c, i) => v + (i + 1) * c.codePointAt(0),
    0
  ) % 64;
}

async function gram(g) {
  const b = bucket(g);

  if (!bucketCache.has(b)) {
    const task = fetchJSON(
      `./data/research_search/${String(b).padStart(2, '0')}.json`
    ).catch(e => {
      bucketCache.delete(b);
      throw e;
    });

    bucketCache.set(b, task);
  }

  return (await bucketCache.get(b))[g] || [];
}

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
          [m.company, m.ticker].filter(Boolean).join(' ') ||
          '研究資料'
        )}
      </div>

      <div class="rm-sub">
        ${escape(m.date)}
        ${escape(m.source)}
        ${escape(m.category)}
      </div>

      <div class="rm-story">
        ${escape(
          clean(m.story) ||
          '此篇研究尚無一句話摘要'
        )}
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
        (category === '週報' || r.date >= since) &&
        r.market === market
      ) ? i : -1;
    })
    .filter(i => i >= 0);

  limit = 30;
  render();
}

async function search(term, token) {
  const q = norm(term);

  if (!q) {
    defaultMatches();
    return;
  }

  meta.textContent = '搜尋歷史索引中…';

  const words = q.split(/\s+/).filter(Boolean);
  let result = null;

  for (const word of words) {
    let candidate;

    if (word.length === 1) {
      candidate = rows
        .map((r, i) => {
          const text = norm([
            r.company,
            r.ticker,
            r.source,
            r.story,
            r.category
          ].join(' '));

          return text.includes(word) ? i : -1;
        })
        .filter(i => i >= 0);
    } else {
      const grams = [
        ...new Set(
          Array.from(
            { length: word.length - 1 },
            (_, i) => word.slice(i, i + 2)
          )
        )
      ];

      const lists = await Promise.all(
        grams.map(gram)
      );

      if (token !== serial) return;

      lists.sort((a, b) => a.length - b.length);

      let set = new Set(lists[0] || []);

      for (const l of lists.slice(1)) {
        const other = new Set(l);

        set = new Set(
          [...set].filter(i => other.has(i))
        );

        if (!set.size) break;
      }

      candidate = [...set];
    }

    const set = new Set(candidate);

    result = result === null
      ? set
      : new Set(
          [...result].filter(i => set.has(i))
        );

    if (!result.size) break;
  }

  if (token !== serial) return;

  matches = [...(result || [])].sort(
    (a, b) => String(rows[b].date)
      .localeCompare(String(rows[a].date))
  );

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

function displayText(value) {
  return escape(clean(value))
    .replace(/\n{3,}/g, '\n\n');
}

function showDetail(r, m) {
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
        <p class="rm-paragraph">
          ${displayText(story)}
        </p>
      </div>
    `;
  }

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
    .map(clean)
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
        >${full.map(displayText).join('\n\n')}</div>
      `
    );
  }

  return html || section(
    '研究內容',
    '尚無可顯示的資料'
  );
}

async function openReader(m) {
  lastScroll = window.scrollY;

  dialog.hidden = false;
  document.body.classList.add(
    'rm-reader-open'
  );

  dialog.scrollTop = 0;

  dialog.querySelector(
    '#rmReaderTitle'
  ).textContent = [
    m.company,
    m.ticker
  ].filter(Boolean).join(' ') || '研究閱讀';

  const content = dialog.querySelector(
    '#rmReaderContent'
  );

  content.textContent = '載入研究內容中…';

  try {
    const items = await shard(m.file);

    if (dialog.hidden) return;

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
