/* Display grouping only: never change source dates, IDs, or AI processing keys. */
(function (root) {
  'use strict';
  function original(value) {
    const s = String(value || '').trim().normalize('NFKC');
    const m = s.match(/^(\d{4})(?:[-/](\d{1,2})[-/](\d{1,2})|(\d{2})(\d{2}))(?:$|[T\s])/);
    if (m) {
      const y = +m[1], month = +(m[2] || m[4]), day = +(m[3] || m[5]);
      const d = new Date(Date.UTC(y, month - 1, day));
      if (d.getUTCFullYear() === y && d.getUTCMonth() === month - 1 && d.getUTCDate() === day)
        return d.toISOString().slice(0, 10);
    }
    const month = s.match(/^(\d{4})[-/](\d{1,2})$/);
    return month && +month[2] >= 1 && +month[2] <= 12
      ? `${month[1]}-${month[2].padStart(2, '0')}` : '日期未確認';
  }

  function foreign(r) {
    return /morgan\s*stanley|摩根士丹利|大摩|goldman\s*sachs|高盛|\bciti\b|花旗|\bubs\b|瑞銀|daiwa|大和|\bbofa\b|merrill\s*lynch|美銀|美林|\bclsa\b|里昂|nomura|野村|j\.?p\.?\s*morgan|小摩|摩根大通|hsbc|匯豐|deutsche|德意志|barclays|巴克萊|jefferies|傑富瑞|macquarie|麥格理|aletheia|gf\s*securities|广发海外|廣發海外/i.test(String(r.broker || r.source || ''));
  }

  function nextWeekday(day, addOneDay) {
    const d = new Date(day + 'T00:00:00Z');
    if (addOneDay) d.setUTCDate(d.getUTCDate() + 1);
    while (d.getUTCDay() === 0 || d.getUTCDay() === 6)
      d.setUTCDate(d.getUTCDate() + 1);
    return d.toISOString().slice(0, 10);
  }

  function group(r) {
    const day = original(r.original_date || r.date);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return day;

    // Keep the existing weekend adjustment for domestic reports.
    if (!foreign(r)) return nextWeekday(day, false);

    // The backend stores the Drive upload date as group_date (from modified_time).
    // received_at is a fallback; never use today's date or a mutable browser clock.
    const uploaded = original(r.group_date || r.received_at);
    const tPlusOne = nextWeekday(day, true);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(uploaded)) return tPlusOne;

    // A Friday report uploaded Friday stays Friday; uploaded on a weekend
    // is grouped on Monday. Late uploads never push beyond T+1 trading day.
    const uploadTradingDay = nextWeekday(uploaded, false);
    return uploadTradingDay < tPlusOne ? uploadTradingDay : tPlusOne;
  }

  root.ReportDates = Object.freeze({original, foreign, group});
})(globalThis);
