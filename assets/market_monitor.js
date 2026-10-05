(() => {
  'use strict';

  const root = document.getElementById('marketMonitor');
  if (!root) return;

  let dataset = null;
  let pending = null;

  const year = root.querySelector('[data-mm-year]');
  const month = root.querySelector('[data-mm-month]');
  if (!year || !month) return;

  const fmt = (v, d = 2) =>
    v == null
      ? '—'
      : `${v > 0 ? '+' : ''}${v.toLocaleString('zh-TW', {
          minimumFractionDigits: d,
          maximumFractionDigits: d
        })}`;

  const light = {
    red: '紅燈',
    yellow: '黃燈',
    normal: '正常'
  };

  function render() {
    if (!dataset) return;

    // 日期由小到大排列：1號 → 31號
    const rows = dataset.rows
      .filter(r => r.date.slice(0, 7) === `${year.value}-${month.value}`)
      .sort((a, b) => a.date.localeCompare(b.date));

    const incomplete = rows.filter(r => r.foreign == null || r.margin == null || r.index == null).length;
    const signals = rows.filter(r => r.intersection == null).length;
    const coverage = rows.length
      ? `${year.value}年${Number(month.value)}月 ${rows.length}個交易日｜` +
        (incomplete || signals ? `原始資料待補 ${incomplete} 日、燈號待補 ${signals} 日` : '本月資料與燈號齊全')
      : '本月尚無資料，請確認歷史回補是否完成';
    root.querySelector('[data-mm-status]').textContent =
      `資料截至 ${dataset.as_of_date || '尚無資料'}｜${dataset.scope || ''}｜${coverage}｜更新 ${dataset.updated_at || '—'}`;

    root.querySelector('tbody').innerHTML = rows.length
      ? rows.map(r => `
          <tr>
            <td>${r.date.slice(5).replace('-', '/')}</td>

            <td class="mm-${r.foreign_light || 'missing'}">
              ${fmt(r.foreign)}
              <small>
                ${light[r.foreign_light] || '資料不足'}
              </small>
            </td>

            <td class="mm-${r.margin_light || 'missing'}">
              ${fmt(r.relative)}${r.relative == null ? '' : '%'}
              <small>
                ${light[r.margin_light] || '資料不足'}
              </small>
            </td>

            <td class="mm-${r.intersection || 'missing'}">
              ${light[r.intersection] || '資料不足'}
            </td>
          </tr>
        `).join('')
      : `
          <tr>
            <td colspan="4">
              本月尚無已公布交易日資料
            </td>
          </tr>
        `;
  }

  async function load() {
    if (pending) return pending;

    pending = (async () => {
      try {
        const response = await fetch(
          './data/market_monitor.json?v=' + Date.now(),
          { cache: 'no-store' }
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        dataset = await response.json();

        if (!Array.isArray(dataset.rows)) {
          throw new Error('資料格式錯誤');
        }

        const selectedYear = year.value;
        const latest = dataset.as_of_date || new Date().toLocaleDateString('sv-SE', {timeZone: 'Asia/Taipei'});
        const endYear = Math.max(2026, Number(latest.slice(0, 4)), ...dataset.rows.map(r => Number(r.date.slice(0, 4))));
        year.replaceChildren(...Array.from({length: endYear - 2024 + 1}, (_, i) =>
          new Option(`${2024 + i}年`, String(2024 + i))));
        year.value = selectedYear || latest.slice(0, 4);
        if (!month.value) month.value = latest.slice(5, 7);

        render();
      } catch (error) {
        root.querySelector('[data-mm-status]').textContent =
          '大盤監控資料讀取失敗，請稍後按重新整理';
      } finally {
        pending = null;
      }
    })();

    return pending;
  }

  year.replaceChildren(...[2024, 2025, 2026].map(y => new Option(`${y}年`, String(y))));
  year.value = '';
  month.replaceChildren(...Array.from({length: 12}, (_, i) =>
    new Option(`${i + 1}月`, String(i + 1).padStart(2, '0'))));
  month.value = '';
  year.addEventListener('change', render);

  month.addEventListener('change', render);

  root.querySelector('button').addEventListener('click', load);

  // 僅監聽本分頁是否開啟，避免整頁監聽與持續輪詢
  new MutationObserver(() => {
    if (root.classList.contains('active') && !dataset) {
      load();
    }
  }).observe(root, {
    attributes: true,
    attributeFilter: ['class']
  });

  if (root.classList.contains('active')) {
    load();
  }
})();

