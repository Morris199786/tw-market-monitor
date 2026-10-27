/* 產業資料庫：券商報告／法說訪談／市場情報／美股；不呼叫 AI API。 */
(() => {
'use strict';
const root = document.getElementById('reports');
const legacy = document.getElementById('reportList');
if (!root || !legacy) return;
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clean = x => {
  if (Array.isArray(x)) return x.map(clean).filter(Boolean).join('\n');
  const v = String(x ?? '').trim();
  return /^(?:null|none|nan)$/i.test(v) ? '' : v;
};
const categories = ['全部','券商報告','產業報告','早報','法說／訪談','美股'];
let category = '全部', query = '', rows = [], manifest = null;
let selectedDay = '', calendarMonth = '', searchSeq = 0, searchHits = null;
let indexRows = []; 
let limit = 30, loaded = false, loading = false, searchTimer, readerSerial = 0, scrollY = 0;
const cache = new Map();
const panel = document.createElement('section');
panel.id = 'researchMergedPanel';
panel.innerHTML = `<div class="rm-toolbar"><div class="rm-cats">${categories.map(c => `<button type="button" class="rm-chip" data-category="${esc(c)}">${esc(c)}</button>`).join('')}</div><div class="rm-date-tools"><button id="rmDateToggle" type="button">📅 <span id="rmDateLabel">全部日期</span></button><button id="rmLatest" type="button">最新報告</button></div><div class="rm-search"><input id="rmQuery" type="search" placeholder="搜尋公司、代號、主題或內文" aria-label="搜尋研究報告"><button id="rmClear" type="button">清除</button></div><div class="rm-meta" id="rmMeta">載入研究索引中…</div><div id="rmCalendar" hidden></div></div><div id="rmCards"></div><button id="rmMore" type="button" hidden>顯示更多</button>`;
legacy.parentNode.insertBefore(panel, legacy);
const reader = document.createElement('div');
reader.id = 'rmReader'; reader.hidden = true;
reader.innerHTML = `<div class="rm-reader-header" role="banner"><strong id="rmReaderTitle"></strong><button type="button" id="rmClose" aria-label="關閉">✕</button></div><main id="rmReaderContent"></main>`;
document.body.appendChild(reader);
const style = document.createElement('style');
style.textContent = `
#researchMergedPanel[hidden],#researchMergedPanel [hidden],#rmReader[hidden]{display:none!important}
#researchMergedPanel{font:14px/1.65 -apple-system,BlinkMacSystemFont,'Noto Sans TC',sans-serif;color:#243246;margin:12px 0 24px}
#researchMergedPanel * ,#rmReader *{box-sizing:border-box}
#researchMergedPanel .rm-toolbar{display:grid;gap:10px;margin-bottom:14px}
#researchMergedPanel .rm-cats{display:flex;flex-wrap:nowrap;align-items:center;gap:8px;padding:2px 0 6px;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;scrollbar-width:none;scroll-snap-type:x proximity}
#researchMergedPanel .rm-cats::-webkit-scrollbar{display:none}
#researchMergedPanel button,#researchMergedPanel input{font:inherit}
#researchMergedPanel .rm-chip{flex:0 0 auto;white-space:nowrap;min-height:40px;border:1px solid #dce1e8;background:#fff;color:#808895;border-radius:999px;padding:7px 14px;font-size:14px;font-weight:750;text-align:center;scroll-snap-align:nearest}
#researchMergedPanel .rm-chip.active{background:#141924;border-color:#141924;color:#fff}
#researchMergedPanel .rm-search{display:flex;gap:8px}
#researchMergedPanel #rmQuery{min-width:0;flex:1;background:#fff;color:#243246;border:1px solid #d4dce7;border-radius:10px;padding:10px 12px;font-size:14px}
#researchMergedPanel #rmClear,#researchMergedPanel #rmMore{border:1px solid #d4dce7;background:#fff;color:#243246;border-radius:10px;padding:10px 13px}
#researchMergedPanel .rm-meta{font-size:12px;color:#64748b}
#researchMergedPanel .rm-date{font-weight:700;margin:20px 0 8px;font-size:14px}
#researchMergedPanel .rm-card{border:1px solid #dce3eb;background:#fff;border-radius:15px;padding:14px;margin:10px 0;overflow-wrap:anywhere;min-width:0}
#researchMergedPanel .rm-title{font-size:17px;font-weight:750;line-height:1.45}
#researchMergedPanel .rm-sub{color:#64748b;font-size:12px;margin:5px 0 10px}
#researchMergedPanel .rm-story{white-space:pre-line;font-size:14px;line-height:1.7;display:block;overflow:visible}
#researchMergedPanel .rm-company-list{margin:8px 0 12px;color:#64748b;font-size:13px}
#researchMergedPanel .rm-company-list>div{padding:3px 0}
#researchMergedPanel .rm-open{margin-top:10px;border:0;border-radius:8px;background:#eaf1ff;color:#2058bb;padding:8px 12px;font-weight:650}
#researchMergedPanel #rmMore{width:100%;margin-top:12px}
#rmReader{position:fixed;inset:0;z-index:2147483000;background:#f7f9fc;color:#243246;overflow:auto;width:100%;font:15px/1.8 -apple-system,BlinkMacSystemFont,'Noto Sans TC',sans-serif;overscroll-behavior:contain}
#rmReader .rm-reader-header{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#fff;border-bottom:1px solid #e1e6ee;padding:calc(12px + env(safe-area-inset-top)) 16px 12px}
#rmReaderTitle{flex:1;min-width:0;font-size:17px;line-height:1.35;overflow-wrap:anywhere}
#rmClose{flex:0 0 42px;border:1px solid #dce3eb;background:#fff;color:#233247;border-radius:50%;width:38px;height:38px;font-size:21px}
#rmReaderContent{max-width:900px;width:100%;margin:auto;padding:18px 15px calc(28px + env(safe-area-inset-bottom))}
#rmReader .rm-info{color:#64748b;font-size:13px;margin-bottom:10px}
#rmReader .rm-section{background:#fff;border:1px solid #e3e8f0;border-radius:13px;padding:15px;margin:12px 0;overflow-wrap:anywhere}
#rmReader h3{font-size:16px;margin:0 0 10px;color:#1d3554}
#rmReader .rm-table-scroll{overflow-x:auto;max-width:100%}
#rmReader table{border-collapse:collapse;width:100%;font-size:13px}
#rmReader th,#rmReader td{padding:10px;border-bottom:1px solid #e1e6ee;text-align:left;vertical-align:top;min-width:95px}
#rmReader .rm-number{font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}
#rmReader td details{min-width:100px;max-width:260px}
#rmReader .rm-original-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.8}
#rmReader .rm-table-wrap{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
#rmReader table{border-collapse:collapse;width:100%;font-size:14px}
#rmReader th,#rmReader td{border-bottom:1px solid #e6ebf2;text-align:left;padding:9px 10px;vertical-align:top}
#rmReader th{background:#f3f6fa;font-weight:650}
#researchAiAudit,#reportList .report-v2-tabs{display:none!important}
#researchMergedPanel .rm-date-group{margin:0 0 10px;border:1px solid #dce3eb;border-radius:17px;background:#f8fafc;overflow:hidden}
#researchMergedPanel .rm-date-group>.report-date-head{min-height:64px;display:flex;align-items:center;justify-content:space-between;padding:12px 16px;cursor:pointer;list-style:none}
#researchMergedPanel .rm-date-group>.report-date-head::-webkit-details-marker{display:none}
#researchMergedPanel .rm-date-group>.report-date-head b{font-size:17px}
#researchMergedPanel .rm-date-group>.report-date-head small{font-size:12px;color:#8a94a3;margin-left:8px}
#researchMergedPanel .rm-date-group>.report-date-body{padding:0 12px 12px}
#researchMergedPanel .rm-date-group[open] .report-date-arrow{transform:rotate(180deg)}
#researchMergedPanel .rm-date-tools{display:flex;gap:9px}
#researchMergedPanel .rm-date-tools button{border:1px solid #d4dce7;border-radius:12px;background:#fff;color:#263344;padding:9px 12px}
#rmCalendar{max-width:440px;border:1px solid #dce3eb;border-radius:18px;padding:15px;background:#fff;box-shadow:0 12px 35px #11182724}
#rmCalendar .rm-cal-head,#rmCalendar .rm-cal-foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:8px 0 14px}
#rmCalendar button{background:transparent;color:#1d293b;border:0;border-radius:10px;min-height:39px;font:inherit}
#rmCalendar .rm-cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;text-align:center}
#rmCalendar .rm-cal-grid>b{padding:8px 0;color:#7a8494}
#rmCalendar .rm-cal-grid>button{position:relative;min-height:45px}
#rmCalendar .rm-cal-grid>button.selected{background:#151b27;color:#fff}
#rmCalendar .rm-cal-grid i{position:absolute;bottom:3px;left:calc(50% - 3px);width:6px;height:6px;border-radius:50%;background:#26b879}
#rmCalendar .rm-cal-foot button{border:1px solid #dce3eb;padding:6px 12px}
#rmCalendar .rm-cal-foot button:last-child{background:#151b27;color:#fff}
#researchMergedPanel mark.rm-hit,#rmReader mark.rm-hit{background:#ffe17b;color:#243246;border-radius:2px;padding:0 1px}
#researchMergedPanel .rm-type{font-weight:750;color:#2563c9}
#researchMergedPanel .rm-empty{padding:20px;text-align:center;color:#64748b}
html[data-theme=dark] #researchMergedPanel .rm-chip,html[data-theme=dark] #rmCalendar,html[data-theme=dark] #researchMergedPanel .rm-date-group{background:#22272e;color:#e5e8ec;border-color:#414a55}
html[data-theme=dark] #researchMergedPanel .rm-chip.active{background:#10151e;color:#fff}
html[data-theme=dark] #researchMergedPanel .rm-card{background:#22272e;color:#e5e8ec;border-color:#414a55}
body.rm-reader-open{overflow:hidden}
@media(max-width:600px){#rmReaderContent{padding:12px 12px 30px}#rmReader .rm-section{padding:12px}}

#rmReader .rm-ai-chart{margin:18px 0;padding:16px;border:1px solid #dfe6ef;border-radius:14px;background:#fbfcfe;max-width:100%;overflow:hidden}
#rmReader .rm-ai-chart figcaption{font-size:16px;font-weight:750;margin-bottom:12px}
#rmReader .rm-ai-bars{display:grid;gap:12px}
#rmReader .rm-ai-barrow{display:grid;grid-template-columns:minmax(90px,1fr) minmax(70px,2fr) auto;gap:9px;align-items:center;font-size:13px}
#rmReader .rm-ai-track{height:13px;border-radius:7px;background:#e9eef4;overflow:hidden}
#rmReader .rm-ai-track i{display:block;height:100%;border-radius:7px}
#rmReader .rm-ai-line{display:block;width:100%;max-height:220px}
#rmReader .rm-ai-donut{height:180px;width:180px;max-width:100%;border-radius:50%;margin:0 auto 14px;mask:radial-gradient(circle,transparent 0 45%,#000 46%);-webkit-mask:radial-gradient(circle,transparent 0 45%,#000 46%)}
#rmReader .rm-ai-legend{display:flex;gap:9px 16px;flex-wrap:wrap;font-size:12px;margin-top:12px}
#rmReader .rm-ai-legend span{display:inline-flex;gap:5px;align-items:center}
#rmReader .rm-ai-legend i{width:9px;height:9px;display:inline-block;border-radius:2px}
#rmReader .rm-ai-chart small{display:block;color:#64748b;margin-top:10px}
`;
style.textContent += `
#rmReader .rm-ai-heading{font-size:16px;margin:18px 0 8px}
#rmReader .rm-ai-paragraph{margin:10px 0;line-height:1.85;white-space:pre-wrap}
#rmReader .rm-ai-list{padding-left:22px;margin:10px 0}
#rmReader .rm-ai-list li{margin:6px 0}
#rmReader .rm-ai-quote{border-left:3px solid #94a3b8;padding:6px 14px;margin:12px 0;background:#f8fafc;white-space:pre-wrap}
 /* AI 全文閱讀：只改善排版，不更動 AI 產出的內容 */
 #rmReader .rm-ai-paragraph{font-size:16px;line-height:1.72;margin:10px 0 15px;overflow-wrap:break-word}
 #rmReader .rm-ai-heading{font-size:17px;line-height:1.5;margin:23px 0 10px}
 #rmReader .rm-ai-list{font-size:16px;line-height:1.72}
 #rmReader .rm-ai-table{margin:16px 0 20px;min-width:0;max-width:100%}
 #rmReader .rm-ai-table-title{font-size:15px;font-weight:750;color:#1d3554;margin:0 0 9px;line-height:1.5}
 #rmReader .rm-ai-table-hint{font-size:12px;color:#64748b;margin:0 0 7px}
 #rmReader .rm-ai-table .rm-table-scroll{display:block;max-width:100%;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;border:1px solid #e3e8f0;border-radius:9px}
 #rmReader .rm-ai-table table{width:100%;min-width:560px;table-layout:auto;border-collapse:collapse;font-size:14px;line-height:1.55}
 #rmReader .rm-ai-table[data-cols="4"] table{min-width:760px}
 #rmReader .rm-ai-table[data-cols="5"] table{min-width:900px}
 #rmReader .rm-ai-table th,#rmReader .rm-ai-table td{min-width:130px;padding:11px 13px;overflow-wrap:break-word;word-break:normal;vertical-align:top}
 #rmReader .rm-ai-table th{white-space:nowrap;background:#f3f6fa;font-weight:700}
 #rmReader .rm-ai-table-note{display:block;font-size:12px;line-height:1.6;color:#64748b;margin-top:8px}
 @media(max-width:600px){
   #rmReader .rm-ai-paragraph{font-size:16px;line-height:1.7;margin:9px 0 13px}
   #rmReader .rm-ai-heading{font-size:17px;margin:20px 0 8px}
   #rmReader .rm-ai-list{font-size:16px;line-height:1.7}
   #rmReader .rm-ai-table table{font-size:13.5px;min-width:580px}
   #rmReader .rm-ai-table[data-cols="4"] table{min-width:780px}
   #rmReader .rm-ai-table[data-cols="5"] table{min-width:940px}
   #rmReader .rm-ai-table th,#rmReader .rm-ai-table td{padding:10px 12px;min-width:135px}
 }
`;

/* 2026-10-27: 全資料庫一致字級；閱讀全文標題列隔離網站全域樣式 */
style.textContent += `
#researchMergedPanel .rm-title{font-size:18px!important;line-height:1.45!important}
#researchMergedPanel .rm-story{font-size:15px!important;line-height:1.65!important;white-space:pre-line!important;margin:7px 0 10px!important}
#researchMergedPanel .rm-sub,#researchMergedPanel .report-meta{font-size:13px!important;line-height:1.5!important}
#researchMergedPanel .rm-card{padding:13px!important}
#researchMergedPanel .rm-card .report-title{font-size:18px!important;line-height:1.45!important}
#researchMergedPanel .rm-card .report-summary,#researchMergedPanel .rm-card .report-details-body{font-size:15px!important;line-height:1.65!important}
#researchMergedPanel .rm-card .report-summary li{margin-bottom:5px!important}
#rmReader{font-size:16px!important;line-height:1.65!important}
#rmReader > .rm-reader-header{position:sticky!important;top:0!important;z-index:10!important;display:flex!important;flex-direction:row!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;width:100%!important;min-height:62px!important;height:auto!important;margin:0!important;padding:calc(9px + env(safe-area-inset-top)) 16px 10px!important;background:#fff!important;color:#243246!important;border-bottom:1px solid #e1e6ee!important}
#rmReaderTitle{display:block!important;flex:1 1 auto!important;min-width:0!important;font-size:18px!important;line-height:1.45!important;font-weight:750!important;white-space:normal!important;overflow-wrap:anywhere!important;color:#243246!important}
#rmReader > .rm-reader-header #rmClose{display:flex!important;align-items:center!important;justify-content:center!important;flex:0 0 40px!important;margin:0!important}
#rmReader .rm-info{font-size:13px!important;line-height:1.5!important}
#rmReader .rm-ai-paragraph,#rmReader .rm-ai-list,#rmReader .rm-ai-quote,#rmReader .rm-original-text{font-size:16px!important;line-height:1.65!important}
#rmReader .rm-ai-paragraph{margin:8px 0 12px!important}
#rmReader .rm-ai-list{margin:8px 0 12px!important}
#rmReader .rm-ai-heading{margin:17px 0 8px!important}
#rmReader .rm-section{margin:10px 0!important}
@media(max-width:600px){#rmReaderTitle{font-size:18px!important}#rmReader .rm-section{padding:12px!important}}
`;
/* AI 表格文字縮放保護：不覆寫既有桌機 14px／手機 13.5px 字級及排版。 */
style.textContent += `
#rmReader .rm-ai-table table,
#rmReader .rm-ai-table th,
#rmReader .rm-ai-table td {
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}
/* 只統一 AI 表格儲存格文字；不改 table、欄寬、間距、換行或滑動。 */
#rmReader .rm-ai-table th,
#rmReader .rm-ai-table td {
  font-size: 14px !important;
}
@media (max-width:600px) {
  #rmReader .rm-ai-table th,
  #rmReader .rm-ai-table td {
    font-size: 13.5px !important;
  }
}
`;
/* 全資料庫共用手機版視覺規格：僅調整展示，不更動資料、搜尋或 AI。 */
style.textContent += `
#researchMergedPanel{font-size:14px;line-height:1.65}
#researchMergedPanel .rm-toolbar{gap:12px;margin-bottom:16px}
#researchMergedPanel .rm-cats{gap:8px;padding:2px 0 4px}
#researchMergedPanel .rm-chip{font-family:inherit!important;font-size:14px!important;font-weight:650!important;min-height:40px;line-height:1.35;padding:9px 14px}
#researchMergedPanel .rm-date-tools{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
#researchMergedPanel .rm-date-tools button{font-family:inherit!important;font-size:14px!important;font-weight:600!important;line-height:1.35!important;min-height:42px;padding:9px 13px!important;white-space:nowrap;border-radius:12px!important}
#researchMergedPanel .rm-search{display:flex;align-items:stretch;gap:8px;min-width:0}
#researchMergedPanel #rmQuery{min-width:0;min-height:44px;font-size:14px!important;font-weight:400!important;line-height:1.4!important;border-radius:12px!important;padding:10px 12px!important}
#researchMergedPanel #rmClear{min-height:44px;flex:0 0 auto;font-size:14px!important;font-weight:600!important;line-height:1.4!important;border-radius:12px!important;padding:9px 13px!important}
#researchMergedPanel .rm-meta{font-size:12px!important;line-height:1.5!important;margin:0;color:#718096}
#researchMergedPanel .rm-date-group>.report-date-head{min-height:58px;padding:12px 14px}
#researchMergedPanel .rm-date-group>.report-date-head b{font-size:16px!important;font-weight:700!important}
#researchMergedPanel .rm-date-group>.report-date-head small{font-size:12px!important;font-weight:500!important}
#researchMergedPanel .rm-card{padding:14px!important;margin:10px 0;border-radius:15px}
#researchMergedPanel .rm-title,#researchMergedPanel .rm-card .report-title{font-size:16px!important;line-height:1.5!important;font-weight:700!important;letter-spacing:0!important}
#researchMergedPanel .rm-card .report-broker{font-size:12px!important;line-height:1.5!important;font-weight:600!important;color:#778293}
#researchMergedPanel .rm-sub,#researchMergedPanel .report-meta{font-size:12px!important;line-height:1.55!important}
#researchMergedPanel .rm-story,#researchMergedPanel .rm-card .report-summary,#researchMergedPanel .rm-card .report-details-body{font-size:15px!important;line-height:1.72!important}
#researchMergedPanel .rm-story{white-space:pre-line!important;margin:9px 0 11px!important}
#researchMergedPanel .rm-card .report-summary{padding-left:22px;margin:10px 0}
#researchMergedPanel .rm-card .report-summary li{margin-bottom:8px!important}
#researchMergedPanel .report-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:8px 0 10px}
#researchMergedPanel .report-chip{font-size:12px!important;line-height:1.45!important;font-weight:600!important;max-width:100%;overflow-wrap:anywhere;white-space:normal}
#researchMergedPanel .report-target{max-width:100%;overflow-wrap:anywhere;white-space:normal}
/* 原券商報告仍使用既有完整卡片，縮小過大的標題與券商名稱。 */
#reportList .report-v2-card .report-broker,#reportCardsV3 .report-broker{font-size:12px!important;font-weight:600!important;line-height:1.5!important}
#reportList .report-v2-card .report-title,#reportCardsV3 .report-title{font-size:16px!important;font-weight:700!important;line-height:1.5!important;letter-spacing:0!important}
#reportList .report-v2-card .report-target,#reportCardsV3 .report-target{max-width:100%;white-space:normal!important;overflow-wrap:anywhere;line-height:1.45!important}
#reportList .report-v2-card .report-chip,#reportCardsV3 .report-chip{font-size:12px!important;line-height:1.45!important}
@media(max-width:600px){
 #researchMergedPanel .rm-card{padding:13px!important}
 #researchMergedPanel .rm-date-group>.report-date-body{padding:0 10px 10px}
 #researchMergedPanel .rm-date-tools button{font-size:14px!important}
}
`;
style.textContent += `
#rmReader .brv-root{display:grid;gap:14px;margin:16px 0}
#rmReader .brv-card{min-width:0;padding:14px;border:1px solid #dce3eb;border-radius:12px;background:#fff;color:#243246}
#rmReader .brv-card h4{font-size:15px;margin:0 0 12px}
#rmReader .brv-scroll{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
#rmReader .brv-table{border-collapse:collapse;min-width:380px;width:100%;font-size:13px}
#rmReader .brv-table th,#rmReader .brv-table td{padding:9px;border-bottom:1px solid #e3e8f0;white-space:nowrap}
#rmReader .brv-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:10px}
#rmReader .brv-kpi{display:grid;gap:5px;padding:12px;border-radius:9px;background:#f2f5f8}
#rmReader .brv-legend{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;font-size:12px}
#rmReader .brv-legend span{display:inline-flex;gap:5px;align-items:center}
#rmReader .brv-legend i{display:inline-block;width:10px;height:10px;border-radius:3px}
#rmReader .brv-timeline{list-style:none;border-left:2px solid #dce3eb;padding-left:24px}
#rmReader .brv-timeline li{position:relative;margin-bottom:16px;display:grid;gap:4px}
#rmReader .brv-timeline li:before{content:'';position:absolute;left:-31px;top:7px;width:11px;height:11px;border-radius:50%;background:#2563eb}
#rmReader .brv-flow{display:flex;flex-wrap:wrap;gap:10px}
#rmReader .brv-flow-node{flex:1 1 150px;border:1px solid #dce3eb;padding:12px;border-radius:10px;display:grid;gap:4px}
#rmReader .brv-flow-links{padding-left:20px;font-size:13px}
#rmReader .brv-note{font-size:12px;color:#64748b}
`;
document.head.appendChild(style);
const cards = panel.querySelector('#rmCards'), meta = panel.querySelector('#rmMeta');
const more = panel.querySelector('#rmMore'), input = panel.querySelector('#rmQuery');
const broker = () => category === '券商報告';
const marketOf = r => String(r.market || 'TW').toUpperCase();
const originalType = r => clean(r.original_type).toLowerCase();
function reportCategory(r) {
  if (marketOf(r) === 'US') return '美股';
  if (r.source_kind === 'broker') {
    const type=clean(r._liveBroker?.report_type || r.report_type).toLowerCase();
    return ['sector','theme'].includes(type) || (!type && clean(r.category)==='產業研究')
      ? '產業報告' : '券商報告';
  }
  const c=clean(r.category);
  if (c==='早報') return '早報';
  if (c==='產業研究') return '產業報告';
  if (c==='法說／訪談') return '法說／訪談';
  if (c==='市場情報') return '市場情報';
  // Backward-compatible fallback for older metadata.
  return ['法說會','call memo'].includes(originalType(r))?'法說／訪談':'市場情報';
}
function inCategory(r) {
  const c=reportCategory(r);
  if (category==='全部') return c!=='美股';
  return c===category;
}

function heading(r) {
  const codes=stockCodes(r.ticker);
  const multi=r.is_multi_company || codes.length>1;
  let title=clean(r.title)||clean(r.company);
  title=title.replace(/[（(]多檔聚合[）)]\s*/g,'').trim();
  if(multi){
    title=title.replace(/(?:\s*[;；、]?\s*\d{4,6}\.(?:TWO|TW))+\s*$/i,'').trim();
    const ticker=clean(r.ticker);if(ticker && title.endsWith(ticker))title=title.slice(0,-ticker.length).trim();
    return title || '多公司研究報告';
  }
  if(codes.length===1){
    const name=companyNames.get(codes[0])||clean(r.company);
    if(!title || /^(?:\d{4}|[1-4]Q\d{2})(?:\s+\d{4,6})?$/.test(title))title=name;
    if(title===name)return `${name} ${codes[0]}`;
  }
  return title||'研究資料';
}
function readableText(value,r) {
  let text=clean(value);
  // Parse list serialization, rather than stripping quotation marks from prose.
  if(text.startsWith('[')){try{const v=JSON.parse(text);if(Array.isArray(v)&&v.every(x=>typeof x==='string'))text=v.join('\n\n')}catch(_){}}
  text=text.replace(/\r\n?/g,'\n');
  const codes=stockCodes(r.ticker);
  const names=codes.map(c=>companyNames.get(c)).filter(Boolean);
  const escapeRE=x=>x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const starts=names.map(escapeRE).join('|');
  if(starts){
    text=text.replace(new RegExp('([;；]|[\\n])\\s*(?=(?:📌\\s*)?(?:'+starts+'))','g'),'\n\n');
    text=text.replace(new RegExp('([:：])\\s*(?=(?:'+starts+')[（(]\\d)','g'),'$1\n\n');
  }
  text=text.replace(/\s*📌\s*/g,'\n\n📌 ');
  text=text.split('\n').map(line=>{
    if(!/[\u3400-\u9fff]/.test(line))return line;
    return line.replace(/,/g,(c,i,t)=>/\d/.test(t[i-1]||'')&&/\d/.test(t[i+1]||'')?',':'，').replace(/;/g,'；').replace(/:/g,'：');
  }).join('\n');
  return text.replace(/\n{3,}/g,'\n\n').trim();
}
// Reflow PDF physical line breaks only; keep headings, lists and real paragraphs.
function readableProse(value,r) {
  const raw=String(value||'').replace(/\r\n?/g,'\n');
  const lines=raw.split('\n');
  const wrapped=lines.filter(x=>x.trim().length>=28).length>=3;
  if(!wrapped)return readableText(raw,r);
  const out=[];
  const heading=x=>/^(?:[\-•●📌📍]|\d+[.、]\s|Q&A|重點摘要|營運成果|營運展望|投資建議|評論及分析|重要訊息|【|\|)/.test(x)
    || /^[\u3400-\u9fffA-Za-z\-]+\s*[（(]\d{4}/.test(x)
    || /^(?:\d{4}\s*[\u3400-\u9fff]|[1-4]Q\d{2}(?:\s+[1-4]Q\d{2}){2})/.test(x);
  for(const line of lines){
    const t=line.trim(),prev=out[out.length-1]||'';
    if(t&&prev&&prev.length>=28&&!/[。！？：:]$/.test(prev)&&!heading(t)&&!heading(prev)
      && /[\u3400-\u9fff]/.test(prev)&& !/\t|\s{3,}/.test(line)){
      const sep=/[A-Za-z0-9]$/.test(prev)&&/^[A-Za-z0-9]/.test(t)?' ':'';
      out[out.length-1]=prev+sep+t;
    }else out.push(t);
  }
  return readableText(out.join('\n'),r);
}
function companyList(r) {
  const codes=stockCodes(r.ticker);
  if(codes.length<2)return '';
  return `<details class="rm-company-list"><summary>涵蓋 ${codes.length} 家公司</summary>${codes.map(c=>`<div>${highlight((companyNames.get(c)||'')+' '+c)}</div>`).join('')}</details>`;
}
function summary(r) {return clean(r.story || r.summary || r.title);}
function classify(r) { return reportCategory(r); }

function highlight(t) {
  const text=String(t ?? '');
  if (!query.trim()) return esc(text);
  const terms=new Set(searchTerms());
  for(const term of [...terms]) {
    for(const code of companyAliases.get(term)||[]) {
      terms.add(code);
      if(companyNames.get(code))terms.add(companyNames.get(code));
    }
  }
  const patterns=[...terms].filter(Boolean).sort((a,b)=>b.length-a.length).map(term=>{
    const safe=term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    return /^\d+$/.test(term)?`(?<![\\d.,])${safe}(?!\\d|[.,]\\d)`:safe;
  });
  if(!patterns.length)return esc(text);
  const regex=new RegExp(patterns.join('|'),'gi');
  let result='',offset=0;
  for(const match of text.matchAll(regex)) {
    result+=esc(text.slice(offset,match.index))+`<mark class="rm-hit">${esc(match[0])}</mark>`;
    offset=match.index+match[0].length;
  }
  return result+esc(text.slice(offset));
}
const normalizeSearch = x => clean(x).normalize('NFKC').toLowerCase().replace(/臺/g,'台').trim();
const companyAliases = new Map();
const companyNames = new Map();
function stockCodes(value) {
  return [...normalizeSearch(value).matchAll(/(?:^|[^a-z0-9])(\d{4,6})(?:\.(?:tw|two)|\s+tt)?(?=$|[^a-z0-9])/g)].map(m=>m[1]);
}
function registerCompany(code,name,aliases=[]) {
  if (!/^\d{4,6}$/.test(code)) return;
  if (name) companyNames.set(code,clean(name));
  for (const alias of [code,code+'.TW',code+'.TWO',name,...aliases]) {
    const key=normalizeSearch(alias);if (!key) continue;
    if (!companyAliases.has(key)) companyAliases.set(key,new Set());
    companyAliases.get(key).add(code);
  }
}
function buildCompanyAliases(registry) {
  companyAliases.clear();companyNames.clear();
  for (const [code,entry] of Object.entries(registry||{})) registerCompany(code,entry.name,entry.aliases||[]);
  for (const r of rows) {
    const codes=stockCodes(r.ticker);
    if (codes.length===1 && !r.is_multi_company && !/多檔|[、;]/.test(clean(r.company))) {
      registerCompany(codes[0],companyNames.get(codes[0])||r.company,[r.company]);
    }
  }
}
function reportCompanies(r) {
  const result=new Set(stockCodes(r.ticker));
  for (const part of clean(r.company).split(/[、;；]/)) {
    for (const code of companyAliases.get(normalizeSearch(part))||[]) result.add(code);
  }
  return result;
}
function searchTerms() {
  const q=normalizeSearch(query);
  return companyAliases.has(q) ? [q] : q.split(/\s+/).filter(Boolean);
}
const topicBodies = new Map(), searchBuckets = new Map();
let topicSearching=false, topicSearchError='';
function isCompanyTerm(term) {
  return companyAliases.has(term) || /^\d{4,6}(?:\.(?:tw|two))?$/.test(term);
}
function searchValue(value) {
  if(Array.isArray(value))return value.map(searchValue).join(' ');
  if(value && typeof value==='object')return Object.values(value).map(searchValue).join(' ');
  return typeof value==='string' || typeof value==='number' ? String(value) : '';
}
function reportSearchText(r) {
  const b=r._liveBroker||r;
  const fields=['company','name','ticker','stock_id','source','broker','source_name',
    'summary','story','full_text','full_text_2','full_text_3','revenue','eps','inventory',
    'utilization','guidance','trend','numbers','rating_target','title','report_title',
    'industry','sector','detail','key_points','forecast_changes','risks','beneficiaries',
    'ai_research','display'];
  return fields.map(k=>searchValue(b[k])).join(' ').replace(/\s+/g,' ');
}
function topicText(r) {
  return normalizeSearch(reportSearchText(r)+' '+(topicBodies.get(r.id)||''));
}
function matching(r) {
  if (!inCategory(r) || (selectedDay && r.date!==selectedDay)) return false;
  const subjects=reportCompanies(r);
  const metadata=topicText(r);
  return searchTerms().every(term=>{
    const codes=companyAliases.get(term);
    if(codes) return marketOf(r)==='TW' && [...codes].some(code=>subjects.has(code));
    if(/^\d{4,6}(?:\.(?:tw|two))?$/.test(term)) return subjects.has(term.split('.')[0]);
    return metadata.includes(term);
  });
}
function topicSnippet(r) {
  const terms=searchTerms().filter(t=>!isCompanyTerm(t));
  if(!terms.length)return '';
  const text=topicBodies.get(r.id)||reportSearchText(r);
  const normalized=normalizeSearch(text);
  return terms.filter(t=>!normalizeSearch(summary(r)).includes(t)).map(t=>{
    const at=normalized.indexOf(t);
    if(at<0)return '';
    const start=Math.max(0,at-70),end=Math.min(text.length,at+t.length+150);
    return (start?'…':'')+text.slice(start,end)+(end<text.length?'…':'');
  }).filter(Boolean).join('\n');
}
function matchedSummary(r) {
  const codes=new Set(searchTerms().flatMap(t=>[...(companyAliases.get(t)||[])]));
  if (!codes.size || !(r.is_multi_company || stockCodes(r.ticker).length>1)) return summary(r);
  const names=[...codes].flatMap(c=>[companyNames.get(c),c]).filter(Boolean);
  const chunks=summary(r).split(/\n+|[；;]/).filter(t=>names.some(n=>t.includes(n)));
  return chunks.length ? chunks.join('\n\n') : '本報告涵蓋 '+[...codes].map(c=>(companyNames.get(c)||'')+' '+c).join('、')+'，請開啟全文查看相關段落。';
}
function render() {
  panel.querySelectorAll('[data-category]').forEach(b => b.classList.toggle('active',b.dataset.category===category));
  const found = rows.filter(matching);
  const counts = Object.fromEntries(categories.slice(1).map(c => [c,found.filter(r => classify(r)===c).length]));
  meta.textContent = `${query ? '搜尋結果' : category}｜${found.length} 筆` + (query ? '｜'+Object.entries(counts).map(([k,v])=>`${k} ${v}`).join('・') : '');
  if(query && topicSearching)meta.textContent+='｜搜尋全文中…';
  if(query && topicSearchError)meta.textContent+='｜'+topicSearchError;
  cards.replaceChildren();
  const grouped = new Map();
  for (const m of found) {const day=m.date||'日期未明';if(!grouped.has(day))grouped.set(day,[]);grouped.get(day).push(m)}
  let n=0;
  for (const [day, group] of grouped) {
    if (n >= limit) break;
    const details=document.createElement('details');details.className='report-date-group rm-date-group';
    if (query || selectedDay || n===0) details.open=true;
    const head=document.createElement('summary');head.className='report-date-head';
    head.innerHTML=`<span><b>${esc(dateLabel(day))}</b> <small>${group.length} 份報告</small></span><span class="report-date-arrow">⌄</span>`;
    details.appendChild(head);
    const body=document.createElement('div');body.className='report-date-body';
    for (const m of group) {
      const card=document.createElement('article');card.className='rm-card report-v2-card';
      const story=readableText(matchedSummary(m),m);
      const snippet=topicSnippet(m);
      const hitHTML=snippet?`<div class="rm-story"><strong>關鍵字相關內文</strong><br>${highlight(snippet)}</div>`:'';
      if (m.source_kind === 'broker' && m._liveBroker) {
        card.classList.add('rm-broker-card');
        const b=m._liveBroker;
        const bullet=Array.isArray(b.summary)?b.summary:[];
        const target=b.validation_status==='needs_review'?'':(b.target_price_new==null?'':`目標價 ${esc(b.target_price_old!=null?b.target_price_old+' → ':'')}${esc(b.target_price_new)}`);
        card.innerHTML=`<div class="report-broker">${highlight(b.broker||'券商研究')}</div><div class="report-title">${highlight((b.name||b.title||'券商報告')+(b.ticker?' '+b.ticker:''))}</div><div class="report-meta">${b.rating?`<span class="report-chip">${highlight(b.rating)}</span>`:''}${target?`<span class="report-chip report-target">${target}</span>`:''}<span class="report-chip">報告日期 ${esc(m.date)}</span></div>${bullet.length?`<ul class="report-summary">${bullet.map(x=>`<li>${highlight(x)}</li>`).join('')}</ul>`:''}<details class="report-details"><summary>查看完整摘要</summary><div class="report-details-body">${b.detail?`<p>${highlight(b.detail)}</p>`:''}${['key_points','forecast_changes','risks'].map(k=>Array.isArray(b[k])&&b[k].length?`<ul>${b[k].map((x,i)=>`<li>${researchPoint(x,i)}</li>`).join('')}</ul>`:'').join('')}${b.source_url?`<a href="${esc(b.source_url)}" target="_blank" rel="noopener">查看原始報告</a>`:''}</div></details>`;
        if(hitHTML)card.insertAdjacentHTML('beforeend',hitHTML);
        body.appendChild(card);continue;
      }
      card.innerHTML=`<div class="rm-title">${highlight(heading(m))}</div><div class="rm-sub">${esc(m.date)} · ${highlight(m.source)} · <span class="rm-type">${esc(classify(m))}</span></div>${companyList(m)}<div class="rm-story">${highlight(story)}</div>${hitHTML}<button type="button" class="rm-open">閱讀全文 →</button>`;
      card.querySelector('button').addEventListener('click',()=>openReader(m));body.appendChild(card);
    }
    details.appendChild(body);cards.appendChild(details);n++;
  }
  more.hidden=grouped.size<=limit;
  if (!found.length) cards.innerHTML='<div class="rm-empty">沒有符合條件的報告</div>';
  updateDateLabel();
}
async function topicCandidates(term) {
  // ASCII bigrams use the existing sync-generated index. Other text is verified
  // directly so Unicode normalization cannot silently exclude a valid report.
  if(term.length<2 || /[^\x20-\x7e]/.test(term))return indexRows;
  try {
    const grams=[...new Set(Array.from({length:term.length-1},(_,i)=>term.slice(i,i+2)))];
    const lists=await Promise.all(grams.map(async gram=>{
      const bucket=(gram.charCodeAt(0)+2*gram.charCodeAt(1))%(manifest.search_buckets||64);
      if(!searchBuckets.has(bucket))searchBuckets.set(bucket,
        fetchJSON(`./data/research_search/${String(bucket).padStart(2,'0')}.json`)
          .catch(e=>{searchBuckets.delete(bucket);throw e}));
      return new Set((await searchBuckets.get(bucket))[gram]||[]);
    }));
    return indexRows.filter((r,i)=>lists.every(ids=>ids.has(i)));
  } catch(e) {
    // A missing index must not silently turn into zero results.
    return indexRows;
  }
}
async function fullTextSearch() {
  const seq=++searchSeq;
  searchHits=null;topicSearchError='';
  const terms=searchTerms().filter(t=>!isCompanyTerm(t));
  topicSearching=loaded && terms.length>0;
  render();
  if(!topicSearching)return;
  try {
    const candidates=(await Promise.all(terms.map(topicCandidates))).flat();
    if(seq!==searchSeq)return;
    const files=[...new Set(candidates.filter(r=>r.file && !topicBodies.has(r.id)).map(r=>r.file))];
    for(const file of files) {
      const records=await shard(file);
      if(seq!==searchSeq)return;
      for(const r of records)topicBodies.set(String(r.id),reportSearchText(r));
    }
  } catch(e) {
    if(seq===searchSeq)topicSearchError='部分全文讀取失敗，請重新搜尋';
    console.warn('全文搜尋失敗',e);
  } finally {
    if(seq===searchSeq){topicSearching=false;render();sync();}
  }
}
function updateDateLabel(){const el=panel.querySelector('#rmDateLabel');if(el)el.textContent=selectedDay||'全部日期'}
function drawCalendar(){
  const host=panel.querySelector('#rmCalendar');if(!host)return;
  const valid=rows.filter(inCategory);const dates=new Set(valid.map(r=>r.date));
  const first=valid.find(r=>/^\d{4}-\d{2}-\d{2}$/.test(r.date));
  if(!calendarMonth)calendarMonth=(first?.date||new Date().toISOString().slice(0,10)).slice(0,7);
  const [y,m]=calendarMonth.split('-').map(Number);const firstDay=new Date(y,m-1,1).getDay();const days=new Date(y,m,0).getDate();
  const cells=Array.from({length:firstDay},()=>'<span></span>');
  for(let d=1;d<=days;d++){const date=`${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`;cells.push(`<button type="button" data-rm-day="${date}" class="${selectedDay===date?'selected':''}">${d}${dates.has(date)?'<i></i>':''}</button>`)}
  host.innerHTML=`<div class="rm-cal-head"><button type="button" data-rm-month="-1">❮</button><strong>${y} 年 ${m} 月</strong><button type="button" data-rm-month="1">❯</button></div><div class="rm-cal-grid">${['日','一','二','三','四','五','六'].map(x=>`<b>${x}</b>`).join('')}${cells.join('')}</div><div class="rm-cal-foot"><button type="button" data-rm-action="today">今天</button><button type="button" data-rm-action="clear">清除</button><button type="button" data-rm-action="done">完成</button></div>`;
}
async function fetchJSON(url) {
  // Resolve paths against the site root rather than the current browser URL.
  const target = new URL(url, document.baseURI).href;
  let response;
  try { response = await fetch(target, {cache:'no-cache'}); }
  catch (e) { throw Error(`網路讀取失敗 (${url}): ${e.message}`); }
  if (!response.ok) throw Error(`HTTP ${response.status} (${url})`);
  try { return await response.json(); }
  catch (e) { throw Error(`JSON 解析失敗 (${url}): ${e.message}`); }
}
async function shard(file) {
  if(!file) throw Error('缺少原文資料檔案');
  const filename=String(file).trim();
  // Manifest filenames are flat filenames, not arbitrary paths.
  if (!filename || filename==='.' || filename==='..' || /[/\\\x00-\x1f]/.test(filename)) throw Error('原文資料檔名格式錯誤');
  if(!cache.has(filename)) {
    const task=fetchJSON(`./data/research_shards/${encodeURIComponent(filename)}`)
      .then(x=>{if(!Array.isArray(x.items))throw Error('原文分片資料格式錯誤');return x.items})
      .catch(e=>{cache.delete(filename);throw e});
    cache.set(filename,task);
    if(cache.size>5)cache.delete(cache.keys().next().value);
  }
  return cache.get(filename);
}
function section(title,body) {return `<section class="rm-section"><h3>${esc(title)}</h3>${body}</section>`}
function rawTexts(r) {
  const d=r.display||{};
  const list=[d.full_text ?? r.full_text,d.full_text_2 ?? r.full_text_2,d.full_text_3 ?? r.full_text_3].map(clean).filter(Boolean);
  return [...new Set(list)];
}
let aiDirectPromise;
function loadAiDirect(){
  return aiDirectPromise ||= fetchJSON('./data/research_ai_render.json').then(x=>x.items||{}).catch(()=>({}));
}
// Only short, explicitly authored bullet points receive emphasis. Keep the
// complete sentence (including dates, forecast qualifiers and risks).
function researchPoint(text, index=0) {
  const value=String(text||'');
  const html=highlight(value);
  return index<2 && value.length<=80 && !html.includes('<mark')
    ? `<span class="research-emphasis">${html}</span>` : html;
}
function renderAiDirect(entry){
  const ai=entry?.content;
  if(!ai || typeof ai!=='object')return '';
  const blocks=Array.isArray(ai.blocks)?ai.blocks:null;
  if(blocks){
    const html=blocks.map(b=>{
      if(!b||typeof b!=='object')return '';
      if(b.type==='heading')return `<h3 class="rm-ai-heading">${highlight(b.text||'')}</h3>`;
      if(b.type==='paragraph')return `<p class="rm-ai-paragraph">${highlight(b.text||'')}</p>`;
      if(b.type==='quote')return `<blockquote class="rm-ai-quote">${highlight(b.text||'')}</blockquote>`;
      if(b.type==='bullets')return `<ul class="rm-ai-list">${(Array.isArray(b.items)?b.items:[]).map((t,i)=>`<li>${researchPoint(t,i)}</li>`).join('')}</ul>`;
      if(b.type==='chart'){
        const advanced=['pie','kpi','stacked_bar','waterfall','dual_axis','timeline','flow','scatter','heatmap'];
        if(advanced.includes(b.chart_type)){
          const id='rm-chart-'+(window.__rmChartSerial=(window.__rmChartSerial||0)+1);
          const payload={...b,type:b.chart_type,items:b.kpi_items,headers:b.columns,rows:b.chart_type==='heatmap'?b.heatmap_rows:b.rows};
          (window.__rmPendingCharts ||= new Map()).set(id,payload);
          return `<div class="rm-shared-chart" data-rm-chart-id="${id}"></div>`;
        }
        const labels=Array.isArray(b.labels)?b.labels:[], values=Array.isArray(b.values)?b.values:[];
        if(!labels.length||labels.length!==values.length||values.some(v=>typeof v!=='number'||!Number.isFinite(v)))return '';
        const type=['bar','line','donut'].includes(b.chart_type)?b.chart_type:'bar';
        const unit=String(b.unit||'');
        const colors=['#3969b2','#3e9a8e','#b38b46','#8362ae','#c56c74','#688ca5'];
        const max=Math.max(1,...values.map(v=>Math.abs(v)));
        let graphic='';
        if(type==='donut'&&values.every(v=>v>=0)&&values.reduce((a,v)=>a+v,0)>0){
          const total=values.reduce((a,v)=>a+v,0);let angle=0;
          const stops=values.map((v,i)=>{const start=angle;angle+=v/total*100;return `${colors[i%colors.length]} ${start}% ${angle}%`});
          graphic=`<div class="rm-ai-donut" style="background:conic-gradient(${stops.join(',')})" aria-hidden="true"></div>`;
        }else if(type==='line'&&values.length>=2){
          const lo=Math.min(0,...values),hi=Math.max(...values),span=hi-lo||1;
          const points=values.map((v,i)=>`${10+i*280/(values.length-1)},${120-(v-lo)/span*100}`).join(' ');
          graphic=`<svg class="rm-ai-line" viewBox="0 0 300 140" role="img" aria-label="${esc(b.title||'趨勢圖')}"><polyline points="${points}" fill="none" stroke="#3969b2" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
        }else{
          graphic=`<div class="rm-ai-bars">${labels.map((l,i)=>`<div class="rm-ai-barrow"><span>${esc(l)}</span><div class="rm-ai-track"><i style="width:${Math.max(2,Math.abs(values[i])/max*100)}%;background:${colors[i%colors.length]}"></i></div><strong>${esc(values[i])}${esc(unit)}</strong></div>`).join('')}</div>`;
        }
        return `<figure class="rm-ai-chart"><figcaption>${esc(b.title||'數據比較')}</figcaption>${graphic}<div class="rm-ai-legend">${labels.map((l,i)=>`<span><i style="background:${colors[i%colors.length]}"></i>${esc(l)}：${esc(values[i])}${esc(unit)}</span>`).join('')}</div>${b.note?`<small>${esc(b.note)}</small>`:''}</figure>`;
      }
      if(b.type==='table'){
        const cols=Array.isArray(b.columns)?b.columns:[];
        const rows=Array.isArray(b.rows)?b.rows:[];
        return `<figure class="rm-ai-table" data-cols="${cols.length}">${b.text||b.title?`<figcaption class="rm-ai-table-title">${esc(b.text||b.title)}</figcaption>`:''}<div class="rm-ai-table-hint">表格可左右滑動查看完整欄位 ↔</div><div class="rm-table-scroll" role="region" aria-label="${esc(b.text||b.title||'研究數據表格')}" tabindex="0"><table><thead><tr>${cols.map(c=>`<th scope="col">${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${(Array.isArray(row)?row:[]).map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${b.note?`<small class="rm-ai-table-note">${esc(b.note)}</small>`:''}</figure>`;
      }
      return '';
    }).join('');
    return html?section('AI 完整研究整理',html):'';
  }
  // Old AI schema has no authored full article. Never synthesize tables or
  // invent an article from old extracted facts; wait for the user's paid rerun.
  const overview=Array.isArray(ai.summary)?ai.summary:(ai.summary?[ai.summary]:[]);
  return section('AI 研究摘要（等待新版全文）',
    overview.map(x=>`<p class="rm-ai-paragraph">${esc(x)}</p>`).join('')+
    '<p class="rm-ai-paragraph">此篇尚未產生新版 AI 全文與自主設計圖表；請執行指定重跑。</p>');
}
function detail(r,m,direct={}) {
  const info=`<div class="rm-info">${esc(r.date||m.date)} · ${esc(r.source||m.source)} · ${esc(r.original_type||m.original_type||'')}</div>`;
  const raw=rawTexts(r);
  const modelHtml=renderAiDirect(direct[r.id]);
  const missing=section('AI 研究整理','<p class="rm-ai-paragraph">這篇尚無 AI 完整研究文章；網站不會使用 Python 或固定表格代替模型撰寫。</p>');
  const original=raw.length?`<details class="rm-source-details"><summary>查看 Excel 研究原文</summary>${raw.map((t,i)=>section(raw.length>1?`原文 ${i+1}`:'研究原文',`<div class="rm-original-text">${highlight(readableProse(t,r))}</div>`)).join('')}</details>`:'';
  return info+(modelHtml||missing)+original;
}
async function openReader(m) {
  reader.dataset.reportId=String(m.id);
  const token=++readerSerial;scrollY=window.scrollY;reader.hidden=false;document.body.classList.add('rm-reader-open');reader.scrollTop=0;
  reader.querySelector('#rmReaderTitle').textContent=heading(m)||'研究報告';
  const body=reader.querySelector('#rmReaderContent');body.textContent='載入研究內容中…';
  // AI results and original Excel text are independent. A broken shard must not
  // hide an already-completed AI article or charge for another API request.
  const [aiResult, shardResult] = await Promise.allSettled([loadAiDirect(), shard(m.file)]);
  if(token!==readerSerial||reader.hidden)return;
  const direct=aiResult.status==='fulfilled'?aiResult.value:{};
  const items=shardResult.status==='fulfilled'?shardResult.value:[];
  const r=items.find(x=>String(x.id)===String(m.id));
  if(aiResult.status==='rejected')console.warn('[research reader] AI render unavailable',aiResult.reason);
  if(shardResult.status==='rejected')console.warn('[research reader] source shard unavailable',m.id,m.file,shardResult.reason);
  try {
    if(r){
      body.innerHTML=detail(r,m,direct);
    }else{
      const aiHtml=renderAiDirect(direct[String(m.id)]);
      const info=`<div class="rm-info">${esc(m.date)} · ${esc(m.source)} · ${esc(m.original_type||'')}</div>`;
      const fallback=section('原始研究資料暫時無法載入',
        `<p class="rm-ai-paragraph">${shardResult.status==='rejected'?'原始資料讀取失敗':'原始資料中找不到這篇報告'}；不影響已完成的 AI 內容。</p>`+
        (shardResult.status==='rejected'?`<p class="rm-ai-paragraph">${esc(shardResult.reason?.message||'')}</p>`:''));
      body.innerHTML=info+(aiHtml||section('AI 研究整理','<p class="rm-ai-paragraph">目前沒有可顯示的 AI 完整研究文章。</p>'))+fallback;
    }
  }catch(e){
    console.error('[research reader] rendering failed',m.id,e);
    const aiHtml=renderAiDirect(direct[String(m.id)]);
    body.innerHTML=(aiHtml||section('研究內容顯示失敗',`<p class="rm-ai-paragraph">${esc(e.message)}</p>`));
  }
  // Render only newly added chart types after the reader DOM has been mounted.
  body.querySelectorAll('[data-rm-chart-id]').forEach(el=>{
    const id=el.dataset.rmChartId, item=window.__rmPendingCharts?.get(id);
    if(item && window.BrokerReportCharts?.render) window.BrokerReportCharts.render(el,[item]);
    window.__rmPendingCharts?.delete(id);
  });
}

function closeReader(){++readerSerial;reader.hidden=true;document.body.classList.remove('rm-reader-open');window.scrollTo(0,scrollY)}
reader.querySelector('#rmClose').addEventListener('click',closeReader);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!reader.hidden)closeReader()});
function brokerDay(raw) {
  const text=clean(raw).normalize('NFKC');
  const m=text.match(/^(\d{4})(?:[-/](\d{1,2})[-/](\d{1,2})|(\d{2})(\d{2}))(?:$|[T\s])/);
  if(m){
    const y=+m[1],month=+(m[2]||m[4]),day=+(m[3]||m[5]);
    const d=new Date(Date.UTC(y,month-1,day));
    if(d.getUTCFullYear()===y && d.getUTCMonth()===month-1 && d.getUTCDate()===day)
      return `${y}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
  }
  const month=text.match(/^(\d{4})[-/](\d{1,2})$/);
  if(month && +month[2]>=1 && +month[2]<=12) return `${month[1]}-${month[2].padStart(2,'0')}`;
  return '日期未確認';
}
function dateRank(value) {
  const d=brokerDay(value);
  return /^\d{4}-\d{2}(?:-\d{2})?$/.test(d) ? Number(d.replaceAll('-','').padEnd(8,'0')) : 0;
}
function compareReportDate(a,b) {
  return dateRank(b.date)-dateRank(a.date) || String(a.id||'').localeCompare(String(b.id||''));
}
function dateLabel(day) {
  return day.replaceAll('-','/')+(/^\d{4}-\d{2}$/.test(day)?'（日期未詳）':'');
}
async function init(){
  if(loaded||loading)return;loading=true;
  try{
    const [mf,idx,live,registry]=await Promise.all([
      fetchJSON('./data/research_manifest.json'),
      fetchJSON('./data/research_meta.json'),
      fetchJSON('./data/reports.json').catch(e=>{console.warn('券商即時資料載入失敗',e);return null}),
      fetchJSON('./data/report_company_registry.json').catch(()=>({}))
    ]);
    if(!Array.isArray(idx))throw Error('研究索引格式錯誤');
    manifest=mf;indexRows=idx;
    const brokerItems=Array.isArray(live?.items)?live.items:[];
    // 以券商報告實際使用的 reports.json 為唯一券商清單，避免「全部」漏件。
    // 保留原索引列的順序，以免全文搜尋索引的列號失效。
    if(live && Array.isArray(live.items)) {
      rows=idx.filter(r=>r.source_kind!=='broker');
      rows.push(...brokerItems.map((b,i)=>({
        id:'live-broker-'+String(b.id||i), source_kind:'broker',market:'TW',report_type:b.report_type,
        date:brokerDay(b.date),company:b.name||'',ticker:b.ticker||'',
        title:b.title||b.name||'券商報告',source:b.broker||'',broker:b.broker||'',
        story:Array.isArray(b.summary)?b.summary.join(' '):String(b.summary||''),
        detail:b.detail||'',rating:b.rating||'',key_points:b.key_points||[],
        _liveBroker:b
      })));
    } else {rows=idx;}
    rows=rows.map(r=>({...r,date:brokerDay(r.date)}));
    rows.sort(compareReportDate);
    buildCompanyAliases(registry);
    loaded=true;render();drawCalendar();if(query)fullTextSearch();
  }catch(e){meta.textContent='研究索引載入失敗：'+e.message}
  finally{loading=false}
}
function sync(){const rating=document.getElementById('twRatingsPanel');const active=root.classList.contains('active');const ratingOn=Boolean(rating&&!rating.hidden);const brokerMode=active&&!ratingOn&&broker()&&!query.trim();panel.hidden=!active||ratingOn;legacy.hidden=active&&!ratingOn?!brokerMode:Boolean(ratingOn);cards.hidden=brokerMode;panel.querySelector('.rm-search').hidden=brokerMode;panel.querySelector('.rm-date-tools').hidden=brokerMode;panel.querySelector('#rmCalendar').hidden=brokerMode || panel.querySelector('#rmCalendar').hidden;meta.hidden=brokerMode;more.hidden=brokerMode || cards.querySelectorAll('.rm-date-group').length < limit;if(active&&!ratingOn)init()}
const observer=new MutationObserver(sync);observer.observe(root,{attributes:true,attributeFilter:['class']});const rating=document.getElementById('twRatingsPanel');if(rating)observer.observe(rating,{attributes:true,attributeFilter:['hidden']});
panel.querySelectorAll('[data-category]').forEach(b=>b.addEventListener('click',()=>{category=(category===b.dataset.category && category!=='全部')?'全部':b.dataset.category;selectedDay='';limit=30;render();drawCalendar();sync();panel.querySelector(`[data-category="${category}"]`)?.scrollIntoView({behavior:'smooth',block:'nearest',inline:'nearest'});}));
input.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{query=clean(input.value);limit=30;fullTextSearch();sync()},250)});
panel.querySelector('#rmClear').addEventListener('click',()=>{input.value='';query='';searchHits=null;searchSeq++;clearTimeout(searchTimer);limit=30;render();sync()});
more.addEventListener('click',()=>{limit+=30;render()});
panel.querySelector('#rmDateToggle').addEventListener('click',()=>{const el=panel.querySelector('#rmCalendar');el.hidden=!el.hidden;if(!el.hidden)drawCalendar()});
panel.querySelector('#rmLatest').addEventListener('click',()=>{selectedDay='';query='';input.value='';searchHits=null;searchSeq++;clearTimeout(searchTimer);limit=30;calendarMonth='';panel.querySelector('#rmCalendar').hidden=true;render();drawCalendar();sync();const target=broker()?document.querySelector('#reportCardsV3 .report-date-group'):cards.querySelector('.rm-date-group');if(target){target.open=true;target.scrollIntoView({behavior:'smooth',block:'start'});}else{panel.querySelector('.rm-date-tools').scrollIntoView({behavior:'smooth',block:'start'});}});
panel.querySelector('#rmCalendar').addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.rmMonth){const [y,m]=calendarMonth.split('-').map(Number);const d=new Date(y,m-1+Number(b.dataset.rmMonth),1);calendarMonth=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;drawCalendar()}
 if(b.dataset.rmDay){selectedDay=b.dataset.rmDay;query='';input.value='';searchHits=null;searchSeq++;render();drawCalendar();sync()}
 if(b.dataset.rmAction==='today'){query='';input.value='';searchHits=null;searchSeq++;const d=new Date();calendarMonth=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;selectedDay=`${calendarMonth}-${String(d.getDate()).padStart(2,'0')}`;render();drawCalendar()}
 if(b.dataset.rmAction==='clear'){selectedDay='';render();drawCalendar()}
 if(b.dataset.rmAction==='done')panel.querySelector('#rmCalendar').hidden=true;
});
sync();
})();
