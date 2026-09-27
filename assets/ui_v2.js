/* 月營收：歷史新高篩選按鈕 */
(() => {
  let highOnly = false;

  function applyRevenueFilter() {
    const tabs = document.querySelector("#revenueSectorTabs");
    const sections = document.querySelector("#revenueSections");

    if (!tabs || !sections) return;

    let button = document.querySelector("#revenueHighButton");

    if (!button) {
      button = document.createElement("button");
      button.id = "revenueHighButton";
      button.type = "button";
      button.className = "week-pill";
      button.style.cssText =
        "display:block;margin:16px 0;padding:12px 18px;" +
        "border:2px solid #c99832;border-radius:24px;" +
        "font-weight:700;cursor:pointer;";

      tabs.before(button);

      button.onclick = () => {
        highOnly = !highOnly;
        applyRevenueFilter();
      };
    }

    button.textContent = highOnly
      ? "★ 歷史新高｜再次點擊顯示全部"
      : "★ 歷史新高";

    button.setAttribute("aria-pressed", String(highOnly));
    button.style.background = highOnly ? "#805800" : "#fff0c2";
    button.style.color = highOnly ? "#ffffff" : "#624300";

    sections.querySelectorAll(".sector-revenue").forEach(section => {
      let visibleCount = 0;

      section.querySelectorAll(".revenue-card").forEach(card => {
        const show = !highOnly || card.classList.contains("record-high");
        card.hidden = !show;
        card.style.display = show ? "" : "none";
        if (show) visibleCount++;
      });

      section.hidden = visibleCount === 0;
      section.style.display = visibleCount ? "" : "none";
    });

    let note = document.querySelector("#revenueHighEmpty");

    if (!note) {
      note = document.createElement("p");
      note.id = "revenueHighEmpty";
      note.className = "status";
      sections.after(note);
    }

    const hasHigh = sections.querySelector(".revenue-card.record-high");
    note.textContent = highOnly && !hasHigh
      ? "目前選取族群沒有已標示的新高個股；歷史資料不足時仍需核對"
      : "";
  }

  const originalMonthlyRevenue = monthlyRevenue;

  monthlyRevenue = async function (...args) {
    try {
      return await originalMonthlyRevenue.apply(this, args);
    } finally {
      applyRevenueFilter();
    }
  };

  applyRevenueFilter();
  monthlyRevenue();
})();
