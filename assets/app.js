const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

const st = {
  period: "1d",
  inst: "foreign",
  market: "twse",
  turn: "twse",
  hm: "twse",
  hk: "400",
  aim: "twse",
  advanced: false,
  openSector: null,
  heatPeriod: "1",
  heatWeightMode: "market"
};

const cache = {};
const shortNames = {};

/* =========================================================
   全站 JSON 共用快取
   - 同一 URL 同時間只送一個 request
   - 一般資料 60 秒記憶體快取
   - sectors 10 分鐘
   - stock_detail 5 分鐘
   - force=true 才真正重新抓
========================================================= */

const jsonCache = new Map();
const jsonInflight = new Map();

function jsonTtl(p) {
  if (p.includes("sectors.json")) return 10 * 60 * 1000;
  if (p.includes("stock_detail.json")) return 5 * 60 * 1000;
  return 60 * 1000;
}

async function J(p, options = {}) {
  const force = options === true || options?.force === true;
  const now = Date.now();
  const hit = jsonCache.get(p);

  if (!force && hit && now - hit.at < jsonTtl(p)) {
    return hit.data;
  }

  if (jsonInflight.has(p)) {
    return jsonInflight.get(p);
  }

  const promise = (async () => {
    try {
      const url = p + (p.includes("?") ? "&" : "?") + "v=" + Date.now();
      const r = await fetch(url, { cache: "no-store" });

      if (!r.ok) throw new Error("HTTP " + r.status);

      const data = await r.json();
      jsonCache.set(p, { data, at: Date.now() });
      return data;
    } catch (e) {
      console.error("JSON load failed:", p, e);
      return hit?.data || {};
    } finally {
      jsonInflight.delete(p);
    }
  })();

  jsonInflight.set(p, promise);
  return promise;
}

window.J = J;

window.invalidateJson = function (p) {
  if (p) jsonCache.delete(p);
  else jsonCache.clear();
};

function pct(v) {
  if (
    v === null ||
    v === undefined ||
    Number.isNaN(Number(v))
  ) return "—";

  v = Number(v);
  return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
}

function cl(v) {
  return Number(v) >= 0 ? "up" : "down";
}

function money(v) {
  if (v === null || v === undefined) return "—";
  return (Number(v) > 0 ? "+" : "") +
    Number(v).toFixed(2) +
    "億";
}

