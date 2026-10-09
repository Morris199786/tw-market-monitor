/* =========================================================
   券商報告 V3.5
   - 依收到日期分組
   - 歷史報告永久保留
   - 公司名稱 / 股票代號搜尋
   - 中文公司名可搜尋外資英文報告（依 ticker 自動對照）
   - 網站已顯示的報告內容全文關鍵字搜尋
   - 英文不區分大小寫
   - 搜尋命中的文字顯示黃色底色
   - 搜尋結果數量顯示
   - 搜尋框右側清除按鈕
   - Pushover deep link 直達指定報告
   - 首頁今日券商報告數
   - 券商報告移到導覽第 3 順位
   ========================================================= */

(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];

  const actionMap = {
    upgrade: "上調",
    downgrade: "下調",
    initiate: "初評",
    maintain: "維持",
    sector: "產業報告",
    none: "研究報告"
  };

  let allReports = [];
  let currentFilter = "all";
  let currentQuery = "";

  const stockNamesByTicker = new Map();

  // Verified Taiwan issuer names; display-only: never mutate reports, IDs, or URLs
  const taiwanCompanyNames = [
    ['MediaTek', '聯發科'], ['Global Unichip', '創意'], ['GUC', '創意'],
    ['Taiwan Semiconductor Manufacturing Company', '台積電'], ['TSMC', '台積電'],
    ['United Microelectronics Corporation', '聯電'], ['UMC', '聯電'],
    ['Vanguard International Semiconductor', '世界先進'], ['VIS', '世界先進'],
    ['ASE Technology Holding', '日月光投控'], ['ASEH', '日月光投控'],
    ['Advanced Semiconductor Engineering', '日月光'], ['ASE', '日月光'],
    ['Siliconware Precision Industries', '矽品'], ['SPIL', '矽品'],
    ['Shunsin-KY', '訊芯-KY'], ['ShunSin', '訊芯-KY'],
    ['WinWay', '穎崴'], ['MPI Corporation', '旺矽'], ['MPI', '旺矽'],
    ['Chroma', '致茂'], ['KYEC', '京元電子'],
    ['Integrated Service Technology', '宜特'], ['iST', '宜特'],
    ['FOCI', '上詮'], ['Browave', '波若威'], ['LuxNet', '華星光'],
    ['VisEra', '采鈺'], ['ProMOS', '茂德'], ['FitTech', '惠特'],
    ['Unimicron', '欣興'], ['Nan Ya PCB', '南電'], ['Kinsus', '景碩'],
    ['Elite Material Co., Ltd.', '台光電'], ['Elite Materials', '台光電'],
    ['Elite Material', '台光電'],
    ['Alchip', '世芯-KY'], ['Faraday Technology', '智原'],
    ['Novatek', '聯詠'], ['Realtek', '瑞昱'], ['Nanya Technology', '南亞科'],
    ['Winbond', '華邦電'], ['Macronix', '旺宏'], ['Phison', '群聯'],
    ['Largan', '大立光'], ['Wiwynn', '緯穎'], ['Quanta', '廣達'],
    ['Wistron', '緯創'], ['Inventec', '英業達'], ['Hon Hai', '鴻海']
  ];
  const companyNameMap = new Map(taiwanCompanyNames.map(([a, n]) => [a.toLowerCase(), n]));
  const companyNamePattern = new RegExp(
    '(' + taiwanCompanyNames.map(([a]) => a)
      .sort((a, b) => b.length - a.length)
      .map(a => a.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi'
  );
  const localizedTextCache = new Map();
  function localizeTaiwanCompanies(value) {
    const text = String(value ?? '');
    if (localizedTextCache.has(text)) return localizedTextCache.get(text);
    // Keep links/email verbatim, and match full Latin tokens, not substrings
    const converted = text.split(/((?:https?:\/\/|www\.)[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})/g)
      .map((part, index) => index % 2 ? part : part.replace(companyNamePattern, (match, alias, offset, input) => {
        if (/[A-Za-z0-9_]/.test(input[offset - 1] || '') || /[A-Za-z0-9_]/.test(input[offset + match.length] || '')) return match;
        // iST is also a time zone abbreviation; only accept company brand casing
        if (alias.toLowerCase() === 'ist' && match !== 'iST') return match;
        const name = companyNameMap.get(alias.toLowerCase());
        // Existing bilingual captions: avoid "台積電 台積電" or "台積電（台積電）"
        const after = input.slice(offset + match.length);
        if (after.trimStart().startsWith(name)) return '';
        if (after.trimStart().startsWith('(' + name + ')') || after.trimStart().startsWith('（' + name + '）')) return match;
        return name;
      })).join('');
    if (localizedTextCache.size > 4000) localizedTextCache.clear();
    localizedTextCache.set(text, converted);
    return converted;
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  /* =========================================================
     搜尋關鍵字黃底標示
     ========================================================= */

  function normalizeSearchText(value) {
    return String(value ?? "")
      .normalize("NFKC")
      .toLocaleLowerCase();
  }

  function highlightedText(value) {
    const original = localizeTaiwanCompanies(value);
    const query = normalizeSearchText(
      localizeTaiwanCompanies(currentQuery.trim())
    );

    if (!query || !original) {
      return esc(original);
    }

    const normalized = normalizeSearchText(original);

    /*
      逐字建立正規化文字與原始字元的對照，
      避免全形／半形字元正規化後位置不同，
      導致標示錯誤
    */
    const units = Array.from(original);

    const normalizedParts = [];
    const startMap = [];
    const endMap = [];

    let originalOffset = 0;

    for (const unit of units) {
      const start = originalOffset;
      originalOffset += unit.length;

      const part = normalizeSearchText(unit);

      for (let i = 0; i < part.length; i++) {
        normalizedParts.push(part[i]);
        startMap.push(start);
        endMap.push(originalOffset);
      }
    }

    const searchable = normalizedParts.join("");

    if (!searchable.includes(query)) {
      return esc(original);
    }

    const ranges = [];
    let position = 0;

    while (position < searchable.length) {
      const found = searchable.indexOf(
        query,
        position
      );

      if (found === -1) break;

      const start = startMap[found];
      const end = endMap[
        found + query.length - 1
      ];

      if (
        start !== undefined &&
        end !== undefined
      ) {
        ranges.push([start, end]);
      }

      position = found + Math.max(query.length, 1);
    }

    if (!ranges.length) {
      return esc(original);
    }

    /*
      合併重疊範圍，避免產生不合法的巢狀 mark
    */
    const merged = [];

    for (const range of ranges) {
      const last = merged[merged.length - 1];

      if (last && range[0] <= last[1]) {
        last[1] = Math.max(last[1], range[1]);
      } else {
        merged.push([...range]);
      }
    }

    let result = "";
    let cursor = 0;

    for (const [start, end] of merged) {
      result += esc(original.slice(cursor, start));

      result +=
        `<mark class="report-search-highlight">` +
        esc(original.slice(start, end)) +
        `</mark>`;

      cursor = end;
    }

    result += esc(original.slice(cursor));

    return result;
  }

  function addStockName(ticker, name) {
    const t = String(ticker || "").trim();
    const n = String(name || "").trim();

    if (!t || !n) return;

    if (!stockNamesByTicker.has(t)) {
      stockNamesByTicker.set(t, new Set());
    }

    stockNamesByTicker.get(t).add(n);

    const shortName = n
      .replace(/[-－]KY$/i, "")
      .replace(/\*$/g, "")
      .trim();

    if (shortName) {
      stockNamesByTicker.get(t).add(shortName);
    }
  }

  async function loadStockNameIndex() {
    stockNamesByTicker.clear();

    try {
      const res = await fetch(
        "./data/master.json?v=" + Date.now(),
        { cache: "no-store" }
      );

      if (res.ok) {
        const data = await res.json();
        const stocks = data.stocks || {};

        Object.entries(stocks).forEach(
          ([ticker, row]) => {
            addStockName(ticker, row?.name);
          }
        );
      }
    } catch (e) {
      console.warn(
        "report search master name index failed",
        e
      );
    }

    try {
      const res = await fetch(
        "./data/sectors.json?v=" + Date.now(),
        { cache: "no-store" }
      );

      if (res.ok) {
        const data = await res.json();

        (data.sectors || []).forEach(
          sector => {
            (sector.stocks || []).forEach(
              row => {
                addStockName(
                  row?.ticker,
                  row?.name
                );
              }
            );
          }
        );
      }
    } catch (e) {
      console.warn(
        "report search sector name index failed",
        e
      );
    }
  }

  function namesForTicker(ticker) {
    const t = String(ticker || "").trim();

    return [
      ...(stockNamesByTicker.get(t) || [])
    ];
  }

  function reportGroupDate(r) {
    return (
      r.group_date ||
      r.received_date ||
      (
        r.received_at
          ? String(r.received_at).slice(0, 10)
          : ""
      ) ||
      (
        r.ai_processed_at
          ? String(r.ai_processed_at).slice(0, 10)
          : ""
      ) ||
      "未分類"
    );
  }

  function dateLabel(day) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) {
      return day;
    }

    const [y, m, d] = day.split("-");
    return `${y}/${m}/${d}`;
  }

  function taipeiToday() {
    return new Intl.DateTimeFormat(
      "sv-SE",
      {
        timeZone: "Asia/Taipei",
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
      }
    ).format(new Date());
  }

  function actionClass(a) {
    if (a === "upgrade") return "is-up";
    if (a === "downgrade") return "is-down";
    if (a === "initiate") return "is-init";
    return "is-neutral";
  }

  function targetText(r) {
    if (
      r.validation_status === "needs_review"
    ) {
      return "";
    }

    const oldTp = r.target_price_old;
    const newTp = r.target_price_new;

    if (
      oldTp !== null &&
      oldTp !== undefined &&
      newTp !== null &&
      newTp !== undefined
    ) {
      return `${oldTp} → ${newTp}`;
    }

    if (
      newTp !== null &&
      newTp !== undefined
    ) {
      return String(newTp);
    }

    return "";
  }

  /* =========================================================
     全文搜尋
     只搜尋網站上已經顯示的報告內容
     不讀取原始 PDF
     ========================================================= */

  function searchText(r) {
    const primaryNames =
      namesForTicker(r.ticker);

    const beneficiarySearch =
      (
        Array.isArray(r.beneficiaries)
          ? r.beneficiaries
          : []
      ).flatMap(
        x => [
          x.name,
          x.ticker,
          x.reason,
          ...namesForTicker(x.ticker)
        ]
      );

    const fields = [
      r.broker,
      r.title,
      r.name,
      r.ticker,

      ...primaryNames,

      r.rating,
      r.push_reason,

      ...(
        Array.isArray(r.summary)
          ? r.summary
          : r.summary
            ? [r.summary]
            : []
      ),

      r.detail,

      ...(
        Array.isArray(r.key_points)
          ? r.key_points
          : []
      ),

      ...(
        Array.isArray(r.forecast_changes)
          ? r.forecast_changes
          : []
      ),

      ...(
        Array.isArray(r.risks)
          ? r.risks
          : []
      ),

      ...beneficiarySearch
    ];

    return normalizeSearchText(
      fields
        .filter(
          value =>
            value !== null &&
            value !== undefined
        )
        .map(value => String(value) + " " + localizeTaiwanCompanies(value))
        .join(" ")
    );
  }

  function chips(r) {
    const arr = [];

    if (
      r.validation_status === "needs_review"
    ) {
      return `
        <span class="report-chip">
          來源核對未通過，請先查看原始報告
        </span>
      `;
    }

    if (r.rating) {
      arr.push(`
        <span class="report-chip">
          ${highlightedText(r.rating)}
        </span>
      `);
    }

    const tp = targetText(r);

    if (tp) {
      const targetClass =
        r.action === "upgrade"
          ? "report-target-up"
          : r.action === "downgrade"
          ? "report-target-down"
          : "";

      arr.push(`
        <span
          class="report-chip report-target ${targetClass}"
        >
          目標價 ${highlightedText(tp)}
        </span>
      `);
    }

    if (
      r.report_type === "sector" ||
      r.report_type === "theme"
    ) {
      arr.push(`
        <span class="report-chip">
          產業研究
        </span>
      `);
    }

    if (r.date) {
      arr.push(`
        <span
          class="report-chip report-original-date"
        >
          報告日期 ${esc(r.date)}
        </span>
      `);
    }

    return arr.join("");
  }

  function beneficiaryHtml(r) {
    const rows =
      Array.isArray(r.beneficiaries)
        ? r.beneficiaries
        : [];

    if (!rows.length) return "";

    return `
      <div class="report-beneficiaries">
        <div class="report-subtitle">
          報告關注個股
        </div>

        <div class="report-stock-chips">
          ${rows.map(x => `
            <button
              type="button"
              class="report-stock-chip"
              data-report-stock="${esc(
                x.ticker || x.name || ""
              )}"
              title="${esc(x.reason || "")}"
            >
              ${highlightedText(x.name || "")}

              ${
                x.ticker
                  ? `
                    <small>
                      ${highlightedText(x.ticker)}
                    </small>
                  `
                  : ""
              }
            </button>
          `).join("")}
        </div>
      </div>
    `;
  }

  function listHtml(title, arr) {
    if (
      !Array.isArray(arr) ||
      !arr.length
    ) {
      return "";
    }

    return `
      <div class="report-detail-block">
        <div class="report-subtitle">
          ${esc(title)}
        </div>

        <ul>
          ${arr.map(
            x => `<li>${highlightedText(x)}</li>`
          ).join("")}
        </ul>
      </div>
    `;
  }

  function card(r) {
    const action =
      actionMap[r.action] ||
      r.action ||
      "研究報告";

    const stockTitle =
      r.report_type === "company"
        ? (
            `${r.name || ""}` +
            (
              r.ticker
                ? ` ${r.ticker}`
                : ""
            )
          )
        : (
            r.title ||
            "產業研究"
          );

    const summary =
      r.validation_status === "needs_review"
        ? [
            "此份報告的公司或目標價尚未通過來源核對，請查看原始報告"
          ]
        : Array.isArray(r.summary)
        ? r.summary
        : [];

    return `
      <article
        id="report-${esc(r.id || "")}"
        class="report-v2-card"
        data-report-id="${esc(r.id || "")}"
      >
        <div class="report-v2-top">
          <div>
            <div class="report-broker">
              ${highlightedText(r.broker || "券商研究")}
            </div>

            <div class="report-title">
              ${highlightedText(stockTitle)}
            </div>
          </div>

          <span
            class="report-action ${actionClass(
              r.action
            )}"
          >
            ${highlightedText(action)}
          </span>
        </div>

        <div class="report-meta">
          ${chips(r)}
        </div>

        ${
          summary.length
            ? `
              <ul class="report-summary">
                ${summary.map(
                  x => `<li>${highlightedText(x)}</li>`
                ).join("")}
              </ul>
            `
            : ""
        }

        ${beneficiaryHtml(r)}

        <details class="report-details">
          <summary>
            查看完整摘要
          </summary>

          <div class="report-details-body">
            ${
              r.detail
                ? `
                  <div class="report-detail-block">
                    <div class="report-subtitle">
                      完整摘要
                    </div>

                    <p>
                      ${highlightedText(r.detail)}
                    </p>
                  </div>
                `
                : ""
            }

            ${listHtml(
              "重點數據／邏輯",
              r.key_points
            )}

            ${listHtml(
              "財測調整",
              r.forecast_changes
            )}

            ${listHtml(
              "風險",
              r.risks
            )}

            ${
              r.source_url
                ? `
                  <a
                    class="report-source-link"
                    href="${esc(r.source_url)}"
                    target="_blank"
                    rel="noopener"
                  >
                    查看原始報告
                  </a>
                `
                : ""
            }
          </div>
        </details>
      </article>
    `;
  }

  function matches(r) {
    const okFilter =
      currentFilter === "all" ||
      r.action === currentFilter;

    const q =
      normalizeSearchText(
        currentQuery.trim()
      );

    const okSearch =
      !q ||
      searchText(r).includes(q);

    return okFilter && okSearch;
  }

  function groupedVisibleReports() {
    const visible =
      allReports.filter(matches);

    const groups = new Map();

    for (const r of visible) {
      const day = reportGroupDate(r);

      if (!groups.has(day)) {
        groups.set(day, []);
      }

      groups.get(day).push(r);
    }

    return [...groups.entries()].sort(
      (a, b) =>
        String(b[0]).localeCompare(
          String(a[0])
        )
    );
  }

  /* -----------------------------
     搜尋欄狀態
     ----------------------------- */

  function updateSearchUi() {
    const clearBtn =
      $("#reportSearchClear");

    const meta =
      $("#reportSearchMeta");

    const queryActive =
      Boolean(currentQuery.trim());

    const filterActive =
      currentFilter !== "all";

    const visibleCount =
      allReports.filter(matches).length;

    if (clearBtn) {
      clearBtn.style.display =
        queryActive
          ? "inline-flex"
          : "none";
    }

    if (meta) {
      if (
        queryActive ||
        filterActive
      ) {
        meta.textContent =
          `找到 ${visibleCount} 份｜共 ${allReports.length} 份歷史報告`;
      } else {
        meta.textContent =
          `共 ${allReports.length} 份歷史報告`;
      }
    }
  }

  function renderGroups() {
    const target =
      $("#reportCardsV3");

    if (!target) return;

    updateSearchUi();

    const groups =
      groupedVisibleReports();

    if (!groups.length) {
      target.innerHTML = `
        <div class="report-v2-empty">
          找不到符合條件的券商報告
        </div>
      `;

      return;
    }

    const searching =
      Boolean(currentQuery.trim());

    target.innerHTML =
      groups.map(
        ([day, rows], index) => `
          <details
            class="report-date-group"
            data-report-day="${esc(day)}"
            ${
              searching || index === 0
                ? "open"
                : ""
            }
          >
            <summary class="report-date-head">
              <span>
                <b>
                  ${esc(dateLabel(day))}
                </b>

                <small>
                  ${rows.length} 份報告
                </small>
              </span>

              <span class="report-date-arrow">
                ⌄
              </span>
            </summary>

            <div class="report-date-body">
              ${rows.map(card).join("")}
            </div>
          </details>
        `
      ).join("");

    $$("[data-report-stock]").forEach(
      btn => {
        btn.addEventListener(
          "click",
          () => {
            const q =
              btn.dataset.reportStock || "";

            const input =
              $("#reportSearch");

            if (input) {
              input.value = q;
            }

            currentQuery = q;
            renderGroups();
          }
        );
      }
    );
  }

  function setupDeepLink() {
    const params =
      new URLSearchParams(
        location.search
      );

    const requestedPage =
      params.get("page");

    const reportId =
      params.get("report");

    if (
      requestedPage === "reports" &&
      typeof window.page === "function"
    ) {
      window.page("reports");
    }

    if (!reportId) return;

    setTimeout(
      () => {
        const el =
          document.querySelector(
            `[data-report-id="${CSS.escape(
              reportId
            )}"]`
          );

        if (!el) return;

        const group =
          el.closest(
            ".report-date-group"
          );

        if (group) {
          group.open = true;
        }

        const detail =
          el.querySelector(
            ".report-details"
          );

        if (detail) {
          detail.open = true;
        }

        el.classList.add(
          "report-deep-highlight"
        );

        el.scrollIntoView({
          behavior: "smooth",
          block: "center"
        });

        setTimeout(
          () => {
            el.classList.remove(
              "report-deep-highlight"
            );
          },
          4500
        );
      },
      650
    );
  }

  async function loadReports() {
    const res = await fetch(
      "./data/reports.json?v=" +
        Date.now(),
      { cache: "no-store" }
    );

    if (!res.ok) {
      throw new Error(
        `reports.json HTTP ${res.status}`
      );
    }

    const data = await res.json();

    allReports =
      Array.isArray(data.items)
        ? data.items
        : [];

    return data;
  }

  /* -----------------------------
     搜尋欄與黃底標示樣式
     只作用在券商報告
     ----------------------------- */

  function injectReportSearchStyle() {
    if ($("#reportSearchFieldStyle")) {
      return;
    }

    const style =
      document.createElement("style");

    style.id =
      "reportSearchFieldStyle";

    style.textContent = `
      #reports .report-search-card {
        width: 100%;
        min-width: 0;
      }

      #reports .report-search-wrap {
        position: relative;
        width: 100%;
        min-width: 0;
      }

      #reports .report-search-wrap input {
        width: 100%;
        box-sizing: border-box;
        padding-right: 82px !important;
      }

      #reports .report-search-clear {
        position: absolute;
        right: 8px;
        top: 50%;
        transform: translateY(-50%);

        display: none;
        align-items: center;
        justify-content: center;

        min-height: 36px;
        padding: 6px 12px;

        border:
          1px solid
          rgba(148, 163, 184, .30);

        border-radius: 9px;

        background: #f3f4f6;
        color: #475569;

        font: inherit;
        font-size: 13px;
        font-weight: 800;
        line-height: 1;

        cursor: pointer;

        -webkit-appearance: none;
        appearance: none;
      }

      #reports .report-search-clear:active {
        transform:
          translateY(-50%)
          scale(.97);
      }

      #reports .report-search-meta {
        display: block;

        margin-top: 9px;

        color: var(--muted);
        opacity: .82;

        font-size: 13px;
        font-weight: 650;
        line-height: 1.45;
      }

      /* 搜尋關鍵字黃色底色 */
      #reports mark.report-search-highlight {
        display: inline;
        background: #ffe66d !important;
        color: #172033 !important;

        padding: 0 2px;
        border-radius: 3px;

        font: inherit;
        font-weight: 800;

        box-decoration-break: clone;
        -webkit-box-decoration-break: clone;
      }

      html[data-theme="dark"]
      #reports
      mark.report-search-highlight {
        background: #ffd84d !important;
        color: #111827 !important;
      }

      html[data-theme="dark"]
      #reports
      .report-search-clear {
        border-color: #3b4656;
        background: #273140;
        color: #e2e8f0;
      }

      @media (max-width: 700px) {
        #reports .report-search-wrap input {
          padding-right: 76px !important;
        }

        #reports .report-search-clear {
          right: 7px;
          min-height: 34px;
          padding: 6px 11px;
          font-size: 12px;
        }

        #reports .report-search-meta {
          margin-top: 8px;
          font-size: 12px;
        }
      }
    `;

    document.head.appendChild(style);
  }

  async function renderReportsV3() {
    const box = $("#reportList");

    if (!box) return;

    let data = {};

    try {
      await loadStockNameIndex();
      data = await loadReports();
    } catch (e) {
      console.error(
        "reports v3 load failed",
        e
      );

      box.innerHTML = `
        <div class="report-v2-empty">
          券商報告資料讀取失敗
        </div>
      `;

      return;
    }

    box.classList.add(
      "report-v2-wrap"
    );

    box.innerHTML = `
      <div class="report-v2-tools">
        <div class="report-search-card">
          <div class="report-search-wrap">
            <span class="report-search-icon">
              ⌕
            </span>

            <input
              id="reportSearch"
              type="search"
              inputmode="search"
              autocomplete="off"
              placeholder="搜尋股票、公司或報告內容，例如 CPU / CPO / 毛利率"
              aria-label="搜尋券商報告股票代號、公司名稱或內容關鍵字"
            >

            <button
              id="reportSearchClear"
              class="report-search-clear"
              type="button"
              aria-label="清除券商報告搜尋"
            >
              清除
            </button>
          </div>

          <span
            id="reportSearchMeta"
            class="report-search-meta"
          ></span>
        </div>

        <div class="report-v2-tabs">
          <button
            class="report-filter active"
            data-filter="all"
          >
            全部
          </button>

          <button
            class="report-filter"
            data-filter="upgrade"
          >
            上調
          </button>

          <button
            class="report-filter"
            data-filter="downgrade"
          >
            下調
          </button>

          <button
            class="report-filter"
            data-filter="initiate"
          >
            初評
          </button>

          <button
            class="report-filter"
            data-filter="maintain"
          >
            維持
          </button>

          <button
            class="report-filter"
            data-filter="sector"
          >
            產業
          </button>
        </div>
      </div>

      <div class="report-history-note">
        <span></span>
        <span>
          依收到日期永久保留
        </span>
      </div>

      <div id="reportCardsV3"></div>
    `;

    renderGroups();

    $("#reportSearch")?.addEventListener(
      "input",
      e => {
        currentQuery =
          e.target.value || "";

        renderGroups();
      }
    );

    $("#reportSearchClear")?.addEventListener(
      "click",
      () => {
        const input =
          $("#reportSearch");

        currentQuery = "";

        if (input) {
          input.value = "";
          input.focus();
        }

        renderGroups();
      }
    );

    $$(".report-filter").forEach(
      btn => {
        btn.addEventListener(
          "click",
          () => {
            $$(".report-filter").forEach(
              x => {
                x.classList.remove(
                  "active"
                );
              }
            );

            btn.classList.add(
              "active"
            );

            currentFilter =
              btn.dataset.filter || "all";

            renderGroups();
          }
        );
      }
    );

    setupDeepLink();

    window.__brokerReportsV3 = {
      data,
      items: allReports
    };
  }

  function reorderNavigation() {
    const order = [
      "home",
      "heat",
      "reports",
      "selfReports",
      "flows",
      "volume",
      "turnover",
      "marginLending",
      "ai",
      "holders",
      "monthlyRevenue"
    ];

    const nav =
      document.querySelector(
        "header nav"
      );

    if (nav) {
      order.forEach(
        id => {
          const btn =
            nav.querySelector(
              `[data-p="${id}"]`
            );

          if (btn) {
            nav.appendChild(btn);
          }
        }
      );
    }

    const select =
      $("#mobileNav");

    if (select) {
      order.forEach(
        id => {
          const option =
            select.querySelector(
              `option[value="${id}"]`
            );

          if (option) {
            select.appendChild(option);
          }
        }
      );
    }
  }

  async function addHomeReportCount() {
    let items = [];

    try {
      if (
        window.__brokerReportsV3?.items
      ) {
        items =
          window.__brokerReportsV3.items;
      } else {
        const res = await fetch(
          "./data/reports.json?v=" +
            Date.now(),
          { cache: "no-store" }
        );

        const data = await res.json();

        items =
          Array.isArray(data.items)
            ? data.items
            : [];
      }
    } catch (e) {
      console.error(
        "home report count failed",
        e
      );
    }

    const today = taipeiToday();

    const count =
      items.filter(
        r =>
          reportGroupDate(r) === today
      ).length;

    const feature =
      document.querySelector(
        '[data-feature="reports"] .feature-copy small'
      );

    if (feature) {
      feature.textContent =
        `今日 ${count} 份`;
    }

    const grid =
      $(".daily-signal-grid");

    if (
      grid &&
      !grid.querySelector(
        '[data-pulse-target="reports"]'
      )
    ) {
      const btn =
        document.createElement("button");

      btn.className =
        "daily-signal-item";

      btn.dataset.pulseTarget =
        "reports";

      btn.innerHTML = `
        <span
          class="daily-signal-icon signal-report"
        >
          ▤
        </span>

        <span>
          <small>
            券商報告
          </small>

          <strong>
            ${count}
          </strong>
        </span>

        <i>→</i>
      `;

      btn.addEventListener(
        "click",
        () => {
          if (
            typeof window.page ===
            "function"
          ) {
            window.page("reports");
          }
        }
      );

      grid.prepend(btn);
    }
  }

  function protectReportRenderer() {
    const box = $("#reportList");

    if (!box) return;

    let repairing = false;

    const observer =
      new MutationObserver(
        async () => {
          if (repairing) return;

          const legacy =
            box.querySelector(".report");

          const v3 =
            box.querySelector(
              "#reportCardsV3"
            );

          if (legacy && !v3) {
            repairing = true;

            try {
              await renderReportsV3();
            } finally {
              repairing = false;
            }
          }
        }
      );

    observer.observe(
      box,
      {
        childList: true,
        subtree: true
      }
    );
  }

  function highlightNotificationTarget(el) {
    if (!el) return;

    el.classList.add(
      "report-deep-highlight"
    );

    el.scrollIntoView({
      behavior: "smooth",
      block: "center"
    });

    setTimeout(
      () => {
        el.classList.remove(
          "report-deep-highlight"
        );
      },
      4500
    );
  }

  function findSelfReportCard(
    ticker,
    date,
    time
  ) {
    return [
      ...document.querySelectorAll(
        "#selfReportCards .self-report-card"
      )
    ].find(
      card => {
        const cardTicker =
          card.querySelector(
            ".titleline span"
          )?.textContent?.trim() || "";

        const eyebrow =
          card.querySelector(
            ".eyebrow"
          )?.textContent
            ?.replace(/\s+/g, " ")
            .trim() || "";

        const tickerOk =
          !ticker ||
          cardTicker === ticker;

        const dateOk =
          !date ||
          eyebrow.includes(date);

        const timeOk =
          !time ||
          eyebrow.includes(time);

        return (
          tickerOk &&
          dateOk &&
          timeOk
        );
      }
    );
  }

  function findRevenueCard(ticker) {
    return [
      ...document.querySelectorAll(
        "#revenueSections .revenue-card"
      )
    ].find(
      card =>
        (
          card.querySelector(
            ".ticker"
          )?.textContent?.trim() || ""
        ) === ticker
    );
  }

  function setupNotificationDeepLink() {
    const params =
      new URLSearchParams(
        location.search
      );

    const requestedPage =
      params.get("page");

    if (
      requestedPage !== "selfReports" &&
      requestedPage !== "monthlyRevenue"
    ) {
      return;
    }

    if (
      typeof window.page ===
      "function"
    ) {
      window.page(requestedPage);
    }

    const ticker =
      params.get("ticker") || "";

    const date =
      params.get("date") || "";

    const time =
      params.get("time") || "";

    let tries = 0;

    const timer = setInterval(
      () => {
        tries += 1;

        let target = null;

        if (
          requestedPage === "selfReports"
        ) {
          target = findSelfReportCard(
            ticker,
            date,
            time
          );
        }

        if (
          requestedPage === "monthlyRevenue"
        ) {
          target =
            findRevenueCard(ticker);
        }

        if (target) {
          clearInterval(timer);

          highlightNotificationTarget(
            target
          );

          return;
        }

        if (tries >= 20) {
          clearInterval(timer);
        }
      },
      250
    );
  }

  async function boot() {
    injectReportSearchStyle();

    reorderNavigation();

    setupNotificationDeepLink();

    protectReportRenderer();

    setTimeout(
      async () => {
        await renderReportsV3();

        reorderNavigation();

        await addHomeReportCount();
      },
      900
    );

    setTimeout(
      () => {
        reorderNavigation();
        addHomeReportCount();
      },
      2400
    );
  }

  if (
    document.readyState === "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      boot
    );
  } else {
    boot();
  }
})();

