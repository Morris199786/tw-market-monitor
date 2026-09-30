/* =========================================================
   台股評等 / 目標價調整
   ========================================================= */

(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];

  function esc(v) {
    return String(v ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function num(v) {
    if (v === null || v === undefined || v === "") {
      return "—";
    }

    const n = Number(v);

    if (!Number.isFinite(n)) {
      return esc(v);
    }

    return n.toLocaleString(
      "zh-TW",
      {
        maximumFractionDigits: 2
      }
    );
  }

  function actionText(action) {
    return action === "downgrade"
      ? "下調"
      : "上調";
  }

  function actionClass(action) {
    return action === "downgrade"
      ? "is-down"
      : "is-up";
  }

  function kindText(kind) {
    return kind === "rating"
      ? "評等調整"
      : "目標價調整";
  }

  function rowHtml(x) {
    const oldTp = num(x.target_price_old);
    const newTp = num(x.target_price_new);

    return `
      <div class="tw-rating-card ${actionClass(x.action)}">
        <div class="tw-rating-top">
          <div>
            <div class="tw-rating-broker">
              ${esc(x.broker || "券商")}
            </div>

            <div class="tw-rating-stock">
              <b>${esc(x.name || "")}</b>
              <span>${esc(x.ticker || "")}</span>
            </div>
          </div>

          <div class="tw-rating-action ${actionClass(x.action)}">
            ${actionText(x.action)}
          </div>
        </div>

        <div class="tw-rating-kind">
          ${kindText(x.kind)}
          ${
            x.rating
              ? `｜${esc(x.rating)}`
              : ""
          }
        </div>

        <div class="tw-rating-target">
          <span>目標價</span>
          <b>${oldTp}</b>
          <i>→</i>
          <strong>${newTp}</strong>
        </div>
      </div>
    `;
  }

  async function loadRatings() {
    const status = $("#twRatingsStatus");
    const box = $("#twRatingsList");

    if (!box) {
      return;
    }

    let data = {};

    try {
      const r = await fetch(
        "./data/tw_ratings.json?v=" + Date.now(),
        {
          cache: "no-store"
        }
      );

      if (!r.ok) {
        throw new Error(
          "HTTP " + r.status
        );
      }

      data = await r.json();
    } catch (e) {
      console.error(
        "tw ratings load failed",
        e
      );

      if (status) {
        status.textContent =
          "尚未建立台股評等資料";
      }

      box.innerHTML = `
        <div class="report-v2-empty">
          尚無台股評等資料
        </div>
      `;

      return;
    }

    const items =
      Array.isArray(data.items)
        ? data.items
        : [];

    if (status) {
      status.textContent =
        data.date
          ? `資料日期 ${data.date} · ${items.length} 筆上下調`
          : "尚無資料";
    }

    if (!items.length) {
      box.innerHTML = `
        <div class="report-v2-empty">
          當日沒有目標價／評等上下調
        </div>
      `;
      return;
    }

    const up = items.filter(
      x => x.action === "upgrade"
    );

    const down = items.filter(
      x => x.action === "downgrade"
    );

    box.innerHTML = `
      ${
        up.length
          ? `
            <section class="tw-rating-group">
              <div class="tw-rating-head">
                <b>上調</b>
                <span>${up.length} 筆</span>
              </div>

              <div class="tw-rating-grid">
                ${up.map(rowHtml).join("")}
              </div>
            </section>
          `
          : ""
      }

      ${
        down.length
          ? `
            <section class="tw-rating-group">
              <div class="tw-rating-head">
                <b>下調</b>
                <span>${down.length} 筆</span>
              </div>

              <div class="tw-rating-grid">
                ${down.map(rowHtml).join("")}
              </div>
            </section>
          `
          : ""
      }
    `;
  }

  function setMode(mode) {
    const reportList = $("#reportList");
    const ratingsPanel = $("#twRatingsPanel");

    $$("[data-report-mode]")
      .forEach(
        btn => {
          btn.classList.toggle(
            "active",
            btn.dataset.reportMode === mode
          );
        }
      );

    if (reportList) {
      reportList.hidden =
        mode !== "reports";
    }

    if (ratingsPanel) {
      ratingsPanel.hidden =
        mode !== "ratings";
    }

    if (mode === "ratings") {
      loadRatings();
    }
  }

  function boot() {
    $$("[data-report-mode]")
      .forEach(
        btn => {
          btn.addEventListener(
            "click",
            () => {
              setMode(
                btn.dataset.reportMode
              );
            }
          );
        }
      );

    setMode("reports");
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