function cleanLegalName(name = "") {
  return String(name)
    .replace(/&#\d+;/g, "")
    .replace(/股份有限公司/g, "")
    .replace(/有限公司/g, "")
    .trim();
}

function displayName(x = {}) {
  const t = String(x.ticker || "");

  if (shortNames[t]) return shortNames[t];

  const raw = cleanLegalName(x.name || "");

  return raw || t || "—";
}

function stock(x, rank) {
  const name = displayName(x);

  return `
    <span style="display:inline-flex;align-items:center;min-width:0">
      ${
        rank
          ? `<span class="rank">${rank}</span>`
          : ""
      }

      <span class="stock">
        <b>${name}</b>
        <span>${x.ticker || ""}</span>
      </span>
    </span>
  `;
}

function emptyRow(text = "目前沒有符合條件的資料") {
  return `
    <tr>
      <td colspan="8">
        <div class="empty">${text}</div>
      </td>
    </tr>
  `;
}

/* ----------------------------- 股票簡稱 ----------------------------- */

async function loadShortNames() {
  const sectors = await J("./data/sectors.json");

  (sectors.sectors || []).forEach(sec => {
    (sec.stocks || []).forEach(x => {
      if (x.ticker && x.name) {
        shortNames[String(x.ticker)] = x.name;
      }
    });
  });
}

/* ----------------------------- 導覽 ----------------------------- */

function page(id) {
  $$(".page").forEach(x =>
    x.classList.toggle("active", x.id === id)
  );

  $$(".nav").forEach(x =>
    x.classList.toggle("active", x.dataset.p === id)
  );

  const nav = $("#mobileNav");

  if (nav) nav.value = id;

  window.scrollTo(0, 0);
}

$$(".nav").forEach(b => {
  b.onclick = () => page(b.dataset.p);
});

if ($("#mobileNav")) {
  $("#mobileNav").onchange = e =>
    page(e.target.value);
}

/* ----------------------------- 時鐘 ----------------------------- */

function clock() {
  const el = $("#clock");

  if (!el) return;

  el.textContent = new Intl.DateTimeFormat(
    "zh-TW",
    {
      timeZone: "Asia/Taipei",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    }
  ).format(new Date());
}

clock();

setInterval(clock, 30000);

/* ----------------------------- 深色模式 ----------------------------- */

function setupTheme() {
  let theme =
    localStorage.getItem("tw-market-theme") ||
    "light";

  document.documentElement.dataset.theme = theme;

  let actions = $(".header-actions");

  if (!actions) {
    actions = document.createElement("div");
    actions.className = "header-actions";

    const clockEl = $("#clock");

    if (clockEl && clockEl.parentNode) {
      clockEl.parentNode.insertBefore(
        actions,
        clockEl.nextSibling
      );
    }
  }

  const btn = document.createElement("button");

  btn.className = "icon-btn";
  btn.id = "themeToggle";
  btn.title = "切換深色模式";

  function icon() {
    btn.textContent =
      document.documentElement.dataset.theme === "dark"
        ? "☀︎"
        : "◐";
  }

  icon();

  btn.onclick = () => {
    const next =
      document.documentElement.dataset.theme === "dark"
        ? "light"
        : "dark";

    document.documentElement.dataset.theme = next;

    localStorage.setItem(
      "tw-market-theme",
      next
    );

    icon();
  };

  actions.appendChild(btn);
}

/* ----------------------------- 回到最上方 ----------------------------- */

function setupToTop() {
  const btn = document.createElement("button");

  btn.id = "toTop";
  btn.innerHTML = "↑";

  btn.setAttribute(
    "aria-label",
    "回到最上方"
  );

  document.body.appendChild(btn);

  window.addEventListener(
    "scroll",
    () => {
      btn.classList.toggle(
        "show",
        window.scrollY > 500
      );
    },
    { passive: true }
  );

  btn.onclick = () =>
    window.scrollTo({
      top: 0,
      behavior: "smooth"
    });
}

/* ----------------------------- 熱力圖顏色 ----------------------------- */

function heatClass(v) {
  if (v === null || v === undefined) {
    return "gray";
  }

  const a = Math.abs(Number(v));

  if (Number(v) >= 0) {
    return a >= 3
      ? "r4"
      : a >= 2
        ? "r3"
        : a >= 1
          ? "r2"
          : "r1";
  }

  return a >= 3
    ? "g4"
    : a >= 2
      ? "g3"
      : a >= 1
        ? "g2"
        : "g1";
}

/* ----------------------------- 總覽 ----------------------------- */

async function home(force = false) {
  const [h, a, ho] = await Promise.all([
    J("./data/heatmap.json", { force }),
    J("./data/ai_picks.json", { force }),
    J("./data/holders.json", { force })
  ]);

  const sectors = [...(h.sectors || [])]
    .filter(
      x =>
        x.change_pct !== null &&
        x.change_pct !== undefined
    )
    .sort(
      (x, y) =>
        Number(y.change_pct) -
        Number(x.change_pct)
    );

  const top = sectors.slice(0, 3);

  const cards = $("#homeCards");

  if (cards) {
    cards.innerHTML = `
      <div class="card metric">
        <small>市場熱力圖</small>
        <strong>
          ${h.sectors?.length || 0} 族群
        </strong>
        <small>盤中每 5 分鐘更新</small>
      </div>

      <div class="card metric">
        <small>AI 選股</small>
        <strong>
          ${
            (a.twse?.length || 0) +
            (a.tpex?.length || 0)
          } 檔
        </strong>
        <small>每天 18:00 更新</small>
      </div>

      <div class="card metric">
        <small>大戶籌碼</small>
        <strong>
          ${ho.complete ? "完整" : "待補"}
        </strong>
        <small>每週六 15:00</small>
      </div>

      <div class="card metric">
        <small>目前最強族群</small>
        <strong>
          ${top[0]?.name || "—"}
        </strong>
        <small class="${cl(top[0]?.change_pct)}">
          ${
            top[0]
              ? pct(top[0].change_pct)
              : "—"
          }
        </small>
      </div>
    `;
  }

  const box = $("#topSectors");

  if (box) {
    box.innerHTML = top
      .map(
        (x, i) => `
          <div class="card metric">
            <small>
              0${i + 1} ${x.name}
            </small>

            <strong class="${cl(x.change_pct)}">
              ${pct(x.change_pct)}
            </strong>

            <small>
              ${
                x.complete
                  ? "完整市值加權"
                  : "部分市值資料待補"
              }
            </small>
          </div>
        `
      )
      .join("");
  }
}

/* ----------------------------- 籌碼日報 ----------------------------- */

async function flows(force = false) {
  const d = await J(
    "./data/institutional.json",
    { force }
  );

  if ($("#flowDate")) {
    $("#flowDate").textContent =
      d.date
        ? `截至 ${d.date}`
        : "尚無資料";
  }

  const g =
    d.periods?.[st.period]?.[st.market]?.[
      st.inst
    ] || {
      buy: [],
      sell: [],
      complete: false,
      days_used: 0
    };

  const need =
    st.period === "1d"
      ? 1
      : st.period === "3d"
        ? 3
        : 5;

  const status = $("#flowStatus");

  if (status) {
    status.className =
      "status" +
      (g.complete ? "" : " warn");

    status.textContent = g.complete
      ? `資料完整 · ${g.days_used} 個交易日`
      : `目前 ${g.days_used || 0} / ${need} 個交易日`;
  }

  function rows(arr) {
    if (!(arr || []).length) {
      return emptyRow();
    }

    return arr
      .map(
        (x, i) => `
          <tr class="${
            x.change_pct < 0
              ? "negative-row"
              : ""
          }">
            <td>
              ${stock(x, i + 1)}

              <div class="mobile-meta">
                ${Math.round(
                  (x.shares || 0) / 1000
                ).toLocaleString()} 張
              </div>
            </td>

            <td
              data-label="估算金額"
              class="${
                x.amount_100m >= 0
                  ? "up"
                  : "down"
              }"
            >
              ${money(x.amount_100m)}
            </td>

            <td data-label="張數">
              ${Math.round(
                (x.shares || 0) / 1000
              ).toLocaleString()}
            </td>

            <td
              data-label="漲跌"
              class="${cl(x.change_pct)}"
            >
              ${pct(x.change_pct)}
            </td>
          </tr>
        `
      )
      .join("");
  }

  if ($("#buyRows")) {
    $("#buyRows").innerHTML =
      rows(g.buy);
  }

  if ($("#sellRows")) {
    $("#sellRows").innerHTML =
      rows(g.sell);
  }
}

$$("[data-period]").forEach(b => {
  b.onclick = () => {
    $$("[data-period]").forEach(x =>
      x.classList.remove("active")
    );

    b.classList.add("active");
    st.period = b.dataset.period;

    flows();
  };
});

$$("[data-inst]").forEach(b => {
  b.onclick = () => {
    $$("[data-inst]").forEach(x =>
      x.classList.remove("active")
    );

    b.classList.add("active");
    st.inst = b.dataset.inst;

    flows();
  };
});

$$("[data-market]").forEach(b => {
  b.onclick = () => {
    $$("[data-market]").forEach(x =>
      x.classList.remove("active")
    );

    b.classList.add("active");
    st.market = b.dataset.market;

    flows();
  };
});

/* ----------------------------- 突然放量 ----------------------------- */

function ensureVolumeCriteria() {
  if ($("#volumeCriteria")) return;

  const status = $("#volStatus");

  if (!status) return;

  const box =
    document.createElement("div");

  box.id = "volumeCriteria";
  box.className = "criteria";

  status.insertAdjacentElement(
    "afterend",
    box
  );
}

function renderVolumeCriteria() {
  ensureVolumeCriteria();

  const box = $("#volumeCriteria");

  if (!box) return;

  if (!st.advanced) {
    box.innerHTML = `
      <b>篩選依據</b>

      <p>
        依「今日成交量 ÷ 前 5 個交易日平均成交量」排序
      </p>

      <div class="criteria-grid">
        <span class="criterion">
          僅追蹤自訂科技股
        </span>

        <span class="criterion">
          量比越高排名越前
        </span>
      </div>
    `;

    return;
  }

  box.innerHTML = `
    <b>進階篩選條件</b>

    <div class="criteria-grid">
      <span class="criterion">
        今日量 ≥ 20日均量 1.3倍
      </span>

      <span class="criterion">
        今日量 ≤ 20日均量 2倍
      </span>

      <span class="criterion">
        3日均量 ＞ 5日均量 ＞ 10日均量
      </span>

      <span class="criterion">
        今日成交量 ≥ 1,000張
      </span>
    </div>

    <p>
      「短期均量多頭排列」代表近期成交熱度持續升高，而不是單日突然爆量
    </p>
  `;
}

async function volume(force = false) {
  const [v, s] = await Promise.all([
    J("./data/volume.json", { force }),
    J("./data/screener.json", { force })
  ]);

  if ($("#volDate")) {
    $("#volDate").textContent =
      v.date || "尚無資料";
  }

  const d =
    st.advanced
      ? s.items || []
      : v.items || [];

  const status = $("#volStatus");

  if (status) {
    status.className =
      "status" +
      (
        (
          st.advanced
            ? !s.complete
            : !v.complete
        )
          ? " warn"
          : ""
      );

    status.textContent =
      st.advanced
        ? (
            s.complete
              ? "20日歷史完整"
              : `進階篩選需要 21 個交易日，目前 ${s.history_days || 0}`
          )
        : (
            v.complete
              ? "前 5 日歷史完整"
              : `突然放量需要 6 個交易日，目前 ${v.history_days || 0}`
          );
  }

  renderVolumeCriteria();

  const rows = $("#volRows");

  if (!rows) return;

  if (!d.length) {
    rows.innerHTML =
      emptyRow(
        "目前沒有符合篩選條件的股票"
      );

    return;
  }

  rows.innerHTML = d
    .map((x, i) => {
      const advText =
        st.advanced
          ? `20日量比 ${Number(
              x.volume_ratio_20d || 0
            ).toFixed(2)}x`
          : "";

      const trendText =
        st.advanced
          ? `3日 ${Number(
              x.avg3 || 0
            ).toLocaleString()} ＞ 5日 ${Number(
              x.avg5 || 0
            ).toLocaleString()} ＞ 10日 ${Number(
              x.avg10 || 0
            ).toLocaleString()}`
          : "";

      return `
        <tr class="${
          x.change_pct < 0
            ? "negative-row"
            : ""
        }">
          <td>
            ${stock(x, i + 1)}

            <div class="mobile-meta">
              今日量
              ${Math.round(
                (x.volume || 0) / 1000
              ).toLocaleString()}張
            </div>
          </td>

          <td
            data-label="漲跌"
            class="${cl(x.change_pct)}"
          >
            ${pct(x.change_pct)}
          </td>

          <td data-label="今日量">
            ${Math.round(
              Number(x.volume || 0) / 1000
            ).toLocaleString()}張
          </td>

          <td data-label="5日量比">
            ${Number(
              x.volume_ratio_5d || 0
            ).toFixed(2)}x
          </td>

          <td
            data-label="${
              st.advanced
                ? "進階條件"
                : "訊號"
            }"
          >
            ${
              st.advanced
                ? `
                  <div>${advText}</div>
                  <div
                    style="
                      font-size:10px;
                      color:var(--muted);
                      margin-top:3px
                    "
                  >
                    ${trendText}
                  </div>
                `
                : (
                    x.low_base
                      ? "低基期"
                      : "—"
                  )
            }
          </td>
        </tr>
      `;
    })
    .join("");
}

if ($("#advanced")) {
  $("#advanced").onclick = () => {
    st.advanced = !st.advanced;

    $("#advanced").classList.toggle(
      "active",
      st.advanced
    );

    $("#advanced").textContent =
      st.advanced
        ? "進階篩選 ✓"
        : "進階篩選 ＋";

    volume();
  };
}

/* ----------------------------- 成交排行 ----------------------------- */

async function turnover(force = false) {
  const d = await J(
    "./data/turnover.json",
    { force }
  );

  if ($("#turnDate")) {
    $("#turnDate").textContent =
      d.date || "尚無資料";
  }

  const arr = d[st.turn] || [];

  const rows = $("#turnRows");

  if (!rows) return;

  if (!arr.length) {
    rows.innerHTML = emptyRow();
    return;
  }

  rows.innerHTML = arr
    .map(
      (x, i) => `
        <tr class="${
          x.change_pct < 0
            ? "negative-row"
            : ""
        }">
          <td>
            ${stock(x, i + 1)}

            <div class="mobile-meta">
              ${x.price || "—"} ·
              ${pct(x.change_pct)}
            </div>
          </td>

          <td data-label="成交金額">
            ${(
              Number(x.turnover || 0) /
              1e8
            ).toFixed(2)}億
          </td>

          <td data-label="成交張數">
            ${Math.round(
              Number(x.volume || 0) /
              1000
            ).toLocaleString()}
          </td>

          <td data-label="收盤">
            ${x.price || "—"}
          </td>

          <td
            data-label="漲跌"
            class="${cl(x.change_pct)}"
          >
            ${pct(x.change_pct)}
          </td>
        </tr>
      `
    )
    .join("");
}

$$("[data-turn]").forEach(b => {
  b.onclick = () => {
    $$("[data-turn]").forEach(x =>
      x.classList.remove("active")
    );

    b.classList.add("active");
    st.turn = b.dataset.turn;

    turnover();
  };
});

/* ----------------------------- 大戶籌碼 ----------------------------- */

async function holders(force = false) {
  const d = await J(
    "./data/holders.json",
    { force }
  );

  if ($("#holderDate")) {
    $("#holderDate").textContent =
      d.date
        ? `${d.date}｜週六 15:00`
        : "週六 15:00";
  }

  const status = $("#holderStatus");

  if (status) {
    status.className =
      "status" +
      (d.complete ? "" : " warn");

    status.textContent =
      d.complete
        ? `比較 ${d.previous_date} → ${d.date}`
        : "需要兩期集保資料才能計算大戶增加";
  }

  const arr =
    d[st.hm]?.[st.hk] || [];

  const rows = $("#holderRows");

  if (!rows) return;

  if (!arr.length) {
    rows.innerHTML = emptyRow();
    return;
  }

  rows.innerHTML = arr
    .map(
      (x, i) => `
        <tr class="${
          x.week_change_pct < 0
            ? "negative-row"
            : ""
        }">
          <td>
            ${stock(x, i + 1)}

            <div class="mobile-meta">
              大戶比
              ${Number(
                x.ratio || 0
              ).toFixed(2)}%
            </div>
          </td>

          <td
            data-label="同期股價"
            class="${cl(
              x.week_change_pct
            )}"
          >
            ${pct(
              x.week_change_pct
            )}
          </td>

          <td data-label="大戶比率">
            ${Number(
              x.ratio || 0
            ).toFixed(2)}%
          </td>

          <td
            data-label="增加"
            class="up"
          >
            +${Number(
              x.delta || 0
            ).toFixed(2)} ppt
          </td>
        </tr>
      `
    )
    .join("");
}

$$("[data-hm]").forEach(b => {
  b.onclick = () => {
    $$("[data-hm]").forEach(x =>
      x.classList.remove("active")
    );

    b.classList.add("active");
    st.hm = b.dataset.hm;

    holders();
  };
});

$$("[data-hk]").forEach(b => {
  b.onclick = () => {
    $$("[data-hk]").forEach(x =>
      x.classList.remove("active")
    );

    b.classList.add("active");
    st.hk = b.dataset.hk;

    holders();
  };
});

/* ----------------------------- AI 選股 ----------------------------- */

function ensureAiCriteria() {
  if ($("#aiCriteria")) return;

  const status = $("#aiStatus");

  if (!status) return;

  const box =
    document.createElement("div");

  box.id = "aiCriteria";
  box.className = "criteria";

  status.insertAdjacentElement(
    "afterend",
    box
  );
}

function aiFactorLabel(key) {
  const map = {
    foreign: "外資",
    trust: "投信",
    dealer: "自營商",
    holders: "大戶籌碼",
    volume_price: "量價",
    turnover: "當日成交熱度",
    turnover_5d: "近5日成交熱度"
  };

  return map[key] || key;
}

function renderAiCriteria(d) {
  ensureAiCriteria();

  const box = $("#aiCriteria");

  if (!box) return;

  const logic = d.logic || {};
  const factors = logic.factors || [];

  const dates =
    (
      logic.institutional_dates ||
      []
    ).join("、");

  const factorHtml =
    factors.length
      ? factors
          .map(
            x => `
              <span class="criterion">
                ${
                  x.label ||
                  aiFactorLabel(x.key)
                }
                ${Number(
                  x.weight_pct || 0
                ).toFixed(0)}%
              </span>
            `
          )
          .join("")
      : `
          <span class="criterion">
            外資 20%
          </span>

          <span class="criterion">
            投信 25%
          </span>

          <span class="criterion">
            自營商 10%
          </span>

          <span class="criterion">
            大戶籌碼 25%
          </span>

          <span class="criterion">
            量價 5%
          </span>

          <span class="criterion">
            成交熱度 15%
          </span>
        `;

  const details =
    logic.details || [];

  box.innerHTML = `
    <details>
      <summary
        style="
          cursor:pointer;
          list-style:none;
          display:flex;
          align-items:center;
          justify-content:space-between;
          gap:10px;
          font-size:12px;
          font-weight:800;
          color:var(--ink)
        "
      >
        <span>
          AI 選股邏輯｜
          ${
            d.mode === "sunday"
              ? "週日版"
              : "交易日版"
          }
        </span>

        <span
          style="
            font-size:10px;
            font-weight:600;
            color:var(--muted)
          "
        >
          點擊展開 ▾
        </span>
      </summary>

      <div
        style="
          margin-top:10px;
          padding-top:10px;
          border-top:1px solid var(--line)
        "
      >
        <p style="margin-top:0">
          股票池：
          ${
            logic.universe ||
            "自訂科技股"
          }
        </p>

        ${
          dates
            ? `
              <p>
                法人計算期間：
                ${dates}
              </p>
            `
            : ""
        }

        <div
          class="criteria-grid"
          style="margin-top:8px"
        >
          ${factorHtml}
        </div>

        ${
          details.length
            ? `
              <div
                style="
                  margin-top:10px;
                  padding-top:9px;
                  border-top:1px solid var(--line);
                  font-size:11px;
                  line-height:1.7;
                  color:var(--muted)
                "
              >
                ${details
                  .map(
                    (x, i) => `
                      <div
                        style="
                          margin-bottom:4px
                        "
                      >
                        ${i + 1}. ${x}
                      </div>
                    `
                  )
                  .join("")}
              </div>
            `
            : ""
        }
      </div>
    </details>
  `;

  const detail =
    box.querySelector("details");

  const hint =
    box.querySelector(
      "summary span:last-child"
    );

  if (detail && hint) {
    detail.addEventListener(
      "toggle",
      () => {
        hint.textContent =
          detail.open
            ? "收起 ▴"
            : "點擊展開 ▾";
      }
    );
  }
}

function aiFactorBreakdown(x) {
  const scores =
    x.factor_scores || {};

  const contributions =
    x.contributions || {};

  const keys =
    Object.keys(contributions);

  if (!keys.length) {
    return `
      <div class="empty">
        尚無因子拆解資料
      </div>
    `;
  }

  const rows = keys
    .map(key => ({
      key,
      label: aiFactorLabel(key),
      score: Number(
        scores[key] || 0
      ),
      contribution: Number(
        contributions[key] || 0
      )
    }))
    .sort(
      (a, b) =>
        b.contribution -
        a.contribution
    );

  return `
    <div
      style="
        margin-top:12px;
        padding-top:10px;
        border-top:1px solid var(--line)
      "
    >
      <div
        style="
          font-size:11px;
          font-weight:800;
          margin-bottom:7px
        "
      >
        因子分數拆解
      </div>

      ${rows
        .map(
          r => `
            <div
              style="
                display:grid;
                grid-template-columns:
                  minmax(88px,1fr)
                  64px
                  72px;
                gap:8px;
                align-items:center;
                padding:6px 0;
                border-bottom:
                  1px solid var(--line);
                font-size:11px
              "
            >
              <div>
                ${r.label}
              </div>

              <div
                style="
                  text-align:right;
                  color:var(--muted)
                "
              >
                ${r.score.toFixed(1)} 分
              </div>

              <div
                style="
                  text-align:right;
                  font-weight:800
                "
              >
                +${r.contribution.toFixed(1)}
              </div>
            </div>
          `
        )
        .join("")}

      <div
        style="
          margin-top:8px;
          font-size:10px;
          line-height:1.6;
          color:var(--muted)
        "
      >
        因子分數為同市場追蹤股的相對百分位分數，「貢獻」為因子分數 × 該因子權重
      </div>
    </div>
  `;
}

async function ai(force = false) {
  const d = await J(
    "./data/ai_picks.json",
    { force }
  );

  const status = $("#aiStatus");

  if (status) {
    status.className =
      "status" +
      (d.complete ? "" : " warn");

    status.textContent =
      d.complete
        ? `${
            d.mode === "sunday"
              ? "週日版"
              : "交易日版"
          } · 資料完整 · ${
            d.logic?.version || ""
          }`
        : "部分來源尚未完整";
  }

  renderAiCriteria(d);

  const arr =
    d[st.aim] || [];

  const box = $("#aiCards");

  if (!box) return;

  if (!arr.length) {
    box.innerHTML = `
      <div class="card empty">
        目前沒有 AI 選股資料
      </div>
    `;

    return;
  }

  box.innerHTML = arr
    .map(
      (x, i) => `
        <div class="card aicard">
          <div class="aitop">
            <div>
              <div
                style="
                  font-size:10px;
                  color:var(--muted);
                  margin-bottom:5px
                "
              >
                #${i + 1}
              </div>

              ${stock(x)}

              <div
                style="
                  font-size:10px;
                  margin-top:6px
                "
                class="${cl(x.change_pct)}"
              >
                今日 ${pct(x.change_pct)}
              </div>
            </div>

            <div style="text-align:right">
              <div class="score">
                ${Number(
                  x.score || 0
                ).toFixed(1)}
              </div>

              <div
                style="
                  font-size:9px;
                  color:var(--muted);
                  margin-top:2px
                "
              >
                相對分數
              </div>
            </div>
          </div>

          <div class="tags">
            ${(x.tags || [])
              .map(
                t => `
                  <span class="tag">
                    ${t}
                  </span>
                `
              )
              .join("")}
          </div>

          <div class="reason">
            <div
              style="
                font-weight:800;
                color:var(--ink);
                margin-bottom:5px
              "
            >
              主要入選原因
            </div>

            <div>
              ${x.reason || "—"}
            </div>

            ${aiFactorBreakdown(x)}

            ${
              x.raw
                ? `
                  <div
                    style="
                      margin-top:10px;
                      padding-top:8px;
                      border-top:
                        1px solid var(--line);
                      font-size:10px;
                      line-height:1.7;
                      color:var(--muted)
                    "
                  >
                    ${
                      x.raw
                        .holder_delta_avg_ppt !==
                      undefined
                        ? `
                          <div>
                            大戶週增幅平均：
                            ${Number(
                              x.raw
                                .holder_delta_avg_ppt ||
                                0
                            ).toFixed(2)}
                            ppt
                          </div>
                        `
                        : ""
                    }

                    ${
                      x.raw
                        .volume_ratio_5d !==
                      undefined
                        ? `
                          <div>
                            5日量比：
                            ${Number(
                              x.raw
                                .volume_ratio_5d ||
                                0
                            ).toFixed(2)}x
                          </div>
                        `
                        : ""
                    }
                  </div>
                `
                : ""
            }

            <div
              style="
                margin-top:10px;
                font-size:10px;
                line-height:1.6;
                color:var(--muted)
              "
            >
              分數僅代表同市場追蹤股的相對強弱，不代表未來上漲機率
            </div>
          </div>
        </div>
      `
    )
    .join("");

  $$(".aicard").forEach(card => {
    card.onclick = () =>
      card.classList.toggle("open");
  });
}

$$("[data-aim]").forEach(b => {
  b.onclick = () => {
    $$("[data-aim]").forEach(x =>
      x.classList.remove("active")
    );

    b.classList.add("active");
    st.aim = b.dataset.aim;

    ai();
  };
});
/* ----------------------------- 市場熱力圖 ----------------------------- */
/*
 * 期間：
 * 當日 / 5日 / 10日 / 20日
 *
 * 權重：
 * 市值加權 / 權重上限
 *
 * 預設：
 * 當日 + 市值加權
 *
 * 市值加權：
 * 完全按照各公司 market_cap 比例
 *
 * 權重上限：
 * 依族群股票家數動態限制單一個股最高權重
 *
 * 1檔     100%
 * 2檔      65%
 * 3檔      50%
 * 4檔      40%
 * 5～6檔   35%
 * 7～9檔   30%
 * 10檔以上 25%
 */

let heatDetailData = null;
let heatDetailPromise = null;

const HEAT_PERIODS = [
  ["1", "當日"],
  ["5", "5日"],
  ["10", "10日"],
  ["20", "20日"]
];

const HEAT_WEIGHT_MODES = [
  ["market", "市值加權"],
  ["capped", "權重上限"]
];

function heatPeriodLabel(
  period = st.heatPeriod
) {
  return period === "1"
    ? "當日"
    : `近${period}日`;
}

function heatWeightModeLabel(
  mode = st.heatWeightMode
) {
  return mode === "capped"
    ? "權重上限"
    : "市值加權";
}

function heatLastNumber(values) {
  if (!Array.isArray(values)) {
    return null;
  }

  for (
    let i = values.length - 1;
    i >= 0;
    i -= 1
  ) {
    const value = values[i];

    if (
      value === null ||
      value === undefined ||
      value === ""
    ) {
      continue;
    }

    const n = Number(value);

    if (Number.isFinite(n)) {
      return n;
    }
  }

  return null;
}

function heatValidNumber(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return null;
  }

  const n = Number(value);

  return Number.isFinite(n)
    ? n
    : null;
}

