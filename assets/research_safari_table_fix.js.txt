/* iOS Safari AI research table autosizing fix.
 * Scoped to AI research tables: preserve Safari text sizing and compact column layout.
 * Does not alter report data, AI parsing, or other page tables.
 */
(function () {
  'use strict';
  const id = 'rmSafariTableTextFix';
  if (document.getElementById(id)) return;
  const style = document.createElement('style');
  style.id = id;
  style.textContent = `
#rmReader .rm-ai-table,
#rmReader .rm-ai-table table,
#rmReader .rm-ai-table th,
#rmReader .rm-ai-table td,
#rmReader .rm-ai-table th *,
#rmReader .rm-ai-table td * {
  -webkit-text-size-adjust: none !important;
  text-size-adjust: none !important;
}
`;
  // Override fixed 580/780/940px table widths and 135px cell minimums.
  // Content determines width; only genuinely wide tables need horizontal scrolling.
  style.textContent += `
#rmReader .rm-ai-table { margin:12px 0 16px; }
#rmReader .rm-ai-table .rm-table-scroll {
  width:fit-content !important;
  max-width:100% !important;
  overflow-x:auto;
  margin-right:0;
}
#rmReader .rm-ai-table table,
#rmReader .rm-ai-table[data-cols] table {
  width:max-content !important;
  min-width:0 !important;
  max-width:none !important;
  table-layout:auto !important;
  border-spacing:0;
}
#rmReader .rm-ai-table th,
#rmReader .rm-ai-table td {
  min-width:0 !important;
  width:auto !important;
  max-width:26ch;
  padding:8px 10px !important;
  line-height:1.45 !important;
  overflow-wrap:anywhere;
  word-break:normal;
  vertical-align:top;
}
#rmReader .rm-ai-table th { white-space:normal !important; }
#rmReader .rm-ai-table th:first-child,
#rmReader .rm-ai-table td:first-child { max-width:20ch; }
#rmReader .rm-ai-table th > p,
#rmReader .rm-ai-table td > p { margin:0 !important; }
@media(max-width:600px) {
  #rmReader .rm-ai-table table { font-size:13.5px; }
  #rmReader .rm-ai-table th,
  #rmReader .rm-ai-table td { padding:7px 9px !important; max-width:22ch; }
  #rmReader .rm-ai-table th:first-child,
  #rmReader .rm-ai-table td:first-child { max-width:16ch; }
}
`;
  document.head.appendChild(style);
})();
