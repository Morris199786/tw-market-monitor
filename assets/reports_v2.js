/* =========================================================
   券商報告 V3.6
   - 依報告發布日期分組
   - 歷史報告永久保留
   - 公司名稱 / 股票代號搜尋
   - 中文公司名搜尋英文報告
   - 全文關鍵字搜尋
   - 搜尋結果黃色標示
   - 上調 / 下調 / 初評 / 維持 / 產業篩選
   - Deep Link
   - 首頁券商報告數
   - 修正舊版畫面閃爍
   - 移除固定載入等待
   - 避免重複下載與渲染
   ========================================================= */

(function () {
  "use strict";

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
  let brokerDateMode = "all";
  let brokerCalendarMonth = "";
  let brokerSelectedDate = "";

  let reportsPromise = null;
  let stockIndexPromise = null;
  let renderPromise = null;

  let reportsData = null;
  let rendererReady = false;
  let repairing = false;

  const stockNamesByTicker = new Map();
  const localizedTextCache = new Map();

  /* =========================================================
     台灣公司名稱對照
     ========================================================= */

  const taiwanCompanyNames = [
    ["MediaTek", "聯發科"],
    ["Global Unichip", "創意"],
    ["GUC", "創意"],
    ["Taiwan Semiconductor Manufacturing Company", "台積電"],
    ["TSMC", "台積電"],
    ["United Microelectronics Corporation", "聯電"],
    ["UMC", "聯電"],
    ["Taiwan Union Technology", "台燿"],
    ["TUC", "台燿"],
    ["Vanguard International Semiconductor", "世界先進"],
    ["VIS", "世界先進"],
    ["ASE Technology Holding", "日月光投控"],
    ["ASEH", "日月光投控"],
    ["Advanced Semiconductor Engineering", "日月光"],
    ["ASE", "日月光"],
    ["Siliconware Precision Industries", "矽品"],
    ["SPIL", "矽品"],
    ["Shunsin-KY", "訊芯-KY"],
    ["ShunSin", "訊芯-KY"],
    ["WinWay", "穎崴"],
    ["MPI Corporation", "旺矽"],
    ["MPI", "旺矽"],
    ["Chroma", "致茂"],
    ["KYEC", "京元電子"],
    ["Integrated Service Technology", "宜特"],
    ["iST", "宜特"],
    ["FOCI", "上詮"],
    ["Browave", "波若威"],
    ["LuxNet", "華星光"],
    ["VisEra", "采鈺"],
    ["ProMOS", "茂德"],
    ["FitTech", "惠特"],
    ["Unimicron", "欣興"],
    ["Nan Ya PCB", "南電"],
    ["Kinsus", "景碩"],
    ["Elite Material Co., Ltd.", "台光電"],
    ["Elite Materials", "台光電"],
    ["Elite Material", "台光電"],
    ["Alchip", "世芯-KY"],
    ["Faraday Technology", "智原"],
    ["Novatek", "聯詠"],
    ["Realtek", "瑞昱"],
    ["Nanya Technology", "南亞科"],
    ["Winbond", "華邦電"],
    ["Macronix", "旺宏"],
    ["Phison", "群聯"],
    ["Largan", "大立光"],
    ["Wiwynn", "緯穎"],
    ["Quanta", "廣達"],
    ["Wistron", "緯創"],
    ["Inventec", "英業達"],
    ["Hon Hai", "鴻海"]
  ];

  const companyNameMap = new Map(
    taiwanCompanyNames.map(
      ([english, chinese]) => [
        english.toLowerCase(),
        chinese
      ]
    )
  );

  const companyNamePattern = new RegExp(
    "(" +
    taiwanCompanyNames
      .map(([name]) => name)
      .sort((a, b) => b.length - a.length)
      .map(name =>
        name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
      )
      .join("|") +
    ")",
    "gi"
  );

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function normalizeSearchText(value) {
    return String(value ?? "")
      .normalize("NFKC")
      .toLocaleLowerCase();
  }

  function localizeTaiwanCompanies(value) {
    const text = String(value ?? "");

    if (localizedTextCache.has(text)) {
      return localizedTextCache.get(text);
    }

    const converted = text
      .split(
        /((?:https?:\/\/|www\.)[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})/g
      )
      .map((part, index) => {
        if (index % 2) return part;

        return part.replace(
          companyNamePattern,
          (match, alias, offset, input) => {
            const before = input[offset - 1] || "";
            const afterChar =
              input[offset + match.length] || "";

            if (
              /[A-Za-z0-9_]/.test(before) ||
              /[A-Za-z0-9_]/.test(afterChar)
            ) {
              return match;
            }

            if (
              alias.toLowerCase() === "ist" &&
              match !== "iST"
            ) {
              return match;
            }

            const name =
              companyNameMap.get(alias.toLowerCase());

            if (!name) return match;

            const after =
              input.slice(offset + match.length);

            if (after.trimStart().startsWith(name)) {
              return "";
            }

            if (
              after.trimStart().startsWith("(" + name + ")") ||
              after.trimStart().startsWith("（" + name + "）")
            ) {
              return match;
            }

            return name;
          }
        );
      })
      .join("");

    if (localizedTextCache.size > 4000) {
      localizedTextCache.clear();
    }

    localizedTextCache.set(text, converted);

    return converted;
  }

  /* =========================================================
     搜尋黃色標示
     ========================================================= */

  function highlightedText(value) {
    const original =
      localizeTaiwanCompanies(value);

    const query =
      normalizeSearchText(
        localizeTaiwanCompanies(currentQuery.trim())
      );

    if (!query || !original) {
      return esc(original);
    }

    const units = Array.from(original);
    const normalizedParts = [];
    const startMap = [];
    const endMap = [];

    let offset = 0;

    for (const unit of units) {
      const start = offset;
      offset += unit.length;

      const normalized =
        normalizeSearchText(unit);

      for (let i = 0; i < normalized.length; i++) {
        normalizedParts.push(normalized[i]);
        startMap.push(start);
        endMap.push(offset);
      }
    }

    const searchable =
      normalizedParts.join("");

    if (!searchable.includes(query)) {
      return esc(original);
    }

    const ranges = [];
    let position = 0;

    while (position < searchable.length) {
      const found =
        searchable.indexOf(query, position);

      if (found === -1) break;

      ranges.push([
        startMap[found],
        endMap[found + query.length - 1]
      ]);

      position =
        found + Math.max(query.length, 1);
    }

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
        '<mark class="report-search-highlight">' +
        esc(original.slice(start, end)) +
        "</mark>";

      cursor = end;
    }

    result += esc(original.slice(cursor));

    return result;
  }

  /* =========================================================
     評等分類
     ========================================================= */

  function reportAction(r) {
    if (r.action === "initiate") {
      return "initiate";
    }

    if (r.validation_status === "needs_review") {
      return r.action || "none";
    }

    const price = value => {
      if (
        value == null ||
        String(value).trim() === ""
      ) {
        return null;
      }

      const n = Number(
        String(value).replace(/,/g, "")
      );

      return Number.isFinite(n) && n > 0
        ? n
        : null;
    };

    const oldPrice = price(r.target_price_old);
    const newPrice = price(r.target_price_new);

    if (oldPrice !== null && newPrice !== null) {
      if (newPrice > oldPrice) return "upgrade";
      if (newPrice < oldPrice) return "downgrade";
    } else if (
      ["upgrade", "downgrade"].includes(
        r.target_price_action
      )
    ) {
      return r.target_price_action;
    }

    if (
      r.report_type === "company" &&
      newPrice !== null &&
      oldPrice === null
    ) {
      const texts = [
        r.title,
        ...(Array.isArray(r.summary) ? r.summary : []),
        ...(Array.isArray(r.forecast_changes)
          ? r.forecast_changes
          : []),
        r.detail
      ];

      const directions = new Set();

      const pattern =
        /目標價\s*(?:由|從)\s*(?:新台幣|新臺幣|NT\$|NTD|TWD)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*元?\s*(上調|調升|提高|下調|調降|降低|調整)\s*(?:至|到|為)\s*(?:新台幣|新臺幣|NT\$|NTD|TWD)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)/g;

      for (const text of texts) {
        for (const match of String(text || "").matchAll(pattern)) {
          const from = price(match[1]);
          const to = price(match[3]);

          if (
            from === null ||
            to !== newPrice ||
            from === to
          ) {
            continue;
          }

          const direction =
            to > from ? "upgrade" : "downgrade";

          if (
            /上調|調升|提高/.test(match[2]) &&
            direction !== "upgrade"
          ) {
            continue;
          }

          if (
            /下調|調降|降低/.test(match[2]) &&
            direction !== "downgrade"
          ) {
            continue;
          }

          directions.add(direction);
        }
      }

      if (directions.size === 1) {
        return [...directions][0];
      }
    }

    return r.action || "none";
  }

  function actionClass(action) {
    if (action === "upgrade") return "is-up";
    if (action === "downgrade") return "is-down";
    if (action === "initiate") return "is-init";
    return "is-neutral";
  }

  /* =========================================================
     股票名稱索引
     ========================================================= */

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

  async function fetchJson(path) {
    const response = await fetch(
      path + "?v=" + Date.now(),
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw new Error(
        `${path} HTTP ${response.status}`
      );
    }

    return response.json();
  }

  function loadStockNameIndex() {
    if (stockIndexPromise) {
      return stockIndexPromise;
    }

    stockIndexPromise = Promise.allSettled([
      fetchJson("./data/master.json"),
      fetchJson("./data/sectors.json")
    ]).then(results => {
      stockNamesByTicker.clear();

      if (results[0].status === "fulfilled") {
        const stocks =
          results[0].value.stocks || {};

        Object.entries(stocks).forEach(
          ([ticker, row]) => {
            addStockName(ticker, row?.name);
          }
        );
      } else {
        console.warn(
          "report master index failed",
          results[0].reason
        );
      }

      if (results[1].status === "fulfilled") {
        const sectors =
          results[1].value.sectors || [];

        sectors.forEach(sector => {
          (sector.stocks || []).forEach(row => {
            addStockName(row?.ticker, row?.name);
          });
        });
      } else {
        console.warn(
          "report sector index failed",
          results[1].reason
        );
      }
    });

    return stockIndexPromise;
  }

  function namesForTicker(ticker) {
    return [
      ...(stockNamesByTicker.get(
        String(ticker || "").trim()
      ) || [])
    ];
  }

  /* =========================================================
     報告資料快取
     ========================================================= */

  function loadReports() {
    if (reportsPromise) {
      return reportsPromise;
    }

    reportsPromise =
      fetchJson("./data/reports.json")
        .then(data => {
          reportsData = data;

          allReports =
            Array.isArray(data.items)
              ? data.items
              : [];

          window.__brokerReportsV3 = {
            data,
            items: allReports
          };

          return data;
        })
        .catch(error => {
          reportsPromise = null;
          throw error;
        });

    return reportsPromise;
  }

  /* =========================================================
     日期處理
     ========================================================= */

  function reportGroupDate(r) {
    const isBroker = r.source_kind === "broker" || r.broker || r.report_type || r.source_file_id;
    return isBroker ? window.ReportDates.group(r) : window.ReportDates.original(r.date);
  }

  function dateLabel(day) {
    if (/^\d{4}-\d{2}$/.test(day)) {
      return day.replace("-", "/") + "（未註明日）";
    }

    if (/^\d{4}-\d{2}-\d{2}$/.test(day)) {
      return day.replaceAll("-", "/");
    }

    return day;
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

  /* =========================================================
     目標價與隱含漲跌幅
     ========================================================= */

  function upsideText(r) {
    if (
      r.implied_upside_pct == null ||
      !r.upside_basis
    ) {
      return "";
    }

    const n = Number(r.implied_upside_pct);

    if (!Number.isFinite(n)) {
      return "";
    }

    return (
      `（隱含${n >= 0 ? "漲" : "跌"}幅 ` +
      `${n >= 0 ? "+" : ""}${n.toFixed(1)}%，報告基準）`
    );
  }

  // 僅處理顯示層；不修改報告資料。
  function displayTargetPrice(value) {
    return String(value).replace(/[,，\s]/g, '');
  }

  function isPureTargetRecap(value) {
    const t = String(value || '').replace(/\s+/g, ' ').trim();
    return /^[^｜|]{1,35}[｜|]\s*目標(?:股)?價\s*(?:NT\$|新台幣)?\s*[\d,]+(?:\.\d+)?(?:\s*元)?(?:\s*[（(]隱含[漲跌]幅[^）)]*[）)])?[。.]?$/.test(t);
  }

  function detailLongformHtml(value, report) {
    const raw = String(value || '');
    if (raw.length < 350) return `<p>${brokerEmphasis(raw, report)}</p>`;
    // 只在句末或開頭辨識「短主題：」，避免數字、比例、網址誤斷。
    const re = /(^|[。！？]\s*)([^。！？\n：:]{3,24})[：:](?=[^：:\n])/g;
    const hits = [];
    for (const m of raw.matchAll(re)) {
      const title = m[2].trim();
      if (/\d{2,}|[%％=→]|https?|\d+\s*[:：]\s*\d+/i.test(title)) continue;
      if (title.split(/[,，、]/).length > 2) continue;
      const start = m.index + m[1].length;
      hits.push({start, bodyStart:start + m[2].length + 1, title});
    }
    if (hits.length < 2) return `<p>${brokerEmphasis(raw, report)}</p>`;
    let html = '<div class="report-longform">';
    if (raw.slice(0,hits[0].start).trim()) html += `<p class="report-longform-paragraph">${brokerEmphasis(raw.slice(0,hits[0].start).trim(),report)}</p>`;
    for (let i=0;i<hits.length;i++) {
      const h=hits[i];
      const body=raw.slice(h.bodyStart,i+1<hits.length?hits[i+1].start:raw.length).trim();
      html += `<section class="report-longform-section"><strong class="report-longform-heading">${highlightedText(h.title)}</strong><p class="report-longform-paragraph">${brokerEmphasis(body,report)}</p></section>`;
    }
    return html + '</div>';
  }

  // AI reading structure is optional. Legacy reports keep the existing renderer.
  function structuredResearchHtml(sections, report) {
    if (!Array.isArray(sections) || !sections.length) return '';
    const valid = sections.filter(s => s && Array.isArray(s.paragraphs) &&
      s.paragraphs.some(p => typeof p === 'string' && p.trim()));
    if (!valid.length) return '';
    return '<div class="report-longform report-longform-ai">' + valid.map(s => {
      const heading = String(s.heading || '').trim();
      const paras = s.paragraphs.filter(p => typeof p === 'string' && p.trim());
      return '<section class="report-longform-section">' +
        (heading ? '<strong class="report-longform-heading">' + highlightedText(heading) + '</strong>' : '') +
        paras.map(p => '<p class="report-longform-paragraph">' + brokerEmphasis(p, report) + '</p>').join('') +
        '</section>';
    }).join('') + '</div>';
  }

  function targetText(r) {
    if (r.validation_status === "needs_review") {
      return "";
    }

    const oldTp = r.target_price_old;
    const newTp = r.target_price_new;
    const upside = upsideText(r);

    if (oldTp != null && newTp != null) {
      return displayTargetPrice(oldTp) === displayTargetPrice(newTp)
        ? `${newTp}${upside}`
        : `${oldTp} → ${newTp}${upside}`;
    }

    if (newTp != null) {
      return String(newTp) + upside;
    }

    return "";
  }

  /* =========================================================
     搜尋
     ========================================================= */

  function searchText(r) {
    const primaryNames =
      namesForTicker(r.ticker);

    const beneficiarySearch =
      (
        Array.isArray(r.beneficiaries)
          ? r.beneficiaries
          : []
      ).flatMap(x => [
        x.name,
        x.ticker,
        x.reason,
        ...namesForTicker(x.ticker)
      ]);

    const fields = [
      r.broker,
      r.title,
      r.name,
      r.ticker,
      ...primaryNames,
      r.rating,
      r.push_reason,
      ...(Array.isArray(r.summary)
        ? r.summary
        : r.summary
          ? [r.summary]
          : []),
      r.detail,
      JSON.stringify(r.industry_sections || []),
      ...(Array.isArray(r.research_sections) ? r.research_sections.flatMap(s => [s?.heading, ...(Array.isArray(s?.paragraphs) ? s.paragraphs : [])]) : []),
      ...(Array.isArray(r.key_points)
        ? r.key_points
        : []),
      ...(Array.isArray(r.forecast_changes)
        ? r.forecast_changes
        : []),
      ...(Array.isArray(r.risks)
        ? r.risks
        : []),
      ...beneficiarySearch,
      // English aliases for the TPCA supply-chain references.
      ...(/\bTUC\b/i.test([r.title, r.detail, ...(Array.isArray(r.summary) ? r.summary : [])].join(" ")) ? ["台燿", "6274", "Taiwan Union Technology"] : [])
    ];

    return normalizeSearchText(
      fields
        .filter(value =>
          value !== null &&
          value !== undefined
        )
        .map(value =>
          String(value) + " " +
          localizeTaiwanCompanies(value)
        )
        .join(" ")
    );
  }

  function matches(r) {
    // Include sector/theme reports in search; keep source data unchanged.
    const okFilter =
      currentFilter === "all" ||
      reportAction(r) === currentFilter;

    const query =
      normalizeSearchText(currentQuery.trim());

    const localizedQuery =
      normalizeSearchText(
        localizeTaiwanCompanies(currentQuery.trim())
      );

    const text =
      query ? searchText(r) : "";

    const okSearch =
      !query ||
      text.includes(query) ||
      text.includes(localizedQuery);

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

    const sorted = [...groups.entries()].sort(
      (a, b) => {
        if (a[0] === "日期未確認") {
          return b[0] === a[0] ? 0 : 1;
        }

        if (b[0] === "日期未確認") {
          return -1;
        }

        return String(b[0]).localeCompare(
          String(a[0])
        );
      }
    );
    if (brokerDateMode === "latest") return sorted.slice(0, 1);
    if (brokerDateMode === "selected") return sorted.filter(([day]) => day === brokerSelectedDate);
    return sorted;
  }

  /* =========================================================
     報告卡片
     ========================================================= */

  function chips(r) {
    const arr = [];

    if (r.validation_status === "needs_review") {
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
      const action = reportAction(r);

      const targetClass =
        action === "upgrade"
          ? "report-target-up"
          : action === "downgrade"
            ? "report-target-down"
            : "";

      arr.push(`
        <span class="report-chip report-target ${targetClass}">
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
        <span class="report-chip report-original-date">
          原始日期 ${esc(r.date)}${reportGroupDate(r) !== window.ReportDates.original(r.date) ? `・歸類 ${esc(reportGroupDate(r))}` : ""}
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

  function listHtml(title, arr, r) {
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
            (x,i) => {
              const html=brokerEmphasis(x, r);
              return `<li>${html}</li>`;
            }
          ).join("")}
        </ul>
      </div>
    `;
  }

  // AI 指定的原文片段才加琥珀色底線；搜尋黃底仍優先。
  function brokerEmphasis(value, r) {
    const original = localizeTaiwanCompanies(value);
    const phrases = Array.isArray(r.emphasis) ? r.emphasis : [];
    const matches = phrases.map(x => localizeTaiwanCompanies(String(x || '').trim()))
      .filter(x => x.length >= 3 && original.includes(x))
      .sort((a,b) => b.length-a.length);
    if (!matches.length || currentQuery.trim()) return highlightedText(value);
    const ranges = [];
    matches.forEach(phrase => { let pos=0, idx; while ((idx=original.indexOf(phrase,pos)) !== -1) {
      if (!ranges.some(([a,b]) => idx < b && idx+phrase.length > a)) ranges.push([idx,idx+phrase.length]);
      pos=idx+phrase.length;
    }});
    ranges.sort((a,b)=>a[0]-b[0]);
    let out='',start=0;
    ranges.forEach(([a,b]) => {out+=esc(original.slice(start,a));out+='<span class="broker-ai-amber">'+esc(original.slice(a,b))+'</span>';start=b;});
    return out+esc(original.slice(start));
  }

  function brokerVisuals(r) {
    return Array.isArray(r.visualizations) && r.visualizations.length
      ? '<div class="broker-ai-visuals" data-broker-visuals></div>' : '';
  }

  function renderBrokerVisuals() {
    if (!window.BrokerReportCharts) return;
    document.querySelectorAll('#reportCardsV3 [data-broker-visuals]').forEach(box => {
      const report = allReports.find(r => String(r.id||'') === box.closest('[data-report-id]')?.dataset.reportId);
      if (report) window.BrokerReportCharts.render(box, report.visualizations);
    });
  }

  function card(r) {
    const actionValue = reportAction(r);

    const action =
      actionMap[actionValue] ||
      actionValue ||
      "研究報告";

    const stockTitle =
      r.report_type === "company"
        ? (
            `${r.name || ""}` +
            (r.ticker ? ` ${r.ticker}` : "")
          )
        : (r.title || "產業研究");

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

          <span class="report-action ${actionClass(actionValue)}">
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
                ${summary.filter(x => !isPureTargetRecap(x)).map(x => `
                  <li>
                    ${highlightedText(
                      x +
                      (
                        /目標(?:股)?價/.test(x) &&
                        !/隱含[漲跌]幅/.test(x)
                          ? upsideText(r)
                          : ""
                      )
                    )}
                  </li>
                `).join("")}
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
            ${window.IndustrySummary?.applies(r) ? window.IndustrySummary.render(r, value => brokerEmphasis(value, r)) : `            ${
              r.detail
                ? `
                  <div class="report-detail-block">
                    <div class="report-subtitle">
                      完整摘要
                    </div>

                    ${structuredResearchHtml(r.research_sections, r) || (r.ai_layout_version === "ai-directed-v2" ? `<p>${highlightedText(r.detail || "AI 閱讀結構缺漏，請檢查解析結果")}</p>` : detailLongformHtml(r.detail, r))}
                  </div>
                `
                : ""
            }

            ${listHtml("重點數據／邏輯", r.key_points, r)}
            ${listHtml("財測調整", r.forecast_changes, r)}
            ${listHtml("風險", r.risks, r)}
            ${brokerVisuals(r)}`}

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

  /* =========================================================
     搜尋與日期分組渲染
     ========================================================= */

  function updateSearchUi() {
    const clearBtn = $("#reportSearchClear");
    const meta = $("#reportSearchMeta");

    const queryActive =
      Boolean(currentQuery.trim());

    const filterActive =
      currentFilter !== "all";

    const visibleCount =
      allReports.filter(matches).length;

    const dateButton = $("#reportDateToggle");
    const latestButton = $("#reportLatest");
    if (dateButton) dateButton.textContent = brokerDateMode === "selected"
      ? `📅 ${brokerSelectedDate.replaceAll("-", "/")}` : "📅 全部日期";
    if (latestButton) latestButton.classList.toggle("active", brokerDateMode === "latest");

    if (clearBtn) {
      clearBtn.style.display =
        queryActive ? "inline-flex" : "none";
    }

    if (meta) {
      meta.textContent =
        queryActive || filterActive
          ? `找到 ${visibleCount} 份｜共 ${allReports.length} 份歷史報告`
          : `共 ${allReports.length} 份歷史報告`;
    }
  }

  function renderGroups() {
    const target = $("#reportCardsV3");

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
                <b>${esc(dateLabel(day))}</b>

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

    renderBrokerVisuals();

    $$("#reportCardsV3 [data-report-stock]").forEach(
      btn => {
        btn.addEventListener(
          "click",
          () => {
            const q =
              btn.dataset.reportStock || "";

            const input = $("#reportSearch");

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

  /* =========================================================
     防止舊版渲染
     ========================================================= */

  function injectLegacyProtection() {
    if ($("#reportLegacyProtection")) {
      return;
    }

    const style =
      document.createElement("style");

    style.id = "reportLegacyProtection";

    style.textContent = `
      #reportList .report:not(.report-v2-card) {
        display: none !important;
      }

      #reportList:not(.report-v2-wrap) {
        min-height: 90px;
      }

      #reportList .report-v2-empty {
        padding: 20px;
        text-align: center;
      }
    `;

    document.head.appendChild(style);
  }

  function protectReportRenderer() {
    const box = $("#reportList");

    if (!box) return;

    const observer =
      new MutationObserver(() => {
        if (repairing || !rendererReady) {
          return;
        }

        const v3 =
          box.querySelector("#reportCardsV3");

        if (v3) return;

        repairing = true;

        try {
          buildReportInterface();
        } finally {
          repairing = false;
        }
      });

    observer.observe(box, {
      childList: true,
      subtree: false
    });
  }

  /* =========================================================
     搜尋樣式
     ========================================================= */

  function injectReportSearchStyle() {
    if ($("#reportSearchFieldStyle")) {
      return;
    }

    const style =
      document.createElement("style");

    style.id = "reportSearchFieldStyle";

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
        font-size: 16px !important;
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
        border: 1px solid rgba(148,163,184,.30);
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
        transform: translateY(-50%) scale(.97);
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
      #reports mark.report-search-highlight {
        background: #ffd84d !important;
        color: #111827 !important;
      }

      html[data-theme="dark"]
      #reports .report-search-clear {
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
    if (!document.getElementById('brokerAmberEmphasisStyle')) {
      const amber=document.createElement('style');amber.id='brokerAmberEmphasisStyle';
      amber.textContent='#reports .broker-ai-amber{background:linear-gradient(transparent 78%,rgba(245,158,11,.58) 78%,rgba(245,158,11,.58) 97%,transparent 97%);box-decoration-break:clone;-webkit-box-decoration-break:clone}html[data-theme="dark"] #reports .broker-ai-amber{background:linear-gradient(transparent 77%,rgba(251,191,36,.48) 77%,rgba(251,191,36,.48) 97%,transparent 97%)}';
      document.head.appendChild(amber);
    }
  }

  /* =========================================================
     主畫面
     ========================================================= */

  function buildReportInterface() {
    const box = $("#reportList");

    if (!box) return;

    if (box.querySelector("#reportCardsV3")) {
      return;
    }

    box.classList.add("report-v2-wrap");

    box.innerHTML = `
      <div class="report-v2-tools">
        <div class="report-date-tools" aria-label="券商報告日期篩選">
          <button id="reportDateToggle" class="report-date-tool" type="button" aria-expanded="false" aria-controls="reportDateCalendar">📅 全部日期</button>
          <button id="reportLatest" class="report-date-tool" type="button">最新報告</button>
        </div>
        <div id="reportDateCalendar" class="report-date-calendar" hidden></div>
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
              value="${esc(currentQuery)}"
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
          <button class="report-filter" data-filter="all" type="button">
            全部
          </button>

          <button class="report-filter" data-filter="upgrade" type="button">
            上調
          </button>

          <button class="report-filter" data-filter="downgrade" type="button">
            下調
          </button>

          <button class="report-filter" data-filter="initiate" type="button">
            初評
          </button>

          <button class="report-filter" data-filter="maintain" type="button">
            維持
          </button>


        </div>
      </div>

      <div class="report-history-note">
        <span></span>

        <span>
          依報告發布日期分組・歷史報告永久保留
        </span>
      </div>

      <div id="reportCardsV3"></div>
    `;

    $$("#reportList .report-filter").forEach(
      btn => {
        btn.classList.toggle(
          "active",
          btn.dataset.filter === currentFilter
        );
      }
    );

    renderGroups();

    function drawBrokerCalendar() {
      const host = $("#reportDateCalendar");
      if (!host) return;
      const valid = allReports.filter(matches);
      const dates = new Set(valid.map(reportGroupDate));
      const first = [...dates].filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d)).sort().reverse()[0];
      if (!brokerCalendarMonth) brokerCalendarMonth = (first || new Date().toISOString().slice(0,10)).slice(0,7);
      const [year, month] = brokerCalendarMonth.split("-").map(Number);
      const offset = new Date(year, month-1, 1).getDay();
      const count = new Date(year, month, 0).getDate();
      const cells = Array.from({length: offset}, () => '<span></span>');
      for (let day=1; day<=count; day++) {
        const date = `${year}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
        cells.push(`<button type="button" data-broker-day="${date}" class="${brokerDateMode === "selected" && brokerSelectedDate === date ? "selected" : ""}">${day}${dates.has(date) ? "<i></i>" : ""}</button>`);
      }
      host.innerHTML = `<div class="report-cal-head"><button type="button" data-broker-month="-1">❮</button><strong>${year} 年 ${month} 月</strong><button type="button" data-broker-month="1">❯</button></div><div class="report-cal-grid">${["日","一","二","三","四","五","六"].map(d=>`<b>${d}</b>`).join("")}${cells.join("")}</div><div class="report-cal-foot"><button type="button" data-broker-action="today">今天</button><button type="button" data-broker-action="clear">清除</button><button type="button" data-broker-action="done">完成</button></div>`;
    }
    $("#reportDateToggle")?.addEventListener("click", () => {
      const calendar = $("#reportDateCalendar");
      if (!calendar) return;
      calendar.hidden = !calendar.hidden;
      $("#reportDateToggle").setAttribute("aria-expanded", String(!calendar.hidden));
      if (!calendar.hidden) drawBrokerCalendar();
    });
    $("#reportDateCalendar")?.addEventListener("click", e => {
      const button = e.target.closest("button");
      if (!button) return;
      if (button.dataset.brokerMonth) {
        const [y,m] = brokerCalendarMonth.split("-").map(Number);
        const d = new Date(y, m-1+Number(button.dataset.brokerMonth), 1);
        brokerCalendarMonth = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
        drawBrokerCalendar();
      }
      if (button.dataset.brokerDay) {
        brokerSelectedDate = button.dataset.brokerDay;
        brokerDateMode = "selected";
        renderGroups();
        drawBrokerCalendar();
      }
      if (button.dataset.brokerAction === "today") {
        const d = new Date();
        brokerCalendarMonth = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
        brokerSelectedDate = `${brokerCalendarMonth}-${String(d.getDate()).padStart(2,"0")}`;
        brokerDateMode = "selected";
        renderGroups();
        drawBrokerCalendar();
      }
      if (button.dataset.brokerAction === "clear") {
        brokerDateMode = "all";
        brokerSelectedDate = "";
        renderGroups();
        drawBrokerCalendar();
      }
      if (button.dataset.brokerAction === "done") {
        $("#reportDateCalendar").hidden = true;
        $("#reportDateToggle").setAttribute("aria-expanded", "false");
      }
    });
    $("#reportLatest")?.addEventListener("click", () => {
      brokerDateMode = brokerDateMode === "latest" ? "all" : "latest";
      brokerSelectedDate = "";
      brokerCalendarMonth = "";
      $("#reportDateCalendar").hidden = true;
      $("#reportDateToggle").setAttribute("aria-expanded", "false");
      renderGroups();
      const target = $("#reportCardsV3 .report-date-group");
      if (target) { target.open = true; target.scrollIntoView({behavior:"smooth",block:"start"}); }
    });

    $("#reportSearch")?.addEventListener(
      "input",
      event => {
        currentQuery =
          event.target.value || "";

        renderGroups();
      }
    );

    $("#reportSearchClear")?.addEventListener(
      "click",
      () => {
        const input = $("#reportSearch");

        currentQuery = "";

        if (input) {
          input.value = "";
          input.focus();
        }

        renderGroups();
      }
    );

    $$("#reportList .report-filter").forEach(
      btn => {
        btn.addEventListener(
          "click",
          () => {
            $$("#reportList .report-filter").forEach(
              item => item.classList.remove("active")
            );

            btn.classList.add("active");

            currentFilter =
              btn.dataset.filter || "all";

            renderGroups();
          }
        );
      }
    );

    setupDeepLink();
  }

  function renderReportsV3() {
    if (renderPromise) {
      return renderPromise;
    }

    renderPromise =
      Promise.all([
        loadStockNameIndex(),
        loadReports()
      ])
        .then(() => {
          rendererReady = true;
          buildReportInterface();
          return reportsData;
        })
        .catch(error => {
          console.error(
            "reports v3 load failed",
            error
          );

          const box = $("#reportList");

          if (box) {
            box.innerHTML = `
              <div class="report-v2-empty">
                券商報告資料讀取失敗
              </div>
            `;
          }

          throw error;
        })
        .finally(() => {
          renderPromise = null;
        });

    return renderPromise;
  }

  /* =========================================================
     券商報告 Deep Link
     ========================================================= */

  function setupDeepLink() {
    const params =
      new URLSearchParams(location.search);

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

    const el = [
      ...document.querySelectorAll(
        "#reportCardsV3 [data-report-id]"
      )
    ].find(
      item => item.dataset.reportId === reportId
    );

    if (!el) return;

    const group =
      el.closest(".report-date-group");

    if (group) {
      group.open = true;
    }

    const detail =
      el.querySelector(".report-details");

    if (detail) {
      detail.open = true;
    }

    el.classList.add("report-deep-highlight");

    requestAnimationFrame(() => {
      el.scrollIntoView({
        behavior: "smooth",
        block: "center"
      });
    });

    setTimeout(() => {
      el.classList.remove(
        "report-deep-highlight"
      );
    }, 4500);
  }

  /* =========================================================
     導覽排序
     ========================================================= */

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
      document.querySelector("header nav");

    if (nav) {
      order.forEach(id => {
        const btn =
          nav.querySelector(`[data-p="${id}"]`);

        if (btn) {
          nav.appendChild(btn);
        }
      });
    }

    const select = $("#mobileNav");

    if (select) {
      order.forEach(id => {
        const option =
          select.querySelector(
            `option[value="${id}"]`
          );

        if (option) {
          select.appendChild(option);
        }
      });
    }
  }

  /* =========================================================
     首頁券商報告數
     ========================================================= */

  async function addHomeReportCount() {
    let items = [];

    try {
      const data = await loadReports();

      items =
        Array.isArray(data.items)
          ? data.items
          : [];
    } catch (error) {
      console.error(
        "home report count failed",
        error
      );

      return;
    }

    const today = taipeiToday();

    const count =
      items.filter(
        r => reportGroupDate(r) === today
      ).length;

    // Count today's published records, not API attempts. Failure is not zero.
    const readHome = async path => {
      const response = await fetch(path, {cache: "no-store"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    };
    const results = await Promise.allSettled([
      readHome("./data/research_meta.json"),
      readHome("./data/self_reports.json"),
      readHome("./data/quarterly_earnings.json"),
      readHome("./data/quarterly_earnings_recovered.json")
    ]);
    const value = i => results[i].status === "fulfilled" ? results[i].value : null;
    const research = Array.isArray(value(0)) ? value(0) : null;
    const unique = list => new Set(list.map(r => r.id || r.source_file_id ||
      JSON.stringify([r.date,r.source,r.broker,r.company,r.name,r.title,r.ticker]))).size;
    const todayResearch = research?.filter(r => r.source_kind !== "broker" &&
      String(r.market || "TW").toUpperCase() !== "US" && reportGroupDate(r) === today);
    const reportCount = unique(items.filter(r => reportGroupDate(r) === today));
    const industryCount = todayResearch ? unique(todayResearch.filter(r =>
      r.category === "產業研究" || r.category === "產業報告")) : null;
    const memoCount = todayResearch ? unique(todayResearch.filter(r =>
      r.category === "法說／訪談" || (!r.category &&
      ["call memo", "法說會"].includes(String(r.original_type || "").toLowerCase())))) : null;
    const morningCount = todayResearch ? unique(todayResearch.filter(r => r.category === "早報")) : null;
    const setFeature = (id, text) => {
      const el = document.querySelector(`[data-feature="${id}"] .feature-copy small`);
      if (el) { el.textContent = text; el.style.whiteSpace = "pre-line"; el.style.lineHeight = "1.5"; }
    };
    setFeature("reports", `今日\n報告 ${industryCount === null ? "—" : reportCount + industryCount} 篇\nmemo ${memoCount ?? "—"} 篇・早報 ${morningCount ?? "—"} 篇`);
    const companiesToday = list => new Set(list.filter(r =>
      reportGroupDate({date:r.publish_date}) === today).map(r =>
      String(r.ticker || r.name || "").replace(/\.(TW|TWO)$/i, "")).filter(Boolean)).size;
    const selfRows = value(1)?.items;
    const currentQuarterRows = value(2)?.reports;
    const recovered = value(3)?.reports || [];
    const quarterMap = new Map();
    for (const r of [...recovered, ...(currentQuarterRows || [])]) quarterMap.set(`${r.ticker}|${r.period}`, r);
    setFeature("selfReports", `今日\n自結 ${Array.isArray(selfRows) ? companiesToday(selfRows) : "—"} 家・季報 ${Array.isArray(currentQuarterRows) ? companiesToday([...quarterMap.values()]) : "—"} 家`);

    const grid = $(".daily-signal-grid");

    if (!grid) return;

    let btn =
      grid.querySelector(
        '[data-pulse-target="reports"]'
      );

    if (!btn) {
      btn = document.createElement("button");

      btn.className = "daily-signal-item";
      btn.dataset.pulseTarget = "reports";

      btn.innerHTML = `
        <span class="daily-signal-icon signal-report">
          ▤
        </span>

        <span>
          <small>券商報告</small>
          <strong>${count}</strong>
        </span>

        <i>→</i>
      `;

      btn.addEventListener("click", () => {
        if (typeof window.page === "function") {
          window.page("reports");
        }
      });

      grid.prepend(btn);
    } else {
      const strong = btn.querySelector("strong");

      if (strong) {
        strong.textContent = String(count);
      }
    }
  }

  /* =========================================================
     自結與月營收 Deep Link
     ========================================================= */

  function highlightNotificationTarget(el) {
    if (!el) return;

    el.classList.add("report-deep-highlight");

    el.scrollIntoView({
      behavior: "smooth",
      block: "center"
    });

    setTimeout(() => {
      el.classList.remove(
        "report-deep-highlight"
      );
    }, 4500);
  }

  function findSelfReportCard(ticker, date, time) {
    return [
      ...document.querySelectorAll(
        "#selfReportCards .self-report-card"
      )
    ].find(card => {
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

      return (
        (!ticker || cardTicker === ticker) &&
        (!date || eyebrow.includes(date)) &&
        (!time || eyebrow.includes(time))
      );
    });
  }

  function findRevenueCard(ticker) {
    return [
      ...document.querySelectorAll(
        "#revenueSections .revenue-card"
      )
    ].find(card =>
      (
        card.querySelector(
          ".ticker"
        )?.textContent?.trim() || ""
      ) === ticker
    );
  }

  function setupNotificationDeepLink() {
    const params =
      new URLSearchParams(location.search);

    const requestedPage =
      params.get("page");

    if (
      requestedPage !== "selfReports" &&
      requestedPage !== "monthlyRevenue"
    ) {
      return;
    }

    if (typeof window.page === "function") {
      window.page(requestedPage);
    }

    const ticker = params.get("ticker") || "";
    const date = params.get("date") || "";
    const time = params.get("time") || "";

    let tries = 0;

    const timer = setInterval(() => {
      tries++;

      let target = null;

      if (requestedPage === "selfReports") {
        target = findSelfReportCard(
          ticker,
          date,
          time
        );
      }

      if (requestedPage === "monthlyRevenue") {
        target = findRevenueCard(ticker);
      }

      if (target) {
        clearInterval(timer);
        highlightNotificationTarget(target);
        return;
      }

      if (tries >= 20) {
        clearInterval(timer);
      }
    }, 250);
  }

  /* =========================================================
     啟動
     ========================================================= */

  function boot() {
    injectLegacyProtection();
    injectReportSearchStyle();

    reorderNavigation();
    setupNotificationDeepLink();

    protectReportRenderer();

    // 立即載入，不等待 900ms
    renderReportsV3()
      .then(() => {
        addHomeReportCount();
      })
      .catch(error => {
        console.error(
          "broker report initialization failed",
          error
        );
      });

    // 首頁元件可能稍後建立，只重試顯示數字
    setTimeout(() => {
      addHomeReportCount();
    }, 1200);
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      boot,
      { once: true }
    );
  } else {
    boot();
  }
})();