async function loadHeatDetail(
  force = false
) {
  if (!force && heatDetailData) {
    return heatDetailData;
  }

  if (heatDetailPromise) {
    return heatDetailPromise;
  }

  heatDetailPromise = J(
    "./data/stock_detail.json",
    { force }
  )
    .then(data => {
      if (
        data &&
        typeof data === "object" &&
        Object.keys(data).length
      ) {
        heatDetailData = data;
      }

      return heatDetailData || {};
    })
    .finally(() => {
      heatDetailPromise = null;
    });

  return heatDetailPromise;
}

/* -------------------- 權重計算 -------------------- */

function heatWeightCap(n) {
  if (n <= 1) return 1;
  if (n === 2) return 0.65;
  if (n === 3) return 0.50;
  if (n === 4) return 0.40;
  if (n <= 6) return 0.35;
  if (n <= 9) return 0.30;

  return 0.25;
}

/*
 * 原始市值加權
 * 不做任何 cap
 */

function heatMarketWeights(items) {
  const valid = items.filter(
    x =>
      Number.isFinite(x.cap) &&
      x.cap > 0
  );

  const out = new Map();

  const sum = valid.reduce(
    (total, x) =>
      total + x.cap,
    0
  );

  if (!(sum > 0)) {
    return out;
  }

  valid.forEach(x => {
    out.set(
      x.ticker,
      x.cap / sum
    );
  });

  return out;
}

