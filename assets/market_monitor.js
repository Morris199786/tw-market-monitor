(() => {
  'use strict';

  const root = document.getElementById('marketMonitor');
  if (!root) return;

  let dataset = null;
  let pending = null;

  const month = root.querySelector('select');

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

    const rows = dataset.rows
      .filter(r => r.date.slice(0, 7) === month.value)
      .reverse();

    root.querySelector('[data-mm-status]').textContent =
      `資料截至 ${dataset.as_of_date || '尚無資料'}` +
      `｜${dataset.scope}` +
      `｜${
        dataset.errors.length
          ? `來源有 ${dataset.errors.length} 項缺漏，尚未齊全`
          : '來源已取得'
      }` +
      `｜更新 ${dataset.updated_at}`;

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

        if (!month.value) {
          month.value = (
            dataset.as_of_date || '2026-01'
          ).slice(0, 7);
        }

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

  month.innerHTML =
    '<option value="" disabled>選擇月份</option>' +
    Array.from({ length: 12 }, (_, i) => {
      const value = `2026-${String(i + 1).padStart(2, '0')}`;

      return `
        <option value="${value}">
          2026年${i + 1}月
        </option>
      `;
    }).join('');

  month.value = '';

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
