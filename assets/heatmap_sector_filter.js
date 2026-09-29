/* =========================================================
   市場熱力圖：族群下拉 + PCB 細分
   2026-09-29 final
   ========================================================= */

(function () {
  const $h = s => document.querySelector(s);

  let sectorConfig = [];
  let selectedSector = "all";
  let selectedSubgroup = "all";
  let applying = false;

  async function loadSectorConfig() {
    try {
      const r = await fetch(
        "./data/sectors.json?v=" + Date.now(),
        { cache: "no-store" }
      );

      if (!r.ok) {
        throw new Error("HTTP " + r.status);
      }

      const d = await r.json();

      sectorConfig =
        d.sectors || [];

      return sectorConfig;
    } catch (e) {
      console.error(
        "sector selector load failed",
        e
      );

      sectorConfig = [];

      return [];
    }
  }

  function findSector(name) {
    return sectorConfig.find(
      x =>
        x.name === name
    );
  }

  function directHeatButtons() {
    const grid =
      $h("#heatGrid");

    if (!grid) {
      return [];
    }

    return [
      ...grid.children
    ].filter(
      el =>
        el.matches?.(
          "button.heat[data-sec]"
        )
    );
  }

  function updateStaticLabels() {
    const count =
      sectorConfig.length;

    const heatHero =
      $h("#heat .hero p");

    if (heatHero) {
      heatHero.textContent =
        `${count} 個自訂族群｜市值加權｜紅漲綠跌｜可直接下拉選族群`;
    }

    const revenueHero =
      $h(
        "#monthlyRevenue .hero p"
      );

    if (revenueHero) {
      revenueHero.textContent =
        `${count} 個科技族群｜最新已公布月份｜營收、MoM、YoY`;
    }

    document
      .querySelectorAll(
        ".feature-card"
      )
      .forEach(card => {
        const title =
          card.querySelector(
            ".feature-copy b"
          )?.textContent
            ?.trim();

        const small =
          card.querySelector(
            ".feature-copy small"
          );

        if (!small) {
          return;
        }

        if (
          title ===
          "市場熱力圖"
        ) {
          small.textContent =
            `${count}族群・5分鐘`;
        }

        if (
          title ===
          "月營收公布"
        ) {
          small.textContent =
            `${count}族群`;
        }
      });
  }

  function ensureControls() {
    const grid =
      $h("#heatGrid");

    if (
      !grid ||
      $h("#heatSectorControl")
    ) {
      return;
    }

    const wrap =
      document.createElement(
        "div"
      );

    wrap.id =
      "heatSectorControl";

    wrap.className =
      "heat-sector-control";

    wrap.innerHTML = `
      <div class="heat-sector-copy">
        <span class="heat-sector-kicker">
          SECTOR FILTER
        </span>

        <strong>
          選擇想看的族群
        </strong>

        <small id="heatSectorMeta">
          ${sectorConfig.length} 個自訂族群
        </small>
      </div>

      <div class="heat-sector-actions">
        <label
          class="heat-sector-select-wrap"
          for="heatSectorSelect"
        >
          <span>
            族群
          </span>

          <select
            id="heatSectorSelect"
            aria-label="選擇熱力圖族群"
          >
            <option value="all">
              全部族群
            </option>

            ${sectorConfig
              .map(
                sec => `
                  <option
                    value="${sec.name}"
                  >
                    ${sec.name}
                  </option>
                `
              )
              .join("")}
          </select>
        </label>

        <button
          id="heatSectorReset"
          class="heat-sector-reset"
          type="button"
        >
          全部
        </button>
      </div>
    `;

    grid.parentNode.insertBefore(
      wrap,
      grid
    );

    $h("#heatSectorSelect")
      ?.addEventListener(
        "change",
        e => {
          selectedSector =
            e.target.value;

          selectedSubgroup =
            "all";

          rerenderSelected();
        }
      );

    $h("#heatSectorReset")
      ?.addEventListener(
        "click",
        () => {
          selectedSector =
            "all";

          selectedSubgroup =
            "all";

          const sel =
            $h(
              "#heatSectorSelect"
            );

          if (sel) {
            sel.value =
              "all";
          }

          rerenderSelected();
        }
      );
  }

  function rerenderSelected() {
    /*
      app.js 的 st / heat()
      是原本既有熱力圖邏輯

      這裡只控制 openSector
      不改熱力圖計算方式
    */

    try {
      if (
        typeof st !==
        "undefined"
      ) {
        st.openSector =
          selectedSector ===
          "all"
            ? null
            : selectedSector;
      }

      if (
        typeof heat ===
        "function"
      ) {
        Promise
          .resolve(
            heat()
          )
          .finally(
            () => {
              setTimeout(
                () => {
                  applySectorFilter();
                  injectSubgroupControl();
                },
                20
              );
            }
          );

        return;
      }
    } catch (e) {
      console.warn(
        "heat rerender fallback",
        e
      );
    }

    applySectorFilter();
    injectSubgroupControl();
  }

  function applySectorFilter() {
    if (applying) {
      return;
    }

    applying = true;

    directHeatButtons()
      .forEach(
        btn => {
          btn.hidden =
            selectedSector !==
              "all" &&
            btn.dataset.sec !==
              selectedSector;
        }
      );

    const meta =
      $h(
        "#heatSectorMeta"
      );

    if (meta) {
      meta.textContent =
        selectedSector ===
        "all"
          ? `${sectorConfig.length} 個自訂族群`
          : `目前：${selectedSector}`;
    }

    const reset =
      $h(
        "#heatSectorReset"
      );

    if (reset) {
      reset.classList.toggle(
        "active",
        selectedSector !==
          "all"
      );
    }

    applying = false;
  }

  function injectSubgroupControl() {
    if (
      selectedSector ===
      "all"
    ) {
      return;
    }

    const detail =
      $h(
        "#heatGrid .heat-detail"
      );

    if (!detail) {
      return;
    }

    const sector =
      findSector(
        selectedSector
      );

    const groups =
      sector?.subgroups ||
      [];

    if (!groups.length) {
      return;
    }

    if (
      detail.querySelector(
        ".heat-subgroup-control"
      )
    ) {
      filterSubgroupStocks();

      return;
    }

    const control =
      document.createElement(
        "div"
      );

    control.className =
      "heat-subgroup-control";

    control.innerHTML = `
      <div>
        <span
          class="heat-subgroup-kicker"
        >
          SUB-SECTOR
        </span>

        <b>
          ${sector.name}
        </b>
      </div>

      <label
        class="heat-subgroup-select-wrap"
      >
        <span>
          細分類
        </span>

        <select
          id="heatSubgroupSelect"
          aria-label="選擇細分產業"
        >
          <option value="all">
            全部成分
          </option>

          ${groups
            .map(
              g => `
                <option
                  value="${g.name}"
                >
                  ${g.name}
                </option>
              `
            )
            .join("")}
        </select>
      </label>
    `;

    const list =
      detail.querySelector(
        ".heat-stock-list"
      );

    if (!list) {
      return;
    }

    detail.insertBefore(
      control,
      list
    );

    const select =
      control.querySelector(
        "#heatSubgroupSelect"
      );

    if (select) {
      select.value =
        selectedSubgroup;

      select.addEventListener(
        "change",
        e => {
          selectedSubgroup =
            e.target.value;

          filterSubgroupStocks();
        }
      );
    }

    filterSubgroupStocks();
  }

  function filterSubgroupStocks() {
    const detail =
      $h(
        "#heatGrid .heat-detail"
      );

    const sector =
      findSector(
        selectedSector
      );

    if (
      !detail ||
      !sector
    ) {
      return;
    }

    const group =
      (
        sector.subgroups ||
        []
      ).find(
        g =>
          g.name ===
          selectedSubgroup
      );

    const allowed =
      group
        ? new Set(
            (
              group.tickers ||
              []
            ).map(
              String
            )
          )
        : null;

    const rows = [
      ...detail.querySelectorAll(
        ".heat-stock"
      )
    ];

    let visible = 0;

    rows.forEach(
      row => {
        const ticker =
          row.querySelector(
            ".t"
          )?.textContent
            ?.trim();

        const show =
          !allowed ||
          allowed.has(
            String(
              ticker
            )
          );

        row.hidden =
          !show;

        if (show) {
          visible += 1;
        }
      }
    );

    const meta =
      detail.querySelector(
        ".heat-detail-head > span"
      );

    if (meta) {
      meta.textContent =
        selectedSubgroup ===
          "all"
          ? `${rows.length} 檔｜依漲跌幅排序`
          : `${selectedSubgroup}｜${visible} 檔｜依漲跌幅排序`;
    }
  }

  function observeHeatmap() {
    const grid =
      $h(
        "#heatGrid"
      );

    if (!grid) {
      return;
    }

    const observer =
      new MutationObserver(
        () => {
          if (applying) {
            return;
          }

          applySectorFilter();

          setTimeout(
            injectSubgroupControl,
            0
          );
        }
      );

    observer.observe(
      grid,
      {
        childList: true,
        subtree: true
      }
    );
  }

  async function init() {
    await loadSectorConfig();

    ensureControls();
    updateStaticLabels();
    observeHeatmap();

    let tries = 0;

    const wait =
      setInterval(
        () => {
          tries += 1;

          ensureControls();
          updateStaticLabels();

          if (
            directHeatButtons()
              .length
          ) {
            applySectorFilter();

            clearInterval(
              wait
            );
          }

          if (
            tries > 30
          ) {
            clearInterval(
              wait
            );
          }
        },
        150
      );
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      init
    );
  } else {
    init();
  }
})();