/*
 * 權重上限模式
 *
 * 超過 cap 的股票先固定在 cap
 * 剩餘權重依其餘股票市值重新分配
 * 持續重算直到沒有股票超過 cap
 */

function heatCappedWeights(items) {
  const valid = items.filter(
    x =>
      Number.isFinite(x.cap) &&
      x.cap > 0
  );

  const out = new Map();

  if (!valid.length) {
    return out;
  }

  const limit =
    heatWeightCap(valid.length);

  let rest = [...valid];
  let left = 1;

  while (
    rest.length &&
    left > 1e-12
  ) {
    const sum = rest.reduce(
      (total, x) =>
        total + x.cap,
      0
    );

    if (!(sum > 0)) {
      const w =
        left / rest.length;

      rest.forEach(x =>
        out.set(
          x.ticker,
          w
        )
      );

      break;
    }

    const over = rest.filter(
      x =>
        (
          left *
          x.cap /
          sum
        ) >
        limit +
        1e-12
    );

    if (!over.length) {
      rest.forEach(x =>
        out.set(
          x.ticker,
          left *
          x.cap /
          sum
        )
      );

      break;
    }

    over.forEach(x =>
      out.set(
        x.ticker,
        limit
      )
    );

    left -=
      limit *
      over.length;

    rest = rest.filter(
      x => !over.includes(x)
    );
  }

  return out;
}

