/* -----------------------------
   啟動
----------------------------- */

async function init() {
  setupTheme();
  setupToTop();

  await loadShortNames();

  await Promise.all([
    home(),
    flows(),
    volume(),
    turnover(),
    holders(),
    ai(),
    heat(),
    reports()
  ]);
}

init();
