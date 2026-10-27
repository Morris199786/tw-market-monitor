/* iOS Safari AI research table autosizing fix.
 * Scoped to AI research tables only; does not alter widths, scrolling, layout, or content.
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
  document.head.appendChild(style);
})();