/* -------------------- 個股期間漲跌幅 -------------------- */

function heatStockReturn(
  stock,
  period = st.heatPeriod
) {
  if (!stock) return null;

  if (period === "1") {
    return heatValidNumber(
      stock.change_pct
    );
  }

  const ticker =
    String(stock.ticker || "");

  const detail =
    heatDetailData?.stocks?.[
      ticker
    ];

  if (!detail) return null;

  const values =
    detail
      .returns_by_period?.[
        period
      ] ||
    (
      period === "5"
        ? detail.returns
        : null
    );

  return heatLastNumber(values);
}

/* -------------------- 族群期間漲跌幅 -------------------- */

function heatSectorReturn(
  sector,
  period = st.heatPeriod,
  weightMode = st.heatWeightMode
) {
  const usable =
    (sector?.stocks || [])
      .map(stock => ({
        ticker:
          String(
            stock.ticker || ""
          ),

        cap:
          Number(
            stock.market_cap
          ),

        value:
          heatStockReturn(
            stock,
            period
          )
      }))
      .filter(
        x =>
          x.ticker &&
          Number.isFinite(x.cap) &&
          x.cap > 0 &&
          x.value !== null &&
          Number.isFinite(x.value)
      );

  if (!usable.length) {
    return null;
  }

  const weights =
    weightMode === "capped"
      ? heatCappedWeights(
          usable
        )
      : heatMarketWeights(
          usable
        );

  let total = 0;
  let used = 0;

  usable.forEach(x => {
    const w =
      Number(
        weights.get(x.ticker)
      );

    if (
      !Number.isFinite(w) ||
      w <= 0
    ) {
      return;
    }

    total +=
      x.value * w;

    used += w;
  });

  return used > 0
    ? total / used
    : null;
}

