// ui_v2.js 自結日期篩選更新
// 基準：repo main 最新 assets/ui_v2.js
// Git blob SHA: 5053700fdf4c25fd3a5a6ffe920f9b558c30e4d1
//
// 需求：
// 1. 總覽自結家數只算「今天 publish_date」
// 2. 自結公布頁提供日期篩選
// 3. 預設顯示最新有資料的日期
// 4. 股票搜尋只搜尋目前選定日期
//
// 注意：這是針對最新版 ui_v2.js 的完整修改區塊，不是舊版邏輯

let selfReportDateSelected = "latest";

function selfReportLocalDate() {
  const parts = new Intl.DateTimeFormat(
    "en-CA",
    {
      timeZone: "Asia/Taipei",
      year: "numeric",
      month: "2-digit",
      day: "2-digit"
    }
  ).formatToParts(new Date());

  const get = type =>
    parts.find(x => x.type === type)?.value || "";

  return `${get("year")}-${get("month")}-${get("day")}`;
}

function selfReportDates(items) {
  return [
    ...new Set(
      (items || [])
        .map(x => String(x.publish_date || "").trim())
        .filter(Boolean)
    )
  ].sort((a, b) => b.localeCompare(a));
}

function selfReportSelectedDate(items) {
  const dates = selfReportDates(items);

  if (!dates.length) return "";

  if (
    selfReportDateSelected !== "latest" &&
    dates.includes(selfReportDateSelected)
  ) {
    return selfReportDateSelected;
  }

  return dates[0];
}

function ensureSelfReportDatePicker(items) {
  const searchCard =
    document.querySelector(".self-report-search-card");

  if (!searchCard) return;

  let wrap =
    document.getElementById("selfReportDateFilter");

  if (!wrap) {
    wrap = document.createElement("div");
    wrap.id = "selfReportDateFilter";
    wrap.style.cssText =
      "width:100%;display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:2px";

    searchCard.prepend(wrap);
  }

  const dates = selfReportDates(items);
  const selected = selfReportSelectedDate(items);

  wrap.innerHTML = `
    <label
      for="selfReportDateSelect"
      style="font-size:13px;font-weight:700;opacity:.72"
    >
      公告日期
    </label>

    <select
      id="selfReportDateSelect"
      aria-label="篩選自結公告日期"
      style="
        min-height:42px;
        padding:0 38px 0 12px;
        border:1px solid #d8dee8;
        border-radius:11px;
        background:var(--card,#fff);
        color:inherit;
        font:inherit;
        font-weight:700;
      "
    >
      ${
        dates.map(date => `
          <option
            value="${date}"
            ${date === selected ? "selected" : ""}
          >
            ${date}
          </option>
        `).join("")
      }
    </select>
  `;

  const select =
    document.getElementById("selfReportDateSelect");

  if (select) {
    select.onchange = () => {
      selfReportDateSelected = select.value;
      selfReports(false);
    };
  }
}

/*
 * 在 buildMarketPulse() 原本讀取 self_reports.json 的 .then(d => {...})
 * 將 count 改為下面邏輯：
 *
 * const today = selfReportLocalDate();
 * const count = (d.items || []).filter(
 *   x => String(x.publish_date || "") === today
 * ).length;
 *
 * 如此首頁「自結監控」與「今日異動 → 自結公告」
 * 都只顯示今天的公告家數，不再顯示歷史累計
 */


/*
 * selfReports() 修改邏輯：
 *
 * 原本：
 * const allItems = d.items || [];
 *
 * 改成：
 */

function filterSelfReportsByDateAndSearch(d, searchText) {
  const allItems = d.items || [];

  ensureSelfReportDatePicker(allItems);

  const selectedDate =
    selfReportSelectedDate(allItems);

  const dateItems =
    selectedDate
      ? allItems.filter(
          x =>
            String(x.publish_date || "") ===
            selectedDate
        )
      : [];

  const normalizeSearch =
    value =>
      String(value || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "");

  const keyword =
    normalizeSearch(searchText);

  const arr =
    !keyword
      ? dateItems
      : dateItems.filter(x => {
          const ticker =
            normalizeSearch(x.ticker);

          const name =
            normalizeSearch(x.name);

          return (
            ticker.includes(keyword) ||
            name.includes(keyword)
          );
        });

  return {
    allItems,
    dateItems,
    arr,
    selectedDate
  };
}

/*
 * selfReports() 中 resultMeta 改為：
 *
 * const filtered =
 *   filterSelfReportsByDateAndSearch(
 *     d,
 *     selfReportSearch
 *   );
 *
 * const arr = filtered.arr;
 * const dateItems = filtered.dateItems;
 * const selectedDate = filtered.selectedDate;
 *
 * resultMeta.textContent =
 *   selfReportSearch
 *     ? `找到 ${arr.length} 筆｜${selectedDate} 共 ${dateItems.length} 筆自結`
 *     : `${selectedDate} 共 ${dateItems.length} 筆自結`;
 *
 * 空資料文字：
 * 「目前尚未偵測到新的自結公告」
 * 可改為：
 * `${selectedDate || "所選日期"}沒有自結公告`
 */
