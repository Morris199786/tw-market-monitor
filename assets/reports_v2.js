/* =========================================================
   券商報告 V2
   ========================================================= */

(function () {
  const $r = s =>
    document.querySelector(s);

  const actionMap = {
    upgrade: "上調",
    downgrade: "下調",
    initiate: "初評",
    maintain: "維持",
    sector: "產業報告",
    none: "研究報告"
  };

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function actionClass(a) {
    if (a === "upgrade") return "is-up";
    if (a === "downgrade") return "is-down";
    if (a === "initiate") return "is-init";
    return "is-neutral";
  }

  function targetText(r) {
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

  function chips(r) {
    const arr = [];

    if (r.rating) {
      arr.push(
        `<span class="report-chip">${esc(r.rating)}</span>`
      );
    }

    const tp = targetText(r);

    if (tp) {
      arr.push(
        `<span class="report-chip">目標價 ${esc(tp)}</span>`
      );
    }

    if (r.report_type === "sector") {
      arr.push(
        `<span class="report-chip">產業研究</span>`
      );
    }

    return arr.join("");
  }

  function beneficiaryHtml(r) {
    const rows = Array.isArray(r.beneficiaries)
      ? r.beneficiaries
      : [];

    if (!rows.length) return "";

    return `
      <div class="report-beneficiaries">
        <div class="report-subtitle">報告關注個股</div>

        <div class="report-stock-chips">
          ${rows.map(x => `
            <span class="report-stock-chip">
              ${esc(x.name || "")}

              ${
                x.ticker
                  ? `<small>${esc(x.ticker)}</small>`
                  : ""
              }
            </span>
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
          ${arr
            .map(
              x => `
                <li>
                  ${esc(x)}
                </li>
              `
            )
            .join("")}
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
        ? `${
            r.name ||
            ""
          }${
            r.ticker
              ? ` ${r.ticker}`
              : ""
          }`
        : (
            r.title ||
            "產業研究"
          );

    const summary =
      Array.isArray(r.summary)
        ? r.summary
        : [];

    return `
      <article
        class="report-v2-card"
        data-action="${esc(
          r.action ||
          "none"
        )}"
        data-search="${esc(
          [
            r.broker,
            r.title,
            r.name,
            r.ticker,
            ...(
              r.beneficiaries ||
              []
            ).flatMap(
              x => [
                x.name,
                x.ticker
              ]
            )
          ]
            .filter(Boolean)
            .join(" ")
        )}"
      >

        <div class="report-v2-top">
          <div>
            <div class="report-broker">
              ${esc(
                r.broker ||
                "券商研究"
              )}
            </div>

            <div class="report-title">
              ${esc(stockTitle)}
            </div>
          </div>

          <span
            class="
              report-action
              ${actionClass(
                r.action
              )}
            "
          >
            ${esc(action)}
          </span>
        </div>

        <div class="report-meta">

          ${
            r.date
              ? `
                <span>
                  ${esc(r.date)}
                </span>
              `
              : ""
          }

          ${chips(r)}

        </div>

        ${
          summary.length
            ? `
              <ul class="report-summary">
                ${summary
                  .map(
                    x => `
                      <li>
                        ${esc(x)}
                      </li>
                    `
                  )
                  .join("")}
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
                      ${esc(r.detail)}
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
                    href="${esc(
                      r.source_url
                    )}"
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

  async function renderReportsV2() {
    const box =
      $r("#reportList");

    if (!box) {
      return;
    }

    let data = {};

    try {
      const res =
        await fetch(
          "./data/reports.json?v=" +
            Date.now(),
          {
            cache: "no-store"
          }
        );

      data =
        await res.json();

    } catch (e) {
      console.error(
        "reports v2 load failed",
        e
      );

      return;
    }

    const items =
      Array.isArray(
        data.items
      )
        ? data.items
        : [];

    box.classList.add(
      "report-v2-wrap"
    );

    if (!items.length) {
      box.innerHTML = `
        <div class="report-v2-empty">
          尚無已整理的券商報告
        </div>
      `;

      return;
    }

    box.innerHTML = `
      <div class="report-v2-tools">

        <input
          id="reportSearch"
          type="search"
          placeholder="搜尋股票代號、公司、券商或關鍵字"
        >

        <div class="report-v2-tabs">

          <button
            class="
              report-filter
              active
            "
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

      <div id="reportCardsV2">
        ${items
          .map(card)
          .join("")}
      </div>
    `;

    let filter = "all";

    function apply() {
      const q = (
        $r("#reportSearch")
          ?.value ||
        ""
      )
        .trim()
        .toLowerCase();

      document
        .querySelectorAll(
          ".report-v2-card"
        )
        .forEach(
          el => {
            const a =
              el.dataset.action ||
              "";

            const hay = (
              el.dataset.search ||
              ""
            ).toLowerCase();

            const okFilter =
              filter === "all" ||
              a === filter;

            const okSearch =
              !q ||
              hay.includes(q);

            el.hidden =
              !(
                okFilter &&
                okSearch
              );
          }
        );
    }

    $r("#reportSearch")
      ?.addEventListener(
        "input",
        apply
      );

    document
      .querySelectorAll(
        ".report-filter"
      )
      .forEach(
        btn => {
          btn.addEventListener(
            "click",
            () => {
              document
                .querySelectorAll(
                  ".report-filter"
                )
                .forEach(
                  x =>
                    x.classList.remove(
                      "active"
                    )
                );

              btn.classList.add(
                "active"
              );

              filter =
                btn.dataset.filter ||
                "all";

              apply();
            }
          );
        }
      );
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      () =>
        setTimeout(
          renderReportsV2,
          1200
        )
    );
  } else {
    setTimeout(
      renderReportsV2,
      1200
    );
  }

})();