/* -------------------- 大盤／OTC 同期漲跌幅 -------------------- */

/*
 * 當日：
 * 優先使用 heatmap.json 的盤中即時指數
 *
 * 5 / 10 / 20 日：
 * 若後端提供對應期間基準價，
 * 使用最新指數直接計算
 *
 * 若沒有基準價：
 * 使用原本歷史報酬率資料
 *
 * 不使用昨天的當日漲跌幅冒充盤中數字
 */

function heatBenchmarkReturn(
  period = st.heatPeriod,
  market = "twse"
) {
  const live =
    cache.heat?.indices?.[market];

  const benchmark =
    heatDetailData?.benchmark;

  const history =
    market === "twse"
      ? benchmark
      : (
          heatDetailData?.otc_benchmark ||
          heatDetailData?.benchmark_tpex
        );

  if (period === "1") {
    return heatValidNumber(
      live?.change_pct
    );
  }

  const livePrice =
    heatValidNumber(
      live?.price ??
      live?.index ??
      live?.value
    );

  const basePrice =
    heatValidNumber(
      history?.base_prices?.[period]
    );

  if (
    livePrice !== null &&
    livePrice > 0 &&
    basePrice !== null &&
    basePrice > 0
  ) {
    return (
      livePrice / basePrice - 1
    ) * 100;
  }

  const values =
    history
      ?.returns_by_period?.[
        period
      ] ||
    (
      period === "5"
        ? history?.returns
        : null
    );

  return heatLastNumber(values);
}

/* -------------------- 期間顏色 -------------------- */

function heatPeriodThresholds(
  period = st.heatPeriod
) {
  if (period === "1") {
    return [0.5, 1, 2, 3];
  }

  if (period === "5") {
    return [1, 2.5, 5, 8];
  }

  if (period === "10") {
    return [2, 5, 10, 15];
  }

  return [3, 7, 14, 22];
}

function heatPeriodClass(
  value,
  period = st.heatPeriod
) {
  if (
    value === null ||
    value === undefined ||
    !Number.isFinite(
      Number(value)
    )
  ) {
    return "gray";
  }

  const n = Number(value);
  const a = Math.abs(n);

  const t =
    heatPeriodThresholds(
      period
    );

  const level =
    a >= t[3]
      ? 4
      : a >= t[2]
        ? 3
        : a >= t[1]
          ? 2
          : 1;

  return n >= 0
    ? `r${level}`
    : `g${level}`;
}

/* -------------------- 熱力圖控制列 -------------------- */

function ensureHeatPeriodUi() {
  const grid =
    $("#heatGrid");

  if (!grid) return;

  let wrap =
    $("#heatPeriodWrap");

  if (!wrap) {
    wrap =
      document.createElement(
        "div"
      );

    wrap.id =
      "heatPeriodWrap";

    wrap.className =
      "heat-period-wrap";

    wrap.innerHTML = `
      <div class="heat-control-row">

        <div
          class="heat-period-tabs"
          role="tablist"
          aria-label="熱力圖期間"
        >
          ${HEAT_PERIODS
            .map(
              ([key, label]) => `
                <button
                  type="button"
                  class="heat-period-btn"
                  data-heat-period="${key}"
                >
                  ${label}
                </button>
              `
            )
            .join("")}
        </div>

        <div
          class="heat-weight-tabs"
          role="tablist"
          aria-label="熱力圖權重模式"
        >
          ${HEAT_WEIGHT_MODES
            .map(
              ([key, label]) => `
                <button
                  type="button"
                  class="heat-weight-btn"
                  data-heat-weight="${key}"
                >
                  ${label}
                </button>
              `
            )
            .join("")}
        </div>

      </div>

      <div class="heat-period-meta">
        <span
          id="heatWeightDescription"
        ></span>

        <span
          id="heatPeriodBenchmark"
          class="heat-period-benchmark"
        ></span>
      </div>
    `;

    grid.parentNode.insertBefore(
      wrap,
      grid
    );

    wrap.addEventListener(
      "click",
      async event => {

        /* ---------- 期間切換 ---------- */

        const periodButton =
          event.target.closest(
            "[data-heat-period]"
          );

        if (periodButton) {
          const next =
            String(
              periodButton
                .dataset
                .heatPeriod ||
              "1"
            );

          if (
            !HEAT_PERIODS.some(
              ([key]) =>
                key === next
            )
          ) {
            return;
          }

          if (
            next ===
            st.heatPeriod
          ) {
            return;
          }

          st.heatPeriod = next;

          if (
            next !== "1" &&
            !heatDetailData
          ) {
            await loadHeatDetail(
              false
            );
          }

          renderHeat(
            cache.heat || {}
          );

          window.dispatchEvent(
            new CustomEvent(
              "heatmap:period-changed",
              {
                detail: {
                  period:
                    st.heatPeriod,

                  label:
                    heatPeriodLabel(),

                  weightMode:
                    st.heatWeightMode
                }
              }
            )
          );

          return;
        }

        /* ---------- 權重模式切換 ---------- */

        const weightButton =
          event.target.closest(
            "[data-heat-weight]"
          );

        if (weightButton) {
          const nextMode =
            String(
              weightButton
                .dataset
                .heatWeight ||
              "market"
            );

          if (
            !HEAT_WEIGHT_MODES.some(
              ([key]) =>
                key === nextMode
            )
          ) {
            return;
          }

          if (
            nextMode ===
            st.heatWeightMode
          ) {
            return;
          }

          st.heatWeightMode =
            nextMode;

          renderHeat(
            cache.heat || {}
          );

          window.dispatchEvent(
            new CustomEvent(
              "heatmap:weight-changed",
              {
                detail: {
                  period:
                    st.heatPeriod,

                  weightMode:
                    st.heatWeightMode,

                  label:
                    heatWeightModeLabel()
                }
              }
            )
          );
        }
      }
    );
  }

  wrap
    .querySelectorAll(
      "[data-heat-period]"
    )
    .forEach(button => {
      button.classList.toggle(
        "active",
        button.dataset
          .heatPeriod ===
          st.heatPeriod
      );
    });

  wrap
    .querySelectorAll(
      "[data-heat-weight]"
    )
    .forEach(button => {
      button.classList.toggle(
        "active",
        button.dataset
          .heatWeight ===
          st.heatWeightMode
      );
    });

  const description =
    $("#heatWeightDescription");

  if (description) {
    description.textContent =
      st.heatWeightMode ===
      "capped"
        ? "權重上限｜依族群家數限制單一個股最高權重"
        : "市值加權｜完全依公司實際市值占比計算";
  }

  const benchmark =
    $("#heatPeriodBenchmark");

  if (benchmark) {
    const twse =
      heatBenchmarkReturn(
        st.heatPeriod,
        "twse"
      );

    const tpex =
      heatBenchmarkReturn(
        st.heatPeriod,
        "tpex"
      );

    const color = value =>
      value === null
        ? ""
        : value > 0
          ? "up"
          : value < 0
            ? "down"
            : "";

    benchmark.innerHTML = `
      <span>
        大盤${heatPeriodLabel()}漲幅

        <strong class="${color(twse)}">
          ${pct(twse)}
        </strong>
      </span>

      <span style="margin-left:12px">
        OTC${heatPeriodLabel()}漲幅

        <strong class="${color(tpex)}">
          ${pct(tpex)}
        </strong>
      </span>
    `;
  }
}

/* -------------------- 展開族群個股 -------------------- */

function heatDetail(
  sec,
  sectorValue
) {
  const period =
    st.heatPeriod;

  const stocks =
    [...(sec.stocks || [])]
      .map(stock => ({
        ...stock,

        _periodReturn:
          heatStockReturn(
            stock,
            period
          )
      }))
      .sort((a, b) => {
        const av =
          a._periodReturn !== null &&
          Number.isFinite(
            Number(
              a._periodReturn
            )
          )
            ? Number(
                a._periodReturn
              )
            : -999999;

        const bv =
          b._periodReturn !== null &&
          Number.isFinite(
            Number(
              b._periodReturn
            )
          )
            ? Number(
                b._periodReturn
              )
            : -999999;

        return bv - av;
      });

  return `
    <div
      class="heat-detail"
      data-sector="${sec.name}"
    >
      <div class="heat-detail-head">

        <b>
          ${sec.name}

          <span
            class="${cl(
              sectorValue
            )}"
          >
            ${pct(
              sectorValue
            )}
          </span>
        </b>

        <span>
          ${stocks.length} 檔｜
          依${heatPeriodLabel(
            period
          )}漲跌幅排序｜
          ${heatWeightModeLabel()}
        </span>

      </div>

      <div class="heat-stock-list">

        ${stocks
          .map(
            x => `
              <div
                class="heat-stock"
                data-ticker="${x.ticker}"
                data-sector="${sec.name}"
                data-period-return="${
                  x._periodReturn !== null &&
                  Number.isFinite(
                    Number(
                      x._periodReturn
                    )
                  )
                    ? x._periodReturn
                    : ""
                }"
              >
                <div>
                  <span class="n">
                    ${displayName(x)}
                  </span>

                  <span class="t">
                    ${x.ticker}
                  </span>
                </div>

                <span
                  class="v ${
                    x._periodReturn === null
                      ? ""
                      : cl(x._periodReturn)
                  }"
                >
                  ${pct(
                    x._periodReturn
                  )}
                </span>
              </div>
            `
          )
          .join("")}

      </div>
    </div>
  `;
}

/* -------------------- 熱力圖 render -------------------- */

function renderHeat(
  d,
  options = {}
) {
  if (
    !d ||
    !Array.isArray(d.sectors) ||
    !d.sectors.length
  ) {
    return;
  }

  cache.heat = d;

  if ($("#heatTime")) {
    $("#heatTime").textContent =
      d.updated_at ||
      "尚無資料";
  }

  const box =
    $("#heatGrid");

  if (!box) return;

  ensureHeatPeriodUi();

  const mobileHeat =
    window.matchMedia(
      "(max-width: 720px)"
    ).matches;

  box.style.gridAutoRows =
    mobileHeat &&
    st.openSector
      ? "auto"
      : "";

  /*
   * 先記錄目前畫面上的族群順序
   *
   * 點擊展開/收合時使用
   * 避免族群位置跳動
   */

  const currentOrder =
    [
      ...box.querySelectorAll(
        "button.heat[data-sec]"
      )
    ]
      .map(
        button =>
          button.dataset.sec
      )
      .filter(Boolean);

  let sectors =
    [...(d.sectors || [])]
      .map(sec => ({
        ...sec,

        _periodReturn:
          heatSectorReturn(
            sec,
            st.heatPeriod,
            st.heatWeightMode
          )
      }));

  /*
   * 只有展開/收合時 preserveOrder
   *
   * 切換：
   * - 當日 / 5日 / 10日 / 20日
   * - 市值加權 / 權重上限
   *
   * 都會依新的族群漲跌幅重新排序
   */

  if (
    options.preserveOrder &&
    currentOrder.length
  ) {
    const orderMap =
      new Map(
        currentOrder.map(
          (name, index) => [
            name,
            index
          ]
        )
      );

    sectors.sort(
      (a, b) => {
        const ai =
          orderMap.has(a.name)
            ? orderMap.get(a.name)
            : Number
                .MAX_SAFE_INTEGER;

        const bi =
          orderMap.has(b.name)
            ? orderMap.get(b.name)
            : Number
                .MAX_SAFE_INTEGER;

        if (ai !== bi) {
          return ai - bi;
        }

        const av =
          a._periodReturn !== null &&
          Number.isFinite(
            Number(
              a._periodReturn
            )
          )
            ? Number(
                a._periodReturn
              )
            : -999999;

        const bv =
          b._periodReturn !== null &&
          Number.isFinite(
            Number(
              b._periodReturn
            )
          )
            ? Number(
                b._periodReturn
              )
            : -999999;

        return bv - av;
      }
    );
  } else {
    sectors.sort(
      (a, b) => {
        const av =
          a._periodReturn !== null &&
          Number.isFinite(
            Number(
              a._periodReturn
            )
          )
            ? Number(
                a._periodReturn
              )
            : -999999;

        const bv =
          b._periodReturn !== null &&
          Number.isFinite(
            Number(
              b._periodReturn
            )
          )
            ? Number(
                b._periodReturn
              )
            : -999999;

        return bv - av;
      }
    );
  }

  if (!sectors.length) {
    box.innerHTML = `
      <div class="empty">
        目前沒有熱力圖資料
      </div>
    `;

    return;
  }

  let html = "";

  sectors.forEach(
    (x, i) => {
      html += `
        <button
          class="
            heat
            ${
              i === 1
                ? "s5 tall"
                : i === 11
                  ? "s6 tall"
                  : i % 3 === 0
                    ? "s4"
                    : "s3"
            }
            ${heatPeriodClass(
              x._periodReturn,
              st.heatPeriod
            )}
          "
          data-sec="${x.name}"
          data-period-return="${
            x._periodReturn !== null &&
            Number.isFinite(
              Number(
                x._periodReturn
              )
            )
              ? x._periodReturn
              : ""
          }"
          style="min-height:100px"
        >
          <b>
            ${x.name}
          </b>

          <strong>
            ${pct(
              x._periodReturn
            )}
          </strong>

          <small>
            ${
              x.complete
                ? `${
                    x.stocks
                      ?.length || 0
                  }檔`
                : `${
                    x.stocks
                      ?.length || 0
                  }檔 · 市值待補${
                    x.missing
                      ?.length || 0
                  }`
            }
          </small>
        </button>
      `;

      if (
        st.openSector ===
        x.name
      ) {
        html += heatDetail(
          x,
          x._periodReturn
        );
      }
    }
  );

  box.innerHTML = html;

  /*
   * 點族群只展開/收合
   * 不重新改變族群順序
   */

  box
    .querySelectorAll(
      "button.heat[data-sec]"
    )
    .forEach(button => {
      button.onclick = () => {
        st.openSector =
          st.openSector ===
          button.dataset.sec
            ? null
            : button.dataset.sec;

        renderHeat(
          cache.heat || d,
          {
            preserveOrder: true
          }
        );

        window.dispatchEvent(
          new CustomEvent(
            "heatmap:detail-rendered",
            {
              detail: {
                period:
                  st.heatPeriod,

                weightMode:
                  st.heatWeightMode,

                sector:
                  st.openSector
              }
            }
          )
        );
      };
    });

  const oldSection =
    $("#heatTitle")
      ?.closest(".section");

  if (oldSection) {
    oldSection.style.display =
      "none";
  }

  const oldTable =
    $("#heatRows")
      ?.closest(".card");

  if (oldTable) {
    oldTable.style.display =
      "none";
  }
}

/* -------------------- 熱力圖資料載入 -------------------- */

async function heat(
  force = false
) {
  const [d] =
    await Promise.all([
      J(
        "./data/heatmap.json",
        { force }
      ),

      loadHeatDetail(force)
    ]);

  if (
    Array.isArray(d?.sectors) &&
    d.sectors.length
  ) {
    renderHeat(d);
  }
}

/*
 * 給其他 heatmap module 使用
 */

window.getHeatmapActivePeriod =
  () =>
    String(
      st.heatPeriod || "1"
    );

window.getHeatmapWeightMode =
  () =>
    String(
      st.heatWeightMode ||
      "market"
    );

window.renderHeatCurrentPeriod =
  () =>
    renderHeat(
      cache.heat || {}
    );

/* ----------------------------- 券商報告 ----------------------------- */

async function reports(force = false) {
  const d = await J(
    "./data/reports.json",
    { force }
  );

  const map = {
    upgrade: "上調",
    downgrade: "下調",
    initiate: "初評",
    maintain: "維持"
  };

  const box = $("#reportList");

  if (!box) return;

  if (!(d.items || []).length) {
    box.innerHTML = `
      <div class="report">
        <div class="rmain">
          <div class="rtitle">
            尚無券商報告
          </div>

          <div class="rmeta">
            收到 PDF 或連結後即會整理至此
          </div>
        </div>
      </div>
    `;

    return;
  }

  box.innerHTML = d.items
    .map(
      r => `
        <div class="report">

          <div class="broker">
            ${r.broker || ""}
          </div>

          <div class="rmain">

            <div class="rtitle">
              ${r.broker || ""}
              ${map[r.action] || r.action || ""}
              ${r.name || ""}
              ${r.ticker || ""}
            </div>

            <div class="rmeta">
              ${r.summary || ""}
              ${
                r.date
                  ? ` · ${r.date}`
                  : ""
              }
            </div>

          </div>

          <div class="tp">
            ${
              r.target_price
                ? `目標價 ${r.target_price}`
                : ""
            }
          </div>

        </div>
      `
    )
    .join("");
}

/* ----------------------------- Lazy Load ----------------------------- */

const pageLoaders = {
  home,
  flows,
  volume,
  turnover,
  holders,
  ai,
  heat,
  reports
};

const loadedPages =
  new Set();

const loadingPages =
  new Map();

async function loadPageOnce(id) {
  const fn =
    pageLoaders[id];

  if (
    !fn ||
    loadedPages.has(id)
  ) {
    return;
  }

  if (
    loadingPages.has(id)
  ) {
    return loadingPages.get(id);
  }

  const promise =
    Promise.resolve()
      .then(() => fn())
      .then(() => {
        loadedPages.add(id);
      })
      .catch(err => {
        console.error(
          "[lazy page]",
          id,
          err
        );
      })
      .finally(() => {
        loadingPages.delete(id);
      });

  loadingPages.set(
    id,
    promise
  );

  return promise;
}

function loadCurrentPage() {
  const active =
    document.querySelector(
      ".page.active"
    );

  if (active) {
    loadPageOnce(
      active.id
    );
  }
}

const originalPage = page;

page = function (id) {
  originalPage(id);

  requestAnimationFrame(
    () => loadPageOnce(id)
  );
};

window.markPageLoaded =
  function (id) {
    if (id) {
      loadedPages.add(id);
    }
  };

window.invalidatePage =
  function (id) {
    if (id) {
      loadedPages.delete(id);
    }
  };

/* ----------------------------- 熱力圖每 5 分鐘更新 ----------------------------- */

/*
 * 只重新抓 heatmap.json
 *
 * 不重複執行其他頁面
 * 不重新抓全部資料
 * 不影響其他功能
 *
 * 當頁面重新回到前景時，
 * 如果距離上次更新已超過 5 分鐘，
 * 才補抓一次
 */

let heatRefreshing = false;
let lastHeatRefresh = 0;

const HEAT_REFRESH_INTERVAL =
  5 * 60 * 1000;

async function refreshHeatmapLive(
  force = false
) {
  if (heatRefreshing) {
    return;
  }

  if (document.hidden) {
    return;
  }

  const now = Date.now();

  if (
    !force &&
    now - lastHeatRefresh <
      HEAT_REFRESH_INTERVAL
  ) {
    return;
  }

  heatRefreshing = true;

  try {
    const d = await J(
      "./data/heatmap.json",
      { force: true }
    );

    if (
      !Array.isArray(d?.sectors) ||
      !d.sectors.length
    ) {
      return;
    }

    lastHeatRefresh = Date.now();

    cache.heat = d;

    const activePage =
      document.querySelector(
        ".page.active"
      );

    if (
      activePage?.id === "heat"
    ) {
      renderHeat(d);
    }

    window.dispatchEvent(
      new CustomEvent(
        "heatmap:data-updated",
        {
          detail: {
            updatedAt:
              d.updated_at || null,

            indices:
              d.indices || null,

            period:
              st.heatPeriod,

            weightMode:
              st.heatWeightMode
          }
        }
      )
    );
  } catch (error) {
    console.warn(
      "[heatmap refresh]",
      error
    );
  } finally {
    heatRefreshing = false;
  }
}

setInterval(
  () => {
    refreshHeatmapLive();
  },
  HEAT_REFRESH_INTERVAL
);

document.addEventListener(
  "visibilitychange",
  () => {
    if (!document.hidden) {
      refreshHeatmapLive();
    }
  }
);

/* ----------------------------- 啟動 ----------------------------- */

async function init() {
  setupTheme();
  setupToTop();

  /*
   * 先載入目前頁面
   * 不再等待 sectors.json
   * 避免整個網站首屏卡住
   */
  loadCurrentPage();

  /*
   * 股票簡稱背景載入
   */
  loadShortNames()
    .catch(err => {
      console.warn(
        "[short names]",
        err
      );
    });
}

init();
